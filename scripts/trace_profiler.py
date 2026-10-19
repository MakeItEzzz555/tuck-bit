#!/usr/bin/env python3
"""Summarize explicitly supplied, redacted agent-event metrics without reading transcripts.

This is a descriptive profiler, not a model benchmark or token-savings claim.
No prompting, agent invocations, filesystem scans, or data uploads.
"""
import argparse
from collections import Counter
import json
import os
import stat
from pathlib import Path
import re
import sys

MAX_BYTES = 2097152
MAX_EVENTS = 10000
DIGEST = re.compile(r"^[0-9a-f]{64}$")
CATEGORIES = {"tool_read", "tool_write", "test", "build", "handoff",
              "agent_message", "planning", "other"}
ROLES = {"root", "worker", "reviewer"}
FIELDS = {"category", "role", "input_tokens", "cached_input_tokens",
          "output_tokens", "reasoning_output_tokens", "result_bytes",
          "duration_ms", "operation_sha256", "result_sha256", "revision_sha256",
          "tool_invocations", "model_invocations", "failed_attempts", "retries",
          "context_bytes", "output_bytes", "delegations", "delegation_overhead_ms"}
METRICS = ("input_tokens", "cached_input_tokens", "output_tokens",
           "reasoning_output_tokens", "result_bytes", "duration_ms",
           "tool_invocations", "model_invocations", "failed_attempts", "retries",
           "context_bytes", "output_bytes", "delegations", "delegation_overhead_ms")

class ProfileError(ValueError):
    pass

def read_text(path):
    if Path(path).is_symlink():
        raise ProfileError("Input must not be a symlink")
    fd = os.open(Path(path), os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ProfileError("Input must be an ordinary file")
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ProfileError("Input exceeds size limit")
    try:
        return content.decode("utf-8")
    except UnicodeError:
        raise ProfileError("Invalid UTF-8 input") from None


def load(path):
    try:
        trace = json.loads(read_text(path))
    except (ValueError, UnicodeError):
        raise ProfileError("Invalid UTF-8 JSON trace") from None
    validate(trace)
    return trace

def validate(trace):
    if (not isinstance(trace, dict) or not {"schema", "events", "outcome"} <= set(trace)
            or set(trace) - {"schema", "events", "outcome", "accounting", "wall_time_ms", "execution"}):
        raise ProfileError("Trace needs only schema, events, outcome")
    if type(trace["schema"]) is not int or trace["schema"] != 1:
        raise ProfileError("Unsupported trace schema")
    if "execution" in trace:
        from execution_events import validate as validate_execution
        validate_execution(trace["execution"])
    if "accounting" in trace and trace["accounting"] != {
            "cached_input": "included_in_input", "reasoning_output": "included_in_output"}:
        raise ProfileError("Unsupported accounting definitions; normalize explicitly before import")
    if "wall_time_ms" in trace and (type(trace["wall_time_ms"]) is not int
                                   or not 0 <= trace["wall_time_ms"] <= 10**12):
        raise ProfileError("Invalid wall time")
    events = trace["events"]
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ProfileError("Events must be a bounded list")
    outcome = trace["outcome"]
    if not isinstance(outcome, dict) or set(outcome) != {"verified", "acceptance_checks_passed"}:
        raise ProfileError("Outcome needs only verified and acceptance_checks_passed")
    if any(type(v) is not bool for v in outcome.values()):
        raise ProfileError("Outcome indicators must be explicit booleans")
    for event in events:
        if not isinstance(event, dict) or set(event) - FIELDS:
            raise ProfileError("Unexpected event fields (raw logs are not accepted)")
        if (not isinstance(event.get("category"), str) or event["category"] not in CATEGORIES
                or not isinstance(event.get("role"), str) or event["role"] not in ROLES):
            raise ProfileError("Invalid event category or role")
        for key in METRICS:
            value = event.get(key)
            if value is not None and (type(value) is not int or not 0 <= value <= 10**12):
                raise ProfileError("Invalid nonnegative metric: " + key)
        if (event.get("cached_input_tokens") is not None and event.get("input_tokens") is not None
                and event["cached_input_tokens"] > event["input_tokens"]):
            raise ProfileError("Cached input cannot exceed total input")
        if (event.get("reasoning_output_tokens") is not None and event.get("output_tokens") is not None
                and event["reasoning_output_tokens"] > event["output_tokens"]):
            raise ProfileError("Reasoning output cannot exceed reported total output")
        for key in ("operation_sha256", "result_sha256", "revision_sha256"):
            if key in event and (not isinstance(event[key], str) or not DIGEST.fullmatch(event[key])):
                raise ProfileError("Malformed digest: " + key)

def profile(trace):
    validate(trace)
    counts = Counter()
    aggregates = Counter()
    available = Counter()
    categories = Counter()
    roles = Counter()
    identical = Counter()
    big = 0
    for event in trace["events"]:
        counts["events"] += 1
        category = event["category"]
        categories[category] += 1
        roles[event["role"]] += 1
        for field in METRICS:
            if event.get(field) is not None:
                aggregates[field] += event[field]
                available[field] += 1
        if event.get("result_bytes") is not None and event["result_bytes"] >= 16384:
            big += 1
        if all(k in event for k in ("operation_sha256", "result_sha256", "revision_sha256")):
            # Same operation, exact same output and unchanged revision;
            # still only a potential duplicate; legitimate repetitions may exist.
            key = (event["category"], event["operation_sha256"],
                   event["result_sha256"], event["revision_sha256"])
            identical[key] += 1
    complete = lambda key: aggregates[key] if available[key] == counts["events"] and available[key] else None
    coverage = {key: {"measured_events": available[key], "total_events": counts["events"],
                       "status": "complete" if available[key] and available[key] == counts["events"]
                       else "partial" if available[key] else "unknown"} for key in METRICS}
    paired = [e["input_tokens"] - e["cached_input_tokens"] for e in trace["events"]
              if e.get("input_tokens") is not None and e.get("cached_input_tokens") is not None]
    result = {
        "schema": 1,
        "metric_availability": coverage,
        "observed_subtotals": {key: aggregates[key] if available[key] else None for key in METRICS},
        "reported_metrics": {key: complete(key) for key in METRICS},
        "wall_time_ms": trace.get("wall_time_ms"),
        "metrics_source": "explicit_redacted_trace",
        "verified_outcome": trace["outcome"]["verified"],
        "acceptance_checks_passed": trace["outcome"]["acceptance_checks_passed"],
        "event_count": counts["events"],
        "by_category": dict(sorted(categories.items())),
        "by_role": dict(sorted(roles.items())),
        "reported_input_tokens": complete("input_tokens"),
        "reported_cached_input_tokens": complete("cached_input_tokens"),
        "reported_uncached_input_tokens": sum(paired) if paired and len(paired) == counts["events"] else None,
        "reported_output_tokens": complete("output_tokens"),
        "reported_reasoning_output_tokens": complete("reasoning_output_tokens"),
        "total_result_bytes": complete("result_bytes"),
        "sum_event_durations_ms": complete("duration_ms"),
        "large_results_16k_or_more": big,
        "potential_identical_repeats": sum(n-1 for n in identical.values() if n>1),
        "limitations": [
            "Model/provider accounting varies; tokens are only caller-reported.",
            "Sum of event durations is not end-to-end wall time (overlap is possible).",
            "Identical calls may be necessary; a duplicate count is not proven waste.",
            "This does not collect raw prompts, file paths, tool arguments or outputs.",
            "Quality, cost and savings require controlled real-world A/B trials."
        ]
    }
    if "execution" in trace:
        from execution_events import summarize
        result["execution"] = summarize(trace["execution"])
    return result

def compare(base, candidate):
    a, b = profile(base), profile(candidate)
    differences = {}
    for key in ("event_count","reported_input_tokens","reported_cached_input_tokens",
                "reported_uncached_input_tokens","reported_output_tokens","reported_reasoning_output_tokens",
                "total_result_bytes","sum_event_durations_ms","wall_time_ms",
                "potential_identical_repeats"):
        differences[key] = {"baseline": a[key], "candidate": b[key],
                            "delta_candidate_minus_baseline": b[key]-a[key] if a[key] is not None and b[key] is not None else None}
    for metric in METRICS:
        left, right = a["reported_metrics"][metric], b["reported_metrics"][metric]
        differences["metric_" + metric] = {"baseline": left, "candidate": right,
            "delta_candidate_minus_baseline": right-left if left is not None and right is not None else None}
    comparable = a["verified_outcome"] and a["acceptance_checks_passed"] and (
        b["verified_outcome"] and b["acceptance_checks_passed"])
    return {"schema": 1, "both_verified": bool(comparable),
            "descriptive_differences": differences,
            "metric_availability": {"baseline": a["metric_availability"], "candidate": b["metric_availability"]},
            "claim_of_savings": False,
            "warning": "Synthetic or unmatched traces are NOT a controlled benchmark; verify outcomes and equivalent tasks."}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    single = sub.add_parser("profile")
    single.add_argument("--trace", required=True)
    pair = sub.add_parser("compare")
    pair.add_argument("--baseline", required=True)
    pair.add_argument("--candidate", required=True)
    args = parser.parse_args()
    try:
        if args.cmd == "profile":
            result = profile(load(args.trace))
        else:
            result = compare(load(args.baseline), load(args.candidate))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ProfileError, OSError) as error:
        print("TuckBit trace profiler rejected invalid or inaccessible input", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
