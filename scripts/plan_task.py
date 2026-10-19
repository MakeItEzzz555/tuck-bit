#!/usr/bin/env python3
"""Compile an advisory task plan from explicitly supplied JSON. No model or host inspection."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ROOT / "skills/tuck-bit/assets/hosts.json"

TASK_KEYS = {
    "request", "constraints", "host", "model", "tools", "needed_tools",
    "instruction_references", "risk", "parallel", "continuous", "checks",
    "complexity", "enable_orchestration", "workstreams", "event_trigger",
    "checkpoint_reference", "signals", "review_only", "approvals",
    "forbidden_operations", "risk_factors"
}
SIGNALS = {
    "unchanged_retries", "failed_checks", "large_tool_outputs",
    "unresolved_dependencies", "duplicate_tool_calls", "file_conflicts"
}
RISK_FACTORS = {"security", "data_loss", "privacy", "production", "permissions"}


def check_strings(values, label, limit=100):
    if not isinstance(values, list) or len(values) > limit or any(
            not isinstance(v, str) or not v.strip() or len(v.encode("utf-8")) > 8192
            for v in values):
        raise ValueError(label + " must be a bounded list of nonempty strings")


def validate_task(task, hosts=None):
    """One explicit envelope for compiler and router; descriptions confer no authority."""
    if not isinstance(task, dict):
        raise ValueError("Task must be a JSON object")
    if set(task) - TASK_KEYS:
        raise ValueError("Unexpected fields: " + ", ".join(sorted(set(task) - TASK_KEYS)))
    if len(json.dumps(task, ensure_ascii=False).encode("utf-8")) > 180000:
        raise ValueError("Task too large")
    request = task.get("request")
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request must be nonempty text")
    if len(request.encode("utf-8")) > 128000:
        raise ValueError("Request too large")
    host_map = hosts if hosts is not None else json.loads(HOSTS.read_text())["hosts"]
    host = task.get("host", "generic")
    if not isinstance(host, str) or host not in host_map:
        raise ValueError("Unsupported host")
    for key in ("constraints", "checks", "instruction_references", "tools", "needed_tools",
                "approvals", "forbidden_operations", "risk_factors"):
        check_strings(task.get(key, []), key)
    if any(not isinstance(task.get(k, False), bool) for k in (
            "parallel", "continuous", "enable_orchestration", "review_only")):
        raise ValueError("Workflow flags must be booleans")
    if not isinstance(task.get("risk", "normal"), str) or task.get("risk", "normal") not in ("normal", "high"):
        raise ValueError("Risk must be normal or high")
    if set(task.get("risk_factors", [])) - RISK_FACTORS:
        raise ValueError("Unsupported explicit risk factor")
    if not isinstance(task.get("complexity", "standard"), str) or task.get("complexity", "standard") not in ("fast", "standard", "deep"):
        raise ValueError("complexity must be fast, standard or deep")
    for field in ("event_trigger", "checkpoint_reference", "model"):
        if field in task and (not isinstance(task[field], str) or not task[field].strip()
                              or len(task[field]) > 300):
            raise ValueError(field + " must be short nonempty text")
    signals = task.get("signals", {})
    if not isinstance(signals, dict) or set(signals) - SIGNALS:
        raise ValueError("signals must contain allowed observations")
    if any(type(value) is not int or not 0 <= value <= 10000 for value in signals.values()):
        raise ValueError("signals must be bounded nonnegative integers")
    streams = task.get("workstreams", [])
    if not isinstance(streams, list) or len(streams) > 8:
        raise ValueError("workstreams must be a list of at most 8")
    for item in streams:
        if not isinstance(item, dict) or set(item) != {"goal", "owned_files"}:
            raise ValueError("each workstream requires goal and owned_files")
        check_strings([item["goal"]], "goal", 1)
        check_strings(item["owned_files"], "owned_files", 40)
        if not item["owned_files"]:
            raise ValueError("workstreams require owned files")
        for file in item["owned_files"]:
            normalized = file.replace("\\", "/")
            if (normalized.startswith("/") or ":" in normalized or ".." in normalized.split("/")
                    or not normalized.strip("./") or any(ord(c) < 32 for c in normalized)
                    or any(c in normalized for c in "*?[]")):
                raise ValueError("workstream ownership must be repository-relative")
    return task


def compile_plan(task, hosts=None):
    validate_task(task, hosts)
    request = task["request"]
    host_map = hosts if hosts is not None else json.loads(HOSTS.read_text())["hosts"]
    host = task.get("host", "generic")
    constraints = task.get("constraints", [])
    checks = task.get("checks", [])
    references = task.get("instruction_references", [])
    tools = task.get("tools", [])
    needed = task.get("needed_tools", [])
    known = set(tools)
    chosen = [name for name in needed if name in known]
    missing = [name for name in needed if name not in known]
    mode = "single"
    if task.get("review_only"):
        mode = "review"
    elif task.get("continuous"):
        mode = "recurring_candidate"
    elif task.get("parallel"):
        mode = "parallel_candidate"
    return {
        "schema": 1, "advisory_only": True,
        "task_input": json.loads(json.dumps(task)),
        "approvals_verbatim": list(task.get("approvals", [])),
        "forbidden_operations_verbatim": list(task.get("forbidden_operations", [])),
        "effective_prohibitions": list(task.get("forbidden_operations", [])) + (
            ["Review only: do not modify source, perform unapproved side effects, or initiate unrelated work"]
            if task.get("review_only") else []),
        "risk_assessment": {"source": "explicit_fields_only", "verified": False,
                            "factors": list(task.get("risk_factors", [])),
                            "note": "Caller declarations are not host authorization or a safety assessment"},
        "request": request, "request_sha256": hashlib.sha256(request.encode()).hexdigest(),
        "constraints_verbatim": list(constraints), "required_checks_verbatim": list(checks),
        "instruction_references": list(references),
        "host": host, "model_label": task.get("model", "unspecified"),
        "host_execution_profile": host_map[host],
        "private_reasoning_observable": False,
        "capabilities": {"declared_available": tools, "requested_known": chosen,
                         "requested_unavailable": missing, "execution_performed": False},
        "execution": {"mode": mode, "risk": "high" if task.get("risk_factors") else task.get("risk", "normal"),
            "native_permissions_required": True,
            "sequence": [
                "Read authoritative original task and applicable host-provided instructions.",
                "Select only relevant existing tools; expand discovery if necessary.",
                ("Review evidence without modifying source; preserve supplied constraints and ownership."
                 if task.get("review_only") else "Implement or research within supplied constraints and ownership."),
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
            if dest.exists() or dest.is_symlink():
                raise ValueError("Output path exists")
            with dest.open("x", encoding="utf-8") as output:
                output.write(result)
        else:
            print(result, end="")
        return 0
    except (ValueError, OSError, UnicodeError) as error:
        parser.error(str(error))

if __name__ == "__main__":
    raise SystemExit(main())
