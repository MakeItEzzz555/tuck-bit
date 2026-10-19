import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_runner import native_run
from native_diagnostics import StartupDiagnostics,LIMIT,validate,resolved_executable,probe_thread
from native_fixture import portable_native_temp


class DiagnosticTests(unittest.TestCase):
    def client(self,source,prompt='',timeout=2):
        return native_run([sys.executable,'-c',source],prompt,timeout,'controlled')

    def test_nonzero_exit_retains_only_reason_codes(self):
        r=self.client("import sys;sys.stderr.write('Error loading config PRIVATE_SECRET /private/user/file');sys.exit(23)")
        d=r['startup_diagnostics'];self.assertEqual(d['exit_code'],23)
        self.assertIn('configuration_error',d['reason_codes'])
        self.assertNotIn('PRIVATE_SECRET',json.dumps(r));self.assertNotIn('/private/user',json.dumps(r))

    def test_all_signatures_are_bounded_and_nonexecuting(self):
        samples={'unexpected argument --x':'incompatible_flags','invalid_api_key PRIVATE':'authentication_error',
                 'model_not_found':'model_unavailable','rate_limit_exceeded':'quota_or_rate_limit',
                 'failed to initialize sandbox: Operation not permitted':'sandbox_startup_denied'}
        for text,expected in samples.items():
            d=StartupDiagnostics();d.stderr(text.encode());result=d.finish(1)
            self.assertIn(expected,result['reason_codes']);self.assertEqual(result['stderr_retained_bytes'],0)

    def test_stderr_flood_is_drained_bounded_and_cannot_hang_stdin(self):
        r=self.client("import sys,time;sys.stderr.write('x'*1000000);sys.stderr.flush();time.sleep(10)",prompt='p'*1000000,timeout=.5)
        d=r['startup_diagnostics'];self.assertFalse(r['ok'])
        self.assertIn('diagnostic_limit',d['reason_codes'])
        self.assertLessEqual(d['stderr_bytes_observed'],LIMIT+65536)

    def test_public_error_message_is_reason_coded_only(self):
        r=self.client("import json;print(json.dumps({'type':'error','message':'unsupported_model PRIVATE'}))")
        self.assertIn('model_unavailable',r['startup_diagnostics']['reason_codes'])
        self.assertNotIn('PRIVATE',json.dumps(r))

    def test_success_stderr_and_missing_completion_are_not_conflated(self):
        r=self.client("import json,sys;sys.stderr.write('progress');print(json.dumps({'type':'turn.started'}));print(json.dumps({'type':'turn.completed'}))")
        self.assertTrue(r['ok']);self.assertEqual(r['startup_diagnostics']['reason_codes'],[])
        r=self.client("print('not json')")
        self.assertIn('malformed_public_stream',r['startup_diagnostics']['reason_codes'])

    def test_spawn_timeout_and_signal_failures_are_retained(self):
        r=native_run(['/private/tmp/no-v51-client'], '',1,'controlled')
        self.assertIn('spawn_unavailable',r['startup_diagnostics']['reason_codes'])
        self.assertIsNone(r['startup_diagnostics']['exit_code'])
        r=self.client('import time;time.sleep(10)',timeout=.05)
        self.assertIn('timeout',r['startup_diagnostics']['reason_codes'])
        r=self.client('import os,signal;os.kill(os.getpid(),signal.SIGTERM)')
        self.assertEqual(r['startup_diagnostics']['signal'],signal.SIGTERM)

    def test_private_or_malformed_diagnostic_fields_rejected(self):
        value=StartupDiagnostics().finish(0)
        for fields in ({'stderr':'PRIVATE'},{'exit_code':True},{'reason_codes':['raw secret']}):
            with self.assertRaises(ValueError):validate({**value,**fields})

    def test_symlink_launcher_is_resolved_without_changing_policy(self):
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as d:
            link=Path(d)/'client';link.symlink_to(sys.executable)
            self.assertEqual(resolved_executable(str(link)),str(Path(sys.executable).resolve()))
            r=native_run([str(link),'-c',"import json;print(json.dumps({'type':'turn.started'}));print(json.dumps({'type':'turn.completed'}))"],'',2,'controlled')
            self.assertTrue(r['ok'])

    def test_model_free_probe_sends_no_turn_or_private_task(self):
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as d:
            executable=Path(d)/'client'
            executable.write_text('#!'+sys.executable+'\n'+'''import json,sys
for line in sys.stdin:
    request=json.loads(line)
    assert request['method'] in {'initialize','initialized','thread/start'}
    if request['method']=='initialize':print(json.dumps({'id':1,'result':{}}),flush=True)
    if request['method']=='thread/start':
        assert request['params']['ephemeral'] is True
        assert request['params']['approvalPolicy']=='never'
        print(json.dumps({'id':2,'result':{'model':request['params']['model']}}),flush=True)
        break
''')
            executable.chmod(0o700)
            with portable_native_temp():r=probe_thread(str(executable),'controlled')
            self.assertTrue(r['initialize']);self.assertTrue(r['thread_configuration_ready'])
            self.assertTrue(r['model_matches']);self.assertEqual(r['model_calls'],0)


if __name__=='__main__':unittest.main()
