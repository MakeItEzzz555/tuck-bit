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
