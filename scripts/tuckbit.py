#!/usr/bin/env python3
"""TuckBit Phase 1: read-only module configuration and distribution diagnostics."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "skills" / "tuck-bit" / "assets" / "modules.json"
VALID_PROFILES = ("economy", "balanced", "critical")

def read_json(path):
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return obj

def defaults():
    obj = read_json(CATALOG)
    mods = obj.get("modules", {})
    if not isinstance(mods, dict) or not all(isinstance(v, bool) for v in mods.values()):
        raise ValueError("Invalid default module catalog")
    return {"profile": obj.get("profile", "balanced"), "modules": mods.copy()}

def overlay(base, src, label):
    allowed = set(base["modules"])
    unknown = set(src) - {"profile", "modules"}
    if unknown:
        raise ValueError(f"Unsupported fields in {label}: {sorted(unknown)}")
    if "profile" in src:
        if src["profile"] not in VALID_PROFILES:
            raise ValueError(f"Invalid profile in {label}")
        base["profile"] = src["profile"]
    if "modules" in src:
        mods = src["modules"]
        if not isinstance(mods, dict) or any(k not in allowed or not isinstance(v, bool) for k,v in mods.items()):
            raise ValueError(f"Invalid modules in {label}")
        base["modules"].update(mods)
    return base

def resolve(project, global_config=None, session_profile=None, enable=(), disable=()):
    result = defaults()
    global_file = Path(global_config) if global_config else Path.home()/".tuck-bit"/"config.json"
    project_file = Path(project).expanduser().resolve()/".tuck-bit"/"config.json"
    for path in (global_file, project_file):
        if path.is_file():
            overlay(result, read_json(path), str(path))
    if session_profile:
        overlay(result, {"profile": session_profile}, "session")
    if set(enable) & set(disable):
        raise ValueError("Cannot enable and disable the same module")
    overlay(result, {"modules": {k: True for k in enable} | {k: False for k in disable}}, "session")
    return result

def doctor(root=ROOT):
    problems=[]
    skill = root/"skills"/"tuck-bit"/"SKILL.md"
    refs = root/"skills"/"tuck-bit"/"references"
    plugin = root/".claude-plugin"/"plugin.json"
    for path in (skill, plugin, root/"README.md"):
        if not path.is_file():
            problems.append(f"Missing: {path.relative_to(root)}")
    if skill.is_file() and not skill.read_text(encoding="utf-8").startswith("---\nname: tuck-bit\n"):
        problems.append("Invalid or missing skill frontmatter/name")
    if plugin.is_file():
        try:
            manifest=read_json(plugin)
            if manifest.get("name")!="tuck-bit": problems.append("Incorrect Claude plugin name")
        except ValueError as exc: problems.append(str(exc))
    for key in defaults()["modules"]:
        if not (refs/f"{key}.md").is_file():
            problems.append(f"Missing playbook: {key}")
    return problems

def main():
    p=argparse.ArgumentParser(description="TuckBit Phase 1 local inspector (never invokes an AI agent).")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor",help="check installed source layout; read-only")
    c=sub.add_parser("config",help="print resolved module policy; read-only")
    c.add_argument("--project",default=".")
    c.add_argument("--global-config",default=None)
    c.add_argument("--profile",choices=VALID_PROFILES)
    c.add_argument("--enable",action="append",default=[],metavar="MODULE")
    c.add_argument("--disable",action="append",default=[],metavar="MODULE")
    args=p.parse_args()
    if args.command=="doctor":
        problems=doctor()
        print("TuckBit doctor: "+("PASS" if not problems else "FAIL"))
        for item in problems: print(" - "+item)
        return 0 if not problems else 1
    try:
        print(json.dumps(resolve(args.project,args.global_config,args.profile,args.enable,args.disable),indent=2))
        return 0
    except ValueError as exc:
        print(f"TuckBit configuration error: {exc}",file=os.sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
