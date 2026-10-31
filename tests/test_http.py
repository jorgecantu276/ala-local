import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class QuietHandler(server.Handler):
    def log_message(self,*args): pass

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=server.DB
        server.DB=Path(self.temp.name)/'agenda.sqlite3';server.initialize()
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.http.server_port}'
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();server.DB=self.old;self.temp.cleanup()
    def get(self,path):
        return urlopen(self.url+path)
    def test_static_health_and_no_database_exposure(self):
        with self.get('/api/health') as r:self.assertEqual(json.load(r)['app'],'ala-local')
        with self.get('/') as r:self.assertIn(b'Agenda privada',r.read())
        with self.assertRaises(HTTPError) as e:self.get('/data/agenda.sqlite3')
        self.assertEqual(e.exception.code,404)
    def test_cross_origin_mutation_and_host_rejected(self):
        req=Request(self.url+'/api/bookings',method='POST',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://example.com'})
        with self.assertRaises(HTTPError) as e:urlopen(req)
        self.assertEqual(e.exception.code,403)
        req=Request(self.url+'/api/state',headers={'Host':'example.com'})
        with self.assertRaises(HTTPError) as e:urlopen(req)
        self.assertEqual(e.exception.code,403)
    def test_api_lifecycle_and_binary_downloads(self):
        item=dict(kind='Vuelo',owner=1,origin='MAM',destination='MTY',start='2026-11-10T15:00:00Z',end='2026-11-10T19:00:00Z',status='Confirmada',notes='')
        req=Request(self.url+'/api/bookings',method='POST',data=json.dumps(item).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req) as r:self.assertEqual(r.status,201)
        with self.get('/api/report.pdf?from=2026-11-01&to=2026-11-30') as r:
            self.assertEqual(r.headers['Content-Type'],'application/pdf');self.assertTrue(r.read().startswith(b'%PDF'))
        with self.get('/api/backup') as r:self.assertEqual(len(json.load(r)['bookings']),1)

if __name__=='__main__':unittest.main()
