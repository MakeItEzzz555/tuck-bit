"""Deterministic protocol-shaped controls, never native model measurements."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dashboard_export as d

FIXTURE = Path(__file__).parent/'dashboard/fixtures/codex-rollout.jsonl'


class CodexImportTests(unittest.TestCase):
    def setUp(self):
        self.rows = [json.loads(line) for line in FIXTURE.read_text().splitlines()]

    def load(self, rows=None):
        return d.import_text('\n'.join(json.dumps(row) for row in (rows if rows is not None else self.rows)))

    def test_cumulative_reports_are_not_summed_or_added_to_last(self):
        row = self.load()['sessions'][0]
        for key,value in {'input_tokens':160,'cached_input_tokens':60,'uncached_input_tokens':100,'output_tokens':20,'session_elapsed_ms':8000,'tool_calls_observed':2,'error_events_observed':1,'usage_snapshots_observed':3}.items():
            self.assertEqual(row['metrics'][key]['value'],value,key)
        self.assertNotIn('wall_ms',row['metrics'])
        self.assertEqual(row['metrics']['uncached_input_tokens']['status'],'derived')
        self.assertEqual(row['provider'],'OpenAI')
        self.assertEqual(row['model'],'gpt-6.1-sol')
        self.assertIsNone(row['arm'])
        self.assertFalse(row['qualification']['qualified'])
        self.assertTrue(all(stage['state']=='unknown' for stage in row['activation']))

    def test_no_raw_private_fields_or_content_survive(self):
        document = self.load()
        output = json.dumps(document)
        for canary in ('PRIVATE_', 'call-private-id','patch-private-id','01234567-89ab','exec_command','base_instructions'):
            self.assertNotIn(canary,output)
        self.assertRegex(document['sessions'][0]['project'],r'^project:[a-f0-9]{24}$')
        self.assertEqual(d.import_document(document)['sessions'],document['sessions'])

    def test_hostile_fields_never_survive_even_with_every_capture_option(self):
        import dashboard_server
        rows=copy.deepcopy(self.rows)
        rows[0]['payload'].update(originator='SECRET_ACCOUNT', cli_version='SECRET_VERSION', instructions='SECRET_INSTRUCTIONS',
            git={'commit_hash':'SECRET_COMMIT','branch':'SECRET_BRANCH','repository_url':'https://SECRET_REPO'},
            cwd='/synthetic-workspace/project')
        rows[1:1]=[{'timestamp':'2026-10-18T10:00:01Z','type':kind,'payload':payload} for kind,payload in (
            ('response_item',{'type':'reasoning','summary':[{'type':'summary_text','text':'SECRET_REASONING'}],'encrypted_content':'SECRET_ENC'}),
            ('response_item',{'type':'function_call_output','call_id':'SECRET_OUTPUT_CALL','output':'SECRET_TOOL_OUTPUT sk-SECRETKEY'}),
            ('response_item',{'type':'local_shell_call','call_id':'shell-1','action':{'type':'exec','command':['cat','/synthetic-workspace/.env']}}),
            ('event_msg',{'type':'agent_message','message':'SECRET_AGENT_TEXT'}),
            ('event_msg',{'type':'user_message','message':'SECRET_USER_TEXT'}),
            ('event_msg',{'type':'error','message':'SECRET_ERROR <script>alert(1)</script>'}),
            ('event_msg',{'type':'token_count','info':None,'rate_limits':{'plan_type':'SECRET_PLAN','primary':{'used_percent':12}}}))]
        document=dashboard_server.sanitize_capture(self.load(rows),{key:True for key in dashboard_server.CAPTURE})
        output=json.dumps(document)
        for canary in ('SECRET','sk-','<script','/synthetic-workspace/','.env'):
            self.assertNotIn(canary,output)
        session=document['sessions'][0]
        self.assertEqual(session['metrics']['error_events_observed']['value'],2)
        self.assertEqual(session['metrics']['tool_calls_observed']['value'],3)

    def test_duplicate_source_and_tool_calls_are_stable(self):
        first = self.load()
        self.assertEqual(first,self.load())
        self.rows.insert(4,copy.deepcopy(self.rows[3]))
        row = self.load()['sessions'][0]
        self.assertEqual(row['metrics']['tool_calls_observed']['value'],2)

    def test_conflicting_call_rejected(self):
        extra=copy.deepcopy(self.rows[3]);extra['payload']['name']='apply_patch';self.rows.append(extra)
        with self.assertRaisesRegex(d.ImportError,'codex_conflicting_call'):self.load()

    def test_counter_reset_rejected(self):
        self.rows[-2]['payload']['info']['total_token_usage']={'input_tokens':1,'cached_input_tokens':0,'output_tokens':1,'total_tokens':2}
        with self.assertRaisesRegex(d.ImportError,'codex_counter_reset'):self.load()

    def test_invalid_counters_rejected(self):
        for bad in (-1,0.5,True,'4',10**16):
            with self.subTest(bad=bad):
                rows=copy.deepcopy(self.rows);rows[-2]['payload']['info']['total_token_usage']['input_tokens']=bad
                with self.assertRaises(d.ImportError):self.load(rows)

    def test_inconsistent_total_and_cache_rejected(self):
        for field,value,reason in [('cached_input_tokens',1000,'cache_exceeds_input'),('total_tokens',999,'inconsistent_total')]:
            rows=copy.deepcopy(self.rows);rows[-2]['payload']['info']['total_token_usage'][field]=value
            with self.assertRaisesRegex(d.ImportError,reason):self.load(rows)

    def test_missing_final_fields_are_unknown_not_filled_from_earlier(self):
        del self.rows[-2]['payload']['info']['total_token_usage']['cached_input_tokens']
        row=self.load()['sessions'][0]
        self.assertIsNone(row['metrics']['cached_input_tokens']['value'])
        self.assertIsNone(row['metrics']['uncached_input_tokens']['value'])
        self.assertIn('cached_input_tokens is absent',' '.join(row['limitations']))

    def test_incremental_only_is_unavailable(self):
        for row in self.rows:
            if row['payload'].get('type')=='token_count':del row['payload']['info']['total_token_usage']
        row=self.load()['sessions'][0]
        self.assertIsNone(row['metrics']['input_tokens']['value'])
        self.assertIn('Incremental-only',' '.join(row['limitations']))

    def test_last_incremental_cannot_leave_stale_cumulative_totals(self):
        del self.rows[-2]['payload']['info']['total_token_usage']
        self.assertIsNone(self.load()['sessions'][0]['metrics']['input_tokens']['value'])

    def test_absent_usage_keeps_events(self):
        rows=[row for row in self.rows if row['payload'].get('type')!='token_count']
        row=self.load(rows)['sessions'][0]
        self.assertIsNone(row['metrics']['output_tokens']['value'])
        self.assertEqual(len(row['events']),2)

    def test_mixed_or_unknown_models_disable_attribution(self):
        for model in ('gpt-another-model', 'PRIVATE MODEL', None):
            rows=copy.deepcopy(self.rows);rows.append({'timestamp':rows[-1]['timestamp'],'type':'turn_context','payload':{'model':model}})
            self.assertIsNone(self.load(rows)['sessions'][0]['model'])
        del self.rows[1]
        self.assertIsNone(self.load()['sessions'][0]['model'])

    def test_usage_before_model_context_cannot_be_priced_as_later_model(self):
        context=self.rows.pop(1);self.rows.append(context)
        self.assertIsNone(self.load()['sessions'][0]['model'])

    def test_unknown_provider_not_guessed(self):
        self.rows[0]['payload']['model_provider']='private-provider-canary'
        document=self.load()
        self.assertIsNone(document['sessions'][0]['provider'])
        self.assertNotIn('private-provider-canary',json.dumps(document))

    def test_forked_and_multiple_sessions_rejected(self):
        for key in ('forked_from_id','parent_thread_id','history_base'):
            rows=copy.deepcopy(self.rows);rows[0]['payload'][key]='some-parent'
            with self.assertRaisesRegex(d.ImportError,'inherited_history'):self.load(rows)
        with self.assertRaisesRegex(d.ImportError,'multiple_sessions'):self.load(self.rows+[self.rows[0]])

    def test_metadata_identity_and_timestamp_required(self):
        for key,value in [('id','not-a-uuid'),('timestamp',None),('timestamp','2026-02-30T10:00:00Z')]:
            rows=copy.deepcopy(self.rows);rows[0]['payload'][key]=value
            with self.assertRaises(d.ImportError):self.load(rows)
        with self.assertRaisesRegex(d.ImportError,'session_meta_required'):self.load(self.rows[1:])

    def test_timestamp_order_preserved_without_fake_latency(self):
        self.rows[-1]['timestamp']='2026-10-18T10:00:01Z'
        row=self.load()['sessions'][0]
        self.assertIsNone(row['metrics']['session_elapsed_ms']['value'])
        self.assertIsNone(row['events'][0]['success'])
        self.assertIsNone(row['events'][0]['duration_ms'])

    def test_missing_record_timestamp_prevents_a_false_complete_duration(self):
        del self.rows[-1]['timestamp']
        row=self.load()['sessions'][0]
        self.assertIsNone(row['metrics']['session_elapsed_ms']['value'])
        self.assertIn('timestamps are absent',' '.join(row['limitations']))

    def test_duplicate_json_keys_and_malformed_lines_rejected(self):
        for text in (FIXTURE.read_text()+'{"type":"x","type":"y"}', FIXTURE.read_text()+'{broken', '[]\n{}'):
            with self.assertRaises(d.ImportError):d.import_text(text)

    def test_broken_later_line_is_distinct_from_non_json_file(self):
        with self.assertRaisesRegex(d.ImportError,'^codex_malformed_line$'):d.import_text(FIXTURE.read_text()+'{broken')
        with self.assertRaisesRegex(d.ImportError,'^invalid_json$'):d.import_text('{broken\n'+FIXTURE.read_text())
        for text in ('{"a":1}\n{broken','[1]\n{broken','1\n{broken','"x"\n{broken'):
            with self.assertRaisesRegex(d.ImportError,'^invalid_json$'):d.import_text(text)

    def test_every_codex_import_rejection_code_has_specific_guidance(self):
        import re
        source=(Path(d.__file__)).read_text()
        codex=source[source.index('def import_text'):source.index('def _import_document')]
        codes=set(re.findall(r"_fail\('([a-z_]+)'\)",codex))|{'invalid_json','duplicate_json_key','invalid_number','size_limit'}
        app=(Path(d.ROOT)/'web/js/app.js').read_text()
        guidance=app[app.index('function importDiagnostic'):app.index('async function importFiles')]
        self.assertEqual(sorted(code for code in codes if code+':' not in guidance),[])

    def test_oversize_and_deep_input_rejected(self):
        with self.assertRaisesRegex(d.ImportError,'size_limit'):d.import_text(' '* (d.MAX_BYTES+1))
        with self.assertRaises(d.ImportError):d.import_text('['*2000+'0'+']'*2000)

    def test_single_metadata_record_imports_with_unknown_usage(self):
        document=d.import_text(json.dumps(self.rows[0]))
        self.assertEqual(len(document['sessions']),1)
        self.assertIsNone(document['sessions'][0]['metrics']['input_tokens']['value'])


if __name__=='__main__':unittest.main()
