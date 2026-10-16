import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "tuckbit.py"
spec = importlib.util.spec_from_file_location("tuckbit", SOURCE)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        cfg=app.defaults()
        self.assertEqual(cfg["profile"],"balanced")
        self.assertEqual(cfg["modules"],{
            "registry":True,"context":True,"verification":True,
            "budget":True,"orchestration":False,"metrics":False})
    def test_profile_override(self):
        with tempfile.TemporaryDirectory() as t:
            cfg=app.resolve(t,global_config=Path(t)/"none.json",session_profile="critical")
            self.assertEqual(cfg["profile"],"critical")
    def test_global_project_and_session_precedence(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            gc=p/"global.json"
            gc.write_text(json.dumps({"profile":"economy","modules":{"metrics":True}}))
            (p/".tuck-bit").mkdir()
            (p/".tuck-bit"/"config.json").write_text(json.dumps({"profile":"critical","modules":{"metrics":False}}))
            cfg=app.resolve(p,global_config=gc,session_profile="balanced",enable=["orchestration"])
            self.assertEqual(cfg["profile"],"balanced")
            self.assertTrue(cfg["modules"]["orchestration"])
            self.assertFalse(cfg["modules"]["metrics"])
    def test_unknown_module_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                app.resolve(t,global_config=Path(t)/"none.json",enable=["unknown"])
    def test_conflicting_override_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                app.resolve(t,global_config=Path(t)/"none.json",enable=["metrics"],disable=["metrics"])
    def test_invalid_config_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            (p/".tuck-bit").mkdir()
            (p/".tuck-bit"/"config.json").write_text('{"modules":{"budget":"yes"}}')
            with self.assertRaises(ValueError):
                app.resolve(p,global_config=p/"none.json")
    def test_doctor(self):
        self.assertEqual(app.doctor(),[])
    def test_doctor_detects_missing_source(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(app.doctor(Path(t)))
if __name__ == "__main__":
    unittest.main()
