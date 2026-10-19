import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from provider_events import ProfileError, codex_trace, read_approved
from trace_profiler import profile


def export():
    return [{"type": "thread.started", "thread_id": "private-id"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "reasoning", "text": "secret"}},
            {"type": "item.completed", "item": {"id": "x", "type": "command_execution",
                                                "command": "private", "aggregated_output": "secret"}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 5,
                                                 "output_tokens": 3, "reasoning_output_tokens": 1}}]


class ProviderEventsTests(unittest.TestCase):
    def test_import_extracts_only_numeric_metadata(self):
        trace = codex_trace(export())
        self.assertEqual(profile(trace)["reported_uncached_input_tokens"], 5)
        self.assertEqual(trace["events"][0]["tool_invocations"], 1)
        self.assertFalse(trace["outcome"]["verified"])
        text = json.dumps(trace)
        for private in ("secret", "private", "command", "reasoning\"", "thread_id"):
            self.assertNotIn(private, text)

    def test_unknown_usage_is_unknown_not_zero(self):
        events = export()
        events[-1]["usage"] = None
        self.assertIsNone(profile(codex_trace(events))["reported_input_tokens"])

    def test_explicit_zero_and_missing_counter(self):
        events = export()
        events[-1]["usage"] = {"input_tokens": 0}
        report = profile(codex_trace(events))
        self.assertEqual(report["reported_input_tokens"], 0)
        self.assertIsNone(report["reported_cached_input_tokens"])

    def test_invalid_usage_rejected_without_echoing_payload(self):
        for value in (-1, True, "secret", 1.5):
            events = export()
            events[-1]["usage"]["input_tokens"] = value
            with self.assertRaises(ProfileError):
                codex_trace(events)

    def test_conflicting_accounting_rejected(self):
        events = export()
        events[-1]["usage"]["cached_input_tokens"] = 11
        with self.assertRaises(ProfileError):
            codex_trace(events)

    def test_duplicate_completion_and_bad_lifecycle_rejected(self):
        for events in ([export()[-1]], [export()[1], export()[1]],
                       export()[:-1] + [export()[3], export()[-1]]):
            with self.assertRaises(ProfileError):
                codex_trace(events)

    def test_failed_or_interrupted_turn_is_not_verified(self):
        for events in ([{"type": "turn.started"}, {"type": "turn.failed", "error": {"message": "secret"}}],
                       [{"type": "turn.started"}]):
            trace = codex_trace(events)
            self.assertFalse(trace["outcome"]["verified"])
            self.assertIsNone(profile(trace)["reported_input_tokens"])

    def test_read_requires_consent_and_refuses_symlink_and_malformed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in export()))
            with self.assertRaises(ProfileError):
                read_approved(path)
            self.assertEqual(len(read_approved(path, True)), 5)
            link = path.with_name("link")
            link.symlink_to(path)
            with self.assertRaises((OSError, ProfileError)):
                read_approved(link, True)
            path.write_text("{secret invalid}")
            with self.assertRaises(ProfileError) as error:
                read_approved(path, True)
            self.assertNotIn("secret", str(error.exception))

    def test_cli_unapproved_input_does_not_expose_path_or_payload(self):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] /
                                 "scripts/provider_events.py"), "--codex-jsonl", "/secret/file"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("/secret", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_incomplete_or_failed_export_cannot_certify_outcome(self):
        for events in ([], [{"type": "turn.started"}],
                       [{"type": "turn.started"}, {"type": "turn.failed"}],
                       export() + [{"type": "error", "message": "private"}]):
            for verified, accepted in ((True, True), (True, False), (False, True)):
                with self.assertRaises(ProfileError):
                    codex_trace(events, verified=verified, acceptance_checks_passed=accepted)
        partial = codex_trace([{"type": "turn.started"}])
        self.assertIsNone(profile(partial)["reported_metrics"]["tool_invocations"])
        self.assertTrue(codex_trace(export(), True, True)["outcome"]["verified"])
