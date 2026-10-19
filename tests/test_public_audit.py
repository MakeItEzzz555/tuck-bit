import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout
import io
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("public_audit", ROOT / "scripts/public_audit.py")
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)

class PublicAuditTests(unittest.TestCase):
    def test_detects_private_key(self):
        start = "-----BEGIN " + "PRIVATE KEY-----"
        self.assertIn("private_key_block", audit_module.scan_text(start))

    def test_detects_token_prefix(self):
        fake = ("gh" + "p_") + ("a" * 35)
        self.assertIn("recognizable_token_prefix", audit_module.scan_text(fake))

    def test_detects_posix_personal_home(self):
        path = "/" + "Users" + "/privateperson/Documents/"
        self.assertIn("personal_home_path", audit_module.scan_text(path))

    def test_detects_windows_personal_home(self):
        path = "C:" + chr(92) + "Users" + chr(92) + "privateperson" + chr(92) + "Documents"
        self.assertIn("personal_home_path", audit_module.scan_text(path))

    def test_safe_documentation(self):
        self.assertEqual(audit_module.scan_text("public repo https://github.com/example/name"), [])
        self.assertEqual(audit_module.scan_text("fake@example.com and sk-REDACTED"), [])

    def test_sensitive_file_name_denied(self):
        self.assertIn("high_risk_filename", audit_module.check_path(".env"))
        self.assertIn("high_risk_filename", audit_module.check_path("build/archive.p12"))
        self.assertIn("high_risk_filename", audit_module.check_path("trace.jsonl"))

    def test_internal_folder_denied(self):
        self.assertIn("private_workspace_path", audit_module.check_path("private/notes.md"))
        self.assertEqual(audit_module.check_path("docs/ROADMAP.md"), [])

    def test_risky_filenames_and_case_insensitive_extensions(self):
        for name in ("config/credentials.json", "keys/id_ed25519", "cert.PEM", "logs/session.HAR"):
            with self.subTest(name=name):
                self.assertEqual(audit_module.check_path(name), ["high_risk_filename"])

    def test_only_the_exact_synthetic_fixture_path_is_exempt(self):
        self.assertEqual(audit_module.check_path("tests/dashboard/fixtures/codex-rollout.jsonl"), [])
        for rel in ("codex-rollout.jsonl", "tests/codex-rollout.jsonl", "tests/dashboard/fixtures/real.jsonl",
                    "tests/dashboard/fixtures/codex-rollout.JSONL", "x/tests/dashboard/fixtures/codex-rollout.jsonl"):
            self.assertEqual(audit_module.check_path(rel), ["high_risk_filename"], rel)

    def test_benign_filename_lookalikes_are_not_flagged(self):
        for name in (".env.example", "docs/private.md", "docs/sessions-guide.md", "public/key.txt"):
            with self.subTest(name=name):
                self.assertEqual(audit_module.check_path(name), [])

    def test_relative_paths_and_redacted_placeholders_are_safe(self):
        for text in ("docs/guide.md", "<HOME>/Documents/",
                     "C:" + chr(92) + "Users" + chr(92) + "<user>" + chr(92),
                     "github_pat_REDACTED", "sk-REDACTED"):
            with self.subTest(text=text):
                self.assertEqual(audit_module.scan_text(text), [])

    def test_home_like_substring_in_relative_example_is_flagged(self):
        text = "./" + "Users/example/notes.md"
        self.assertEqual(audit_module.scan_text(text), ["personal_home_path"])

    def test_invalid_text_and_filename_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            audit_module.scan_text(b"not decoded")
        self.assertEqual(audit_module.check_path(None), ["invalid_filename"])

    def test_main_fails_closed_without_echoing_read_errors(self):
        for error in (OSError("private diagnostic"), subprocess.CalledProcessError(1, "git")):
            with self.subTest(error=type(error).__name__):
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(audit_module, "audit", side_effect=error):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        self.assertEqual(audit_module.main(), 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn(type(error).__name__, stderr.getvalue())
                self.assertNotIn("private diagnostic", stderr.getvalue())

    def test_main_returns_failure_for_findings_and_success_for_clean_files(self):
        for findings, expected in (([(".env", "high_risk_filename")], 1), ([], 0)):
            with self.subTest(findings=findings):
                with patch.object(audit_module, "audit", return_value=(1, 0, findings)):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(audit_module.main(), expected)

    def test_audit_reports_oversized_files_without_reading_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "large.txt").write_text("synthetic", encoding="utf-8")
            with patch.object(audit_module, "tracked_and_new_files", return_value=["large.txt"]):
                with patch.object(audit_module, "MAX_TEXT_BYTES", 1):
                    self.assertEqual(audit_module.audit(root),
                                     (0, 0, [("large.txt", "oversized_unreviewed_file")]))

    def test_no_secrets_echoed(self):
        fake = ("github_" + "pat_" + "a" * 60)
        result = audit_module.scan_text(fake)
        self.assertNotIn(fake, str(result))
        self.assertIn("recognizable_token_prefix", result)

if __name__ == "__main__":
    unittest.main()
