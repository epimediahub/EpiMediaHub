"""Incremental series progress shared by web processes and the analysis worker."""
from __future__ import annotations

import time

from skip_markers import page_number, now

FILTERS = {'all', 'completed', 'with_intro', 'missing_intro', 'open'}
METRICS = ('files', 'episodes', 'intros', 'disabled', 'pending', 'analyzed',
           'not_found', 'waiting', 'running', 'failed', 'no_reference', 'paused', 'inventory_pending')
FIELDS = ('playlist_id', 'source_key', 'title', 'year', *METRICS)
POLICY = 'series_progress_cache_v1'


def migrate(con):
    con.executescript('''
      CREATE TABLE IF NOT EXISTS skip_progress_series(
        playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE,
        source_key TEXT NOT NULL,title TEXT NOT NULL,year TEXT NOT NULL,
        ''' + ','.join(name + ' INTEGER NOT NULL' for name in METRICS) + ''',
        PRIMARY KEY(playlist_id,source_key));
      CREATE TABLE IF NOT EXISTS skip_progress_dirty(
        playlist_id INTEGER NOT NULL,source_key TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(playlist_id,source_key));
      CREATE TABLE IF NOT EXISTS skip_progress_clock(id INTEGER PRIMARY KEY CHECK(id=1),value INTEGER NOT NULL);
      INSERT OR IGNORE INTO skip_progress_clock VALUES(1,0);
      CREATE INDEX IF NOT EXISTS idx_skip_progress_dirty_source ON skip_progress_dirty(source_key);
      CREATE INDEX IF NOT EXISTS idx_skip_progress_dirty_order ON skip_progress_dirty(revision);
      CREATE INDEX IF NOT EXISTS idx_skip_progress_assets
        ON skip_assets(playlist_id,source_key) WHERE media_type='episode';
      CREATE INDEX IF NOT EXISTS idx_skip_progress_intro
        ON skip_records(asset_key,media_type,season,episode,status,reviewed_at DESC,id DESC,duration_ms,disabled)
        WHERE segment_type='intro';
    ''')
    # Pure SQL triggers also observe writes from another Gunicorn process,
    # the worker, and older command-line helpers. Never modify the markers.
    tick = 'UPDATE skip_progress_clock SET value=value+1 WHERE id=1;'
    revision = '(SELECT value FROM skip_progress_clock WHERE id=1)'
    upsert = ' ON CONFLICT(playlist_id,source_key) DO UPDATE SET revision=excluded.revision;'
    def asset(ref):
        return (tick + "INSERT INTO skip_progress_dirty SELECT " + ref + ".playlist_id," + ref +
                ".source_key," + revision + " WHERE " + ref + ".media_type='episode'" + upsert)
    def file(ref):
        return (tick + "INSERT INTO skip_progress_dirty SELECT playlist_id,source_key," + revision + " FROM skip_assets "
                "WHERE asset_key=" + ref + ".asset_key AND media_type='episode'" + upsert)
    def series(ref):
        return (tick + "INSERT INTO skip_progress_dirty SELECT DISTINCT a.playlist_id,a.source_key," + revision + " "
                "FROM skip_catalogue_episodes e JOIN skip_assets a ON a.asset_key=e.asset_key "
                "WHERE e.playlist_id=" + ref + ".playlist_id AND e.series_id=" + ref +
                ".series_id AND a.media_type='episode'" + upsert)
    triggers = [
        ('asset_add', 'AFTER INSERT ON skip_assets', asset('NEW')),
        ('asset_remove', 'AFTER DELETE ON skip_assets', asset('OLD')),
        ('asset_change', 'AFTER UPDATE OF playlist_id,source_key,media_type,season,episode,duration_ms,title,year ON skip_assets WHEN ' +
         ' OR '.join('OLD.' + field + ' IS NOT NEW.' + field for field in ('playlist_id','source_key','media_type','season','episode','duration_ms','title','year')), asset('OLD') + asset('NEW')),
        ('job_add', 'AFTER INSERT ON skip_jobs', file('NEW')),
        ('job_remove', 'AFTER DELETE ON skip_jobs', file('OLD')),
        ('job_change', 'AFTER UPDATE OF status,asset_key ON skip_jobs WHEN OLD.status IS NOT NEW.status OR OLD.asset_key IS NOT NEW.asset_key', file('OLD') + file('NEW')),
        ('intro_add', "AFTER INSERT ON skip_records WHEN NEW.segment_type='intro'", file('NEW')),
        ('intro_remove', "AFTER DELETE ON skip_records WHEN OLD.segment_type='intro'", file('OLD')),
        ('intro_change', "AFTER UPDATE OF asset_key,media_type,season,episode,duration_ms,segment_type,status,disabled,reviewed_at ON skip_records WHEN OLD.segment_type='intro' OR NEW.segment_type='intro'", file('OLD') + file('NEW')),
        ('episode_add', 'AFTER INSERT ON skip_catalogue_episodes', file('NEW')),
        ('episode_remove', 'AFTER DELETE ON skip_catalogue_episodes', file('OLD')),
        ('episode_change', 'AFTER UPDATE ON skip_catalogue_episodes', file('OLD') + file('NEW')),
        ('series_add', 'AFTER INSERT ON skip_catalogue_series', series('NEW')),
        ('series_remove', 'AFTER DELETE ON skip_catalogue_series', series('OLD')),
        ('series_change', 'AFTER UPDATE OF playlist_id,series_id,pending_generation,status ON skip_catalogue_series', series('OLD') + series('NEW')),
    ]
    con.executescript('\n'.join('CREATE TRIGGER IF NOT EXISTS skip_progress_' + name + ' ' + event +
                              ' BEGIN ' + body + ' END;' for name, event, body in triggers))
    if not con.execute('SELECT 1 FROM skip_auto_maintenance WHERE name=?', (POLICY,)).fetchone():
        con.execute("""INSERT OR IGNORE INTO skip_progress_dirty
          SELECT DISTINCT playlist_id,source_key,(SELECT value FROM skip_progress_clock WHERE id=1)
          FROM skip_assets WHERE media_type='episode'""")
        con.execute('INSERT INTO skip_auto_maintenance VALUES(?,?)', (POLICY, now()))


def _metrics(con, playlist_id, source_key):
    # Materialize the per-file flags once. SQLite would otherwise repeat the
    # approved-marker lookup for every SUM that uses intro_disabled.
    rows = con.execute('''WITH files AS MATERIALIZED (
      SELECT a.playlist_id,a.source_key,a.title,a.year,a.season,a.episode,
        COALESCE(j.status,'queued') job_status,
        (SELECT r.disabled FROM skip_records r WHERE r.asset_key=a.asset_key
          AND r.media_type=a.media_type AND r.season=a.season AND r.episode=a.episode
          AND ABS(r.duration_ms-a.duration_ms)<=2000 AND r.segment_type='intro' AND r.status='approved'
          ORDER BY r.reviewed_at DESC,r.id DESC LIMIT 1) intro_disabled,
        EXISTS(SELECT 1 FROM skip_records r WHERE r.asset_key=a.asset_key
          AND r.media_type=a.media_type AND r.season=a.season AND r.episode=a.episode
          AND ABS(r.duration_ms-a.duration_ms)<=2000 AND r.segment_type='intro' AND r.status='pending') pending_intro,
        EXISTS(SELECT 1 FROM skip_catalogue_episodes e JOIN skip_catalogue_series s
          ON s.playlist_id=e.playlist_id AND s.series_id=e.series_id
          WHERE e.asset_key=a.asset_key AND e.playlist_id=a.playlist_id
          AND (s.pending_generation>0 OR s.status<>'ok')) inventory_pending
      FROM skip_assets a LEFT JOIN skip_jobs j ON j.asset_key=a.asset_key
      WHERE a.media_type='episode' AND a.playlist_id=? AND a.source_key=?
    ) SELECT playlist_id,source_key,MIN(title) title,MIN(year) year,COUNT(*) files,
        COUNT(DISTINCT CAST(season AS TEXT)||':'||CAST(episode AS TEXT)) episodes,
        COALESCE(SUM(intro_disabled=0),0) intros,COALESCE(SUM(intro_disabled=1),0) disabled,
        SUM(pending_intro) pending,SUM(job_status IN ('done','no_match','review')) analyzed,
        SUM(job_status IN ('done','no_match','review') AND COALESCE(intro_disabled,1)=1) not_found,
        SUM(job_status IN ('queued','running')) waiting,SUM(job_status='running') running,
        SUM(job_status IN ('failed','unmatched')) failed,SUM(job_status='no_reference') no_reference,
        SUM(job_status='disabled') paused,MAX(inventory_pending) inventory_pending
      FROM files GROUP BY playlist_id,source_key''', (playlist_id, source_key)).fetchone()
    return dict(rows) if rows else None


def refresh(con, limit=64, budget=.2, preferred_source=''):
    """Recompute only changed series, and hold the writer lock only to publish.

    Revision checks preserve changes committed while statistics were being
    read. A racing group stays dirty for the next request or worker invocation.
    """
    changed = []
    if preferred_source:
        changed.extend(con.execute('SELECT * FROM skip_progress_dirty WHERE source_key=? ORDER BY revision LIMIT ?',
                                   (preferred_source, limit)).fetchall())
    keys = {(r['playlist_id'], r['source_key']) for r in changed}
    for row in con.execute('SELECT * FROM skip_progress_dirty ORDER BY revision LIMIT ?', (limit,)).fetchall():
        key = (row['playlist_id'], row['source_key'])
        if len(changed) >= limit:
            break
        if key not in keys:
            keys.add(key)
            changed.append(row)
    calculated = []
    deadline = time.monotonic() + budget if budget is not None else None
    for row in changed:
        if calculated and deadline is not None and time.monotonic() >= deadline:
            break
        calculated.append((dict(row), _metrics(con, row['playlist_id'], row['source_key'])))
    if not calculated:
        return 0
    own_transaction = not con.in_transaction
    if own_transaction:
        con.execute('BEGIN IMMEDIATE')
    try:
        updated = 0
        for changed, metrics in calculated:
            key = (changed['playlist_id'], changed['source_key'])
            revision = con.execute('SELECT revision FROM skip_progress_dirty WHERE playlist_id=? AND source_key=?', key).fetchone()
            if not revision or revision[0] != changed['revision']:
                continue
            if metrics:
                con.execute('INSERT OR REPLACE INTO skip_progress_series (' + ','.join(FIELDS) +
                            ') VALUES(' + ','.join('?' for _ in FIELDS) + ')', tuple(metrics[k] for k in FIELDS))
            else:
                con.execute('DELETE FROM skip_progress_series WHERE playlist_id=? AND source_key=?', key)
            con.execute('DELETE FROM skip_progress_dirty WHERE playlist_id=? AND source_key=? AND revision=?', (*key, changed['revision']))
            updated += 1
        if own_transaction:
            con.commit()
        return updated
    except BaseException:
        if own_transaction:
            con.rollback()
        raise


def populate(con):
    """Warm the installed database or a private diagnostic snapshot offline."""
    total = 0
    while con.execute('SELECT 1 FROM skip_progress_dirty LIMIT 1').fetchone():
        updated = refresh(con, limit=512, budget=None)
        total += updated
        if not updated:
            break
    return total


def overview(con, selected='all', search='', page=1, preferred_source=''):
    selected = selected if selected in FILTERS else 'all'
    search = str(search).strip()[:120]
    refresh(con, preferred_source=preferred_source)
    rows = con.execute('''SELECT f.*,p.name playlist_name,c.name customer_name,
        COALESCE(s.enabled,0) analysis_enabled,c.enabled customer_enabled
      FROM skip_progress_series f JOIN customer_playlists p ON p.id=f.playlist_id JOIN customers c ON c.id=p.customer_id
      LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id
      ORDER BY LOWER(f.title),f.playlist_id,f.source_key''').fetchall()
    series = []
    for raw in rows:
        row = dict(raw)
        for name in ('intros','disabled'):
            row[name] = row[name] or 0
        row['missing'] = row['files'] - row['intros']
        row['complete'] = row['analyzed'] == row['files'] and not row['inventory_pending'] and not row['pending']
        row['percent'] = row['analyzed'] * 100 // row['files']
        if row['complete']:
            row['status'] = 'Analyse abgeschlossen'
        elif not row['analysis_enabled'] or not row['customer_enabled'] or row['paused']:
            row['status'] = 'Analyse pausiert'
        elif row['failed']:
            row['status'] = 'Zugriff oder Datei prüfen'
        elif row['no_reference']:
            row['status'] = 'Wartet auf eine Referenz'
        elif row['running']:
            row['status'] = 'Wird analysiert'
        elif row['pending']:
            row['status'] = 'Freigaben offen'
        else:
            row['status'] = 'Analyse offen'
        series.append(row)
    totals = dict(series=len(series), completed=sum(r['complete'] for r in series),
                  with_intro=sum(r['intros']>0 for r in series), missing_intro=sum(r['missing']>0 for r in series),
                  files=sum(r['files'] for r in series), intros=sum(r['intros'] for r in series))
    visible = [r for r in series if (not search or search.casefold() in (r['title']+' '+r['playlist_name']).casefold())
               and (selected=='all' or selected=='completed' and r['complete']
                    or selected=='with_intro' and r['intros']>0 or selected=='missing_intro' and r['missing']>0
                    or selected=='open' and not r['complete'])]
    pages = max(1,(len(visible)+19)//20)
    page = min(page_number(page),pages)
    budget = con.execute('SELECT count FROM skip_analysis_budget WHERE day=?', (now()[:10],)).fetchone()
    inventory_pending = con.execute('''SELECT COUNT(*) FROM skip_catalogue_series s
      JOIN skip_catalogue_runs r ON r.playlist_id=s.playlist_id
      WHERE s.seen_generation=r.generation AND (s.pending_generation>0 OR s.status<>'ok')''').fetchone()[0]
    return dict(rows=visible[(page-1)*20:page*20],total=len(visible),totals=totals,page=page,pages=pages,
                selected=selected,search=search,used_today=budget[0] if budget else 0,inventory_pending=inventory_pending,
                updating=con.execute('SELECT COUNT(*) FROM skip_progress_dirty').fetchone()[0])
