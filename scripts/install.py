#!/usr/bin/env python3
"""TuckBit portable skill installer: explicit, reversible, and local-only.

No network, global side effects without an explicit --scope global, hooks, MCP calls,
or model requests. A dedicated state record tracks managed copies and backups.
"""
import argparse
from functools import wraps
from inspect import signature
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import uuid

SOURCE = Path(__file__).resolve().parents[1] / "skills" / "tuck-bit"
PROJECT = {
    "claude": ".claude/skills/tuck-bit",
    "codex": ".agents/skills/tuck-bit",
    "gemini": ".gemini/skills/tuck-bit",
    "cursor": ".cursor/skills/tuck-bit",
    "opencode": ".opencode/skills/tuck-bit",
    "copilot": ".github/skills/tuck-bit",
}
GLOBAL = {
    "claude": ".claude/skills/tuck-bit",
    "codex": ".agents/skills/tuck-bit",
    "gemini": ".gemini/skills/tuck-bit",
    "cursor": ".cursor/skills/tuck-bit",
    "opencode": ".config/opencode/skills/tuck-bit",
    "copilot": ".copilot/skills/tuck-bit",
}
STATE_REL = Path(".tuck-bit/installations.json")
CLIENTS = tuple(PROJECT)
HASH_FORMAT = "sha256-length-framed-v1"
MAX_STATE_BYTES = 2097152


class InstallError(ValueError):
    pass


def _root(root):
    root = Path(os.path.abspath(Path(root).expanduser()))
    for path in (root, *root.parents):
        # macOS exposes these system-owned canonical aliases by default.
        if path.is_symlink() and not (sys.platform == "darwin" and str(path) in ("/tmp", "/var")):
            raise InstallError(f"Refusing symlink root/ancestor: {path}")
    root = root.resolve()
    if not root.is_dir():
        raise InstallError(f"Root directory does not exist: {root}")
    return root


def _secure_path(root, relative):
    root = _root(root)
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise InstallError("Installation path must stay within selected root")
    target = root / relative
    current = target
    while current != root:
        if current.is_symlink():
            raise InstallError(f"Refusing symlink target/ancestor: {current}")
        current = current.parent
    return target


def _state_path(root):
    return _secure_path(root, STATE_REL)


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _backup(root, client, relative):
    if not isinstance(relative, str) or not re.fullmatch(r"\.tuck-bit/backups/" + client + r"-[0-9a-f]{32}", relative):
        raise InstallError("Invalid installer backup path")
    return _secure_path(root, relative)


def _load_state(root):
    root = _root(root)
    path = _state_path(root)
    if not path.exists():
        return {"schema": 2, "hash_format": HASH_FORMAT, "entries": {}}
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise InstallError("Installer state must be an ordinary file")
            content = stream.read(MAX_STATE_BYTES + 1)
        if len(content) > MAX_STATE_BYTES:
            raise InstallError("Installer state exceeds size limit")
        result = json.loads(content.decode("utf-8"))
    except (OSError, ValueError) as e:
        raise InstallError(f"Cannot read installer state: {e}") from e
    if not isinstance(result, dict) or type(result.get("schema")) is not int or result["schema"] not in (1, 2) or not isinstance(result.get("entries"), dict):
        raise InstallError("Invalid installer state format")
    legacy = result["schema"] == 1
    if not legacy and result.get("hash_format") != HASH_FORMAT:
        raise InstallError("Unknown installer integrity format")
    for client, entry in result["entries"].items():
        if client not in CLIENTS or not isinstance(entry, dict):
            raise InstallError("Invalid installer client record")
        allowed_targets = {str(_secure_path(root, PROJECT[client])), str(_secure_path(root, GLOBAL[client]))}
        if not isinstance(entry.get("target"), str) or entry["target"] not in allowed_targets or not _hash(entry.get("sha256")):
            raise InstallError("Invalid installer target or integrity record")
        if not isinstance(entry.get("version", "legacy-unknown"), str):
            raise InstallError("Invalid installer version")
        entry.setdefault("version", "legacy-unknown")
        if legacy:
            target = Path(entry["target"])
            if digest(target, legacy=True) != entry["sha256"]:
                raise InstallError("Legacy managed skill was modified; refusing migration")
            entry["sha256"] = digest(target)
        backup_rel = entry.get("backup")
        if backup_rel is not None:
            backup = _backup(root, client, backup_rel)
            if legacy:
                if "backup_sha256" in entry and digest(backup, legacy=True) != entry["backup_sha256"]:
                    raise InstallError("Legacy backup was modified; refusing migration")
                entry["backup_sha256"] = digest(backup)
            if not _hash(entry.get("backup_sha256")):
                raise InstallError("Invalid backup integrity record")
        elif entry.get("backup_sha256") is not None:
            raise InstallError("Backup integrity record without backup")
        history = entry.setdefault("history", [])
        if not isinstance(history, list):
            raise InstallError("Invalid installer history")
        paths = {backup_rel} if backup_rel else set()
        for previous in history:
            if not isinstance(previous, dict) or not _hash(previous.get("sha256")) or not isinstance(previous.get("version"), str):
                raise InstallError("Invalid installer rollback record")
            _backup(root, client, previous.get("path"))
            if previous["path"] in paths:
                raise InstallError("Duplicate installer backup path")
            paths.add(previous["path"])
            if legacy:
                prior = _backup(root, client, previous["path"])
                if digest(prior, legacy=True) != previous["sha256"]:
                    raise InstallError("Legacy managed backup was modified; refusing migration")
                previous["sha256"] = digest(prior)
    result["schema"] = 2
    result["hash_format"] = HASH_FORMAT
    return result


def _verify_backups(root, client, entry):
    records = list(entry["history"])
    if entry.get("backup"):
        records.append({"path": entry["backup"], "sha256": entry["backup_sha256"]})
    for record in records:
        if digest(_backup(root, client, record["path"])) != record["sha256"]:
            raise InstallError(f"{client}: backup was modified; refusing operation")


def _version():
    match = re.search(r'^  version: "([^"\n]+)"$', (SOURCE / "SKILL.md").read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise InstallError("Source skill is missing its metadata version")
    return match[1]


def _save_state(root, state):
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".state-", suffix=".tmp",
                                     delete=False, encoding="utf-8") as f:
        name = Path(f.name)
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    try:
        os.replace(name, path)
    finally:
        name.unlink(missing_ok=True)


def digest(directory, legacy=False):
    """Hash managed regular files and their paths, rejecting unexpected symlinks."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise InstallError(f"Not a normal skill folder: {directory}")
    h = hashlib.sha256()
    for file in sorted(directory.rglob("*")):
        if file.is_symlink():
            raise InstallError(f"Symlink found inside skill: {file}")
        if file.is_dir():
            continue
        if not file.is_file():
            raise InstallError(f"Unexpected special file inside skill: {file}")
        rel = file.relative_to(directory).as_posix()
        encoded, content = rel.encode("utf-8"), file.read_bytes()
        if legacy:
            h.update(encoded + b"\0" + content + b"\0")
        else:
            h.update(len(encoded).to_bytes(8, "big") + encoded)
            h.update(len(content).to_bytes(8, "big") + content)
    return h.hexdigest()


def _where(root, scope, client):
    mapping = GLOBAL if scope == "global" else PROJECT
    if client not in mapping:
        raise InstallError(f"Unsupported agent client: {client}")
    return _secure_path(root, Path(mapping[client]))


def _clean_parent(path, root):
    """Remove our empty install parent directories only, not the root or other user dirs."""
    while path != root and path.is_relative_to(root):
        try:
            path.rmdir()
        except OSError:
            break
        path = path.parent


def _exclusive(operation):
    parameters = signature(operation)
    @wraps(operation)
    def run(root, *args, **kwargs):
        if parameters.bind(root, *args, **kwargs).arguments.get("dry_run", False):
            return operation(root, *args, **kwargs)
        root = _root(root)
        lock = _secure_path(root, ".tuck-bit/install.lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock.mkdir()
        except FileExistsError as exc:
            raise InstallError("Installer is busy or a prior run was interrupted; inspect .tuck-bit/install.lock") from exc
        try:
            return operation(root, *args, **kwargs)
        finally:
            lock.rmdir()
    return run


@_exclusive
def install(root, scope, client, replace=False, dry_run=False):
    root = _root(root)
    if not SOURCE.is_dir():
        raise InstallError("TuckBit source skill is missing")
    target = _where(root, scope, client)
    state = _load_state(root)
    entry = state["entries"].get(client)
    existing = target.exists()
    new_hash = digest(SOURCE)
    version = _version()
    if entry:
        if Path(entry.get("target", "")) != target:
            raise InstallError("Recorded destination does not match selected target")
        if not existing or digest(target) != entry.get("sha256"):
            raise InstallError("Managed skill was modified: inspect manually; refusing update")
        _verify_backups(root, client, entry)
        if new_hash == entry["sha256"]:
            return f"{client}: already installed (unchanged)"
        raise InstallError(f"{client}: installed version differs; use the explicit update action")
    elif existing and not target.is_dir():
        raise InstallError(f"{client}: destination is not a directory; refusing replacement")
    elif existing and not replace:
        raise InstallError(f"{client}: destination already exists; use --replace to back it up first")
    if existing:
        digest(target)
    if dry_run:
        return f"{client}: would install to {target}" + (" (backup existing)" if existing else "")
    temp = None
    previous_backup = None
    old_entry = entry
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=".tuck-bit-stage-", dir=target.parent))
        shutil.copytree(SOURCE, temp / "skill")
        if digest(temp / "skill") != new_hash:
            raise InstallError("Staged source integrity mismatch")
        if existing:
            backup_root = _secure_path(root, Path(".tuck-bit/backups"))
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = _secure_path(root, Path(".tuck-bit/backups") / (client + "-" + uuid.uuid4().hex))
            target.rename(backup)
            previous_backup = str(backup.relative_to(root))
        (temp / "skill").rename(target)
        state["entries"][client] = {
            "target": str(target),
            "sha256": new_hash,
            "backup": previous_backup,
            "backup_sha256": digest(root / previous_backup) if previous_backup else None,
            "version": version,
            "history": [],
        }
        _save_state(root, state)
        return f"{client}: installed to {target}" + (" (prior installation backed up)" if previous_backup else "")
    except Exception:
        if temp and (temp / "skill").is_dir():
            shutil.rmtree(temp / "skill")
        # On failure after new copy, do not leave a false successful installation.
        if not old_entry and previous_backup:
            if target.exists():
                shutil.rmtree(target)
            (root / previous_backup).rename(target)
        elif target.exists() and not existing:
            shutil.rmtree(target)
        raise
    finally:
        if temp and temp.exists():
            shutil.rmtree(temp)


@_exclusive
def uninstall(root, scope, client, dry_run=False):
    root = _root(root)
    state = _load_state(root)
    entry = state["entries"].get(client)
    if not entry:
        return f"{client}: not installed by TuckBit"
    target = _where(root, scope, client)
    if Path(entry.get("target", "")) != target:
        raise InstallError(f"{client}: recorded target mismatch; refusing uninstall")
    if not target.is_dir() or digest(target) != entry["sha256"]:
        raise InstallError(f"{client}: installed files changed; refusing removal")
    backup_rel = entry.get("backup")
    _verify_backups(root, client, entry)
    backup = _backup(root, client, backup_rel) if backup_rel else None
    if backup and not backup.is_dir():
        raise InstallError(f"{client}: prior backup missing; refusing removal")
    if dry_run:
        return f"{client}: would remove managed installation" + (" and restore backup" if backup else "")
    # Rename the managed copy away first. If state persistence fails, recover
    # the previous managed copy and leave the install record unchanged.
    quarantine = target.parent / (".tuck-bit-undo-" + uuid.uuid4().hex)
    target.rename(quarantine)
    original_restored = False
    try:
        if backup:
            backup.rename(target)
            original_restored = True
        del state["entries"][client]
        _save_state(root, state)
    except Exception:
        state["entries"][client] = entry
        if original_restored and backup:
            target.rename(backup)
        if quarantine.exists():
            quarantine.rename(target)
        raise
    shutil.rmtree(quarantine)
    for previous in entry["history"]:
        shutil.rmtree(_backup(root, client, previous["path"]))
    _clean_parent(target.parent, root)
    return f"{client}: uninstalled" + (" and restored original" if backup else "")


@_exclusive
def update(root, scope, client, dry_run=False, rollback=False):
    root = _root(root)
    state = _load_state(root)
    entry = state["entries"].get(client)
    target = _where(root, scope, client)
    if not entry or entry["target"] != str(target):
        raise InstallError(f"{client}: no managed installation at selected target")
    if digest(target) != entry["sha256"]:
        raise InstallError(f"{client}: managed skill was modified; refusing update")
    _verify_backups(root, client, entry)
    if rollback:
        if not entry["history"]:
            raise InstallError(f"{client}: no previous managed version")
        previous = entry["history"][-1]
        source = _backup(root, client, previous["path"])
        new_hash, version = previous["sha256"], previous["version"]
    else:
        source = SOURCE
        new_hash, version = digest(source), _version()
        if new_hash == entry["sha256"]:
            return f"{client}: already installed (unchanged)"
    action = "roll back" if rollback else "update"
    if dry_run:
        return f"{client}: would {action} {entry['version']} to {version} ({new_hash})"
    backup_root = _secure_path(root, ".tuck-bit/backups")
    backup_root.mkdir(parents=True, exist_ok=True)
    saved = _backup(root, client, ".tuck-bit/backups/" + client + "-" + uuid.uuid4().hex)
    stage = Path(tempfile.mkdtemp(prefix=".tuck-bit-stage-", dir=target.parent))
    moved = False
    try:
        shutil.copytree(source, stage / "skill")
        if digest(stage / "skill") != new_hash:
            raise InstallError("Staged source integrity mismatch")
        target.rename(saved)
        moved = True
        (stage / "skill").rename(target)
        updated = dict(entry, sha256=new_hash, version=version, history=list(entry["history"]))
        if rollback:
            updated["history"].pop()
        else:
            updated["history"].append({"path": str(saved.relative_to(root)), "sha256": entry["sha256"], "version": entry["version"]})
        state["entries"][client] = updated
        _save_state(root, state)
    except Exception:
        if moved:
            if target.exists():
                shutil.rmtree(target)
            saved.rename(target)
        raise
    finally:
        shutil.rmtree(stage)
    if rollback:
        shutil.rmtree(saved)
        shutil.rmtree(source)
    return f"{client}: {'rolled back' if rollback else 'updated'} to {version} ({new_hash})"


def status(root, scope, client):
    root = _root(root)
    state = _load_state(root)
    entry = state["entries"].get(client)
    target = _where(root, scope, client)
    if not entry:
        return f"{client}: not managed ({'occupied' if target.exists() else 'empty'})"
    if Path(entry.get("target", "")) != target:
        return f"{client}: record mismatch"
    try:
        _verify_backups(root, client, entry)
        same = target.is_dir() and digest(target) == entry["sha256"]
    except InstallError:
        same = False
    return f"{client}: {'installed, intact' if same else 'MODIFIED'}"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("install", "update", "rollback", "uninstall", "status"))
    p.add_argument("--scope", choices=("project", "global"), default="project")
    p.add_argument("--project", default=".", help="Root for project-scoped installs")
    p.add_argument("--home", default=None, help="Explicit home root (for testing, global scope only)")
    p.add_argument("--client", choices=CLIENTS + ("all",), default="all")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--replace", action="store_true", help="Back up an existing skill before first install")
    args = p.parse_args()
    if args.replace and args.action != "install":
        p.error("--replace is only valid for install")
    root = Path(args.home).expanduser() if args.scope == "global" and args.home else (
        Path.home() if args.scope == "global" else Path(args.project).expanduser()
    )
    selected = CLIENTS if args.client == "all" else (args.client,)
    if args.action in ("update", "rollback") and args.client == "all":
        p.error("Select one --client for an explicit update or rollback")
    try:
        root = _root(root)
        if args.action in ("update", "rollback"):
            print(update(root, args.scope, args.client, dry_run=args.dry_run, rollback=args.action == "rollback"))
            return 0
        # Preflight each client before any multi-client change.
        if args.action == "install":
            state = _load_state(root)
            source_hash = digest(SOURCE)
            for c in selected:
                target = _where(root, args.scope, c)
                if target.exists() and not target.is_dir():
                    raise InstallError(f"{c}: destination is not a directory")
                if c in state["entries"]:
                    entry = state["entries"][c]
                    if entry.get("target") != str(target) or not target.is_dir() or digest(target) != entry["sha256"]:
                        raise InstallError(f"{c}: managed installation was altered")
                    if entry["sha256"] != source_hash:
                        raise InstallError(f"{c}: use explicit update for installed version")
                elif target.exists() and not args.replace:
                    raise InstallError(f"{c}: destination already exists; use --replace")
        completed=[]
        try:
            for client in selected:
                func = {"install": install, "uninstall": uninstall, "status": status}[args.action]
                options = {"dry_run": args.dry_run} if args.action == "uninstall" else (
                    {"dry_run": args.dry_run, "replace": args.replace} if args.action == "install" else {}
                )
                result=func(root, args.scope, client, **options)
                print(result)
                if args.action == "install" and not args.dry_run and result.startswith(client+": installed"):
                    completed.append(client)
        except Exception:
            # Best effort rollback of changes made in this batch; pre-existing managed
            # installs cannot be updated in-place, so these are all new records.
            for done in reversed(completed):
                try:
                    uninstall(root,args.scope,done)
                except Exception as rollback_error:
                    print(f"WARNING: rollback for {done} failed: {rollback_error}",file=sys.stderr)
            raise
        return 0
    except (InstallError, OSError, ValueError) as exc:
        print(f"TuckBit installer error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
