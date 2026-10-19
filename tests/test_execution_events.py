"""Controlled public events prove classification and privacy, never model efficiency."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import execution_events as ee
from provider_events import public_tool_event, codex_execution, codex_trace
from trace_profiler import profile, ProfileError
from benchmark_runner import native_run

KEY = b'k'*32


def event(identity, command='cat sample.py', output='answer\n', code=0, phase='completed', **extra):
    return public_tool_event({'type':'item.'+phase,'item':{'id':identity,'type':'command_execution',
        'command':command,'aggregated_output':output,'exit_code':code,**extra}})


def read(observer, folder, identity, command='cat sample.py', output='answer\n', **extra):
    observer(event(identity,command,phase='started'), folder)
    observer(event(identity,command,output,**extra),folder)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.root=Path(self.temp.name);(self.root/'sample.py').write_text('answer\n')
        self.observer=ee.Observer(KEY,'controlled_public_events')

    def tearDown(self): self.temp.cleanup()

    def summary(self, reviews=None): return ee.summarize(self.observer.export(True),reviews)

    def test_unchanged_read_is_potential_not_proven_waste(self):
        read(self.observer,self.root,'a');read(self.observer,self.root,'b')
        summary=self.summary();last=summary['context_observations'][-1]
        self.assertTrue(last['previously_available_to_agent'])
        self.assertEqual(last['classification'],'identical_unchanged_source_reread')
        self.assertIsNone(last['independently_unnecessary'])
        self.assertEqual(summary['context_counts']['independently_unnecessary'],0)

    def test_source_change_is_not_potential_redundancy(self):
        read(self.observer,self.root,'a');(self.root/'sample.py').write_text('changed\n')
        read(self.observer,self.root,'b',output='changed\n')
        last=self.summary()['context_observations'][-1]
        self.assertTrue(last['source_changed']);self.assertFalse(last['previously_available_to_agent'])
        self.assertEqual(last['classification'],'changed_source_reread')

    def test_change_during_operation_cannot_credit_delivery(self):
        self.observer(event('a',phase='started'),self.root)
        (self.root/'sample.py').write_text('changed\n')
        self.observer(event('a',output='changed\n'),self.root)
        e=self.observer.export(True)['calls'][0]['evidence']
        self.assertFalse(e['delivered']);self.assertIsNone(e['bytes'])

    def test_range_and_file_are_separate_evidence(self):
        (self.root/'sample.py').write_text('one\ntwo\nthree\n')
        read(self.observer,self.root,'a',command="sed -n '1,2p' sample.py",output='one\ntwo\n')
        read(self.observer,self.root,'b',command='head -n 1 sample.py',output='one\n')
        self.assertTrue(all(c['evidence']['delivered'] for c in self.observer.export(True)['calls']))
        self.assertTrue(all(r['classification']=='first_observed_access' for r in self.summary()['context_observations']))
        self.assertIsNone(self.observer.read("sed -n '99,100p' sample.py",self.root))
        (self.root/'empty').write_bytes(b'')
        self.assertEqual(self.observer.read('cat empty',self.root)['selector'],
                         self.observer.read('head -n 1 empty',self.root)['selector'])

    def test_equivalent_readers_share_ranges_without_merging_equal_text_at_different_lines(self):
        (self.root/'sample.py').write_bytes(b'same\nsame\n')
        for i,command in enumerate(('cat sample.py','head -n 99 sample.py',"sed -n '1,2p' sample.py",'tail -n 99 sample.py')):
            read(self.observer,self.root,str(i),command=command,output='same\nsame\n')
        self.assertEqual(self.summary()['context_counts']['potential_redundant_unchanged_rereads'],3)
        for i,command in enumerate(('head -n 1 sample.py','tail -n 1 sample.py')):
            read(self.observer,self.root,'part'+str(i),command=command,output='same\n')
        self.assertTrue(all(r['classification']=='first_observed_access' for r in self.summary()['context_observations'][-2:]))

    def test_truncated_recovery_and_mismatched_output(self):
        read(self.observer,self.root,'a',output='ans',truncated=True)
        read(self.observer,self.root,'b')
        self.assertEqual(self.summary()['context_observations'][-1]['classification'],'truncated_output_recovery')
        read(self.observer,self.root,'c',output='wrong')
        self.assertEqual(self.summary()['context_observations'][-1]['classification'],'unknown_purpose_reread')
        read(self.observer,self.root,'d',truncated=True)
        self.assertFalse(self.observer.export(True)['calls'][-1]['evidence']['delivered'])

    def test_verification_and_relevance_require_independent_attestation(self):
        read(self.observer,self.root,'a');read(self.observer,self.root,'b')
        identity=self.observer.export(True)['calls'][-1]['id']
        reviews={identity:{'receipt':'a'*64,'purpose':'required_verification','relevance':'relevant','unnecessary':False}}
        s=self.summary(reviews)
        self.assertEqual(s['context_observations'][-1]['classification'],'required_verification')
        self.assertEqual(s['context_counts']['potential_redundant_unchanged_rereads'],0)
        reviews[identity]['unnecessary']=True
        with self.assertRaises(ProfileError):self.summary(reviews)

    def test_worker_duplicate_does_not_imply_shared_context(self):
        read(self.observer,self.root,'a')
        worker=ee.Observer(KEY,'controlled_public_events','worker-1');read(worker,self.root,'b')
        value=self.observer.export(True);value['calls']+=worker.export(True)['calls']
        last=ee.summarize(value)['context_observations'][-1]
        self.assertTrue(last['observed_in_other_agent']);self.assertFalse(last['previously_available_to_agent'])
        self.assertEqual(last['classification'],'first_observed_access')

    def test_missing_worker_identity_does_not_imply_context_available(self):
        self.observer=ee.Observer(KEY,'controlled_public_events',None)
        read(self.observer,self.root,'a');read(self.observer,self.root,'b')
        last=self.summary()['context_observations'][-1]
        self.assertIsNone(last['previously_available_to_agent'])
        self.assertEqual(last['classification'],'unknown_purpose_reread')

    def test_failures_unfinished_starts_and_unknown_durations_retained(self):
        self.observer(event('a',code=1),self.root)
        self.observer(event('b',phase='started'),self.root)
        value=self.observer.export(True);self.assertFalse(value['complete'])
        self.assertIsNone(value['calls'][0]['duration_ms'])
        self.assertEqual(sum(c['success'] is False for c in value['calls']),1)
        self.assertEqual(sum(c['success'] is None for c in value['calls']),1)

    def test_escaped_or_unsupported_commands_never_claim_source_reads(self):
        outside=self.root.parent/'outside-v5-source'
        for command in ('cat ../outside-v5-source','cat sample.py | head','python3 -c "print(1)"','rg answer .'):
            self.assertIsNone(self.observer.read(command,self.root))
        (self.root/'link.py').symlink_to(self.root/'sample.py')
        self.assertIsNone(self.observer.read('cat link.py',self.root))
        self.assertFalse(outside.exists())

    def test_model_link_swap_and_hardlink_cannot_read_outside_source(self):
        import os
        outside=self.root/'private-controlled';outside.write_text('unapproved fixture bytes')
        original_open=os.open
        def swapped(path,*args,**kwargs):
            if path=='sample.py':
                (self.root/'sample.py').unlink();(self.root/'sample.py').symlink_to(outside)
            return original_open(path,*args,**kwargs)
        with patch.object(ee.os,'open',side_effect=swapped):
            self.assertIsNone(self.observer.read('cat sample.py',self.root))
        (self.root/'sample.py').unlink();os.link(outside,self.root/'sample.py')
        self.assertIsNone(self.observer.read('cat sample.py',self.root))

    def test_no_raw_commands_paths_source_or_payload_persist(self):
        read(self.observer,self.root,'id_PRIVATE')
        value=json.dumps(self.observer.export(True))
        for private in ('sample.py','answer','cat ','id_PRIVATE',str(self.root)):
            self.assertNotIn(private,value)
        c=self.observer.export(True)['calls'][0]
        self.assertEqual(c['output_bytes'],7);self.assertIsNone(c['evidence']['tokens'])

    def test_missing_output_cannot_prove_delivery_or_result_verification(self):
        self.observer({'phase':'started','id':'a','type':'command_execution','command':'cat sample.py'},self.root)
        self.observer({'phase':'completed','id':'a','type':'command_execution','command':'cat sample.py','success':True},self.root)
        self.assertFalse(self.observer.export(True)['calls'][0]['evidence']['delivered'])

    def test_capability_lifecycle_never_infers_unobserved_stages(self):
        (self.root/'SKILL.md').write_text('answer\n')
        read(self.observer,self.root,'a',command='cat SKILL.md')
        self.observer({'phase':'completed','id':'b','type':'mcp_tool_call','success':True,'capability':'server/tool'},self.root)
        stages=list(self.summary()['capability_lifecycle'].values())
        self.assertEqual(sum(s['instructions_read'] is True for s in stages),1)
        self.assertTrue(all(s['result_verified'] is None and s['selected'] is None for s in stages))

    def test_malformed_schema_duplicate_events_and_private_fields_rejected(self):
        read(self.observer,self.root,'a')
        with self.assertRaises(ProfileError):read(self.observer,self.root,'a')
        for change in ({'prompt':'secret'},{'id':'raw'},{'output_bytes':True},{'category':'raw command'}):
            value=self.observer.export(True);value['calls'][0].update(change)
            with self.assertRaises(ProfileError):ee.summarize(value)

    def test_profiler_and_export_import_have_explicit_coverage_limits(self):
        source=[{'type':'turn.started'}, {'type':'item.completed','item':{'type':'command_execution','id':'a',
                 'command':'cat sample.py','exit_code':0,'aggregated_output':'answer\n'}}, {'type':'turn.completed'}]
        execution=codex_execution(source,KEY)
        self.assertIsNone(execution['calls'][0]['evidence'])
        result=profile(codex_trace(source,execution=execution))
        self.assertEqual(result['reported_metrics']['tool_invocations'],1)
        self.assertEqual(result['execution']['coverage']['file_range_coverage'],'unknown')
        repeated=codex_execution(source+source,KEY)
        self.assertEqual(len(repeated['calls']),2)
        self.assertNotEqual(repeated['calls'][0]['id'],repeated['calls'][1]['id'])

    def test_native_streamer_extension_uses_controlled_subprocess_only(self):
        producer=self.root/'producer.py'
        messages=[{'type':'turn.started'},{'type':'item.started','item':{'type':'command_execution','id':'a','command':'cat sample.py'}},
                  {'type':'item.completed','item':{'type':'command_execution','id':'a','command':'cat sample.py','exit_code':0,'aggregated_output':'answer\n'}},
                  {'type':'turn.completed'}]
        producer.write_text('import json,time\nfor e in '+repr(messages)+':\n print(json.dumps(e),flush=True)\n time.sleep(0.02)\n')
        result=native_run([sys.executable,str(producer),'-C',str(self.root)],'',3,'controlled',execution_observer=self.observer)
        self.assertTrue(result['ok'])
        self.assertTrue(self.observer.export(True)['calls'][0]['evidence']['delivered'])


if __name__=='__main__':unittest.main()
