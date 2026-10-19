#!/usr/bin/env python3
"""Choose an advisory host-aware workflow from an explicit task and observable signals.

Zero model calls. No tool execution. No global context discovery. No hidden reasoning access.
"""
import argparse
import json
from pathlib import Path
from plan_task import compile_plan
from capability_registry import load_snapshot, query as find_capabilities, verify_sources
from trace_profiler import load as load_trace, profile as summarize_trace

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "skills/tuck-bit/assets/workflows.json"
MAX_INPUT_BYTES = 180000


def _ownership_collisions(items):
    owners = []
    collisions = set()
    for number, item in enumerate(items):
        for file in item["owned_files"]:
            normalized = "/".join(part for part in file.replace("\\", "/").lower().split("/") if part not in ("", "."))
            for previous, owner in owners:
                if owner != number and (normalized == previous or normalized.startswith(previous + "/") or previous.startswith(normalized + "/")):
                    collisions.add(file)
            owners.append((normalized, number))
    return sorted(collisions)


def route(task, capability_snapshot=None, trace_summary=None, *, capability_roots=None,
          capability_tools_file=None, capability_revision=None, capability_environment=None,
          focused_discovery=False):
    if type(focused_discovery) is not bool:
        raise ValueError("Focused discovery must be boolean")
    base = compile_plan(task)
    observations = dict(task.get("signals", {}))
    if trace_summary is not None:
        if not isinstance(trace_summary, dict) or trace_summary.get("metrics_source") != "explicit_redacted_trace":
            raise ValueError("Unsupported trace summary")
        for signal, metric in (("duplicate_tool_calls", "potential_identical_repeats"),
                               ("large_tool_outputs", "large_results_16k_or_more")):
            value = trace_summary.get(metric)
            if type(value) is not int or not 0 <= value <= 10000:
                raise ValueError("Invalid trace-derived metric: " + metric)
            observations[signal] = max(observations.get(signal, 0), value)
    streams = task.get("workstreams", [])
    collisions = _ownership_collisions(streams)
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
    candidates = []
    registry_freshness = "not_supplied"
    if capability_snapshot is not None:
        # Reading an old catalog is not evidence that a tool remains available.
        if capability_roots is None:
            registry_freshness = "unverified"
            notices.append("Registry ignored: explicitly reverify its roots, tools snapshot and binding before discovery")
        elif not verify_sources(capability_snapshot, capability_roots, capability_tools_file,
                                capability_revision, capability_environment):
            registry_freshness = "stale"
            notices.append("Registry ignored: sources, revision or environment changed")
        else:
            registry_freshness = "fresh_explicit_sources"
    if registry_freshness == "fresh_explicit_sources":
        if len(base["request"]) > 1000:
            notices.append("Capability discovery uses the first 1000 request characters; full task is preserved")
        for row in find_capabilities(capability_snapshot, base["request"][:1000], limit=5, focused=focused_discovery):
            candidates.append({"type": row["type"], "name": row["name"],
                               "provider": row.get("provider"),
                               "source": row["source"],
                               "relevance_score": row["relevance_score"],
                               "trust": "untrusted_metadata",
                               "permission": row.get("permission", "unknown"),
                               "requires_host_authorization": True})
    return {
        "schema": 1,
        "kind": "advisory_workflow",
        "task": base,
        "routing": {
            "depth": depth,
            "workflow": workflow,
            "reason": reasons,
            "notices": notices,
            "stage_sequence": base["execution"]["sequence"] if workflow == "review" else policy["depths"][depth]["stages"],
            "validation_scope": policy["depths"][depth]["validation"],
            "host_strategy": profile["strategy"],
            "host_tool_selection": profile["tool_selection"],
            "host_worker_policy": profile["workers"],
            "host_source": profile["source"],
            "checks": checks,
            "suggested_capabilities": candidates,
            "registry_freshness": registry_freshness,
            "prohibitions": base["effective_prohibitions"],
            "approvals": base["approvals_verbatim"],
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
    p.add_argument("--registry-snapshot", help="Explicit local capability metadata snapshot (advisory only)")
    p.add_argument("--registry-root", action="append", help="Explicit original registry skill root; repeatable")
    p.add_argument("--registry-tools-file", help="Explicit original registry tool metadata snapshot")
    p.add_argument("--source-revision", help="Explicit registry source binding")
    p.add_argument("--environment", help="Explicit registry environment binding")
    p.add_argument("--trace", help="Explicit redacted event trace used only for observable hints")
    args = p.parse_args()
    try:
        source = Path(args.task_file).expanduser()
        if not source.is_file() or source.is_symlink() or source.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError("task source must be a small ordinary file")
        catalog = load_snapshot(args.registry_snapshot) if args.registry_snapshot else None
        trace = summarize_trace(load_trace(args.trace)) if args.trace else None
        result = route(json.loads(source.read_text(encoding="utf-8")), catalog, trace,
                       capability_roots=(args.registry_root or []) if (args.registry_root is not None or args.registry_tools_file is not None) else None,
                       capability_tools_file=args.registry_tools_file,
                       capability_revision=args.source_revision, capability_environment=args.environment)
        data = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            dest = Path(args.output).expanduser()
            if dest.exists() or dest.is_symlink():
                raise ValueError("output exists; not overwriting")
            with dest.open("x", encoding="utf-8") as output:
                output.write(data)
            print("Wrote advisory workflow: " + str(dest))
        else:
            print(data, end="")
    except (ValueError, OSError, UnicodeError) as error:
        p.error(str(error))

if __name__ == "__main__":
    main()
