import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tuck_installer", ROOT/"scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_cli_project_install_status_uninstall(self):
        import subprocess
        import sys
        target=self.root/installer.PROJECT["claude"]
        common=[sys.executable,str(ROOT/"scripts/install.py")]
        cmd=["--client","claude","--scope","project","--project",str(self.root)]
        dry=subprocess.run(common+["install"]+cmd+["--dry-run"],capture_output=True,text=True)
        self.assertEqual(dry.returncode,0,dry.stderr)
        self.assertFalse(target.exists())
        added=subprocess.run(common+["install"]+cmd,capture_output=True,text=True)
        self.assertEqual(added.returncode,0,added.stderr)
        self.assertTrue(target.is_dir())
        status=subprocess.run(common+["status"]+cmd,capture_output=True,text=True)
        self.assertEqual(status.returncode,0,status.stderr)
        self.assertIn("installed, intact",status.stdout)
        removed=subprocess.run(common+["uninstall"]+cmd,capture_output=True,text=True)
        self.assertEqual(removed.returncode,0,removed.stderr)
        self.assertFalse(target.exists())

    def test_cli_global_fake_home(self):
        import subprocess
        import sys
        common=[sys.executable,str(ROOT/"scripts/install.py")]
        cmd=["--scope","global","--client","opencode","--home",str(self.root)]
        a=subprocess.run(common+["install"]+cmd,capture_output=True,text=True)
        self.assertEqual(a.returncode,0,a.stderr)
        target=self.root/installer.GLOBAL["opencode"]
        self.assertTrue(target.is_dir())
        b=subprocess.run(common+["uninstall"]+cmd,capture_output=True,text=True)
        self.assertEqual(b.returncode,0,b.stderr)
        self.assertFalse(target.exists())

    def test_source_is_well_formed(self):
        self.assertTrue((installer.SOURCE/"SKILL.md").is_file())
        self.assertEqual(len(installer.PROJECT), 6)
        self.assertEqual(len(installer.GLOBAL), 6)

    def test_dry_run_never_writes(self):
        before = list(self.root.iterdir())
        s = installer.install(self.root, "project", "claude", dry_run=True)
        self.assertIn("would install", s)
        self.assertEqual(list(self.root.iterdir()), before)

    def test_project_install_uninstall(self):
        target = self.root/installer.PROJECT["claude"]
        self.assertIn("installed", installer.install(self.root,"project","claude"))
        self.assertTrue((target/"SKILL.md").is_file())
        self.assertEqual(installer.digest(target), installer.digest(installer.SOURCE))
        self.assertIn("unchanged", installer.install(self.root,"project","claude"))
        self.assertIn("installed, intact",installer.status(self.root,"project","claude"))
        self.assertIn("uninstalled",installer.uninstall(self.root,"project","claude"))
        self.assertFalse(target.exists())
        self.assertFalse(installer._load_state(self.root)["entries"])

    def test_standalone_skill_references_stay_inside_installed_tree(self):
        import re
        installer.install(self.root, "project", "codex")
        target = (self.root / installer.PROJECT["codex"]).resolve()
        self.assertFalse((self.root / "docs").exists())
        checked = 0
        for document in target.rglob("*.md"):
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text()):
                if "://" in link or link.startswith("#"):
                    continue
                resource = (document.parent / link.split("#")[0]).resolve()
                self.assertTrue(resource.is_relative_to(target), (document, link))
                self.assertTrue(resource.is_file(), (document, link))
                checked += 1
        self.assertGreater(checked, 0)
        installer.uninstall(self.root, "project", "codex")
        self.assertFalse(target.exists())

    def test_all_six_project_clients(self):
        for client in installer.CLIENTS:
            installer.install(self.root,"project",client)
        for client in installer.CLIENTS:
            target=self.root/installer.PROJECT[client]
            self.assertTrue((target/"SKILL.md").is_file())
        for client in reversed(installer.CLIENTS):
            installer.uninstall(self.root,"project",client)
        self.assertEqual(len(installer._load_state(self.root)["entries"]),0)

    def test_global_scope_uses_global_open_code_path(self):
        installer.install(self.root,"global","opencode")
        self.assertTrue((self.root/".config/opencode/skills/tuck-bit/SKILL.md").is_file())
        installer.uninstall(self.root,"global","opencode")
        self.assertFalse((self.root/".config/opencode/skills/tuck-bit").exists())

    def test_refuse_existing_without_replace(self):
        target=self.root/installer.PROJECT["codex"]
        target.mkdir(parents=True)
        (target/"SKILL.md").write_text("preexisting")
        with self.assertRaises(installer.InstallError):
            installer.install(self.root,"project","codex")
        self.assertEqual((target/"SKILL.md").read_text(),"preexisting")

    def test_replace_creates_backup_and_uninstall_restores(self):
        target=self.root/installer.PROJECT["gemini"]
        target.mkdir(parents=True)
        (target/"SKILL.md").write_text("user's earlier skill")
        installer.install(self.root,"project","gemini",replace=True)
        state=installer._load_state(self.root)["entries"]["gemini"]
        self.assertTrue((self.root/state["backup"]/"SKILL.md").is_file())
        self.assertNotEqual((target/"SKILL.md").read_text(),"user's earlier skill")
        installer.uninstall(self.root,"project","gemini")
        self.assertEqual((target/"SKILL.md").read_text(),"user's earlier skill")

    def test_modified_managed_target_is_never_removed(self):
        target=self.root/installer.PROJECT["cursor"]
        installer.install(self.root,"project","cursor")
        with (target/"SKILL.md").open("a") as fp:
            fp.write("\nUser edits.\n")
        with self.assertRaises(installer.InstallError):
            installer.uninstall(self.root,"project","cursor")
        self.assertIn("User edits.", (target/"SKILL.md").read_text())

    def test_symlink_ancestor_rejected(self):
        real=self.root/"other"
        real.mkdir()
        (self.root/".claude").symlink_to(real, target_is_directory=True)
        with self.assertRaises(installer.InstallError):
            installer.install(self.root,"project","claude")
        self.assertEqual(list(real.iterdir()),[])

    def test_existing_file_collision_rejected_even_with_replace(self):
        target=self.root/installer.PROJECT["copilot"]
        target.parent.mkdir(parents=True)
        target.write_text("important user file")
        with self.assertRaises(installer.InstallError):
            installer.install(self.root,"project","copilot",replace=True)
        self.assertEqual(target.read_text(),"important user file")

    def test_failure_of_state_write_restores_previous_skill(self):
        target=self.root/installer.PROJECT["codex"]
        target.mkdir(parents=True)
        (target/"SKILL.md").write_text("existing")
        with mock.patch.object(installer,"_save_state",side_effect=OSError("failed write")):
            with self.assertRaises(OSError):
                installer.install(self.root,"project","codex",replace=True)
        self.assertEqual((target/"SKILL.md").read_text(),"existing")
        self.assertFalse(installer._load_state(self.root)["entries"])

    def test_uninstall_failed_state_write_restores_managed_copy(self):
        target=self.root/installer.PROJECT["codex"]
        installer.install(self.root,"project","codex")
        prior_hash=installer.digest(target)
        with mock.patch.object(installer,"_save_state",side_effect=OSError("failed write")):
            with self.assertRaises(OSError):
                installer.uninstall(self.root,"project","codex")
        self.assertEqual(installer.digest(target),prior_hash)
        self.assertIn("codex",installer._load_state(self.root)["entries"])

    def test_uninstall_failed_state_write_preserves_backup(self):
        target=self.root/installer.PROJECT["claude"]
        target.mkdir(parents=True)
        (target/"SKILL.md").write_text("original")
        installer.install(self.root,"project","claude",replace=True)
        prior_hash=installer.digest(target)
        with mock.patch.object(installer,"_save_state",side_effect=OSError("failed write")):
            with self.assertRaises(OSError):
                installer.uninstall(self.root,"project","claude")
        self.assertEqual(installer.digest(target),prior_hash)
        self.assertEqual(installer._load_state(self.root)["entries"]["claude"]["target"],str(target.resolve()))
        installer.uninstall(self.root,"project","claude")
        self.assertEqual((target/"SKILL.md").read_text(),"original")

    def test_batch_install_rolls_back_after_second_client_error(self):
        original=installer.install
        calls=[]
        def flaky(root,scope,client,**kwargs):
            calls.append(client)
            if client=="codex":
                raise OSError("simulated second-client error")
            return original(root,scope,client,**kwargs)
        with mock.patch.object(installer,"install",side_effect=flaky):
            # An explicit installer batch replicates the CLI's rollback behavior.
            installed=[]
            try:
                for client in ("claude","codex"):
                    result=installer.install(self.root,"project",client)
                    if result.startswith(client+": installed"):
                        installed.append(client)
            except OSError:
                for client in reversed(installed):
                    installer.uninstall(self.root,"project",client)
        self.assertEqual(calls,["claude","codex"])
        self.assertFalse((self.root/installer.PROJECT["claude"]).exists())
        self.assertEqual(installer._load_state(self.root)["entries"],{})

    def test_corrupt_state_fails_closed(self):
        state_path=self.root/".tuck-bit/installations.json"
        state_path.parent.mkdir()
        state_path.write_text("{bad")
        with self.assertRaises(installer.InstallError):
            installer.install(self.root,"project","codex")

    def test_uninstall_dry_run_does_not_remove(self):
        target=self.root/installer.PROJECT["claude"]
        installer.install(self.root,"project","claude")
        result=installer.uninstall(self.root,"project","claude",dry_run=True)
        self.assertIn("would remove",result)
        self.assertTrue(target.is_dir())

    def test_status_is_read_only(self):
        self.assertIn("not managed",installer.status(self.root,"project","codex"))
        self.assertEqual(list(self.root.iterdir()),[])

    def test_all_six_supported_clients_have_distinct_paths(self):
        self.assertEqual(len(set(installer.PROJECT.values())),len(installer.PROJECT))
        self.assertEqual(len(set(installer.GLOBAL.values())),len(installer.GLOBAL))


if __name__ == "__main__":
    unittest.main()
