"""Read cached aggregate statistics; keep full queue planning off HTTP GETs."""
import json
import time


def migrate(con):
    con.execute('''CREATE TABLE IF NOT EXISTS skip_dashboard_stats(
      id INTEGER PRIMARY KEY CHECK(id=1),value_json TEXT NOT NULL,updated_at INTEGER NOT NULL)''')


def refresh(con, *, force=False):
    stamp=int(time.time())
    row=con.execute('SELECT updated_at FROM skip_dashboard_stats WHERE id=1').fetchone()
    if not force and row and stamp-row['updated_at']<30:
        return 0
    from skip_catalogue import dashboard
    from skip_schedule import overview
    value=dict(catalogues=dashboard(con),schedule=overview(con))
    # Calculation uses read snapshots; only publication acquires the writer.
    con.execute('''INSERT INTO skip_dashboard_stats VALUES(1,?,?)
      ON CONFLICT(id) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at''',
      (json.dumps(value,separators=(',',':')),int(time.time())))
    return 1


def read(con):
    row=con.execute('SELECT value_json,updated_at FROM skip_dashboard_stats WHERE id=1').fetchone()
    if row:
        try:
            value=json.loads(row['value_json'])
            if isinstance(value,dict) and isinstance(value.get('catalogues'),list) and isinstance(value.get('schedule'),dict):
                return value|dict(updated_at=row['updated_at'])
        except (ValueError,TypeError):
            pass
    return dict(catalogues=[],schedule={},updated_at=0)


def catalogue_view(con, snapshot):
    from skip_catalogue import dashboard
    counts={row['id']:row for row in snapshot['catalogues'] if isinstance(row,dict) and 'id' in row}
    return dashboard(con,counts_cache=counts)


def schedule_view(con, snapshot):
    from skip_schedule import playlists
    rows=playlists(con)
    names={row['id']:row['name'] for row in rows}
    for position,row in enumerate(rows,1):row['position']=position
    cached=snapshot['schedule']
    current=cached.get('current')
    if not isinstance(current,dict) or current.get('playlist_id') not in names:
        current=None
    elif current.get('asset_key') and not con.execute(
            "SELECT 1 FROM skip_jobs WHERE asset_key=? AND status IN ('queued','running')",
            (current['asset_key'],)).fetchone():
        current=None
    if current:
        current=dict(current,playlist_name=names[current['playlist_id']])
    stage=cached.get('language_stage')
    # Live running state is bounded by the status index. Its series counts read
    # only that series, not the entire queue. Playlist settings stay live too.
    running=con.execute('''SELECT a.*,COALESCE(l.priority,2) language FROM skip_jobs j
      JOIN skip_assets a USING(asset_key)
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      LEFT JOIN skip_language_priority l USING(asset_key)
      WHERE j.status='running' ORDER BY j.id LIMIT 1''').fetchone()
    if running:
        asset=dict(running)
        counts=con.execute('''SELECT COUNT(*) files,
          SUM(j.status NOT IN ('queued','running','disabled')) processed,
          SUM(j.status IN ('failed','unmatched','no_reference')) problems,
          SUM(j.status='review') review FROM skip_assets a JOIN skip_jobs j USING(asset_key)
          WHERE a.playlist_id=? AND a.source_key=?''',(asset['playlist_id'],asset['source_key'])).fetchone()
        current=asset|dict(counts)|dict(playlist_name=names[asset['playlist_id']])
        stage=asset['language']
    return dict(playlists=rows,current=current,language_stage=stage if rows else None,
                statistics_pending=not snapshot['updated_at'] or bool(cached.get('current') and not current))
