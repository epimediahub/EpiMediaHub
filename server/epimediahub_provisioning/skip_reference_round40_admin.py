"""Authenticated, exact-ID review of EpiScene round-40 owner-marked references.

The shadow DB has *attested device observations*, NOT verified administrator
labels. Until the administrator explicitly confirms a frozen preview, this
module performs no writes, and it never approves unrelated machine markers.
"""
from __future__ import annotations
import hashlib
import json
import secrets
import sqlite3
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone

SHADOW=Path('/var/lib/episcene-learning/reference-round-40/shadow.sqlite3')
MAX_ROWS=80
KINDS={'intro':300_000,'recap':300_000,'outro':900_000}
EXPLICITLY_INVALID={2282}

def _shadow_records(path=SHADOW):
    if path.is_symlink() or not path.is_file():
        return [], 'Die Referenz-Datenbank ist hier nicht verfügbar.'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        records=[dict(row) for row in db.execute("""SELECT marker_id,ref,title,season,episode,playlist_id,
               asset_key,kind,start_ms,end_ms,provenance,verified_backend
               FROM owner_attested_round40 ORDER BY marker_id""")]
    if not 1<=len(records)<=MAX_ROWS:
        return [], 'Referenzumfang unerwartet. Keine Sammelfreigabe.'
    if any(row['marker_id'] in EXPLICITLY_INVALID or row['provenance']!='owner_chat_batch_attestation_2026_10_14'
           or row['verified_backend']!=0 for row in records):
        return [], 'Referenzherkunft/Status ungültig. Keine Sammelfreigabe.'
    return records,None

def preview(con,shadow_path=SHADOW):
    """All device rows checked against exact immutable attested fields."""
    shadow,error=_shadow_records(shadow_path)
    if error:
        return dict(eligible=[],excluded=[],digest='',error=error,totals={})
    eligible,excluded=[],[]
    for ref in shadow:
        row=con.execute("""SELECT r.*,a.playlist_id current_playlist,
                 a.source_key current_source_key,a.season current_season,
                 a.episode current_episode,a.duration_ms current_duration,
                 a.asset_key current_asset_key
                 FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
                 WHERE r.id=?""",(ref['marker_id'],)).fetchone()
        reason=None
        if ref['playlist_id'] is None or not ref['asset_key']:
            reason='Keine Playlist-/Asset-Verknüpfung'
        elif row is None:
            reason='Asset fehlt oder passt nicht'
        else:
            row=dict(row)
            if (row['source']!='device' or row['status']!='pending' or row['disabled']
                or row['media_type']!='episode' or row['segment_type']!=ref['kind']
                or row['asset_key']!=ref['asset_key'] or row['current_playlist']!=ref['playlist_id']
                or row['current_source_key']!=row['source_key']
                or row['season']!=ref['season'] or row['episode']!=ref['episode']
                or row['current_season']!=ref['season'] or row['current_episode']!=ref['episode']
                or row['start_ms']!=ref['start_ms'] or row['end_ms']!=ref['end_ms']
                or abs(row['duration_ms']-row['current_duration'])>500
                or row['title'].casefold().strip()!=ref['title'].casefold().strip()):
                reason='Manueller Marker geändert, entschieden oder Quelle abweichend'
            elif (not 0<=row['start_ms']<row['end_ms']<=row['duration_ms']
                  or row['end_ms']-row['start_ms']<5000
                  or row['end_ms']-row['start_ms']>KINDS[ref['kind']]):
                reason='Unzulässige Markerzeit'
            elif con.execute("""SELECT 1 FROM skip_records d
                 WHERE d.asset_key=? AND d.segment_type=? AND d.id<>?
                 AND d.status='pending' AND d.source='device'
                 AND ABS(d.duration_ms-?)<=2000 LIMIT 1""",
                 (row['asset_key'],row['segment_type'],row['id'],row['duration_ms'])).fetchone():
                reason='Andere offene manuelle Markierung derselben Datei'
            elif con.execute("""SELECT 1 FROM skip_records d WHERE d.asset_key=?
                 AND d.segment_type=? AND d.id<>? AND d.status IN ('approved','rejected')
                 AND ABS(d.duration_ms-?)<=2000 LIMIT 1""",
                 (row['asset_key'],row['segment_type'],row['id'],row['duration_ms'])).fetchone():
                reason='Bereits entschiedener Marker derselben Datei'
        if reason:
            excluded.append(dict(id=ref['marker_id'],ref=ref['ref'],kind=ref['kind'],reason=reason))
        else:
            eligible.append(dict(id=row['id'],ref=ref['ref'],title=ref['title'],
                 season=ref['season'],episode=ref['episode'],kind=ref['kind'],
                 playlist_id=ref['playlist_id'],asset_key=ref['asset_key'],
                 start_ms=ref['start_ms'],end_ms=ref['end_ms'],
                 duration_ms=row['duration_ms'],created_at=row['created_at']))
    # A batch confirmation should never guess whether a duplicate is correct.
    c=Counter((r['asset_key'],r['kind']) for r in eligible)
    if any(v>1 for v in c.values()):
        return dict(eligible=[],excluded=excluded,digest='',error='Doppelte Zeitmarken. Keine Sammelfreigabe.',totals={})
    snapshot=json.dumps(eligible,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    digest=hashlib.sha256(snapshot.encode()).hexdigest() if eligible else ''
    return dict(eligible=eligible,excluded=excluded,digest=digest,error=None,
                totals=dict(eligible=len(eligible),excluded=len(excluded),
                    intro=sum(x['kind']=='intro' for x in eligible),
                    recap=sum(x['kind']=='recap' for x in eligible),
                    outro=sum(x['kind']=='outro' for x in eligible)))

def execute(con,fingerprint,expected_count,shadow_path=SHADOW):
    """Call ONLY behind the existing authenticated, CSRF-protected POST."""
    con.execute('BEGIN IMMEDIATE')
    batch=preview(con,shadow_path)
    if batch['error'] or not batch['eligible'] or batch['digest']!=fingerprint or len(batch['eligible'])!=expected_count:
        raise ValueError('Referenzstand verändert. Bitte Vorschau erneut prüfen.')
    from skip_markers import review_record, wake_reference_jobs
    sources=set()
    for item in batch['eligible']:
        row=con.execute('SELECT * FROM skip_records WHERE id=?',(item['id'],)).fetchone()
        if row is None or row['status']!='pending' or row['source']!='device':
            raise ValueError('Referenzstand während der Bestätigung geändert.')
        review_record(con,row,'approve',item['start_ms'],item['end_ms'],False,wake=False)
        sources.add(row['source_key'])
    for source in sources:
        wake_reference_jobs(con,source)
    con.execute("""CREATE TABLE IF NOT EXISTS skip_reference_round40_admin_audit(
        id INTEGER PRIMARY KEY,confirmed_utc TEXT NOT NULL,reviewed_marker_ids_json TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL,verification_method TEXT NOT NULL)""")
    con.execute("""INSERT INTO skip_reference_round40_admin_audit(
        confirmed_utc,reviewed_marker_ids_json,snapshot_sha256,verification_method)
        VALUES(?,?,?,'authenticated_admin_session_csrf_exact_snapshot')""",
        (datetime.now(timezone.utc).isoformat(),json.dumps([r['id'] for r in batch['eligible']]),batch['digest']))
    return len(batch['eligible'])


def install(app,db,web_auth):
    from flask import abort,redirect,render_template,request,session,url_for
    @app.get('/admin/skip/reference-round40')
    def episcene_round40_preview():
        guard=web_auth()
        if guard:return guard
        session.setdefault('skip_csrf',secrets.token_urlsafe(32))
        with db() as con:
            details=preview(con)
        return render_template('skip_reference_round40.html',batch=details,csrf=session['skip_csrf'])

    @app.post('/admin/skip/reference-round40/confirm')
    def episcene_round40_confirm():
        guard=web_auth()
        if guard:return guard
        known=session.get('skip_csrf','')
        token=request.form.get('csrf','')
        if not known or not secrets.compare_digest(known,token):
            abort(403)
        if request.form.get('confirmation')!='REFERENZEN BESTÄTIGEN':
            abort(400)
        fingerprint=request.form.get('snapshot','')
        count=request.form.get('count','')
        if (len(fingerprint)!=64 or any(c not in '0123456789abcdef' for c in fingerprint)
                or not count.isdigit() or not 1<=int(count)<=MAX_ROWS):
            abort(400)
        with db() as con:
            try:
                done=execute(con,fingerprint,int(count))
            except ValueError:
                con.rollback()
                return redirect(url_for('episcene_round40_preview',changed=1),code=303)
        return redirect(url_for('episcene_round40_preview',approved=done),code=303)
