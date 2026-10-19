#!/usr/bin/env python3
"""Explicit, bound execution feedback. No scans, model calls or permission changes."""
import argparse
from collections import Counter
import copy
import json
from pathlib import PurePosixPath

from execution_state import binding, digest, load, write_new, DIGEST
from plan_task import compile_plan, RISK_FACTORS
from trace_profiler import profile
from workflow_router import route

DEPTHS = ("fast", "standard", "deep")
RESULTS = {"passed", "failed", "skipped", "blocked"}
PROVENANCE = {"host_observed", "user_declared", "synthetic", "unknown"}
LIMITS = {"max_retries": (0, 20), "max_result_bytes": (128, 10**7), "max_delegations": (0, 8)}


def exact(value, fields, label, optional=()):
    if not isinstance(value, dict) or set(value) - set(fields) - set(optional) or set(fields) - set(value):
        raise ValueError("Invalid " + label + " fields")


def fingerprint(value):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise ValueError("Expected a lowercase SHA-256 fingerprint")


def current_binding(value):
    exact(value, ("revision", "environment"), "binding")
    return binding(value["revision"], value["environment"])


def bounded_list(value, maximum, label):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(label + " must be a bounded list")


def validate_scope(scope):
    exact(scope, ("source_sha256", "provenance"), "scope",
          ("repository_files", "changed_files", "risk_indicators", "independent_workstreams", "budgets"))
    fingerprint(scope["source_sha256"])
    provenance = scope["provenance"]
    exact(provenance, ("kind", "reference_sha256"), "provenance")
    if not isinstance(provenance["kind"], str) or provenance["kind"] not in PROVENANCE:
        raise ValueError("Unsupported observation provenance")
    fingerprint(provenance["reference_sha256"])
    for field, maximum in (("repository_files", 10**6), ("independent_workstreams", 8)):
        value = scope.get(field)
        if value is not None and (type(value) is not int or not 0 <= value <= maximum):
            raise ValueError("Invalid scope count: " + field)
    files = scope.get("changed_files")
    if files is not None:
        bounded_list(files, 200, "changed_files")
        seen = set()
        for path in files:
            if (not isinstance(path, str) or not path or len(path) > 1024
                    or any(ord(c) < 32 for c in path) or any(c in path for c in "\\:*?[]")):
                raise ValueError("Changed files require literal repository-relative paths")
            key = PurePosixPath(path)
            if key.is_absolute() or ".." in key.parts or str(key) == "." or str(key).casefold() in seen:
                raise ValueError("Unsafe or duplicate changed file")
            seen.add(str(key).casefold())
        if scope.get("repository_files") is not None and len(files) > scope["repository_files"]:
            raise ValueError("Changed-file count exceeds declared repository scope")
    risks = scope.get("risk_indicators", [])
    bounded_list(risks, 5, "risk_indicators")
    if any(not isinstance(risk, str) or risk not in RISK_FACTORS for risk in risks) or len(set(risks)) != len(risks):
        raise ValueError("Unsupported explicit risk indicator")
    budgets = scope.get("budgets", {})
    exact(budgets, (), "budgets", LIMITS)
    for key, value in budgets.items():
        low, high = LIMITS[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid advisory budget: " + key)


def prepare(task, scope, current, events=None, evidence=None):
    """Recommend from explicit observations; the exact original task stays separate."""
    contract = compile_plan(task)
    current = current_binding(current)
    validate_scope(scope)
    events = [] if events is None else events
    evidence = [] if evidence is None else evidence
    bounded_list(events, 500, "events")
    bounded_list(evidence, 100, "evidence")
    current_events = []
    stale_events = 0
    for row in events:
        exact(row, ("binding", "source_sha256", "event"), "event observation")
        current_binding(row["binding"])
        fingerprint(row["source_sha256"])
        # Reuse the profiler's strict allowlist; raw text/arguments are rejected.
        profile({"schema": 1, "events": [row["event"]],
                 "outcome": {"verified": False, "acceptance_checks_passed": False}})
        event = row["event"]
        if "revision_sha256" in event and event["revision_sha256"] != row["source_sha256"]:
            raise ValueError("Event revision fingerprint conflicts with its source binding")
        if row["binding"] == current and row["source_sha256"] == scope["source_sha256"]:
            current_events.append(event)
        else:
            stale_events += 1
    summary = profile({"schema": 1, "events": current_events,
                       "outcome": {"verified": False, "acceptance_checks_passed": False}})
    checks = contract["required_checks_verbatim"]
    results = {}
    stale_checks = set()
    identities = set()
    for row in evidence:
        exact(row, ("check", "result", "binding", "source_sha256", "contract_sha256", "evidence_sha256"), "validation evidence")
        current_binding(row["binding"])
        fingerprint(row["source_sha256"])
        fingerprint(row["evidence_sha256"])
        fingerprint(row["contract_sha256"])
        if not isinstance(row["check"], str) or row["check"] not in checks:
            raise ValueError("Evidence check must match an original mandatory check")
        if not isinstance(row["result"], str) or row["result"] not in RESULTS:
            raise ValueError("Unsupported validation result")
        identity = (row["check"], row["binding"]["revision"], row["binding"]["environment"], row["source_sha256"], row["contract_sha256"])
        if identity in identities:
            raise ValueError("Conflicting or duplicate validation evidence")
        identities.add(identity)
        if (row["binding"] == current and row["source_sha256"] == scope["source_sha256"]
                and row["contract_sha256"] == digest(contract)):
            results[row["check"]] = row["result"]
        else:
            stale_checks.add(row["check"])

    original = route(task)
    inferred = copy.deepcopy(task)
    inferred["risk_factors"] = sorted(set(task.get("risk_factors", [])) | set(scope.get("risk_indicators", [])))
    signals = dict(task.get("signals", {}))
    failed = sum(result == "failed" for result in results.values())
    failed = max(failed, summary["observed_subtotals"]["failed_attempts"] or 0)
    signals["failed_checks"] = max(signals.get("failed_checks", 0), min(10000, failed))
    inferred["signals"] = signals
    changed = scope.get("changed_files")
    floor = ("deep" if changed is not None and len(changed) >= 8 else "standard"
             if changed is None or scope.get("repository_files") is None
             or scope["provenance"]["kind"] == "unknown" or len(changed) >= 3
             or scope["repository_files"] >= 10000 else "fast")
    inferred["complexity"] = DEPTHS[max(DEPTHS.index(original["routing"]["depth"]), DEPTHS.index(floor))]
    selected = route(inferred, trace_summary=summary)["routing"]
    recommendations = []

    def recommend(name, reason):
        recommendations.append({"id": name, "reason": reason, "mandatory_checks_preserved": True})

    if changed is None or scope.get("repository_files") is None or scope["provenance"]["kind"] == "unknown":
        recommend("confirm_scope", "Scope is incomplete or unverified; retrieve only the relevant current evidence before narrowing work.")
    if selected["depth"] != original["routing"]["depth"]:
        recommend("broaden_inspection", "Observed scope, explicit risk or failed checks requires deeper inspection and validation.")
    operations = Counter((event["category"], event["operation_sha256"]) for event in current_events if "operation_sha256" in event)
    if any(count > 1 and category == "tool_read" for (category, _), count in operations.items()):
        recommend("reuse_read_evidence", "Same read operation recurred at the same bound source/environment; inspect retained evidence before rereading. Necessary rereads remain allowed.")
    maximum = scope.get("budgets", {}).get("max_result_bytes", 16384)
    if any((event.get("result_bytes") or 0) >= maximum for event in current_events):
        recommend("narrow_output", "Observed output reached the advisory size bound; narrow the next query and retain truncation/reread references.")
    if any(count > 1 and category == "test" for (category, _), count in operations.items()):
        recommend("justify_test_repeat", "The same test operation recurred on unchanged bound inputs; check whether new evidence justifies another run. Mandatory checks remain required.")
    retry_limit = scope.get("budgets", {}).get("max_retries", 2)
    retries = summary["observed_subtotals"]["retries"]
    if retries is not None and retries > 0 and retries >= retry_limit:
        recommend("reassess_retry", "Observed retries reached the advisory limit; change the evidence/approach or seek a decision before another unchanged attempt.")
    delegations = summary["observed_subtotals"]["delegations"]
    if delegations and ((changed is not None and len(changed) <= 2 and scope.get("independent_workstreams") == 0)
                        or delegations > scope.get("budgets", {}).get("max_delegations", 8)):
        recommend("reassess_delegation", "Reassess delegation against the observed independent work and overhead; retain required independent review and authorized parallel work.")
    status = {check: results.get(check, "stale" if check in stale_checks else "unknown") for check in checks}
    if not checks or any(result != "passed" for result in status.values()):
        recommend("complete_validation", "Acceptance is incomplete, stale or unspecified; perform original mandatory checks against current inputs before claiming completion.")
    inputs = copy.deepcopy({"task": task, "scope": scope, "binding": current, "events": events, "evidence": evidence})
    body = {"schema": 1, "kind": "adaptive_execution_advice", "inputs": inputs, "contract": contract,
            "binding": current, "source_sha256": scope["source_sha256"],
            "routing": selected, "recommendations": recommendations, "verification": status,
            "observability": {"current_events": len(current_events), "stale_events_ignored": stale_events,
                              "metrics": summary["reported_metrics"], "metric_availability": summary["metric_availability"],
                              "planned_source_ranges": None,
                              "reported_read_events": sum(event["category"] == "tool_read" for event in current_events) if current_events else None,
                              "read_coverage": "caller_selected_events_only"},
            "adherence": {item["id"]: "unknown" for item in recommendations},
            "advisory_only": True, "permissions_granted": False, "tools_executed": False,
            "limitations": ["Inputs and receipts are caller-declared, not authenticated host telemetry.",
                            "Hashes show consistency, not that a check/action ran or that selected scope is complete.",
                            "Advice cannot override original task, mandatory checks or native permissions."]}
    return {**body, "sha256": digest(body)}


def feedback(report, receipts):
    if not isinstance(report, dict) or not isinstance(report.get("inputs"), dict):
        raise ValueError("Expected an adaptive report with original inputs")
    inputs = report["inputs"]
    exact(inputs, ("task", "scope", "binding", "events", "evidence"), "report input")
    expected = prepare(inputs["task"], inputs["scope"], inputs["binding"], inputs["events"], inputs["evidence"])
    if expected != report:
        raise ValueError("Adaptive report changed; prepare current advice again")
    bounded_list(receipts, 8, "action receipts")
    adherence = dict(report["adherence"])
    for receipt in receipts:
        exact(receipt, ("recommendation_id", "status", "binding", "report_sha256", "evidence_sha256"), "action receipt")
        name = receipt["recommendation_id"]
        if not isinstance(name, str) or name not in adherence or adherence[name] != "unknown":
            raise ValueError("Unknown or duplicate recommendation receipt")
        if receipt["status"] not in ("followed", "declined", "not_applicable"):
            raise ValueError("Unsupported action receipt status")
        current_binding(receipt["binding"])
        fingerprint(receipt["evidence_sha256"])
        if receipt["binding"] != report["binding"] or receipt["report_sha256"] != report["sha256"]:
            raise ValueError("Action receipt belongs to stale or different advice")
        adherence[name] = receipt["status"]
    return {"schema": 1, "kind": "adaptive_action_feedback", "report_sha256": report["sha256"],
            "binding": copy.deepcopy(report["binding"]), "source_sha256": report["source_sha256"],
            "adherence": adherence, "observed_receipts": len(receipts), "advisory_only": True,
            "receipts_are_caller_reported": True, "permissions_granted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("input", help="Explicit JSON task/scope/binding/events/evidence envelope")
    p = commands.add_parser("feedback")
    p.add_argument("input", help="Previously prepared report")
    p.add_argument("receipts", help="Explicit bound action-receipt JSON list")
    for p in commands.choices.values():
        p.add_argument("--output", help="New private output file; refuses overwrite")
    args = parser.parse_args()
    try:
        value = load(args.input)
        if args.command == "prepare":
            exact(value, ("task", "scope", "binding"), "prepare input", ("events", "evidence"))
            result = prepare(value["task"], value["scope"], value["binding"], value.get("events"), value.get("evidence"))
        else:
            result = feedback(value, load(args.receipts))
        if args.output:
            write_new(args.output, result)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
