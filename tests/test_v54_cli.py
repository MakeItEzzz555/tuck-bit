import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v54_tuckbit", ROOT/"scripts/tuckbit.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
spec = importlib.util.spec_from_file_location("v54_installer", ROOT/"scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class V54CLITests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT/"scripts/tuckbit.py"), *map(str, args)],
                              capture_output=True, text=True, timeout=10)

    def test_doctor_uses_selected_catalog_and_keeps_list_api(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(ROOT/"skills", root/"skills")
            shutil.copytree(ROOT/".claude-plugin", root/".claude-plugin")
            shutil.copyfile(ROOT/"README.md", root/"README.md")
            catalog = root/"skills/tuck-bit/assets/modules.json"
            catalog.write_text(json.dumps({"modules": {"local_only": True}}))
            self.assertEqual(app.doctor(root), ["Missing playbook: local_only"])
            catalog.unlink()
            self.assertIn("missing_catalog", {r["code"] for r in app.doctor_status(root)["issues"]})
            self.assertEqual(app.doctor(), [])

    def test_missing_installation_json_is_actionable_without_paths(self):
        with tempfile.TemporaryDirectory(prefix="PRIVATE_SENTINEL_") as folder:
            result = self.cli("doctor", "--root", folder, "--json")
            self.assertEqual(result.returncode, 1, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "fail")
            self.assertTrue(all(row["hint"] for row in payload["issues"]))
            self.assertIn("--root", payload["issues"][0]["hint"])
            self.assertIn("activation are unverified", payload["scope"])
            self.assertNotIn("PRIVATE_SENTINEL", result.stdout+result.stderr)

    def test_corrupt_metadata_is_sanitized_and_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(ROOT/"skills", root/"skills")
            (root/".claude-plugin").mkdir()
            (root/"README.md").write_text("local")
            bad = root/".claude-plugin/plugin.json"
            catalog = root/"skills/tuck-bit/assets/modules.json"
            for file in (bad, catalog):
                file.write_bytes(b'PRIVATE_CREDENTIAL_SENTINEL\xff')
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            result = self.cli("doctor", "--root", root, "--json")
            self.assertEqual(result.returncode, 1)
            self.assertEqual({r["code"] for r in json.loads(result.stdout)["issues"]},
                             {"invalid_plugin", "invalid_catalog"})
            self.assertNotIn("PRIVATE_CREDENTIAL_SENTINEL", result.stdout+result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_all_six_host_skill_layouts_do_not_require_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            for host, relative in installer.PROJECT.items():
                with self.subTest(host=host):
                    skill = Path(folder)/relative
                    shutil.copytree(ROOT/"skills/tuck-bit", skill)
                    status = app.doctor_status(skill)
                    self.assertEqual(status["status"], "pass", status)
                    self.assertEqual(status["layout"], "skill-only")
                    self.assertIn("separate from skill", status["runtime"])
                    self.assertFalse((skill/"scripts").exists())
            self.assertEqual(len(installer.PROJECT), 6)

    def test_project_only_never_looks_up_home_and_preserves_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project/".tuck-bit").mkdir()
            (project/".tuck-bit/config.json").write_text(json.dumps({"modules": {"metrics": True}}))
            with patch.object(app.Path, "home", side_effect=AssertionError("global lookup")):
                result = app.resolve(project, project_only=True, session_profile="critical", disable=["metrics"])
            self.assertEqual(result["profile"], "critical")
            self.assertFalse(result["modules"]["metrics"])
            with self.assertRaisesRegex(ValueError, "Cannot combine"):
                app.resolve(project, global_config=project/"global.json", project_only=True)
            result = self.cli("config", "--project", project, "--project-only")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["modules"]["metrics"])

    def test_config_json_errors_do_not_disclose_config_keys_or_paths(self):
        with tempfile.TemporaryDirectory(prefix="PRIVATE_SENTINEL_") as folder:
            root = Path(folder)
            (root/".tuck-bit").mkdir()
            (root/".tuck-bit/config.json").write_text('{"PRIVATE_CREDENTIAL_SENTINEL":true}')
            result = self.cli("config", "--project", root, "--project-only", "--json-errors")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)["code"], "invalid_configuration")
            self.assertNotIn("PRIVATE_", result.stdout+result.stderr)
            self.assertEqual(result.stdout, "")

    def test_text_doctor_and_catalog_validation_remain_explicit(self):
        result = self.cli("doctor")
        self.assertEqual((result.returncode, result.stdout), (0, "TuckBit doctor: PASS\n"))
        for invalid in ({"profile":"unsupported","modules":{"context":True}},
                        {"modules":{"../PRIVATE_SENTINEL":True}}, {"modules":{}}, {"modules":[]}):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as folder:
                skill = Path(folder)
                (skill/"SKILL.md").write_text("---\nname: tuck-bit\n---\n")
                (skill/"assets").mkdir()
                (skill/"assets/modules.json").write_text(json.dumps(invalid))
                status = app.doctor_status(skill)
                self.assertEqual(status["issues"][0]["code"], "invalid_catalog")
                self.assertNotIn("PRIVATE_SENTINEL", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
