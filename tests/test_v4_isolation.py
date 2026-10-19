"""Policy validation tests make no client/model calls or sandbox changes."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import v4_isolation as isolation
from native_fixture import portable_native_temp


class IsolationTests(unittest.TestCase):
    def setUp(self):
        context=portable_native_temp();context.__enter__()
        self.addCleanup(context.__exit__,None,None,None)
    def observed(self, writable=True):
        return {'workspace':True,'outside':False,'evaluator':False,'symlink_escape':False,
                'workspace_write':writable,'outside_write':False,'protected_write':False}

    def results(self, values):
        return [subprocess.CompletedProcess([],0,'codex-cli 0.163.0\n',''),
                subprocess.CompletedProcess([],0,json.dumps(values),'')]

    def test_policy_closes_host_temp_network_and_retains_native_protections(self):
        args=isolation.arguments()
        self.assertIn('default_permissions="v4"',args)
        policy=args[3]
        for value in ['extends=":workspace"','":root"="deny"','":minimal"="read"',
                      '":tmpdir"="deny"','":slash_tmp"="deny"','network={enabled=false}']:
            self.assertIn(value,policy)
        self.assertIn('approval_policy="never"',args)
        self.assertNotIn('--ignore-rules',args)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',args)

    def test_successful_canaries_pin_client_and_policy_without_model(self):
        for writable in (True,False):
            with mock.patch.object(isolation.platform,'system',return_value='Darwin'), \
                 mock.patch.object(isolation.subprocess,'run',side_effect=self.results(self.observed(writable))) as run:
                result=isolation.preflight(writable=writable)
                self.assertTrue(result['verified']);self.assertEqual(result['model_calls'],0)
                commands=[c.args[0] for c in run.call_args_list]
                self.assertTrue(all('exec' not in command for command in commands))
                self.assertIn('--include-managed-config',commands[1])
                self.assertNotIn('--strict-config',commands[1])

    def test_every_denial_and_protected_write_must_pass(self):
        for key in self.observed():
            values=self.observed();values[key]=not values[key]
            with self.subTest(key=key),mock.patch.object(isolation.platform,'system',return_value='Darwin'), \
                 mock.patch.object(isolation.subprocess,'run',side_effect=self.results(values)):
                with self.assertRaisesRegex(ValueError,'canary failed'):
                    isolation.preflight()

    def test_unavailable_client_platform_and_malformed_probe_fail_closed(self):
        with mock.patch.object(isolation.platform,'system',return_value='Linux'):
            with self.assertRaises(ValueError):isolation.preflight()
        for completed in [subprocess.CompletedProcess([],1,'','PRIVATE'),subprocess.CompletedProcess([],0,'codex-cli 0.1.0','')]:
            with mock.patch.object(isolation.platform,'system',return_value='Darwin'),mock.patch.object(isolation.subprocess,'run',return_value=completed):
                with self.assertRaises(ValueError):isolation.preflight()
        result=self.results(self.observed());result[1].stdout='PRIVATE_NOT_JSON'
        with mock.patch.object(isolation.platform,'system',return_value='Darwin'),mock.patch.object(isolation.subprocess,'run',side_effect=result):
            with self.assertRaisesRegex(ValueError,'no model launched') as error:isolation.preflight()
            self.assertNotIn('PRIVATE',str(error.exception))


if __name__=='__main__':unittest.main()
