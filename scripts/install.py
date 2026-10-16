#!/usr/bin/env python3
"""TuckBit portable skill installer: explicit, reversible, and local-only.

No network, global side effects without an explicit --scope global, hooks, MCP calls,
or model requests. A dedicated state record tracks managed copies and backups.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
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


class InstallError(ValueError):
    pass


def _secure_path(root, relative):
    """Reject installed target directories containing symlinks, including ancestors."""
    root = Path(root).expanduser().resolve()
    target = root / relative
    if not target.is_relative_to(root):
        raise InstallError("Installation target escapes selected root")
    current = target
    while current != root:
        if current.is_symlink():
            raise InstallError(f"Refusing symlink target/ancestor: {current}")
        current = current.parent
    return target


def _state_path(root):
    return _secure_path(root, STATE_REL)


def _load_state(root):
    path = _state_path(root)
    if not path.exists():
        return {"schema": 1, "entries": {}}
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InstallError(f"Cannot read installer state: {e}") from e
    if result.get("schema") != 1 or not isinstance(result.get("entries"), dict):
        raise InstallError("Invalid installer state format")
    return result


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


def digest(directory):
    """Hash managed regular files and their paths, rejecting unexpected symlinks."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise InstallError(f"Not a normal skill folder: {directory}")
    h = hashlib.sha256()
    for file in sorted(directory.rglob("*")):
        if file.is_symlink():
            raise InstallError(f"Symlink found inside skill: {file}")
        if not file.is_file():
            continue
        rel = file.relative_to(directory).as_posix()
        h.update(rel.encode("utf-8") + b"\0")
        h.update(file.read_bytes())
        h.update(b"\0")
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


def install(root, scope, client, replace=False, dry_run=False):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise InstallError(f"Root directory does not exist: {root}")
    if not SOURCE.is_dir():
        raise InstallError("TuckBit source skill is missing")
    target = _where(root, scope, client)
    state = _load_state(root)
    entry = state["entries"].get(client)
    existing = target.exists()
    new_hash = digest(SOURCE)
    if entry:
        if Path(entry.get("target", "")) != target:
            raise InstallError("Recorded destination does not match selected target")
        if not existing or digest(target) != entry.get("sha256"):
            raise InstallError("Managed skill was modified: inspect manually; refusing update")
        if new_hash == entry["sha256"]:
            return f"{client}: already installed (unchanged)"
        raise InstallError(f"{client}: installed version differs; uninstall first, then install the new version")
    elif existing and not target.is_dir():
        raise InstallError(f"{client}: destination is not a directory; refusing replacement")
    elif existing and not replace:
        raise InstallError(f"{client}: destination already exists; use --replace to back it up first")
    if dry_run:
        return f"{client}: would install to {target}" + (" (backup existing)" if existing else "")
    temp = None
    previous_backup = None
    old_entry = entry
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=".tuck-bit-stage-", dir=target.parent))
        shutil.copytree(SOURCE, temp / "skill")
        digest(temp / "skill")
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


def uninstall(root, scope, client, dry_run=False):
    root = Path(root).expanduser().resolve()
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
    backup = _secure_path(root, Path(backup_rel)) if backup_rel else None
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
    _clean_parent(target.parent, root)
    return f"{client}: uninstalled" + (" and restored original" if backup else "")


def status(root, scope, client):
    root = Path(root).expanduser().resolve()
    state = _load_state(root)
    entry = state["entries"].get(client)
    target = _where(root, scope, client)
    if not entry:
        return f"{client}: not managed ({'occupied' if target.exists() else 'empty'})"
    if Path(entry.get("target", "")) != target:
        return f"{client}: record mismatch"
    try:
        same = target.is_dir() and digest(target) == entry["sha256"]
    except InstallError:
        same = False
    return f"{client}: {'installed, intact' if same else 'MODIFIED'}"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("install", "uninstall", "status"))
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
    try:
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
                        raise InstallError(f"{c}: uninstall old version before updating")
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
