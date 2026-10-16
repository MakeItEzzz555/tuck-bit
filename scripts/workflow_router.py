#!/usr/bin/env python3
"""Choose an advisory host-aware workflow from an explicit task and observable signals.

Zero model calls. No tool execution. No global context discovery. No hidden reasoning access.
"""
import argparse
import json
from pathlib import Path
from plan_task import compile_plan

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "skills/tuck-bit/assets/workflows.json"
SIGNALS = {
    "unchanged_retries", "failed_checks", "large_tool_outputs",
    "unresolved_dependencies", "duplicate_tool_calls", "file_conflicts"
}
EXTRA_KEYS = {
    "complexity", "enable_orchestration", "workstreams", "event_trigger",
    "checkpoint_reference", "signals", "review_only"
}
INPUT_KEYS = {
    "request", "constraints", "host", "model", "tools", "needed_tools",
    "instruction_references", "risk", "parallel", "continuous", "checks"
}
MODES = ("fast", "standard", "deep")
MAX_INPUT_BYTES = 128000

def _check_strings(values, label, limit=40):
    if not isinstance(values, list) or len(values) > limit:
        raise ValueError(label + " must be a bounded list")
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(label + " must contain nonempty strings")

def _validate_workstreams(items):
    if not isinstance(items, list) or len(items) > 8:
        raise ValueError("workstreams must be a list of at most 8")
    seen = set()
    collisions = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"goal", "owned_files"}:
            raise ValueError("each workstream requires goal and owned_files")
        if not isinstance(item["goal"], str) or not item["goal"].strip():
            raise ValueError("workstream goal must be nonempty")
        _check_strings(item["owned_files"], "owned_files")
        if not item["owned_files"]:
            raise ValueError("workstreams require at least one owned file")
        for file in item["owned_files"]:
            normalized = file.replace("\\", "/").lower()
            if normalized.startswith("/") or ":" in normalized or ".." in normalized.split("/"):
                raise ValueError("workstream ownership must be repository-relative")
            if normalized in seen:
                collisions.append(file)
            seen.add(normalized)
    return sorted(set(collisions))

def _signals(obj):
    if not isinstance(obj, dict) or set(obj) - SIGNALS:
        raise ValueError("signals must be a dictionary of allowed observations")
    for key, value in obj.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10000:
            raise ValueError("signal values must be bounded nonnegative integers")
    return obj

def route(task):
    if not isinstance(task, dict):
        raise ValueError("task must be an object")
    unknown = set(task) - EXTRA_KEYS - INPUT_KEYS
    if unknown:
        raise ValueError("unknown task fields: " + ", ".join(sorted(unknown)))
    if task.get("complexity", "standard") not in MODES:
        raise ValueError("complexity must be fast, standard or deep")
    if not isinstance(task.get("enable_orchestration", False), bool):
        raise ValueError("enable_orchestration must be boolean")
    if not isinstance(task.get("review_only", False), bool):
        raise ValueError("review_only must be boolean")
    for field in ("event_trigger", "checkpoint_reference"):
        if field in task and (
            not isinstance(task[field], str) or not task[field].strip()
            or len(task[field]) > 300
        ):
            raise ValueError(field + " must be a short nonempty string")
    observations = _signals(task.get("signals", {}))
    streams = task.get("workstreams", [])
    collisions = _validate_workstreams(streams)
    base = compile_plan({k:v for k,v in task.items() if k in INPUT_KEYS})
    policy = json.loads(CATALOG.read_text(encoding="utf-8"))
    host = base["host"]
    profile = policy["hosts"].get(host, policy["hosts"]["generic"])

    depth = task.get("complexity", "standard")
    reasons = ["Declared task complexity: " + depth]
    if base["execution"]["risk"] == "high" and depth != "deep":
        depth = "deep"
        reasons.append("High-risk task preserves deeper validation and final review")
    if observations.get("unresolved_dependencies", 0) >= 2 and depth == "fast":
        depth = "standard"
        reasons.append("Related dependencies require broader inspection")
    if observations.get("failed_checks", 0) >= 2 and depth != "deep":
        depth = "deep"
        reasons.append("Repeated failing checks require root-cause investigation")
    if task.get("review_only"):
        workflow = "review"
        reasons.append("Explicitly requested review-only work")
    else:
        workflow = "single"
    notices = []
    if task.get("parallel"):
        if task.get("enable_orchestration") and len(streams) >= 2 and not collisions and not observations.get("file_conflicts"):
            workflow = "parallel_candidate" if not task.get("review_only") else "review"
            reasons.append("Optional parallelism justified by bounded nonoverlapping ownership")
        else:
            notices.append("Parallelism deferred: requires opt-in, >=2 workstreams, and disjoint file ownership")
    if task.get("continuous"):
        if task.get("enable_orchestration") and task.get("event_trigger") and task.get("checkpoint_reference") and not task.get("review_only"):
            workflow = "event_driven_candidate"
            reasons.append("Optional loop has trigger and durable checkpoint")
        else:
            notices.append("Continuous work deferred: requires opt-in, event trigger and checkpoint reference")
    if collisions:
        notices.append("Overlapping file ownership: " + ", ".join(collisions))
    if observations.get("unchanged_retries", 0) >= 2:
        notices.append("Stop repeating unchanged attempts; inspect new evidence or seek user decision")
    if observations.get("duplicate_tool_calls", 0) >= 2:
        notices.append("Investigate repeated tool calls; use retained evidence and narrow results")
    if observations.get("large_tool_outputs", 0) >= 1:
        notices.append("Filter oversized tool output and preserve raw artifact references")
    if observations.get("file_conflicts", 0) >= 1:
        notices.append("Coordinate shared resources; serialize conflicting edits")
    checks = list(base["required_checks_verbatim"])
    if not checks:
        checks.append("Perform meaningful validation appropriate to scope and risk (not yet specified)")
    if base["execution"]["risk"] == "high":
        checks.append("Review required security and rollback implications")
    checks.append("Review final change or evidence and report remaining uncertainties")
    return {
        "schema": 1,
        "kind": "advisory_workflow",
        "task": base,
        "routing": {
            "depth": depth,
            "workflow": workflow,
            "reason": reasons,
            "notices": notices,
            "stage_sequence": policy["depths"][depth]["stages"],
            "validation_scope": policy["depths"][depth]["validation"],
            "host_strategy": profile["strategy"],
            "host_tool_selection": profile["tool_selection"],
            "host_worker_policy": profile["workers"],
            "host_source": profile["source"],
            "checks": checks,
            "observations": observations,
            "effective_permissions": "unknown; original host authorization always required",
            "tool_calls_made": 0,
            "model_calls_made": 0,
            "assurance": "suggested policy, not measured quality or enforced host behavior"
        }
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("task_file", help="Explicit JSON task file")
    p.add_argument("--output", help="Optional new output file; never overwrites")
    args = p.parse_args()
    try:
        source = Path(args.task_file).expanduser()
        if not source.is_file() or source.is_symlink() or source.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError("task source must be a small ordinary file")
        result = route(json.loads(source.read_text(encoding="utf-8")))
        data = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            dest = Path(args.output).expanduser()
            if dest.exists() or dest.is_symlink():
                raise ValueError("output exists; not overwriting")
            dest.write_text(data, encoding="utf-8")
            print("Wrote advisory workflow: " + str(dest))
        else:
            print(data, end="")
    except (ValueError, OSError, UnicodeError) as error:
        p.error(str(error))

if __name__ == "__main__":
    main()
