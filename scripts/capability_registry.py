#!/usr/bin/env python3
"""Explicit, local-only capability metadata index. Never starts or invokes a tool.

Catalog entries are untrusted discovery hints. They are NOT execution instructions
and do not grant access to skills, MCP providers, files, or other systems.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

SCHEMA = 1
PERMISSIONS = {"unknown", "granted", "denied"}
SKILL_LIMIT = 131072
CATALOG_LIMIT = 1048576
MAX_SKILLS_PER_ROOT = 256
MAX_TOOLS = 500
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IDENTITY = re.compile(r"^[a-zA-Z0-9_.:/-]{1,128}$")
WORD = re.compile(r"[a-z0-9]+")
STOP = {"the", "and", "for", "with", "this", "that", "when", "using",
        "you", "your", "into", "from", "are", "all", "agent", "agents",
        "tool", "tools", "use", "code", "task", "tasks"}
FOCUSED_STOP = {"help", "please", "fix", "improve", "implement", "relevant",
                "capability", "capabilities", "work", "need", "needed"}

class RegistryError(ValueError):
    pass

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read_regular(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RegistryError(f"Not a normal file: {path}")
    if path.stat().st_size > limit:
        raise RegistryError(f"Oversize file: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise RegistryError(f"Oversize file: {path}")
    return raw

def plain(value):
    if not isinstance(value, str):
        raise RegistryError("Expected text")
    if any((ord(c) < 32 and c not in "\r\n\t") or ord(c) == 127 for c in value):
        raise RegistryError("Control character in metadata")
    value = " ".join(value.split())
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise RegistryError("Control character in metadata")
    return value

def parse_skill(raw, folder):
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        raise RegistryError("Invalid UTF-8 skill")
    if not lines or lines[0].strip() != "---":
        raise RegistryError("Missing skill frontmatter")
    try:
        end = lines.index("---", 1, min(140, len(lines)))
    except ValueError:
        raise RegistryError("Unterminated skill frontmatter")
    data = {}
    i = 1
    while i < end:
        line = lines[i]
        if line and not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            value = value.strip()
            if key in ("name", "description"):
                if key in data:
                    raise RegistryError(f"Duplicate frontmatter field: {key}")
                if value in (">", "|", ">-", "|-"):
                    values = []
                    i += 1
                    while i < end and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                        values.append(lines[i].strip())
                        i += 1
                    data[key] = plain(" ".join(values))
                    continue
                if value.startswith('"') and value.endswith('"'):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        raise RegistryError("Malformed quoted metadata")
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1].replace("''", "'")
                data[key] = plain(value)
        i += 1
    name = data.get("name", "")
    description = data.get("description", "")
    if not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name) or name != folder:
        raise RegistryError("Skill name must match its lowercase kebab-case folder")
    if not description or len(description) > 1024:
        raise RegistryError("Skill description missing or too long")
    return name, description

def scan_skills(roots):
    entries = []
    for idx, rawroot in enumerate(roots):
        root = Path(rawroot).expanduser()
        if root.is_symlink() or not root.is_dir():
            raise RegistryError(f"Skill root must be a normal directory: {rawroot}")
        child_dirs = sorted(root.iterdir(), key=lambda x: x.name)
        if len(child_dirs) > MAX_SKILLS_PER_ROOT:
            raise RegistryError("Too many entries in skill root")
        candidates = [root] if (root / "SKILL.md").is_file() else child_dirs
        for directory in candidates:
            if directory.is_symlink() or not directory.is_dir():
                continue
            skill = directory / "SKILL.md"
            if skill.is_symlink() or not skill.is_file():
                continue
            raw = read_regular(skill, SKILL_LIMIT)
            try:
                name, description = parse_skill(raw, directory.name)
            except RegistryError:
                # An invalid skill is neither activated nor placed in the catalog.
                continue
            relative = skill.relative_to(root).as_posix()
            entries.append({"type": "skill", "name": name,
                            "description": description, "source": f"root:{idx}",
                            "relative_path": relative, "sha256": sha(raw),
                            "trust": "untrusted_metadata"})
    return entries

def scan_tools(path):
    if path is None:
        return [], None
    raw = read_regular(path, CATALOG_LIMIT)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise RegistryError("Invalid UTF-8 JSON tool metadata snapshot")
    if not isinstance(data, dict) or not isinstance(data.get("tools"), list):
        raise RegistryError("Tool snapshot requires tools array")
    if len(data["tools"]) > MAX_TOOLS:
        raise RegistryError("Too many tool entries")
    entries = []
    seen = set()
    identities = set()
    for item in data["tools"]:
        if not isinstance(item, dict):
            raise RegistryError("Tool metadata entries must be objects")
        provider, name = item.get("provider"), item.get("name")
        description = plain(item.get("description", ""))
        enabled = item.get("enabled", True)
        if not isinstance(provider, str) or not IDENTITY.fullmatch(provider):
            raise RegistryError("Invalid provider")
        if not isinstance(name, str) or not IDENTITY.fullmatch(name):
            raise RegistryError("Invalid tool name")
        if not description or len(description) > 1024 or type(enabled) is not bool:
            raise RegistryError("Invalid tool description/enabled status")
        ident = (provider, name)
        if ident in seen:
            raise RegistryError("Duplicate provider/tool pair")
        seen.add(ident)
        aliases = item.get("aliases", [])
        permission = item.get("permission", "unknown")
        revoked = item.get("revoked", False)
        if not isinstance(permission, str) or permission not in PERMISSIONS or type(revoked) is not bool:
            raise RegistryError("Invalid permission or revocation state")
        if not isinstance(aliases, list) or len(aliases) > 20 or any(
                not isinstance(alias, str) or not IDENTITY.fullmatch(alias) for alias in aliases):
            raise RegistryError("Invalid aliases")
        for alias in [name] + aliases:
            identity = (provider, alias)
            if identity in identities:
                raise RegistryError("Conflicting tool alias")
            identities.add(identity)
        if not enabled or revoked or permission == "denied":
            continue
        # Never copy schemas, credentials, arguments, endpoints or unknown keys.
        entry = {"type": "tool", "name": name, "provider": provider,
                 "description": description, "source": "provided-tool-snapshot",
                 "trust": "untrusted_metadata", "permission": permission,
                 "aliases": aliases}
        if "inputSchema" in item and not isinstance(item["inputSchema"], dict):
            raise RegistryError("Tool inputSchema must be an object")
        if "inputSchema" in item:
            serialized = json.dumps(item["inputSchema"], sort_keys=True,
                                    separators=(",", ":")).encode()
            entry["schema_sha256"] = sha(serialized)
        entries.append(entry)
    return entries, sha(raw)

def build(roots, tools_file=None, revision=None, environment=None):
    if not isinstance(roots, (list, tuple)) or len(roots) > 16:
        raise RegistryError("At most 16 explicitly selected skill roots")
    binding = {}
    for key, value in (("revision", revision), ("environment", environment)):
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 200:
                raise RegistryError("Binding labels must be short nonempty text")
            binding[key] = value
    skills = scan_skills(roots)
    unique = {}
    for item in skills:
        previous = unique.get(item["name"])
        if previous is not None:
            if previous["sha256"] != item["sha256"]:
                raise RegistryError("Conflicting skill identity: " + item["name"])
            previous.setdefault("source_aliases", []).append({
                "source": item["source"], "relative_path": item["relative_path"]})
        else:
            item["permission"] = "unknown"
            unique[item["name"]] = item
    skills = list(unique.values())
    tools, catalog_hash = scan_tools(tools_file)
    entries = skills + tools
    entries.sort(key=lambda x: (x["type"], x.get("provider", ""), x["name"], x["source"]))
    return {"schema": SCHEMA, "scope": "explicit-inputs-only",
            "roots_count": len(roots),
            "tool_snapshot_sha256": catalog_hash,
            "binding": binding,
            "capabilities": entries,
            "caution": "Untrusted hints only. Resolve live availability, policies and permission at the original host."}

def terms(value):
    return {x for x in WORD.findall(value.lower().replace("_", "-")) if x not in STOP}

def query(snapshot, phrase, limit=5, *, focused=False):
    if not isinstance(phrase, str) or not phrase.strip() or len(phrase) > 1000:
        raise RegistryError("Query requires short nonempty text")
    if type(limit) is not int or not 1 <= limit <= 25:
        raise RegistryError("Limit must be 1..25")
    if type(focused) is not bool:
        raise RegistryError("Focused matching must be boolean")
    validate_snapshot(snapshot)
    wanted = terms(phrase)
    if focused:
        wanted -= FOCUSED_STOP
    matched = []
    for item in snapshot["capabilities"]:
        if item.get("permission", "unknown") == "denied" or item.get("revoked", False):
            continue
        name_terms = terms(" ".join([item["name"]] + item.get("aliases", [])))
        desc_terms = terms(item["description"])
        identifiers = [item["name"], *item.get("aliases", [])]
        if item.get("provider"):
            identifiers += [item["provider"] + "/" + name for name in identifiers.copy()]
        exact = phrase.strip().casefold() in {name.casefold() for name in identifiers}
        # Broad prose needs two description terms; a name or explicit alias suffices.
        if focused and not (exact or wanted & name_terms or len(wanted & desc_terms) >= 2):
            continue
        score = 5 * len(wanted & name_terms) + len(wanted & desc_terms)
        if focused and exact:
            score += 10000
        if item["name"].lower() == phrase.lower().strip():
            score += 20
        if score:
            matched.append((score, item))
    if focused and any(score >= 10000 for score, _ in matched):
        matched = [(score, item) for score, item in matched if score >= 10000]
    matched.sort(key=lambda x: (-x[0], x[1]["type"], x[1]["name"], x[1].get("provider", "")))
    return [{"relevance_score": score, **item} for score, item in matched[:limit]]

def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or type(snapshot.get("schema")) is not int or snapshot["schema"] != SCHEMA:
        raise RegistryError("Unsupported registry snapshot")
    if set(snapshot) - {"schema", "scope", "roots_count", "tool_snapshot_sha256", "binding", "capabilities", "caution"}:
        raise RegistryError("Unknown snapshot fields")
    roots_count = snapshot.get("roots_count")
    if type(roots_count) is not int or not 0 <= roots_count <= 16:
        raise RegistryError("Invalid roots count")
    binding = snapshot.get("binding", {})
    if not isinstance(binding, dict) or set(binding) - {"revision", "environment"} or any(
            not isinstance(v, str) or not v.strip() or len(v) > 200 for v in binding.values()):
        raise RegistryError("Invalid source/environment binding")
    digest = snapshot.get("tool_snapshot_sha256")
    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
        raise RegistryError("Invalid tool digest")
    entries = snapshot.get("capabilities")
    if not isinstance(entries, list) or len(entries) > 10000:
        raise RegistryError("Malformed registry capabilities")
    seen = set()
    def source_path(source, relative):
        if not isinstance(source, str) or len(source) > 8 or not re.fullmatch(r"root:[0-9]+", source) or int(source[5:]) >= roots_count:
            raise RegistryError("Invalid root reference")
        if not isinstance(relative, str) or not relative or len(relative) > 2048 or relative.startswith("/") or "\\" in relative or ":" in relative or any(
                part in ("", ".", "..") for part in relative.split("/")) or not relative.endswith("SKILL.md"):
            raise RegistryError("Unsafe skill-relative path")
    for item in entries:
        if not isinstance(item, dict) or item.get("type") not in ("skill", "tool"):
            raise RegistryError("Malformed registry entry")
        common = {"type", "name", "description", "source", "trust", "permission"}
        extra = {"relative_path", "sha256", "source_aliases"} if item["type"] == "skill" else {"provider", "aliases", "schema_sha256", "revoked"}
        if set(item) - common - extra:
            raise RegistryError("Unexpected metadata field")
        for key in ("name", "description", "source", "trust"):
            if not isinstance(item.get(key), str) or not item[key] or plain(item[key]) != item[key]:
                raise RegistryError("Malformed registry field")
        permission = item.get("permission", "unknown")
        if not isinstance(permission, str) or permission not in PERMISSIONS or type(item.get("revoked", False)) is not bool:
            raise RegistryError("Invalid permission or revocation state")
        if item["trust"] != "untrusted_metadata" or len(item["description"]) > 1024:
            raise RegistryError("Invalid metadata trust or description")
        if item["type"] == "skill":
            if len(item["name"]) > 64 or not NAME.fullmatch(item["name"]):
                raise RegistryError("Invalid skill identity")
            source_path(item["source"], item.get("relative_path"))
            if not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
                raise RegistryError("Invalid skill digest")
            aliases = item.get("source_aliases", [])
            if not isinstance(aliases, list) or len(aliases) > 15:
                raise RegistryError("Invalid source aliases")
            for alias in aliases:
                if not isinstance(alias, dict) or set(alias) != {"source", "relative_path"}:
                    raise RegistryError("Invalid source alias")
                source_path(alias["source"], alias["relative_path"])
            identities = [("skill", item["name"])]
        else:
            if not IDENTITY.fullmatch(item["name"]) or not isinstance(item.get("provider"), str) or not IDENTITY.fullmatch(item["provider"]):
                raise RegistryError("Invalid tool identity")
            if item["source"] != "provided-tool-snapshot":
                raise RegistryError("Invalid tool source")
            aliases = item.get("aliases", [])
            if not isinstance(aliases, list) or len(aliases) > 20 or any(
                    not isinstance(alias, str) or not IDENTITY.fullmatch(alias) for alias in aliases):
                raise RegistryError("Invalid tool aliases")
            if "schema_sha256" in item and (not isinstance(item["schema_sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["schema_sha256"])):
                raise RegistryError("Invalid tool schema digest")
            identities = [("tool", item["provider"], alias) for alias in [item["name"]] + aliases]
        for identity in identities:
            if identity in seen:
                raise RegistryError("Duplicate or conflicting capability identity")
            seen.add(identity)


def verify_sources(snapshot, roots, tools_file=None, revision=None, environment=None):
    """Compare only explicitly selected inputs; no cached permission becomes a grant."""
    validate_snapshot(snapshot)
    current = build(roots, tools_file, revision, environment)
    # Schema-1 snapshots written before optional binding/permission fields remain usable.
    normalized = json.loads(json.dumps(snapshot))
    normalized.setdefault("binding", {})
    for item in normalized["capabilities"]:
        item.setdefault("permission", "unknown")
        if item["type"] == "tool":
            item.setdefault("aliases", [])
    return current == normalized

def load_snapshot(path):
    raw = read_regular(path, 4000000)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise RegistryError("Invalid registry JSON")
    validate_snapshot(data)
    return data

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("build", "verify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", action="append", default=[], help="Explicit skill directory (repeatable)")
        cmd.add_argument("--tools-file", help="Explicit nonsecret MCP/tool metadata JSON snapshot")
        cmd.add_argument("--source-revision", help="Explicit source revision label (not inferred)")
        cmd.add_argument("--environment", help="Explicit environment fingerprint/label (not inferred)")
        if name == "build":
            cmd.add_argument("--output", help="New snapshot path (never overwrites existing)")
        else:
            cmd.add_argument("--snapshot", required=True)
    cmd = sub.add_parser("query")
    cmd.add_argument("--snapshot", required=True)
    cmd.add_argument("--text", required=True)
    cmd.add_argument("--limit", type=int, default=5)
    cmd.add_argument("--focused", action="store_true", help="opt-in conservative prose matching and exact alias priority")
    args = parser.parse_args()
    try:
        if args.cmd == "build":
            result = build(args.root, args.tools_file, args.source_revision, args.environment)
            payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
            if args.output:
                output = Path(args.output).expanduser()
                if output.exists() or output.is_symlink():
                    raise RegistryError("Output exists; refusing overwrite")
                with output.open("x", encoding="utf-8") as f:
                    os.fchmod(f.fileno(), 0o600)
                    f.write(payload)
                print("Indexed metadata into " + str(output))
            else:
                print(payload, end="")
        elif args.cmd == "query":
            result = query(load_snapshot(args.snapshot), args.text, args.limit, focused=args.focused)
            print(json.dumps({"results": result, "freshness": "unverified", "authorized_to_execute": False}, indent=2))
        else:
            old = load_snapshot(args.snapshot)
            if not verify_sources(old, args.root, args.tools_file, args.source_revision, args.environment):
                print("STALE: sources or capability metadata have changed", file=sys.stderr)
                return 1
            print("FRESH: snapshot matches explicitly supplied sources")
        return 0
    except (RegistryError, OSError, UnicodeError) as error:
        print(f"TuckBit registry error: {error}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
