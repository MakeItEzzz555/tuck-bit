"""Model-free safety checks for optional translated onboarding and skills."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
import sys
sys.path.insert(0,str(SCRIPTS))
import check_i18n


class LocalizationTests(unittest.TestCase):
    def test_catalog_has_fourteen_distinct_locales(self):
        data=json.loads((ROOT / "localization-catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["locales"]),14)
        self.assertEqual(len(set(data["locales"])),14)
        self.assertEqual(data["canonical_skill"], "skills/tuck-bit/SKILL.md")

    def test_localization_build_is_deterministic(self):
        self.assertIn("i18n PASS",check_i18n.validate())

    def test_translated_skills_are_not_in_canonical_plugin_root(self):
        self.assertEqual([p.relative_to(ROOT).as_posix() for p in (ROOT / "skills").rglob("SKILL.md")],
                         ["skills/tuck-bit/SKILL.md"])
        self.assertEqual(len(list((ROOT / "locales").rglob("SKILL.md"))),14)

    def test_all_manual_skill_install_commands_are_project_scoped(self):
        for p in (ROOT/"docs/i18n").glob("*/README.md"):
            text=p.read_text(encoding="utf-8")
            self.assertIn("/path/to/project/.agents/skills",text)
            self.assertNotIn("--scope global",text)

    def test_source_language_explanations_never_promise_token_savings(self):
        for p in (ROOT/"docs/i18n").glob("*/README.md"):
            self.assertIn(json.loads((ROOT/"localization-catalog.json").read_text())["locales"][p.parent.name]["install_notice"],p.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
