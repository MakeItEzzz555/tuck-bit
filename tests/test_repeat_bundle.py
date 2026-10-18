import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import repeat_bundle as bench

class RepeatBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = bench.load_bundle(ROOT/"evals/bundles/offline-v1.json")

    def test_checked_in_bundle_valid(self):
        bench.validate_bundle(self.bundle)
        self.assertEqual(self.bundle["kind"],"offline_fixture_only")
        self.assertEqual(len(self.bundle["tasks"]),3)

    def test_run_repeats_each_task_and_condition_from_one_commit(self):
        fixture=copy.deepcopy(self.bundle)
        fixture["repetitions"]=2
        result=bench.execute(fixture)
        self.assertEqual(result["total_trials"],12)
        self.assertEqual(result["total_passes"],12)
        self.assertEqual(len({r["starting_commit"] for r in result["records"]}),1)
        self.assertEqual(result["starting_commit"],result["records"][0]["starting_commit"])
        for name, group in result["by_task"].items():
            self.assertEqual(group["baseline"]["trials"],2)
            self.assertEqual(group["tuckbit"]["trials"],2)
        self.assertFalse(result["claim_of_model_efficiency"])
        self.assertTrue(result["conditions_are_simulated"])
        self.assertIsNone(result["model"])

    def test_condition_order_counterbalanced(self):
        bundle=copy.deepcopy(self.bundle)
        bundle["tasks"]=bundle["tasks"][:1]
        bundle["repetitions"]=2
        result=bench.execute(bundle)
        self.assertEqual([r["treatment"] for r in result["records"]],
                         ["baseline","tuckbit","tuckbit","baseline"])

    def test_reproducible_start_commit_and_bundle_fingerprint(self):
        b=copy.deepcopy(self.bundle)
        b["tasks"]=b["tasks"][:1]
        b["repetitions"]=1
        first=bench.execute(b)
        second=bench.execute(b)
        self.assertEqual(first["starting_commit"],second["starting_commit"])
        self.assertEqual(first["fixture_tree_sha"],second["fixture_tree_sha"])
        self.assertEqual(first["bundle_sha256"],second["bundle_sha256"])

    def test_failed_acceptance_retained_for_both_conditions(self):
        b=copy.deepcopy(self.bundle)
        b["tasks"]=b["tasks"][:1]
        b["tasks"][0]["expected"]="wrong output\n"
        b["repetitions"]=2
        report=bench.execute(b)
        self.assertEqual(report["total_trials"],4)
        self.assertEqual(report["total_passes"],0)
        for trial in report["records"]:
            self.assertFalse(trial["passed"])
            self.assertFalse(trial["check_results"]["expected_output"])
        group=report["by_task"][b["tasks"][0]["id"]]
        self.assertEqual(group["baseline"]["passes"],0)
        self.assertEqual(group["tuckbit"]["passes"],0)
        self.assertEqual(group["baseline"]["failures"],2)
        self.assertEqual(group["tuckbit"]["pass_rate"],0.0)

    def test_budget_enforced_as_success_gate(self):
        b=copy.deepcopy(self.bundle)
        b["tasks"]=b["tasks"][:1]
        b["budget"]["max_operations"]=3
        result=bench.execute(b)
        self.assertTrue(all(r["check_results"]["within_operation_budget"] for r in result["records"]))
        self.assertTrue(all("within_wall_budget" in r["check_results"] for r in result["records"]))

    def test_banned_command_fields_rejected(self):
        b=copy.deepcopy(self.bundle)
        b["tasks"][0]["command"]="curl private.example"
        with self.assertRaises(bench.BundleError):
            bench.validate_bundle(b)

    def test_unrecognized_adapter_rejected(self):
        b=copy.deepcopy(self.bundle)
        b["tasks"][0]["adapter"]="shell"
        with self.assertRaises(bench.BundleError):
            bench.validate_bundle(b)

    def test_duplicate_task_names_rejected(self):
        b=copy.deepcopy(self.bundle)
        b["tasks"].append(copy.deepcopy(b["tasks"][0]))
        with self.assertRaises(bench.BundleError):
            bench.validate_bundle(b)

    def test_rejects_invalid_checks(self):
        b=copy.deepcopy(self.bundle)
        b["mandatory_checks"]=["expected_output"]
        with self.assertRaises(bench.BundleError):
            bench.validate_bundle(b)

    def test_rejects_invalid_budget_types(self):
        for bad in (True, -1, "7"):
            b=copy.deepcopy(self.bundle)
            b["budget"]["max_operations"]=bad
            with self.assertRaises(bench.BundleError):
                bench.validate_bundle(b)

    def test_rejects_unsafe_task_id(self):
        b=copy.deepcopy(self.bundle)
        b["tasks"][0]["id"]="../escape"
        with self.assertRaises(bench.BundleError):
            bench.validate_bundle(b)

    def test_rejects_json_manifest_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"bundle.json"
            path.symlink_to(ROOT/"evals/bundles/offline-v1.json")
            with self.assertRaises(bench.BundleError):
                bench.load_bundle(path)

    def test_cli_does_not_replace_reports(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"report.json"
            out.write_text("valuable")
            p=subprocess.run([sys.executable,str(ROOT/"scripts/repeat_bundle.py"),
                              "--bundle",str(ROOT/"evals/bundles/offline-v1.json"),
                              "--output",str(out)],capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,2,p.stderr)
            self.assertEqual(out.read_text(),"valuable")

    def test_result_does_not_claim_model_metrics(self):
        b=copy.deepcopy(self.bundle)
        b["tasks"]=b["tasks"][:1]
        b["repetitions"]=1
        result=bench.execute(b)
        for row in result["records"]:
            self.assertIsNone(row["reported_tokens"])
            self.assertIsNone(row["human_editing_ms"])
            self.assertIsNone(row["human_review_ms"])
            self.assertEqual(row["re_runs"],0)
            self.assertTrue(row["starting_commit"])
        self.assertIn("no AI coding agents", result["limitations"][0])

if __name__=="__main__":
    unittest.main()
