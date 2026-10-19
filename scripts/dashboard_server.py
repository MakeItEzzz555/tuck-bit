#!/usr/bin/env python3
"""Serve only Observatory assets and explicitly selected sanitized JSON on loopback."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import socket
from urllib.parse import urlsplit, unquote

import dashboard_export as exporter

WEB = exporter.ROOT / 'web'
MAX_BODY = exporter.MAX_BYTES
# The JSON envelope escapes quotes, backslashes and newlines; import_text still enforces MAX_BYTES on the text.
MAX_IMPORT_BODY = 2 * exporter.MAX_BYTES + 1024
CAPTURE = {'discovery','delivery','invocation','tools','context','qualification'}
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"


def sanitize_capture(document, capture):
    if not isinstance(capture,dict) or set(capture)!=CAPTURE or any(type(v) is not bool for v in capture.values()):
        raise exporter.ImportError('invalid_capture_configuration')
    for row in document['sessions']:
        for event in row.get('events',[]):
            if not capture['context']:event['evidence']=None
            if not capture['discovery'] and not capture['invocation']:event['capabilities']=[]
            elif not capture['discovery']:
                event['capabilities']=[c for c in event.get('capabilities',[]) if c.get('stage')=='invoked']
            elif not capture['invocation']:
                event['capabilities']=[c for c in event.get('capabilities',[]) if c.get('stage')!='invoked']
        if not capture['tools']:row['events']=[]
        if not capture['context']:row['context']={}
        for stage in row.get('activation',[]):
            group='delivery' if stage['stage'].startswith('delivery') else 'invocation' if stage['stage']=='invocation' else 'discovery'
            if not capture[group] and stage['state']!='not_applicable':
                stage.update(state='unknown',note='Evidence details omitted by import privacy settings.',provenance='capture_disabled',events=[])
        if not capture['qualification']:
            row['qualification']={'qualified':False,'evaluator':'capture_settings','reasons':['qualification_import_disabled']}
        row.setdefault('limitations',[]).append('Import detail coverage follows explicit local capture settings; no background collection is performed.')
    if not capture['qualification']:
        for pair in document['comparisons']:
            pair.update(qualified=False,quality_qualified=False,evaluator='capture_settings',reasons=['qualification_import_disabled'])
    return document


class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True

    def __init__(self,address,handler=None,web_root=WEB):
        if address[0] not in {'127.0.0.1','localhost'}:
            raise ValueError('loopback_only')
        self.web_root=Path(web_root).resolve()
        # The inventory is frozen at startup. Repository, diagnostics and arbitrary filesystem paths are never routable.
        self.assets={}
        if self.web_root.is_dir():
            for path in self.web_root.rglob('*'):
                if path.is_file() and path.suffix in {'.html','.css','.js','.svg','.json','.woff2','.png','.ico'} and not any(part.startswith('.') for part in path.relative_to(self.web_root).parts):
                    if not any(p.is_symlink() for p in (path,*path.parents)):
                        self.assets['/'+path.relative_to(self.web_root).as_posix()]=path
        super().__init__(address,handler or Handler)


class Handler(BaseHTTPRequestHandler):
    server_version='TuckBitObservatory'
    sys_version=''
    protocol_version='HTTP/1.1'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self,*args):
        # Requests may contain private strings; keep local diagnostics categorical.
        pass

    def _allowed(self,write=False):
        port=self.server.server_address[1]
        hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
        host=self.headers.get('Host')
        if host not in hosts:return False
        origin=self.headers.get('Origin')
        if origin is not None and origin!=f'http://{host}':return False
        if write and self.headers.get('X-Observatory-Import')!='selected-file':return False
        fetch=self.headers.get('Sec-Fetch-Site')
        if fetch is not None and fetch not in {'same-origin','none'}:
            # A user following a link from another site may have Sec-Fetch-Site:
            # cross-site. Permit ONLY a top-level GET navigation to the static
            # document; never permit external subresource/API/import requests.
            # Host and Origin validation above still prevents DNS rebinding and
            # cross-origin requests with an explicit foreign Origin header.
            is_document_navigation = (not write and self.command == 'GET'
                and self.path in {'/', '/index.html'}
                and self.headers.get('Origin') is None
                and fetch == 'cross-site'
                and self.headers.get('Sec-Fetch-Mode') == 'navigate'
                and self.headers.get('Sec-Fetch-Dest') == 'document')
            if not is_document_navigation:return False
        return True

    def _send(self,status,body=b'',kind='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',CSP)
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Connection','close')
        self.end_headers()
        self.close_connection=True
        if self.command!='HEAD':self.wfile.write(body)

    def _error(self,status,code):
        self._send(status,json.dumps({'error':code}).encode())

    def do_HEAD(self):self.do_GET()

    def do_GET(self):
        if not self._allowed():return self._error(403,'origin_denied')
        target=urlsplit(self.path)
        name=unquote(target.path)
        if target.fragment or '\\' in name or '..' in name.split('/') or '%' in name or any(p.startswith('.') for p in name.split('/') if p):
            return self._error(404,'not_found')
        if name=='/api/historical':
            if target.query not in {'','controls=1'}:return self._error(400,'invalid_query')
            try:body=json.dumps(exporter.historical(target.query=='controls=1'),allow_nan=False).encode()
            except (ValueError,OSError,KeyError):return self._error(503,'historical_source_unavailable')
            return self._send(200,body)
        if target.query:return self._error(404,'not_found')
        if name=='/':name='/index.html'
        path=self.server.assets.get(name)
        if path is None:return self._error(404,'not_found')
        try:
            if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():return self._error(404,'not_found')
            body=path.read_bytes()
            if len(body)>MAX_BODY:return self._error(413,'asset_size_limit')
        except OSError:return self._error(404,'not_found')
        kind=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        self._send(200,body,kind+('; charset=utf-8' if path.suffix in {'.html','.css','.js','.json','.svg'} else ''))

    def do_POST(self):
        if not self._allowed(write=True):return self._error(403,'origin_denied')
        if self.path!='/api/import':return self._error(404,'not_found')
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self._error(415,'json_required')
        length=self.headers.get('Content-Length','')
        if not length.isdecimal() or len(length)>10:return self._error(411,'length_required')
        size=int(length)
        if not 0<size<=MAX_IMPORT_BODY:return self._error(413,'size_limit')
        try:
            raw=self.rfile.read(size)
            if len(raw)!=size:return self._error(400,'incomplete_body')
            value=exporter.parse_bytes(raw,MAX_IMPORT_BODY)
            # Only escaped document_text gets envelope headroom; other bodies keep the original bound.
            if size>MAX_BODY and not (isinstance(value,dict) and set(value)=={'document_text','capture'}):return self._error(413,'size_limit')
            capture=None
            if isinstance(value,dict) and set(value) in ({'document','capture'},{'document_text','capture'}):
                capture=value['capture']
                if 'document_text' in value:
                    if not isinstance(value['document_text'],str):raise exporter.ImportError('invalid_document_text')
                    result=exporter.import_text(value['document_text'])
                else:result=exporter.import_document(value['document'])
            else:result=exporter.import_document(value)
            if capture is not None:result=sanitize_capture(result,capture)
            self._send(200,json.dumps(result,allow_nan=False).encode())
        except exporter.ImportError as error:self._error(400,str(error))
        except (ValueError,TypeError,KeyError,AttributeError,OSError,TimeoutError):self._error(400,'invalid_document')

    def do_OPTIONS(self):self._error(405,'method_not_allowed')
    def do_PUT(self):self._error(405,'method_not_allowed')
    def do_DELETE(self):self._error(405,'method_not_allowed')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args(argv)
    if not 0<=args.port<=65535:parser.error('port must be between 0 and 65535')
    try:server=Server(('127.0.0.1',args.port))
    except OSError:
        print('Observatory could not bind the local port. Choose --port with an unused port.')
        return 2
    print(f'TuckBit Observatory: http://127.0.0.1:{server.server_address[1]} (local only; no background session collection)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0


if __name__=='__main__':raise SystemExit(main())
