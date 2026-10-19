"""HTTP confinement, explicit import consent and disabled collection boundaries."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dashboard_export as exporter
import dashboard_server as server


class DashboardServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.web=Path(self.temp.name)
        (self.web/'index.html').write_text('<main>Local Observatory</main>')
        (self.web/'app.js').write_text('export const safe = true;')
        (self.web/'.private.json').write_text('{"private":true}')
        (self.web/'secret.txt').write_text('private')
        (self.web/'linked.json').symlink_to(self.web/'.private.json')
        self.http=server.Server(('127.0.0.1',0),web_root=self.web)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.port=self.http.server_address[1]

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path='/',method='GET',body=None,headers=None):
        client=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        client.request(method,path,body=body,headers=headers or {})
        response=client.getresponse();data=response.read();result=(response.status,dict(response.getheaders()),data)
        client.close();return result

    def test_selected_codex_jsonl_is_sanitized_and_capture_gated(self):
        fixture=Path(__file__).parent/'dashboard/fixtures/codex-rollout.jsonl'
        capture={key:False for key in server.CAPTURE}
        headers={'Content-Type':'application/json','X-Observatory-Import':'selected-file'}
        body=json.dumps({'document_text':fixture.read_text(),'capture':capture})
        code,_,data=self.request('/api/import','POST',body,headers)
        self.assertEqual(code,200)
        self.assertNotIn(b'PRIVATE_',data)
        row=json.loads(data)['sessions'][0]
        self.assertEqual(row['metrics']['input_tokens']['value'],160)
        self.assertEqual(row['events'],[])
        capture['tools']=True
        body=json.dumps({'document_text':fixture.read_text(),'capture':capture})
        code,_,data=self.request('/api/import','POST',body,headers)
        self.assertEqual(code,200)
        self.assertEqual(len(json.loads(data)['sessions'][0]['events']),2)
        malformed=fixture.read_text().replace('"input_tokens": 160','"input_tokens": 1')
        code,_,data=self.request('/api/import','POST',json.dumps({'document_text':malformed,'capture':capture}),headers)
        self.assertEqual(code,400)
        self.assertNotIn(b'PRIVATE_',data)

    def test_localhost_assets_csp_no_cors(self):
        code,headers,body=self.request()
        self.assertEqual(code,200);self.assertIn(b'Local Observatory',body)
        self.assertIn("connect-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertEqual(self.request('/app.js')[0],200)

    def test_no_arbitrary_file_or_symlink_or_hidden_access(self):
        for path in ('/secret.txt','/.private.json','/linked.json','/../scripts/dashboard_export.py',
                     '/%2e%2e/secret','/docs/evaluations/V51_NATIVE_RECEIPTS.json','/api/file?path=/etc/passwd','//etc/passwd'):
            self.assertEqual(self.request(path)[0],404,path)
        (self.web/'app.js').unlink();(self.web/'app.js').symlink_to(self.web/'secret.txt')
        self.assertEqual(self.request('/app.js')[0],404)

    def test_dns_rebinding_foreign_origin_and_fetch_denied(self):
        for headers in ({'Host':'attacker.test'}, {'Origin':'https://attacker.test'}, {'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request(headers=headers)[0],403)
        self.assertEqual(self.request(headers={'Host':f'localhost:{self.port}','Origin':f'http://localhost:{self.port}'})[0],200)

    def test_cross_site_top_level_browser_link_only(self):
        # A user clicking an external link should be able to open the local UI,
        # but that external page cannot fetch local receipts or post imports.
        nav={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'}
        for path in ('/', '/index.html'):
            code,headers,body=self.request(path,headers=nav)
            self.assertEqual(code,200)
            self.assertIn(b'Local Observatory',body)
            self.assertNotIn('Access-Control-Allow-Origin',headers)
        for path in ('/api/historical','/app.js','/index.html?controls=1'):
            self.assertEqual(self.request(path,headers=nav)[0],403,path)
        for headers in (
            {**nav,'Host':'attacker.invalid'},
            {**nav,'Origin':'https://chatgpt.com'},
            {**nav,'Sec-Fetch-Mode':'cors'},
            {**nav,'Sec-Fetch-Dest':'empty'},
            {**nav,'Sec-Fetch-Site':'same-site'},
            {'Sec-Fetch-Site':'cross-site'},
        ):
            self.assertEqual(self.request('/',headers=headers)[0],403,headers)
        self.assertEqual(self.request('/',method='HEAD',headers=nav)[0],403)
        self.assertEqual(self.request('/api/import','POST',headers={**nav,'X-Observatory-Import':'selected-file'})[0],403)

    def test_public_release_excludes_private_historical_receipts(self):
        # The public build ships no private research receipts, grader answers or control transcripts.
        for path in ('/api/historical','/api/historical?controls=1'):
            code,_,body=self.request(path)
            self.assertEqual(code,503)
            self.assertEqual(json.loads(body)['error'],'historical_source_unavailable')
        self.assertEqual(self.request('/api/historical?path=/private')[0],400)

    def test_import_requires_json_and_explicit_local_file_header(self):
        body=json.dumps({'schema':1,'events':[],'outcome':{'verified':False,'acceptance_checks_passed':False}})
        self.assertEqual(self.request('/api/import','POST',body,{'Content-Type':'application/json'})[0],403)
        headers={'Content-Type':'text/plain','X-Observatory-Import':'selected-file'}
        self.assertEqual(self.request('/api/import','POST',body,headers)[0],415)
        headers['Content-Type']='application/json'
        status,_,out=self.request('/api/import','POST',body,headers)
        self.assertEqual(status,200);self.assertEqual(len(json.loads(out)['sessions']),1)
        self.assertEqual(self.request('/api/import','POST',body,{**headers,'Origin':'https://attacker.test'})[0],403)

    def test_errors_never_echo_private_input(self):
        body=json.dumps({'prompt':'PRIVATESECRET','path':'/private/data'})
        headers={'Content-Type':'application/json','X-Observatory-Import':'selected-file'}
        status,_,out=self.request('/api/import','POST',body,headers)
        self.assertEqual(status,400);self.assertNotIn(b'PRIVATESECRET',out);self.assertNotIn(b'/private',out)
        self.assertEqual(json.loads(out),{'error':'unsupported_schema'})

    def test_disabled_capture_omits_events_no_collection_or_storage(self):
        trace={'schema':1,'events':[{'category':'tool_read','role':'root'}],
               'outcome':{'verified':False,'acceptance_checks_passed':False}}
        capture={k:False for k in server.CAPTURE}
        body=json.dumps({'document':trace,'capture':capture})
        headers={'Content-Type':'application/json','X-Observatory-Import':'selected-file'}
        with mock.patch.object(exporter,'read_selected',side_effect=AssertionError('must not scan source files')):
            status,_,out=self.request('/api/import','POST',body,headers)
        self.assertEqual(status,200)
        row=json.loads(out)['sessions'][0]
        self.assertEqual(row['events'],[]);self.assertEqual(row['context'],{})
        self.assertFalse(row['qualification']['qualified'])
        self.assertTrue(all(s['state']=='unknown' for s in row['activation']))
        self.assertEqual(sorted(p.name for p in self.web.iterdir()),['.private.json','app.js','index.html','linked.json','secret.txt'])

    def test_escaped_envelope_of_file_under_limit_is_accepted(self):
        fixture=Path(__file__).parent/'dashboard/fixtures/codex-rollout.jsonl'
        rows=[json.loads(line) for line in fixture.read_text().splitlines()]
        rows[0]['payload']['base_instructions']={'text':'"\\'*int(exporter.MAX_BYTES*0.2)}
        text='\n'.join(json.dumps(row) for row in rows)
        body=json.dumps({'document_text':text,'capture':{key:False for key in server.CAPTURE}})
        self.assertLess(len(text.encode()),exporter.MAX_BYTES);self.assertGreater(len(body.encode()),exporter.MAX_BYTES)
        headers={'Content-Type':'application/json','X-Observatory-Import':'selected-file'}
        code,_,data=self.request('/api/import','POST',body,headers)
        self.assertEqual(code,200);self.assertNotIn(b'base_instructions',data)
        code,_,data=self.request('/api/import','POST',json.dumps({'document_text':'[1]\n{broken','capture':{key:False for key in server.CAPTURE}}),headers)
        self.assertEqual((code,json.loads(data)),(400,{'error':'invalid_json'}))
        raw=json.dumps({'schema':exporter.SCHEMA,'padding':'x'*(exporter.MAX_BYTES+10)})
        self.assertEqual(self.request('/api/import','POST',raw,headers)[0],413)

    def test_oversized_request_and_unsupported_method(self):
        headers={'Content-Type':'application/json','X-Observatory-Import':'selected-file','Content-Length':str(server.MAX_IMPORT_BODY+1)}
        self.assertEqual(self.request('/api/import','POST',b'',headers)[0],413)
        self.assertEqual(self.request('/api/import','OPTIONS')[0],405)
        self.assertEqual(self.request('/api/import','DELETE')[0],405)


    def test_document_text_envelope_preserves_duplicate_key_rejection(self):
        capture={name:False for name in server.CAPTURE}
        raw='{"schema":1,"schema":1,"events":[],"outcome":{"verified":false,"acceptance_checks_passed":false}}'
        headers={'Content-Type':'application/json','X-Observatory-Import':'selected-file'}
        status,_,body=self.request('/api/import','POST',json.dumps({'document_text':raw,'capture':capture}),headers)
        self.assertEqual(status,400);self.assertEqual(json.loads(body)['error'],'duplicate_json_key')
        valid='{"schema":1,"events":[],"outcome":{"verified":false,"acceptance_checks_passed":false}}'
        status,_,body=self.request('/api/import','POST',json.dumps({'document_text':valid,'capture':capture}),headers)
        self.assertEqual(status,200);self.assertEqual(len(json.loads(body)['sessions']),1)

    def test_nonloopback_bind_denied(self):
        with self.assertRaises(ValueError):server.Server(('0.0.0.0',0),web_root=self.web)


if __name__=='__main__':unittest.main()
