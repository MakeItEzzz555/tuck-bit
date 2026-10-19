#!/usr/bin/env python3
"""Bounded V4 plans and private receipts; native execution fails closed without read isolation.

Reuses V3's event streamer, numeric profiler and atomic journal lifecycle. This
module never discovers sessions, private host instructions or global catalogs.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import random
import shutil
import stat
import sys
import tempfile
import time

from benchmark_journal import BenchmarkJournal, JournalError
from benchmark_runner import (canonical_skill_fingerprint, fingerprint, native_run,
                              literal_command, trusted_executable,
                              treatment_fingerprint)
from provider_events import codex_trace
from trace_profiler import profile, ProfileError
import runtime_prepare
import v4_isolation

ROOT = Path(__file__).resolve().parents[1]
DIGEST = re.compile(r"[0-9a-f]{64}")
IDENTITY = {"task", "source", "dependencies", "environment", "model", "client", "runtime", "permissions", "treatment", "configuration"}
METRICS = {"wall_ms", "initialization_ms", "agent_ms", "verification_ms", "input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "tool_invocations", "model_turns", "model_calls", "instruction_reads", "plan_reads", "unsafe_attempts", "unclassified_commands", "checkpoint_ms", "context_bytes", "truncations", "delegation_ms", "batch_setup_ms"}
METRIC_SOURCES = {"monotonic_clock", "public_provider_events", "successful_literal_read", "command_policy_observer", "consolidated_launcher", "model_free_fixture", "unavailable"}
LIMITATIONS = ["Public events cannot prove adherence to every skill instruction.",
               "Filesystem write confinement does not establish host read isolation.",
               "Missing counters stay unknown; no private reasoning is inferred."]
CONTROL_VARIANTS={'correct','wrong','incomplete','partial_activation','missing_activation','unclassified','unknown_tool'}


def corpus():
    import v4_corpus
    return v4_corpus


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**15


def _marker(value):
    if (not isinstance(value, dict) or set(value) != {"case", "trial", "mode", "identity"}
            or not isinstance(value["case"], str) or re.fullmatch(r"D[0-9]{2}[-_][A-Za-z0-9_-]+", value["case"]) is None
            or value["mode"] not in ("A", "B", "C", "D")
            or type(value["trial"]) is not int or not 1 <= value["trial"] <= 1000
            or not isinstance(value["identity"], dict) or set(value["identity"]) != IDENTITY
            or any(not isinstance(v, str) or DIGEST.fullmatch(v) is None for v in value["identity"].values())):
        raise JournalError("Invalid V4 identity marker")


def validate_receipt(value):
    fields = {"schema", "case", "trial", "mode", "identity", "domain", "complexity", "observation_source", "accepted", "activation_qualified", "comparison_eligible", "validation_complete", "isolation_verified", "safety_violations", "status", "metrics", "output_sha256", "grade_sha256", "failure_categories"}
    if not isinstance(value, dict) or set(value) != fields or value["schema"] != 4:
        raise JournalError("Invalid V4 receipt fields")
    _marker({k: value[k] for k in ("case", "trial", "mode", "identity")})
    if (value["domain"] not in {f"D{n:02}" for n in range(1, 21)} or value["complexity"] not in {"small", "medium", "complex"}
            or value["observation_source"] not in {"native_public_events", "model_free_fixture"}
            or value["status"] not in {"accepted", "rejected", "timeout", "incomplete", "provider_error"}
            or any(type(value[k]) is not bool for k in ("accepted", "activation_qualified", "comparison_eligible", "validation_complete", "isolation_verified"))
            or type(value["safety_violations"]) is not int or not 0 <= value["safety_violations"] <= 100000
            or any(not isinstance(value[k], str) or DIGEST.fullmatch(value[k]) is None for k in ("output_sha256", "grade_sha256"))):
        raise JournalError("Invalid V4 receipt values")
    allowed_failures = {"activation_unverified", "baseline_contamination", "missing_validation", "task_failed", "tool_policy", "source_changed", "treatment_changed", "timeout", "provider_error", "incomplete_turn", "isolation_unverified", "synthetic_evidence", "grader_limitation", "policy_unverified"}
    if (not isinstance(value["failure_categories"], list) or len(value["failure_categories"]) != len(set(value["failure_categories"]))
            or any(k not in allowed_failures for k in value["failure_categories"])):
        raise JournalError("Unexpected failure category")
    if not isinstance(value["metrics"], dict) or set(value["metrics"]) != METRICS:
        raise JournalError("Missing metric provenance")
    for metric in value["metrics"].values():
        if (not isinstance(metric, dict) or set(metric) != {"value", "source", "status"}
                or metric["source"] not in METRIC_SOURCES or metric["status"] not in {"measured", "unknown"}
                or (metric["value"] is None) != (metric["status"] == "unknown")
                or metric["value"] is not None and not _number(metric["value"])
                or (metric["value"] is None) != (metric["source"] == "unavailable")):
            raise JournalError("Invalid metric/provenance")
    eligible = (value["accepted"] and value["activation_qualified"] and value["validation_complete"]
                and value["isolation_verified"] and value["safety_violations"] == 0
                and value["observation_source"] == "native_public_events"
                and value['metrics']['unclassified_commands']['value'] == 0)
    if (value["comparison_eligible"] != eligible
            or value["accepted"] and (not value["validation_complete"] or value["safety_violations"] or value["status"] != "accepted")
            or (value["status"] == "accepted") != value["accepted"]
            or value["comparison_eligible"] and value["metrics"]["wall_ms"]["value"] is None):
        raise JournalError("Receipt eligibility contradicts evidence")
    return value


class V4Journal(BenchmarkJournal):
    """V4 schema adapter over the V3 locking, atomic storage and resume protocol."""
    validate_receipt = staticmethod(validate_receipt)
    def __init__(self, path, *args, **kwargs):
        from execution_state import symlink
        target = Path(path).expanduser().absolute()
        if ".." in target.parts or any(symlink(p) for p in (target, *target.parents)):
            raise JournalError("Journal symlink ancestry or traversal refused")
        super().__init__(target, *args, **kwargs)

    def _validate(self):
        doc = self.document
        if (not isinstance(doc, dict) or set(doc) != {"schema", "run_sha256", "runs", "inflight", "interrupted", "order"}
                or type(doc["schema"]) is not int or doc["schema"] != 1 or not isinstance(doc["run_sha256"], str) or not DIGEST.fullmatch(doc["run_sha256"])
                or any(not isinstance(doc[k], list) or len(doc[k]) > 1000 for k in ("runs", "interrupted", "order"))):
            raise JournalError("Invalid V4 journal schema")
        keys = []
        for row in doc["runs"]:
            self.validate_receipt(row)
            keys.append((row["case"], row["trial"], row["mode"]))
        for row in doc["interrupted"] + ([doc["inflight"]] if doc["inflight"] is not None else []):
            _marker(row)
            keys.append((row["case"], row["trial"], row["mode"]))
        if len(keys) != len(set(keys)):
            raise JournalError("Duplicate V4 trial slot")
        completed = {(r["case"], r["trial"], r["mode"]): r["identity"] for r in doc["runs"] + doc["interrupted"]}
        ordered = []
        for row in doc["order"]:
            _marker(row)
            key = (row["case"], row["trial"], row["mode"])
            if completed.get(key) != row["identity"]:
                raise JournalError("Inconsistent V4 journal order")
            ordered.append(key)
        if len(ordered) != len(set(ordered)) or set(ordered) != set(completed):
            raise JournalError("Inconsistent V4 completion prefix")

    def marker(self, case, trial, mode, identity):
        value = {"case": case, "trial": trial, "mode": mode, "identity": dict(identity)}
        _marker(value)
        return value

    def start(self, marker):
        self._owned()
        _marker(marker)
        if self.document["inflight"] is not None or self.has(marker):
            raise JournalError("V4 trial already recorded or inflight")
        self.document["inflight"] = json.loads(json.dumps(marker))
        self._save()

    def complete(self, receipt):
        self._owned()
        self.validate_receipt(receipt)
        pending = self.document["inflight"]
        marker = {key: receipt[key] for key in ("case", "trial", "mode", "identity")}
        if pending != marker:
            raise JournalError("V4 completion identity differs from inflight marker")
        self.document["runs"].append(json.loads(json.dumps(receipt)))
        self.document["order"].append(pending)
        self.document["inflight"] = None
        self._save()


def safe_inventory(root, exclude_treatment=False):
    """Hash a bounded exact snapshot, rejecting links, devices and hidden escapes."""
    root = Path(root).absolute()
    from execution_state import symlink
    if ".." in root.parts or any(symlink(p) for p in (root, *root.parents)) or not root.is_dir():
        raise ValueError("Snapshot requires real directory ancestry")
    found, total = {}, 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(parent) / name
            if path.is_symlink():
                raise ValueError("Snapshot symlink refused")
            if exclude_treatment and path == root / ".agents":
                dirs.remove(name)
        for name in files:
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ValueError("Snapshot symlink refused")
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2_000_000:
                raise ValueError("Snapshot requires bounded unlinked regular files")
            if exclude_treatment and relative == "ADAPTER_PLAN.json":
                continue
            total += info.st_size
            if len(found) >= 3000 or total > 32_000_000:
                raise ValueError("Snapshot resource bound exceeded")
            found[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def snapshot(source, destination):
    before = safe_inventory(source)
    destination = Path(destination).absolute()
    from execution_state import symlink
    if ".." in destination.parts or any(symlink(p) for p in (destination, *destination.parents)):
        raise ValueError("Snapshot destination ancestry or traversal refused")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Snapshot destination must be new")
    destination.mkdir(mode=0o700)
    for relative in before:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((Path(source) / relative).read_bytes())
    if safe_inventory(destination) != before or safe_inventory(source) != before:
        raise ValueError("Snapshot source changed during copy")
    return {"source_sha256": fingerprint(before), "files": len(before)}


def plan(case_ids, model=None, timeout=120, trials=1, arms=("A", "B", "C"), run_budget=6, time_budget=720,
         seed=None, mirrored=False):
    manifest = {row["id"]: row for row in corpus().cases()}
    repeated = seed is not None
    if type(mirrored) is not bool or mirrored and not repeated or repeated and (type(seed) is not int or not 0<=seed<2**32):
        raise ValueError('Bounded integer trial seed required')
    if (not isinstance(case_ids,list) or not 1<=len(case_ids)<=2
            or any(not isinstance(name,str) or name not in manifest for name in case_ids) or len(set(case_ids))!=len(case_ids)
            or type(timeout) is not int or not 1<=timeout<=(120 if repeated else 300)
            or type(trials) is not int or not 1<=trials<=(6 if repeated and mirrored else 3 if repeated else 2)
            or tuple(arms) != ("A", "B", "C")
            or type(run_budget) is not int or not 1 <= run_budget <= (18 if repeated else 6)
            or type(time_budget) is not int or not 1 <= time_budget <= (2160 if repeated else 1800)
            or model is not None and (not isinstance(model, str) or re.fullmatch(r"[A-Za-z0-9._:/-]{1,120}", model) is None)):
        raise ValueError("Initial calibration requires 1–2 unique cases, A/B/C and explicit bounded budgets")
    schedule = []
    orders=list(('ABC','BCA','CAB'));random.Random(seed).shuffle(orders)
    if mirrored:
        reverse=list(('CBA','ACB','BAC'));random.Random(seed ^ 0xA5A5).shuffle(reverse);orders+=reverse
    for trial in range(1, trials+1):
        for index, name in enumerate(case_ids):
            order = orders[(trial-1)%len(orders)] if repeated else ("A", "B", "C") if (trial + index) % 2 else ("C", "B", "A")
            schedule.extend({"case": name, "trial": trial, "mode": arm} for arm in order)
    if len(schedule) > run_budget or timeout * len(schedule) > time_budget:
        raise ValueError("Projected native calls/time exceed the declared calibration budget")
    result = {"schema": 4, "execution_performed": False, "planned_runs": len(schedule), "schedule": schedule,
            "model": model, "timeout_seconds": timeout, "run_budget": run_budget, "time_budget_seconds": time_budget,
            "projected_provider_seconds_upper_bound": timeout * len(schedule),
            "token_budget": None, "token_budget_status": "provider does not expose an enforceable hard token cap",
            "native_ready": False, "blocking_gate": "Native execution requires explicit enablement and a current host-read-isolated canary; workspace-write alone is insufficient.",
            "parallel_status": "D requires a supported genuine native delegation transport and reviewed independent ownership; not emulated."}
    if repeated:result.update(seed=seed,mirrored=mirrored,schedule_sha256=fingerprint(schedule),position_balanced=trials in (3,6))
    return result


class PolicyObserver:
    """Static syntax/path evidence only; raw commands and messages never survive."""
    def __init__(self):
        self.unsafe = 0
        self.unclassified = 0
        self.successful_checks = 0
        self.observed_commands = self.classified_commands = 0
        self.successful_commands = self.failed_commands = self.unknown_outcomes = 0
        self.reason_counts = {}

    def _reason(self, reason):
        self.reason_counts[reason] = self.reason_counts.get(reason, 0) + 1

    def __call__(self, item, folder):
        from command_evidence import classify
        if not isinstance(item, dict):
            self.unclassified += 1
            self._reason("unknown_event")
            return
        kind = item.get("type")
        if kind=='unrecognized_public_item':
            self.unclassified+=1;self._reason('unknown_event');return
        if kind in {"mcp_tool_call", "web_search"}:
            self.unsafe += 1  # Core calibration permits only local shell/file work.
            self._reason("prohibited_tool")
        if kind != "command_execution":
            return
        self.observed_commands += 1
        evidence = classify(item.get("command"), folder)
        self.classified_commands += evidence["classified"]
        self.unclassified += not evidence["classified"]
        self.unsafe += evidence["unsafe"]
        self._reason(evidence["reason"])
        code = item.get("exit_code")
        if type(code) is not int:
            self.unknown_outcomes += 1
            self._reason("unknown_outcome")
        else:
            self.successful_commands += code == 0
            self.failed_commands += code != 0
            self.successful_checks += code == 0 and evidence["check"]

    def export(self):
        return {"schema": 1, "observed_commands": self.observed_commands,
                "classified_commands": self.classified_commands, "successful_commands": self.successful_commands,
                "failed_commands": self.failed_commands, "unknown_outcomes": self.unknown_outcomes,
                "unclassified": self.unclassified, "unsafe": self.unsafe,
                "reason_counts": dict(sorted(self.reason_counts.items()))}


def _runtime_identity():
    files = [*sorted((ROOT / "scripts").glob("*.py")), *sorted((ROOT / "evals/v4").rglob("*.json")),
             ROOT/'docs/evaluations/V4_EVALUATION_DESIGN.md']
    files += sorted((ROOT/'evals/v52').glob('*.py'))
    files += sorted((ROOT/'evals/v6').glob('*.json'))
    if (ROOT/'docs/evaluations/V53_EVALUATION_DESIGN.md').exists():
        files.append(ROOT/'docs/evaluations/V53_EVALUATION_DESIGN.md')
    return fingerprint({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


def _metric(value=None, source="unavailable"):
    return {"value": value, "source": source if value is not None else "unavailable",
            "status": "measured" if value is not None else "unknown"}


def _task(case, model):
    return {"host": "codex", "request": case["task"], "model": model,
            "constraints": ["Use only this disposable workspace; preserve host instructions and declared permissions."],
            "checks": ["Independent V4 acceptance grader; preserve all protected files and treatment metadata."],
            "tools": case["permissions"]["allowed_tools"],
            "forbidden_operations": case["permissions"]["forbidden_actions"],
            "complexity": {"small": "fast", "medium": "standard", "complex": "deep"}[case["complexity"]],
            "review_only": not bool(case["editable"])}


def _prepare(case, folder, environment, model, hashes):
    # All arms receive identical explicit user requirements; treatment adds only advice.
    ranges = [{"path": name, "start": 1, "end": min(20, len((folder / name).read_text().splitlines()))}
              for name in sorted(hashes)[:4] if (folder / name).read_text().splitlines()]
    return runtime_prepare.prepare({"task": _task(case, model), "scope": {
        "source_sha256": fingerprint(hashes), "provenance": {"kind": "host_observed", "reference_sha256": case["source_revision"]},
        "repository_files": len(hashes), "changed_files": []},
        "binding": {"revision": fingerprint(hashes), "environment": environment},
        "source_root": str(folder), "source_ranges": ranges})


def validate_context_control(value):
    if (not isinstance(value, dict) or set(value) != {"view", "packet_reads", "skill_reads"}
            or not isinstance(value["view"], str) or value["view"] not in {"full", "compact", "references"}
            or any(type(value[k]) is not int or value[k] not in (1, 2) for k in ("packet_reads", "skill_reads"))):
        raise ValueError("Invalid model-free context control")
    return dict(value)


def execute(case_ids, model, *, journal_path, explicit=False, timeout=120, trials=1, run_budget=6,
            time_budget=720, resume=False, acknowledge_incomplete=False, runner=None, executable="codex", allow_native=False,
            track="v4", study_key=None, bundle_path=None, runtime_archive=None, seed=None, mirrored=False,
            approved_launches=None, benchmark_rerun=0, continue_controls=False, control_variant=None, context_control=None):
    if track not in {"v4", "v5", "v51", "v52"} or track in {"v5","v51","v52"} and (not isinstance(study_key, bytes) or len(study_key) != 32):
        raise ValueError("V5 requires an explicit private 32-byte study key")
    if track=='v52' and seed is None:raise ValueError('V5.2 requires an explicit trial seed')
    if track!='v52' and (seed is not None or mirrored):raise ValueError('Repeated protocol requires V5.2')
    configuration = plan(case_ids, model, timeout, trials, run_budget=run_budget, time_budget=time_budget,seed=seed,mirrored=mirrored)
    if track=='v52':configuration['benchmark_rerun']=benchmark_rerun
    if explicit is not True or not model:
        raise ValueError("Execution requires --execute, explicit model and native/time/run budgets")
    native = runner is None
    if context_control is not None:
        if native or track != 'v52':
            raise ValueError('Context ablations are model-free only')
        configuration['context_control'] = validate_context_control(context_control)
    if control_variant is not None and (native or not isinstance(control_variant,str) or control_variant not in CONTROL_VARIANTS):
        raise ValueError('Invalid model-free client identity')
    if track=='v52':configuration['control_variant']=None if native else control_variant or 'correct'
    if (type(continue_controls) is not bool or native and continue_controls
            or type(benchmark_rerun) is not int or not 0<=benchmark_rerun<=1000):
        raise ValueError('Invalid controlled-failure or rerun metadata')
    if track=='v52' and native and (type(approved_launches) is not int or approved_launches!=configuration['planned_runs']):
        raise ValueError('A separately approved full pilot launch allowance is required; the remaining launch is not used automatically')
    if runner is native_run or native and allow_native is not True:
        raise ValueError(configuration["blocking_gate"])
    setup_start = time.monotonic()
    manifest = {row["id"]: row for row in corpus().cases()}
    bundle = None
    if track in {'v51','v52'}:
        import benchmark_bundle,native_diagnostics
        if not bundle_path or not runtime_archive or run_budget>(18 if track=='v52' else 3) or timeout>120:
            raise ValueError('V5.1 requires a bundle, pinned runtime archive and at most three 120-second launches')
        bundle=benchmark_bundle.verify(bundle_path,executable)
        if bundle['schema']!=(52 if track=='v52' else 51):raise ValueError('Bundle protocol differs from execution track')
        if case_ids!=[bundle['payload']['case']] or model!=bundle['payload']['model']['id']:
            raise ValueError('Task/model differs from pinned bundle')
        if track=='v52' and bundle['payload']['study']!={'seed':seed,'trials':trials,'mirrored':mirrored,'timeout':timeout}:
            raise ValueError('Seed/repetitions/budgets differ from frozen protocol')
        if not benchmark_bundle.reproduce(bundle_path,runtime_archive,executable)['independent_reproduction_passed']:
            raise ValueError('Independent bundle reproduction failed')
        if native:executable=native_diagnostics.resolved_executable(executable)
    preflight = None
    if native:
        validation = corpus().validate_all()
        if validation['graders_validated'] != 60 or not all(c['complexity_qualified'] is True for c in manifest.values()):
            raise ValueError('All 60 qualified reference graders must pass before native execution')
        proofs = [v4_isolation.preflight(executable, writable=writable)
                  for writable in sorted({bool(manifest[name]['editable']) for name in case_ids})]
        if track in {'v51','v52'}:
            startup=native_diagnostics.probe_thread(executable,model)
            if not startup['thread_configuration_ready'] or not startup['model_matches']:
                raise ValueError('Native startup prerequisite failed: '+','.join(startup['diagnostics']['reason_codes']))
        preflight = {'client_version': proofs[0]['client_version'],
                     'policy_sha256': fingerprint([proof['policy_sha256'] for proof in proofs])}
        runner = native_run
    # Injected transports remain model-free self-checks and never qualify native evidence.
    skill = ROOT / "skills/tuck-bit"
    skill_sha = canonical_skill_fingerprint(skill)
    runtime = _runtime_identity()
    if track in {"v5","v51","v52"}:
        runtime = fingerprint({"implementation": runtime, "v5_protocol": hashlib.sha256((ROOT/'docs/evaluations/V5_EVALUATION_DESIGN.md').read_bytes()).hexdigest()})
    bound_runtime = runtime
    environment = fingerprint({"platform": platform.platform(), "python": platform.python_version(),
                               "transport": "native_public_events" if native else "model_free_fixture",
                               "isolation_policy": preflight['policy_sha256'] if preflight else None})
    run_sha = fingerprint({"configuration": configuration, "runtime": runtime, "skill": skill_sha,
                           "cases": [manifest[name] for name in case_ids], "environment": environment,
                           "track": track, "study_namespace": fingerprint(study_key.hex()) if track in {"v5","v51","v52"} else None,
                           "bundle_sha256":bundle['sha256'] if bundle else None})
    batch_setup_ms = (time.monotonic()-setup_start)*1000
    batch_start = time.monotonic()
    if track in {"v5","v51","v52"}:
        import v5_evaluation
    journal_type = benchmark_bundle.V52Journal if track=='v52' else benchmark_bundle.V51Journal if track=='v51' else v5_evaluation.V5Journal if track == "v5" else V4Journal
    with journal_type(journal_path, run_sha, resume, acknowledge_incomplete) as journal:
        for index, slot in enumerate(configuration["schedule"]):
            case = manifest[slot["case"]]
            identity = {"task": fingerprint(_task(case, model)), "source": case["source_revision"],
                        "dependencies": case["dependency_fingerprint"], "environment": environment,
                        "model": fingerprint(model), "client": fingerprint(preflight['client_version'] if preflight else "injected-model-free-transport"),
                        "runtime": runtime, "permissions": fingerprint(case["permissions"]),
                        "treatment": fingerprint({"mode": slot["mode"], "skill": skill_sha if slot["mode"] != "A" else None}),
                        "configuration": fingerprint({'plan':configuration,'bundle_sha256':bundle['sha256']}) if bundle else fingerprint(configuration)}
            if track=='v52':identity['treatment']=bundle['payload']['treatments'][slot['mode']]
            marker = journal.marker(**slot, identity=identity)
            if journal.check_slot(marker, index):
                continue
            if time.monotonic() - batch_start + timeout > time_budget:
                break
            journal.start(marker)
            started = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="tuckbit-v4-private-", dir="/private/tmp" if native else Path(tempfile.gettempdir()).resolve()) as temp:
                folder = Path(temp)
                if bundle:benchmark_bundle.stage(bundle_path,folder,executable)
                else:corpus().materialize(case["id"], folder)
                original = safe_inventory(folder)
                if original != case["source_hashes"]:
                    raise JournalError("Corpus source fingerprint differs from manifest")
                prompt = json.dumps(_task(case, model), sort_keys=True)
                if slot["mode"] != "A":
                    target = folder / ".agents/skills/tuck-bit"
                    target.parent.mkdir(parents=True)
                    shutil.copytree(skill, target)
                    if canonical_skill_fingerprint(target) != skill_sha:
                        raise JournalError("Skill changed while staging")
                    prompt += '\n'+(benchmark_bundle.ACTIVATION_REQUEST if track=='v52' else 'Apply $tuck-bit; explicitly read .agents/skills/tuck-bit/SKILL.md.')
                prepared = None
                preparation_ms = 0
                if slot["mode"] == "C":
                    prepare_started=time.monotonic()
                    prepared = _prepare(case, folder, environment, model, original)
                    delivered = runtime_prepare.delivery(prepared, context_control['view']) if context_control else prepared
                    if context_control:runtime_prepare.validate_delivery(delivered, prepared, context_control['view'])
                    (folder / "ADAPTER_PLAN.json").write_text(json.dumps(delivered))
                    prompt += '\n'+(benchmark_bundle.PREPARATION_REQUEST if track=='v52' else 'Read and follow ADAPTER_PLAN.json; advice grants no permissions.')
                    preparation_ms=(time.monotonic()-prepare_started)*1000
                treatment_before = treatment_fingerprint(folder)
                initialization_ms = (time.monotonic() - started) * 1000
                command = [executable, "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--json", "--sandbox",
                           "workspace-write" if case["editable"] else "read-only", "--model", model, "-C", str(folder), "-"]
                if native:
                    command = [executable, 'exec', '--strict-config', '--ephemeral', '--ignore-user-config',
                               '--skip-git-repo-check', '--json', *v4_isolation.arguments(bool(case['editable'])),
                               '--model', model, '-C', str(folder), '-']
                    if bundle:command[2:2]=['-c','model_reasoning_effort="low"']
                observer = PolicyObserver()
                telemetry = None
                if track in {"v5","v51","v52"}:
                    from execution_events import Observer
                    telemetry = Observer(study_key, "native_public_events" if native else "controlled_public_events")
                agent_start = time.monotonic()
                arguments = {"observer": observer}
                if telemetry is not None:
                    arguments["execution_observer"] = telemetry
                if bundle:arguments['reproducible']=True
                result = runner(command, prompt, timeout, case["id"], **arguments)
                if track=='v52' and not native and result.get('control_variant')!=configuration['control_variant']:
                    raise JournalError('Executed controlled client differs from the pinned trial configuration')
                if context_control is not None and result.get('context_control') != context_control:
                    raise JournalError('Executed context control differs from the pinned configuration')
                agent_ms = (time.monotonic() - agent_start) * 1000
                grading_start = time.monotonic()
                failures = set() if native else {"synthetic_evidence", "isolation_unverified"}
                try:
                    after = safe_inventory(folder, exclude_treatment=True)
                    safety = sum(after.get(name) != digest for name, digest in original.items() if name not in case["editable"])
                    safety += len(set(after) - set(original)) + len(set(original) - set(after))
                    safety += int(treatment_fingerprint(folder) != treatment_before)
                except (ValueError, OSError):
                    after, safety = {}, 1
                safety += max(observer.unsafe, result.get('violations', 0))
                grading = corpus().grade(case["id"], folder, result.get("final_text", ""))
                safety += grading.get("safety_violations", 0)
                if grading.get('limited'):
                    failures.add('grader_limitation')
                if observer.unclassified or track=='v52' and observer.unknown_outcomes:
                    failures.add('policy_unverified')
                activation = result.get("activation_evidence", {})
                skill_read = result.get("skill_read") is True and type(activation.get("skill_reads")) is int and activation["skill_reads"] > 0
                plan_read = result.get("plan_read") is True and type(activation.get("plan_reads")) is int and activation["plan_reads"] > 0
                execution=telemetry.export(result.get('ok') is True) if telemetry is not None else None
                instruction_delivery=None
                if track=='v52':
                    def delivered(name):
                        target=folder/name
                        if not target.is_file():return False
                        expected=hashlib.sha256(target.read_bytes()).hexdigest()
                        return any(c['success'] is True and c['evidence'] and c['evidence']['source']==telemetry.opaque(name)
                            and c['evidence']['delivered'] and c['evidence']['content']==expected
                            and c['evidence']['revision']==expected for c in execution['calls'])
                    instruction_delivery=delivered('.agents/skills/tuck-bit/SKILL.md')
                    skill_read=skill_read if slot['mode']=='A' else instruction_delivery
                    plan_read=delivered('ADAPTER_PLAN.json')
                qualified = not skill_read if slot["mode"] == "A" else skill_read and (slot["mode"] != "C" or plan_read)
                if slot["mode"] == "A" and (skill_read or plan_read):
                    qualified = False
                    failures.add("baseline_contamination")
                if not qualified:
                    failures.add("activation_unverified")
                validation_complete = grading.get("accepted") is True and bool(grading.get("checks"))
                checkpoint_ms = None
                if prepared is not None and validation_complete and not safety:
                    check_start = time.monotonic()
                    final_prepared = _prepare(case, folder, environment, model, after)
                    packet = final_prepared["packet"]
                    validations = [{"check": check, "result": "passed", "binding": packet["binding"],
                                    "packet_sha256": packet["sha256"], "evidence_sha256": fingerprint(grading)}
                                   for check in final_prepared["contract"]["required_checks_verbatim"]]
                    checkpoint = runtime_prepare.finalize(final_prepared, validations, "Return the independently graded receipt.")
                    validation_complete &= checkpoint.get("all_required_checks_passed") is True
                    checkpoint_ms = (time.monotonic() - check_start) * 1000
                if not validation_complete:
                    failures.add("missing_validation")
                if safety:
                    failures.add("tool_policy")
                accepted = result.get("ok") is True and validation_complete and not safety
                try:
                    imported = profile(codex_trace(result.get("events", []), accepted, accepted))
                    counts = imported["reported_metrics"]
                except (ProfileError, ValueError, TypeError):
                    counts, accepted = {}, False
                    failures.add("provider_error")
                if not accepted:
                    failures.add("task_failed")
                failures.update(k for k in result.get("failure_categories", []) if k in {"timeout", "provider_error", "incomplete_turn"})
                metrics = {name: _metric() for name in METRICS}
                for name, value in {"wall_ms": (time.monotonic()-started)*1000, "initialization_ms": initialization_ms,
                                    "agent_ms": agent_ms, "verification_ms": (time.monotonic()-grading_start)*1000,
                                    "checkpoint_ms": checkpoint_ms, "batch_setup_ms": batch_setup_ms}.items():
                    metrics[name] = _metric(value, "monotonic_clock")
                for name in ("input_tokens", "cached_input_tokens", "output_tokens", "tool_invocations"):
                    metrics[name] = _metric(counts.get(name), "public_provider_events" if native else "model_free_fixture")
                metrics["uncached_input_tokens"] = _metric(imported.get("reported_uncached_input_tokens") if counts else None, "public_provider_events" if native else "model_free_fixture")
                metrics["model_turns"] = _metric(sum(event.get("type") == "turn.completed" for event in result.get("events", [])) if counts else None, "public_provider_events" if native else "model_free_fixture")
                metrics["instruction_reads"] = _metric(activation.get("skill_reads"), "successful_literal_read" if native else "model_free_fixture")
                metrics["plan_reads"] = _metric(activation.get("plan_reads"), "successful_literal_read" if native else "model_free_fixture")
                metrics["unsafe_attempts"] = _metric(observer.unsafe, "command_policy_observer")
                metrics["unclassified_commands"] = _metric(observer.unclassified+(observer.unknown_outcomes if track=='v52' else 0), "command_policy_observer")
                status = "accepted" if accepted else "timeout" if "timeout" in failures else "provider_error" if "provider_error" in failures else "incomplete" if "incomplete_turn" in failures else "rejected"
                receipt = {"schema": 4, **marker, "domain": case["domain"], "complexity": case["complexity"],
                           "observation_source": "native_public_events" if native else "model_free_fixture", "accepted": bool(accepted),
                           "activation_qualified": bool(qualified), "comparison_eligible": bool(native and accepted and qualified and not safety and metrics['unclassified_commands']['value']==0),
                           "validation_complete": bool(validation_complete), "isolation_verified": native,
                           "safety_violations": safety, "status": status, "metrics": metrics,
                           "output_sha256": fingerprint(after), "grade_sha256": fingerprint(grading),
                           "failure_categories": sorted(failures)}
                current_runtime = _runtime_identity()
                if track in {"v5","v51","v52"}:
                    current_runtime = fingerprint({"implementation": current_runtime, "v5_protocol": hashlib.sha256((ROOT/'docs/evaluations/V5_EVALUATION_DESIGN.md').read_bytes()).hexdigest()})
                    receipt = v5_evaluation.enrich(receipt, execution, grading, case,
                                                   fingerprint(study_key.hex()))
                if bundle:
                    if benchmark_bundle.verify(bundle_path,executable)['sha256']!=bundle['sha256']:
                        raise JournalError('Bundle changed mid-trial')
                    receipt.update(schema=51,bundle_sha256=bundle['sha256'],startup_diagnostics=result.get('startup_diagnostics'))
                    if native and receipt['startup_diagnostics'] is None:
                        receipt['comparison_eligible']=False
                        receipt['failure_categories']=sorted(set(receipt['failure_categories'])|{'policy_unverified'})
                    receipt['metrics']['wall_ms']=_metric((time.monotonic()-started)*1000,'monotonic_clock')
                    receipt['metrics']['verification_ms']=_metric((time.monotonic()-grading_start)*1000,'monotonic_clock')
                if track=='v52':
                    effort={name:_metric() for name in v5_evaluation.EFFORT_METRICS}
                    effort.update(preparation_ms=_metric(preparation_ms,'monotonic_clock'),
                        benchmark_reruns={'value':benchmark_rerun,'source':'explicit_protocol','status':'measured'})
                    edits=[c['duration_ms'] for c in execution['calls'] if c['category']=='source_modification']
                    if edits and all(x is not None for x in edits):
                        effort['automated_edit_observed_sum_ms']={'value':sum(edits),'source':'public_event_duration_sum','status':'measured'}
                    block=''.join(s['mode'] for s in configuration['schedule'] if s['trial']==slot['trial'])
                    receipt.update(schema=52,experiment={'seed':seed,'schedule_sha256':configuration['schedule_sha256'],
                        'order_index':index,'block_order':block,'source_before_sha256':fingerprint(original),
                        'workspace_sha256':telemetry.opaque(str(folder)),'benchmark_rerun':benchmark_rerun,
                        'control_variant':configuration['control_variant']},
                        observability={'policy':observer.export(),'activation':{'offered':slot['mode']!='A','selected':None,
                        'instructions_delivered':True if instruction_delivery else None,'instructions_read':True if instruction_delivery else None,
                        'invoked':None,'independently_verified':receipt['accepted'],'consumption':'unobservable'},'effort':effort})
                if current_runtime != bound_runtime:
                    raise JournalError("Runtime implementation changed mid-batch")
                journal.complete(receipt)
                if not continue_controls and (not result.get("ok") or bundle and (not receipt['accepted'] or not receipt['activation_qualified']
                                                        or observer.unclassified or track=='v52' and observer.unknown_outcomes
                                                        or native and not receipt['comparison_eligible'])):
                    break
        return journal.runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--model")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--run-budget", type=int, default=6)
    parser.add_argument("--time-budget", type=int, default=720)
    parser.add_argument("--journal")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--ack-incomplete", action="store_true")
    parser.add_argument("--track", choices=("v4", "v5", "v51", "v52"), default="v4")
    parser.add_argument('--seed',type=int)
    parser.add_argument('--mirrored',action='store_true')
    parser.add_argument('--approved-launches',type=int,help='Separately authorized full V5.2 pilot allowance; never grants approval itself')
    parser.add_argument('--benchmark-rerun',type=int,default=0)
    parser.add_argument('--bundle',help='Required content-addressed source bundle for V5.1')
    parser.add_argument('--runtime-archive',help='Required private pinned runtime archive for V5.1')
    parser.add_argument("--study-key", help="Explicit private file containing 64 hex characters; required for V5 execution")
    args = parser.parse_args()
    names = args.cases or [row["id"] for row in corpus().cases() if row["domain"] in {"D05", "D11"} and row["complexity"] == "small"]
    try:
        if args.execute:
            if not args.journal:
                raise ValueError("Native execution needs an explicit private journal")
            study_key = None
            if args.track in {"v5","v51","v52"}:
                from execution_events import read_study_key
                study_key = read_study_key(args.study_key)
            result = execute(names, args.model, journal_path=args.journal, explicit=True, timeout=args.timeout,
                             trials=args.trials, run_budget=args.run_budget, time_budget=args.time_budget,
                             resume=args.resume, acknowledge_incomplete=args.ack_incomplete, allow_native=True,
                             track=args.track, study_key=study_key,bundle_path=args.bundle,runtime_archive=args.runtime_archive,
                             seed=args.seed,mirrored=args.mirrored,approved_launches=args.approved_launches,benchmark_rerun=args.benchmark_rerun)
        else:
            if args.resume or args.ack_incomplete or args.journal:
                raise ValueError("Resume/journal options require explicit execution")
            result = plan(names, args.model, args.timeout, args.trials, run_budget=args.run_budget, time_budget=args.time_budget,
                          seed=args.seed,mirrored=args.mirrored)
            result["track"] = args.track
            result["context_tool_track_required"] = args.track in {"v5","v51","v52"}
        print(json.dumps(result, indent=2, sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
