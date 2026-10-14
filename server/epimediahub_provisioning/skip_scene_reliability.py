"""Versioned overlay for honest outcomes and durable visual progress.

Hooks preserve deployed playlist/lane wrappers instead of replacing live
orchestration. Failed reads/comparisons never create successful checkpoints.
"""
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid

POLICY = 'episcene_progress_20261012_v1'
CONTEXT = ContextVar('episcene_attempt', default=None)
DEADLINE = ContextVar('episcene_deadline', default=None)
WORKER_ACTIVE = ContextVar('episcene_worker_active', default=False)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def asset_version(asset):
    asset = dict(asset)
    return digest({k: asset.get(k) for k in ('asset_key','source_key','playlist_id','stream_id',
                  'extension','duration_ms','season','episode','updated_at','content_version','etag')})


def error_code(error):
    code = str(error)
    return code if re.fullmatch(r'[a-z_]+(?:_[1-5][0-9]{2})?', code) else type(error).__name__


def analysis_playlist(con,playlist_id):
    # The live installation has independent inventories. Never resolve their
    # IDs against a customer's playlist table. Older test fixtures use the
    # original schema and have no independent table.
    table='skip_analysis_playlists' if con.execute("SELECT 1 FROM sqlite_master WHERE name='skip_analysis_playlists'").fetchone() else 'customer_playlists'
    return con.execute('SELECT * FROM '+table+' WHERE id=?',(playlist_id,)).fetchone()


def migrate(con):
    for sql in (
        "CREATE TABLE IF NOT EXISTS skip_scene_progress(asset_key TEXT NOT NULL,kind TEXT NOT NULL,version TEXT NOT NULL,attempt_id TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,updated_at REAL NOT NULL,PRIMARY KEY(asset_key,kind))",
        "CREATE TABLE IF NOT EXISTS skip_scene_compare_cache(cache_key TEXT PRIMARY KEY,decision TEXT NOT NULL,created_at REAL NOT NULL)",
        "CREATE TABLE IF NOT EXISTS skip_scene_tail_checks(cache_key TEXT PRIMARY KEY,outcome TEXT NOT NULL,checked_at REAL NOT NULL)",
        "CREATE TABLE IF NOT EXISTS skip_scene_window_versions(window_id INTEGER PRIMARY KEY,version TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS skip_scene_heartbeats(id INTEGER PRIMARY KEY CHECK(id=1),at REAL NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL)",
    ):
        con.execute(sql)


def event(con, kind, asset_key='', **payload):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='episcene_report_events'").fetchone():
        return
    from skip_daily_reports import encode
    con.execute('INSERT INTO episcene_report_events(at,kind,asset_key,payload) VALUES(?,?,?,?)',
                (time.time(), kind, asset_key, encode(payload)))


def heartbeat(db, status, reason=''):
    with db() as con:
        migrate(con)
        con.execute('INSERT OR REPLACE INTO skip_scene_heartbeats VALUES(1,?,?,?)', (time.time(), status, reason))
        event(con, 'heartbeat', status=status, reason=reason)


def state(db, asset, kind, status, reason=''):
    context = CONTEXT.get()
    attempt_id = context['attempt_id'] if context else uuid.uuid4().hex
    with db() as con:
        migrate(con)
        con.execute('INSERT OR REPLACE INTO skip_scene_progress VALUES(?,?,?,?,?,?,?)',
                    (asset['asset_key'], kind, asset_version(asset), attempt_id, status, reason, time.time()))
        event(con, 'visual_phase', asset['asset_key'], segment_type=kind, status=status,
              reason=reason, attempt_id=attempt_id)


def reserve(seconds, phase):
    deadline = DEADLINE.get()
    context = CONTEXT.get()
    if context and time.monotonic()-context.get('heartbeat_at',0)>30:
        heartbeat(context['db'], 'running', phase)
        context['heartbeat_at']=time.monotonic()
    if context and context.get('scene_deadline'):
        deadline = min(deadline or float('inf'), context['scene_deadline'])
    if deadline is not None and deadline - time.monotonic() < seconds:
        from skip_remote_client import RemoteDeferred
        raise RemoteDeferred('EpiScene: verbleibendes Zeitbudget reicht nicht für ' + phase + '; gültiger Fortschritt bleibt gespeichert')


def install_scene(scene):
    if getattr(scene, '_reliability', False):
        return
    scene._reliability = True
    original_migrate, original_state = scene.migrate, scene._state
    original_cache, original_save = scene._cache, scene._save
    original_compare, original_analyze = scene._compare, scene.analyze
    original_refresh, original_release = scene.refresh_neighbours, scene.release_ready
    original_rows = scene._cached_rows
    original_snapshot=scene._snapshot
    @wraps(original_snapshot)
    def snapshot(row,asset):
        return dict(original_snapshot(row,asset),source_version=asset_version(asset))

    @wraps(original_migrate)
    def scene_migrate(con):
        original_migrate(con)
        migrate(con)

    @wraps(original_cache)
    def cache(con, asset, kind, offset, length):
        migrate(con)
        row = original_cache(con, asset, kind, offset, length)
        if row:
            version = con.execute('SELECT version FROM skip_scene_window_versions WHERE window_id=?', (row['id'],)).fetchone()
            if not version:
                # A legacy window may be bound to the current metadata
                # revision only when it was saved after that revision. An
                # unknown/newer revision is re-read, never silently adopted.
                try:
                    revised=datetime.fromisoformat(dict(asset)['updated_at'].replace('Z','+00:00')).timestamp()
                except (KeyError,TypeError,ValueError):
                    return None
                if row['created_at']<int(revised):
                    return None
                con.execute('INSERT INTO skip_scene_window_versions VALUES(?,?)',(row['id'],asset_version(asset)))
            elif version[0] != asset_version(asset):
                return None
        return row

    @wraps(original_save)
    def save(con, asset, kind, offset, length, frames):
        # _save calls _cache; persist revision before returning the new row.
        original_save(con, asset, kind, offset, length, frames)
        row = con.execute('''SELECT id FROM skip_scene_windows WHERE asset_key=? AND kind=?
          AND offset_ms=? AND length_ms=? AND step_ms=? AND duration_ms=? AND policy=?''',
          (asset['asset_key'],kind,offset,length,scene.STEP_MS,asset['duration_ms'],scene.POLICY)).fetchone()
        con.execute('INSERT OR REPLACE INTO skip_scene_window_versions VALUES(?,?)', (row[0], asset_version(asset)))
        return scene._cache(con, asset, kind, offset, length)

    @wraps(original_rows)
    def cached_rows(con, asset, kind):
        migrate(con)
        valid=[]
        for row in original_rows(con, asset, kind):
            parent=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',(row['asset_key'],)).fetchone()
            current=scene._cache(con,parent,kind,row['offset_ms'],row['length_ms']) if parent else None
            if current:
                valid.append(row)
        return valid

    def capture(db,asset,kind,start,end,busy,*,verified=False):
        from skip_analysis import probe,provider_proxy,source_url
        from skip_remote_client import visual_fingerprint
        from skip_analysis_worker import busy_check
        start=max(0,int(start)//scene.STEP_MS*scene.STEP_MS)
        end=min(asset['duration_ms'],math_ceil(int(end),scene.STEP_MS))
        length=end-start
        if not 5000<=length<=720000:
            raise ValueError('visual_window')
        with db() as con:
            cached=scene._cache(con,asset,kind,start,length)
        if cached:
            return cached
        frames,cursor,measured=[],start,verified
        while cursor<end:
            if busy():
                raise ValueError('analysis_deferred')
            part=min(scene.CHUNK_MS,end-cursor)
            if 0<end-cursor-part<5000:
                part-=5000
            with db() as con:
                row=scene._cache(con,asset,kind,cursor,part)
                playlist=analysis_playlist(con,asset['playlist_id'])
                # Reuse a valid larger window, including one saved by the full
                # analysis. Keep exact 500ms sampling and content revision.
                if not row:
                    for larger in con.execute('''SELECT w.* FROM skip_scene_windows w JOIN skip_scene_window_versions v ON v.window_id=w.id
                      WHERE w.asset_key=? AND w.offset_ms<=? AND w.offset_ms+w.length_ms>=?
                      AND w.step_ms=? AND w.policy=? AND w.duration_ms=? AND v.version=? AND w.created_at>=?
                      ORDER BY w.length_ms LIMIT 4''',(asset['asset_key'],cursor,cursor+part,scene.STEP_MS,scene.POLICY,asset['duration_ms'],asset_version(asset),time.time()-scene.CACHE_SECONDS)):
                        first=(cursor-larger['offset_ms'])//scene.STEP_MS
                        chunk=json.loads(larger['frames_json'])[first:first+(part+scene.STEP_MS-1)//scene.STEP_MS]
                        row=scene._save(con,asset,kind,cursor,part,chunk)
                        break
            if row:
                chunk=scene._window(row,asset).frames
            else:
                provider_busy=busy_check(db,[playlist])
                def protected_read():
                    return busy() or provider_busy()
                if protected_read():
                    raise ValueError('analysis_deferred')
                with provider_proxy(source_url(playlist,asset),protected_read) as source:
                    if not measured:
                        duration,_=probe(source,protected_read)
                        if abs(duration-asset['duration_ms'])>500:
                            raise ValueError('visual_runtime_changed')
                        measured=True
                    chunk=visual_fingerprint(source,cursor,part,scene.STEP_MS,protected_read)
                with db() as con:
                    scene._save(con,asset,kind,cursor,part,chunk)
            frames.extend(chunk)
            cursor+=part
        with db() as con:
            return scene._save(con,asset,kind,start,length,frames)

    @wraps(original_state)
    def scene_state(db, asset, kind, detail):
        original_state(db, asset, kind, detail)
        if 'Bildprüfung unvollständig' in detail:
            error = sys.exc_info()[1]
            code=error_code(error) if error else 'visual_incomplete'
            status='partial' if code in ('visual_incomplete','visual_window','visual_failed') else 'technical_error'
            state(db, asset, kind, status, code)
            if error is not None:
                error_id=getattr(error,'_episcene_error_id',None) or uuid.uuid4().hex
                error._episcene_error_id=error_id
                context=CONTEXT.get()
                with db() as con:
                    event(con,'phase_error',asset['asset_key'],phase='visual_'+kind,error_code=code,
                          error_id=error_id,attempt_id=context['attempt_id'] if context else '')

    @wraps(original_compare)
    def compare(db, asset, kind, own, selected, busy):
        context = CONTEXT.get()
        if context:
            context['asset'], context['db'], context['kind'] = dict(asset), db, kind
        # Add real independent episodes already in the season cache. Different
        # dubs of one episode have the same number and cannot add support.
        selected = list(selected)
        used = {asset['episode'], *(p['episode'] for _, p in selected)}
        if len(used) < 4:
            with db() as con:
                for row in scene._cached_rows(con, asset, kind):
                    if row['episode'] not in used:
                        parent = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (row['asset_key'],)).fetchone()
                        selected.append((row, dict(parent)))
                        used.add(row['episode'])
                        if len(used) >= 5:
                            break
        reserve(12, 'Bildvergleich')
        result = original_compare(db, asset, kind, own, selected, busy)
        if context:
            context['comparison_status'] = 'no_reference' if len(used) < 2 else 'complete'
        return result

    @wraps(original_analyze)
    def analyze(db, asset, kind, references, busy):
        with db() as con:
            if not scene.enabled(con):
                return original_analyze(db, asset, kind, references, busy)
        inherited = CONTEXT.get()
        context = dict(attempt_id=(inherited or {}).get('attempt_id', uuid.uuid4().hex),
                       asset=dict(asset),db=db,kind=kind,comparison_status=None,
                       scene_deadline=time.monotonic()+scene.JOB_SECONDS)
        token = CONTEXT.set(context)
        state(db, asset, kind, 'running')
        try:
            reserve(30, 'Bildsuche')
            result = original_analyze(db, asset, kind, references, busy)
            with db() as con:
                latest = con.execute('SELECT status FROM skip_scene_progress WHERE asset_key=? AND kind=?', (asset['asset_key'],kind)).fetchone()
            if latest and latest[0] == 'running':
                state(db, asset, kind, context['comparison_status'] or 'no_reference')
            return result
        except BaseException as error:
            deferred = str(error) == 'analysis_deferred'
            state(db, asset, kind, 'deferred' if deferred else 'partial', error_code(error))
            raise
        finally:
            CONTEXT.reset(token)

    @wraps(original_refresh)
    def refresh(db, asset, kind, busy):
        # Neighbour work is optional after the target's required comparison.
        # Exhausting its budget must not turn a completed target into a retry.
        context=CONTEXT.get()
        token=CONTEXT.set(dict(context)) if context else None
        try:
            reserve(20, 'Nachbarvergleich')
            return original_refresh(db, asset, kind, busy)
        except ValueError as error:
            if str(error) != 'analysis_deferred':
                raise
            with db() as con:
                event(con, 'neighbour_wait', asset['asset_key'], reason=getattr(error, 'reason', error_code(error)))
        finally:
            if token is not None:
                CONTEXT.reset(token)

    @wraps(original_release)
    def release_ready(con, row, evidence):
        if not isinstance(evidence,dict):
            return False
        if evidence.get('method') == 'verified_variant_reuse':
            from skip_variant_reuse import release_ready as variant_ready
            return variant_ready(con, row, evidence)
        proof = evidence.get('decision', {}).get('tail_check') if isinstance(evidence.get('decision'), dict) else None
        if proof and not isinstance(proof,dict):
            return False
        if proof:
            asset = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (row['asset_key'],)).fetchone()
            if not asset or proof.get('source_version') != asset_version(asset):
                return False
        if evidence.get('method')=='episcene_consensus':
            windows=evidence.get('windows',[])
            if not isinstance(windows,list) or any(not isinstance(item,dict) for item in windows):
                return False
            for item in windows:
                parent=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',(item.get('asset_key'),)).fetchone()
                if not parent:
                    return False
                current=asset_version(parent)
                if item.get('source_version') is None:
                    # Approved legacy sources retain their policy only when
                    # the cache still represents their current revision.
                    if row['status']!='approved':
                        return False
                    cached=scene._cache(con,parent,row['segment_type'],item.get('offset_ms'),item.get('length_ms'))
                    if not cached or cached['id']!=item.get('id'):
                        return False
                elif item['source_version']!=current:
                    return False
        return original_release(con, row, evidence)

    scene.migrate, scene._cache, scene._save, scene._state = scene_migrate, cache, save, scene_state
    scene._cached_rows,scene.capture=cached_rows,capture
    scene._snapshot=snapshot
    scene._compare, scene.analyze, scene.refresh_neighbours = compare, analyze, refresh
    scene.release_ready = release_ready
    install_remote(scene)
    from skip_tail_check import install_visual
    import skip_visual
    install_visual(skip_visual)
    scene.validate_result = skip_visual.validate_result


def math_ceil(value,step):
    return ((value+step-1)//step)*step


def install_remote(scene):
    import skip_remote_client as remote
    if getattr(remote, '_durable_visual', False):
        return
    remote._durable_visual = True
    original_detect, original_fingerprint = remote.visual_detect, remote.visual_fingerprint
    @wraps(original_fingerprint)
    def fingerprint(source, start_ms, length_ms, step_ms=500, busy=lambda: False):
        reserve(min(100, max(20, length_ms/1000+10)), 'Bildfenster')
        return original_fingerprint(source, start_ms, length_ms, step_ms, busy)
    @wraps(original_detect)
    def detect(target, partners, kind, busy=lambda: False):
        context = CONTEXT.get()
        if not context:
            return original_detect(target, partners, kind, busy)
        if busy():
            raise ValueError('analysis_deferred')
        key = digest([POLICY,target.payload(),[p.payload() for p in partners],kind,
                      asset_version(context['asset'])])
        db = context['db']
        with db() as con:
            migrate(con)
            row = con.execute('SELECT decision FROM skip_scene_compare_cache WHERE cache_key=? AND created_at>=?', (key,time.time()-scene.CACHE_SECONDS)).fetchone()
        if row:
            decision = json.loads(row[0])
            from skip_visual import validate_result
            validate_result(decision, target, partners, kind)
        else:
            reserve(12, 'Bildvergleich')
            decision = original_detect(target, partners, kind, busy)
            with db() as con:
                con.execute('INSERT OR REPLACE INTO skip_scene_compare_cache VALUES(?,?,?)', (key,json.dumps(decision),time.time()))
                con.execute('DELETE FROM skip_scene_compare_cache WHERE cache_key NOT IN (SELECT cache_key FROM skip_scene_compare_cache ORDER BY created_at DESC LIMIT 2048)')
        with db() as con:
            tail_checked=con.execute('SELECT 1 FROM skip_scene_tail_checks WHERE cache_key=? AND checked_at>=?',(key,time.time()-scene.CACHE_SECONDS)).fetchone()
        if not tail_checked:
            from skip_tail_check import confirm_tail
            context['tail_outcome']=None
            upgraded=confirm_tail(db,context['asset'],decision,target,partners,kind,busy)
            with db() as con:
                if context['tail_outcome'] in ('empty','not_empty'):
                    con.execute('INSERT OR REPLACE INTO skip_scene_tail_checks VALUES(?,?,?)',(key,context['tail_outcome'],time.time()))
                    con.execute('DELETE FROM skip_scene_tail_checks WHERE checked_at<?',(time.time()-scene.CACHE_SECONDS,))
                if upgraded!=decision:
                    con.execute('INSERT OR REPLACE INTO skip_scene_compare_cache VALUES(?,?,?)',(key,json.dumps(upgraded),time.time()))
            decision=upgraded
        with db() as con:
            event(con, 'comparison_cache', target.episode_id, hit=bool(row),phase=kind,
                  attempt_id=context['attempt_id'])
        return decision
    remote.visual_fingerprint, remote.visual_detect = fingerprint, detect


def install_automation(audio):
    if getattr(audio, '_reliability', False):
        return
    audio._reliability = True
    original, original_probe = audio.analyze, audio.probe
    from contextlib import contextmanager
    original_phase=audio.analysis_phase
    @contextmanager
    def phase(name):
        try:
            with original_phase(name):
                yield
        except BaseException as error:
            context=CONTEXT.get()
            if context:
                error_id=getattr(error,'_episcene_error_id',None) or uuid.uuid4().hex
                error._episcene_error_id=error_id
                with context['db']() as con:
                    event(con,'phase_error',context.get('asset',{}).get('asset_key',''),
                          phase=name,error_code=error_code(error),error_id=error_id,attempt_id=context['attempt_id'])
            raise
    audio.analysis_phase=phase
    @wraps(original_probe)
    def probe(source, busy):
        value = original_probe(source, busy)
        context = CONTEXT.get()
        if context:
            with context['db']() as con:
                event(con, 'probe_success', context.get('asset', {}).get('asset_key',''), duration_ms=value[0])
        return value
    @wraps(original)
    def analyze(db, job, busy_factory):
        with db() as con:
            migrate(con)
            asset = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (job['asset_key'],)).fetchone()
            if not asset:
                return original(db, job, busy_factory)
            asset = dict(asset)
            from skip_scene import enabled
            use_scene = enabled(con)
            required = [k for k in ('intro','outro') if not audio.protected(con, asset, k)]
            resumed=bool(con.execute("SELECT 1 FROM skip_scene_progress WHERE asset_key=? AND version=? AND status IN ('partial','deferred','running','pending') LIMIT 1",(asset['asset_key'],asset_version(asset))).fetchone())
        token = CONTEXT.set(dict(attempt_id=uuid.uuid4().hex, db=db, asset=asset))
        with db() as con:
            event(con,'analysis_scope',asset['asset_key'],required=required,resumed=resumed,attempt_id=CONTEXT.get()['attempt_id'],playlist_id=asset['playlist_id'])
        try:
            if use_scene:
                for kind in required:
                    state(db, asset, kind, 'pending')
                from skip_variant_reuse import try_reuse
                reused = try_reuse(db, asset, busy_factory, required)
                if required and len(reused) == len(required):
                    return 'done', 'Bestätigte Zeitmarken einer anderen Sprachfassung visuell geprüft und übernommen'
            status, detail = original(db, job, busy_factory)
            if use_scene and status == 'no_match':
                with db() as con:
                    rows = {r['kind']:r['status'] for r in con.execute('SELECT * FROM skip_scene_progress WHERE asset_key=?', (asset['asset_key'],))}
                statuses = [rows.get(k, 'pending') for k in required]
                if 'technical_error' in statuses:
                    return 'failed', 'Technischer Bildprüfungsfehler; Fehlercode und Phase im Tagesbericht verfügbar'
                if any(s in ('pending','running','partial','deferred') for s in statuses):
                    return 'partial', 'Bildprüfung unvollständig; gültige Fenster und vorhandene Vorschläge bleiben erhalten'
                if 'no_reference' in statuses:
                    return 'no_reference', 'Bilder gespeichert; unabhängige Vergleichsfolge oder bestätigte Referenz fehlt'
            return status, detail
        finally:
            with db() as con:
                if use_scene:
                    rows={r['kind']:r['status'] for r in con.execute('SELECT kind,status FROM skip_scene_progress WHERE asset_key=?',(asset['asset_key'],))}
                    event(con,'analysis_completion',asset['asset_key'],required=required,
                          phases={k:rows.get(k,'pending') for k in required},attempt_id=CONTEXT.get()['attempt_id'],playlist_id=asset['playlist_id'])
            CONTEXT.reset(token)
    audio.analyze, audio.probe = analyze, probe


def install_worker(worker):
    if getattr(worker, '_reliability', False):
        return
    worker._reliability = True
    import skip_catalogue, skip_schedule
    from skip_source_preferences import install
    install(skip_catalogue, skip_schedule)
    import skip_automation
    install_automation(skip_automation)
    def bounded(original):
        @wraps(original)
        def process(db, *args, **kwargs):
            if WORKER_ACTIVE.get():
                return original(db,*args,**kwargs)
            deadline = kwargs.get('deadline')
            token = DEADLINE.set(deadline)
            active_token=WORKER_ACTIVE.set(True)
            heartbeat(db, 'running')
            try:
                if deadline is not None and deadline-time.monotonic() < 120:
                    heartbeat(db, 'waiting', 'Verbleibendes Laufbudget unter 120 Sekunden; kein neuer Auftrag begonnen')
                    return 'queued'
                result = original(db, *args, **kwargs)
                heartbeat(db, result)
                return result
            except BaseException as error:
                heartbeat(db, 'error', error_code(error))
                raise
            finally:
                WORKER_ACTIVE.reset(active_token)
                DEADLINE.reset(token)
        return process
    worker.process_one = bounded(worker.process_one)
    # The installed parallel runner can call the internal lane entry directly.
    # Protect that entry too; nested normal calls retain one deadline/heartbeat.
    if hasattr(worker,'_process_one'):
        worker._process_one=bounded(worker._process_one)


def install_reports(reports):
    if getattr(reports, '_reliability', False):
        return
    reports._reliability = True
    reports.FINISHED.add('partial')
    original = reports.build_report
    original_register=reports.register_build
    @wraps(original_register)
    def register(con):
        original_register(con)
        names=('skip_scene_reliability.py','skip_variant_reuse.py','skip_tail_check.py','skip_source_preferences.py')
        root=Path(__file__).resolve().parent
        hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
        value=digest(hashes)
        previous=con.execute("SELECT value FROM episcene_report_meta WHERE name='reliability_build'").fetchone()
        if not previous or previous[0]!=value:
            event(con,'upgrade_build',policy=POLICY,module_hashes=hashes)
            con.execute("INSERT OR REPLACE INTO episcene_report_meta VALUES('reliability_build',?)",(value,))
    @wraps(original)
    def build(con, day, generated_at=None):
        report = original(con, day, generated_at)
        enrich_report(report)
        begin=reports.period(day)[0].timestamp()
        report['upgrade_builds']=[e for e in report['events'] if e['kind']=='upgrade_build']
        baseline=con.execute("SELECT at,payload FROM episcene_report_events WHERE kind='upgrade_build' AND at<? ORDER BY at DESC,id DESC LIMIT 1",(begin,)).fetchone()
        if baseline:
            report['upgrade_builds'].insert(0,dict(at=baseline['at'],payload=json.loads(baseline['payload']),baseline=True))
        # Snapshot current access flags without writing them or predicting
        # expiry. No credentials or raw playlist configurations are exported.
        table = 'skip_analysis_playlists'
        if con.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
            cols = {r[1] for r in con.execute('PRAGMA table_info(skip_analysis_playlists)')}
            fields = [f for f in ('id','name','enabled','active','paused','updated_at') if f in cols]
            report['analysis_access_snapshot'] = [dict(r) for r in con.execute('SELECT '+','.join(fields)+' FROM skip_analysis_playlists')] if fields else []
            flags=dict(con.execute('SELECT playlist_id,enabled FROM skip_analysis_sources'))
            archived=dict(con.execute('SELECT id,archived FROM skip_analysis_playlists')) if 'archived' in cols else {}
            for row in report['analysis_access_snapshot']:
                row['enabled']=bool(flags.get(row['id'],0))
                row['archived']=bool(archived.get(row['id'],0))
                row['paused']=not row['enabled'] or row['archived']
        return report
    reports.build_report,reports.register_build = build,register


def enrich_report(report):
    events = report['events']
    incomplete = []
    for e in events:
        p = e['payload']
        if e['kind'] == 'job' and p.get('previous_status') == 'running' and p.get('job',{}).get('status') == 'no_match':
            start = p.get('started_at')
            if start is not None and any(s['asset_key']==e['asset_key'] and start<=s['at']<=e['at']
                  and s['kind']=='scene' and 'Bildprüfung unvollständig' in s['payload'].get('detail','') for s in events):
                incomplete.append(e['id'])
    summary = report['summary']
    summary['incomplete_negative_attempts'] = len(incomplete)
    complete_negatives=0
    for e in events:
        p=e['payload']
        if e['kind']=='job' and p.get('previous_status')=='running' and p.get('job',{}).get('status')=='no_match' and p.get('started_at') is not None:
            completed=[c for c in events if c['kind']=='analysis_completion' and c['asset_key']==e['asset_key'] and p['started_at']<=c['at']<=e['at']]
            if completed and all(v=='complete' for v in completed[-1]['payload'].get('phases',{}).values()):
                complete_negatives+=1
    summary['fully_checked_no_match'] = complete_negatives
    summary['legacy_unverified_no_match'] = max(0,summary['outcomes'].get('no_match',0)-len(incomplete)-complete_negatives)
    summary['visual_outcomes'] = {}
    summary['source_languages'] = {}
    summary['unique_phase_errors']=len({e['payload'].get('error_id') for e in events if e['kind']=='phase_error'})
    summary['resumed_attempts']=sum(int(e['payload'].get('resumed',False)) for e in events if e['kind']=='analysis_scope')
    for e in events:
        p = e['payload']
        if e['kind']=='visual_phase':
            key=p['status']; summary['visual_outcomes'][key]=summary['visual_outcomes'].get(key,0)+1
        if e['kind']=='variant_reuse':
            summary['verified_variant_reuse']=summary.get('verified_variant_reuse',0)+int(p.get('status')=='verified')
        if e['kind']=='source_language':
            source=summary['source_languages'].setdefault(str(p['playlist_id']),dict(preferred_language=p['preferred_language'],preferred_selections=0,fallback_selections=0,unknown_selections=0))
            source['preferred_selections' if p['selection']=='preferred' else 'fallback_selections']+=1
            source['unknown_selections']+=int(not p.get('codes'))
    report['incomplete_negative_event_ids'] = incomplete
    report['worker_health'] = {label: next((e['at'] for e in reversed(events) if e['kind']==kind),None)
                              for label,kind in [('last_heartbeat','heartbeat'),('last_successful_probe','probe_success'),('last_completion','analysis_completion')]}
    report['worker_health']['last_reason']=next((e['payload'].get('reason','') for e in reversed(events) if e['kind']=='heartbeat'),None)
    if incomplete:
        report['findings'].append(f'{len(incomplete)} als no_match protokollierte Versuche enthalten unvollständige Bildprüfungen; getrennt von vollständigen negativen Ergebnissen bewerten.')
    return report
