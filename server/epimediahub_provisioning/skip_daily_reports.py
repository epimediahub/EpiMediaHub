"""Append-only EpiScene audit log and immutable 07:00 Europe/Berlin reports.

SQL triggers observe every writer, including old workers and dashboard reviews.
The dashboard only reads prepared reports; it never scans the catalogue or starts
an analysis. Provider credentials, URLs and media payloads are not collected.
"""
from __future__ import annotations

import collections
import copy
from datetime import date, datetime, time as clock, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import statistics
import time
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Berlin')
VERSION = 1
SQL_NOW = "((julianday('now')-2440587.5)*86400.0)"
FINISHED = {'done', 'review', 'no_match', 'no_reference', 'failed', 'unmatched'}
KINDS = {'intro': 'Intro', 'recap': 'Rückblick', 'outro': 'Abspann'}


def clean(value):
    """Defense in depth for exported evidence, user titles and status strings."""
    if isinstance(value, dict):
        return {str(k): ('[entfernt]' if re.search(
            r'password|passwd|secret|token|username|authorization|cookie|api_key|headers|config_json|url|frames_json|words_json', str(k), re.I)
            else clean(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(?:https?|rtsp|ftp)://[^\s<>"\']+', '[URL entfernt]', value, flags=re.I)
        value = re.sub(r'(?i)\b(password|passwd|secret|token|username|authorization)\s*[:=]\s*[^\s,;]+',
                       r'\1=[entfernt]', value)
        return value
    return value


def encode(value):
    return json.dumps(clean(value), ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _object(alias, fields):
    return 'json_object(' + ','.join("'" + f + "'," + alias + '.' + f for f in fields.split()) + ')'


def migrate(con):
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='episcene_report_meta'").fetchone():
        if con.execute("SELECT 1 FROM episcene_report_meta WHERE name='schema' AND value=?", (str(VERSION),)).fetchone():
            return
    playlist_table = ('skip_analysis_playlists' if con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='skip_analysis_playlists'").fetchone() else 'customer_playlists')
    con.executescript('''
      CREATE TABLE IF NOT EXISTS episcene_report_meta(name TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS episcene_report_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL,
        asset_key TEXT NOT NULL DEFAULT '', record_id INTEGER, payload TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS episcene_report_time ON episcene_report_events(at,id);
      CREATE INDEX IF NOT EXISTS episcene_report_record ON episcene_report_events(record_id,id);
      CREATE INDEX IF NOT EXISTS episcene_report_kind_time ON episcene_report_events(kind,at,id);
      CREATE TABLE IF NOT EXISTS episcene_report_active(job_id INTEGER PRIMARY KEY,started REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS episcene_daily_reports(
        day TEXT PRIMARY KEY, start_at REAL NOT NULL,end_at REAL NOT NULL,
        generated_at REAL NOT NULL,payload TEXT NOT NULL);
    ''')
    asset = """COALESCE((SELECT json_object('playlist_id',a.playlist_id,'playlist',p.name,
      'source_key',a.source_key,'title',a.title,'year',a.year,'season',a.season,'episode',a.episode,
      'duration_ms',a.duration_ms,'media_type',a.media_type,
      'language_priority',COALESCE((SELECT priority FROM skip_language_priority WHERE asset_key=a.asset_key),2))
      FROM skip_assets a LEFT JOIN """ + playlist_table + " p ON p.id=a.playlist_id WHERE a.asset_key=NEW.asset_key),'{}')"
    detail = "json_object('id',NEW.id,'status',NEW.status,'attempts',NEW.attempts,'detail',NEW.detail)"
    con.executescript(f'''
      CREATE TRIGGER IF NOT EXISTS episcene_report_job_start AFTER UPDATE OF status ON skip_jobs
      WHEN NEW.status='running' AND OLD.status<>'running' BEGIN
        INSERT OR REPLACE INTO episcene_report_active VALUES(NEW.id,{SQL_NOW});
      END;
      CREATE TRIGGER IF NOT EXISTS episcene_report_job AFTER UPDATE OF status ON skip_jobs
      WHEN NEW.status<>OLD.status BEGIN
        INSERT INTO episcene_report_events(at,kind,asset_key,payload)
        VALUES({SQL_NOW},'job',NEW.asset_key,json_object('asset',json({asset}),
          'job',json({detail}),'previous_status',OLD.status,
          'started_at',(SELECT started FROM episcene_report_active WHERE job_id=NEW.id),
          'elapsed_seconds',CASE WHEN OLD.status='running' AND NEW.status<>'running' THEN
            (SELECT MAX(0,{SQL_NOW}-started) FROM episcene_report_active WHERE job_id=NEW.id) ELSE NULL END));
        DELETE FROM episcene_report_active WHERE job_id=NEW.id AND NEW.status<>'running';
      END;
    ''')
    marker_fields = 'id source_key title year media_type season episode duration_ms segment_type start_ms end_ms disabled status source confidence created_at reviewed_at'
    marker = _object('NEW', marker_fields)
    previous = _object('OLD', marker_fields)
    evidence = "COALESCE((SELECT evidence_json FROM skip_auto_evidence WHERE record_id=NEW.id),'{}')"
    human = 'COALESCE((SELECT human_review FROM skip_auto_evidence WHERE record_id=NEW.id),0)'
    for suffix, event, before in (
        ('add', 'AFTER INSERT ON skip_records', 'NULL'),
        ('change', '''AFTER UPDATE OF status,start_ms,end_ms,disabled,confidence,reviewed_at ON skip_records
          WHEN OLD.status IS NOT NEW.status OR OLD.start_ms IS NOT NEW.start_ms OR OLD.end_ms IS NOT NEW.end_ms
          OR OLD.disabled IS NOT NEW.disabled OR OLD.confidence IS NOT NEW.confidence OR OLD.reviewed_at IS NOT NEW.reviewed_at''', previous)):
        con.executescript(f'''CREATE TRIGGER IF NOT EXISTS episcene_report_marker_{suffix} {event} BEGIN
          INSERT INTO episcene_report_events(at,kind,asset_key,record_id,payload)
          VALUES({SQL_NOW},'marker',NEW.asset_key,NEW.id,json_object('asset',json({asset}),
            'marker',json({marker}),'before',json({before}),'evidence_text',{evidence},'human_review',{human})); END;''')
    for suffix, event in (('add', 'AFTER INSERT'), ('change', 'AFTER UPDATE')):
        con.executescript(f'''CREATE TRIGGER IF NOT EXISTS episcene_report_evidence_{suffix}
          {event} ON skip_auto_evidence BEGIN
          INSERT INTO episcene_report_events(at,kind,asset_key,record_id,payload)
          VALUES({SQL_NOW},'evidence',COALESCE((SELECT asset_key FROM skip_records WHERE id=NEW.record_id),''),
            NEW.record_id,json_object('evidence_text',NEW.evidence_json,'human_review',NEW.human_review)); END;''')
        con.executescript(f'''CREATE TRIGGER IF NOT EXISTS episcene_report_scene_{suffix}
          {event} ON skip_scene_state BEGIN
          INSERT INTO episcene_report_events(at,kind,asset_key,payload)
          VALUES({SQL_NOW},'scene',NEW.asset_key,json_object('asset',json({asset}),
            'segment_type',NEW.kind,'detail',NEW.detail)); END;''')
    con.execute("INSERT OR IGNORE INTO episcene_report_meta VALUES('collection_started',?)", (str(time.time()),))
    con.execute("INSERT OR REPLACE INTO episcene_report_meta VALUES('schema',?)", (str(VERSION),))


def period(day):
    day = date.fromisoformat(day) if isinstance(day, str) else day
    end = datetime.combine(day, clock(7), ZONE)
    start = datetime.combine(day - timedelta(days=1), clock(7), ZONE)
    return start, end


def due_day(at=None):
    local = datetime.fromtimestamp(time.time() if at is None else at, ZONE)
    return local.date() - timedelta(days=int(local.time() < clock(7)))


def _events(con, start, end):
    for row in con.execute('SELECT * FROM episcene_report_events WHERE at>=? AND at<? ORDER BY id', (start, end)):
        item = dict(row)
        item['payload'] = json.loads(item['payload'])
        raw = item['payload'].pop('evidence_text', None)
        if raw is not None:
            try:
                parsed = json.loads(raw)
                item['payload']['evidence'] = parsed if isinstance(parsed,dict) else {'unreadable': True}
            except (ValueError, TypeError):
                item['payload']['evidence'] = {'unreadable': True}
        yield clean(item)


def _percentile(values, fraction):
    return round(sorted(values)[max(0, int(len(values) * fraction + .999999) - 1)], 3) if values else None


def build_report(con, day, generated_at=None):
    start, end = period(day)
    begin, cutoff = start.timestamp(), end.timestamp()
    generated_at = time.time() if generated_at is None else generated_at
    if generated_at < cutoff:
        raise ValueError('report_period_still_open')
    collected = float(con.execute("SELECT value FROM episcene_report_meta WHERE name='collection_started'").fetchone()[0])
    events = list(_events(con, begin, cutoff))
    # Resolve evidence written just after a proposal/review in the same transaction.
    # Never read today's mutable marker rows to build yesterday's report.
    by_record = collections.defaultdict(list)
    for event in events:
        if event['record_id'] is not None:
            by_record[event['record_id']].append(event)
    markers = []
    for record_events in by_record.values():
        for index, event in enumerate(record_events):
            if event['kind'] != 'marker':
                continue
            event = copy.deepcopy(event)
            for later in record_events[index + 1:]:
                if later['kind'] == 'marker':
                    break
                if later['kind'] in ('evidence','review'):
                    event['payload'].update(later['payload'])
            if event['payload']['marker']['media_type']=='episode':
                markers.append(event)
    finished = [e for e in events if e['kind'] == 'job' and e['payload']['previous_status'] == 'running'
                and e['payload']['job']['status'] in FINISHED and e['payload'].get('asset',{}).get('media_type')=='episode']
    paused = [e for e in events if e['kind'] == 'job' and e['payload']['previous_status'] == 'running'
              and e['payload']['job']['status'] == 'queued']
    runtimes = [e['payload']['elapsed_seconds'] for e in finished if e['payload']['elapsed_seconds'] is not None]
    series = {}
    for event in finished:
        data = event['payload']; asset = data.get('asset', {})
        key = (asset.get('playlist_id'), asset.get('source_key'))
        row = series.setdefault(key, dict(playlist_id=key[0], source_key=key[1],
            playlist=asset.get('playlist', ''), title=asset.get('title', 'Unbekannte Serie'),
            year=asset.get('year', ''), episodes={}, attempts=0, failures=0, seconds=0))
        row['attempts'] += 1
        row['failures'] += int(data['job']['status'] == 'failed')
        row['seconds'] += data['elapsed_seconds'] or 0
        # File identity distinguishes different versions and repeated attempts.
        row['episodes'][event['asset_key']] = dict(season=asset.get('season'),episode=asset.get('episode'),
            status=data['job']['status'], detail=data['job']['detail'])
    for row in series.values():
        row['episodes'] = list(row['episodes'].values())
        row['seconds'] = round(row['seconds'], 2)
    new = {e['record_id']: e for e in markers if e['payload']['before'] is None}
    approvals = [e for e in markers if e['payload']['marker']['status'] == 'approved'
        and (e['payload']['before'] or {}).get('status') != 'approved' and not e['payload']['marker']['disabled']]
    corrections = [e for e in markers if e['payload']['before'] and e['payload'].get('human_review')
        and any(e['payload']['before'][k] != e['payload']['marker'][k] for k in ('start_ms','end_ms','disabled','status'))]
    counts = collections.Counter(e['payload']['job']['status'] for e in finished)
    failures = collections.Counter(e['payload']['job']['detail'] for e in finished if e['payload']['job']['status'] == 'failed')
    phases = collections.defaultdict(list)
    cache = collections.Counter()
    worker_statuses = collections.Counter()
    for event in events:
        if event['kind'] == 'phase':
            phases[event['payload']['phase']].append(event['payload']['elapsed_seconds'])
        if event['kind'] == 'cache':
            cache[event['payload']['cache'] + ('_hit' if event['payload']['hit'] else '_miss')] += 1
        if event['kind'] == 'worker':
            worker_statuses[event['payload']['status']] += 1
    findings = []
    if collected > begin:
        findings.append('Unvollständiger Zeitraum: Die Protokollierung war noch nicht durchgehend aktiv. Frühere Versuche lassen sich nicht rückwirkend rekonstruieren.')
    if not finished:
        findings.append('Keine abgeschlossenen Analyseversuche protokolliert. Laufende, pausierte oder fehlende Analyseläufe sind damit nicht ausgeschlossen.')
    if failures:
        findings.append('Technische Fehler prüfen: ' + '; '.join(f'{n} × {text}' for text,n in failures.most_common(3)))
    if worker_statuses['daily_limit']:
        findings.append(f"Das Tageslimit wurde bei {worker_statuses['daily_limit']} Analyseprüfungen als erreicht gemeldet.")
    if worker_statuses['preferred_pending']:
        findings.append('Die Analyse meldete Wartezeiten auf priorisierte Sprachen. Reihenfolge und Katalogbestand prüfen.')
    if counts['no_reference']:
        findings.append(f"{counts['no_reference']} Versuche ohne geeignete Vergleichsgrundlage: Staffelbestand und verfügbare Referenzfolgen prüfen.")
    if corrections:
        findings.append(f'{len(corrections)} manuelle Korrekturen/Ablehnungen protokolliert: Zeitgrenzen und Erkennungsevidenz vergleichen.')
    if phases:
        slowest = max(phases, key=lambda k: sum(phases[k]))
        findings.append(f'Größter gemessener Zeitanteil: {slowest} ({sum(phases[slowest]):.1f} s). Phasen können ineinander verschachtelt sein.')
    builds = [e['payload'] for e in events if e['kind'] == 'build']
    baseline = con.execute("SELECT payload FROM episcene_report_events WHERE kind='build' AND at<? ORDER BY at DESC,id DESC LIMIT 1", (begin,)).fetchone()
    if baseline:
        builds.insert(0, clean(json.loads(baseline[0])))
    summary = dict(series=len(series), episodes=len({e['asset_key'] for e in finished}),
        attempts=len(finished), interrupted=len(paused), outcomes=dict(counts),
        language_priorities=dict(collections.Counter(str(e['payload']['asset']['language_priority']) for e in finished)),
        proposals=len(new), segments=dict(collections.Counter(e['payload']['marker']['segment_type'] for e in new.values())),
        approvals=len({e['record_id'] for e in approvals}),
        automatic_approvals=len({e['record_id'] for e in approvals if
            e['payload'].get('evidence', {}).get('automatic_acceptance') is True and not e['payload'].get('human_review')}),
        corrections=len(corrections), seconds=round(sum(runtimes), 3), runtime_samples=len(runtimes),
        median_seconds=round(statistics.median(runtimes), 3) if runtimes else None,
        p95_seconds=_percentile(runtimes, .95), cache=dict(cache), worker_statuses=dict(worker_statuses),
        phases={k:dict(count=len(v),seconds=round(sum(v),3),p95_seconds=_percentile(v,.95)) for k,v in phases.items()})
    return dict(schema=VERSION,day=end.date().isoformat(),timezone='Europe/Berlin',
        start=start.isoformat(),end=end.isoformat(),hours=(cutoff-begin)/3600,
        generated_at=datetime.fromtimestamp(generated_at, timezone.utc).isoformat(),
        collection_started=datetime.fromtimestamp(collected, ZONE).isoformat(), complete=collected<=begin,
        summary=summary,series=sorted(series.values(),key=lambda r:(-r['attempts'],r['title'])),
        markers=markers,events=events,builds=builds,findings=findings,
        limitations=['Confidence ist ein Erkennungsscore, keine gemessene Trefferquote.',
          'Tageswerte zählen abgeschlossene Versuche; Wiederholungen sind getrennt von eindeutigen Dateien.',
          'CPU/RAM-Messungen betreffen den Steuerprozess, nicht den separaten Rechen-Worker.',
          'Warteschlangenstand und verbleibende Gesamtlaufzeit werden nicht rückwirkend geschätzt.'])


def generate_due(db, at=None):
    at = time.time() if at is None else at
    due = due_day(at)
    with db() as con:
        migrate(con)
        started = float(con.execute("SELECT value FROM episcene_report_meta WHERE name='collection_started'").fetchone()[0])
        first = min(due, datetime.fromtimestamp(started, ZONE).date())
        existing = {r[0] for r in con.execute('SELECT day FROM episcene_daily_reports')}
    written = []
    day = first
    while day <= due:
        if day.isoformat() not in existing:
            with db() as con:
                # Explicit read transaction keeps log rows and build provenance consistent.
                con.execute('BEGIN')
                report = build_report(con, day, at)
            start, end = period(day)
            with db() as con:
                result = con.execute('INSERT OR IGNORE INTO episcene_daily_reports VALUES(?,?,?,?,?)',
                    (day.isoformat(),start.timestamp(),end.timestamp(),at,encode(report)))
                if result.rowcount:
                    written.append(day.isoformat())
        day += timedelta(days=1)
    return written


def read_report(con, day=None):
    if day:
        row = con.execute('SELECT payload FROM episcene_daily_reports WHERE day=?', (day,)).fetchone()
    else:
        row = con.execute('SELECT payload FROM episcene_daily_reports ORDER BY day DESC LIMIT 1').fetchone()
    return json.loads(row[0]) if row else None


def register_build(con):
    root = Path(__file__).resolve().parent
    names = ('skip_daily_reports.py','skip_report_telemetry.py','skip_analysis_worker.py','skip_automation.py',
             'skip_scene.py','skip_detector_v2.py','skip_detector_v3.py','skip_visual.py','skip_release.py','skip_schedule.py')
    build = {'schema': VERSION, 'sha256': {name:hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in names if (root/name).is_file()}}
    value = encode(build)
    old = con.execute("SELECT value FROM episcene_report_meta WHERE name='build'").fetchone()
    if not old or old[0] != value:
        con.execute("INSERT INTO episcene_report_events(at,kind,payload) VALUES(?,'build',?)", (time.time(),value))
        con.execute("INSERT OR REPLACE INTO episcene_report_meta VALUES('build',?)", (value,))


def install(app, db):
    from flask import abort, jsonify, render_template, request, Response
    from app import web_auth
    if app.extensions.get('episcene_reports'):
        return
    with db() as con:
        migrate(con)
        register_build(con)
    app.extensions['episcene_reports'] = True
    @app.context_processor
    def episcene_report_context():
        return {'episcene_reports_enabled': True}
    from skip_report_telemetry import install as telemetry
    telemetry(db)

    @app.get('/admin/skip/reports')
    def episcene_report_page():
        guard = web_auth()
        if guard:
            return guard
        day = request.args.get('day')
        if day and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):
            abort(400)
        with db() as con:
            report = read_report(con,day)
            days = [r[0] for r in con.execute('SELECT day FROM episcene_daily_reports ORDER BY day DESC LIMIT 90')]
        if day and report is None:
            abort(404)
        response = app.make_response(render_template('skip_daily_report.html',report=report,days=days,
            stale=report is None or report['day']!=due_day().isoformat(),kinds=KINDS,
            marker_preview=report['markers'][:100] if report else []))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/admin/skip/reports/latest')
    def episcene_report_latest():
        guard = web_auth()
        if guard:
            return guard
        with db() as con:
            row = con.execute('SELECT day FROM episcene_daily_reports ORDER BY day DESC LIMIT 1').fetchone()
        response = jsonify(day=row[0] if row else None,expected_day=due_day().isoformat())
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/admin/skip/reports/<day>.json')
    def episcene_report_json(day):
        guard = web_auth()
        if guard:
            return guard
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):
            abort(400)
        with db() as con:
            report = read_report(con,day)
        if report is None:
            abort(404)
        return Response(encode(report),mimetype='application/json',headers={
            'Content-Disposition': f'attachment; filename="EpiScene-{day}.json"', 'Cache-Control':'no-store'})

