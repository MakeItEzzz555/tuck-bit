#!/usr/bin/env python3
"""TuckBit Phase 1: read-only module configuration and distribution diagnostics."""
import argparse
import json
import os
from pathlib import Path
import re

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

def defaults(catalog=None):
    obj = read_json(CATALOG if catalog is None else catalog)
    mods = obj.get("modules", {})
    if (obj.get("profile", "balanced") not in VALID_PROFILES or not isinstance(mods, dict)
            or not mods or any(not re.fullmatch(r"[a-z][a-z0-9_]*", k)
                              or not isinstance(v, bool) for k, v in mods.items())):
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

def resolve(project, global_config=None, session_profile=None, enable=(), disable=(), project_only=False):
    result = defaults()
    project_file = Path(project).expanduser().resolve()/".tuck-bit"/"config.json"
    if project_only and global_config is not None:
        raise ValueError("Cannot combine project-only policy with a global config")
    paths = [project_file]
    if not project_only:
        paths.insert(0, Path(global_config) if global_config else Path.home()/".tuck-bit"/"config.json")
    for path in paths:
        if path.is_file():
            overlay(result, read_json(path), str(path))
    if session_profile:
        overlay(result, {"profile": session_profile}, "session")
    if set(enable) & set(disable):
        raise ValueError("Cannot enable and disable the same module")
    overlay(result, {"modules": {k: True for k in enable} | {k: False for k in disable}}, "session")
    return result

def doctor_status(root=ROOT):
    """Inspect only the selected source or skill directory; never activate a host."""
    root = Path(root)
    skill_only = (root/"SKILL.md").is_file()
    skill_root = root if skill_only else root/"skills"/"tuck-bit"
    skill = skill_root/"SKILL.md"
    refs = skill_root/"references"
    catalog = skill_root/"assets"/"modules.json"
    plugin = root/".claude-plugin"/"plugin.json"
    issues=[]
    def issue(code, message, hint):
        issues.append({"code": code, "message": message, "hint": hint})
    paths = (skill,) if skill_only else (skill, plugin, root/"README.md")
    for path in paths:
        if not path.is_file():
            issue("missing_source_file", f"Missing: {path.relative_to(root)}",
                  "Select a complete source checkout or an installed tuck-bit skill directory with --root.")
    if skill.is_file():
        try:
            if not skill.read_text(encoding="utf-8").startswith("---\nname: tuck-bit\n"):
                issue("invalid_skill", "Invalid or missing skill frontmatter/name", "Restore the canonical skill file.")
        except (OSError, UnicodeError):
            issue("unreadable_skill", "Cannot read skill instructions", "Check local file access and UTF-8 encoding.")
    if not skill_only and plugin.is_file():
        try:
            manifest=read_json(plugin)
            if manifest.get("name")!="tuck-bit":
                issue("invalid_plugin", "Incorrect Claude plugin name", "Restore the canonical plugin manifest.")
        except (ValueError, UnicodeError):
            issue("invalid_plugin", "Cannot read Claude plugin manifest", "Restore valid UTF-8 JSON plugin metadata.")
    try:
        modules = defaults(catalog)["modules"]
    except (ValueError, UnicodeError):
        code = "invalid_catalog" if catalog.is_file() else "missing_catalog"
        issue(code, "Cannot read a valid module catalog", "Restore assets/modules.json from the same canonical distribution.")
        modules = {}
    for key in modules:
        if not (refs/f"{key}.md").is_file():
            issue("missing_playbook", f"Missing playbook: {key}", "Restore the matching references directory.")
    return {"schema": 1, "status": "fail" if issues else "pass",
            "layout": "skill-only" if skill_only else "source", "issues": issues,
            "scope": "local packaging; host availability and activation are unverified",
            "runtime": "Optional utilities are separate from skill installation; no runtime is installed or invoked."}

def doctor(root=ROOT):
    return [issue["message"] for issue in doctor_status(root)["issues"]]

def main():
    p=argparse.ArgumentParser(description="TuckBit Phase 1 local inspector (never invokes an AI agent).")
    sub=p.add_subparsers(dest="command",required=True)
    d=sub.add_parser("doctor",help="check source or skill packaging; read-only, no host activation")
    d.add_argument("--root",type=Path,default=ROOT,help="source checkout or installed tuck-bit skill directory")
    d.add_argument("--json",action="store_true",help="sanitized machine-readable status with reason codes")
    c=sub.add_parser("config",help="print resolved module policy; read-only")
    c.add_argument("--project",default=".")
    c.add_argument("--global-config",default=None)
    c.add_argument("--project-only",action="store_true",help="read defaults and project policy only; ignore global configuration")
    c.add_argument("--json-errors",action="store_true",help="emit sanitized JSON errors on stderr")
    c.add_argument("--profile",choices=VALID_PROFILES)
    c.add_argument("--enable",action="append",default=[],metavar="MODULE")
    c.add_argument("--disable",action="append",default=[],metavar="MODULE")
    args=p.parse_args()
    if args.command=="doctor":
        status=doctor_status(args.root)
        if args.json:
            print(json.dumps(status,indent=2))
        else:
            print("TuckBit doctor: "+status["status"].upper())
            for item in status["issues"]: print(" - "+item["message"])
        return 0 if status["status"]=="pass" else 1
    try:
        print(json.dumps(resolve(args.project,args.global_config,args.profile,args.enable,args.disable,args.project_only),indent=2))
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        if args.json_errors:
            print(json.dumps({"schema":1,"status":"error","code":"invalid_configuration",
                              "message":"Cannot resolve module policy; check catalog and selected configuration files."}),file=os.sys.stderr)
        else:
            print(f"TuckBit configuration error: {exc}",file=os.sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
