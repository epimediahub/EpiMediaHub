#!/usr/bin/env python3
"""Bounded second-look for independent episodes used by approved visual markers.

Only reprioritizes verified same-series/season EpiScene visual peers, never
publishes markers or lowers acceptance thresholds. Normal provider playback
scheduler and existing release gates remain authoritative.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import fcntl,json,os,re,sqlite3,sys,time
import shutil

DB=Path('/var/lib/epimediahub/provisioning.db')
ENGINE=Path('/opt/episcene-learning')
CODE=Path('/opt/epimediahub/provisioning')
LOCK=Path('/var/lib/epimediahub/.episcene-one-step-releases.lock')
BACKUPS=Path('/var/backups/epimediahub/reciprocal-visual-peers')
MAX_PER_RUN=4
MAX_DAILY=8
STATES=('done','review','no_match','no_reference','partial')
KINDS=('intro','recap','outro')

def evidence(text):
    try:
        value=json.loads(text or '{}')
        return value if isinstance(value,dict) else {}
    except (TypeError,ValueError):
        return {}

def partner_keys(approved):
    """Selection signal only: one confirmed marker with >=3 independent matches.

    A selected peer still requires fresh analysis and the original approval gate.
    """
    result=defaultdict(set)
    for row in approved:
        proof=evidence(row['evidence_json'])
        d=proof.get('decision')
        if not isinstance(d,dict) or proof.get('audio_visual_disagreement') is True:
            continue
        if d.get('status')!='AUTO_CONFIRMED' or d.get('support',0)<3:
            continue
        if d.get('ambiguous') is True or d.get('boundaries_confirmed') is not True:
            continue
        matches=d.get('matches',[])
        if not isinstance(matches,list) or len(matches)<3:
            continue
        valid=set()
        for match in matches:
            if not isinstance(match,dict):
                continue
            key=match.get('partner')
            if (not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{64}',key)
                or match.get('boundaries_confirmed') is not True
                or not isinstance(match.get('quality'),(int,float))
                or match['quality']<0.95):
                continue
            valid.add(key)
        if len(valid)<3:continue
        family=(row['playlist_id'],row['source_key'],row['season'],row['segment_type'])
        for key in valid:
            if key!=row['asset_key']:
                result[family].add(key)
    return result

def table_ok(db,name,required):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():
        return False
    cols={r[1] for r in db.execute('PRAGMA table_info('+name+')')}
    return set(required)<=cols

def get_plan(db,v2,now):
    schemas={
      'skip_records':('id','status','source','disabled','asset_key','source_key',
                      'season','episode','segment_type','duration_ms'),
      'skip_assets':('asset_key','source_key','playlist_id','season','episode','title','duration_ms','media_type'),
      'skip_jobs':('id','asset_key','status','updated_at','attempts'),
      'skip_auto_evidence':('record_id','evidence_json','human_review'),
      'episcene_safe_release_retries':('asset_key','attempt_count','last_requeued_utc','original_job_status'),
      'skip_analysis_playlists':('id','archived'),
      'skip_analysis_sources':('playlist_id','enabled'),
      'skip_auto_settings':('playlist_id','enabled'),
      'skip_presence':('playlist_id','expires_at'),
      'skip_release_settings':('playlist_id',),
      'skip_auto_blocks':('asset_key','kind','duration_ms')
    }
    if not all(table_ok(db,t,cols) for t,cols in schemas.items()):
        raise RuntimeError('STOP_EXPECTED_RELEASE_SCHEMA_MISSING')
    from skip_release import enabled as release_enabled
    if not release_enabled(db,10):
        raise RuntimeError('STOP_THE_BEST_RELEASE_DISABLED')
    if db.execute('SELECT 1 FROM skip_presence WHERE playlist_id=10 AND expires_at>? LIMIT 1',
                  (int(time.time()),)).fetchone():
        raise RuntimeError('STOP_THE_BEST_VIEWER_ACTIVE')
    if not db.execute("""SELECT 1 FROM skip_analysis_playlists p
      JOIN skip_analysis_sources s ON s.playlist_id=p.id AND s.enabled=1
      JOIN skip_auto_settings a ON a.playlist_id=p.id AND a.enabled=1
      WHERE p.id=10 AND p.archived=0""").fetchone():
        raise RuntimeError('STOP_THE_BEST_ANALYSIS_DISABLED')
    approved=db.execute("""
      SELECT r.asset_key,r.source_key,r.season,r.segment_type,
        a.playlist_id, e.evidence_json
      FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
      JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE a.playlist_id=10 AND a.media_type='episode'
       AND r.status='approved' AND r.disabled=0 AND r.source='episcene'
       AND r.segment_type IN ('intro','recap','outro')
       AND r.source_key=a.source_key AND r.season=a.season
      ORDER BY r.id DESC LIMIT 500""").fetchall()
    peers=partner_keys(approved)
    if not peers:return [],{'no_confirmed_reciprocal_peers':1}
    target=set().union(*peers.values())
    if len(target)>120:
        raise RuntimeError('STOP_UNEXPECTED_PEER_TARGET_COUNT')
    keys=sorted(target)
    placeholders=','.join('?' for _ in keys)
    raw=db.execute("""
      SELECT j.id job_id,j.asset_key,j.status original_status,
        a.playlist_id,a.source_key,a.season,a.episode,a.duration_ms,
        a.media_type,a.title,r.segment_type kind,r.id marker_id,e.evidence_json,
        z.attempt_count,z.last_requeued_utc
      FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
      JOIN skip_records r ON r.asset_key=a.asset_key
        AND r.status='pending' AND r.source IN
        ('audio','audio_repetition','episcene','theintrodb','chapter')
        AND r.source_key=a.source_key AND r.season=a.season
        AND r.episode=a.episode AND ABS(r.duration_ms-a.duration_ms)<=2000
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      LEFT JOIN episcene_safe_release_retries z ON z.asset_key=j.asset_key
      WHERE a.playlist_id=10 AND a.asset_key IN ("""+placeholders+""")
        AND a.media_type='episode' AND a.duration_ms>0 AND
        j.status IN ('done','review','no_match','no_reference','partial')
      ORDER BY j.updated_at,j.id
    """,keys).fetchall()
    by_asset_kind=defaultdict(list)
    for row in raw:
        rec=dict(row); family=(rec['playlist_id'],rec['source_key'],rec['season'],rec['kind'])
        if rec['asset_key'] not in peers.get(family,set()):
            continue
        if rec['title'].strip().casefold()!='futurama':continue
        if rec['attempt_count'] not in (None,1):continue
        if rec['attempt_count']==1:
            # A second look only on a different day, never a tight retry loop.
            stamp=rec['last_requeued_utc']
            if not isinstance(stamp,str) or stamp[:10]>=now[:10]:continue
        rec['evidence']=evidence(rec.get('evidence_json'))
        if v2.protected(db,rec):continue
        by_asset_kind[(rec['asset_key'],rec['kind'])].append(rec)
    # Never choose between multiple pending markers for the same asset/kind.
    possibilities=[]
    for (asset,kind),options in by_asset_kind.items():
        if len(options)!=1:continue
        r=options[0]
        possibilities.append(r)
    # One kind per asset, with preference for a first attempt.
    options_by_asset=defaultdict(list)
    for row in possibilities:options_by_asset[row['asset_key']].append(row)
    ranking=[]
    for asset,rows in options_by_asset.items():
        row=sorted(rows,key=lambda x:(x['attempt_count'] is not None,
                                      x['kind']!='intro',x['job_id']))[0]
        ranking.append(row)
    ranking.sort(key=lambda r:(r['attempt_count'] is not None,
                    r['kind']!='intro',r['season'],r['episode'],r['job_id']))
    today=now[:10]
    spent=db.execute("""SELECT COUNT(*) FROM episcene_safe_release_retries
         WHERE substr(last_requeued_utc,1,10)=?""",(today,)).fetchone()[0]
    capacity=max(0,min(MAX_PER_RUN,MAX_DAILY-spent))
    return ranking[:capacity],dict(approved_reference_count=len(approved),
      visual_peer_groups=len(peers),candidate_assets=len(ranking),
      daily_retry_slots_remaining=max(0,MAX_DAILY-spent),
      selected=len(ranking[:capacity]))

def execute(db,selection,now):
    from skip_schedule import request_series
    changed=0
    for rec in selection:
        update=db.execute("""UPDATE skip_jobs
          SET status='queued',attempts=0,
           detail='Rückwirkender Bildkonsens: bestätigte Referenzfolge vorhanden',
           updated_at=? WHERE id=? AND asset_key=? AND status=?""",
          (now,rec['job_id'],rec['asset_key'],rec['original_status']))
        if update.rowcount!=1:
            raise RuntimeError('STOP_REQUEUE_RACE_DETECTED')
        if rec['attempt_count'] is None:
            db.execute("""INSERT INTO episcene_safe_release_retries
             (asset_key,last_requeued_utc,attempt_count,original_job_status)
             VALUES(?,?,1,?)""",(rec['asset_key'],now,rec['original_status']))
        else:
            if db.execute("""UPDATE episcene_safe_release_retries
                SET last_requeued_utc=?,attempt_count=2
                WHERE asset_key=? AND attempt_count=1
                  AND substr(last_requeued_utc,1,10)<?""",
                (now,rec['asset_key'],now[:10])).rowcount!=1:
                raise RuntimeError('STOP_SECOND_RETRY_RACE')
        request_series(db,rec['asset_key'],reason='playback')
        changed+=1
    return changed

def backup():
    if DB.is_symlink() or BACKUPS.is_symlink():
        raise RuntimeError('STOP_SYMLINK_BACKUP')
    BACKUPS.mkdir(parents=True,exist_ok=True,mode=0o700)
    BACKUPS.chmod(0o700)
    if shutil.disk_usage(BACKUPS).free<2*DB.stat().st_size+64*1024*1024:
        raise RuntimeError('STOP_INSUFFICIENT_BACKUP_SPACE')
    name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+str(os.getpid())+'.sqlite3'
    dest=BACKUPS/name
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True) as old:
        with sqlite3.connect(dest) as new:
            old.backup(new)
            if new.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                dest.unlink(missing_ok=True)
                raise RuntimeError('STOP_DATABASE_BACKUP_CHECK')
    dest.chmod(0o600)
    return dest

def main():
    if os.geteuid()!=0 or not DB.is_file() or DB.is_symlink() or not ENGINE.is_dir() or not CODE.is_dir():
        raise RuntimeError('STOP_EXPECTED_INSTALLATION_MISSING')
    sys.path[:0]=[str(ENGINE),str(CODE)]
    import safe_release_rollout_v2 as v2
    import safe_release_rollout as original
    if not callable(getattr(v2,'protected',None)) or original.MAX_REQUEUE_PER_DAY!=8:
        raise RuntimeError('STOP_RELEASE_POLICY_VERSION_UNEXPECTED')
    if LOCK.is_symlink():raise RuntimeError('STOP_LOCK_SYMLINK')
    with LOCK.open('a') as fd:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            now=datetime.now(timezone.utc).isoformat(timespec='seconds')
            with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=20) as con:
                con.row_factory=sqlite3.Row
                con.execute('PRAGMA query_only=ON')
                selection,stats=get_plan(con,v2,now)
            print('PEER_PREFLIGHT:',json.dumps(stats,sort_keys=True),flush=True)
            if not selection:
                print('NO_ELIGIBLE_PEERS; MARKERS_UNCHANGED')
                return
            dest=backup()
            print('DATABASE_BACKUP_OK:',dest,flush=True)
            with sqlite3.connect(DB,timeout=30) as con:
                con.row_factory=sqlite3.Row
                con.execute('BEGIN IMMEDIATE')
                try:
                    current,fresh=get_plan(con,v2,now)
                    if [r['job_id'] for r in current]!=[r['job_id'] for r in selection]:
                        raise RuntimeError('STOP_PLAN_CHANGED')
                    amount=execute(con,current,now)
                    con.commit()
                except BaseException:
                    con.rollback()
                    raise
            print('RECIPROCAL_PEER_REQUEUED:',amount)
            print('RELEASE_GATES_UNCHANGED; NO_MARKERS_DIRECTLY_APPROVED')
            print('NORMAL_ANALYSIS_LANES_OWN_PROVIDER_ACCESS')
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN)

if __name__=='__main__':
    try:main()
    except Exception as err:
        msg=(str(err) if isinstance(err,RuntimeError) and
             str(err).startswith('STOP_') else 'STOP_'+type(err).__name__)
        print('SAFE_STOP:',msg)
        raise SystemExit(1)
