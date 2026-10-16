import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workflow_router import route

class WorkflowRouterTests(unittest.TestCase):
    def task(self, **kwargs):
        return {"request": "Fix the bug without merging unrelated branches",
                "constraints": ["Leave main unchanged", "Preserve all required tests"],
                "checks": ["Run the targeted regression"], **kwargs}

    def test_fast_is_lightweight(self):
        r = route(self.task(complexity="fast"))
        self.assertEqual(r["routing"]["depth"], "fast")
        self.assertEqual(r["routing"]["workflow"], "single")

    def test_standard_is_default(self):
        self.assertEqual(route(self.task())["routing"]["depth"], "standard")

    def test_high_risk_cannot_downgrade(self):
        result = route(self.task(complexity="fast", risk="high"))
        self.assertEqual(result["routing"]["depth"], "deep")
        self.assertIn("Review required security and rollback implications", result["routing"]["checks"])

    def test_failed_checks_escalate(self):
        r = route(self.task(signals={"failed_checks": 2}))
        self.assertEqual(r["routing"]["depth"], "deep")

    def test_one_failed_check_does_not_escalate(self):
        self.assertEqual(route(self.task(signals={"failed_checks": 1}))["routing"]["depth"], "standard")

    def test_fast_expands_for_dependencies(self):
        self.assertEqual(route(self.task(complexity="fast",
            signals={"unresolved_dependencies": 2}))["routing"]["depth"], "standard")

    def test_observations_warn_on_repetition(self):
        r = route(self.task(signals={"unchanged_retries": 3,
            "duplicate_tool_calls": 3, "large_tool_outputs": 1}))
        notices = " ".join(r["routing"]["notices"])
        self.assertIn("Stop repeating", notices)
        self.assertIn("repeated tool calls", notices)
        self.assertIn("oversized", notices)

    def test_parallel_requires_opt_in(self):
        r = route(self.task(parallel=True, workstreams=[
            {"goal": "Tests", "owned_files": ["tests/a.py"]},
            {"goal": "Implementation", "owned_files": ["src/a.py"]}]))
        self.assertEqual(r["routing"]["workflow"], "single")
        self.assertTrue(r["routing"]["notices"])

    def test_parallel_nonoverlap_opt_in(self):
        r = route(self.task(parallel=True, enable_orchestration=True, workstreams=[
            {"goal": "Tests", "owned_files": ["tests/a.py"]},
            {"goal": "Implementation", "owned_files": ["src/a.py"]}]))
        self.assertEqual(r["routing"]["workflow"], "parallel_candidate")

    def test_parallel_overlap_is_blocked(self):
        r = route(self.task(parallel=True, enable_orchestration=True, workstreams=[
            {"goal": "Tests", "owned_files": ["src/a.py"]},
            {"goal": "Implementation", "owned_files": ["src/a.py"]}]))
        self.assertEqual(r["routing"]["workflow"], "single")
        self.assertIn("Overlapping", " ".join(r["routing"]["notices"]))

    def test_parallel_file_conflicts_defer(self):
        r = route(self.task(parallel=True, enable_orchestration=True,
            signals={"file_conflicts": 1}, workstreams=[
                {"goal": "Tests", "owned_files": ["tests/a.py"]},
                {"goal": "Implementation", "owned_files": ["src/a.py"]}]))
        self.assertEqual(r["routing"]["workflow"], "single")

    def test_continuous_requires_trigger_and_checkpoint(self):
        r = route(self.task(continuous=True, enable_orchestration=True))
        self.assertEqual(r["routing"]["workflow"], "single")
        self.assertIn("deferred", " ".join(r["routing"]["notices"]))

    def test_continuous_candidate_with_opt_in(self):
        r = route(self.task(continuous=True, enable_orchestration=True,
            event_trigger="GitHub release event", checkpoint_reference="state/last.json"))
        self.assertEqual(r["routing"]["workflow"], "event_driven_candidate")
        self.assertEqual(r["routing"]["model_calls_made"], 0)

    def test_review_only_cannot_be_overridden_by_parallel(self):
        r = route(self.task(review_only=True, parallel=True,
            enable_orchestration=True, workstreams=[
                {"goal": "Review A", "owned_files": ["src/a.py"]},
                {"goal": "Review B", "owned_files": ["src/b.py"]}]))
        self.assertEqual(r["routing"]["workflow"], "review")

    def test_original_task_and_checks_retained(self):
        task = self.task(host="claude")
        r = route(task)
        self.assertEqual(r["task"]["request"], task["request"])
        self.assertEqual(r["task"]["constraints_verbatim"], task["constraints"])
        self.assertTrue(set(task["checks"]).issubset(set(r["routing"]["checks"])))

    def test_all_host_profiles_have_sources_and_strategies(self):
        profiles=json.loads((ROOT/"skills/tuck-bit/assets/workflows.json").read_text())["hosts"]
        for host in profiles:
            r=route(self.task(host=host))
            self.assertTrue(r["routing"]["host_source"].startswith("https://"))
            self.assertTrue(r["routing"]["host_strategy"])
            self.assertFalse(r["task"]["private_reasoning_observable"])

    def test_unrecognized_field_rejected(self):
        with self.assertRaises(ValueError):
            route(self.task(hidden_reasoning="please read it"))

    def test_malformed_ownership_rejected(self):
        with self.assertRaises(ValueError):
            route(self.task(workstreams=[{"goal": "Fix", "owned_files": ["../private"]}]))

    def test_windows_style_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            route(self.task(workstreams=[{"goal": "Sensitive", "owned_files": ["..\\secrets.txt"]}]))
        with self.assertRaises(ValueError):
            route(self.task(workstreams=[{"goal": "Drive", "owned_files": ["C:\\secret.txt"]}]))

    def test_negative_signal_and_boolean_rejected(self):
        for sig in ({"failed_checks": -1}, {"failed_checks": True}, {"private_thoughts": 4}):
            with self.assertRaises(ValueError):
                route(self.task(signals=sig))

    def test_no_orchestration_implicit(self):
        r=route(self.task(request="Parallel tasks please", parallel=False))
        self.assertEqual(r["routing"]["workflow"],"single")

    def test_router_uses_explicit_registry_metadata_without_tool_execution(self):
        from capability_registry import build
        catalog = build([ROOT/"skills"], ROOT/"examples/tool-metadata.synthetic.json")
        task = self.task(request="Search repository source for regression tests", host="codex")
        output = route(task, catalog)
        choices = output["routing"]["suggested_capabilities"]
        self.assertTrue(choices)
        self.assertEqual(choices[0]["trust"], "untrusted_metadata")
        self.assertTrue(all(c["requires_host_authorization"] for c in choices))
        self.assertEqual(output["routing"]["tool_calls_made"], 0)
        self.assertNotIn("description", choices[0])

    def test_explicit_trace_prompts_reflection_not_unproved_savings(self):
        from trace_profiler import load, profile
        events=profile(load(ROOT/"examples/trace-baseline.synthetic.json"))
        routed=route(self.task(), trace_summary=events)
        self.assertEqual(routed["routing"]["observations"]["large_tool_outputs"], 2)
        self.assertEqual(routed["routing"]["observations"]["duplicate_tool_calls"], 1)
        self.assertIn("oversized", " ".join(routed["routing"]["notices"]))
        self.assertEqual(routed["routing"]["tool_calls_made"], 0)

    def test_invalid_trace_summary_fails_closed(self):
        with self.assertRaises(ValueError):
            route(self.task(), trace_summary={"metrics_source":"unknown"})

    def test_cli_explicit_trace_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            task=Path(folder)/"task.json"
            task.write_text(json.dumps(self.task()))
            res=subprocess.run([sys.executable,str(ROOT/"scripts/workflow_router.py"),str(task),
                "--trace",str(ROOT/"examples/trace-baseline.synthetic.json")],
                capture_output=True,text=True)
            self.assertEqual(res.returncode,0,res.stderr)
            report=json.loads(res.stdout)
            self.assertEqual(report["routing"]["observations"]["large_tool_outputs"],2)

    def test_registry_is_opt_in(self):
        self.assertEqual(route(self.task())["routing"]["suggested_capabilities"], [])

    def test_cli_reads_explicit_registry_snapshot(self):
        from capability_registry import build
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            task = folder/"task.json"
            snapshot = folder/"snapshot.json"
            task.write_text(json.dumps(self.task(request="Search repository source for regression tests")))
            snapshot.write_text(json.dumps(build([ROOT/"skills"], ROOT/"examples/tool-metadata.synthetic.json")))
            p = subprocess.run([sys.executable, str(ROOT/"scripts/workflow_router.py"),str(task),
                                "--registry-snapshot",str(snapshot)],capture_output=True,text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue(json.loads(p.stdout)["routing"]["suggested_capabilities"])

    def test_cli_outputs_parseable_json_without_side_effects(self):
        with tempfile.TemporaryDirectory() as d:
            task=Path(d)/"task.json"
            task.write_text(json.dumps(self.task(host="gemini", complexity="fast")))
            result=subprocess.run([sys.executable,str(ROOT/"scripts/workflow_router.py"),str(task)],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)["routing"]["depth"],"fast")
            self.assertEqual(sorted(Path(d).iterdir()), [task])

    def test_cli_does_not_overwrite_output(self):
        with tempfile.TemporaryDirectory() as d:
            task=Path(d)/"task.json"
            out=Path(d)/"result.json"
            task.write_text(json.dumps(self.task()))
            out.write_text("original")
            result=subprocess.run([sys.executable,str(ROOT/"scripts/workflow_router.py"),
                str(task),"--output",str(out)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(out.read_text(),"original")

if __name__ == "__main__":
    unittest.main()
