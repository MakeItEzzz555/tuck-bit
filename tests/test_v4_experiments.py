from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import v4_experiments as experiment


class V4ExperimentTests(unittest.TestCase):
    def test_preparation_actual_processes_and_parity(self):
        result = experiment.preparation_benchmark(2)
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["original_v3_commands"], 5)
        self.assertEqual(result["consolidated_commands"], 1)
        self.assertTrue(all(row["parity"] for row in result["trials"]))
        self.assertNotEqual(result["trials"][0]["order"], result["trials"][1]["order"])
        self.assertIsNone(result["native_task_benefit"])

    def test_adapters_zero_exit_does_not_bypass_parity(self):
        with patch.object(experiment, "command", return_value=None):
            with self.assertRaises((ValueError, OSError)):
                experiment.preparation_benchmark(1)

    def test_catalog_sizes_accuracy_and_safety(self):
        reports = experiment.discovery_benchmark()
        self.assertEqual([row["catalog_raw_entries"] for row in reports], [10, 50, 250, 1000])
        for report in reports:
            self.assertTrue(report["fresh"])
            self.assertTrue(report["content_hash_invalidation_same_mtime"])
            self.assertTrue(report["revocation_propagated"])
            self.assertTrue(report["schema_change_invalidated"])
            self.assertEqual(report["stale_direct_query_recommendation_rate"], 1)
            self.assertEqual(report["stale_guarded_recommendation_rate"], 0)
            self.assertEqual(report["queries"][3]["precision_at_1"], 1)
            self.assertTrue(report["concurrent_reads_stable"])
            self.assertTrue(report["malformed_duplicate_schema_rejected"])
            self.assertEqual(report["instruction_files_opened_by_query"], 0)
            self.assertEqual(report["queries"][1]["precision_at_1"], 1)
            self.assertTrue(all(row["negative_declined"] for row in report["queries"][4:]))
            self.assertTrue(all(row["actual_tool_invocation"] is None for row in report["queries"]))
            names = [item["name"] for row in report["queries"] for item in row["recommendations"]]
            self.assertNotIn("revoked-secret", names)
            self.assertNotIn("missing-browser", names)
            self.assertNotIn("forbidden-shell", names)

    def test_ranking_denominator_and_negative_decisions(self):
        result = experiment.ranking_metrics([{"name": "right", "provider": "p"}], {("p", "right")})
        self.assertEqual(result["precision_at_5"], .2)
        self.assertEqual(result["recall_at_5"], 1)
        self.assertFalse(experiment.ranking_metrics([{"name": "wrong"}], set())["negative_declined"])
        self.assertEqual(experiment.ranking_metrics([], {("p", "right")})["reciprocal_rank"], 0)

    def test_dependency_snapshots_have_correct_excerpts_and_staleness(self):
        reports = experiment.context_benchmark()
        self.assertEqual([row["files"] for row in reports], [30, 150, 1200])
        for row in reports:
            self.assertEqual(row["files"], row["dependency_edges"])
            self.assertTrue(all(row["static_activity_probes"].values()))
            self.assertTrue(row["packet_valid"])
            self.assertTrue(row["reference_runtime_correct"])
            self.assertTrue(row["dependency_excerpts_correct"])
            self.assertTrue(row["stale_evidence_rejected"])
            self.assertIn(row["rg_callsite_correct"], (True, None))
            self.assertIsNone(row["native_agent_files_opened"])

    def spans(self):
        return [{"id": "a", "worker": "worker1", "start_ms": 10, "end_ms": 50, "depends_on": [], "stage": "execution"},
                {"id": "b", "worker": "worker2", "start_ms": 10, "end_ms": 60, "depends_on": [], "stage": "execution"},
                {"id": "join", "worker": "parent", "start_ms": 60, "end_ms": 70, "depends_on": ["a", "b"], "stage": "integration"}]

    def test_parallel_wall_not_sum_and_no_unmeasured_claim(self):
        report = experiment.analyze_spans(self.spans(), 75)
        self.assertEqual(report["observed_wall_ms"], 75)
        self.assertEqual(report["dependency_critical_path_ms"], 60)
        self.assertEqual(report["sequential_execution_estimate_ms"], 90)
        self.assertEqual(report["estimated_benefit_ms"], 15)
        self.assertIsNone(report["observed_parallel_benefit_ms"])
        self.assertIsNone(report["measured_sequential_wall_ms"])

    def test_dependency_overlap_worker_conflict_cycles_limits_and_nan_rejected(self):
        variants = []
        rows = self.spans(); rows[2]["start_ms"] = 55; variants.append(rows)
        rows = self.spans(); rows[1]["worker"] = "worker1"; variants.append(rows)
        rows = self.spans(); rows[0]["depends_on"] = ["join"]; variants.append(rows)
        rows = self.spans(); rows[0]["depends_on"] = ["missing"]; variants.append(rows)
        rows = self.spans(); rows[0]["start_ms"] = float("nan"); variants.append(rows)
        rows = self.spans(); rows[1]["id"] = "a"; variants.append(rows)
        for rows in variants:
            with self.assertRaises(ValueError):
                experiment.analyze_spans(rows, 75)
        with self.assertRaises(ValueError):
            experiment.analyze_spans(self.spans(), 75, worker_limit=1)
        with self.assertRaises(ValueError):
            experiment.analyze_spans(self.spans(), float("inf"))

    def test_resource_bounds(self):
        for value in (0, 21, True):
            with self.assertRaises(ValueError):
                experiment.preparation_benchmark(value)
        with self.assertRaises(ValueError):
            experiment.context_benchmark((10000,))
        with self.assertRaises(ValueError):
            experiment.discovery_benchmark((10000,))


if __name__ == "__main__":
    unittest.main()
