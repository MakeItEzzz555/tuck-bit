"""Restricted evaluation must agree with the allowed Python execution semantics."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_runner import GradingError, safe_call


class GraderSemanticsTests(unittest.TestCase):
    def test_boolean_operand_values_and_short_circuit(self):
        files = {"p.py": "def choose(a, b):\n    return a and b\n"}
        value = safe_call(files, "p", "choose", [0, True])
        self.assertIs(type(value), int)
        self.assertEqual(value, 0)
        files["p.py"] = "def choose(a, b):\n    return a or (b / 0)\n"
        self.assertIs(safe_call(files, "p", "choose", [True, 1]), True)

    def test_unreachable_local_binding_shadows_import(self):
        files = {"p.py": "from q import f\ndef choose(a):\n    return f(a)\n    f = 0\n",
                 "q.py": "def f(a):\n    return a\n"}
        with self.assertRaises(GradingError):
            safe_call(files, "p", "choose", [1])
        files["p.py"] = "from q import f\ndef choose(a):\n    return f(a)\n    def f(a):\n        return a\n"
        with self.assertRaises(GradingError):
            safe_call(files, "p", "choose", [1])

    def test_only_executed_dependency_edges_are_observed(self):
        files = {"p.py": "from q import f\ndef choose(a):\n    return a\ndef unused(a):\n    return f(a)\n",
                 "q.py": "def f(a):\n    return a\n"}
        observed = set()
        safe_call(files, "p", "choose", [1], call_trace=observed)
        self.assertNotIn(("p", "unused", "q", "f"), observed)
        safe_call(files, "p", "unused", [1], call_trace=observed)
        self.assertIn(("p", "unused", "q", "f"), observed)

    def test_expansion_budget_bounds_acyclic_call_fanout(self):
        source = "def f0(a):\n    return a\n"
        for n in range(1, 16):
            source += f"def f{n}(a):\n    return f{n-1}(a) + f{n-1}(a)\n"
        with self.assertRaisesRegex(GradingError, "budget"):
            safe_call({"p.py": source}, "p", "f15", [1])


if __name__ == "__main__":
    unittest.main()
