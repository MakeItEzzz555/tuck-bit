#!/usr/bin/env python3
"""Versioned V6 executable companions; candidates run only in checked native isolation."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

import v4_corpus as corpus
import v4_isolation as isolation

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'evals/v6/runtime_cases.json'
TEMP_ROOT = '/private/tmp' if sys.platform == 'darwin' else None
MAX_OUTPUT = 32768
MAX_SOURCE = 65536
LIMITS = {'cpu_seconds': 2, 'rss_watchdog_bytes': 268435456, 'rss_poll_ms': 50, 'file_bytes': 65536,
          'open_files': 64, 'processes': 0, 'wall_seconds': 10, 'output_bytes': MAX_OUTPUT}
FORK_POLICY = 'trusted-launcher-hard-RLIMIT_NPROC=0;non-root-required'
# Public harness only: inputs and invocation mechanics, never expected answers.
LAUNCH = '''import os,resource,runpy,sys
if os.getsid(0)!=os.getpid():os.setsid()
print('TUCKBIT_SESSION:'+str(os.getpid()),flush=True)
for which,value in [(resource.RLIMIT_CPU,2),(resource.RLIMIT_FSIZE,65536),(resource.RLIMIT_NOFILE,64),(resource.RLIMIT_NPROC,0)]:
 resource.setrlimit(which,(value,value))
sys.path.insert(0,os.path.abspath('.agents/source'))
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
PROBE = '''import inspect,itertools,json
import policy,legacy,service
functions=[policy.eligible,legacy.can_use,service.allowed]
values=[(a,b,q) for a,b,q in itertools.product([False,True],[False,True],[-1,0,1,2])]
print(json.dumps({'interfaces':[list(inspect.signature(f).parameters) for f in functions],
 'values':[[a,b,q,policy.eligible(a,b),legacy.can_use(a,b),service.allowed(a,b,q)] for a,b,q in values]}))
'''


def _load():
    body = json.loads(DATA.read_text())
    if not isinstance(body, dict) or set(body) != {'schema', 'cases'} or body['schema'] != 6:
        raise ValueError('Invalid runtime companion manifest')
    ids = set()
    for case in body['cases']:
        fields = {'id', 'parent_case', 'language', 'complexity', 'task', 'files', 'reference', 'editable', 'source_revision', 'requirements_sha256', 'reference_sha256', 'controls', 'controls_sha256'}
        if not isinstance(case, dict) or set(case) != fields or case['id'] in ids:
            raise ValueError('Invalid runtime companion identity')
        ids.add(case['id'])
        parent, _ = corpus._case(case['parent_case'])
        if case['complexity'] != parent['complexity'] or case['language'] != 'Python':
            raise ValueError('Invalid companion provenance')
        for mapping in (case['files'], case['reference']):
            if not isinstance(mapping, dict) or not mapping:
                raise ValueError('Missing companion source')
            for name, source in mapping.items():
                if (not isinstance(name, str) or Path(name).name != name or not name.endswith('.py')
                        or not isinstance(source, str) or len(source.encode()) > MAX_SOURCE):
                    raise ValueError('Unsafe companion source')
        if set(case['reference']) - set(case['editable']) or set(case['editable']) - set(case['files']):
            raise ValueError('Invalid companion editable inventory')
        if (case['source_revision'] != corpus.digest(case['files'])
                or case['requirements_sha256'] != corpus.digest(case['task'])
                or case['reference_sha256'] != corpus.digest(case['reference'])
                or case['controls_sha256'] != corpus.digest(case['controls'])):
            raise ValueError('Companion identity changed')
    return body


def cases():
    """Public task metadata excludes reference implementations."""
    return [{k: v for k, v in case.items() if k not in {'reference', 'controls'}} for case in _load()['cases']]


def _case(case_id):
    for case in _load()['cases']:
        if case['id'] == case_id:
            return case
    raise ValueError('Unknown runtime companion')


def materialize(case_id, destination):
    case = _case(case_id)
    folder = Path(destination)
    if folder.is_symlink() or folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise ValueError('Companion destination must be empty')
    if any(p.is_symlink() and str(p) not in {'/tmp', '/var'} for p in folder.parents):
        raise ValueError('Symlinked companion destination')
    folder.mkdir(parents=True, exist_ok=True)
    for name, source in case['files'].items():
        (folder / name).write_text(source)
    return {k: v for k, v in case.items() if k not in {'reference', 'controls'}}


def _snapshot(case, folder):
    """Copy validated bytes once; execution never touches mutable submitted paths."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir() or any(p.is_symlink() and str(p) not in {'/tmp', '/var'} for p in folder.parents):
        raise ValueError('Unsafe candidate workspace')
    if {p.name for p in folder.iterdir()} != set(case['files']):
        raise ValueError('Candidate inventory mismatch')
    result = {}; directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in folder.resolve().parts[1:]:
            next_directory = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = next_directory
        if set(os.listdir(directory)) != set(case['files']):
            raise ValueError('Candidate inventory mismatch')
        for name in case['files']:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                before = os.fstat(descriptor)
                if before.st_nlink != 1 or not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE:
                    raise ValueError('Unsafe candidate file')
                data = os.read(descriptor, MAX_SOURCE + 1)
                after = os.fstat(descriptor)
                if len(data) > MAX_SOURCE or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                    raise ValueError('Candidate changed during snapshot')
                result[name] = data.decode()
            finally:
                os.close(descriptor)
            if name not in case['editable'] and result[name] != case['files'][name]:
                raise ValueError('Protected source modified')
    finally:
        os.close(directory)
    return result


def _command(client, work, argv):
    return [client, *isolation.arguments(True), 'sandbox', '-P', 'v4', '--include-managed-config',
            '-C', str(work), '/usr/bin/python3',
            '-I', '-B', '-c', LAUNCH, *argv]


def _run(client, work, argv, inventory=True):
    started = time.monotonic()
    env = {'PATH': '/usr/bin:/bin', 'TMPDIR': '/private/tmp', 'LC_ALL': 'C'}
    process = subprocess.Popen(_command(client, work, argv), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                               start_new_session=True, close_fds=True)
    output = bytearray(); limited = None; candidate_pid = None; header_seen = False; rss_peak = None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while selector.get_map() or process.poll() is None:
            if time.monotonic() - started > LIMITS['wall_seconds']:
                limited = 'timeout'; break
            if candidate_pid:
                try:
                    if inventory: _files(work)
                except (ValueError, OSError):
                    limited = 'output_inventory'; break
                try:
                    if os.getsid(candidate_pid) != candidate_pid:
                        limited = 'session_changed'; break
                    measured = subprocess.run(['/bin/ps', '-o', 'rss=', '-p', str(candidate_pid)], capture_output=True, text=True, timeout=1, close_fds=True)
                    if measured.returncode or not measured.stdout.strip().isdigit():
                        try: os.getsid(candidate_pid)
                        except ProcessLookupError: continue
                        limited = 'rss_unavailable'; break
                    rss_peak = max(rss_peak or 0, int(measured.stdout.strip()) * 1024)
                    if rss_peak > LIMITS['rss_watchdog_bytes']:
                        limited = 'rss_watchdog'; break
                except ProcessLookupError: pass
                except (OSError, subprocess.TimeoutExpired):
                    limited = 'rss_unavailable'; break
            for key, _ in selector.select(0.05):
                part = os.read(key.fileobj.fileno(), 4096)
                if not part:
                    selector.unregister(key.fileobj); break
                output.extend(part)
                if not header_seen and b'\n' in output:
                    header, _, rest = output.partition(b'\n')
                    if not header.startswith(b'TUCKBIT_SESSION:') or not header[16:].isdigit():
                        limited = 'invalid_launcher'; break
                    candidate_pid = int(header[16:]); header_seen = True; output = bytearray(rest)
                    if candidate_pid <= 1 or candidate_pid == os.getpid():
                        limited = 'invalid_launcher'; break
                if len(output) > MAX_OUTPUT:
                    limited = 'output_limit'; break
            if limited:
                break
        if limited:
            if candidate_pid:
                try: os.kill(candidate_pid, signal.SIGKILL)
                except ProcessLookupError: pass
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            limited = limited or 'incomplete_exit'
    finally:
        if candidate_pid:
            try:
                if os.getsid(candidate_pid) == candidate_pid: os.kill(candidate_pid, signal.SIGKILL)
            except ProcessLookupError: pass
        if process.poll() is None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=1)
        selector.close(); process.stdout.close()
    return {'exit_code': process.returncode, 'stdout': bytes(output[:MAX_OUTPUT]),
            'limited': limited, 'cleanup_verified': _cleanup_verified(candidate_pid), 'rss_peak_bytes': rss_peak, 'wall_ms': (time.monotonic() - started) * 1000}


def _cleanup_verified(pid):
    if pid is None:
        return False
    try:
        if os.getsid(pid) != pid:
            return False
        state = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True, timeout=1, close_fds=True)
        return state.returncode != 0 or state.stdout.strip().startswith('Z')
    except ProcessLookupError:
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def preflight(client='codex'):
    """No inference: retain existing policy and additionally prove child creation denied."""
    executable = shutil.which(client)
    if not executable:
        raise ValueError('Runtime acceptance needs supported local Codex sandbox client')
    executable = str(Path(executable).resolve())
    base = isolation.preflight(executable, writable=True)
    with tempfile.TemporaryDirectory(dir=TEMP_ROOT, prefix='tuckbit-v6-boundary-') as directory:
        root = Path(directory); work = root / 'workspace'; work.mkdir()
        protected = work / '.agents'; protected.mkdir(); (work / 'data').mkdir()
        outside = root / 'outside'; outside.write_text('synthetic')
        (work / 'escape').symlink_to(outside)
        probe = '''import errno,json,os,resource,socket,subprocess
from pathlib import Path
r={'session_leader':os.getpid()==os.getsid(0),'non_root':os.getuid()!=0}
try:resource.setrlimit(resource.RLIMIT_NPROC,(32,32));r['raise_nproc']=True
except (OSError,ValueError):r['raise_nproc']=False
try:
 child=os.fork()
 if child==0:os._exit(0)
 os.waitpid(child,0);r['fork']=True
except OSError:r['fork']=False
try:
 child=os.posix_spawn('/usr/bin/true',['/usr/bin/true'],{});os.waitpid(child,0);r['spawn']=True
except OSError:r['spawn']=False
try:os.setsid();r['detach']=True
except OSError:r['detach']=False
try:
 s=socket.socket();s.bind(('127.0.0.1',0));s.close();r['network']=True
except OSError as e:r['network']=e.errno not in (errno.EPERM,errno.EACCES)
for label,path in TARGETS:
 try: Path(path).read_bytes();r[label]=True
 except OSError:r[label]=False
for label,path in WRITES:
 try: Path(path).write_text('probe');r[label]=True
 except OSError:r[label]=False
try:subprocess.run(['/usr/bin/true'],check=True);r['child']=True
except OSError:r['child']=False
print(json.dumps(r))
'''.replace('TARGETS', repr([('outside', str(outside)), ('evaluator', str(DATA)), ('symlink', str(work / 'escape'))])).replace('WRITES', repr([('source_write', str(protected / 'probe.py')), ('data_write', str(work / 'data' / 'written')), ('outside_write', str(root / 'forbidden'))]))
        (protected / 'probe.py').write_text(probe)
        sibling = subprocess.Popen(['/bin/sleep', '10'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        probe = probe.replace("print(json.dumps(r))", "try:os.kill("+str(sibling.pid)+",0);r['outside_signal']=True\nexcept OSError:r['outside_signal']=False\nprint(json.dumps(r))")
        (protected / 'probe.py').write_text(probe)
        try:
            observed = _run(executable, work, ['.agents/probe.py'], inventory=False)
        finally:
            sibling.terminate(); sibling.wait(timeout=2)
        expected = {'outside': False, 'evaluator': False, 'symlink': False, 'source_write': False,
                    'data_write': True, 'outside_write': False, 'child': False, 'session_leader': True, 'detach': False, 'network': False, 'non_root': True, 'raise_nproc': False, 'fork': False, 'spawn': False, 'outside_signal': False}
        try:
            actual = json.loads(observed['stdout'])
        except (ValueError, UnicodeError):
            raise ValueError('Runtime boundary unavailable; no candidate executed') from None
        if observed['exit_code'] or observed['limited'] or not observed['cleanup_verified'] or actual != expected:
            raise ValueError('Runtime boundary failed; no candidate executed')
    return {'verified': True, 'client': executable, 'client_sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
            'policy_sha256': corpus.digest(isolation.arguments(True)), 'fork_policy_sha256': corpus.digest(FORK_POLICY),
            'checks': actual, 'base': base, 'model_calls': 0}


def resource_canaries(client='codex'):
    """Fixed small trusted controls only; this does not establish a hard memory ceiling."""
    boundary = preflight(client); results = {}
    with tempfile.TemporaryDirectory(dir=TEMP_ROOT, prefix='tuckbit-v6-resources-') as directory:
        work = Path(directory); (work / '.agents').mkdir(); (work / 'data').mkdir()
        programs = {'allocation': "import time\nvalue=bytearray(64*1024*1024)\ntime.sleep(10)\n",
                    'closed_stdout': "import os,time\nos.close(1)\ntime.sleep(20)\n"}
        for name, source in programs.items():
            (work / '.agents/probe.py').write_text(source)
            old = LIMITS['rss_watchdog_bytes']
            try:
                if name == 'allocation': LIMITS['rss_watchdog_bytes'] = 32 * 1024 * 1024
                observed = _run(boundary['client'], work, ['.agents/probe.py'])
            finally:
                LIMITS['rss_watchdog_bytes'] = old
            expected = 'rss_watchdog' if name == 'allocation' else 'timeout'
            results[name] = {'passed': observed['limited'] == expected and observed['cleanup_verified'],
                             'limited': observed['limited'], 'cleanup_verified': observed['cleanup_verified'],
                             'rss_peak_bytes': observed['rss_peak_bytes'], 'wall_ms': observed['wall_ms']}
    if not all(row['passed'] for row in results.values()):
        raise ValueError('Trusted resource canary failed; candidate execution blocked')
    return {'schema': 6, 'model_calls': 0, 'verified': True, 'trusted_controls_only': True,
            'hard_memory_limit': 'unsupported', 'results': results}


def _files(root):
    result = {}; total = 0; directories = 0
    for parent, names, files in os.walk(root, followlinks=False):
        directories += len(names)
        if directories > 10:
            raise ValueError('Runtime directory inventory exceeded')
        for name in names:
            if (Path(parent) / name).is_symlink():
                raise ValueError('Unsafe runtime directory')
        for name in files:
            p = Path(parent) / name
            info = p.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Unsafe runtime output')
            total += info.st_size
            if len(result) >= 30 or info.st_size > MAX_SOURCE or total > 262144:
                raise ValueError('Runtime output inventory exceeded')
            result[str(p.relative_to(root))] = p.read_bytes()
    return result


def grade(case_id, workspace, client='codex', boundary=None):
    """External expectations stay here, never in candidate Python or agent workspace."""
    started = time.monotonic(); case = _case(case_id); source = _snapshot(case, workspace)
    trusted = [case['files'], {**case['files'], **case['reference']}]
    trusted += [{**case['files'], **value} for value in case['controls'].values()]
    if corpus.digest(source) not in {corpus.digest(value) for value in trusted}:
        raise ValueError('Unknown submitted code blocked: enforceable hard memory limit unavailable')
    # Boundary receipts are advisory only; every grading call rechecks the live transport.
    boundary = preflight(client)
    observations = []; checks = []
    with tempfile.TemporaryDirectory(dir=TEMP_ROOT, prefix='tuckbit-v6-grade-') as directory:
        work = Path(directory); src = work / '.agents/source'; src.mkdir(parents=True); data = work / 'data'; data.mkdir()
        for name, text in source.items():
            (src / name).write_text(text)
        if case['parent_case'] == 'D04-medium':
            (work / '.agents/probe.py').write_text(PROBE)
            expected = {'interfaces': [['active', 'blocked'], ['active', 'blocked'], ['active', 'blocked', 'quota']],
                        'values': [[a, b, q, a and not b, a and not b, a and not b and q > 0]
                                   for a, b, q in itertools.product((False, True), (False, True), (-1, 0, 1, 2))]}
            before = _files(work)
            outcome = _run(boundary['client'], work, ['.agents/probe.py']); observations.append(outcome)
            try: value = json.loads(outcome['stdout'])
            except (ValueError, UnicodeError, RecursionError): value = None
            checks.extend([not outcome['limited'] and outcome['cleanup_verified'], outcome['exit_code'] == 0, corpus.digest(value) == corpus.digest(expected), _files(work) == before])
            # Existing structural/API/dependency contract remains independently mandatory.
            with tempfile.TemporaryDirectory(dir=TEMP_ROOT, prefix='tuckbit-v6-legacy-') as legacy_directory:
                legacy = Path(legacy_directory); corpus.materialize('D04-medium', legacy)
                for name in ('policy.py', 'legacy.py', 'service.py'): (legacy / name).write_text(source[name])
                checks.append(corpus.grade('D04-medium', legacy)['accepted'])
        else:
            records = [{'id': 2, 'name': ' Bee '}, {'id': 1, 'name': ' Aye '}]
            normal = '[{"id":1,"name":"Aye"},{"id":2,"name":"Bee"}]\n'
            inputs = [('valid', records), ('duplicate', [{'id': 1, 'name': 'a'}, {'id': 1, 'name': 'b'}]),
                      ('bool', [{'id': True, 'name': 'a'}]), ('empty', [{'id': 1, 'name': ' '}]),
                      ('malformed', '{'), ('negative', [{'id': -1, 'name': 'bad'}])]
            for label, value in inputs:
                (data / (label + '.json')).write_text(value if isinstance(value, str) else json.dumps(value))
            (data / 'existing.json').write_text('PRESERVE\n')
            plans = [(['data/valid.json', 'data/output.json'], 0, b'{"written":2}\n', normal),
                     (['data/valid.json', 'data/output.json'], 0, b'{"written":2}\n', normal)]
            plans += [(['data/' + label + '.json', 'data/' + label + '-out.json'], 2, b'', None) for label, _ in inputs if label != 'valid']
            plans += [(['data/missing.json', 'data/missing-out.json'], 2, b'', None), ([], 2, b'', None),
                      (['--unknown'], 2, b'', None), (['data/valid.json', 'data/existing.json'], 2, b'', None),
                      (['data/valid.json', 'data/valid.json'], 2, b'', None)]
            protected = _files(work)
            for index, (arguments, code, stdout, content) in enumerate(plans):
                before = _files(work)
                previous_stat = (data / 'output.json').stat() if index == 1 and (data / 'output.json').exists() else None
                outcome = _run(boundary['client'], work, ['.agents/source/normalize.py', *arguments]); observations.append(outcome)
                after = _files(work)
                expected_files = dict(before)
                if content is not None: expected_files['data/output.json'] = content.encode()
                checks.extend([not outcome['limited'] and outcome['cleanup_verified'], outcome['exit_code'] == code, outcome['stdout'] == stdout, after == expected_files])
                if index == 1:
                    current_stat = (data / 'output.json').stat() if (data / 'output.json').exists() else None
                    checks.append(previous_stat is not None and current_stat is not None and (previous_stat.st_ino, previous_stat.st_mtime_ns) == (current_stat.st_ino, current_stat.st_mtime_ns))
            checks.append(all(_files(work).get(k) == v for k, v in protected.items()))
    return {'schema': 6, 'id': case_id, 'parent_case': case['parent_case'], 'source_revision': case['source_revision'],
            'submitted_sha256': corpus.digest(source), 'accepted': bool(checks) and all(checks),
            'checks': len(checks), 'passed_checks': sum(checks), 'model_calls': 0,
            'boundary': {k: v for k, v in boundary.items() if k != 'client'},
            'observations': [{'exit_code': o['exit_code'], 'limited': o['limited'], 'output_bytes': len(o['stdout']),
                              'wall_ms': o['wall_ms'], 'cleanup_verified': o['cleanup_verified']} for o in observations],
            'wall_ms': (time.monotonic() - started) * 1000,
            'limits': LIMITS, 'limitations': ['macOS/Codex 0.163.0 sandbox only; exact trusted control digests only; arbitrary submissions/native trials blocked until enforceable hard memory limits exist.', 'Darwin hard DATA/AS limits unavailable; RSS watchdog polls every 50ms and can overshoot its threshold. Aggregate disk quota is not enforced; parent validates bounded output inventories.']}


def validate_all(client='codex'):
    started = time.monotonic(); results = []
    for case in _load()['cases']:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT, prefix='tuckbit-v6-source-') as directory:
            folder = Path(directory); materialize(case['id'], folder)
            seed = grade(case['id'], folder, client)
            for name, source in case['reference'].items(): (folder / name).write_text(source)
            reference = grade(case['id'], folder, client)
            # Only immutable, test-authored controls are eligible for this limited transport.
            for name, source in case['files'].items(): (folder / name).write_text(source)
            for name, source in case['controls']['zero_exit'].items(): (folder / name).write_text(source)
            wrong = grade(case['id'], folder, client)
            negatives = {}
            for label, changes in case['controls'].items():
                if label == 'zero_exit': continue
                for name, source in case['files'].items(): (folder / name).write_text(source)
                for name, source in changes.items(): (folder / name).write_text(source)
                negatives[label] = grade(case['id'], folder, client)
            results.append({'id': case['id'], 'seed_rejected': not seed['accepted'], 'reference_accepted': reference['accepted'],
                            'zero_exit_rejected': not wrong['accepted'], 'reference_checks': reference['checks'],
                            'seed': seed, 'reference': reference, 'wrong': wrong, 'negative_controls': negatives,
                            'negatives_rejected': all(not value['accepted'] for value in negatives.values())})
    return {'schema': 6, 'model_calls': 0, 'trusted_controls_only': True, 'native_ready': False, 'cases': len(results),
            'graders_validated': sum(r['seed_rejected'] and r['reference_accepted'] and r['zero_exit_rejected'] and r['negatives_rejected'] for r in results),
            'assertions': sum(r['reference_checks'] for r in results), 'results': results,
            'wall_ms': (time.monotonic() - started) * 1000}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['manifest', 'preflight', 'canaries', 'validate'])
    parser.add_argument('--client', default='codex')
    args = parser.parse_args()
    try:
        result = cases() if args.command == 'manifest' else preflight(args.client) if args.command == 'preflight' else resource_canaries(args.client) if args.command == 'canaries' else validate_all(args.client)
        print(json.dumps(result, indent=2))
        return int(args.command == 'validate' and result['graders_validated'] != len(result['results']))
    except (ValueError, OSError, TypeError, KeyError, UnicodeError, subprocess.TimeoutExpired):
        print(json.dumps({'schema': 6, 'error': 'runtime_boundary_or_input_unavailable', 'model_calls': 0}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
