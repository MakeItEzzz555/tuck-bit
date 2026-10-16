#!/usr/bin/env python3
"""Summarize explicitly supplied, redacted agent-event metrics without reading transcripts.

This is a descriptive profiler, not a model benchmark or token-savings claim.
No prompting, agent invocations, filesystem scans, or data uploads.
"""
import argparse
from collections import Counter, defaultdict
import json
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
          "duration_ms", "operation_sha256", "result_sha256", "revision_sha256"}
METRICS = ("input_tokens", "cached_input_tokens", "output_tokens",
           "reasoning_output_tokens", "result_bytes", "duration_ms")

class ProfileError(ValueError):
    pass

def load(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ProfileError("Trace must be a small ordinary file")
    try:
        trace = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ProfileError("Invalid UTF-8 JSON trace")
    validate(trace)
    return trace

def validate(trace):
    if not isinstance(trace, dict) or set(trace) != {"schema", "events", "outcome"}:
        raise ProfileError("Trace needs only schema, events, outcome")
    if trace["schema"] != 1:
        raise ProfileError("Unsupported trace schema")
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
        if event.get("category") not in CATEGORIES or event.get("role") not in ROLES:
            raise ProfileError("Invalid event category or role")
        for key in METRICS:
            value = event.get(key, 0)
            if type(value) is not int or not 0 <= value <= 10**12:
                raise ProfileError("Invalid nonnegative metric: " + key)
        if event.get("cached_input_tokens", 0) > event.get("input_tokens", 0):
            raise ProfileError("Cached input cannot exceed total input")
        if event.get("reasoning_output_tokens", 0) > event.get("output_tokens", 0):
            raise ProfileError("Reasoning output cannot exceed reported total output")
        for key in ("operation_sha256", "result_sha256", "revision_sha256"):
            if key in event and (not isinstance(event[key], str) or not DIGEST.fullmatch(event[key])):
                raise ProfileError("Malformed digest: " + key)

def profile(trace):
    validate(trace)
    counts = Counter()
    aggregates = Counter()
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
            aggregates[field] += event.get(field, 0)
        if event.get("result_bytes", 0) >= 16384:
            big += 1
        if all(k in event for k in ("operation_sha256", "result_sha256", "revision_sha256")):
            # Same operation, exact same output and unchanged revision;
            # still only a potential duplicate; legitimate repetitions may exist.
            key = (event["category"], event["operation_sha256"],
                   event["result_sha256"], event["revision_sha256"])
            identical[key] += 1
    return {
        "schema": 1,
        "metrics_source": "explicit_redacted_trace",
        "verified_outcome": trace["outcome"]["verified"],
        "acceptance_checks_passed": trace["outcome"]["acceptance_checks_passed"],
        "event_count": counts["events"],
        "by_category": dict(sorted(categories.items())),
        "by_role": dict(sorted(roles.items())),
        "reported_input_tokens": aggregates["input_tokens"],
        "reported_cached_input_tokens": aggregates["cached_input_tokens"],
        "reported_uncached_input_tokens": aggregates["input_tokens"]-aggregates["cached_input_tokens"],
        "reported_output_tokens": aggregates["output_tokens"],
        "reported_reasoning_output_tokens": aggregates["reasoning_output_tokens"],
        "total_result_bytes": aggregates["result_bytes"],
        "sum_event_durations_ms": aggregates["duration_ms"],
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

def compare(base, candidate):
    a, b = profile(base), profile(candidate)
    differences = {}
    for key in ("event_count","reported_input_tokens","reported_cached_input_tokens",
                "reported_uncached_input_tokens","reported_output_tokens",
                "total_result_bytes","sum_event_durations_ms",
                "potential_identical_repeats"):
        differences[key] = {"baseline": a[key], "candidate": b[key],
                            "delta_candidate_minus_baseline": b[key]-a[key]}
    comparable = a["verified_outcome"] and a["acceptance_checks_passed"] and (
        b["verified_outcome"] and b["acceptance_checks_passed"])
    return {"schema": 1, "both_verified": bool(comparable),
            "descriptive_differences": differences,
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
        print("TuckBit trace profiler error: " + str(error), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
