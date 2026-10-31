"""Ala Local: agenda privada de una aeronave. Solo escucha en loopback."""
from __future__ import annotations
import argparse
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data' / 'agenda.sqlite3'
DEFAULTS = dict(aircraft='Mi aeronave', model='', base='', people=['Persona 1', 'Persona 2'], buffer=30, timezone='America/Matamoros')
STATUSES = {'Tentativa', 'Confirmada', 'Completada', 'Cancelada'}

class Problem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status

@contextmanager
def connect():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c:
            yield c
    finally:
        c.close()

def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
          CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
          CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY, owner INTEGER, kind TEXT NOT NULL, origin TEXT NOT NULL,
            destination TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
            status TEXT NOT NULL, notes TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
            created TEXT NOT NULL, updated TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, booking_id TEXT, action TEXT, at TEXT, detail TEXT);
        ''')
        c.execute('INSERT OR IGNORE INTO settings(id,value) VALUES(1,?)', (json.dumps(DEFAULTS),))

def settings(c):
    r = c.execute('SELECT * FROM settings WHERE id=1').fetchone()
    return {**json.loads(r['value']), 'version': r['version']}

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def utc(value):
    try:
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError()
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if not d.tzinfo or not 2000 <= d.year <= 2100:
            raise ValueError()
        return d.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise Problem('Revisa las fechas y sus zonas horarias.')

def text_field(data, key, maxlen, required=False):
    v = data.get(key, '')
    if not isinstance(v, str):
        raise Problem('Campo de texto inválido: ' + key)
    v = v.strip()
    if len(v) > maxlen or (required and not v) or any(ord(ch) < 32 and ch not in '\n\t\r' for ch in v):
        raise Problem('Revisa el campo ' + key + ' y su longitud.')
    return v

def validate_booking(data):
    kind = data.get('kind')
    if kind not in ('Vuelo', 'Mantenimiento'):
        raise Problem('Selecciona vuelo o mantenimiento.')
    owner = data.get('owner')
    if kind == 'Vuelo' and (type(owner) is not int or owner not in (0, 1)):
        raise Problem('Cada vuelo debe pertenecer a una de las dos personas.')
    start, end = utc(data.get('start')), utc(data.get('end'))
    if end <= start:
        raise Problem('La liberación debe ser posterior al inicio de la reserva.')
    status = data.get('status')
    if status not in STATUSES:
        raise Problem('Estado de reserva inválido.')
    return dict(owner=owner if kind == 'Vuelo' else None, kind=kind,
                origin=text_field(data, 'origin', 80, kind == 'Vuelo'),
                destination=text_field(data, 'destination', 80, kind == 'Vuelo'),
                start=start.isoformat(timespec='seconds'), end=end.isoformat(timespec='seconds'),
                status=status, notes=text_field(data, 'notes', 2000))

def conflict(c, item, ignore=None, buffer=None):
    if item['status'] == 'Cancelada':
        return None
    margin = timedelta(minutes=settings(c)['buffer'] if buffer is None else buffer)
    for row in c.execute("SELECT * FROM bookings WHERE status != 'Cancelada' ORDER BY start"):
        if row['id'] == ignore:
            continue
        if utc(item['start']) < utc(row['end']) + margin and utc(item['end']) + margin > utc(row['start']):
            return dict(row)
    return None

def save_booking(data, booking_id=None):
    item = validate_booking(data)
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        old = c.execute('SELECT * FROM bookings WHERE id=?', (booking_id,)).fetchone() if booking_id else None
        if booking_id and not old:
            raise Problem('La reserva ya no existe.', 404)
        if old and data.get('version') != old['version']:
            raise Problem('La reserva cambió en otra ventana. Actualiza la agenda antes de editar.', 409)
        hit = conflict(c, item, booking_id)
        if hit:
            s = settings(c)
            person = s['people'][hit['owner']] if hit['kind'] == 'Vuelo' else 'mantenimiento'
            raise Problem('La aeronave está ocupada por ' + person + '. Revisa la agenda y el margen entre reservas.', 409)
        timestamp = now()
        if old:
            params = {**item, 'id': booking_id, 'updated': timestamp}
            c.execute('''UPDATE bookings SET owner=:owner,kind=:kind,origin=:origin,destination=:destination,
                         start=:start,end=:end,status=:status,notes=:notes,version=version+1,updated=:updated WHERE id=:id''', params)
        else:
            booking_id = secrets.token_hex(8)
            params = {**item, 'id': booking_id, 'created': timestamp, 'updated': timestamp}
            c.execute('''INSERT INTO bookings(id,owner,kind,origin,destination,start,end,status,notes,created,updated)
                         VALUES(:id,:owner,:kind,:origin,:destination,:start,:end,:status,:notes,:created,:updated)''', params)
        c.execute('INSERT INTO history(booking_id,action,at,detail) VALUES(?,?,?,?)',
                  (booking_id, 'Edición' if old else 'Creación', timestamp, json.dumps(item, ensure_ascii=False)))
        return dict(c.execute('SELECT * FROM bookings WHERE id=?', (booking_id,)).fetchone())

def save_settings(data):
    people = data.get('people')
    if not isinstance(people, list) or len(people) != 2 or any(not isinstance(p, str) or not p.strip() or len(p.strip()) > 40 for p in people):
        raise Problem('Escribe los nombres de las dos personas (máximo 40 caracteres).')
    if people[0].strip().casefold() == people[1].strip().casefold():
        raise Problem('Usa nombres distintos para identificar a cada persona.')
    buffer = data.get('buffer')
    if type(buffer) is not int or not 0 <= buffer <= 1440:
        raise Problem('El margen debe estar entre 0 y 1440 minutos.')
    tz = text_field(data, 'timezone', 80, True)
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise Problem('Zona horaria desconocida. Ejemplo: America/Matamoros.')
    result = dict(aircraft=text_field(data, 'aircraft', 60, True), model=text_field(data, 'model', 80),
                  base=text_field(data, 'base', 80), people=[p.strip() for p in people], buffer=buffer, timezone=tz)
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if data.get('version') != settings(c)['version']:
            raise Problem('La configuración cambió. Actualiza la página.', 409)
        for item in c.execute("SELECT * FROM bookings WHERE status != 'Cancelada'").fetchall():
            if conflict(c, dict(item), item['id'], buffer):
                raise Problem('Ese margen genera conflictos entre reservas existentes. Ajusta primero las reservas.', 409)
        c.execute('UPDATE settings SET value=?,version=version+1 WHERE id=1', (json.dumps(result),))
        c.execute('INSERT INTO history(action,at,detail) VALUES(?,?,?)', ('Configuración', now(), json.dumps(result)))
        return settings(c)

def state():
    with connect() as c:
        return dict(settings=settings(c), bookings=[dict(x) for x in c.execute('SELECT * FROM bookings ORDER BY start')],
                    history=[dict(x) for x in c.execute('SELECT id,booking_id,action,at FROM history ORDER BY id DESC LIMIT 30')])

def report_data(query):
    snapshot = state()
    start = query.get('from', [''])[0]
    end = query.get('to', [''])[0]
    person = query.get('person', ['all'])[0]
    if person not in ('all', '0', '1'):
        raise Problem('Persona inválida.')
    tz = ZoneInfo(snapshot['settings']['timezone'])
    try:
        first = datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=tz)
        last = datetime.strptime(end, '%Y-%m-%d').replace(tzinfo=tz) + timedelta(days=1)
        if first >= last or (last-first).days > 3660:
            raise ValueError()
    except ValueError:
        raise Problem('Selecciona un periodo válido de hasta diez años.')
    items = [b for b in snapshot['bookings'] if b['status'] != 'Cancelada' and utc(b['start']) < last and utc(b['end']) > first
             and (person == 'all' or b['owner'] == int(person))]
    for b in items:
        b['person'] = snapshot['settings']['people'][b['owner']] if b['kind'] == 'Vuelo' else 'Mantenimiento'
        b['startLabel'] = utc(b['start']).astimezone(tz).strftime('%d/%m/%Y %H:%M')
        b['endLabel'] = utc(b['end']).astimezone(tz).strftime('%d/%m/%Y %H:%M')
        b['route'] = b['origin'] + ' - ' + b['destination'] if b['kind'] == 'Vuelo' else 'Bloqueo de mantenimiento'
    return dict(settings=snapshot['settings'], items=items, period=first.strftime('%d/%m/%Y')+' - '+(last-timedelta(days=1)).strftime('%d/%m/%Y'), generated=now())

def make_pdf(data):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('Brand', fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#1b7568'), spaceAfter=16))
    styles.add(ParagraphStyle('Detail', fontName='Helvetica', fontSize=9, leading=13, spaceAfter=5))
    styles.add(ParagraphStyle('Route', fontName='Helvetica-Bold', fontSize=15, leading=19, spaceAfter=8))
    p = lambda v, style='Detail': Paragraph(escape(str(v)).replace('\n', '<br/>'), styles[style])
    s = data['settings']
    story = [p('ALA LOCAL / PROGRAMA DE RESERVAS', 'Brand'), p(s['aircraft'], 'Title'),
             p(data['period']), p('Zona horaria: '+s['timezone']),
             p('Reservas: '+str(len(data['items']))+' / Margen entre usos: '+str(s['buffer'])+' minutos'), Spacer(1, 18)]
    if not data['items']:
        story.append(p('No hay reservas activas en el periodo seleccionado.'))
    for b in data['items']:
        content = [p(b['route'], 'Route'), p(b['person']+' / '+b['status']),
                   p('Inicio de uso: '+b['startLabel']), p('Liberación / regreso: '+b['endLabel'])]
        if b['notes']:
            content.append(p('Notas: '+b['notes']))
        # Notes may span pages; do not force an unbounded paragraph into a single page.
        story += [KeepTogether(content[:4]), *content[4:], Spacer(1, 18)]
    story += [Spacer(1, 16), p('Resumen de agenda. La confirmación operativa del vuelo se realiza por separado.')]
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#d4e0dd'))
        canvas.line(42, 39, A4[0]-42, 39)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#526761'))
        canvas.drawString(42, 25, 'Ala Local / '+s['aircraft'])
        canvas.drawRightString(A4[0]-42, 25, str(doc.page))
    SimpleDocTemplate(stream, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=52,
                      title='Programa de reservas - '+s['aircraft'], author='Ala Local').build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()

def make_pptx(data):
    config_path = ROOT / 'runtime.json'
    config = json.loads(config_path.read_text('utf-8')) if config_path.exists() else {'node': shutil.which('node')}
    if not config.get('node'):
        raise Problem('Instala Node.js y ejecuta npm ci para generar PowerPoint.', 503)
    with tempfile.TemporaryDirectory(prefix='export-', dir=DB.parent) as td:
        folder = Path(td)
        (folder / 'input.json').write_text(json.dumps(data, ensure_ascii=False), 'utf-8')
        result = subprocess.run([config['node'], str(ROOT/'export-presentation.mjs'), str(folder/'input.json'), str(folder/'programa.pptx')],
                                capture_output=True, timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            print(result.stderr.decode('utf-8', errors='replace')[-2000:], file=sys.stderr)
            raise Problem('No se pudo generar la presentación. Revisa el registro del servidor.', 500)
        return (folder/'programa.pptx').read_bytes()

class Handler(BaseHTTPRequestHandler):
    server_version = 'AlaLocal/1.0'
    def send(self, code, body, content_type='application/json; charset=utf-8', filename=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="'+filename+'"')
        self.end_headers()
        self.wfile.write(body)

    def check_local(self, mutation=False):
        allowed = {'127.0.0.1:'+str(self.server.server_port), 'localhost:'+str(self.server.server_port)}
        if self.headers.get('Host') not in allowed:
            raise Problem('Acceso local requerido.', 403)
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://'+host for host in allowed}:
            raise Problem('Origen no permitido.', 403)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Problem('Origen no permitido.', 403)
        if mutation and self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise Problem('Se requiere JSON.', 415)

    def body(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 24000:
                raise ValueError()
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeDecodeError):
            raise Problem('Solicitud inválida.')

    def do_GET(self):
        try:
            self.check_local()
            parsed = urlparse(self.path)
            path, q = parsed.path, parse_qs(parsed.query)
            if path == '/api/health':
                return self.send(200, {'app': 'ala-local', 'version': 1})
            if path == '/api/state':
                return self.send(200, state())
            if path == '/api/backup':
                with connect() as c:
                    data = dict(format='ala-local-backup-v1', exported=now(), settings=settings(c),
                                bookings=[dict(x) for x in c.execute('SELECT * FROM bookings')],
                                history=[dict(x) for x in c.execute('SELECT * FROM history')])
                return self.send(200, data, filename='ala-local-respaldo-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
            if path in ('/api/report.pdf', '/api/report.pptx'):
                data = report_data(q)
                if path.endswith('pdf'):
                    return self.send(200, make_pdf(data), 'application/pdf', 'programa-de-vuelos.pdf')
                return self.send(200, make_pptx(data), 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'programa-de-vuelos.pptx')
            static = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/favicon.ico': None}
            if path in static:
                if static[path] is None:
                    return self.send(204, b'')
                mime = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8', '/style.css': 'text/css; charset=utf-8'}[path]
                return self.send(200, (ROOT/'static'/static[path]).read_bytes(), mime)
            raise Problem('Página no encontrada.', 404)
        except Problem as e:
            self.send(e.status, {'error': e.message})
        except subprocess.TimeoutExpired:
            self.send(503, {'error': 'La presentación tardó demasiado. Inténtalo nuevamente.'})
        except Exception:
            import traceback
            traceback.print_exc()
            self.send(500, {'error': 'Ocurrió un error. Los datos guardados se conservan.'})

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def mutate(self):
        try:
            self.check_local(True)
            path = urlparse(self.path).path
            data = self.body()
            if self.command == 'POST' and path == '/api/bookings':
                return self.send(201, save_booking(data))
            if self.command == 'PUT' and re.fullmatch(r'/api/bookings/[0-9a-f]{16}', path):
                return self.send(200, save_booking(data, path.rsplit('/', 1)[1]))
            if self.command == 'PUT' and path == '/api/settings':
                return self.send(200, save_settings(data))
            raise Problem('Operación no disponible.', 404)
        except Problem as e:
            self.send(e.status, {'error': e.message})
        except sqlite3.OperationalError:
            self.send(503, {'error': 'La agenda está ocupada. Intenta guardar nuevamente.'})
        except Exception:
            import traceback
            traceback.print_exc()
            self.send(500, {'error': 'No se pudo guardar. Revisa los datos e intenta nuevamente.'})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8877)
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    global DB
    if args.data_dir:
        DB = args.data_dir.resolve()/'agenda.sqlite3'
    initialize()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Ala Local disponible en http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()

if __name__ == '__main__':
    main()
