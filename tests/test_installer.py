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

    def test_standalone_installed_skill_documentation_stays_inside_copied_tree(self):
        import re
        installer.install(self.root, "project", "codex")
        target=(self.root/installer.PROJECT["codex"]).resolve()
        self.assertFalse((self.root/"docs").exists())
        checked=0
        for document in target.rglob("*.md"):
            for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', document.read_text()):
                if '://' in link or link.startswith('#'):
                    continue
                resource=(document.parent/link.split('#')[0]).resolve()
                self.assertTrue(resource.is_relative_to(target), (document, link))
                self.assertTrue(resource.is_file(), (document, link))
                checked+=1
        self.assertGreater(checked,0)
        installer.uninstall(self.root,"project","codex")
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

    def changed_source(self):
        import shutil
        source = self.root / "source"
        shutil.copytree(installer.SOURCE, source)
        skill = source / "SKILL.md"
        skill.write_text(skill.read_text().replace('version: "0.1.2"', 'version: "0.1.3"') + "\nNew revision\n")
        return source

    def test_explicit_update_rollback_and_original_restore(self):
        target = self.root / installer.PROJECT["codex"]
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("original user skill")
        installer.install(self.root, "project", "codex", replace=True)
        original_hash = installer.digest(target)
        source = self.changed_source()
        with mock.patch.object(installer, "SOURCE", source):
            with self.assertRaises(installer.InstallError):
                installer.install(self.root, "project", "codex", replace=True)
            self.assertIn("would update", installer.update(self.root, "project", "codex", dry_run=True))
            self.assertEqual(installer.digest(target), original_hash)
            self.assertIn("updated", installer.update(self.root, "project", "codex"))
            self.assertEqual(installer.digest(target), installer.digest(source))
        self.assertIn("rolled back", installer.update(self.root, "project", "codex", rollback=True))
        self.assertEqual(installer.digest(target), original_hash)
        self.assertEqual(installer._load_state(self.root)["entries"]["codex"]["history"], [])
        installer.uninstall(self.root, "project", "codex")
        self.assertEqual((target / "SKILL.md").read_text(), "original user skill")

    def test_update_state_failure_restores_current_and_keeps_original(self):
        installer.install(self.root, "project", "codex")
        target = self.root / installer.PROJECT["codex"]
        original_hash = installer.digest(target)
        state_bytes = installer._state_path(self.root).read_bytes()
        source = self.changed_source()
        with mock.patch.object(installer, "SOURCE", source), mock.patch.object(installer, "_save_state", side_effect=OSError("failed state")):
            with self.assertRaises(OSError):
                installer.update(self.root, "project", "codex")
        self.assertEqual(installer.digest(target), original_hash)
        self.assertEqual(installer._state_path(self.root).read_bytes(), state_bytes)

    def test_rollback_failure_preserves_both_managed_versions(self):
        installer.install(self.root, "project", "codex")
        source = self.changed_source()
        with mock.patch.object(installer, "SOURCE", source):
            installer.update(self.root, "project", "codex")
        target = self.root / installer.PROJECT["codex"]
        original_hash = installer.digest(target)
        state_bytes = installer._state_path(self.root).read_bytes()
        with mock.patch.object(installer, "_save_state", side_effect=OSError("failed state")):
            with self.assertRaises(OSError):
                installer.update(self.root, "project", "codex", rollback=True)
        self.assertEqual(installer.digest(target), original_hash)
        self.assertEqual(installer._state_path(self.root).read_bytes(), state_bytes)
        installer.update(self.root, "project", "codex", rollback=True)

    def test_uninstall_after_upgrade_removes_managed_history(self):
        installer.install(self.root, "project", "codex")
        with mock.patch.object(installer, "SOURCE", self.changed_source()):
            installer.update(self.root, "project", "codex")
        installer.uninstall(self.root, "project", "codex")
        self.assertEqual(list((self.root / ".tuck-bit/backups").iterdir()), [])

    def test_modified_or_missing_backup_refuses_update_and_uninstall(self):
        target = self.root / installer.PROJECT["codex"]
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("original")
        installer.install(self.root, "project", "codex", replace=True)
        entry = installer._load_state(self.root)["entries"]["codex"]
        backup = self.root / entry["backup"] / "SKILL.md"
        backup.write_text("edited original")
        for action in (installer.uninstall, installer.update):
            with self.assertRaises(installer.InstallError):
                action(self.root, "project", "codex")
        self.assertIn("MODIFIED", installer.status(self.root, "project", "codex"))
        self.assertEqual(backup.read_text(), "edited original")

    def test_modified_managed_copy_refuses_update_and_rollback(self):
        installer.install(self.root, "project", "codex")
        (self.root / installer.PROJECT["codex"] / "SKILL.md").write_text("my edits")
        for rollback in (False, True):
            with self.assertRaises(installer.InstallError):
                installer.update(self.root, "project", "codex", rollback=rollback)

    def test_arbitrary_root_paths_cannot_be_used_as_backups(self):
        import json
        installer.install(self.root, "project", "codex")
        state = installer._load_state(self.root)
        important = self.root / "important"
        important.mkdir()
        (important / "notes").write_text("private data")
        for value in ("important", ".tuck-bit/backups/../important", str(important), ".tuck-bit/backups/codex-1234", ".tuck-bit/backups/claude-" + "a" * 32):
            state["entries"]["codex"]["backup"] = value
            state["entries"]["codex"]["backup_sha256"] = installer.digest(important)
            installer._state_path(self.root).write_text(json.dumps(state))
            with self.assertRaises(installer.InstallError):
                installer.uninstall(self.root, "project", "codex")
            self.assertEqual((important / "notes").read_text(), "private data")

    def test_corrupted_state_types_fail_with_install_error(self):
        import json
        path = installer._state_path(self.root)
        path.parent.mkdir()
        values = [[], None, 1, {"schema": True, "entries": {}}, {"schema": 1, "entries": []},
                  {"schema": 2, "entries": {"codex": []}}, {"schema": 2, "entries": {"unknown": {}}}]
        for value in values:
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                with self.assertRaises(installer.InstallError):
                    installer._load_state(self.root)

    def test_corrupted_entry_types_fail_closed(self):
        import copy
        import json
        installer.install(self.root, "project", "codex")
        base = installer._load_state(self.root)
        for key, value in (("target", []), ("sha256", None), ("backup", []), ("history", {}),
                           ("history", [None]), ("version", 3), ("backup_sha256", "f" * 64)):
            state = copy.deepcopy(base)
            state["entries"]["codex"][key] = value
            installer._state_path(self.root).write_text(json.dumps(state))
            with self.subTest(key=key), self.assertRaises(installer.InstallError):
                installer.uninstall(self.root, "project", "codex")

    def test_legacy_state_migrates_only_on_successful_mutation(self):
        import json
        installer.install(self.root, "project", "codex")
        state = installer._load_state(self.root)
        state["schema"] = 1
        state.pop("hash_format")
        state["entries"]["codex"]["sha256"] = installer.digest(self.root / installer.PROJECT["codex"], legacy=True)
        for key in ("version", "history", "backup_sha256"):
            state["entries"]["codex"].pop(key, None)
        path = installer._state_path(self.root)
        path.write_text(json.dumps(state))
        before = path.read_bytes()
        self.assertIn("intact", installer.status(self.root, "project", "codex"))
        self.assertEqual(path.read_bytes(), before)
        with mock.patch.object(installer, "SOURCE", self.changed_source()):
            installer.update(self.root, "project", "codex")
        self.assertEqual(json.loads(path.read_text())["schema"], 2)
        installer.update(self.root, "project", "codex", rollback=True)
        self.assertIn("intact", installer.status(self.root, "project", "codex"))

    def test_symlink_root_and_ancestor_are_rejected(self):
        real = self.root / "real"
        real.mkdir()
        child = real / "child"
        child.mkdir()
        link = self.root / "linked"
        link.symlink_to(real, target_is_directory=True)
        for path in (link, link / "child"):
            with self.assertRaises(installer.InstallError):
                installer.install(path, "project", "codex")
        self.assertEqual(list(child.iterdir()), [])

    def test_state_symlink_and_source_file_symlink_are_rejected(self):
        state = installer._state_path(self.root)
        state.parent.mkdir()
        outside = self.root / "outside"
        outside.write_text("{}")
        state.symlink_to(outside)
        with self.assertRaises(installer.InstallError):
            installer.install(self.root, "project", "codex")
        state.unlink()
        source = self.changed_source()
        (source / "external").symlink_to(outside)
        with mock.patch.object(installer, "SOURCE", source), self.assertRaises(installer.InstallError):
            installer.install(self.root, "project", "codex")

    def test_source_changed_during_staging_is_rejected(self):
        original = installer.shutil.copytree
        def modified(src, dst, *args, **kwargs):
            result = original(src, dst, *args, **kwargs)
            (Path(dst) / "SKILL.md").write_text("changed during copy")
            return result
        with mock.patch.object(installer.shutil, "copytree", side_effect=modified):
            with self.assertRaises(installer.InstallError):
                installer.install(self.root, "project", "codex")
        self.assertFalse((self.root / installer.PROJECT["codex"]).exists())

    def test_backup_symlink_rejected_before_uninstall(self):
        installer.install(self.root, "project", "codex")
        with mock.patch.object(installer, "SOURCE", self.changed_source()):
            installer.update(self.root, "project", "codex")
        entry = installer._load_state(self.root)["entries"]["codex"]
        backup = self.root / entry["history"][0]["path"]
        renamed = self.root / "renamed"
        backup.rename(renamed)
        backup.symlink_to(renamed, target_is_directory=True)
        with self.assertRaises(installer.InstallError):
            installer.uninstall(self.root, "project", "codex")


    def test_active_or_interrupted_installer_lock_blocks_mutations(self):
        lock = self.root / ".tuck-bit/install.lock"
        lock.mkdir(parents=True)
        for action in (installer.install, installer.update, installer.uninstall):
            with self.assertRaises(installer.InstallError):
                action(self.root, "project", "codex")
        self.assertTrue(lock.is_dir())
        self.assertIn("would install", installer.install(self.root, "project", "codex", dry_run=True))

    def test_failure_releases_installer_lock(self):
        with mock.patch.object(installer, "_save_state", side_effect=OSError("failed state")):
            with self.assertRaises(OSError):
                installer.install(self.root, "project", "codex")
        self.assertFalse((self.root / ".tuck-bit/install.lock").exists())
        installer.install(self.root, "project", "codex")


    def test_length_framing_prevents_file_boundary_digest_collision(self):
        left, right = self.root / "left", self.root / "right"
        left.mkdir()
        right.mkdir()
        (left / "a").write_bytes(b"x")
        (left / "b").write_bytes(b"y")
        (right / "a").write_bytes(b"x\x00b\x00y")
        self.assertEqual(installer.digest(left, legacy=True), installer.digest(right, legacy=True))
        self.assertNotEqual(installer.digest(left), installer.digest(right))

    def test_legacy_migration_rejects_changed_target_before_rehashing(self):
        import json
        installer.install(self.root, "project", "codex")
        target = self.root / installer.PROJECT["codex"]
        state = installer._load_state(self.root)
        state["schema"] = 1
        state.pop("hash_format")
        state["entries"]["codex"] = {"target": str(target.resolve()), "sha256": installer.digest(target, legacy=True), "backup": None}
        installer._state_path(self.root).write_text(json.dumps(state))
        (target / "SKILL.md").write_text("changed")
        with self.assertRaises(installer.InstallError):
            installer.update(self.root, "project", "codex")
        self.assertEqual((target / "SKILL.md").read_text(), "changed")

    def test_unknown_hash_format_refused(self):
        import json
        installer.install(self.root, "project", "codex")
        state = installer._load_state(self.root)
        state["hash_format"] = "unsupported"
        installer._state_path(self.root).write_text(json.dumps(state))
        with self.assertRaises(installer.InstallError):
            installer.uninstall(self.root, "project", "codex")


    def test_state_fifo_rejected_without_blocking(self):
        import os
        import subprocess
        import sys
        path = installer._state_path(self.root)
        path.parent.mkdir()
        os.mkfifo(path)
        result = subprocess.run([sys.executable, str(ROOT / "scripts/install.py"), "status", "--client", "codex", "--project", str(self.root)],
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertIn("ordinary file", result.stderr)

    def test_oversized_state_rejected(self):
        path = installer._state_path(self.root)
        path.parent.mkdir()
        path.write_bytes(b" " * (installer.MAX_STATE_BYTES + 1))
        with self.assertRaises(installer.InstallError):
            installer._load_state(self.root)

    def test_legacy_original_backup_restores_after_framed_migration(self):
        import json
        target = self.root / installer.PROJECT["codex"]
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("original user skill")
        installer.install(self.root, "project", "codex", replace=True)
        state = installer._load_state(self.root)
        state["schema"] = 1
        state.pop("hash_format")
        entry = state["entries"]["codex"]
        state["entries"]["codex"] = {"target": str(target.resolve()), "sha256": installer.digest(target, legacy=True), "backup": entry["backup"]}
        installer._state_path(self.root).write_text(json.dumps(state))
        with mock.patch.object(installer, "SOURCE", self.changed_source()):
            installer.update(self.root, "project", "codex")
        self.assertEqual(installer._load_state(self.root)["hash_format"], installer.HASH_FORMAT)
        installer.uninstall(self.root, "project", "codex")
        self.assertEqual((target / "SKILL.md").read_text(), "original user skill")


    def test_positional_dry_run_never_creates_state_or_lock(self):
        self.assertIn("would install", installer.install(self.root, "project", "codex", False, True))
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertIn("not installed", installer.uninstall(self.root, "project", "codex", True))
        self.assertEqual(list(self.root.iterdir()), [])
        with self.assertRaises(installer.InstallError):
            installer.update(self.root, "project", "codex", True)
        self.assertEqual(list(self.root.iterdir()), [])



if __name__ == "__main__":
    unittest.main()
