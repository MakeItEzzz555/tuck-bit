"""Bounded transient startup signatures. Only codes/counts/exit status leave memory."""
import re

LIMIT = 65536
SIGNATURES = {
    'incompatible_flags': r'unexpected argument|unrecognized (?:argument|option)',
    'configuration_error': r'error loading config|failed to load config|unknown field|invalid configuration|TOML parse error|invalid type|invalid value',
    'permission_profile_error': r'permission profile.*(?:not found|unknown|invalid)|unknown permission profile|permissions.*cannot',
    'authentication_error': r'invalid_api_key|authentication_error|not logged in|401 unauthorized',
    'model_unavailable': r'model_not_found|unsupported_model|model[^\n]{0,160}(?:not supported|does not exist)',
    'quota_or_rate_limit': r'rate_limit_exceeded|insufficient_quota|usage limit (?:has been )?reached',
    'network_error': r'connection refused|failed to resolve|dns error|error sending request',
    'sandbox_startup_denied': r'failed to (?:apply|initialize).*sandbox|sandbox-exec.*operation not permitted',
    'git_preflight_error': r'not inside a trusted directory|failed to read git|badRefContent',
    'seatbelt_apply_denied': r'sandbox_apply: Operation not permitted',
}
CODES = set(SIGNATURES) | {'spawn_unavailable', 'process_signal', 'timeout', 'malformed_public_stream',
                          'diagnostic_limit', 'unknown_nonzero_exit', 'missing_completed_turn'}
DETAILS = {'network_proxy':r'network proxy|network_proxy', 'seatbelt':r'seatbelt|sandbox-exec|sandbox_apply',
           'exec_server':r'exec.server',
           'certificate_store':r'certificate|keychain|trust store', 'state_database':r'sqlite|state database',
           'permission_profile':r'permission profile|default_permissions', 'loopback_bind':r'bind|listen|loopback',
           'filesystem':r'filesystem|file system|directory', 'permission_denied':r'permission denied|operation not permitted',
           'missing_path':r'no such file|not found', 'strict_config':r'strict.config|unknown field'}


class StartupDiagnostics:
    def __init__(self):
        self.buffer = bytearray()
        self.observed = 0
        self.codes = set()
        self.details = set()

    def stderr(self, chunk):
        self.observed += len(chunk)
        self.buffer.extend(chunk[:max(0, LIMIT-len(self.buffer))])
        if self.observed > LIMIT:
            self.codes.add('diagnostic_limit')
            return False
        return True

    def public_error(self, source):
        # Public errors may carry a string or structured message. Never copy arbitrary fields.
        values = [source.get('message'), source.get('code')]
        error = source.get('error')
        if isinstance(error, dict): values.extend(error.get(k) for k in ('message','code'))
        elif isinstance(error, str): values.append(error)
        self.classify(' '.join(v[:4096] for v in values if isinstance(v,str)))

    def classify(self, text):
        for code, pattern in SIGNATURES.items():
            if re.search(pattern, text, re.IGNORECASE): self.codes.add(code)
        for code,pattern in DETAILS.items():
            if re.search(pattern,text,re.IGNORECASE):self.details.add(code)

    def finish(self, exit_code=None, *, complete=False, timed_out=False, malformed=False, spawned=True):
        self.classify(self.buffer.decode('utf-8', errors='replace'))
        self.buffer.clear()
        if not spawned: self.codes.add('spawn_unavailable')
        if timed_out: self.codes.add('timeout')
        if malformed: self.codes.add('malformed_public_stream')
        if exit_code is not None and exit_code < 0: self.codes.add('process_signal')
        if exit_code not in (None,0) and not self.codes: self.codes.add('unknown_nonzero_exit')
        if not complete: self.codes.add('missing_completed_turn')
        result={'schema':1,'exit_code':exit_code,'signal':-exit_code if exit_code is not None and exit_code < 0 else None,
                'stderr_bytes_observed':self.observed,'stderr_retained_bytes':0,'reason_codes':sorted(self.codes),
                'detail_codes':sorted(self.details),
                'completed_turn':complete,'source':'bounded_stdio_and_public_error_signatures'}
        validate(result)
        return result


def validate(value):
    if (not isinstance(value,dict) or set(value) != {'schema','exit_code','signal','stderr_bytes_observed',
            'stderr_retained_bytes','reason_codes','detail_codes','completed_turn','source'} or type(value['schema']) is not int or value['schema']!=1
            or value['source']!='bounded_stdio_and_public_error_signatures'
            or value['exit_code'] is not None and (type(value['exit_code']) is not int or not -255<=value['exit_code']<=255)
            or value['signal'] != (-value['exit_code'] if value['exit_code'] is not None and value['exit_code']<0 else None)
            or type(value['stderr_bytes_observed']) is not int or not 0<=value['stderr_bytes_observed']<=LIMIT+65536
            or type(value['stderr_retained_bytes']) is not int or value['stderr_retained_bytes']!=0
            or type(value['completed_turn']) is not bool or not isinstance(value['reason_codes'],list)
            or any(not isinstance(c,str) or c not in CODES for c in value['reason_codes'])
            or len(value['reason_codes']) != len(set(value['reason_codes']))):
        raise ValueError('Invalid sanitized startup diagnostics')
    if not isinstance(value['detail_codes'],list) or any(not isinstance(c,str) or c not in DETAILS for c in value['detail_codes']) or len(value['detail_codes'])!=len(set(value['detail_codes'])):
        raise ValueError('Invalid diagnostic detail codes')
    return value


def resolved_executable(executable='codex'):
    import shutil,stat
    from pathlib import Path
    name=shutil.which(executable)
    if name is None: raise ValueError('Pinned executable unavailable')
    path=Path(name).resolve()
    if not stat.S_ISREG(path.stat().st_mode): raise ValueError('Pinned executable is not regular')
    return str(path)


def probe_thread(executable='codex', model='gpt-6.1-sol', resolve_launcher=True):
    """Initialize one ephemeral thread configuration. Never sends turn/start or user input."""
    import json,os,selectors,signal,subprocess,tempfile,time
    from pathlib import Path
    import v4_isolation
    with tempfile.TemporaryDirectory(dir='/private/tmp',prefix='tuckbit-v51-startup-') as folder:
        command=[resolved_executable(executable) if resolve_launcher else executable,'--strict-config',*v4_isolation.arguments(),
                 '-c','model_reasoning_effort="low"','-c','mcp_servers={}','app-server','--stdio']
        diagnostics=StartupDiagnostics()
        result={'model_calls':0,'turns_started':0,'initialize':False,'thread_configuration_ready':False,
                'model_matches':None,'public_error_code':None,'scope':'app_server_ephemeral_thread_no_inference'}
        try:p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        except OSError:
            result['diagnostics']=diagnostics.finish(spawned=False);return result
        selector=selectors.DefaultSelector()
        selector.register(p.stdout,selectors.EVENT_READ);selector.register(p.stderr,selectors.EVENT_READ)
        pending=b'';done=False;malformed=False;expired=False
        def send(value):
            p.stdin.write((json.dumps(value)+'\n').encode());p.stdin.flush()
        try:
            send({'id':1,'method':'initialize','params':{'clientInfo':{'name':'tuckbit_v51_preflight','version':'0.1.0'}}})
            deadline=time.monotonic()+15
            while not done and selector.get_map() and time.monotonic()<deadline:
                for key,_ in selector.select(.1):
                    chunk=os.read(key.fd,65536)
                    if not chunk:selector.unregister(key.fileobj);continue
                    if key.fileobj is p.stderr:
                        if not diagnostics.stderr(chunk):done=True;malformed=True
                        continue
                    pending+=chunk
                    if len(pending)>2*1024*1024:done=True;malformed=True;break
                    while b'\n' in pending:
                        line,pending=pending.split(b'\n',1)
                        msg=json.loads(line)
                        if msg.get('id')==1:
                            result['initialize']='result' in msg
                            if not result['initialize']:diagnostics.public_error(msg);done=True;break
                            send({'method':'initialized','params':{}})
                            send({'id':2,'method':'thread/start','params':{'model':model,'cwd':folder,'ephemeral':True,
                                 'approvalPolicy':'never','config':{'mcp_servers':{}}}})
                        elif msg.get('id')==2:
                            result['thread_configuration_ready']='result' in msg
                            if 'result' in msg:result['model_matches']=msg['result'].get('model')==model
                            if 'error' in msg:
                                diagnostics.public_error(msg)
                                code=msg['error'].get('code');result['public_error_code']=code if type(code) is int else None
                            done=True;break
            expired=not done and time.monotonic()>=deadline
        except (ValueError,TypeError,AttributeError,BrokenPipeError):malformed=True
        finally:
            selector.close();p.stdin.close()
            if p.poll() is None:
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                p.wait(timeout=5)
            p.stdout.close();p.stderr.close()
        result['diagnostics']=diagnostics.finish(p.returncode,complete=False,timed_out=expired,malformed=malformed)
        return result


if __name__=='__main__':
    import argparse,json
    from execution_state import write_new
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=probe_thread();write_new(args.output,result)
    print(json.dumps(result))
