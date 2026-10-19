#!/usr/bin/env python3
"""Validate explicit controlled-run receipts; never launch a model or change permissions."""
import argparse
from collections import Counter
import json
import sys

from trace_profiler import DIGEST, ProfileError, compare, profile, validate

MODES = {"baseline", "skill_only", "adapters"}
CASES = {"localized_bug", "repository_search", "multi_file", "security_approval",
         "parallel", "failed_test_recovery", "review_only"}
IDENTITY = {"task_sha256", "source_sha256", "environment_sha256", "model_sha256", "permissions_sha256"}
ACTIVATIONS = {"none", "manual", "native_verified", "unverified"}
KINDS = {"measured", "synthetic", "estimated"}
FAILURE_CATEGORIES = {"task_acceptance", "activation_not_observed", "tool_policy", "timeout",
                      "provider_error", "incomplete_turn", "grader_limitation", "environment_mismatch", "unknown"}


def validate_failure_categories(categories):
    if (not isinstance(categories, list) or len(categories) > len(FAILURE_CATEGORIES)
            or any(not isinstance(value, str) or value not in FAILURE_CATEGORIES for value in categories)
            or len(categories) != len(set(categories))):
        raise ProfileError("Failure categories must be unique allowlisted enums")
    return categories


OBSERVATIONS = {"activation_evidence": {"skill_reads", "plan_reads", "unrecognized_read_commands"},
                "command_categories": {"read", "test", "build", "other"},
                "runtime_evidence": {"plan_task", "workflow_router", "packet", "checkpoint", "adaptive_execution"}}


def validate_observations(observations):
    allowed = set(OBSERVATIONS) | {"potential_repeated_reads", "complete"}
    if not isinstance(observations, dict) or set(observations) - allowed:
        raise ProfileError("Unexpected observation fields")
    for key, value in observations.items():
        if key == "complete":
            if type(value) is not bool:
                raise ProfileError("Observation completeness must be explicit")
            continue
        values = [value]
        if key in OBSERVATIONS:
            if not isinstance(value, dict) or set(value) != OBSERVATIONS[key]:
                raise ProfileError("Unexpected observation counters")
            values = value.values()
        if any(type(count) is not int or not 0 <= count <= 10000 for count in values):
            raise ProfileError("Observation counters must be bounded integers")
    return observations


def validate_run(run):
    required = {"case", "trial", "mode", "evidence_kind", "identity", "activation", "safety_violations", "trace"}
    if not isinstance(run, dict) or not required <= set(run) or set(run) - required - {"failure_categories", "observations"}:
        raise ProfileError("Run must contain only the documented receipt fields")
    if any(not isinstance(run[key], str) or run[key] not in allowed
           for key, allowed in (("case", CASES), ("mode", MODES), ("evidence_kind", KINDS))):
        raise ProfileError("Unsupported case, mode or evidence kind")
    if type(run["trial"]) is not int or not 1 <= run["trial"] <= 1000:
        raise ProfileError("Invalid trial")
    if not isinstance(run["activation"], str) or run["activation"] not in ACTIVATIONS:
        raise ProfileError("Invalid activation method")
    if run["mode"] == "baseline" and run["activation"] != "none":
        raise ProfileError("Baseline cannot activate TuckBit")
    if run["mode"] != "baseline" and run["activation"] == "none":
        raise ProfileError("TuckBit modes must record activation status")
    identity = run["identity"]
    if (not isinstance(identity, dict) or set(identity) != IDENTITY or
            any(not isinstance(value, str) or not DIGEST.fullmatch(value) for value in identity.values())):
        raise ProfileError("Identity must contain only five SHA-256 fingerprints")
    if type(run["safety_violations"]) is not int or not 0 <= run["safety_violations"] <= 10000:
        raise ProfileError("Invalid safety violation count")
    validate(run["trace"])
    if "failure_categories" in run:
        validate_failure_categories(run["failure_categories"])
    if "observations" in run:
        validate_observations(run["observations"])


def diagnostic_categories(run):
    """Legacy failures remain unknown; never infer discarded provider payloads."""
    validate_run(run)
    categories = set(run.get("failure_categories", []))
    if run["safety_violations"]:
        categories.add("tool_policy")
    if run["activation"] == "unverified":
        categories.add("activation_not_observed")
    if not all(run["trace"]["outcome"].values()) and not categories - {"activation_not_observed"}:
        categories.add("unknown")
    return sorted(categories)


def summarize_runs(runs):
    if not isinstance(runs, list) or len(runs) > 1000:
        raise ProfileError("Runs must be a bounded list")
    counts = Counter(category for run in runs for category in diagnostic_categories(run))
    accepted = sum(all(run["trace"]["outcome"].values()) and run["safety_violations"] == 0 for run in runs)
    return {"run_count": len(runs), "task_accepted_runs": accepted, "failed_runs": len(runs)-accepted,
            "unverified_activation_runs": sum(run["activation"] == "unverified" for run in runs),
            "safety_violations": sum(run["safety_violations"] for run in runs),
            "failure_category_counts": dict(sorted(counts.items()))}


def report(runs):
    if not isinstance(runs, list) or not 1 <= len(runs) <= 1000:
        raise ProfileError("Runs must be a nonempty bounded list")
    groups = {}
    for run in runs:
        validate_run(run)
        key = (run["case"], run["trial"])
        group = groups.setdefault(key, {})
        if run["mode"] in group:
            raise ProfileError("Duplicate case/trial/mode")
        group[run["mode"]] = run
    results = []
    for (case, trial), group in sorted(groups.items()):
        entries = list(group.values())
        matched = all(r["identity"] == entries[0]["identity"] for r in entries)
        complete = set(group) == MODES
        measured = all(r["evidence_kind"] == "measured" for r in entries)
        successful = all(r["trace"]["outcome"]["verified"] and
                         r["trace"]["outcome"]["acceptance_checks_passed"] and
                         r["safety_violations"] == 0 for r in entries)
        activated = all(r["activation"] in {"manual", "native_verified"}
                        for r in entries if r["mode"] != "baseline")
        eligible = (matched and complete and measured and successful and activated
                    and not any(r.get("failure_categories") for r in entries)
                    and all(r.get("observations", {}).get("complete", True) for r in entries)
                    and all(r["activation"] != "native_verified" or
                            r.get("observations", {}).get("activation_evidence", {}).get("skill_reads", 1) > 0 for r in entries)
                    and all(r["mode"] != "baseline" or not any(r.get("observations", {}).get("activation_evidence", {}).get(key, 0)
                                                             for key in ("skill_reads", "plan_reads")) for r in entries)
                    and all(r["mode"] != "adapters" or r["activation"] != "native_verified" or
                            r.get("observations", {}).get("activation_evidence", {}).get("plan_reads", 1) > 0 for r in entries))
        differences = {}
        if eligible:
            for mode in sorted(MODES - {"baseline"}):
                differences[mode] = compare(group["baseline"]["trace"], group[mode]["trace"])["descriptive_differences"]
        results.append({"case": case, "trial": trial, "complete_three_modes": complete,
                        "matched_identity": matched, "all_measured": measured,
                        "all_outcomes_and_safety_passed": successful,
                        "activation_evidenced": activated,
                        "controlled_comparison_eligible": eligible,
                        "outcomes": {mode: {**r["trace"]["outcome"], "safety_violations": r["safety_violations"],
                                             "activation": r["activation"], "evidence_kind": r["evidence_kind"],
                                             "failure_categories": diagnostic_categories(r), "observations": r.get("observations", {})}
                                     for mode, r in sorted(group.items())},
                        "profiles": {mode: profile(r["trace"]) for mode, r in sorted(group.items())},
                        "descriptive_differences": differences})
    return {"schema": 1, "run_count": len(runs), "groups": results, "summary": summarize_runs(runs),
            "covered_cases": sorted({r["case"] for r in runs}),
            "missing_cases": sorted(CASES - {r["case"] for r in runs}),
            "claim_of_savings": False,
            "limitations": ["Fingerprints and outcomes are caller attestations, not independently authenticated.",
                            "Unknown or partial metrics have null deltas; fixtures and estimates are not measured evidence.",
                            "One trial does not establish statistical benefit; retain all attempts and vary order."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", required=True, help="Explicit schema-1 JSON containing runs")
    args = parser.parse_args()
    try:
        # Reuse the bounded ordinary-file reader, but the document has its own schema.
        from provider_events import read_export
        document = json.loads(read_export(args.runs, approved=True))
        if not isinstance(document, dict) or set(document) != {"schema", "runs"}:
            raise ProfileError("Expected a JSON document with schema and runs")
        if type(document["schema"]) is not int or document["schema"] != 1:
            raise ProfileError("Unsupported benchmark schema")
        print(json.dumps(report(document["runs"]), sort_keys=True, indent=2))
        return 0
    except (ValueError, OSError, TypeError):
        print("TuckBit benchmark rejected: invalid or inaccessible receipt", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
