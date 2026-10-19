"""Synthetic public-command coverage; no historical command reconstruction or inference."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from command_evidence import REASONS, classify
from v4_runner import PolicyObserver

RG = 'ripgrep (rg) is not installed; rg forms are correctly unclassified without a host-resolved executable'


class V53PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("a", "semi;file", "pipe|file", "a?b", "hash#file"):
            (self.root / name).write_text("safe\n")

    def test_inert_quoted_search_punctuation_is_classified(self):
        for command in (
            "rg -n '(contains|bounds)[.]?' a",
            'rg -n "(contains|bounds)[.]?" a',
            "rg -F 'a && b; c # d > e' a",
            "cat 'semi;file' && cat 'pipe|file'",
            "cat a\\?b",
            "cat 'hash#file'",
            "/bin/sh -lc \"rg -n '(contains|bounds)' a\"",
        ):
            with self.subTest(command=command):
                if "rg " in command and not shutil.which("rg"):
                    self.skipTest(RG)
                self.assertTrue(classify(command, self.root)["classified"])

    def test_known_literal_data_matches_independent_shell_results(self):
        # These fixed test commands contain no input supplied by an agent or external source.
        for command, expected in (
            ("cat 'semi;file' && cat 'pipe|file'", "safe\nsafe\n"),
            ("cat a\\?b", "safe\n"),
            ("printf '%s' '(){}[]|<>*?~;&&#'", "(){}[]|<>*?~;&&#"),
        ):
            self.assertTrue(classify(command, self.root)["classified"])
            observed = subprocess.run(["/bin/sh", "-c", command], cwd=self.root,
                                      capture_output=True, text=True, timeout=5, check=True)
            self.assertEqual(observed.stdout, expected)
            self.assertEqual(observed.stderr, "")

    def test_evaluation_required_syntax_stays_unknown(self):
        for command in (
            "cat a | cat", "cat a > copied", "cat a 2>/dev/null", "cat < a",
            "cat a &", "cat a || cat a", "cat a &&& cat a", "cat a;; cat a",
            "cat a;", "cat a\ncat a", "cat a\rcat a", "cat a # comment",
            "cat $(cat a)", "cat `cat a`", "cat '$HOME'", 'cat "${HOME}"',
            "cat *", "cat a?b", "cat [a]", "cat ~", "(cat a)", "{ cat a; }",
            "find . -name '*.py'", "find . -exec cat '{}' ';'",
            "PATH=/tmp cat a", "/bin/sh -c '/bin/sh -c cat'",
            "python3 -m unittest", "python3 script.py", "python3 -c 'print(1)'",
            "printf -v PATH /tmp && cat a", "printf '%n' PATH && cat a",
            'cat "unterminated', "cat \x00", "x" * 33000,
        ):
            with self.subTest(command=command[:60]):
                self.assertFalse(classify(command, self.root)["classified"])

    def test_quoted_data_never_hides_active_operators_or_forbidden_paths(self):
        (self.root / "link").symlink_to("/etc/passwd")
        os.link(self.root / "a", self.root / "hardlink")
        for command in (
            "cat 'semi;file'; rm a", "cat 'pipe|file' && git gc",
            "cat '../outside'", "cat '/etc/passwd'", "cat 'link'", "cat 'hardlink'",
        ):
            with self.subTest(command=command):
                evidence = classify(command, self.root)
                self.assertFalse(evidence["classified"])
                self.assertTrue(evidence["unsafe"])
        self.assertFalse(classify("cd .; cat a", self.root)["classified"])
        self.assertTrue(classify("cd . && cat 'semi;file'", self.root)["classified"])

    def test_unresolved_search_executable_stays_unclassified(self):
        which = shutil.which
        with mock.patch("benchmark_runner.shutil.which", side_effect=lambda name: None if name == "rg" else which(name)):
            for command in ("rg -n '(contains|bounds)' a", "/bin/sh -lc \"rg -F 'a' a\""):
                with self.subTest(command=command):
                    self.assertFalse(classify(command, self.root)["classified"])
            self.assertTrue(classify("cat 'semi;file'", self.root)["classified"])

    @unittest.skipUnless(shutil.which("rg"), RG)
    def test_public_outcomes_and_sanitized_unknowns_remain_separate(self):
        observer = PolicyObserver()
        for command, outcome in (
            ("rg '(contains|bounds)' a", 1),
            ("cat 'semi;file'", 0),
            ("cat 'PRIVATE_SENTINEL' | cat", 0),
            ("cat a", None),
        ):
            observer({"type": "command_execution", "command": command, "exit_code": outcome}, self.root)
        observer({"type": "unrecognized_public_item"}, self.root)
        result = observer.export()
        self.assertEqual(result["observed_commands"], 4)
        self.assertEqual(result["classified_commands"], 3)
        self.assertEqual(result["failed_commands"], 1)
        self.assertEqual(result["successful_commands"], 2)
        self.assertEqual(result["unknown_outcomes"], 1)
        self.assertEqual(result["unclassified"], 2)
        self.assertEqual(result["reason_counts"]["unsupported_syntax"], 1)
        self.assertLessEqual(set(result["reason_counts"]), REASONS)
        for private in ("PRIVATE_SENTINEL", "semi;file", str(self.root), "contains"):
            self.assertNotIn(private, json.dumps(result))


if __name__ == "__main__":
    unittest.main()
