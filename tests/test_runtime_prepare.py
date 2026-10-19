import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import execution_state as state
import runtime_prepare
from v4_experiments import envelope


class RuntimePrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "module.py").write_text("def query():\n    return 1\n")
        self.value = envelope(self.root)

    def receipt(self, prepared, result="passed"):
        return {"check": "independent acceptance", "result": result, "binding": self.value["binding"],
                "packet_sha256": prepared["packet"]["sha256"], "evidence_sha256": "f" * 64}

    def test_contract_permissions_and_unknown_activation_preserved(self):
        prepared = runtime_prepare.prepare(self.value)
        self.assertEqual(prepared["contract"]["task_input"], self.value["task"])
        self.assertFalse(prepared["permissions_granted"])
        self.assertFalse(prepared["tools_executed"])
        self.assertIsNone(prepared["activation"]["tool_invoked"])
        self.assertEqual(set(prepared["stage_ns"]), {"adaptive", "routing", "context"})
        self.assertFalse(runtime_prepare.finalize(prepared, [], "continue")["all_required_checks_passed"])
        final = runtime_prepare.finalize(prepared, [self.receipt(prepared)], "done")
        self.assertTrue(final["all_required_checks_passed"])

    def test_failure_and_missing_checks_cannot_succeed(self):
        prepared = runtime_prepare.prepare(self.value)
        for status in ("failed", "blocked", "skipped"):
            self.assertFalse(runtime_prepare.finalize(prepared, [self.receipt(prepared, status)], "continue")["all_required_checks_passed"])
        self.value["task"]["checks"] = []
        with self.assertRaises(ValueError):
            runtime_prepare.finalize(runtime_prepare.prepare(self.value), [], "done")

    def test_stale_source_and_unbound_receipts_rejected(self):
        prepared = runtime_prepare.prepare(self.value)
        invalid = self.receipt(prepared)
        invalid["packet_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            runtime_prepare.finalize(prepared, [invalid], "done")
        (self.root / "module.py").write_text("def query():\n    return 2\n")
        with self.assertRaises(ValueError):
            runtime_prepare.finalize(prepared, [self.receipt(prepared)], "done")

    def test_tampering_and_unknown_fields_refused(self):
        for key, value in (("secret", "credential"), ("permission_grants", ["shell"])):
            with self.assertRaises(ValueError):
                runtime_prepare.prepare({**self.value, key: value})
        prepared = runtime_prepare.prepare(self.value)
        prepared["contract"]["required_checks_verbatim"] = []
        with self.assertRaises(ValueError):
            runtime_prepare.finalize(prepared, [], "done")

    def test_explicit_registry_freshness_revocation_and_no_execution(self):
        tools = self.root / "tools.json"
        tools.write_text(json.dumps({"tools": [{"name": "sqlite-query", "provider": "local", "description": "sqlite query validation"}]}))
        self.value["registry"] = {"roots": [], "tools_file": str(tools)}
        prepared = runtime_prepare.prepare(self.value)
        self.assertEqual(prepared["workflow"]["routing"]["registry_freshness"], "fresh_explicit_sources")
        self.assertTrue(prepared["activation"]["recommended"])
        import capability_registry
        snapshot = capability_registry.build([], tools, **self.value["binding"])
        tools.write_text('{"tools": []}')
        self.value["registry"]["snapshot"] = snapshot
        result = runtime_prepare.prepare(self.value)
        self.assertEqual(result["workflow"]["routing"]["registry_freshness"], "stale")
        self.assertFalse(result["activation"]["recommended"])

    def test_explicit_corrupt_registry_snapshot_is_not_silently_rebuilt(self):
        for invalid in ({}, None, [], {"schema": True}):
            self.value["registry"] = {"roots": [], "snapshot": invalid}
            with self.assertRaises(ValueError):
                runtime_prepare.prepare(self.value)

    def test_source_escape_symlink_and_secret_rejected(self):
        for path in ("../outside.py", ".env", "credentials.json"):
            value = copy.deepcopy(self.value)
            value["source_ranges"][0]["path"] = path
            with self.assertRaises((ValueError, OSError)):
                runtime_prepare.prepare(value)
        (self.root / "linked.py").symlink_to(self.root / "module.py")
        self.value["source_ranges"][0]["path"] = "linked.py"
        with self.assertRaises(ValueError):
            runtime_prepare.prepare(self.value)

    def test_cli_private_output_refuses_overwrite(self):
        source, output = self.root / "input.json", self.root / "prepared.json"
        source.write_text(json.dumps(self.value))
        args = [sys.executable, str(ROOT / "scripts/runtime_prepare.py"), "prepare", str(source), "--output", str(output)]
        first = subprocess.run(args, capture_output=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)
        self.assertNotIn(b"def query", first.stdout)


if __name__ == "__main__":
    unittest.main()
