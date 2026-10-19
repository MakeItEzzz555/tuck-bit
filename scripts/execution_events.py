"""V5 privacy-safe public tool observations; never execute commands or retain payloads."""
from collections import Counter
from contextlib import ExitStack
import copy
import hashlib
import hmac
import os
from pathlib import Path
import re
import stat
import time

from trace_profiler import ProfileError, MAX_EVENTS

CATEGORIES = {"search_discovery", "file_inspection", "skill_instructions", "mcp_discovery",
              "source_modification", "tests_builds", "validation_review", "retry_recovery",
              "orchestration_handoff", "other"}
STAGES = {"discovered", "recommended", "selected", "instructions_read", "invoked", "result_verified"}
HEX = re.compile(r"[0-9a-f]{64}")


def read_study_key(path):
    from trace_profiler import read_text
    if not path or Path(path).stat().st_mode & 0o077:
        raise ProfileError("Study key must be an explicit owner-private file")
    encoded = read_text(path).strip()
    if re.fullmatch(r'[0-9a-f]{64}', encoded) is None:
        raise ProfileError("Study key must contain 64 hexadecimal characters")
    return bytes.fromhex(encoded)


def hashed(value):
    return hashlib.sha256(value).hexdigest()


def _digest(value, nullable=False):
    return nullable and value is None or isinstance(value, str) and HEX.fullmatch(value) is not None


def _number(value):
    return value is None or type(value) is int and 0 <= value <= 10**12


def validate(value):
    if (not isinstance(value, dict) or set(value) != {"schema", "source", "complete", "calls", "observer_ns"}
            or value["schema"] != 5 or type(value["schema"]) is not int
            or value["source"] not in {"native_public_events", "controlled_public_events"}
            or type(value["complete"]) is not bool or not _number(value["observer_ns"])
            or value["observer_ns"] is None or not isinstance(value["calls"], list) or len(value["calls"]) > MAX_EVENTS):
        raise ProfileError("Invalid execution observation envelope")
    ids = set()
    for c in value["calls"]:
        if (not isinstance(c, dict) or set(c) != {"id", "agent", "category", "operation", "success", "output_bytes",
                "duration_ms", "result", "evidence", "capabilities"}
                or not _digest(c["id"]) or c["id"] in ids or not _digest(c["agent"], True)
                or c["category"] not in CATEGORIES or not _digest(c["operation"], True)
                or c["success"] is not None and type(c["success"]) is not bool
                or not all(_number(c[k]) for k in ("output_bytes", "duration_ms"))
                or not _digest(c["result"], True) or not isinstance(c["capabilities"], list)
                or len(c["capabilities"]) > 20):
            raise ProfileError("Invalid public tool record")
        ids.add(c["id"])
        for cap in c["capabilities"]:
            if (not isinstance(cap, dict) or set(cap) != {"id", "stage"}
                    or not _digest(cap["id"]) or cap["stage"] not in STAGES):
                raise ProfileError("Invalid capability transition")
        e = c["evidence"]
        if e is not None and (not isinstance(e, dict) or set(e) != {"source", "selector", "revision", "content", "delivered", "truncated", "bytes", "tokens"}
                or not all(_digest(e[k]) for k in ("source", "selector", "revision", "content"))
                or type(e["delivered"]) is not bool
                or e["truncated"] is not None and type(e["truncated"]) is not bool
                or not _number(e["bytes"]) or not _number(e["tokens"])
                or e["delivered"] and (c["success"] is not True or e["truncated"] is not False)):
            raise ProfileError("Invalid file evidence")
    return value


def summarize(value, reviews=None):
    """Review judgments are separate attestations, never inferred model intentions."""
    validate(value)
    reviews = {} if reviews is None else reviews
    if not isinstance(reviews, dict) or set(reviews) - {c["id"] for c in value["calls"]}:
        raise ProfileError("Review must bind observed call identifiers")
    for review in reviews.values():
        if (not isinstance(review, dict) or set(review) != {"receipt", "purpose", "relevance", "unnecessary"}
                or not _digest(review["receipt"]) or review["purpose"] not in {"unknown", "required_verification"}
                or review["relevance"] not in {"unknown", "relevant", "irrelevant"}
                or review["unnecessary"] is not None and type(review["unnecessary"]) is not bool
                or review["purpose"] == "required_verification" and review["unnecessary"] is True):
            raise ProfileError("Invalid independent review attestation")
    categories = {name: Counter() for name in sorted(CATEGORIES)}
    last, available, other_agents, operations = {}, set(), {}, set()
    reads, counts, lifecycle = [], Counter(), {}
    for c in value["calls"]:
        category = categories[c["category"]]
        category["calls"] += 1
        category["successful"] += c["success"] is True
        category["failed"] += c["success"] is False
        category["unknown_status"] += c["success"] is None
        for metric in ("output_bytes", "duration_ms"):
            if c[metric] is not None:
                category[metric+"_observed"] += c[metric]
                category[metric+"_coverage"] += 1
        review = reviews.get(c["id"], {})
        activation = any(cap['stage'] in {'instructions_read', 'invoked'} for cap in c['capabilities'])
        counts['independently_irrelevant_activation'] += activation and review.get('relevance') == 'irrelevant'
        counts['independently_unnecessary_activation'] += activation and review.get('unnecessary') is True
        category["independently_unnecessary"] += review.get("unnecessary") is True
        counts["independently_unnecessary"] += review.get("unnecessary") is True
        # This is an investigation flag, including legitimate repeated tests.
        op = (c["agent"], c["category"], c["operation"], c["result"])
        potential = c["operation"] is not None and c["result"] is not None and op in operations
        category["potential_repeated_calls"] += potential
        if c["success"] is True:
            operations.add(op)
        for cap in c["capabilities"]:
            lifecycle.setdefault(cap["id"], {stage: None for stage in sorted(STAGES)})[cap["stage"]] = True
        e = c["evidence"]
        if e is None:
            continue
        key = (c["agent"], e["source"], e["selector"])
        exact = (*key, e["revision"], e["content"])
        prev = last.get(key)
        previous = exact in available if c["agent"] is not None else None
        changed = prev["revision"] != e["revision"] if prev else None
        required = review.get("purpose") == "required_verification"
        if not e["delivered"]:
            classification = "unknown_purpose_reread" if prev else "unverified_delivery"
        elif required:
            classification = "required_verification"
        elif prev and prev["truncated"] is True and not changed and e["delivered"]:
            classification = "truncated_output_recovery"
        elif c["agent"] is None and prev:
            classification = "unknown_purpose_reread"
        elif changed and e["delivered"]:
            classification = "changed_source_reread"
        elif previous and e["delivered"]:
            classification = "identical_unchanged_source_reread"
        elif prev:
            classification = "unknown_purpose_reread"
        else:
            classification = "first_observed_access"
        counts[classification] += 1
        counts["potential_redundant_unchanged_rereads"] += classification == "identical_unchanged_source_reread"
        counts["relevant_context"] += review.get("relevance") == "relevant"
        counts["irrelevant_context"] += review.get("relevance") == "irrelevant"
        counts["unknown_relevance_context"] += review.get("relevance", "unknown") == "unknown"
        cross_key = (e["source"], e["selector"], e["revision"], e["content"])
        across = bool(other_agents.get(cross_key, set()) - {c["agent"]}) if c["agent"] is not None else None
        reads.append({"call": c["id"], "classification": classification, "previously_available_to_agent": previous,
                      "delivery_verified": e["delivered"],
                      "source_changed": changed, "observed_in_other_agent": across,
                      "required_verification": True if required else None,
                      "independently_unnecessary": review.get("unnecessary"),
                      "relevance": review.get("relevance", "unknown")})
        last[key] = e
        if e["delivered"] and c["agent"] is not None:
            available.add(exact)
            other_agents.setdefault(cross_key, set()).add(c["agent"])
    calls = value["calls"]
    output_coverage = sum(c['output_bytes'] is not None for c in calls)
    duration_coverage = sum(c['duration_ms'] is not None for c in calls)
    return {"total_observed_calls": len(calls), "stream_complete": value["complete"],
            "tool_totals": {'successful':sum(c['success'] is True for c in calls),
                'failed':sum(c['success'] is False for c in calls), 'unknown_status':sum(c['success'] is None for c in calls),
                'potential_repeated_calls':sum(c['potential_repeated_calls'] for c in categories.values()),
                'output_bytes_observed_sum':sum(c['output_bytes'] or 0 for c in calls) if output_coverage else None,
                'output_bytes_complete_total':sum(c['output_bytes'] for c in calls) if calls and output_coverage == len(calls) and value['complete'] else None,
                'output_bytes_measured_calls':output_coverage,
                'duration_ms_observed_sum':sum(c['duration_ms'] or 0 for c in calls) if duration_coverage else None,
                'duration_ms_measured_calls':duration_coverage},
            "by_category": {k: dict(v) for k, v in categories.items()}, "context_counts": dict(counts),
            "context_observations": reads, "capability_lifecycle": lifecycle,
            "coverage": {"exact_file_observations": sum(c["evidence"] is not None and c["evidence"]["delivered"] for c in calls),
                         "candidate_file_observations": len(reads), "tool_calls": len(calls),
                         "unclassified_calls": sum(c["category"] == "other" for c in calls),
                         "file_range_coverage": "partial" if any(c["evidence"] and c["evidence"]["delivered"] for c in calls) else "unknown",
                         "purpose_and_relevance": "independent_review_only"},
            "observer_ns": value["observer_ns"],
            "limitations": ["Observed records are a lower bound, not every file read or evidence available in the model context.",
                "Same-agent earlier delivery does not prove evidence survived truncation; potential redundancy is not waste.",
                "Cross-worker duplication does not establish shared context or unnecessary independent review.",
                "Repeated checks remain investigation candidates; review hashes are attestations, not authentication.",
                "Durations are public-event receive spans; sums can overlap and are not task wall time."]}


class Observer:
    """Literal single-file readers only; byte-match observed output before crediting delivery."""
    def __init__(self, key, source="native_public_events", agent="root"):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ProfileError("Opaque identifiers require an explicit private study key")
        self.key, self.source = key, source
        self.agent = self.opaque(agent) if agent is not None else None
        self.pending, self.calls, self.elapsed = {}, [], 0
        self.completed = set()

    def opaque(self, value):
        return hmac.new(self.key, value.encode(), hashlib.sha256).hexdigest()

    def read(self, text, folder):
        if folder is None:
            return None  # An old export cannot reconstruct source bytes at the time of access.
        from benchmark_runner import literal_command, trusted_executable
        tokens = literal_command(text)
        if not tokens:
            return None
        exe, args = trusted_executable(tokens[0]), tokens[1:]
        selector = ("file",)
        if exe == "cat" and len(args) == 1 and not args[0].startswith("-"):
            name = args[0]
        elif exe == "sed" and len(args) == 3 and args[0] == "-n" and re.fullmatch(r"[1-9][0-9]*(,[1-9][0-9]*)?p", args[1]):
            parts = args[1][:-1].split(",");start, end = int(parts[0]), int(parts[-1])
            if not 1 <= start <= end <= 100000:
                return None
            selector, name = ("lines", start, end), args[2]
        elif exe in {"head", "tail"} and len(args) == 3 and args[0] == "-n" and re.fullmatch(r"[1-9][0-9]{0,4}", args[1]):
            selector, name = (exe, int(args[1])), args[2]
        else:
            return None
        root = Path(folder).absolute();path = Path(name)
        path = path if path.is_absolute() else root / path
        if ".." in path.parts or path.is_symlink() or root not in path.parents:
            return None
        try:
            relative = path.relative_to(root).as_posix()
            # Anchor every component to directory descriptors: model-authored link swaps must not escape.
            with ExitStack() as stack:
                directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                stack.callback(os.close, directory)
                parts = Path(relative).parts
                for part in parts[:-1]:
                    directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    stack.callback(os.close, directory)
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
                stack.callback(os.close, fd)
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2_000_000:
                    return None
                chunks = bytearray()
                while len(chunks) <= 2_000_000:
                    chunk = os.read(fd, min(65536, 2_000_001-len(chunks)))
                    if not chunk: break
                    chunks.extend(chunk)
                if len(chunks) > 2_000_000: return None
                data = bytes(chunks)
            pieces = data.split(b'\n')
            lines = [line+b'\n' for line in pieces[:-1]] + ([pieces[-1]] if pieces[-1] else [])
            selected = data if selector[0] == "file" else b"".join(lines[selector[1]-1:selector[2]]) if selector[0] == "lines" else b"".join(lines[:selector[1]] if selector[0] == "head" else lines[-selector[1]:])
            if exe == "sed" and selected and not selected.endswith(b"\n"):
                return None  # Platform-dependent unterminated-line rendering stays unknown.
            if data and not selected:
                return None  # An out-of-range empty result supplies no source evidence.
            if lines:
                if selector[0] == 'file': selector = ('lines', 1, len(lines))
                elif selector[0] == 'lines': selector = ('lines', selector[1], min(selector[2], len(lines)))
                elif selector[0] == 'head': selector = ('lines', 1, min(selector[1], len(lines)))
                else: selector = ('lines', max(1,len(lines)-selector[1]+1), len(lines))
            else:
                selector = ('empty_file',)
            return {"source": self.opaque(relative), "selector": self.opaque(repr(selector)),
                    "revision": hashed(data), "content": hashed(selected), "bytes": len(selected),
                    "tokens": None, "delivered": False, "truncated": None}
        except OSError:
            return None

    def __call__(self, event, folder):
        started = time.perf_counter_ns()
        try:
            self.observe(event, folder)
        finally:
            self.elapsed += time.perf_counter_ns()-started

    def observe(self, event, folder):
        from benchmark_runner import literal_command, trusted_executable, command_observations
        identity = event.get("id")
        if not isinstance(identity, str) or not identity:
            raise ProfileError("Public tool event needs identifier")
        call_id = self.opaque(identity)
        if event["phase"] == "started":
            if len(self.pending)+len(self.calls) >= MAX_EVENTS:
                raise ProfileError("Too many public tool events")
            if call_id in self.pending or call_id in self.completed:
                raise ProfileError("Duplicate public tool start")
            self.pending[call_id] = (time.monotonic_ns(), self.read(event.get("command", ""), folder))
            return
        if event["phase"] != "completed" or call_id in self.completed:
            raise ProfileError("Duplicate or invalid public tool completion")
        if len(self.calls) >= MAX_EVENTS:
            raise ProfileError("Too many public tool events")
        prior = self.pending.pop(call_id, None)
        self.completed.add(call_id)
        text = event.get("command", "");tokens = literal_command(text)
        exe = trusted_executable(tokens[0]) if tokens else None
        category = "other"
        legacy, _, _ = command_observations(text, Path(folder) if folder is not None else Path('/'))
        if legacy in {"test", "build"}: category = "tests_builds"
        elif exe in {"rg", "find", "ls"}: category = "search_discovery"
        elif exe in {"cat", "head", "tail", "sed"}: category = "file_inspection"
        elif event.get("type") == "file_change": category = "source_modification"
        elif event.get("type") == "web_search": category = "search_discovery"
        success = event.get("success")
        evidence = self.read(text, folder)
        if evidence is not None:
            stable = prior is not None and prior[1] is not None and prior[1]["revision"] == evidence["revision"]
            evidence["delivered"] = success is True and stable and event.get('truncated') is not True and event.get("result") == evidence["content"]
            evidence["truncated"] = False if evidence["delivered"] else event.get("truncated")
            if not evidence["delivered"]:
                evidence["bytes"] = None
        caps = []
        if evidence and evidence["delivered"] and tokens and Path(tokens[-1]).name == "SKILL.md":
            category = "skill_instructions"
            caps.append({"id": evidence["source"], "stage": "instructions_read"})
        if event.get("type") == "mcp_tool_call" and isinstance(event.get("capability"), str):
            caps.append({"id": self.opaque(event["capability"]), "stage": "invoked"})
        self.calls.append({"id": call_id, "agent": self.agent, "category": category,
            "operation": self.opaque(repr(tokens)) if tokens else None, "success": success,
            "output_bytes": event.get("output_bytes"), "duration_ms": (time.monotonic_ns()-prior[0])//1000000 if prior else None,
            "result": event.get("result"), "evidence": evidence, "capabilities": caps})

    def export(self, complete=False):
        # Preserve starts without completions as unknown, never as successful reads.
        calls = copy.deepcopy(self.calls)
        for identity in self.pending:
            calls.append({"id": identity, "agent": self.agent, "category": "other", "operation": None,
                          "success": None, "output_bytes": None, "duration_ms": None, "result": None,
                          "evidence": None, "capabilities": []})
        return validate({"schema": 5, "source": self.source, "complete": bool(complete and not self.pending),
                         "calls": calls, "observer_ns": self.elapsed})
