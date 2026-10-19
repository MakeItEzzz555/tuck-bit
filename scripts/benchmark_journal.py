"""Private, atomic, fail-closed progress ledger for opt-in native benchmarks.

Only validated, redacted benchmark receipts and nonsecret run identifiers persist.
A process killed during a provider call leaves an in-flight marker; it is never
silently interpreted as a failed/successful completed result or rerun.
"""
import json
import fcntl
import re
import os
from pathlib import Path
import stat
import tempfile

from benchmark import CASES, MODES, validate_run

MAX_BYTES = 2 * 1024 * 1024


class JournalError(ValueError):
    pass


def _key(entry):
    return (entry["case"], entry["trial"], entry["mode"])


def _validate_marker(item):
    if (not isinstance(item, dict) or set(item) != {"case", "trial", "mode", "identity"}
            or not isinstance(item["case"], str) or item["case"] not in CASES
            or not isinstance(item["mode"], str) or item["mode"] not in MODES
            or type(item["trial"]) is not int or not 1 <= item["trial"] <= 1000):
        raise JournalError("Invalid benchmark trial marker")
    if (not isinstance(item["identity"], dict)
            or set(item["identity"]) != {"task_sha256", "source_sha256", "environment_sha256", "model_sha256", "permissions_sha256"}
            or any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None for value in item["identity"].values())):
        raise JournalError("Invalid marker identity")


class BenchmarkJournal:
    def __init__(self, path, run_sha256, resume=False, acknowledge_incomplete=False):
        self.path = Path(path).expanduser().absolute()
        self.run_sha256 = run_sha256
        if not self.path.parent.is_dir() or self.path.parent.is_symlink():
            raise JournalError("Journal parent must be an existing real directory")
        if self.path.is_symlink():
            raise JournalError("Symlink journal path refused")
        self._lock_fd = None
        try:
            self._acquire_lock()
            if resume:
                if not self.path.exists():
                    raise JournalError("Cannot resume: no durable journal found")
                info = self.path.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES or info.st_mode & 0o077:
                    raise JournalError("Journal must be a bounded private regular file")
                with self.path.open("rb") as handle:
                    data = handle.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise JournalError("Oversized journal")
                try:
                    self.document = json.loads(data)
                    self._validate()
                except (ValueError, TypeError, KeyError) as exc:
                    raise JournalError("Invalid or incompatible resume journal") from exc
                if self.document["run_sha256"] != run_sha256:
                    raise JournalError("Run identity differs: model/configuration/fixtures/implementation changed")
                if self.document["inflight"] is not None:
                    if not acknowledge_incomplete:
                        raise JournalError("Unresolved in-flight call: use --ack-incomplete to preserve it without rerunning")
                    self.document["interrupted"].append(self.document["inflight"])
                    self.document["order"].append(self.document["inflight"])
                    self.document["inflight"] = None
                    self._save()
            else:
                if self.path.exists() or self.path.is_symlink():
                    raise JournalError("Existing journal refused; --resume is required")
                self.document = {"schema": 1, "run_sha256": run_sha256,
                                 "runs": [], "inflight": None, "interrupted": [], "order": []}
                self._save()
        except BaseException:
            self.close()
            raise

    def _acquire_lock(self):
        lock_path = self.path.with_name(self.path.name + ".lock")
        if lock_path.is_symlink():
            raise JournalError("Symlink journal lock refused")
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise JournalError("Journal lock must be a private regular file")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise JournalError("Another execution owns this journal") from exc
            self._lock_fd = fd
        except BaseException:
            os.close(fd)
            raise

    def close(self):
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def __enter__(self):
        if self._lock_fd is None:
            raise JournalError("Journal ownership has been released")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _owned(self):
        if self._lock_fd is None:
            raise JournalError("Journal ownership has been released")

    def _validate(self):
        doc = self.document
        if (not isinstance(doc, dict) or set(doc) != {"schema", "run_sha256", "runs", "inflight", "interrupted", "order"}
                or type(doc["schema"]) is not int or doc["schema"] != 1
                or not isinstance(doc["run_sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", doc["run_sha256"]) is None
                or not isinstance(doc["runs"], list) or len(doc["runs"]) > 1000
                or not isinstance(doc["interrupted"], list) or len(doc["interrupted"]) > 1000
                or not isinstance(doc["order"], list) or len(doc["order"]) > 1000):
            raise JournalError("Unexpected journal schema")
        for run in doc["runs"]:
            validate_run(run)
        keys = [_key(run) for run in doc["runs"]]
        pending = [doc["inflight"]] if doc["inflight"] is not None else []
        for item in doc["interrupted"] + pending:
            _validate_marker(item)
            keys.append(_key(item))
        if len(keys) != len(set(keys)):
            raise JournalError("Duplicate trial slots")
        for item in doc["order"]:
            _validate_marker(item)
        expected = { _key(item): item["identity"] for item in doc["interrupted"] }
        expected.update({_key(item): item["identity"] for item in doc["runs"]})
        if (len(doc["order"]) != len(expected) or
                any(not isinstance(item, dict) or set(item) != {"case", "trial", "mode", "identity"}
                    or expected.get(_key(item)) != item["identity"] for item in doc["order"]) or
                len({_key(item) for item in doc["order"]}) != len(doc["order"])):
            raise JournalError("Journal completion order is inconsistent")

    def _save(self):
        self._owned()
        self._validate()
        payload = (json.dumps(self.document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(payload) > MAX_BYTES:
            raise JournalError("Journal exceeds size bound")
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=".tuckbit-journal-",
                                             delete=False) as handle:
                temp_path = Path(handle.name)
                os.fchmod(handle.fileno(), 0o600)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.is_symlink():
                raise JournalError("Symlink journal path refused")
            os.replace(temp_path, self.path)
            temp_path = None
            fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def marker(self, case, trial, mode, identity):
        marker = {"case": case, "trial": trial, "mode": mode, "identity": identity}
        _validate_marker(marker)
        return {**marker, "identity": dict(identity)}

    def start(self, marker):
        self._owned()
        _validate_marker(marker)
        if self.document["inflight"] is not None or self.has(marker):
            raise JournalError("Trial is already recorded or in flight")
        self.document["inflight"] = {**marker, "identity": dict(marker["identity"])}
        self._save()

    def complete(self, receipt):
        self._owned()
        validate_run(receipt)
        pending = self.document["inflight"]
        if pending is None or _key(pending) != _key(receipt) or pending["identity"] != receipt["identity"]:
            raise JournalError("Result cannot be attributed to the in-flight trial")
        self.document["runs"].append(json.loads(json.dumps(receipt)))
        self.document["order"].append(pending)
        self.document["inflight"] = None
        self._save()

    def has(self, marker):
        return any(_key(entry) == _key(marker) for entry in self.document["runs"] + self.document["interrupted"])

    def check_slot(self, marker, expected_index):
        entries = self.document["order"]
        matches = [entry for entry in entries if _key(entry) == _key(marker)]
        if matches and matches[0]["identity"] != marker["identity"]:
            raise JournalError("Stored trial identity mismatch")
        # A resume must be a strict chronological prefix, without jumping over missing slots.
        if expected_index < len(entries):
            expected = entries[expected_index]
            if _key(expected) != _key(marker) or expected["identity"] != marker["identity"]:
                raise JournalError("Journal does not match ordered trial schedule")
            return True
        if expected_index != len(entries):
            raise JournalError("Missing intermediate benchmark trials")
        return False

    @property
    def runs(self):
        return list(self.document["runs"])

    @property
    def interrupted(self):
        return list(self.document["interrupted"])
