#!/usr/bin/env python3
"""Explicit, bounded native trials of a repository source investigation (generic example layout)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile

from benchmark import report
from benchmark_journal import BenchmarkJournal
from benchmark_runner import native_run, fingerprint, canonical_skill_fingerprint
from execution_state import binding, packet, regular, write_new
from provider_events import codex_trace
from trace_profiler import profile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PREFIXES = ("Sources/", "Tests/")
SOURCE_NAMES = {"Package.swift", "Package.resolved", "README.md", "AGENTS.md"}
TARGET = "Sources/ExampleApp/Timer/TimerCompletionNotifications.swift"
CALLER = "Sources/ExampleApp/App/ExampleApp.swift"
TASK = """Investigate the current timer notification lifecycle. Can time spent awaiting notification authorization make the eventual notification and sound arrive after the actual countdown deadline? Trace the caller, scheduling and completion sound ownership. Determine whether a defect exists in this source, a minimal correction and a deterministic regression test. Review only: do not change source, tests, settings or permissions, run the app or request authorization. Return only one JSON object: finding (confirmed, absent or uncertain), source_files (repository-relative paths including the coordinator and caller), facts (boolean fields delay_captured_before_authorization, elapsed_authorization_time_deducted, completion_can_delegate_sound_to_late_request), correction (boolean fields preserve_countdown_deadline, recompute_delay_after_authorization, expired_request_must_not_suppress_local_sound), regression (numeric countdown_seconds, authorization_wait_seconds, expected_remaining_seconds, and boolean cover_expired_authorization, cover_cancellation). Derive values from actual source; these field names describe hypotheses, not established facts. Use finding uncertain when evidence is missing."""
BOUNDARY = """Work only with this disposable source snapshot and supplied treatment resources, plus applicable host instructions. No network, credentials, private sessions, agents, background processes, commits, app launches or permission changes. Preserve all source files. You may create private evidence only under .tuck-bit/run/. Use scoped searches and native tools as appropriate. No expensive full build is needed for this read-only investigation. Final conclusions are independently checked; do not claim tests you did not run."""


def response_schema():
    def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    facts={k:{'type':'boolean'} for k in ('delay_captured_before_authorization','elapsed_authorization_time_deducted','completion_can_delegate_sound_to_late_request')}
    fix={k:{'type':'boolean'} for k in ('preserve_countdown_deadline','recompute_delay_after_authorization','expired_request_must_not_suppress_local_sound')}
    regression={k:{'type':'integer'} for k in ('countdown_seconds','authorization_wait_seconds','expected_remaining_seconds')}
    regression.update({k:{'type':'boolean'} for k in ('cover_expired_authorization','cover_cancellation')})
    return obj({'finding':{'type':'string','enum':['confirmed','absent','uncertain']},'source_files':{'type':'array','items':{'type':'string'}},'facts':obj(facts),'correction':obj(fix),'regression':obj(regression)})


def collect(source, revision):
    source = Path(source).absolute()
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != revision:
        raise ValueError("Source revision differs")
    names = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"]).decode().split("\0")
    names = sorted(n for n in names if n in SOURCE_NAMES or n.startswith(SOURCE_PREFIXES))
    if len(names) > 2000:
        raise ValueError("Source inventory exceeds bound")
    files, total = {}, 0
    for name in names:
        path = source / name
        regular(path)
        if not path.is_file() or path.stat().st_size > 1_000_000:
            raise ValueError("Source must be bounded regular files")
        data = path.read_bytes()
        total += len(data)
        if total > 32_000_000:
            raise ValueError("Source snapshot exceeds bound")
        files[name] = data
    if TARGET not in files or "Package.swift" not in files:
        raise ValueError("Not the expected pilot source layout")
    return files


def source_hash(files):
    return fingerprint({name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())})


def same_regular(path, data):
    try:return regular(path).read_bytes()==data
    except (OSError,ValueError):return False


def unchanged(folder, files):
    for name, data in files.items():
        path = folder / name
        if not same_regular(path,data):return False
    allowed = set(files) | {"TASK.json", "EVIDENCE.json", "VALIDATIONS.json", "RESPONSE_SCHEMA.json", "ADAPTIVE_INPUT.json", "ADAPTER_PLAN.json"}
    for parent, dirs, names in os.walk(folder, followlinks=False):
        for name in list(dirs):
            path = Path(parent) / name
            if path.is_symlink():
                return False
            if path in (folder / '.git', folder / '.agents', folder / '.tuck-bit/run'):
                dirs.remove(name)
            elif path.is_relative_to(folder/'.tuck-bit') and path != folder/'.tuck-bit':
                return False
        for name in names:
            if (Path(parent) / name).relative_to(folder).as_posix() not in allowed:
                return False
    return True


def treatment_valid(folder, mode, expected):
    agents=folder/'.agents'
    if mode=='baseline':return not agents.exists() and not agents.is_symlink()
    try:
        if agents.is_symlink() or (agents/'skills').is_symlink() or set(p.name for p in agents.iterdir())!={'skills'}:return False
        if set(p.name for p in (agents/'skills').iterdir())!={'tuck-bit'}:return False
        return canonical_skill_fingerprint(agents/'skills/tuck-bit')==expected
    except (OSError,ValueError):return False


def grade(text, files):
    """Check explicit structured facts, not keyword presence or unreviewed prose."""
    try:
        value = json.loads(text)
        if not isinstance(value, dict) or set(value) != {"finding", "source_files", "facts", "correction", "regression"}:
            return False
        if value['finding'] != 'confirmed' or not isinstance(value['source_files'], list) or len(value['source_files']) > 10:
            return False
        paths = value['source_files']
        if TARGET not in paths or CALLER not in paths or any(not isinstance(p,str) or p not in files for p in paths):
            return False
        expected_facts={'delay_captured_before_authorization':True,'elapsed_authorization_time_deducted':False,
                        'completion_can_delegate_sound_to_late_request':True}
        expected_fix={'preserve_countdown_deadline':True,'recompute_delay_after_authorization':True,
                      'expired_request_must_not_suppress_local_sound':True}
        for field,expected in (('facts',expected_facts),('correction',expected_fix)):
            if not isinstance(value[field],dict) or value[field]!=expected or any(type(v) is not bool for v in value[field].values()):return False
        test=value['regression']
        if not isinstance(test,dict) or set(test)!={'countdown_seconds','authorization_wait_seconds','expected_remaining_seconds','cover_expired_authorization','cover_cancellation'}:return False
        if any(type(test[k]) is not int for k in ('countdown_seconds','authorization_wait_seconds','expected_remaining_seconds')):return False
        return (0<test['authorization_wait_seconds']<test['countdown_seconds']<=1000
                and test['expected_remaining_seconds']==test['countdown_seconds']-test['authorization_wait_seconds']
                and test['cover_expired_authorization'] is True and test['cover_cancellation'] is True)
    except (ValueError, TypeError):
        return False


def validate_workflow(folder, task, revision, environment):
    """Validate actual native-created packet/checkpoint; no self-certified green."""
    from execution_state import load, validate_checkpoint
    run = folder / '.tuck-bit/run'
    try:
        state = load(run / 'checkpoint.json')
        validate_checkpoint(state)
        expected = packet(task, selections((folder/TARGET).read_bytes()), folder, revision, environment,
                          max_chars=state['packet']['excerpt_character_limit'])
        return (state['packet'] == expected and not state['all_required_checks_passed']
                and state['validations'] == [])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def selections(source):
    return [{'path':TARGET,'start':120,'end':min(285,len(source.decode().splitlines()))}]


def oracle(files):
    source=files[TARGET].decode()
    start=source.index('private func schedule(')
    end=source.index('private func cancel(',start)
    body=source[start:end]
    if not (body.index('let request = TimerCompletionNotificationRequest(')<body.index('await client.authorizationStatus()')
            and 'delay: Self.timeInterval(for: remaining)' in body and 'notificationSoundGeneration = generation' in body
            and 'clock.now' not in body):
        raise ValueError('Source no longer matches independently reproduced defect; choose a new pilot')


def execute(source, revision, model, runtime, journal_path, trials=2, timeout=180, resume=False):
    from benchmark_runner import arm_order, failure_categories, numeric_observations
    if type(trials) is not int or trials not in (1,2) or type(timeout) is not int or not 1<=timeout<=180:
        raise ValueError('Native trial budget is out of bounds')
    binding(revision,'0'*64)
    if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,100}',model):raise ValueError('Invalid model ID')
    runtime = regular(runtime)
    files = collect(source, revision)
    oracle(files)
    runtime_bytes=runtime.read_bytes()
    skill_sha=canonical_skill_fingerprint(ROOT/'skills/tuck-bit')
    source_sha = source_hash(files)
    version = subprocess.check_output(['codex','--version'],text=True).strip()
    environment = fingerprint({'platform':platform.platform(),'python':platform.python_version(),
                               'client':version,'flags':['--ephemeral','--ignore-user-config','workspace-write'],
                               'locale':{k:os.environ.get(k) for k in ('LANG','LC_ALL','TZ')}})
    task = {'request':TASK,'host':'codex','model':model,'review_only':True,'checks':[
        'Independently check causal conclusion and source references','Preserve all source files'],
        'constraints':[BOUNDARY], 'forbidden_operations':['source edits','network','credentials','app launch']}
    identity = {'task_sha256':fingerprint(task),'source_sha256':source_sha,
                'environment_sha256':environment,'model_sha256':fingerprint(model),
                'permissions_sha256':fingerprint(BOUNDARY+'workspace-write')}
    helpers={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in
             ('benchmark_runner.py','benchmark.py','benchmark_journal.py','provider_events.py','trace_profiler.py',
              'execution_state.py','plan_task.py','workflow_router.py','capability_registry.py')}
    run_sha = fingerprint({'identity':identity,'runtime':hashlib.sha256(runtime_bytes).hexdigest(),
                          'skill':skill_sha,'helpers':helpers,
                          'code':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          'observer':hashlib.sha256((ROOT/'scripts/benchmark_runner.py').read_bytes()).hexdigest(),
                          'trials':trials,'timeout':timeout,'schedule':'balanced'})
    with BenchmarkJournal(journal_path,run_sha,resume=resume) as journal:
        receipts = journal.runs
        order = [(trial,mode) for trial in range(1,trials+1) for mode in arm_order(trial,'balanced')]
        for index,(trial,mode) in enumerate(order):
            marker=journal.marker('repository_search',trial,mode,identity)
            if journal.check_slot(marker,index):
                continue
            with tempfile.TemporaryDirectory(prefix='tuckbit-v3-repo-') as temporary:
                folder=Path(temporary)
                for name,data in files.items():
                    path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                subprocess.run(['git','init','-q','--template=',str(folder)],check=True,capture_output=True)
                run=folder/'.tuck-bit/run';run.mkdir(parents=True,mode=0o700)
                (folder/'TASK.json').write_text(json.dumps(task))
                (folder/'EVIDENCE.json').write_text(json.dumps(selections(files[TARGET])))
                (folder/'VALIDATIONS.json').write_text('[]')
                (folder/'RESPONSE_SCHEMA.json').write_text(json.dumps(response_schema()))
                adaptive={'task':task,'binding':{'revision':revision,'environment':environment},
                          'scope':{'source_sha256':source_sha,'repository_files':len(files),'changed_files':[],
                                   'provenance':{'kind':'host_observed','reference_sha256':source_sha}}}
                (folder/'ADAPTIVE_INPUT.json').write_text(json.dumps(adaptive))
                prompt=TASK+'\n'+BOUNDARY
                protected={name:(folder/name).read_bytes() for name in ('TASK.json','EVIDENCE.json','VALIDATIONS.json','RESPONSE_SCHEMA.json','ADAPTIVE_INPUT.json')}
                approved=()
                archive=None
                if mode != 'baseline':
                    skill=folder/'.agents/skills/tuck-bit';skill.parent.mkdir(parents=True)
                    shutil.copytree(ROOT/'skills/tuck-bit',skill)
                    prompt+='\nApply the project $tuck-bit skill.'
                treatment=canonical_skill_fingerprint(folder/'.agents/skills/tuck-bit') if mode != 'baseline' else None
                if mode!='baseline' and treatment!=skill_sha:raise ValueError('Canonical skill changed during staging')
                if mode=='adapters':
                    archive=run/'runtime.zip';archive.write_bytes(runtime_bytes);approved=(str(archive),)
                    prompt+=('\nExplicitly enabled local TuckBit runtime: .tuck-bit/run/runtime.zip. Run separate direct commands: '
                             'python3 .tuck-bit/run/runtime.zip adaptive_execution prepare ADAPTIVE_INPUT.json --output .tuck-bit/run/advice.json. Read that advice. '
                             'python3 .tuck-bit/run/runtime.zip plan_task TASK.json --output .tuck-bit/run/contract.json; '
                             'python3 .tuck-bit/run/runtime.zip workflow_router TASK.json --output ADAPTER_PLAN.json. '
                             'Read that ADAPTER_PLAN.json. Then run '
                             f'python3 .tuck-bit/run/runtime.zip execution_state packet TASK.json EVIDENCE.json --root . --revision {revision} --environment {environment} --output .tuck-bit/run/packet.json. '
                             'Use its referenced context for investigation. Before returning, run '
                             f'python3 .tuck-bit/run/runtime.zip execution_state checkpoint .tuck-bit/run/packet.json --root . --revision {revision} --environment {environment} --validations VALIDATIONS.json --next-action Independent-review --output .tuck-bit/run/checkpoint.json. '
                             'Validation receipts are intentionally empty until independent review: do not claim all checks passed. Return only the requested conclusion JSON.')
                journal.start(marker)
                command=['codex','exec','--ephemeral','--ignore-user-config','--json','--sandbox','workspace-write','--model',model,'--output-schema',str(folder/'RESPONSE_SCHEMA.json'),'-C',str(folder),'-']
                result=native_run(command,prompt,timeout,'repository_search',approved_runtime_paths=approved)
                safety=result['violations']+int(not unchanged(folder,files))
                safety+=sum(int(not same_regular(folder/name,data)) for name,data in protected.items())
                if archive is not None:
                    safety+=int(not same_regular(archive,runtime_bytes))
                safety+=int(not treatment_valid(folder,mode,treatment))
                if mode=='baseline' and result['skill_read']:safety+=1
                runtime_counts=result.get('runtime_evidence',{})
                workflow=mode=='adapters' and validate_workflow(folder,task,revision,environment)
                active='none' if mode=='baseline' else 'native_verified' if result['skill_read'] and (
                    mode!='adapters' or workflow and all(runtime_counts.get(k,0)>0 for k in ('plan_task','workflow_router','packet','checkpoint','adaptive_execution'))) else 'unverified'
                accepted=result['ok'] and safety==0 and grade(result['final_text'],files)
                metrics=profile(codex_trace(result['events'],bool(accepted),bool(accepted)))['reported_metrics']
                event={'category':'other','role':'root',**metrics,'duration_ms':result['duration_ms'],'result_bytes':result['result_bytes'],'revision_sha256':source_sha}
                trace={'schema':1,'events':[event],'wall_time_ms':result['duration_ms'],
                       'outcome':{'verified':bool(accepted),'acceptance_checks_passed':bool(accepted)}}
                receipt={**marker,'evidence_kind':'measured','identity':identity,'activation':active,
                         'safety_violations':safety,'trace':trace,
                         'observations':numeric_observations(result),
                         'failure_categories':failure_categories(result,bool(accepted),safety,active)}
                journal.complete(receipt);receipts.append(receipt)
                print(json.dumps({'completed':len(receipts),'accepted':bool(accepted),'activation':active,'workflow_verified':workflow}),flush=True)
                if not result['ok']:break
        return {'schema':1,'pilot':'timer_deadline_example','source_revision':revision,
                'source_sha256':source_sha,'runs':receipts,'report':report(receipts),
                'limitations':['Two partially balanced trials do not establish general efficiency or statistical savings.',
                               'Structured fact grading is task-specific; independent suspended-clock reproduction supplies causal evidence, not general semantic review quality.',
                               'The snapshot contains tracked Sources/Tests and explicit root files; generated graph/build/user state is excluded.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--source');parser.add_argument('--revision');parser.add_argument('--model')
    parser.add_argument('--runtime');parser.add_argument('--journal');parser.add_argument('--resume',action='store_true')
    parser.add_argument('--trials',type=int,choices=(1,2),default=2)
    parser.add_argument('--timeout',type=int,choices=range(1,181),default=180)
    parser.add_argument('--output')
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'execution_performed':False,'pilot':'timer_deadline_example','planned_native_runs':3*args.trials,'maximum_native_seconds':3*args.trials*args.timeout}));return 0
    if not all((args.source,args.revision,args.model,args.runtime,args.journal,args.output)):
        parser.error('Execution requires explicit source/revision/model/runtime/journal/output')
    binding(args.revision,'0'*64)
    if Path(args.output).exists() or Path(args.output).is_symlink():
        parser.error('Output must not exist')
    try:
        value=execute(args.source,args.revision,args.model,args.runtime,args.journal,args.trials,args.timeout,args.resume)
        write_new(args.output,value);return 0
    except (OSError,ValueError,subprocess.SubprocessError):
        print('Repository pilot stopped: invalid environment or incompatible evidence. Private journal retained.');return 2


if __name__=='__main__':
    raise SystemExit(main())
