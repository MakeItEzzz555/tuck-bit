"""Checkpoint safety controls; intrinsic hashes never replace live source checks."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import execution_state as state

class CheckpointSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'source.py').write_text('before\n')
        self.task = {'request':'Inspect synthetic source', 'checks':['tests'], 'constraints':['Local only']}

    def packet(self, task=None, env='b'*64):
        return state.packet(self.task if task is None else task,
                            [{'path':'source.py','start':1,'end':1}],self.root,'a'*40,env)

    def receipt(self, packet):
        return {'check':'tests','result':'passed','binding':packet['binding'],
                'packet_sha256':packet['sha256'],'evidence_sha256':'c'*64}

    def resign(self, value):
        value['sha256'] = state.digest({k:v for k,v in value.items() if k!='sha256'})

    def test_empty_checks_remain_incomplete_and_cannot_be_forged_green(self):
        p = self.packet({'request':'Inspect synthetic source','checks':[]})
        result = state.checkpoint(p, [], 'Define acceptance checks')
        self.assertFalse(result['all_required_checks_passed'])
        state.validate_checkpoint(result)
        result['all_required_checks_passed'] = True
        self.resign(result)
        with self.assertRaises(ValueError): state.validate_checkpoint(result)

    def test_changed_contract_or_environment_requires_a_new_chain(self):
        p = self.packet(); first = state.checkpoint(p, [self.receipt(p)], 'Review')
        for key, value in [('checks',['other']),('constraints',['Network allowed']),
                           ('forbidden_operations',['delete']),('approvals',['ask before edit']),
                           ('host','codex'),('model','different-model')]:
            with self.subTest(key=key):
                task = dict(self.task, **{key:value}); after = self.packet(task)
                with self.assertRaises(ValueError): state.checkpoint(after, [], 'Review', first)
                self.assertEqual(state.checkpoint(after, [], 'Review')['sequence'], 1)
        with self.assertRaises(ValueError): state.checkpoint(self.packet(env='d'*64), [], 'Review', first)

    def test_changed_source_can_continue_only_with_fresh_bound_receipts(self):
        p = self.packet(); old = self.receipt(p); first = state.checkpoint(p, [old], 'Edit')
        (self.root/'source.py').write_text('after\n')
        fresh = self.packet()
        with self.assertRaises(ValueError): state.validate_packet(p,self.root,'a'*40,'b'*64)
        with self.assertRaises(ValueError): state.checkpoint(fresh, [old], 'Review', first)
        result = state.checkpoint(fresh, [self.receipt(fresh)], 'Review', first)
        self.assertTrue(result['all_required_checks_passed'])
        self.assertEqual(result['sequence'],2)
        state.validate_checkpoint(result)
        self.assertTrue(state.validate_packet(fresh,self.root,'a'*40,'b'*64))

    def test_checkpoint_rejects_nested_integrity_and_compiled_contract_tampering(self):
        p = self.packet(); original = state.checkpoint(p, [], 'Review')
        for change in ('excerpt','contract','schema'):
            result = copy.deepcopy(original); packet = result['packet']
            if change=='excerpt': packet['sources'][0]['excerpt']='forged'
            if change=='contract':
                packet['contract']['required_checks_verbatim']=[]
                self.resign(packet)
            if change=='schema':
                packet['schema']=True
                self.resign(packet)
            self.resign(result)
            with self.subTest(change=change):
                with self.assertRaises(ValueError): state.validate_checkpoint(result)

if __name__=='__main__': unittest.main()
