import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import capability_registry as reg
from workflow_router import route
from runtime_prepare import prepare, finalize

class FocusedDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.tools=self.root/'tools.json'
        self.entries=[
            {'provider':'local','name':'database','aliases':['sqlite-read'],'description':'Inspect SQLite query transactions'},
            {'provider':'cloud','name':'database','description':'Search cloud document storage'},
            {'provider':'decoy','name':'helper','description':'Help improve work with source query tools'},
            {'provider':'denied','name':'sqlite','description':'Inspect SQLite query transactions','permission':'denied'},
            {'provider':'revoked','name':'sqlite','description':'Inspect SQLite query transactions','revoked':True}]
        self.tools.write_text(json.dumps({'tools':self.entries})); self.snapshot=reg.build([],self.tools,'a'*40,'b'*64)

    def test_broad_query_rejects_weak_description_overlap(self):
        phrase='Please help improve SQLite query transactions'
        ordinary=reg.query(self.snapshot,phrase)
        focused=reg.query(self.snapshot,phrase,focused=True)
        self.assertIn('helper',[r['name'] for r in ordinary])
        self.assertEqual([(r['provider'],r['name']) for r in focused],[('local','database')])
        self.assertEqual(reg.query(self.snapshot,phrase),ordinary)

    def test_exact_alias_provider_and_ambiguous_names_preserve_scopes(self):
        self.assertEqual(reg.query(self.snapshot,'sqlite-read',focused=True)[0]['provider'],'local')
        self.assertEqual([r['provider'] for r in reg.query(self.snapshot,'cloud/database',focused=True)],['cloud'])
        self.assertEqual({r['provider'] for r in reg.query(self.snapshot,'database',focused=True)}, {'local','cloud'})
        self.assertTrue(all(r['permission']=='unknown' and r['trust']=='untrusted_metadata'
                            for r in reg.query(self.snapshot,'database',focused=True)))

    def test_negative_queries_do_not_force_activation_and_invalid_flags_fail(self):
        for phrase in ('Please help improve work','zoological specimen','source'):
            self.assertEqual(reg.query(self.snapshot,phrase,focused=True),[])
        with self.assertRaises(ValueError): reg.query(self.snapshot,'sqlite',focused='yes')
        with self.assertRaises(ValueError): route({'request':'sqlite'},focused_discovery=1)

    def test_verified_route_keeps_revocation_and_freshness_gates(self):
        task={'request':'Inspect SQLite query transactions','checks':['tests']}
        args={'capability_roots':[],'capability_tools_file':self.tools,
              'capability_revision':'a'*40,'capability_environment':'b'*64,'focused_discovery':True}
        found=route(task,self.snapshot,**args)['routing']
        self.assertEqual([r['provider'] for r in found['suggested_capabilities']],['local'])
        self.assertTrue(found['suggested_capabilities'][0]['requires_host_authorization'])
        self.entries[0]['revoked']=True
        self.tools.write_text(json.dumps({'tools':self.entries}))
        stale=route(task,self.snapshot,**args)['routing']
        self.assertEqual(stale['registry_freshness'],'stale')
        self.assertEqual(stale['suggested_capabilities'],[])
        current=reg.build([],self.tools,'a'*40,'b'*64)
        self.assertEqual(route(task,current,**args)['routing']['suggested_capabilities'],[])

    def test_opt_in_consolidated_preparation_binds_policy_and_preserves_checks(self):
        value={'task':{'request':'Please help improve SQLite query transactions','checks':['tests']},
               'scope':{'source_sha256':'c'*64,'provenance':{'kind':'synthetic','reference_sha256':'d'*64}},
               'binding':{'revision':'a'*40,'environment':'b'*64},'source_root':str(self.root),'source_ranges':[],
               'registry':{'roots':[],'tools_file':str(self.tools),'focused':True}}
        result=prepare(value)
        self.assertTrue(result['inputs']['registry']['focused'])
        self.assertEqual([r['provider'] for r in result['workflow']['routing']['suggested_capabilities']],['local'])
        self.assertFalse(result['permissions_granted'])
        self.assertFalse(finalize(result,[],'Run tests')['all_required_checks_passed'])
        value['registry']['focused']='yes'
        with self.assertRaises(ValueError): prepare(value)

    def test_trivial_tasks_never_initialize_registry(self):
        with patch('runtime_prepare.registry.build',side_effect=AssertionError('must stay optional')):
            result=prepare({'task':{'request':'Inspect source','checks':['tests']},'scope':{'source_sha256':'c'*64,'provenance':{'kind':'synthetic','reference_sha256':'d'*64}},
                            'binding':{'revision':'a'*40,'environment':'b'*64},
                            'source_root':str(self.root),'source_ranges':[]})
        self.assertFalse(result['activation']['recommended'])

if __name__=='__main__': unittest.main()
