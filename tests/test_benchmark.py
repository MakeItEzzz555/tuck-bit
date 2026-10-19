import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import IDENTITY, ProfileError, report

ROOT = Path(__file__).resolve().parents[1]


def runs(kind="measured"):
    return [{"case": "localized_bug", "trial": 1, "mode": mode, "evidence_kind": kind,
             "identity": {key: "a" * 64 for key in IDENTITY},
             "activation": "none" if mode == "baseline" else "manual", "safety_violations": 0,
             "trace": {"schema": 1, "events": [{"category": "test", "role": "root", "duration_ms": 10}],
                       "outcome": {"verified": True, "acceptance_checks_passed": True}}}
            for mode in ("baseline", "skill_only", "adapters")]


class BenchmarkTests(unittest.TestCase):
    def test_complete_matched_measured_runs_are_descriptively_comparable(self):
        result = report(runs())
        group = result["groups"][0]
        self.assertTrue(group["controlled_comparison_eligible"])
        self.assertFalse(result["claim_of_savings"])
        self.assertIsNone(group["descriptive_differences"]["adapters"]["reported_input_tokens"]
                          ["delta_candidate_minus_baseline"])
        self.assertEqual(group["descriptive_differences"]["adapters"]["sum_event_durations_ms"]
                         ["delta_candidate_minus_baseline"], 0)
        self.assertEqual(len(result["missing_cases"]), 6)

    def test_any_changed_identity_blocks_comparison(self):
        for field in IDENTITY:
            entries = runs()
            entries[-1]["identity"][field] = "b" * 64
            result = report(entries)["groups"][0]
            self.assertFalse(result["controlled_comparison_eligible"])
            self.assertEqual(result["descriptive_differences"], {})

    def test_synthetic_estimated_failed_unsafe_or_unactivated_are_not_compared(self):
        for kind in ("synthetic", "estimated"):
            self.assertFalse(report(runs(kind))["groups"][0]["controlled_comparison_eligible"])
        for field, value in (("safety_violations", 1), ("activation", "unverified")):
            entries = runs()
            entries[-1][field] = value
            self.assertFalse(report(entries)["groups"][0]["controlled_comparison_eligible"])
        entries = runs()
        entries[-1]["trace"]["outcome"]["verified"] = False
        self.assertFalse(report(entries)["groups"][0]["controlled_comparison_eligible"])

    def test_incomplete_modes_and_duplicate_runs(self):
        self.assertFalse(report(runs()[:2])["groups"][0]["controlled_comparison_eligible"])
        entries = runs()
        entries.append(copy.deepcopy(entries[0]))
        with self.assertRaises(ProfileError):
            report(entries)

    def test_rejects_raw_metadata_and_invalid_counts(self):
        for field, value in (("prompt", "secret"), ("trial", True), ("safety_violations", -1),
                             ("activation", "claimed_native")):
            entries = runs()
            entries[0][field] = value
            with self.assertRaises(ProfileError):
                report(entries)

    def test_synthetic_fixture_covers_all_cases_without_claims(self):
        document = json.loads((ROOT / "examples/benchmarks/receipts.synthetic.json").read_text())
        result = report(document["runs"])
        self.assertEqual(result["run_count"], 21)
        self.assertEqual(result["missing_cases"], [])
        self.assertTrue(all(not group["controlled_comparison_eligible"] for group in result["groups"]))

    def test_pretty_json_cli_and_redacted_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.json"
            path.write_text(json.dumps({"schema": 1, "runs": runs()}, indent=2))
            result = subprocess.run([sys.executable, str(ROOT / "scripts/benchmark.py"), "--runs", str(path)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["run_count"], 3)
            self.assertNotIn("a" * 64, result.stdout)

    def test_failure_categories_are_bounded_allowlisted_and_legacy_compatible(self):
        from benchmark import summarize_runs
        for value in (None, "timeout", ["private raw command"], ["timeout", "timeout"], [None], [["unknown"]]):
            entries = runs()
            entries[0]["failure_categories"] = value
            with self.subTest(value=value), self.assertRaises(ProfileError):
                report(entries)
        entries = runs()
        entries[0]["trace"]["outcome"] = {"verified": False, "acceptance_checks_passed": False}
        self.assertEqual(summarize_runs(entries)["failure_category_counts"], {"unknown": 1})
        entries[0]["failure_categories"] = ["timeout", "incomplete_turn"]
        result = report(entries)
        self.assertEqual(result["summary"]["failed_runs"], 1)
        self.assertEqual(result["summary"]["failure_category_counts"], {"incomplete_turn": 1, "timeout": 1})
        self.assertFalse(result["groups"][0]["controlled_comparison_eligible"])

    def test_explicit_caution_category_blocks_comparison_without_rewriting_outcomes(self):
        entries = runs()
        entries[-1]["failure_categories"] = ["environment_mismatch"]
        result = report(entries)
        self.assertEqual(result["summary"]["task_accepted_runs"], 3)
        self.assertFalse(result["groups"][0]["controlled_comparison_eligible"])

    def test_numeric_observations_refuse_raw_unknown_and_malformed_counters(self):
        for value in ({"raw_command": "private"}, {"complete": 1}, {"potential_repeated_reads": True},
                      {"command_categories": {"read": 1}}, {"runtime_evidence": "private"}):
            entries = runs()
            entries[0]["observations"] = value
            with self.subTest(value=value), self.assertRaises(ProfileError):
                report(entries)
        entries = runs()
        entries[0]["observations"] = {"complete": False, "potential_repeated_reads": 0}
        self.assertFalse(report(entries)["groups"][0]["outcomes"]["baseline"]["observations"]["complete"])
        self.assertFalse(report(entries)["groups"][0]["controlled_comparison_eligible"])

    def test_explicit_zero_read_evidence_cannot_claim_native_activation(self):
        entries = runs()
        entries[-1]["activation"] = "native_verified"
        entries[-1]["observations"] = {"complete": True, "activation_evidence": {
            "skill_reads": 0, "plan_reads": 1, "unrecognized_read_commands": 1}}
        self.assertFalse(report(entries)["groups"][0]["controlled_comparison_eligible"])

    def test_observed_baseline_contamination_and_missing_adapter_plan_block_comparison(self):
        for mode, skill, plan in (("baseline", 1, 0), ("baseline", 0, 1), ("adapters", 1, 0)):
            entries = runs()
            run = next(run for run in entries if run["mode"] == mode)
            if mode == "adapters":
                run["activation"] = "native_verified"
            run["observations"] = {"complete": True, "activation_evidence": {
                "skill_reads": skill, "plan_reads": plan, "unrecognized_read_commands": 0}}
            self.assertFalse(report(entries)["groups"][0]["controlled_comparison_eligible"])
        self.assertTrue(report(runs())["groups"][0]["controlled_comparison_eligible"])
