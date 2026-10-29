"""Synthetic protocol-shaped controls, never native model measurements."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import dashboard_export as d
from headroom_compare import compare

FIXTURE=ROOT/'tests/dashboard/fixtures/codex-rollout.jsonl'
A,B,C='00000000-0000-4000-8000-00000000000a','00000000-0000-4000-8000-00000000000b','00000000-0000-4000-8000-00000000000c'
PRICES={'uncached_input_per_million':3,'cached_input_per_million':0.3,'output_per_million':15}


def session(thread,input_tokens,cached,model=None):
    rows=[json.loads(line) for line in FIXTURE.read_text().splitlines()]
    for row in rows:
        if row['type']=='session_meta':row['payload']['id']=thread
        if model and row['type']=='turn_context':row['payload']['model']=model
        info=row['payload'].get('info') if isinstance(row.get('payload'),dict) else None
        if isinstance(info,dict):
            for key in ('total_token_usage','last_token_usage'):
                info[key].update(input_tokens=input_tokens,cached_input_tokens=cached,output_tokens=20,total_tokens=input_tokens+20)
    return d.import_text('\n'.join(json.dumps(row) for row in rows))


def without_counter(document,key='cached_input_tokens'):
    document=copy.deepcopy(document)
    document['sessions'][0]['metrics'][key]={'value':None,'source':'unavailable','status':'unknown'}
    return document


class CompareTests(unittest.TestCase):
    def test_fewer_tokens_with_lost_cache_is_flagged_not_called_savings(self):
        # Compressor cuts input 1000 -> 600 but the cache hit drops 900 -> 100: uncached rises 100 -> 500.
        result=compare([session(A,1000,900)],[session(B,600,100)],PRICES)
        self.assertEqual(result['without']['mean']['uncached_input_tokens'],100)
        self.assertEqual(result['with']['mean']['uncached_input_tokens'],500)
        self.assertEqual(set(result['flags']),{'fewer_input_tokens_but_not_fewer_uncached','cache_fraction_decreased',
                                               'fewer_input_tokens_but_configured_cost_not_lower'})
        self.assertEqual(result['cost_basis'],'configured_scenario')
        self.assertNotIn('saving',json.dumps(result['flags']))

    def test_genuine_reduction_raises_no_flags(self):
        result=compare([session(A,1000,500)],[session(B,600,400)],PRICES)
        self.assertEqual(result['flags'],[])
        self.assertLess(result['with']['mean_configured_cost'],result['without']['mean_configured_cost'])

    def test_invalid_prices_rejected(self):
        bad=[{**PRICES,'output_per_million':float('nan')},{**PRICES,'output_per_million':float('inf')},
             {**PRICES,'output_per_million':float('-inf')},{**PRICES,'output_per_million':-1},
             {**PRICES,'output_per_million':True},{**PRICES,'output_per_million':'15'},
             {**PRICES,'output_per_million':10**400},{**PRICES,'output_per_million':1e308},
             {k:v for k,v in PRICES.items() if k!='output_per_million'},{**PRICES,'cache_write_per_million':1},
             {'input':3,'cached_input':0.3,'output':15},[3,0.3,15]]
        for prices in bad:
            with self.subTest(prices=prices),self.assertRaisesRegex(d.ImportError,'^invalid_prices$'):
                compare([session(A,1000,500)],[session(B,600,400)],prices)

    def test_cost_refused_for_mixed_models_and_cache_writes(self):
        mixed=compare([session(A,1000,500)],[session(B,600,400,model='gpt-other')],PRICES)
        self.assertEqual((mixed['cost_basis'],mixed['cost_unavailable_reason']),('unavailable','mixed_or_unknown_provider_model'))
        self.assertIsNone(mixed['with']['mean_configured_cost'])
        writes=session(B,600,400);writes['sessions'][0]['metrics']['cache_creation_input_tokens']={'value':50,'source':'x','status':'observed'}
        result=compare([session(A,1000,500)],[writes],PRICES)
        self.assertEqual(result['cost_unavailable_reason'],'cache_write_billing_unresolved')
        self.assertEqual(compare([session(A,1000,500)],[session(B,600,400)])['cost_unavailable_reason'],'prices_not_configured')

    def test_incomplete_sessions_excluded_once_and_never_averaged(self):
        partial=without_counter(session(C,5,0))
        result=compare([session(A,1000,500),partial,partial],[session(B,600,400)],PRICES)
        self.assertEqual(result['without']['complete_sessions'],1)
        self.assertEqual(result['without']['incomplete_sessions_excluded'],1)
        self.assertEqual(result['without']['mean']['input_tokens'],1000)
        empty=compare([partial],[session(B,600,400)],PRICES)
        self.assertIsNone(empty['without']['mean'])
        self.assertIsNone(empty['without']['cache_fraction'])
        self.assertEqual(empty['flags'],['arm_without_complete_sessions'])
        self.assertEqual(empty['cost_unavailable_reason'],'arm_without_complete_sessions')

    def test_conflicting_or_shared_sessions_rejected(self):
        with self.assertRaisesRegex(d.ImportError,'^session_in_both_arms$'):compare([session(A,10,5)],[session(A,10,5)])
        with self.assertRaisesRegex(d.ImportError,'^conflicting_session$'):compare([session(A,10,5),session(A,11,5)],[session(B,10,5)])
        with self.assertRaisesRegex(d.ImportError,'^conflicting_session$'):compare([session(A,10,5),without_counter(session(A,10,5))],[session(B,10,5)])

    def test_duplicate_import_counted_once(self):
        a=session(A,1000,500)
        self.assertEqual(compare([a,a],[session(B,800,500)])['without']['complete_sessions'],1)

    def test_cli_errors_are_bounded_codes(self):
        def run(*args):
            p=subprocess.run([sys.executable,str(ROOT/'scripts/headroom_compare.py'),*args],capture_output=True,text=True,timeout=30)
            self.assertEqual((p.returncode,p.stderr),(2,''));return json.loads(p.stdout)
        with tempfile.TemporaryDirectory() as folder:
            binary=Path(folder)/'private-name.jsonl';binary.write_bytes(b'\xff\xfe')
            garbage=Path(folder)/'garbage.jsonl';garbage.write_text('PRIVATE_CANARY not json')
            self.assertEqual(run('--without',str(FIXTURE),'--with',str(FIXTURE)),{'error':'session_in_both_arms'})
            self.assertEqual(run('--without',str(FIXTURE),'--with',folder+'/absent'),{'error':'unreadable_file'})
            self.assertEqual(run('--without',str(FIXTURE),'--with',folder),{'error':'unreadable_file'})
            self.assertEqual(run('--without',str(FIXTURE),'--with',str(binary)),{'error':'unsupported_file'})
            self.assertNotIn('PRIVATE_CANARY',json.dumps(run('--without',str(FIXTURE),'--with',str(garbage))))
            self.assertEqual(run('--without',str(FIXTURE),'--with',str(FIXTURE),'--prices','{bad'),{'error':'invalid_prices'})
            self.assertEqual(run('--without',str(FIXTURE),'--with',str(FIXTURE),'--prices','NaN'),{'error':'invalid_prices'})


if __name__=='__main__':unittest.main()
