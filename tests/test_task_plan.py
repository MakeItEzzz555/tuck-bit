import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("taskplan", ROOT / "scripts/plan_task.py")
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)

class PlanTests(unittest.TestCase):
    def test_preserves_request_and_all_constraints(self):
        task = {"request": "Fix the bug; do not merge.",
                "constraints": ["Keep PR open", "Don't skip security checks"]}
        result = planner.compile_plan(task)
        self.assertEqual(result["request"], task["request"])
        self.assertEqual(result["constraints_verbatim"], task["constraints"])
        self.assertFalse(result["private_reasoning_observable"])
    def test_tools_not_invented(self):
        result = planner.compile_plan({"request": "Search for tests",
            "tools": ["git", "rg"], "needed_tools": ["rg", "network"]})
        self.assertEqual(result["capabilities"]["requested_known"], ["rg"])
        self.assertEqual(result["capabilities"]["requested_unavailable"], ["network"])
        self.assertFalse(result["capabilities"]["execution_performed"])
    def test_unknown_host_rejected(self):
        with self.assertRaises(ValueError):
            planner.compile_plan({"request": "Hi", "host": "fake"})
    def test_parallel_is_only_candidate(self):
        result = planner.compile_plan({"request": "Fix A and B", "parallel": True})
        self.assertEqual(result["execution"]["mode"], "parallel_candidate")
    def test_continuous_explicit_candidate(self):
        result = planner.compile_plan({"request": "Daily audit", "continuous": True})
        self.assertEqual(result["execution"]["mode"], "recurring_candidate")
    def test_default_single(self):
        result = planner.compile_plan({"request": "Fix small bug"})
        self.assertEqual(result["execution"]["mode"], "single")
    def test_host_profiles_distinct(self):
        a = planner.compile_plan({"request": "Task", "host": "codex"})
        b = planner.compile_plan({"request": "Task", "host": "claude"})
        self.assertNotEqual(a["host_execution_profile"], b["host_execution_profile"])
    def test_no_runtime_permissions_or_hidden_reasoning_claim(self):
        result = planner.compile_plan({"request": "Implement feature", "host": "claude"})
        self.assertFalse(result["private_reasoning_observable"])
        self.assertTrue(result["execution"]["native_permissions_required"])
        self.assertEqual(result["capabilities"]["declared_available"], [])

    def test_all_known_hosts_compile(self):
        hosts = json.loads((ROOT / "skills/tuck-bit/assets/hosts.json").read_text())["hosts"]
        for host in hosts:
            output = planner.compile_plan({"request": "Inspect task", "host": host})
            self.assertEqual(output["host"], host)

    def test_no_unknown_keys(self):
        with self.assertRaises(ValueError):
            planner.compile_plan({"request": "Task", "hidden_prompt": "secret"})
    def test_no_malformed_lists(self):
        with self.assertRaises(ValueError):
            planner.compile_plan({"request": "Task", "constraints": "none"})
    def test_no_empty_request(self):
        with self.assertRaises(ValueError):
            planner.compile_plan({"request": "   "})
    def test_high_risk_respects_checks(self):
        result = planner.compile_plan({"request": "Auth migration", "risk": "high",
            "checks": ["Security review", "Migration rollback test"]})
        self.assertEqual(result["required_checks_verbatim"],
            ["Security review", "Migration rollback test"])
        self.assertEqual(result["execution"]["risk"], "high")
    def test_cli_no_model(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "task.json"
            path.write_text(json.dumps({"request": "Audit interfaces",
                                        "host": "gemini", "constraints": ["No push"]}))
            result = subprocess.run([sys.executable, str(ROOT/"scripts/plan_task.py"),
                                     str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["constraints_verbatim"], ["No push"])
            self.assertEqual(report["host"], "gemini")
    def test_missing_input_returns_nonzero(self):
        result = subprocess.run([sys.executable, str(ROOT/"scripts/plan_task.py"),
                                 "/nonexistent/tuck-bit/task.json"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

if __name__ == "__main__":
    unittest.main()
