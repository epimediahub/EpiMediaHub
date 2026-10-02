"""Paginated series progress from all registered files, independent of recent logs."""
from __future__ import annotations

from skip_markers import page_number, now

FILTERS = {'all', 'completed', 'with_intro', 'missing_intro', 'open'}


def overview(con, selected='all', search='', page=1):
    selected = selected if selected in FILTERS else 'all'
    search = str(search).strip()[:120]
    rows = con.execute('''WITH files AS (
      SELECT a.*,COALESCE(j.status,'queued') job_status,
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
      FROM skip_assets a LEFT JOIN skip_jobs j ON j.asset_key=a.asset_key WHERE a.media_type='episode'
    ) SELECT f.playlist_id,f.source_key,MIN(f.title) title,MIN(f.year) year,p.name playlist_name,
        c.name customer_name,COUNT(*) files,COUNT(DISTINCT CAST(f.season AS TEXT)||':'||CAST(f.episode AS TEXT)) episodes,
        SUM(f.intro_disabled=0) intros,SUM(f.intro_disabled=1) disabled,
        SUM(f.pending_intro) pending,SUM(f.job_status IN ('done','no_match','review')) analyzed,
        SUM(f.job_status IN ('done','no_match','review') AND COALESCE(f.intro_disabled,1)=1) not_found,
        SUM(f.job_status IN ('queued','running')) waiting,SUM(f.job_status='running') running,
        SUM(f.job_status IN ('failed','unmatched')) failed,SUM(f.job_status='no_reference') no_reference,
        SUM(f.job_status='disabled') paused,MAX(f.inventory_pending) inventory_pending,
        COALESCE(s.enabled,0) analysis_enabled,c.enabled customer_enabled
      FROM files f JOIN customer_playlists p ON p.id=f.playlist_id JOIN customers c ON c.id=p.customer_id
      LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id
      GROUP BY f.playlist_id,f.source_key ORDER BY LOWER(MIN(f.title)),f.playlist_id,f.source_key''').fetchall()
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
                selected=selected,search=search,used_today=budget[0] if budget else 0,inventory_pending=inventory_pending)
