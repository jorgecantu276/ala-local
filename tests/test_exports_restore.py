import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import restore_backup

class ExportAndRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.previous=server.DB
        server.DB=Path(self.temp.name)/'agenda.sqlite3';server.initialize()
        self.reservation=dict(kind='Vuelo',owner=0,origin='MAM & México',destination='MTY',start='2026-11-10T15:00:00Z',end='2026-11-10T19:00:00Z',status='Confirmada',notes='Notas completas con acentos y <texto>.')
    def tearDown(self):
        server.DB=self.previous;self.temp.cleanup()
    def backup(self):
        with server.connect() as c:
            return dict(format='ala-local-backup-v1',settings=server.settings(c),bookings=[dict(r) for r in c.execute('SELECT * FROM bookings')],history=[dict(r) for r in c.execute('SELECT * FROM history')])
    def test_restore_preserves_ids_history_and_keeps_previous_copy(self):
        saved=server.save_booking(self.reservation);backup=self.backup()
        source=Path(self.temp.name)/'backup.json';source.write_text(json.dumps(backup),'utf-8')
        server.save_booking({**saved,'status':'Cancelada'},saved['id'])
        with patch('restore_backup.urlopen',side_effect=OSError()):restore_backup.restore(source,True)
        restored=server.state()
        self.assertEqual(restored['bookings'][0]['id'],saved['id'])
        self.assertEqual(restored['bookings'][0]['status'],'Confirmada')
        self.assertEqual(len(restored['history']),1)
        self.assertEqual(len(list(Path(self.temp.name).glob('antes-de-restaurar-*'))),1)
    def test_invalid_backup_does_not_replace_current_database(self):
        server.save_booking(self.reservation);backup=self.backup();backup['bookings'][0]['owner']=9
        source=Path(self.temp.name)/'bad.json';source.write_text(json.dumps(backup),'utf-8')
        with patch('restore_backup.urlopen',side_effect=OSError()):
            with self.assertRaises(server.Problem):restore_backup.restore(source,True)
        self.assertEqual(server.state()['bookings'][0]['owner'],0)
    @unittest.skipUnless(shutil.which('node'),'Node required for PowerPoint export')
    def test_powerpoint_has_editable_slides_and_complete_notes(self):
        server.save_booking(self.reservation)
        report=server.report_data({'from':['2026-11-01'],'to':['2026-11-30']})
        raw=server.make_pptx(report)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            slides=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
            self.assertEqual(len(slides),3)
            texts=[]
            for n in slides:
                root=ET.fromstring(z.read(n));texts += [e.text for e in root.iter() if e.tag.endswith('}t') and e.text]
            self.assertIn('Notas completas con acentos y <texto>.',texts)
            self.assertIn('MAM & México - MTY',texts)
            self.assertIn('Inicio de uso: 10/11/2026 09:00\nLiberación / regreso: 10/11/2026 13:00','\n'.join(texts))

if __name__=='__main__':unittest.main()
