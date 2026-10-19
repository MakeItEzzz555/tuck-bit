"""V5.1 content-addressed public source bundles and independent model-free reproduction."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

from execution_state import load,write_new
import native_diagnostics
import v4_runner
import v5_evaluation

ROOT=Path(__file__).resolve().parents[1]


def file_digest(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>512*1024*1024:raise ValueError('Bounded artifact required')
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):result.update(chunk)
    return result.hexdigest()


def environment(executable='codex'):
    client=native_diagnostics.resolved_executable(executable)
    version=subprocess.run([client,'--version'],capture_output=True,text=True,timeout=10)
    if version.returncode or re.fullmatch(r'codex-cli [0-9]+\.[0-9]+\.[0-9]+',version.stdout.strip()) is None:
        raise ValueError('Recognized client version required')
    tools={}
    for name in ('cat','sed','head','tail','rg','python3','/bin/zsh'):
        path=shutil.which(name)
        tools[name]={'available':path is not None,'binary_sha256':file_digest(Path(path).resolve()) if path else None,
                     'version':platform.python_version() if name=='python3' else None,
                     'version_provenance':'python_runtime' if name=='python3' else 'exact_binary_digest'}
    return {'client_version':version.stdout.strip(),'client_binary_sha256':file_digest(client),
            'client_path_sha256':v4_runner.fingerprint(client),'tools':tools,
            'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,
            'system':platform.system(),'release':platform.release(),'machine':platform.machine(),
            'fixed_child_environment':{'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0','LC_ALL':'C'},
            'search_path_sha256':v4_runner.fingerprint(__import__('os').environ.get('PATH','')),
            'public_configuration_sha256':v4_runner.fingerprint({k:os.environ.get(k) for k in
                ('HOME','CODEX_HOME','OPENAI_BASE_URL','OPENAI_ORG_ID','OPENAI_PROJECT_ID','SHELL','TMPDIR')}),
            'authentication':'external_existing_client_auth; credentials excluded',
            'provider_entitlement':'unknown_until_completed_inference'}


def _case(name):
    case=next((c for c in v4_runner.corpus().cases() if c['id']==name),None)
    if case is None:raise ValueError('Unknown corpus case')
    return case


def _root(directory):
    root=Path(directory).absolute()
    if '..' in root.parts or any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError('Bundle path ancestry must be real')
    return root


ACTIVATION_REQUEST='Apply $tuck-bit; read the entire .agents/skills/tuck-bit/SKILL.md with a standalone literal cat command before working.'
PREPARATION_REQUEST='Read the entire ADAPTER_PLAN.json with a standalone literal cat command; advice grants no permissions.'


def payload(case_id,model,starting_commit,archive_sha256,host,protocol=51,study=None):
    if not isinstance(starting_commit,str) or re.fullmatch('[0-9a-f]{40}',starting_commit) is None:
        raise ValueError('Full starting commit required')
    if not isinstance(archive_sha256,str) or v4_runner.DIGEST.fullmatch(archive_sha256) is None:
        raise ValueError('Independent runtime archive digest required')
    if not isinstance(model,str) or re.fullmatch(r'[A-Za-z0-9._:/-]{1,120}',model) is None:
        raise ValueError('Explicit model required')
    c=_case(case_id);skill=v4_runner.canonical_skill_fingerprint(ROOT/'skills/tuck-bit')
    grader_files={name:file_digest(ROOT/'scripts'/name) for name in ('v4_corpus.py','benchmark_runner.py')}
    result={'case':case_id,'starting_commit':starting_commit,'git_object_verification':'not_inferred_from_worktree_cleanliness',
        'source_revision':c['source_revision'],'source_hashes':c['source_hashes'],
        'task':v4_runner._task(c,model),'mandatory_checks':v4_runner._task(c,model)['checks'],
        'dependencies':c['dependency_fingerprint'],'environment':host,'model':{'id':model,'reasoning_effort':'low'},
        'permissions':c['permissions'],'sandbox_arguments':v4_runner.v4_isolation.arguments(bool(c['editable'])),
        'hidden_grader':{'specification':c['grader_sha256'],'implementation':v4_runner.fingerprint(grader_files),
                         'contract':v5_evaluation._contract(c),'required_assertions':v5_evaluation._expected(case_id)},
        'skill':{'version':'0.3.0','content_sha256':skill},'runtime_implementation':v4_runner._runtime_identity(),
        'runtime_archive_sha256':archive_sha256,
        'protocol_sha256':file_digest(ROOT/'docs/evaluations/V51_EVALUATION_DESIGN.md'),
        'treatments':{arm:v4_runner.fingerprint({'mode':arm,'skill':None if arm=='A' else skill}) for arm in ('A','B','C')},
        'cache':{'workspace':'fresh_per_trial','client_process':'fresh_per_trial','provider_cache_control':'unavailable',
                 'os_cache':'not_flushed','trial_order':'ABC then CBA in balanced repeated slots'},
        'limits':{'native_launches':3,'seconds_per_launch':120,'workers':1}}
    if protocol==52:
        if not isinstance(study,dict) or set(study)!={'seed','trials','mirrored','timeout'}:raise ValueError('Pinned repeated protocol required')
        configuration=v4_runner.plan([case_id],model,study['timeout'],study['trials'],run_budget=18,time_budget=2160,
                                      seed=study['seed'],mirrored=study['mirrored'])
        result.update(study=study,schedule_sha256=configuration['schedule_sha256'],
            protocol_sha256=file_digest(ROOT/'docs/evaluations/V52_EVALUATION_DESIGN.md'),
            limits={'native_launches':configuration['planned_runs'],'seconds_per_launch':study['timeout'],'workers':1})
        result['cache']['trial_order']='seeded cyclic ABC/BCA/CAB; optional mirrored CBA/ACB/BAC; ABC/CBA alone is not balanced'
        result['treatments']={arm:v4_runner.fingerprint({'mode':arm,'skill':None if arm=='A' else skill,
            'activation_request':None if arm=='A' else ACTIVATION_REQUEST,
            'preparation_request':PREPARATION_REQUEST if arm=='C' else None}) for arm in ('A','B','C')}
    elif protocol!=51:raise ValueError('Unknown bundle protocol')
    return result


def verify_runtime_archive(path):
    import build_cli
    required=list((ROOT/'scripts').glob('*.py'))+list((ROOT/'evals/v4').glob('*.json'))
    required += list((ROOT/'evals/v52').glob('*.py'))
    required += list((ROOT/'evals/v6').glob('*.json'))
    required += [ROOT/'docs/evaluations'/name for name in ('V4_EVALUATION_DESIGN.md','V5_EVALUATION_DESIGN.md','V51_EVALUATION_DESIGN.md')]
    if (ROOT/'docs/evaluations/V52_EVALUATION_DESIGN.md').exists():required.append(ROOT/'docs/evaluations/V52_EVALUATION_DESIGN.md')
    if (ROOT/'docs/evaluations/V53_EVALUATION_DESIGN.md').exists():required.append(ROOT/'docs/evaluations/V53_EVALUATION_DESIGN.md')
    required += [p for p in (ROOT/'skills/tuck-bit').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist();names=[item.filename for item in entries]
        if (len(entries)>3000 or len(names)!=len(set(names)) or sum(item.file_size for item in entries)>32*1024*1024
                or any(Path(n).is_absolute() or '..' in Path(n).parts for n in names)):
            raise ValueError('Unsafe runtime archive inventory')
        contents=json.loads(archive.read('CONTENTS.json'))
        if (not isinstance(contents,dict) or set(names)!=set(contents)|{'CONTENTS.json','__main__.py'}
                or archive.read('__main__.py')!=build_cli.ENTRY.encode()):
            raise ValueError('Runtime content manifest and launcher required')
        for name,digest in contents.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest:raise ValueError('Archive content mismatch')
        for source in required:
            name=source.relative_to(ROOT).as_posix();expected=file_digest(source)
            if contents.get(name)!=expected or hashlib.sha256(archive.read(name)).hexdigest()!=expected:
                raise ValueError('Runtime archive differs from the active trusted implementation')
    return file_digest(path)


def create(destination,case_id,model,starting_commit,runtime_archive,executable='codex',*,protocol=51,seed=0,trials=1,mirrored=False,timeout=120):
    root=_root(destination)
    if root.exists() or root.is_symlink():raise ValueError('Bundle destination must be new')
    study={'seed':seed,'trials':trials,'mirrored':mirrored,'timeout':timeout} if protocol==52 else None
    body=payload(case_id,model,starting_commit,verify_runtime_archive(runtime_archive),environment(executable),protocol,study)
    root.mkdir(mode=0o700);source=root/'source';source.mkdir()
    v4_runner.corpus().materialize(case_id,source)
    if v4_runner.safe_inventory(source)!=body['source_hashes']:raise ValueError('Source identity differs')
    manifest={'schema':protocol,'sha256':v4_runner.fingerprint(body),'payload':body}
    write_new(root/'manifest.json',manifest)
    verify(root,executable)
    return manifest


def verify(directory,executable='codex'):
    root=_root(directory);manifest=load(root/'manifest.json')
    if not isinstance(manifest,dict) or set(manifest)!={'schema','sha256','payload'} or type(manifest['schema']) is not int or manifest['schema'] not in {51,52}:
        raise ValueError('Invalid bundle schema')
    body=manifest['payload']
    if not isinstance(body,dict) or manifest['sha256']!=v4_runner.fingerprint(body):raise ValueError('Bundle address differs')
    expected=payload(body['case'],body['model']['id'],body['starting_commit'],body['runtime_archive_sha256'],environment(executable),manifest['schema'],body.get('study'))
    if body!=expected:raise ValueError('Pinned source/dependencies/grader/treatment/environment/checks differ')
    inventory=v4_runner.safe_inventory(root)
    expected_names={'manifest.json',*('source/'+name for name in body['source_hashes'])}
    if set(inventory)!=expected_names or v4_runner.safe_inventory(root/'source')!=body['source_hashes']:
        raise ValueError('Bundle contamination or source modification')
    return manifest


def stage(directory,workspace,executable='codex'):
    manifest=verify(directory,executable)
    workspace=Path(workspace)
    if workspace.is_symlink() or not workspace.is_dir() or any(workspace.iterdir()):
        raise ValueError('Every trial needs a new empty real workspace')
    # Reuse the existing bounded snapshot, then move its verified regular source inventory.
    target=workspace/'source-snapshot'
    v4_runner.snapshot(Path(directory)/'source',target)
    for name in manifest['payload']['source_hashes']:
        destination=workspace/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(target/name),str(destination))
    # Remove only empty directories created by this owned staging operation.
    for folder in sorted((p for p in target.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):folder.rmdir()
    target.rmdir()
    if v4_runner.safe_inventory(workspace)!=manifest['payload']['source_hashes']:raise ValueError('Staging contamination')
    return manifest


def reproduce(directory,runtime_archive,executable='codex'):
    manifest=verify(directory,executable);name=manifest['payload']['case']
    if verify_runtime_archive(runtime_archive)!=manifest['payload']['runtime_archive_sha256']:
        raise ValueError('Pinned runtime archive required')
    case,fixture=v4_runner.corpus()._case(name);outcomes={}
    for kind in ('seed','reference','negative'):
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve(),prefix='tuckbit-v51-reproduce-') as folder:
            stage(directory,Path(folder),executable)
            if kind!='seed':
                for path,content in fixture[kind].items():(Path(folder)/path).write_text(content)
            grade=v4_runner.corpus().grade(name,folder)
            outcomes[kind]={'accepted':grade['accepted'],'assertions':grade['checks']}
    passed=not outcomes['seed']['accepted'] and outcomes['reference']['accepted'] and not outcomes['negative']['accepted']
    return {'schema':51,'model_calls':0,'bundle_sha256':manifest['sha256'],'independent_reproduction_passed':passed,
            'outcomes':outcomes,'hidden_gold_exported':False}


def base(value):
    return {**{k:v for k,v in value.items() if k not in {'bundle_sha256','startup_diagnostics'}},'schema':5}


def validate_receipt(value):
    if not isinstance(value,dict) or type(value.get('schema')) is not int or value.get('schema')!=51 or not {'bundle_sha256','startup_diagnostics'}<=value.keys():
        raise ValueError('V5.1 bundle and startup receipt required')
    v5_evaluation.validate_receipt(base(value))
    if not isinstance(value['bundle_sha256'],str) or v4_runner.DIGEST.fullmatch(value['bundle_sha256']) is None:
        raise ValueError('Invalid bundle identity')
    if value['startup_diagnostics'] is not None:native_diagnostics.validate(value['startup_diagnostics'])
    if value['comparison_eligible'] and (value['startup_diagnostics'] is None or value['startup_diagnostics']['exit_code']!=0
                                        or not value['startup_diagnostics']['completed_turn']):
        raise ValueError('Unverified native startup cannot establish efficiency')
    return value


class V51Journal(v5_evaluation.V5Journal):
    validate_receipt=staticmethod(validate_receipt)


def v52_base(row):
    return {**{k:v for k,v in row.items() if k not in {'experiment','observability'}},'schema':51}


def validate_v52_receipt(row):
    from command_evidence import REASONS
    if not isinstance(row,dict) or row.get('schema')!=52 or type(row['schema']) is not int:
        raise ValueError('V5.2 receipt required')
    validate_receipt(v52_base(row))
    experiment=row.get('experiment');observation=row.get('observability')
    if (not isinstance(experiment,dict) or set(experiment)!={'seed','schedule_sha256','order_index','block_order',
            'source_before_sha256','workspace_sha256','benchmark_rerun','control_variant'}
            or type(experiment['seed']) is not int or not 0<=experiment['seed']<2**32
            or type(experiment['order_index']) is not int or not 0<=experiment['order_index']<18
            or experiment['block_order'] not in {'ABC','BCA','CAB','CBA','ACB','BAC'}
            or type(experiment['benchmark_rerun']) is not int or not 0<=experiment['benchmark_rerun']<=1000
            or any(not isinstance(experiment[k],str) or v4_runner.DIGEST.fullmatch(experiment[k]) is None
                   for k in ('schedule_sha256','source_before_sha256','workspace_sha256'))
            or not isinstance(observation,dict) or set(observation)!={'policy','activation','effort'}):
        raise ValueError('Invalid repeated experiment identity')
    variant=experiment['control_variant']
    if ((row['observation_source']=='native_public_events')!=(variant is None)
            or variant is not None and (not isinstance(variant,str) or variant not in v4_runner.CONTROL_VARIANTS)):
        raise ValueError('Controlled client identity differs from provenance')
    if experiment['source_before_sha256']!=v4_runner.fingerprint(_case(row['case'])['source_hashes']):
        raise ValueError('Starting source differs from the immutable corpus')
    policy=observation['policy']
    fields={'observed_commands','classified_commands','successful_commands','failed_commands','unknown_outcomes','unclassified','unsafe'}
    if (not isinstance(policy,dict) or set(policy)!=fields|{'schema','reason_counts'} or type(policy['schema']) is not int or policy['schema']!=1
            or any(type(policy[k]) is not int or not 0<=policy[k]<=10000 for k in fields)
            or not isinstance(policy['reason_counts'],dict) or set(policy['reason_counts'])-REASONS
            or any(type(v) is not int or not 0<=v<=10000 for v in policy['reason_counts'].values())
            or policy['successful_commands']+policy['failed_commands']+policy['unknown_outcomes']!=policy['observed_commands']
            or policy['classified_commands']>policy['observed_commands']
            or policy['classified_commands']+policy['unclassified']!=policy['observed_commands']+policy['reason_counts'].get('unknown_event',0)
            or row['metrics']['unsafe_attempts']['value']!=policy['unsafe'] or row['safety_violations']<policy['unsafe']
            or row['metrics']['unclassified_commands']['value']!=policy['unclassified']+policy['unknown_outcomes']):
        raise ValueError('Invalid sanitized policy coverage')
    activation=observation['activation']
    if (not isinstance(activation,dict) or set(activation)!={'offered','selected','instructions_delivered','instructions_read',
            'invoked','independently_verified','consumption'}
            or type(activation['offered']) is not bool or activation['offered']!=(row['mode']!='A')
            or activation['selected'] is not None or activation['invoked'] is not None
            or activation['consumption']!='unobservable' or type(activation['independently_verified']) is not bool
            or activation['independently_verified']!=row['accepted']
            or any(activation[k] is not None and type(activation[k]) is not bool for k in ('instructions_delivered','instructions_read'))
            or activation['instructions_delivered']!=activation['instructions_read']
            or row['mode']!='A' and row['activation_qualified'] and activation['instructions_delivered'] is not True):
        raise ValueError('Instruction delivery is not verified activation')
    if activation['instructions_delivered'] is True:
        canonical=file_digest(ROOT/'skills/tuck-bit/SKILL.md')
        if not any(c['category']=='skill_instructions' and c['success'] is True and c['evidence']
                   and c['evidence']['delivered'] and c['evidence']['content']==canonical
                   and c['evidence']['revision']==canonical for c in row['execution']['calls']):
            raise ValueError('Whole instruction bytes were not independently delivered')
    effort=observation['effort']
    if not isinstance(effort,dict) or set(effort)!=set(v5_evaluation.EFFORT_METRICS):raise ValueError('Effort provenance required')
    for name,value in effort.items():
        if (not isinstance(value,dict) or set(value)!={'value','source','status'}
                or value['source'] not in {'unavailable','monotonic_clock','explicit_protocol','public_event_duration_sum'}
                or value['status'] not in {'unknown','measured'} or (value['value'] is None)!=(value['status']=='unknown')
                or (value['value'] is None)!=(value['source']=='unavailable')
                or value['value'] is not None and not v4_runner._number(value['value'])):
            raise ValueError('Invalid effort measurement')
        if name in {'human_review_ms','human_edit_ms','human_interventions','agent_retries','tool_retries'} and value['value'] is not None:
            raise ValueError('Unobserved human effort or retries cannot be inferred')
    if effort['benchmark_reruns']['value']!=experiment['benchmark_rerun']:raise ValueError('Reruns differ from study metadata')
    return row


class V52Journal(V51Journal):
    validate_receipt=staticmethod(validate_v52_receipt)

    def _validate(self):
        super()._validate()
        rows=self.document['runs']
        workspaces=[r['experiment']['workspace_sha256'] for r in rows]
        if len(workspaces)!=len(set(workspaces)):raise ValueError('Reused mutable trial workspace')
        for i,row in enumerate(rows):
            exp=row['experiment']
            position=next(j for j,m in enumerate(self.document['order']) if (m['case'],m['trial'],m['mode'])==(row['case'],row['trial'],row['mode']))
            if exp['order_index']!=position or exp['block_order'][position%3]!=row['mode']:
                raise ValueError('Actual trial order differs')
            if rows and (row['bundle_sha256']!=rows[0]['bundle_sha256'] or exp['schedule_sha256']!=rows[0]['experiment']['schedule_sha256']
                         or exp['source_before_sha256']!=rows[0]['experiment']['source_before_sha256']):
                raise ValueError('Bundle/source/schedule changed across repetitions')


def controlled_client(command,prompt,timeout,case,*,variant='correct',context_control=None,**observers):
    """Exercise the existing event importer with a trusted Python subprocess, zero inference."""
    if not isinstance(variant,str) or variant not in v4_runner.CONTROL_VARIANTS:raise ValueError('Unknown control variant')
    folder=command[command.index('-C')+1]
    arguments=[sys.executable,str(ROOT/'evals/v52/fake_client.py'),'-C',folder,variant]
    if context_control is not None:
        arguments.append(json.dumps(v4_runner.validate_context_control(context_control),sort_keys=True))
        observer=observers.get('execution_observer')
        if not callable(observer):raise ValueError('Controlled source delivery requires an event observer')
        # A fast fixture must not mutate source until the importer has verified the read.
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve(),prefix='tuckbit-v53-ack-') as temporary:
            ack=Path(temporary)/'ack';os.mkfifo(ack,0o600)
            fd=os.open(ack,os.O_RDWR|os.O_NONBLOCK)
            def observe(event,root):
                observer(event,root)
                if event.get('phase')=='completed' and re.fullmatch(r'[0-9]+:read-[0-9]+:.*',event.get('id','')):
                    os.write(fd,b'1')
            try:
                result=v4_runner.native_run([*arguments,str(ack)],prompt,timeout,case,
                    **{**observers,'execution_observer':observe})
            finally:os.close(fd)
    else:
        result=v4_runner.native_run(arguments,prompt,timeout,case,**observers)
    result['control_variant']=variant
    if context_control is not None:result['context_control']=context_control
    return result


def demonstrate(directory,runtime_archive):
    root=_root(directory)
    if root.exists():raise ValueError('New private demonstration destination required')
    root.mkdir(mode=0o700)
    bundle=create(root/'bundle','D11-small','controlled-event-client','86ca667211d933203c33d62d6d28a5e26b9a9125',
                  runtime_archive,protocol=52,seed=52,trials=3)
    # Study pseudonyms only; never a provider credential or persisted in public receipts.
    key=os.urandom(32)
    rows=v4_runner.execute(['D11-small'],'controlled-event-client',journal_path=root/'journal.json',explicit=True,
            track='v52',study_key=key,bundle_path=root/'bundle',runtime_archive=runtime_archive,
            seed=52,trials=3,run_budget=9,time_budget=1080,runner=controlled_client)
    result=v5_evaluation.per_task_report(rows)
    write_new(root/'results.json',result)
    assert len(rows)==9 and all(r['accepted'] and r['activation_qualified'] for r in rows)
    return {'schema':52,'model_calls':0,'attempts':9,'accepted':9,'native_comparisons':0,'bundle_sha256':bundle['sha256'],
            'distinct_workspaces':len({r['experiment']['workspace_sha256'] for r in rows}),
            'starting_sources':len({r['experiment']['source_before_sha256'] for r in rows}),
            'schedule_sha256':rows[0]['experiment']['schedule_sha256'],'artifact_root':'explicit_private_destination'}


def report(rows):
    if not isinstance(rows,list) or len(rows)>1000:raise ValueError('Bounded trial list required')
    for row in rows:validate_receipt(row)
    converted=[base(r) for r in rows]
    anchors={(r['case'],r['trial']):r for r in rows if r['mode']=='A'}
    mismatches=[]
    for i,row in enumerate(rows):
        anchor=anchors.get((row['case'],row['trial']))
        if anchor is not None and anchor['bundle_sha256']!=row['bundle_sha256']:
            mismatches.append({'case':row['case'],'trial':row['trial'],'mode':row['mode']})
            # Alter the comparison stratum, never rewrite the retained original receipt.
            converted[i]['identity']={**converted[i]['identity'],'configuration':v4_runner.fingerprint(row['bundle_sha256'])}
    result=v5_evaluation.report(converted)
    return {'schema':51,'bundle_mismatches':mismatches,'v5':result,
            'trials':[{'case':r['case'],'trial':r['trial'],'mode':r['mode'],'bundle_sha256':r['bundle_sha256'],
                       'startup_diagnostics':r['startup_diagnostics']} for r in rows]}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    create_parser=sub.add_parser('create');create_parser.add_argument('--destination',required=True)
    for key in ('case','model','starting-commit','runtime-archive'):create_parser.add_argument('--'+key,required=True)
    create_parser.add_argument('--protocol',type=int,choices=(51,52),default=51)
    create_parser.add_argument('--seed',type=int,default=0);create_parser.add_argument('--trials',type=int,default=1)
    create_parser.add_argument('--mirrored',action='store_true');create_parser.add_argument('--timeout',type=int,default=120)
    replay=sub.add_parser('reproduce');replay.add_argument('--bundle',required=True);replay.add_argument('--output',required=True)
    replay.add_argument('--runtime-archive',required=True)
    demo=sub.add_parser('demonstrate');demo.add_argument('--destination',required=True);demo.add_argument('--runtime-archive',required=True)
    analyze=sub.add_parser('report');analyze.add_argument('--journal',required=True);analyze.add_argument('--output',required=True)
    analyze.add_argument('--approved',action='store_true')
    args=parser.parse_args()
    try:
        if args.command=='create':
            r=create(args.destination,args.case,args.model,args.starting_commit,args.runtime_archive,
                     protocol=args.protocol,seed=args.seed,trials=args.trials,mirrored=args.mirrored,timeout=args.timeout)
            print(json.dumps({'bundle_sha256':r['sha256'],'model_calls':0}))
        elif args.command=='reproduce':
            r=reproduce(args.bundle,args.runtime_archive);write_new(args.output,r);print(json.dumps(r))
        elif args.command=='demonstrate':print(json.dumps(demonstrate(args.destination,args.runtime_archive)))
        else:
            if not args.approved:raise ValueError('Explicit journal approval required')
            document=load(args.journal);journal=object.__new__(V51Journal);journal.document=document;journal._validate()
            r=report(document['runs']);r['journal_markers']={k:document[k] for k in ('inflight','interrupted')}
            write_new(args.output,r);print(json.dumps({'written':True,'trials':len(document['runs'])}))
    except (ValueError,OSError,KeyError,TypeError,StopIteration,zipfile.BadZipFile):parser.error('Invalid V5.1 bundle, environment or receipt')


if __name__=='__main__':main()
