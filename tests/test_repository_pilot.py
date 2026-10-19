import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import repository_pilot as pilot
from execution_state import checkpoint,packet

CALLER='Sources/DynamicIsland/App/DynamicIslandApp.swift'
FILES={pilot.TARGET:(('\n'*120)+'''private func schedule() {
let request = TimerCompletionNotificationRequest(delay: Self.timeInterval(for: remaining))
let status = await client.authorizationStatus()
notificationSoundGeneration = generation
}
private func cancel() {}
''').encode(),CALLER:b'coordinator.handle(event)', 'Package.swift':b'// synthetic unit-test snapshot'}
ANSWER={'finding':'confirmed','source_files':[pilot.TARGET,CALLER],
        'facts':{'delay_captured_before_authorization':True,'elapsed_authorization_time_deducted':False,'completion_can_delegate_sound_to_late_request':True},
        'correction':{'preserve_countdown_deadline':True,'recompute_delay_after_authorization':True,'expired_request_must_not_suppress_local_sound':True},
        'regression':{'countdown_seconds':10,'authorization_wait_seconds':8,'expected_remaining_seconds':2,'cover_expired_authorization':True,'cover_cancellation':True}}


class RepositoryPilotTests(unittest.TestCase):
    def test_default_plan_has_no_execution_or_writes(self):
        with tempfile.TemporaryDirectory() as d:
            p=subprocess.run([sys.executable,str(ROOT/'scripts/repository_pilot.py')],cwd=d,capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertFalse(json.loads(p.stdout)['execution_performed'])
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_api_budget_rejects_before_source_or_provider(self):
        with patch.object(pilot,'collect',side_effect=AssertionError('Must not inspect')):
            for trials,timeout in ((True,1),(0,1),(3,1),(1,True),(1,0),(1,181)):
                with self.subTest(trials=trials,timeout=timeout),self.assertRaises(ValueError):
                    pilot.execute('/absent','1'*40,'model','/absent','/absent',trials,timeout)

    def test_grade_checks_facts_types_references_and_math(self):
        self.assertTrue(pilot.grade(json.dumps(ANSWER),FILES))
        for category,field,value in (('facts','elapsed_authorization_time_deducted',True),('facts','delay_captured_before_authorization',1),('regression','expected_remaining_seconds',10),('regression','cover_cancellation',False)):
            a=copy.deepcopy(ANSWER);a[category][field]=value
            self.assertFalse(pilot.grade(json.dumps(a),FILES))
        a=copy.deepcopy(ANSWER);a['source_files']=[pilot.TARGET,'private.txt']
        self.assertFalse(pilot.grade(json.dumps(a),FILES))
        a={'finding':'confirmed','source_files':[pilot.TARGET,CALLER],'cause':'Authorization cannot delay sound','correction':'No remaining correction needed','regression':'No clock test needed'}
        self.assertFalse(pilot.grade(json.dumps(a),FILES))

    def test_oracle_refuses_changed_source_and_hash_tracks_dirty_state(self):
        pilot.oracle(FILES)
        changed={**FILES,pilot.TARGET:FILES[pilot.TARGET].replace(b'let request =',b'let replacement =')}
        self.assertNotEqual(pilot.source_hash(FILES),pilot.source_hash(changed))
        with self.assertRaises(ValueError):pilot.oracle(changed)

    def test_source_protection_refuses_modified_files_and_parent_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            for n,data in FILES.items():
                p=folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            self.assertTrue(pilot.unchanged(folder,FILES))
            (folder/'Package.swift').write_text('modified')
            self.assertFalse(pilot.unchanged(folder,FILES))
            (folder/'Package.swift').write_bytes(FILES['Package.swift'])
            (folder/'extra').symlink_to('/private/tmp')
            self.assertFalse(pilot.unchanged(folder,FILES))

    def test_artifact_permissions_do_not_extend_to_other_hidden_state(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            for n,data in FILES.items():
                p=folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            run=folder/'.tuck-bit/run';run.mkdir(parents=True);(run/'receipt.json').write_text('{}')
            self.assertTrue(pilot.unchanged(folder,FILES))
            outside=folder/'.tuck-bit/outside.json';outside.write_text('{}')
            self.assertFalse(pilot.unchanged(folder,FILES));outside.unlink()
            self.assertTrue(pilot.treatment_valid(folder,'baseline',None))
            (folder/'.agents').mkdir();(folder/'.agents/unapproved.txt').write_text('bad')
            self.assertFalse(pilot.treatment_valid(folder,'baseline',None))

    def test_checkpoint_verifies_real_packet_and_remains_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);target=folder/pilot.TARGET;target.parent.mkdir(parents=True);target.write_bytes(FILES[pilot.TARGET])
            run=folder/'.tuck-bit/run';run.mkdir(parents=True)
            task={'request':'Investigate source','checks':['independent review']}
            p=packet(task,pilot.selections(FILES[pilot.TARGET]),folder,'1'*40,'2'*64)
            c=checkpoint(p,[],'Independent review')
            (run/'checkpoint.json').write_text(json.dumps(c))
            self.assertTrue(pilot.validate_workflow(folder,task,'1'*40,'2'*64))
            compact=packet(task,pilot.selections(FILES[pilot.TARGET]),folder,'1'*40,'2'*64,max_chars=6000)
            (run/'checkpoint.json').write_text(json.dumps(checkpoint(compact,[],'review')))
            self.assertTrue(pilot.validate_workflow(folder,task,'1'*40,'2'*64),
                            'Supported context budgets must not be mistaken for stale workflow evidence')
            c['all_required_checks_passed']=True
            (run/'checkpoint.json').write_text(json.dumps(c))
            self.assertFalse(pilot.validate_workflow(folder,task,'1'*40,'2'*64))

    def test_six_fake_arms_are_isolated_journaled_and_resume_without_replay(self):
        seen=[];real_check_output=subprocess.check_output
        def fake(command,prompt,timeout,case,approved_runtime_paths=()):
            folder=Path(command[command.index('-C')+1]);self.assertNotIn(folder,seen);seen.append(folder)
            self.assertIn('workspace-write',command);self.assertNotIn('--ignore-rules',command)
            active='$tuck-bit' in prompt
            if approved_runtime_paths:
                import re
                env=re.search(r'--environment ([a-f0-9]{64})',prompt)[1]
                task=json.loads((folder/'TASK.json').read_text())
                p=packet(task,pilot.selections(FILES[pilot.TARGET]),folder,'1'*40,env)
                (folder/'.tuck-bit/run/checkpoint.json').write_text(json.dumps(checkpoint(p,[],'review')))
            return {'ok':True,'events':[{'type':'turn.started'},{'type':'turn.completed','usage':{'input_tokens':10,'cached_input_tokens':0,'output_tokens':2}}],
                    'final_text':json.dumps(ANSWER),'skill_read':active,'plan_read':bool(approved_runtime_paths),'violations':0,'duration_ms':1,'result_bytes':10,
                    'runtime_evidence':{k:int(bool(approved_runtime_paths)) for k in ('plan_task','workflow_router','packet','checkpoint','adaptive_execution')}}
        with tempfile.TemporaryDirectory() as d,patch.object(pilot,'collect',return_value=FILES),patch.object(pilot,'native_run',side_effect=fake), \
             patch.object(pilot.subprocess,'check_output',side_effect=lambda command,*a,**k:'codex-cli 0.0.0-synthetic\n'
                          if command==['codex','--version'] else real_check_output(command,*a,**k)) as version:
            runtime=Path(d)/'runtime.zip';runtime.write_bytes(b'synthetic archive')
            journal=Path(d)/'journal.json'
            result=pilot.execute(d,'1'*40,'model',runtime,journal)
            version.assert_any_call(['codex','--version'],text=True)
            self.assertEqual(len(result['runs']),6)
            self.assertTrue(all(r['trace']['outcome']['verified'] for r in result['runs']))
            resumed=pilot.execute(d,'1'*40,'model',runtime,journal,resume=True)
            self.assertEqual(len(seen),6);self.assertEqual(resumed['runs'],result['runs'])
            runtime.write_bytes(b'changed runtime')
            with self.assertRaises(ValueError):pilot.execute(d,'1'*40,'model',runtime,journal,resume=True)


if __name__=='__main__':unittest.main()
