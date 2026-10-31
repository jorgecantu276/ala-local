"""Restaura un respaldo JSON validado. Detén primero el servidor."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from urllib.request import urlopen
import server

def restore(source, replace=False, port=8877):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as r:
            if json.load(r).get('app')=='ala-local':
                raise ValueError('Detén el servidor antes de restaurar el respaldo.')
    except OSError:
        pass
    target=server.DB
    if target.exists() and not replace:
        raise ValueError('Ya existe una agenda. Agrega --replace para reemplazarla conservando una copia previa.')
    if source.stat().st_size > 50_000_000:
        raise ValueError('El respaldo supera el límite de 50 MB.')
    data=json.loads(source.read_text('utf-8-sig'))
    if data.get('format')!='ala-local-backup-v1':
        raise ValueError('Formato de respaldo desconocido.')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='restore-',dir=target.parent) as tmp:
        candidate=Path(tmp)/'agenda.sqlite3'
        try:
            server.DB=candidate
            server.initialize()
            server.save_settings({**data['settings'],'version':1})
            seen=set()
            for b in data['bookings']:
                if not re.fullmatch('[0-9a-f]{16}',b['id']) or b['id'] in seen:
                    raise ValueError('Identificador de reserva inválido o duplicado.')
                seen.add(b['id'])
                saved=server.save_booking(b)
                version=b.get('version',1)
                if type(version) is not int or version<1:
                    raise ValueError('Versión de reserva inválida.')
                with server.connect() as c:
                    c.execute('UPDATE bookings SET id=?,version=?,created=?,updated=? WHERE id=?',
                              (b['id'],version,server.utc(b['created']).isoformat(),server.utc(b['updated']).isoformat(),saved['id']))
            with server.connect() as c:
                c.execute('DELETE FROM history')
                for h in data.get('history',[]):
                    booking_id=h.get('booking_id')
                    if booking_id is not None and booking_id not in seen:
                        raise ValueError('El historial contiene una referencia inválida.')
                    action=server.text_field(h,'action',80,True)
                    detail=server.text_field(h,'detail',24000)
                    c.execute('INSERT INTO history(booking_id,action,at,detail) VALUES(?,?,?,?)',
                              (booking_id,action,server.utc(h['at']).isoformat(),detail))
        finally:
            server.DB=target
        if target.exists():
            prior=target.with_name('antes-de-restaurar-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
            with closing(sqlite3.connect(target)) as original, closing(sqlite3.connect(prior)) as backup:
                original.backup(backup)
        # Use SQLite's backup API so journal state cannot get out of sync with the main database.
        original=sqlite3.connect(candidate)
        destination=sqlite3.connect(target)
        try:
            original.backup(destination)
        finally:
            destination.close();original.close()
    return target

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('--replace',action='store_true')
    p.add_argument('--port',type=int,default=8877)
    a=p.parse_args()
    try: print('Agenda restaurada:',restore(a.source,a.replace,a.port))
    except (ValueError,KeyError,TypeError,OSError,server.Problem) as e: p.exit(1,str(e)+'\n')
