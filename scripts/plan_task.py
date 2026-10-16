#!/usr/bin/env python3
"""Compile an advisory task plan from explicitly supplied JSON. No model or host inspection."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ROOT / "skills/tuck-bit/assets/hosts.json"

def compile_plan(task, hosts=None):
    if not isinstance(task, dict):
        raise ValueError("Task must be a JSON object")
    allowed = {"request", "constraints", "host", "model", "tools", "needed_tools",
               "instruction_references", "risk", "parallel", "continuous", "checks"}
    unknown = set(task) - allowed
    if unknown:
        raise ValueError("Unexpected fields: " + ", ".join(sorted(unknown)))
    request = task.get("request")
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request must be nonempty text")
    if len(request.encode("utf-8")) > 128000:
        raise ValueError("Request too large")
    host_map = hosts or json.loads(HOSTS.read_text())["hosts"]
    host = task.get("host", "generic")
    if host not in host_map:
        raise ValueError("Unsupported host")
    constraints = task.get("constraints", [])
    checks = task.get("checks", [])
    references = task.get("instruction_references", [])
    tools = task.get("tools", [])
    needed = task.get("needed_tools", [])
    for key, values in (("constraints", constraints), ("checks", checks),
                        ("instruction_references", references), ("tools", tools),
                        ("needed_tools", needed)):
        if not isinstance(values, list) or len(values) > 100 or any(
                not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(key + " must be a list of nonempty strings")
    if any(not isinstance(task.get(k, False), bool) for k in ("parallel", "continuous")):
        raise ValueError("Parallel and continuous must be booleans")
    if task.get("risk", "normal") not in ("normal", "high"):
        raise ValueError("Risk must be normal or high")
    known = set(tools)
    chosen = [name for name in needed if name in known]
    missing = [name for name in needed if name not in known]
    mode = "single"
    if task.get("continuous"):
        mode = "recurring_candidate"
    elif task.get("parallel"):
        mode = "parallel_candidate"
    return {
        "schema": 1, "advisory_only": True,
        "request": request, "request_sha256": hashlib.sha256(request.encode()).hexdigest(),
        "constraints_verbatim": constraints, "required_checks_verbatim": checks,
        "instruction_references": references,
        "host": host, "model_label": task.get("model", "unspecified"),
        "host_execution_profile": host_map[host],
        "private_reasoning_observable": False,
        "capabilities": {"declared_available": tools, "requested_known": chosen,
                         "requested_unavailable": missing, "execution_performed": False},
        "execution": {"mode": mode, "risk": task.get("risk", "normal"),
            "native_permissions_required": True,
            "sequence": [
                "Read authoritative original task and applicable host-provided instructions.",
                "Select only relevant existing tools; expand discovery if necessary.",
                "Implement or research within supplied constraints and ownership.",
                "Verify stated acceptance checks and any mandatory safety gates.",
                "Return concise evidence, limitations, and stop or checkpoint."
            ],
            "notes": ["No hidden system prompt, private reasoning or live permissions were inspected.",
                      "The full request and constraints are preserved without paraphrasing.",
                      "Host profiles are guidelines; native policies and explicit user requests win."]}
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_file", help="Explicit task JSON path; never read agent configs")
    parser.add_argument("--output", help="Optional JSON output path (must not exist)")
    args = parser.parse_args()
    try:
        path = Path(args.task_file).expanduser()
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 180000:
            raise ValueError("Task must be a small regular file")
        task = json.loads(path.read_text(encoding="utf-8"))
        plan = compile_plan(task)
        result = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            dest = Path(args.output).expanduser()
            if dest.exists():
                raise ValueError("Output path exists")
            dest.write_text(result, encoding="utf-8")
        else:
            print(result, end="")
        return 0
    except (ValueError, OSError, UnicodeError) as error:
        parser.error(str(error))

if __name__ == "__main__":
    raise SystemExit(main())
