#!/usr/bin/env python3
"""Sanitized V4 matched analysis. Unknown/ineligible observations never become gains."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import statistics

from v4_runner import validate_receipt

MATCHED_IDENTITIES = {"task", "source", "dependencies", "environment", "model", "client", "runtime", "permissions", "configuration"}


def _median(values):
    return statistics.median(values) if values else None


def _bootstrap(values, repetitions=2000):
    # shortcut: fewer than 5 independent matched trial slots, report dispersion without a CI.
    if len(values) < 5:
        return None
    rng = random.Random(4)
    estimates = sorted(statistics.median(rng.choices(values, k=len(values))) for _ in range(repetitions))
    return {"lower": estimates[int(.025 * repetitions)], "upper": estimates[int(.975 * repetitions)],
            "method": "paired percentile bootstrap of trial-slot differences", "replicates": repetitions,
            "unit": "ms", "caution": "Within-task repeated trials and shared cache conditions can remain correlated."}


def _dispersion(values):
    if not values:
        return {"min": None, "max": None, "median_absolute_deviation": None}
    med = statistics.median(values)
    return {"min": min(values), "max": max(values), "median_absolute_deviation": statistics.median(abs(x-med) for x in values)}


def _matched_single(rows, arm):
    by_slot = defaultdict(dict)
    for row in rows:
        key = (row["case"], row["trial"])
        if row["mode"] in by_slot[key]:
            raise ValueError("Duplicate task/trial/arm receipt")
        by_slot[key][row["mode"]] = row
    attempts = accepted_a = accepted_b = mismatches = 0
    pairs, all_pairs = [], []
    for slots in by_slot.values():
        if "A" not in slots or arm not in slots:
            continue
        a, b = slots["A"], slots[arm]
        attempts += 1
        parity = all(a["identity"][key] == b["identity"][key] for key in MATCHED_IDENTITIES)
        parity &= a["domain"] == b["domain"] and a["complexity"] == b["complexity"]
        if not parity:
            mismatches += 1
            continue
        all_pairs.append((a, b))
        accepted_a += a["accepted"]
        accepted_b += b["accepted"]
        if a["comparison_eligible"] and b["comparison_eligible"]:
            pairs.append((a, b))
    deltas = [a["metrics"]["wall_ms"]["value"] - b["metrics"]["wall_ms"]["value"] for a, b in pairs]
    relative = [(a["metrics"]["wall_ms"]["value"] - b["metrics"]["wall_ms"]["value"]) / a["metrics"]["wall_ms"]["value"]
                for a, b in pairs if a["metrics"]["wall_ms"]["value"] > 0]
    token_deltas = {}
    for key in ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "tool_invocations"):
        differences = [a["metrics"][key]["value"] - b["metrics"][key]["value"] for a, b in pairs
                       if a["metrics"][key]["value"] is not None and b["metrics"][key]["value"] is not None]
        token_deltas[key] = {"median_paired_difference": _median(differences), "available_pairs": len(differences)}
    ci = _bootstrap(deltas)
    regression_count = sum(a["accepted"] and not b["accepted"] for a, b in all_pairs)
    security_regressions = sum(b["safety_violations"] > a["safety_violations"] for a, b in all_pairs)
    return {"arm": arm, "matched_attempts": attempts, "identity_mismatches": mismatches,
            "accepted_baseline": accepted_a, "accepted_treatment": accepted_b,
            "correctness_regressions": regression_count,
            "security_regressions": security_regressions,
            "eligible_accepted_pairs": len(pairs), "baseline_median_accepted_wall_ms": _median([a["metrics"]["wall_ms"]["value"] for a, _ in pairs]),
            "treatment_median_accepted_wall_ms": _median([b["metrics"]["wall_ms"]["value"] for _, b in pairs]),
            "median_paired_gain_ms": _median(deltas), "median_paired_relative_gain": _median(relative),
            "dispersion_gain_ms": _dispersion(deltas), "bootstrap_95_percent_ci_ms": ci,
            "metric_differences": token_deltas,
            "provisional_target_observed": bool(deltas and _median(deltas) >= 5000 and relative and _median(relative) >= .15 and not regression_count and not security_regressions),
            "repeatable_improvement_established": bool(len(pairs) >= 10 and len({a["identity"]["source"] for a, _ in pairs}) >= 3
                and ci is not None and ci["lower"] > 0 and _median(deltas) >= 5000
                and relative and _median(relative) >= .15 and not regression_count
                and not any(b["safety_violations"] > a["safety_violations"] for a, b in all_pairs)),
            "limitations": ["Accepted-only latency estimates are conditional on success; all matched correctness outcomes remain counted.",
                            "Targets are provisional; a favorable median is not a replicated product claim.",
                            "Source/model/client/configuration/permissions/dependencies/environment parity is mandatory."]}


STRATUM_IDENTITIES = ("model", "client", "environment", "runtime", "configuration")


def matched(rows, arm):
    """Pool repetitions only inside a common provider/model/environment stratum."""
    anchors = {(r["case"], r["trial"]): r for r in rows if r["mode"] == "A"}
    strata = defaultdict(list)
    for row in rows:
        anchor = anchors.get((row["case"], row["trial"]), row)
        key = tuple(anchor["identity"][name] for name in STRATUM_IDENTITIES)
        strata[key].append(row)
    result = _matched_single(rows, arm)
    result["strata"] = [{"identity": dict(zip(STRATUM_IDENTITIES, key)), "comparison": _matched_single(subset, arm)}
                         for key, subset in sorted(strata.items())]
    result["stratified"] = len(strata) > 1
    if result["stratified"]:
        for key in ("baseline_median_accepted_wall_ms", "treatment_median_accepted_wall_ms", "median_paired_gain_ms",
                    "median_paired_relative_gain", "bootstrap_95_percent_ci_ms"):
            result[key] = None
        result["dispersion_gain_ms"] = _dispersion([])
        result["provisional_target_observed"] = False
        result["repeatable_improvement_established"] = False
        for metric in result["metric_differences"].values():
            metric["median_paired_difference"] = None
        result["limitations"].append("Heterogeneous model/client/runtime/configuration strata are never pooled for performance claims.")
    return result


def diagnose(row):
    validate_receipt(row)
    demonstrated, hypotheses = [], []
    values = {key: metric["value"] for key, metric in row["metrics"].items()}
    if not row["activation_qualified"]:
        demonstrated.append("Treatment activation or uncontaminated baseline was not verified; causal comparison excluded.")
    if not row["isolation_verified"]:
        demonstrated.append("Host read isolation is unverified; native comparison excluded.")
    if row["safety_violations"]:
        demonstrated.append("Observed forbidden behavior or protected-source changes failed acceptance.")
    if values["initialization_ms"] is not None:
        demonstrated.append({"stage": "initialization", "measured_ms": values["initialization_ms"]})
    if values["verification_ms"] is not None:
        demonstrated.append({"stage": "verification", "measured_ms": values["verification_ms"]})
    if values['agent_ms'] is not None:
        demonstrated.append({'stage':'client_or_injected_transport','measured_ms':values['agent_ms']})
    if {'provider_error','incomplete_turn'} & set(row['failure_categories']):
        demonstrated.append('The client did not produce an accepted complete task; provider failure causes remain unknown unless independently observed.')
    if values["unclassified_commands"]:
        hypotheses.append("Unclassified commands need independent policy review; they are not proven violations or waste.")
    if values["cached_input_tokens"] is None:
        hypotheses.append("Cache-condition differences cannot be assessed from unavailable counters.")
    return {"case": row["case"], "trial": row["trial"], "mode": row["mode"], 'failure_categories':row['failure_categories'],
            "demonstrated": demonstrated, "hypotheses": hypotheses,
            "unattributed": ["Provider/model latency, repeated reads and permission waits require direct stage telemetry."]}


def critical_path(nodes, observation_source="synthetic"):
    """Adapt legacy span names to the shared orchestration analyzer."""
    from v4_experiments import analyze_spans
    if observation_source not in {"synthetic", "native_public_events"} or not isinstance(nodes, list) or not 1 <= len(nodes) <= 100:
        raise ValueError("Expected bounded explicitly sourced spans")
    if any(not isinstance(n, dict) or set(n) != {"id", "worker", "start_ms", "end_ms", "dependencies"} for n in nodes):
        raise ValueError("Unexpected span schema")
    if any(type(n[k]) not in {int, float} or not math.isfinite(n[k]) or n[k] < 0 for n in nodes for k in ("start_ms", "end_ms")):
        raise ValueError("Invalid numeric span")
    offset = min(n["start_ms"] for n in nodes)
    wall = max(n["end_ms"] for n in nodes) - offset
    spans = [{"id": n["id"], "worker": n["worker"], "start_ms": n["start_ms"]-offset,
              "end_ms": n["end_ms"]-offset, "depends_on": n["dependencies"], "stage": "execution"} for n in nodes]
    value = analyze_spans(spans, wall)
    return {"observation_source": observation_source, "workers": value["worker_count"], "wall_ms": wall,
            "sum_worker_span_ms": value["sequential_execution_estimate_ms"],
            "dependency_critical_path_ms": value["dependency_critical_path_ms"],
            "observed_parallel_benefit_ms": None, "limitations": [value["limitations"],
            "Legacy spans omit stage labels; no coordination-stage attribution is available."]}


def report(rows):
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError("Expected bounded receipt list")
    for row in rows:
        validate_receipt(row)
    keys = [(r["case"], r["trial"], r["mode"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate task/trial/arm")
    modes = {}
    for arm in ("A", "B", "C", "D"):
        selected = [r for r in rows if r["mode"] == arm]
        modes[arm] = {"attempts": len(selected), "accepted": sum(r["accepted"] for r in selected),
                      "activation_qualified": sum(r["activation_qualified"] for r in selected),
                      "eligible": sum(r["comparison_eligible"] for r in selected),
                      "median_accepted_wall_ms": _median([r["metrics"]["wall_ms"]["value"] for r in selected if r["accepted"] and r["metrics"]["wall_ms"]["value"] is not None]) if len({tuple(r["identity"][k] for k in STRATUM_IDENTITIES) for r in selected}) <= 1 else None,
                      "input_tokens_observed_sum": sum(r["metrics"]["input_tokens"]["value"] for r in selected if r["metrics"]["input_tokens"]["value"] is not None) if any(r["metrics"]["input_tokens"]["value"] is not None for r in selected) else None,
                      "input_token_coverage": sum(r["metrics"]["input_tokens"]["value"] is not None for r in selected)}
    categories = {}
    for domain in [f"D{n:02}" for n in range(1, 21)]:
        subset = [r for r in rows if r["domain"] == domain]
        categories[domain] = {"attempts": len(subset), "comparisons": [matched(subset, arm) for arm in ("B", "C", "D")]}
    return {"schema": 4, "attempts": len(rows), "native_attempts": sum(r["observation_source"] == "native_public_events" for r in rows),
            "accepted": sum(r["accepted"] for r in rows), "failed_or_incomplete": sum(not r["accepted"] for r in rows),
            "activation_qualified_treatments": sum(r["activation_qualified"] and r["mode"] != "A" for r in rows),
            "eligible": sum(r["comparison_eligible"] for r in rows), "modes": modes, "categories": categories,
            "comparisons": [matched(rows, arm) for arm in ("B", "C", "D")], "diagnoses": [diagnose(row) for row in rows],
            "roadmap": [{"capability": name, "decision": "unproven", "confidence": "insufficient replicated native evidence",
                         "recommended_default": default}
                        for name, default in [("portable_skill", "fast: no mandatory runtime commands"),
                                              ("registry", "standard/deep: explicit relevant metadata only"),
                                              ("context", "deep: targeted source references"),
                                              ("verification", "all modes: mandatory acceptance checks"),
                                              ("consolidated_preparation", "gate behind suitable medium/complex trials"),
                                              ("orchestration", "parallel: verified independent critical-path benefit only"),
                                              ("checkpoints", "continuous: explicit bounded resumable triggers")]],
            "limitations": ["Missing measurements are not evidence a capability is ineffective.",
                            "Model-free observations never establish native model speedups.",
                            "No strong improvement claim follows from a single accepted pair."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Explicit sanitized receipt list or private V4 journal")
    args = parser.parse_args()
    try:
        from execution_state import load
        value = load(args.input)
        rows = value["runs"] if isinstance(value, dict) and "runs" in value else value
        result = report(rows)
        if isinstance(value, dict):
            result["interrupted_trials"] = len(value.get("interrupted", []))
            result["inflight_trials"] = int(value.get("inflight") is not None)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
