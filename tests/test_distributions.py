import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"sync_distributions.py"
spec=importlib.util.spec_from_file_location("sync_distributions",SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class DistributionTests(unittest.TestCase):
    def test_generated_manifests_are_synced(self):
        result=subprocess.run([sys.executable,str(SCRIPT),"--check"],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_consistent_identity(self):
        master=json.loads((ROOT/"distribution.json").read_text())
        for path in ("plugin.json",".claude-plugin/plugin.json",".codex-plugin/plugin.json","gemini-extension.json"):
            manifest=json.loads((ROOT/path).read_text())
            self.assertEqual(manifest["name"],master["name"])
            self.assertEqual(manifest["version"],master["version"])

    def test_only_one_skill_source(self):
        # Only one canonical, automatically packaged skill; localized variants are explicit opt-ins.
        all_skill_paths=[p for p in (ROOT/"skills").rglob("SKILL.md") if ".git" not in p.parts]
        self.assertEqual(all_skill_paths,[ROOT/"skills"/"tuck-bit"/"SKILL.md"])

    def test_six_modules_and_defaults(self):
        policy=json.loads((ROOT/"skills"/"tuck-bit"/"assets"/"modules.json").read_text())
        self.assertEqual(sum(policy["modules"].values()),4)
        self.assertEqual(len(policy["modules"]),6)
        self.assertFalse(policy["modules"]["metrics"])
        self.assertFalse(policy["modules"]["orchestration"])

    def test_marketplace_entries_opt_in_and_correct(self):
        claude=json.loads((ROOT/".claude-plugin/marketplace.json").read_text())
        codex=json.loads((ROOT/".agents/plugins/marketplace.json").read_text())
        self.assertEqual(claude["plugins"][0]["name"],"tuck-bit")
        self.assertEqual(codex["plugins"][0]["name"],"tuck-bit")
        self.assertEqual(codex["plugins"][0]["policy"]["installation"],"AVAILABLE")
        self.assertEqual(codex["plugins"][0]["source"]["path"],"./")

    def test_bundled_skill_path(self):
        codex=json.loads((ROOT/".codex-plugin/plugin.json").read_text())
        self.assertEqual(codex["skills"],"./skills/")
        self.assertTrue((ROOT/"skills"/"tuck-bit"/"SKILL.md").is_file())

    def test_no_auto_start_services(self):
        paths=["plugin.json",".claude-plugin/plugin.json",".codex-plugin/plugin.json","gemini-extension.json"]
        for p in paths:
            obj=json.loads((ROOT/p).read_text())
            self.assertNotIn("mcpServers",obj)
            self.assertNotIn("hooks",obj)
            self.assertNotIn("contextFileName",obj)

if __name__=="__main__":
    unittest.main()
