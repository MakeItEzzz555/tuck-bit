import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("hook_advisor",ROOT/"scripts/hook_advisor.py")
hook=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hook)

class HookAdvisorTests(unittest.TestCase):
    def event(self,host,prompt):
        return {"hook_event_name":"UserPromptSubmit" if host=="claude" else "BeforeAgent",
                "session_id":"sensitive-private-id","prompt":prompt}

    def test_claude_hook_output_shape(self):
        out=hook.advise(self.event("claude","Fix a bug in the app"),"claude")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"],"UserPromptSubmit")
        self.assertIn("TuckBit advisory",out["hookSpecificOutput"]["additionalContext"])

    def test_gemini_hook_output_shape(self):
        out=hook.advise(self.event("gemini","Implement the feature"),"gemini")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"],"BeforeAgent")

    def test_unrelated_prompt_is_noop(self):
        for host in ("gemini","claude"):
            self.assertEqual(hook.advise(self.event(host,"Tell me a joke"),host),{})

    def test_no_generic_non_coding_reviews(self):
        for host in ("gemini", "claude"):
            self.assertEqual(hook.advise(self.event(host,"Review the film and rate it"),host),{})
            self.assertEqual(hook.advise(self.event(host,"Audit my vacation spending"),host),{})

    def test_explicit_opt_out(self):
        for host in ("gemini", "claude"):
            self.assertEqual(hook.advise(self.event(host,"Fix code without TuckBit"),host),{})

    def test_wrong_event_noop(self):
        self.assertEqual(hook.advise({"hook_event_name":"PreToolUse","prompt":"fix"},"claude"),{})

    def test_malformed_noop(self):
        self.assertEqual(hook.advise({"hook_event_name":"BeforeAgent","prompt":None},"gemini"),{})

    def test_does_not_echo_prompt_or_metadata(self):
        phrase="private-token-must-not-appear-ABC123"
        for host in ("claude","gemini"):
            event=self.event(host,"Debug "+phrase)
            result=json.dumps(hook.advise(event,host))
            self.assertNotIn(phrase,result)
            self.assertNotIn("sensitive-private-id",result)

    def test_high_risk_keeps_gates(self):
        result=hook.advise(self.event("claude","Fix a security flaw in authentication"),"claude")
        self.assertIn("security and rollback",result["hookSpecificOutput"]["additionalContext"])

    def test_parallel_only_suggests_independent_work(self):
        result=hook.advise(self.event("gemini","Run parallel coding agents"),"gemini")
        self.assertIn("Delegate only independent",result["hookSpecificOutput"]["additionalContext"])

    def test_small_fixed_context(self):
        for host in ("claude","gemini"):
            event=self.event(host,"Implement parallel authentication migration")
            message=hook.advise(event,host)["hookSpecificOutput"]["additionalContext"]
            self.assertLess(len(message),340)

    def test_cli_does_not_run_a_model(self):
        event=self.event("gemini","Review the code")
        p=subprocess.run([sys.executable,str(ROOT/"scripts/hook_advisor.py"),
                          "--host","gemini"],input=json.dumps(event),
                         capture_output=True,text=True,timeout=8)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(p.stderr,"")
        self.assertIn("additionalContext",json.loads(p.stdout)["hookSpecificOutput"])

    def test_nonmatching_cli_returns_empty_json(self):
        p=subprocess.run([sys.executable,str(ROOT/"scripts/hook_advisor.py"),
                          "--host","claude"],input='{"prompt":"hello"}',
                         capture_output=True,text=True,timeout=8)
        self.assertEqual(p.returncode,0)
        self.assertEqual(json.loads(p.stdout),{})

    def test_large_payload_is_skipped(self):
        p=subprocess.run([sys.executable,str(ROOT/"scripts/hook_advisor.py"),
                          "--host","claude"],input=json.dumps(self.event("claude","fix "+"z"*66000)),
                         capture_output=True,text=True,timeout=8)
        self.assertEqual(json.loads(p.stdout),{})

if __name__=="__main__":
    unittest.main()
