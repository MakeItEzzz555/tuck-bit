#!/usr/bin/env python3
"""Repeat a public, fixed task bundle in disposable Git worktrees (NO AI calls).

This is an OFFLINE HARNESS SELF-TEST, not a Codex/Claude benchmark.
Only built-in deterministic task adapters are allowed. No manifest shell execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from trace_profiler import profile

MAX_BUNDLE_BYTES = 65536
MAX_TASKS = 20
TASK_ID = re.compile(r"^[a-z][a-z0-9-]{1,60}$")
ADAPTERS = {"sort_lines", "trim_and_upper"}
CHECKS = ("expected_output", "source_unchanged", "clean_tracked_files")
ORDER = ("baseline", "tuckbit")

class BundleError(ValueError):
    pass

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(bundle):
    return json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def git(cwd, *args):
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                            text=True, timeout=20)
    if result.returncode:
        raise BundleError(f"Git {args[0]} failed; sanitized stderr category: git_exit_{result.returncode}")
    return result.stdout.strip()

def load_bundle(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BUNDLE_BYTES:
        raise BundleError("Bundle must be a small regular JSON file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise BundleError("Invalid JSON task bundle") from exc
    validate_bundle(data)
    return data

def validate_bundle(data):
    fields = {"schema", "bundle_id", "version", "kind", "repetitions", "budget",
              "mandatory_checks", "tasks"}
    if not isinstance(data, dict) or set(data) != fields:
        raise BundleError("Unexpected or missing bundle fields")
    if data["schema"] != 1 or data["kind"] != "offline_fixture_only":
        raise BundleError("Only schema=1 offline fixtures are supported")
    for key in ("bundle_id", "version"):
        if not isinstance(data[key], str) or len(data[key]) > 70 or not TASK_ID.fullmatch(data[key]):
            raise BundleError(f"Invalid {key}")
    if type(data["repetitions"]) is not int or not 1 <= data["repetitions"] <= 10:
        raise BundleError("Repetitions must be 1..10")
    budget = data["budget"]
    if not isinstance(budget, dict) or set(budget) != {"max_wall_ms", "max_operations"}:
        raise BundleError("Budget needs max_wall_ms and max_operations")
    if (type(budget["max_wall_ms"]) is not int or not 10 <= budget["max_wall_ms"] <= 120000
            or type(budget["max_operations"]) is not int or not 3 <= budget["max_operations"] <= 100):
        raise BundleError("Invalid bounded budget")
    checks = data["mandatory_checks"]
    if not isinstance(checks, list) or set(checks) != set(CHECKS) or len(checks) != len(CHECKS):
        raise BundleError("All mandatory checks must be included exactly once")
    tasks = data["tasks"]
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_TASKS:
        raise BundleError("Need 1..20 public fixture tasks")
    seen = set()
    for t in tasks:
        if not isinstance(t, dict) or set(t) != {"id", "adapter", "input", "expected"}:
            raise BundleError("Task fields: id, adapter, input, expected")
        if not isinstance(t["id"], str) or not TASK_ID.fullmatch(t["id"]) or t["id"] in seen:
            raise BundleError("Invalid or duplicate task id")
        seen.add(t["id"])
        if t["adapter"] not in ADAPTERS:
            raise BundleError("Unsupported task adapter: never execute arbitrary commands")
        for key in ("input", "expected"):
            if not isinstance(t[key], str) or len(t[key].encode("utf-8")) > 8192:
                raise BundleError("Task fixture content must be short UTF-8 text")

def prepare_repository(folder, bundle):
    seed = folder / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    for task in bundle["tasks"]:
        dst = seed / "tasks" / task["id"]
        dst.mkdir(parents=True)
        (dst / "input.txt").write_text(task["input"], encoding="utf-8")
        (dst / "expected.txt").write_text(task["expected"], encoding="utf-8")
    git(seed, "add", "--", "tasks")
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "TuckBit Fixture",
        "GIT_COMMITTER_NAME": "TuckBit Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+0000",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+0000",
    })
    result = subprocess.run(["git", "-C", str(seed), "-c", "commit.gpgsign=false",
                             "commit", "-q", "-m", "Pinned public offline fixture"],
                            capture_output=True, text=True, env=env, timeout=20)
    if result.returncode:
        raise BundleError("Could not commit disposable fixture")
    start_commit = git(seed, "rev-parse", "HEAD")
    tree_hash = git(seed, "rev-parse", "HEAD^{tree}")
    return seed, start_commit, tree_hash

def event(category, content, operation):
    data = content.encode("utf-8")
    return {"category": category, "role": "root",
            "result_bytes": len(data),
            "operation_sha256": sha(operation.encode()),
            "result_sha256": sha(data)}

def run_adapter(worktree, task):
    original = (worktree / "tasks" / task["id"] / "input.txt").read_text(encoding="utf-8")
    events = [event("tool_read", original, "read-input:" + task["id"])]
    if task["adapter"] == "sort_lines":
        result = "".join(x + "\n" for x in sorted(original.splitlines()))
    elif task["adapter"] == "trim_and_upper":
        result = "".join(line.strip().upper() + "\n" for line in original.splitlines())
    else:
        raise BundleError("Adapter unavailable")
    (worktree / "tasks" / task["id"] / "result.txt").write_text(result, encoding="utf-8")
    events.append(event("tool_write", result, "write-result:" + task["id"]))
    return original, result, events

def trial(seed, start_commit, bundle, task, repetition, treatment, root):
    # All trial worktrees attach ONLY to a temporary fixture repo; never the user's Git checkout.
    name = f"{task['id']}-{repetition}-{treatment}"
    dest = root / name
    git(seed, "worktree", "add", "--quiet", "--detach", str(dest), start_commit)
    try:
        begun = time.perf_counter_ns()
        original, result, events = run_adapter(dest, task)
        checks = {
            "expected_output": result == (dest / "tasks" / task["id"] / "expected.txt").read_text(encoding="utf-8"),
            "source_unchanged": original == (dest / "tasks" / task["id"] / "input.txt").read_text(encoding="utf-8"),
            "clean_tracked_files": not bool(git(dest, "status", "--porcelain", "--untracked-files=no"))
        }
        events.append(event("test", str(checks), "mandatory-checks:" + task["id"]))
        wall_ms = (time.perf_counter_ns() - begun) / 1_000_000
        checks["within_wall_budget"] = wall_ms <= bundle["budget"]["max_wall_ms"]
        checks["within_operation_budget"] = len(events) <= bundle["budget"]["max_operations"]
        passed = all(checks.values())
        trace = {"schema": 1, "events": events, "outcome": {
            "verified": passed,
            "acceptance_checks_passed": all(checks[k] for k in CHECKS)}}
        summary = profile(trace)
        return {
            "task_id": task["id"], "repetition": repetition, "treatment": treatment,
            "starting_commit": git(dest, "rev-parse", "HEAD"),
            "check_results": checks, "passed": passed,
            "tool_operations": len(events),
            "wall_ms": round(wall_ms, 3),
            "reported_tokens": None,
            "human_review_ms": None, "human_editing_ms": None,
            "re_runs": 0,
            "profiler": {
                "event_count": summary["event_count"],
                "total_result_bytes": summary["total_result_bytes"],
                "potential_identical_repeats": summary["potential_identical_repeats"]
            }
        }
    finally:
        git(seed, "worktree", "remove", "--force", str(dest))

def execute(bundle):
    validate_bundle(bundle)
    runs = []
    with tempfile.TemporaryDirectory(prefix="tuckbit-offline-bundle-") as name:
        folder = Path(name)
        seed, start, tree = prepare_repository(folder, bundle)
        root = folder / "trials"
        root.mkdir()
        for repetition in range(1, bundle["repetitions"]+1):
            # Counterbalance execution order, while preserving per-trial starting state.
            condition_order = ORDER if repetition % 2 else ORDER[::-1]
            for task in bundle["tasks"]:
                for condition in condition_order:
                    runs.append(trial(seed, start, bundle, task, repetition, condition, root))
    by_task = {}
    for task in bundle["tasks"]:
        rows = [r for r in runs if r["task_id"] == task["id"]]
        by_task[task["id"]] = {
            condition: {
                "passes": sum(r["passed"] for r in rows if r["treatment"] == condition),
                "failures": sum(not r["passed"] for r in rows if r["treatment"] == condition),
                "trials": sum(r["treatment"] == condition for r in rows),
                "pass_rate": sum(r["passed"] for r in rows if r["treatment"] == condition) /
                             sum(r["treatment"] == condition for r in rows),
                "wall_ms_distribution": [r["wall_ms"] for r in rows if r["treatment"] == condition],
                "tool_call_distribution": [r["tool_operations"] for r in rows if r["treatment"] == condition],
            } for condition in ORDER
        }
    return {
        "schema": 1, "kind": "offline_harness_self_test_NOT_agent_benchmark",
        "bundle_id": bundle["bundle_id"], "version": bundle["version"],
        "bundle_sha256": sha(canonical(bundle)), "starting_commit": start,
        "fixture_tree_sha": tree, "starting_state_restored_per_trial": True,
        "execution_order": "baseline-first on odd repetitions, tuckbit-first on even repetitions",
        "conditions_are_simulated": True, "model": None, "model_version": None,
        "python_version": sys.version.split()[0],
        "git_version": subprocess.run(["git", "--version"], capture_output=True,
                                      text=True, timeout=5).stdout.strip(),
        "budget": bundle["budget"], "mandatory_checks": bundle["mandatory_checks"],
        "records": runs, "by_task": by_task,
        "total_passes": sum(r["passed"] for r in runs),
        "total_trials": len(runs),
        "claim_of_model_efficiency": False,
        "limitations": [
            "Both conditions execute identical deterministic Python adapters; no AI coding agents are invoked.",
            "Token usage, model cost, human review, and human editing time are unavailable, not zero.",
            "Pass distributions validate the harness, not TuckBit's performance.",
            "A separate approved native agent adapter and real repeated trials are needed for efficiency claims."
        ]
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", required=True, help="Explicit public offline-fixture bundle")
    p.add_argument("--output", help="New JSON report file; refuse overwrite")
    args = p.parse_args()
    try:
        bundle = load_bundle(args.bundle)
        report = execute(bundle)
        result = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            out = Path(args.output).expanduser()
            if out.exists() or out.is_symlink():
                raise BundleError("Output exists; refusing overwrite")
            with out.open("x", encoding="utf-8") as fp:
                os.fchmod(fp.fileno(), 0o600)
                fp.write(result)
            print(f"Produced offline fixture report: {out} ({report['total_passes']}/{report['total_trials']} passes)")
        else:
            print(result, end="")
        return 0 if report["total_passes"] == report["total_trials"] else 1
    except (BundleError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Benchmark runner error: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
