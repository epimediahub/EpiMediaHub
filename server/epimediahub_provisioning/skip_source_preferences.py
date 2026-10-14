"""Source-specific DE/IT ordering, retaining actual language declarations.

Unknown languages stay unknown. Only independent analysis playlists are
configured; customer playlists and access activation are never changed here.
"""
from functools import wraps
import json
import time


def migrate(con):
    for sql in (
        "CREATE TABLE IF NOT EXISTS skip_source_preferences(playlist_id INTEGER PRIMARY KEY,language TEXT NOT NULL CHECK(language IN ('de','it')))",
        "CREATE TABLE IF NOT EXISTS skip_asset_languages(asset_key TEXT PRIMARY KEY,codes TEXT NOT NULL,method TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS skip_series_languages(playlist_id INTEGER NOT NULL,series_id TEXT NOT NULL,codes TEXT NOT NULL,PRIMARY KEY(playlist_id,series_id))",
        "CREATE TABLE IF NOT EXISTS skip_source_rotation(playlist_id INTEGER PRIMARY KEY,last_served REAL NOT NULL)",
    ):
        con.execute(sql)


class LanguagePriority(int):
    def __new__(cls, value, codes=()):
        result = super().__new__(cls, value)
        result.codes = frozenset(codes)
        return result


def declared_codes(catalogue, row):
    if not isinstance(row, dict):
        return set()
    codes = set().union(*(catalogue.language_codes(row.get(f)) for f in catalogue.LANGUAGE_FIELDS))
    return codes or catalogue.label_languages(row.get('name', '')) or catalogue.label_languages(row.get('category_name', ''), category=True)


def preference(con, playlist_id):
    migrate(con)
    row = con.execute('SELECT language FROM skip_source_preferences WHERE playlist_id=?', (playlist_id,)).fetchone()
    return row[0] if row else None


def recover_saved_languages(con,playlist_id):
    import skip_catalogue as catalogue
    rows=con.execute('''SELECT e.asset_key,z.payload_json FROM skip_catalogue_episodes e
      JOIN skip_catalogue_series z ON z.playlist_id=e.playlist_id AND z.series_id=e.series_id
      LEFT JOIN skip_asset_languages k USING(asset_key)
      WHERE e.playlist_id=? AND k.asset_key IS NULL LIMIT 2000''',(playlist_id,)).fetchall()
    for row in rows:
        try:
            metadata=json.loads(row['payload_json'])
        except (ValueError,TypeError):
            continue
        codes=declared_codes(catalogue,metadata)
        con.execute('INSERT OR IGNORE INTO skip_asset_languages VALUES(?,?,?)',
                    (row['asset_key'],json.dumps(sorted(codes)),'saved_provider_declaration' if codes else 'saved_language_unknown'))


def asset_codes(row,catalogue):
    try:
        stored=json.loads(row['codes']) if row['codes'] else []
    except (ValueError,TypeError):
        stored=[]
    return set(stored) or catalogue.label_languages(row['title'])


def preferred_keys(con, playlist_id, excluded=(), stage=None):
    language = preference(con, playlist_id)
    if not language:
        return []
    recover_saved_languages(con,playlist_id)
    rows = con.execute("""SELECT j.id,a.asset_key,a.title,k.codes,l.priority FROM skip_jobs j
      JOIN skip_assets a USING(asset_key) LEFT JOIN skip_asset_languages k USING(asset_key)
      LEFT JOIN skip_language_priority l USING(asset_key)
      WHERE a.playlist_id=? AND j.status='queued' AND j.attempts<3""", (playlist_id,)).fetchall()
    import skip_catalogue as catalogue
    result = []
    for row in rows:
        if row['id'] in excluded or stage is not None and (row['priority'] if row['priority'] is not None else 2) != stage:
            continue
        codes = asset_codes(row,catalogue)
        if language in codes:
            result.append(row['asset_key'])
    return result


def source_stage(con,playlist_id,fallback):
    if not preference(con,playlist_id):
        return fallback
    row=con.execute("""SELECT MIN(COALESCE(l.priority,2)) FROM skip_jobs j JOIN skip_assets a USING(asset_key)
      LEFT JOIN skip_language_priority l USING(asset_key) WHERE a.playlist_id=? AND j.status='queued' AND j.attempts<3""",(playlist_id,)).fetchone()
    return row[0] if row and row[0] is not None else fallback


class PreferredConnection:
    """Filter the existing scheduler so its focus/reference rules still apply.

    The predicate uses a temporary in-memory set passed as JSON, avoiding a
    queue rewrite and SQLite's parameter limit for large catalogues.
    """
    def __init__(self, con, keys):
        self.con, self.keys = con, json.dumps(keys)

    def execute(self, sql, params=()):
        if ('SELECT' in sql.upper() and 'skip_jobs j' in sql and
                'skip_assets a' in sql and 'WHERE a.playlist_id=?' in sql):
            predicate = "WHERE a.asset_key IN (SELECT value FROM json_each(?)) AND a.playlist_id=?"
            sql = sql.replace('WHERE a.playlist_id=?', predicate, 1)
            # These scheduler statements have no parameters before WHERE.
            if sql.split('WHERE', 1)[0].count('?'):
                raise ValueError('unsupported_source_preference_query')
            params = (self.keys, *params)
        return self.con.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self.con, name)


def install(catalogue=None, schedule=None):
    if catalogue is None and schedule is not None:
        import skip_catalogue as catalogue
    if catalogue is not None and not getattr(catalogue, '_source_preferences', False):
        catalogue._source_preferences = True
        original_priority = catalogue.language_priority
        @wraps(original_priority)
        def rank(row, categories=None, fallback=2):
            value = original_priority(row, categories, fallback)
            codes = declared_codes(catalogue, row)
            if not codes and isinstance(row, dict):
                ranks = [(categories or {})[key] for key in catalogue.category_ids(row) if key in (categories or {})]
                best = min(ranks) if ranks else None
                if best is not None:
                    codes = set().union(*(getattr(r, 'codes', ()) for r in ranks if r == best))
            return LanguagePriority(value, codes)
        catalogue.language_priority = rank
        original_asset, original_series = catalogue.set_asset_language, catalogue.set_series_language
        @wraps(original_asset)
        def asset_language(con, asset_key, priority):
            original_asset(con, asset_key, int(priority))
            migrate(con)
            codes = getattr(priority, 'codes', ())
            if not codes:
                stored=con.execute('''SELECT s.codes FROM skip_series_languages s JOIN skip_catalogue_episodes e
                  ON e.playlist_id=s.playlist_id AND e.series_id=s.series_id WHERE e.asset_key=? LIMIT 1''',(asset_key,)).fetchone()
                codes=json.loads(stored[0]) if stored else ()
            if codes:
                con.execute('INSERT OR REPLACE INTO skip_asset_languages VALUES(?,?,?)',
                            (asset_key, json.dumps(sorted(codes)), 'provider_or_structured_tag'))
        @wraps(original_series)
        def series_language(con, playlist_id, series_id, priority):
            original_series(con, playlist_id, series_id, int(priority))
            migrate(con)
            codes = getattr(priority, 'codes', ())
            if codes:
                encoded = json.dumps(sorted(codes))
                con.execute('INSERT OR REPLACE INTO skip_series_languages VALUES(?,?,?)', (playlist_id, str(series_id), encoded))
                con.execute("""INSERT OR REPLACE INTO skip_asset_languages
                  SELECT asset_key,?,'provider_series' FROM skip_catalogue_episodes WHERE playlist_id=? AND series_id=?""",
                            (encoded, playlist_id, str(series_id)))
        catalogue.set_asset_language, catalogue.set_series_language = asset_language, series_language

    if schedule is not None and not getattr(schedule, '_source_preferences', False):
        schedule._source_preferences = True
        original_select, original_current, original_remember, original_ready = schedule.select_job, schedule.current_playlist, schedule.remember, schedule.ready
        @wraps(original_ready)
        def ready(con,playlist_id,*,stage=None,**kwargs):
            fallback=schedule.language_stage(con) if stage is None else stage
            return original_ready(con,playlist_id,stage=source_stage(con,playlist_id,fallback),**kwargs)
        @wraps(original_select)
        def select(con, playlist_id, excluded=(), *, stage=None,**kwargs):
            fallback = schedule.language_stage(con) if stage is None else stage
            actual_stage=source_stage(con,playlist_id,fallback)
            keys = preferred_keys(con, playlist_id, excluded, actual_stage) if playlist_id is not None else []
            if keys:
                job, reason = original_select(PreferredConnection(con, keys), playlist_id, excluded, stage=actual_stage,**kwargs)
                if job is not None:
                    from skip_scene_reliability import event
                    row=con.execute('SELECT a.title,k.codes FROM skip_assets a LEFT JOIN skip_asset_languages k USING(asset_key) WHERE asset_key=?',(job['asset_key'],)).fetchone()
                    codes=sorted(asset_codes(row,catalogue))
                    event(con,'source_language',job['asset_key'],playlist_id=playlist_id,
                          preferred_language=preference(con,playlist_id),selection='preferred',codes=codes)
                    return job, reason
            job,reason=original_select(con, playlist_id, excluded, stage=actual_stage,**kwargs)
            if job is not None and preference(con,playlist_id):
                from skip_scene_reliability import event
                row=con.execute('SELECT a.title,k.codes FROM skip_assets a LEFT JOIN skip_asset_languages k USING(asset_key) WHERE asset_key=?',(job['asset_key'],)).fetchone()
                codes=sorted(asset_codes(row,catalogue))
                event(con,'source_language',job['asset_key'],playlist_id=playlist_id,
                      preferred_language=preference(con,playlist_id),selection='fallback',codes=codes)
            return job,reason
        @wraps(original_current)
        def current(con, excluded=(), *, stage=None,**kwargs):
            selected = original_current(con, excluded, stage=stage,**kwargs)
            if kwargs.get('parallel') or kwargs.get('lane_id') is not None:
                return selected
            actual_stage = schedule.language_stage(con) if stage is None else stage
            migrate(con)
            candidates = [r['id'] for r in schedule.playlists(con) if r['id'] not in excluded
                          and preference(con, r['id']) and schedule.ready(con, r['id'], stage=actual_stage)]
            # Lane-scoped connection views naturally restrict this set to one
            # source. With a shared controller, rotate at job boundaries.
            if len(candidates) > 1:
                served = dict(con.execute('SELECT playlist_id,last_served FROM skip_source_rotation'))
                return min(candidates, key=lambda pid: (served.get(pid, 0), pid))
            return selected
        @wraps(original_remember)
        def remember(con, job,*args,**kwargs):
            original_remember(con, job,*args,**kwargs)
            migrate(con)
            row = con.execute('SELECT playlist_id FROM skip_assets WHERE asset_key=?', (job['asset_key'],)).fetchone()
            if row:
                con.execute('INSERT OR REPLACE INTO skip_source_rotation VALUES(?,?)', (row[0], time.time()))
        schedule.select_job, schedule.current_playlist, schedule.remember, schedule.ready = select, current, remember, ready
