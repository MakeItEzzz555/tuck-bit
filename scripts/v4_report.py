#!/usr/bin/env python3
"""Reproduce Tier 0 and assemble sanitized evidence; never invoke a model."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess

from execution_state import digest, load, write_new
import v4_analysis
import v4_corpus
import v4_experiments
import v4_runner

ROOT = Path(__file__).resolve().parents[1]
START = "257d9ecd5a81cf9e22f7aa727a4615a630ad1106"


def assemble(corpus_validation, experiments, native_rows=None):
    """Combine trusted module outputs; only receipt inputs are externally supplied."""
    manifest = v4_corpus.cases()
    expected_ids = {case["id"] for case in manifest}
    rows = corpus_validation["results"]
    if (len(rows) != 60 or {row["id"] for row in rows} != expected_ids
            or len(experiments["discovery"]) != 4
            or {row["catalog_raw_entries"] for row in experiments["discovery"]} != {10, 50, 250, 1000}
            or len(experiments["context"]) != 3
            or {row["files"] for row in experiments["context"]} != {30, 150, 1200}
            or not 1 <= len(experiments["preparation"]["trials"]) <= 20):
        raise ValueError("Incomplete model-free evidence")
    domains = {}
    for number in range(1, 21):
        domain = f"D{number:02}"
        selected = [case for case in manifest if case["domain"] == domain]
        domains[domain] = {"category": selected[0]["category"],
                           "difficulties": {level: sum(c["complexity"] == level for c in selected)
                                            for level in ("small", "medium", "complex")}}
    gates = {
        "sixty_validated_graders": corpus_validation["cases"] == corpus_validation["graders_validated"] == 60,
        "all_reference_seed_negative_checks": all(row["reference_accepted"] and row["seed_rejected"]
            and row["negative_rejected"] for row in corpus_validation["results"]),
        "preparation_parity": all(row["parity"] for row in experiments["preparation"]["trials"]),
        "registry_integrity": all(all(row[key] for key in (
            "fresh", "concurrent_reads_stable", "content_hash_invalidation_same_mtime",
            "revocation_propagated", "schema_change_invalidated", "malformed_duplicate_schema_rejected"))
            for row in experiments["discovery"]),
        "context_integrity": all(row["stale_evidence_rejected"] and row["dependency_excerpts_correct"] and row['reference_runtime_correct']
            and all(row["static_activity_probes"].values()) for row in experiments["context"]),
    }
    native = v4_analysis.report([] if native_rows is None else native_rows)
    qualified = sum(case.get("complexity_qualified") is True for case in manifest)
    remaining = max(0, 6-1-native['native_attempts'])
    return {"schema": 4, "kind": "v4_evidence", "starting_revision": START,
            "observation_source": "local_model_free_and_separately_qualified_native_receipts",
            "deterministic_validation_passed": all(gates.values()),
            "tier0_passed": all(gates.values()) and qualified == 60, "model_free_gates": gates,
            "corpus_qualification": {"nominal_cases": len(manifest), "qualified_controlled_cases": qualified,
                "unqualified_cases": [case["id"] for case in manifest if case.get("complexity_qualified") is not True],
                "full_complexity_coverage_ready": qualified == 60},
            "corpus_distribution": domains, "corpus_validation": corpus_validation,
            "deterministic_experiments": experiments, "native": native,
            "known_launch_accounting": {'initial_ceiling':6, 'retained_harness_incident':1,
                'supplied_native_attempts':native['native_attempts'], 'known_remaining':remaining,
                'limitation':'Counts only the preserved incident and explicitly supplied receipts; no private/global usage scan.'},
            "native_plan": v4_runner.plan(["D05-small"], run_budget=remaining, time_budget=remaining*120) if remaining >= 3 else None,
            "limitations": ["Controlled difficulty is relative to bounded fixtures; production generalization requires richer tasks.",
                            "No native task gain is established by deterministic preparation timings.",
                            "HTML semantics and interpreted Swift predicates are not browser/native runtime acceptance.",
                            "Native execution requires current macOS/Codex 0.163.0 canary proof; inert plans never establish readiness.",
                            "Continuous workers and other providers require separate native evidence."]}


def implementation_identity():
    files = [*sorted((ROOT / "scripts").glob("*.py")), *sorted((ROOT / "evals/v4").rglob("*.json")),
             ROOT / "docs/evaluations/V4_EVALUATION_DESIGN.md"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def reproduce(repeats=5, native_rows=None):
    before = implementation_identity()
    corpus_validation = v4_corpus.validate_all()
    experiments = {"schema": 1, "observation_source": "local deterministic stdlib experiments", "model_calls": 0,
                   "preparation": v4_experiments.preparation_benchmark(repeats),
                   "discovery": v4_experiments.discovery_benchmark(),
                   "context": v4_experiments.context_benchmark(),
                   "orchestration": {"native_runs": 0, "benefit": None, "analyzer_available": True}}
    result = assemble(corpus_validation, experiments, native_rows)
    if implementation_identity() != before:
        raise ValueError("Implementation changed during model-free measurements")
    result["implementation_sha256"] = digest(before)
    result["protocol_sha256"] = before["docs/evaluations/V4_EVALUATION_DESIGN.md"]
    result["environment"] = {"python": platform.python_version(), "system": platform.system(),
                             "machine": platform.machine(), "sqlite": sqlite3.sqlite_version}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New private sanitized result file; no overwrite")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--native-receipts", help="Explicit existing sanitized receipt list or private V4 journal")
    args = parser.parse_args()
    try:
        rows, markers = None, None
        if args.native_receipts:
            value = load(args.native_receipts)
            if isinstance(value, dict):
                journal = object.__new__(v4_runner.V4Journal)
                journal.document = value
                journal._validate()
                rows = value["runs"]
                markers = {"interrupted": value["interrupted"], "inflight": value["inflight"]}
            else:
                rows = value
        result = reproduce(args.repeats, rows)
        if markers is not None:
            result["native_journal_markers"] = markers
        write_new(args.output, result)
        print(json.dumps({"written": True, "tier0_passed": result["tier0_passed"],
                          "validated_graders": result["corpus_validation"]["graders_validated"],
                          "native_attempts": result["native"]["native_attempts"]}))
        return int(not result["tier0_passed"])
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, subprocess.TimeoutExpired):
        parser.error("Invalid V4 inputs or failed model-free experiment; no native invocation performed")


if __name__ == "__main__":
    raise SystemExit(main())
