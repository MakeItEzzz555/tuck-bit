import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("trace_profiler", ROOT/"scripts/trace_profiler.py")
prof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prof)

def sample():
    op="a"*64
    output="b"*64
    revision="c"*64
    return {"schema":1, "outcome":{"verified":True, "acceptance_checks_passed":True},
            "events":[
                {"category":"tool_read","role":"root","input_tokens":100,
                 "cached_input_tokens":75,"output_tokens":10,"result_bytes":16000,
                 "duration_ms":40,"operation_sha256":op,
                 "result_sha256":output,"revision_sha256":revision},
                {"category":"tool_read","role":"worker","input_tokens":100,
                 "cached_input_tokens":80,"output_tokens":20,"result_bytes":17000,
                 "duration_ms":50,"operation_sha256":op,
                 "result_sha256":output,"revision_sha256":revision},
                {"category":"test","role":"root","input_tokens":100,
                 "cached_input_tokens":0,"output_tokens":30,
                 "reasoning_output_tokens":5,"result_bytes":500,"duration_ms":100}]}

class ProfileTests(unittest.TestCase):
    def test_totals_and_repeated_call_counts(self):
        report=prof.profile(sample())
        self.assertEqual(report["event_count"],3)
        self.assertEqual(report["reported_input_tokens"],300)
        self.assertEqual(report["reported_uncached_input_tokens"],145)
        self.assertEqual(report["potential_identical_repeats"],1)
        self.assertEqual(report["large_results_16k_or_more"],1)
        self.assertEqual(report["sum_event_durations_ms"],190)

    def test_repeated_calls_require_same_revision_and_result(self):
        trace=sample()
        trace["events"][1]["revision_sha256"]="d"*64
        self.assertEqual(prof.profile(trace)["potential_identical_repeats"],0)
        trace["events"][1]["revision_sha256"]="c"*64
        trace["events"][1]["result_sha256"]="e"*64
        self.assertEqual(prof.profile(trace)["potential_identical_repeats"],0)

    def test_unverified_outcome_blocks_comparability(self):
        baseline=sample()
        candidate=sample()
        candidate["outcome"]["verified"]=False
        report=prof.compare(baseline,candidate)
        self.assertFalse(report["both_verified"])
        self.assertFalse(report["claim_of_savings"])

    def test_both_verified_remain_descriptive_only(self):
        report=prof.compare(sample(),sample())
        self.assertTrue(report["both_verified"])
        self.assertFalse(report["claim_of_savings"])

    def test_raw_logs_or_sensitive_keys_rejected(self):
        t=sample()
        t["events"][0]["prompt"]="Top secret"
        with self.assertRaises(prof.ProfileError):
            prof.profile(t)

    def test_unrecognized_top_level_rejected(self):
        t=sample()
        t["internal_notes"]="Something private"
        with self.assertRaises(prof.ProfileError):
            prof.profile(t)

    def test_negative_and_noninteger_counts_rejected(self):
        for value in (-1,1.5,True):
            t=sample()
            t["events"][0]["input_tokens"]=value
            with self.assertRaises(prof.ProfileError):
                prof.profile(t)

    def test_cached_greater_than_input_rejected(self):
        t=sample()
        t["events"][0]["cached_input_tokens"]=101
        with self.assertRaises(prof.ProfileError):
            prof.profile(t)

    def test_invalid_hex_digest_rejected(self):
        t=sample()
        t["events"][0]["revision_sha256"]="repo-key-plaintext"
        with self.assertRaises(prof.ProfileError):
            prof.profile(t)

    def test_invalid_category_or_role_rejected(self):
        for category,role in (("shell_command","root"),("tool_read","alice@example.com")):
            t=sample()
            t["events"][0]["category"]=category
            t["events"][0]["role"]=role
            with self.assertRaises(prof.ProfileError):
                prof.profile(t)

    def test_empty_trace_is_allowed(self):
        t={"schema":1,"events":[],"outcome":{"verified":False,"acceptance_checks_passed":False}}
        self.assertEqual(prof.profile(t)["event_count"],0)

    def test_output_omits_raw_identifiers(self):
        report=prof.profile(sample())
        content=json.dumps(report)
        self.assertNotIn("a"*64,content)
        self.assertNotIn("b"*64,content)
        self.assertNotIn("c"*64,content)

    def test_max_event_count_is_bounded(self):
        t=sample()
        t["events"]=[{"category":"other","role":"root"}]*(prof.MAX_EVENTS+1)
        with self.assertRaises(prof.ProfileError):
            prof.profile(t)

    def test_cli_reads_explicit_json_and_aggregates(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"trace.json"
            path.write_text(json.dumps(sample()))
            command=[sys.executable,str(ROOT/"scripts/trace_profiler.py")]
            result=subprocess.run(command+["profile","--trace",str(path)],
                                  capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(result.stdout)
            self.assertEqual(report["event_count"],3)
            self.assertEqual(sorted(Path(d).iterdir()),[path])

    def test_cli_compare(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"trace.json"
            path.write_text(json.dumps(sample()))
            command=[sys.executable,str(ROOT/"scripts/trace_profiler.py")]
            result=subprocess.run(command+["compare","--baseline",str(path),
                                           "--candidate",str(path)],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(json.loads(result.stdout)["claim_of_savings"])

if __name__=="__main__":
    unittest.main()


class AvailabilityTests(unittest.TestCase):
    def trace(self, events):
        return {"schema": 1, "events": [{"category": "build", "role": "root", **e} for e in events],
                "outcome": {"verified": True, "acceptance_checks_passed": True}}

    def test_omitted_and_null_metrics_remain_unknown(self):
        for event in ({"duration_ms": 100}, {"input_tokens": None}):
            report = prof.profile(self.trace([event]))
            self.assertIsNone(report["reported_input_tokens"])
            self.assertIsNone(report["reported_output_tokens"])
            self.assertEqual(report["metric_availability"]["input_tokens"]["status"], "unknown")

    def test_measured_zero_is_complete(self):
        report = prof.profile(self.trace([{"input_tokens": 0, "cached_input_tokens": 0}]))
        self.assertEqual(report["reported_input_tokens"], 0)
        self.assertEqual(report["reported_uncached_input_tokens"], 0)
        self.assertEqual(report["metric_availability"]["input_tokens"]["status"], "complete")

    def test_partial_subtotal_does_not_masquerade_as_total(self):
        trace = self.trace([{"input_tokens": 100}, {"duration_ms": 5}])
        report = prof.profile(trace)
        self.assertIsNone(report["reported_input_tokens"])
        self.assertEqual(report["observed_subtotals"]["input_tokens"], 100)
        self.assertEqual(report["metric_availability"]["input_tokens"]["status"], "partial")
        self.assertIsNone(prof.compare(trace, trace)["descriptive_differences"]["reported_input_tokens"]
                          ["delta_candidate_minus_baseline"])

    def test_partial_pair_is_accepted_but_derived_value_is_unknown(self):
        report = prof.profile(self.trace([{"cached_input_tokens": 20}]))
        self.assertEqual(report["reported_cached_input_tokens"], 20)
        self.assertIsNone(report["reported_uncached_input_tokens"])

    def test_conflicting_provider_definition_is_rejected(self):
        trace = self.trace([{}])
        trace["accounting"] = {"cached_input": "additional_to_input", "reasoning_output": "included_in_output"}
        with self.assertRaises(prof.ProfileError):
            prof.profile(trace)

    def test_accounting_and_wall_time_are_explicit(self):
        trace = self.trace([{"duration_ms": 80}, {"duration_ms": 80}])
        trace["wall_time_ms"] = 90
        trace["accounting"] = {"cached_input": "included_in_input", "reasoning_output": "included_in_output"}
        report = prof.profile(trace)
        self.assertEqual(report["wall_time_ms"], 90)
        self.assertEqual(report["sum_event_durations_ms"], 160)

    def test_invalid_null_adjacent_values_and_wall_time_rejected(self):
        for key, value in (("wall_time_ms", True), ("wall_time_ms", -1), ("schema", True)):
            trace = self.trace([{}])
            trace[key] = value
            with self.assertRaises(prof.ProfileError):
                prof.profile(trace)

    def test_file_reader_refuses_symlink_and_limits_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text(json.dumps(self.trace([{}])))
            link = path.with_name("link")
            link.symlink_to(path)
            with self.assertRaises((prof.ProfileError, OSError)):
                prof.load(link)
            path.write_bytes(b" " * (prof.MAX_BYTES + 1))
            with self.assertRaises(prof.ProfileError):
                prof.load(path)

    def test_file_reader_refuses_fifo_without_blocking(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fifo"
            os.mkfifo(path)
            with self.assertRaises(prof.ProfileError):
                prof.load(path)

    def test_context_rereads_separate_unchanged_changed_and_post_mutation(self):
        a, b, x, y = "a"*64, "b"*64, "1"*64, "2"*64
        read = lambda source, result: {"category": "tool_read", "role": "root",
                                       "target_sha256": source, "result_sha256": result}
        trace = {"schema": 1, "outcome": {"verified": True, "acceptance_checks_passed": True}, "events": [
            read(a, x), {**read(a, x), "role": "worker"}, read(a, y),
            {"category": "tool_write", "role": "root", "target_sha256": a},
            read(a, y), read(b, x), {"category": "test", "role": "root", "target_sha256": b}, read(b, x)]}
        rereads = prof.profile(trace)["context_rereads"]
        self.assertEqual(rereads, {"coverage": "complete", "tracked_reads": 6, "untracked_reads": 0,
                                   "first_reads": 2, "unchanged_content": 2, "changed_content": 1,
                                   "after_mutation": 1})
        self.assertNotIn(a, json.dumps(prof.profile(trace)))

    def test_unscoped_write_counts_next_reread_as_post_mutation(self):
        read = {"category": "tool_read", "role": "root", "target_sha256": "a"*64, "result_sha256": "1"*64}
        trace = self.trace([])
        trace["events"] = [read, {"category": "tool_write", "role": "worker"}, read]
        rereads = prof.profile(trace)["context_rereads"]
        self.assertEqual((rereads["after_mutation"], rereads["unchanged_content"]), (1, 0))

    def test_reread_coverage_is_explicit_and_partial_deltas_are_unknown(self):
        tracked = {"category": "tool_read", "role": "root", "target_sha256": "a"*64, "result_sha256": "1"*64}
        partial = self.trace([])
        partial["events"] = [tracked, tracked, {"category": "tool_read", "role": "root", "target_sha256": "a"*64}]
        self.assertEqual(prof.profile(partial)["context_rereads"]["coverage"], "partial")
        self.assertEqual(prof.profile(partial)["context_rereads"]["untracked_reads"], 1)
        self.assertEqual(prof.profile(self.trace([{}]))["context_rereads"]["coverage"], "unknown")
        complete = self.trace([])
        complete["events"] = [tracked, tracked]
        differences = prof.compare(complete, partial)["descriptive_differences"]
        self.assertIsNone(differences["context_rereads_unchanged_content"]["delta_candidate_minus_baseline"])
        differences = prof.compare(complete, complete)["descriptive_differences"]
        self.assertEqual(differences["context_rereads_unchanged_content"]["delta_candidate_minus_baseline"], 0)

    def test_malformed_source_digest_rejected(self):
        with self.assertRaises(prof.ProfileError):
            prof.profile(self.trace([{"target_sha256": "src/app.py:10-20"}]))

    def test_identical_repeats_are_split_by_category(self):
        report = prof.profile(sample())
        self.assertEqual(report["identical_repeats_by_category"], {"tool_read": 1})

    def test_invocations_retries_and_overhead_use_complete_only_deltas(self):
        before = self.trace([{"tool_invocations": 3, "retries": 1, "delegation_overhead_ms": 5}])
        after = self.trace([{"tool_invocations": 2, "retries": 0}])
        differences = prof.compare(before, after)["descriptive_differences"]
        self.assertEqual(differences["metric_retries"]["delta_candidate_minus_baseline"], -1)
        self.assertEqual(differences["metric_tool_invocations"]["delta_candidate_minus_baseline"], -1)
        self.assertIsNone(differences["metric_delegation_overhead_ms"]["delta_candidate_minus_baseline"])
