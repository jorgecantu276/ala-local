import concurrent.futures
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

class AgendaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = server.DB
        server.DB = Path(self.temp.name)/'agenda.sqlite3'
        server.initialize()
    def tearDown(self):
        server.DB = self.previous
        self.temp.cleanup()
    def item(self, **changes):
        return dict(kind='Vuelo', owner=0, origin='MAM', destination='MTY',
                    start='2026-11-10T15:00:00Z', end='2026-11-10T19:00:00Z',
                    status='Tentativa', notes='Vuelo de prueba', **changes) if not changes else {**self.item(), **changes}
    def test_persistence_and_exactly_two_people(self):
        saved=server.save_booking(self.item())
        self.assertEqual(server.state()['bookings'][0]['id'], saved['id'])
        with self.assertRaises(server.Problem): server.save_booking(self.item(owner=2))
        with self.assertRaises(server.Problem): server.save_settings({**server.state()['settings'],'people':['Solo una']})
    def test_overlap_is_rejected_for_both_people(self):
        server.save_booking(self.item())
        for owner in (0,1):
            with self.assertRaises(server.Problem) as caught: server.save_booking(self.item(owner=owner))
            self.assertEqual(caught.exception.status,409)
    def test_interval_inside_an_existing_trip(self):
        server.save_booking(self.item())
        with self.assertRaises(server.Problem): server.save_booking(self.item(owner=1,start='2026-11-10T16:00:00Z',end='2026-11-10T17:00:00Z'))
    def test_inclusive_buffer_boundary_and_reverse_order(self):
        server.save_booking(self.item())
        server.save_booking(self.item(owner=1,start='2026-11-10T19:30:00Z',end='2026-11-10T21:00:00Z'))
        with self.assertRaises(server.Problem): server.save_booking(self.item(start='2026-11-10T13:00:00Z',end='2026-11-10T14:31:00Z'))
        server.save_booking(self.item(start='2026-11-10T13:00:00Z',end='2026-11-10T14:30:00Z'))
    def test_cancelled_releases_interval(self):
        saved=server.save_booking(self.item())
        server.save_booking({**saved,'status':'Cancelada'},saved['id'])
        server.save_booking(self.item(owner=1))
        self.assertEqual(len(server.state()['bookings']),2)
    def test_maintenance_blocks_aircraft(self):
        server.save_booking(self.item(kind='Mantenimiento',owner=None,origin='',destination=''))
        with self.assertRaises(server.Problem): server.save_booking(self.item(owner=1))
    def test_stale_edits_rejected(self):
        saved=server.save_booking(self.item())
        updated=server.save_booking({**saved,'status':'Confirmada'},saved['id'])
        self.assertEqual(updated['version'],2)
        with self.assertRaises(server.Problem): server.save_booking(saved,saved['id'])
    def test_invalid_times_and_owner_types(self):
        for change in [dict(end='2026-11-10T14:00:00Z'),dict(start='2026-11-10T15:00'),dict(start='invalid'),dict(owner=True),dict(notes='a\x00b')]:
            with self.assertRaises(server.Problem): server.save_booking(self.item(**change))
    def test_timezone_offsets_compare_as_instants(self):
        server.save_booking(self.item(start='2026-11-10T09:00:00-06:00',end='2026-11-10T13:00:00-06:00'))
        with self.assertRaises(server.Problem): server.save_booking(self.item(owner=1))
    def test_configuration_will_not_introduce_conflicts(self):
        server.save_booking(self.item())
        server.save_booking(self.item(owner=1,start='2026-11-10T19:30:00Z',end='2026-11-10T21:00:00Z'))
        with self.assertRaises(server.Problem): server.save_settings({**server.state()['settings'],'buffer':31})
        self.assertEqual(server.state()['settings']['buffer'],30)
    def test_concurrent_reservations_only_one_wins(self):
        def write(owner):
            try: server.save_booking(self.item(owner=owner)); return 'saved'
            except server.Problem as e: return e.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(write,[0,1]))
        self.assertCountEqual(results,['saved',409])
    def test_reports_include_multiday_overlap_exclude_cancelled(self):
        server.save_booking(self.item(start='2026-11-09T15:00:00Z',end='2026-11-12T19:00:00Z'))
        server.save_booking(self.item(status='Cancelada',owner=1))
        report=server.report_data({'from':['2026-11-10'],'to':['2026-11-10']})
        self.assertEqual(len(report['items']),1)
        self.assertEqual(report['items'][0]['person'],'Persona 1')
        self.assertEqual(len(server.report_data({'from':['2026-11-10'],'to':['2026-11-10'],'person':['1']})['items']),0)
    def test_pdf_handles_user_markup_and_long_notes(self):
        from pypdf import PdfReader
        import io
        server.save_booking(self.item(origin='<MAM &>', notes=('Nota con <etiquetas> & acentos áéñ.\n'*40)))
        report=server.report_data({'from':['2026-11-01'],'to':['2026-11-30']})
        document=PdfReader(io.BytesIO(server.make_pdf(report)))
        self.assertGreaterEqual(len(document.pages),1)
        self.assertIn('<MAM &>', ''.join(p.extract_text() for p in document.pages))
    def test_history_tracks_creation_and_edit(self):
        saved=server.save_booking(self.item());server.save_booking({**saved,'notes':'Cambio'},saved['id'])
        self.assertEqual([h['action'] for h in server.state()['history']],['Edición','Creación'])

if __name__=='__main__': unittest.main()
