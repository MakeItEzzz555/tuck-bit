import importlib.util
from pathlib import Path
import tempfile
import unittest

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

    def test_no_secrets_echoed(self):
        fake = ("github_" + "pat_" + "a" * 60)
        result = audit_module.scan_text(fake)
        self.assertNotIn(fake, str(result))
        self.assertIn("recognizable_token_prefix", result)

if __name__ == "__main__":
    unittest.main()
