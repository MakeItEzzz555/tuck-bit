"""Model-free tests for crash-safe, private, fail-closed native benchmark resume."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark_journal import BenchmarkJournal, JournalError
from benchmark_runner import execute, fingerprint, canonical_skill_fingerprint
from test_benchmark_runner import fake_run


class JournalTests(unittest.TestCase):
    def test_private_atomic_creation_and_explicit_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"receipts.json"
            journal = BenchmarkJournal(path, "a"*64)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(journal.runs, [])
            with self.assertRaises(JournalError):
                BenchmarkJournal(path, "a"*64)
            journal.close()
            with BenchmarkJournal(path, "a"*64, resume=True) as resumed:
                self.assertEqual(resumed.runs, [])
            with self.assertRaises(JournalError):
                BenchmarkJournal(path, "b"*64, resume=True)
            self.assertEqual(set(json.loads(path.read_text())), {"schema", "run_sha256", "runs", "inflight", "interrupted", "order"})

    def test_resume_runs_only_missing_arms(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"run.json"
            observed = []
            def run(*args):
                observed.append(args[3])
                return fake_run(*args)
            first = execute(["localized_bug"], "fake", 2, 1, runner=run, executable=sys.executable, journal_path=path)
            self.assertEqual(len(first), 3)
            self.assertEqual(len(observed), 3)
            observed.clear()
            again = execute(["localized_bug"], "fake", 2, 1, runner=run, executable=sys.executable, journal_path=path, resume=True)
            self.assertEqual(first, again)
            self.assertEqual(observed, [])
            with self.assertRaises(JournalError):
                execute(["localized_bug"], "other-model", 2, 1, runner=run, executable=sys.executable,
                        journal_path=path, resume=True)
            with self.assertRaises(JournalError):
                execute(["localized_bug"], "fake", 3, 1, runner=run, executable=sys.executable,
                        journal_path=path, resume=True)

    def test_interruption_blocks_silent_replay_then_records_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"partial.json"
            count = 0
            def interrupted(*args):
                nonlocal count
                count += 1
                if count == 2:
                    raise RuntimeError("simulated lost client")
                return fake_run(*args)
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                execute(["localized_bug"], "fake", 2, 1, runner=interrupted,
                        executable=sys.executable, journal_path=path)
            payload = json.loads(path.read_text())
            self.assertEqual(len(payload["runs"]), 1)
            self.assertEqual(payload["inflight"]["mode"], "skill_only")
            with self.assertRaises(JournalError):
                execute(["localized_bug"], "fake", 2, 1, runner=fake_run,
                        executable=sys.executable, journal_path=path, resume=True)
            recovered = execute(["localized_bug"], "fake", 2, 1, runner=fake_run,
                                executable=sys.executable, journal_path=path,
                                resume=True, acknowledge_incomplete=True)
            self.assertEqual([r["mode"] for r in recovered], ["baseline", "adapters"])
            ledger = json.loads(path.read_text())
            self.assertEqual([a["mode"] for a in ledger["interrupted"]], ["skill_only"])
            self.assertIsNone(ledger["inflight"])
            self.assertEqual([a["mode"] for a in ledger["order"]], ["baseline", "skill_only", "adapters"])

    def test_corruption_wrong_order_symlink_and_permissions_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"run.json"
            complete = execute(["localized_bug"], "fake", 2, 1, runner=fake_run,
                               executable=sys.executable, journal_path=path)
            self.assertEqual(len(complete), 3)
            data = json.loads(path.read_text())
            digest = data["run_sha256"]
            data["order"].reverse()
            path.write_text(json.dumps(data))
            with self.assertRaises(JournalError):
                execute(["localized_bug"], "fake", 2, 1, runner=fake_run,
                        executable=sys.executable, journal_path=path, resume=True)
            path.write_text("INVALID")
            with self.assertRaises(JournalError):
                BenchmarkJournal(path, digest, resume=True)
            path.chmod(0o644)
            with self.assertRaises(JournalError):
                BenchmarkJournal(path, digest, resume=True)
            path.unlink()
            path.symlink_to(Path(directory)/"other")
            with self.assertRaises(JournalError):
                BenchmarkJournal(path, digest)
            with self.assertRaises(JournalError):
                BenchmarkJournal(path, digest, resume=True)

    def test_cli_requires_explicit_opt_in(self):
        runner = ROOT/"scripts/benchmark_runner.py"
        for args in (["--resume"], ["--ack-incomplete"], ["--execute", "--resume", "--model", "fake"],
                     ["--execute", "--ack-incomplete", "--journal", "/tmp/unused", "--model", "fake"]):
            p = subprocess.run([sys.executable, str(runner), *args], capture_output=True, timeout=10)
            self.assertEqual(p.returncode, 2, args)

    def test_exclusive_owner_prevents_concurrent_overwrite_of_failure(self):
        from test_benchmark import runs
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "concurrent.json"
            failed = runs()[0]
            failed["trace"]["outcome"] = {"verified": False, "acceptance_checks_passed": False}
            with BenchmarkJournal(path, "a"*64) as owner:
                marker = owner.marker(failed["case"], failed["trial"], failed["mode"], failed["identity"])
                owner.start(marker)
                with self.assertRaisesRegex(JournalError, "owns"):
                    BenchmarkJournal(path, "a"*64, resume=True, acknowledge_incomplete=True)
                script = ("import sys; sys.path.insert(0," + repr(str(ROOT / "scripts")) + "); "
                          "from benchmark_journal import BenchmarkJournal; "
                          "BenchmarkJournal(" + repr(str(path)) + ", 'a'*64, resume=True, acknowledge_incomplete=True)")
                blocked = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn("Another execution owns", blocked.stderr)
                owner.complete(failed)
            with self.assertRaisesRegex(JournalError, "released"):
                owner.complete(runs()[0])
            with BenchmarkJournal(path, "a"*64, resume=True) as resumed:
                self.assertEqual(resumed.runs, [failed])
                with self.assertRaises(JournalError):
                    resumed.start(marker)
            self.assertFalse(json.loads(path.read_text())["runs"][0]["trace"]["outcome"]["verified"])

    def test_execute_releases_owner_lock_after_exception_and_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lifetime.json"
            def interrupted(*args):
                with self.assertRaisesRegex(JournalError, "owns"):
                    BenchmarkJournal(path, "a"*64, resume=True)
                raise RuntimeError("stop")
            with self.assertRaisesRegex(RuntimeError, "stop"):
                execute(["localized_bug"], "fake", 2, 1, runner=interrupted,
                        executable=sys.executable, journal_path=path)
            recovered = execute(["localized_bug"], "fake", 2, 1, runner=fake_run,
                                executable=sys.executable, journal_path=path, resume=True, acknowledge_incomplete=True)
            self.assertEqual(len(recovered), 2)
            digest = json.loads(path.read_text())["run_sha256"]
            with BenchmarkJournal(path, digest, resume=True) as reopened:
                self.assertEqual(reopened.runs, recovered)

    def test_resume_invalidates_changed_reference_or_asset_before_any_model_call(self):
        import benchmark_runner
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            (checkout / "scripts").mkdir(parents=True)
            for name in ("benchmark_runner.py", "benchmark.py", "benchmark_journal.py", "plan_task.py", "provider_events.py", "trace_profiler.py"):
                shutil.copyfile(ROOT / "scripts" / name, checkout / "scripts" / name)
            shutil.copytree(ROOT / "skills", checkout / "skills")
            with mock.patch.object(benchmark_runner, "ROOT", checkout):
                for relative in ("references/verification.md", "assets/hosts.json"):
                    with self.subTest(relative=relative):
                        path = Path(directory) / (Path(relative).stem + ".json")
                        execute(["localized_bug"], "fake", 2, 1, runner=fake_run, executable=sys.executable, journal_path=path)
                        changed = checkout / "skills/tuck-bit" / relative
                        original = changed.read_bytes()
                        changed.write_bytes(original + b"\nchanged fixture input\n")
                        denied_runner = mock.Mock(side_effect=AssertionError("must reject before model execution"))
                        with self.assertRaisesRegex(JournalError, "identity differs"):
                            execute(["localized_bug"], "fake", 2, 1, runner=denied_runner, executable=sys.executable,
                                    journal_path=path, resume=True)
                        denied_runner.assert_not_called()
                        changed.write_bytes(original)

    def test_canonical_skill_tree_rejects_symlinks_special_files_and_size_overruns(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("entry")
            expected = canonical_skill_fingerprint(skill)
            (skill / "references").mkdir()
            self.assertNotEqual(expected, canonical_skill_fingerprint(skill))
            path = skill / "references/proof.md"
            path.write_text("reference")
            self.assertNotEqual(expected, canonical_skill_fingerprint(skill))
            path.unlink()
            path.symlink_to(skill / "SKILL.md")
            with self.assertRaises(JournalError):
                canonical_skill_fingerprint(skill)
            path.unlink()
            os.mkfifo(path)
            with self.assertRaises(JournalError):
                canonical_skill_fingerprint(skill)
            path.unlink()
            path.write_bytes(b"x"*180001)
            with self.assertRaises(JournalError):
                canonical_skill_fingerprint(skill)

    def test_lock_symlinks_special_files_and_entry_overruns_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = root / "run.json"
            lock = root / "run.json.lock"
            lock.symlink_to(root / "other")
            with self.assertRaises(JournalError):
                BenchmarkJournal(journal, "a"*64)
            lock.unlink()
            os.mkfifo(lock, 0o600)
            with self.assertRaises(JournalError):
                BenchmarkJournal(journal, "a"*64)
            self.assertFalse(journal.exists())
            skill = root / "skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("entry")
            for number in range(128):
                (skill / str(number)).mkdir()
            with self.assertRaisesRegex(JournalError, "entry bound"):
                canonical_skill_fingerprint(skill)

    def test_schedule_changes_invalidate_resume_without_more_provider_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "balanced.json"
            first = execute(["localized_bug"], "fake", 2, 2, runner=fake_run, executable=sys.executable,
                            journal_path=path, arm_schedule="balanced")
            self.assertEqual([run["mode"] for run in first], ["baseline", "skill_only", "adapters", "adapters", "skill_only", "baseline"])
            refused_runner = mock.Mock(side_effect=AssertionError("must not replay"))
            again = execute(["localized_bug"], "fake", 2, 2, runner=refused_runner, executable=sys.executable,
                            journal_path=path, resume=True, arm_schedule="balanced")
            self.assertEqual(first, again)
            with self.assertRaisesRegex(JournalError, "identity differs"):
                execute(["localized_bug"], "fake", 2, 2, runner=refused_runner, executable=sys.executable,
                        journal_path=path, resume=True, arm_schedule="legacy")
            refused_runner.assert_not_called()

    def test_raw_or_malformed_trial_markers_are_rejected_before_mutation_or_persistence(self):
        from test_benchmark import runs
        receipt = runs()[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private-markers.json"
            with BenchmarkJournal(path, "a"*64) as journal:
                before = path.read_bytes()
                base = {"case": "localized_bug", "trial": 1, "mode": "baseline", "identity": receipt["identity"]}
                for key, value in (("case", "PRIVATE RAW COMMAND"), ("mode", "PRIVATE ENDPOINT"), ("trial", True),
                                   ("trial", 0), ("trial", 1001), ("case", []), ("mode", None)):
                    with self.subTest(key=key, value=value), self.assertRaises(JournalError):
                        journal.start({**base, key: value})
                    self.assertEqual(path.read_bytes(), before)
                    self.assertIsNone(journal.document["inflight"])
                    self.assertNotIn(b"PRIVATE", path.read_bytes())
                valid = journal.marker("localized_bug", 1, "baseline", receipt["identity"])
                journal.start(valid)
                valid["case"] = "PRIVATE MUTATION"
                journal.complete(receipt)
                self.assertNotIn(b"PRIVATE", path.read_bytes())
                receipt["trace"]["outcome"]["verified"] = False
                self.assertTrue(journal.runs[0]["trace"]["outcome"]["verified"])


if __name__ == "__main__":
    unittest.main()
