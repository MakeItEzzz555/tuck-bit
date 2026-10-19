#!/usr/bin/env python3
"""Model-free Codex/macOS policy canaries; no host configuration is written."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shlex
import subprocess
import tempfile

from execution_state import write_new

ROOT = Path(__file__).resolve().parents[1]


def arguments(writable=True):
    parent = ':workspace' if writable else ':read-only'
    access = 'write' if writable else 'read'
    policy = ('permissions.v4={extends="'+parent+'",filesystem={":root"="deny",":minimal"="read",'
              '":tmpdir"="deny",":slash_tmp"="deny",":workspace_roots"={"."="'+access+'"}},network={enabled=false}}')
    return ['-c', 'default_permissions="v4"', '-c', policy, '-c', 'approval_policy="never"',
            '-c', 'web_search="disabled"', '-c', 'features.multi_agent=false']


def preflight(executable='codex', writable=True):
    if platform.system() != 'Darwin':
        raise ValueError('Native read-isolation transport is validated only on macOS')
    version = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=10)
    label = version.stdout.strip()
    if version.returncode or re.fullmatch(r'codex-cli 0\.163\.0', label) is None:
        raise ValueError('Native client version has not passed this isolation protocol')
    with tempfile.TemporaryDirectory(dir='/private/tmp', prefix='tuckbit-v4-isolation-') as directory:
        root = Path(directory)
        work = root/'workspace'; work.mkdir()
        (work/'allowed').write_text('synthetic readable canary')
        (work/'.agents').mkdir(); (work/'.agents/guard').write_text('protected canary')
        outside = root/'outside'; outside.write_text('synthetic denied canary')
        (work/'escape').symlink_to(outside)
        targets = {'workspace': work/'allowed', 'outside': outside,
                   'evaluator': ROOT/'evals/v4/fixtures.json', 'symlink_escape': work/'escape'}
        commands = ['set -u']
        for name, path in targets.items():
            commands.append('if /usr/bin/head -c 1 '+shlex.quote(str(path))+' >/dev/null 2>&1; then '+name+'=true; else '+name+'=false; fi')
        for name, path in [('workspace_write', work/'created'), ('outside_write', root/'forbidden'), ('protected_write', work/'.agents/guard')]:
            commands.append('if (printf probe > '+shlex.quote(str(path))+') 2>/dev/null; then '+name+'=true; else '+name+'=false; fi')
        fields = list(targets)+['workspace_write', 'outside_write', 'protected_write']
        fmt = '{'+','.join('"'+name+'":%s' for name in fields)+'}\\n'
        commands.append('printf '+shlex.quote(fmt)+' '+' '.join('"$'+name+'"' for name in fields))
        command = [executable, *arguments(writable), 'sandbox', '-P', 'v4',
                   '--include-managed-config', '-C', str(work), '/bin/sh', '-c', '\n'.join(commands)]
        observed = subprocess.run(command, capture_output=True, text=True, timeout=20)
        try:
            values = json.loads(observed.stdout)
        except (ValueError, TypeError):
            raise ValueError('Read-isolation canary unavailable or blocked; no model launched') from None
        expected = {'workspace': True, 'outside': False, 'evaluator': False, 'symlink_escape': False,
                    'workspace_write': writable, 'outside_write': False, 'protected_write': False}
        if observed.returncode or values != expected or any(type(v) is not bool for v in values.values()):
            raise ValueError('Host-read-isolated canary failed; no model launched')
    return {'schema': 4, 'kind': 'native_isolation_preflight', 'model_calls': 0,
            'client_version': label, 'policy_sha256': hashlib.sha256(json.dumps(arguments(writable)).encode()).hexdigest(),
            'observation_source': 'supported_codex_sandbox_canaries', 'writable': writable,
            'checks': values, 'verified': True,
            'limitations': ['macOS and Codex 0.163.0 only; minimal runtime paths remain readable.',
                            'Command network is disabled by policy; no external network probe performed.',
                            'No global policy, authentication, private session or credential was inspected.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--read-only', action='store_true')
    args = parser.parse_args()
    try:
        result = preflight(writable=not args.read_only)
        write_new(args.output, result)
        print(json.dumps({'verified': True, 'model_calls': 0}))
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
