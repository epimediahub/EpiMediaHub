#!/usr/bin/env python3
"""EpiScene: guarded restart and actual post-restart work verification.
No customer playlists/markers/job statuses are written. Fail closed.
"""
import argparse,fcntl,json,os,sqlite3,subprocess,sys,time
from pathlib import Path
from urllib.request import urlopen

DB=Path('/var/lib/epimediahub/provisioning.db')
LOCK=Path('/var/lib/epimediahub/skip-analysis.lock')
MUTEX=Path('/var/lib/epimediahub/.episcene-verified-restart.lock')
RELOAD=Path('/var/lib/epimediahub/episcene-visual-peer-reload-pending')
TIMER='epimediahub-skip-analysis.timer'
BATCH='epimediahub-skip-analysis.service'
COMPUTE='epimediahub-analysis-worker.service'
WEB='epimediahub-provisioning.service'
LANES=(8,10)
GOOD={'done','review','no_match','no_reference','partial'}

def cmd(*args):
    r=subprocess.run(['systemctl',*args],capture_output=True,text=True,timeout=90)
    if r.returncode:raise RuntimeError('SYSTEMD_COMMAND_FAILED:'+' '.join(args))
    return r.stdout.strip()

def active(unit):
    state=cmd('show',unit,'--property=ActiveState','--value')
    if state in ('active','activating','reloading','deactivating'):return True
    if state in ('inactive','failed'):return False
    raise RuntimeError('UNKNOWN_UNIT_STATE:'+unit)

def ro():
    if DB.is_symlink() or not DB.is_file():raise RuntimeError('DATABASE_UNAVAILABLE')
    c=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
    return c

def diagnosis():
    """Read-only, PII-free inventory of the live DB schema and systemd states."""
    names=('skip_analysis_playlists','skip_presence','skip_jobs',
           'skip_assets','episcene_report_events')
    with ro() as c:
        existing={r['name'] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        result={}
        for name in names:
            if name not in existing:
                result[name]={'present':False}
                continue
            cols=[r['name'] for r in c.execute('PRAGMA table_info('+name+')')]
            info={'present':True,'columns':cols}
            if name=='skip_analysis_playlists' and 'id' in cols:
                # Only IDs and safe state flags, never playlist credentials or labels.
                fields=['id']+[v for v in
                    ('enabled','active','is_active','archived','paused','disabled')
                    if v in cols]
                rows=c.execute('SELECT '+','.join(fields)+
                    ' FROM skip_analysis_playlists WHERE id IN (?,?) ORDER BY id',
                    LANES).fetchall()
                info['lane_flags']=[{k:r[k] for k in fields} for r in rows]
            result[name]=info
    services={}
    for unit in (TIMER,BATCH,COMPUTE,WEB):
        try:services[unit]=cmd('show',unit,'--property=ActiveState','--value')
        except (OSError,RuntimeError,subprocess.SubprocessError):
            services[unit]='UNAVAILABLE'
    print('DIAGNOSTIC '+json.dumps({'tables':result,'units':services},
                                   sort_keys=True),flush=True)
    return 0

def snap(c):
    tables={r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'episcene_report_events','skip_analysis_playlists','skip_presence','skip_jobs','skip_assets'}
    if not required<=tables:raise RuntimeError('DATABASE_SCHEMA_NOT_COMPATIBLE')
    columns={r['name'] for r in c.execute('PRAGMA table_info(episcene_report_events)')}
    if not {'id','kind','payload'}<=columns:raise RuntimeError('TELEMETRY_SCHEMA_NOT_COMPATIBLE')
    playlist_cols={r['name'] for r in c.execute('PRAGMA table_info(skip_analysis_playlists)')}
    if not {'id','enabled','archived','paused'}<=playlist_cols:
        raise RuntimeError('PLAYLIST_SCHEMA_UNSUPPORTED_RUN_DIAGNOSE')
    lanes=tuple(r['id'] for r in c.execute("""
      SELECT id FROM skip_analysis_playlists
      WHERE id IN (8,10) AND enabled=1 AND archived=0 AND paused=0 ORDER BY id"""))
    if lanes!=LANES:raise RuntimeError('ANALYSIS_LANES_NOT_BOTH_ENABLED')
    presence=c.execute('SELECT COUNT(*) n FROM skip_presence WHERE expires_at>?',
        (int(time.time()),)).fetchone()['n']
    waiting={}
    for pid in LANES:
        waiting[pid]=c.execute("""SELECT COUNT(*) n FROM skip_jobs j
          JOIN skip_assets a ON a.asset_key=j.asset_key
          WHERE a.playlist_id=? AND j.status IN ('queued','running','processing','in_progress')""",
          (pid,)).fetchone()['n']
    high=c.execute('SELECT COALESCE(MAX(id),0) FROM episcene_report_events').fetchone()[0]
    return {'event_id':high,'waiting':waiting,'presence':presence}

def progress(c,base):
    result={pid:dict(completions=0,successful_jobs=0,failed_jobs=0,running=0) for pid in LANES}
    heartbeat=0
    for r in c.execute("""SELECT kind,payload FROM episcene_report_events
        WHERE id>? AND kind IN ('heartbeat','job','analysis_completion')
        ORDER BY id""",(base['event_id'],)):
        try:p=json.loads(r['payload']) if isinstance(r['payload'],str) else r['payload']
        except (ValueError,TypeError):continue
        if not isinstance(p,dict):continue
        if r['kind']=='heartbeat':heartbeat+=1;continue
        if r['kind']=='analysis_completion':
            if p.get('playlist_id') in result:result[p['playlist_id']]['completions']+=1
            continue
        j=p.get('job');asset=p.get('asset')
        if not isinstance(j,dict) or not isinstance(asset,dict):continue
        pid=asset.get('playlist_id')
        if pid not in result:continue
        state=j.get('status')
        if state in GOOD:result[pid]['successful_jobs']+=1
        elif state=='failed':result[pid]['failed_jobs']+=1
        elif state=='running':result[pid]['running']+=1
    return result,heartbeat

def health(url):
    try:
        with urlopen(url,timeout=5) as r:return r.status==200
    except Exception:return False

def guarded_restart(base,drain=600):
    if os.geteuid()!=0:raise RuntimeError('ROOT_REQUIRED')
    if base['presence']:raise RuntimeError('PLAYBACK_ACTIVE')
    if RELOAD.exists():raise RuntimeError('EXISTING_SCENE_RELOAD_PENDING')
    if not active(TIMER):raise RuntimeError('ANALYSIS_TIMER_INACTIVE_REFUSE_AUTO_ENABLE')
    if LOCK.is_symlink() or not LOCK.is_file():raise RuntimeError('WORKER_LOCK_MISSING')
    if MUTEX.is_symlink():raise RuntimeError('UNSAFE_RESTART_MUTEX')
    with MUTEX.open('a') as mutex:
        try:fcntl.flock(mutex,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('CONCURRENT_RESTART')
        cmd('stop',TIMER)
        try:
            until=time.monotonic()+drain
            while active(BATCH):
                with ro() as c:
                    if snap(c)['presence']:raise RuntimeError('NEW_PLAYBACK_DURING_DRAIN')
                if time.monotonic()>until:raise RuntimeError('BATCH_DID_NOT_FINISH')
                time.sleep(5)
            with LOCK.open('rb') as worker:
                try:fcntl.flock(worker,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise RuntimeError('WORKER_LOCK_BUSY')
                if active(BATCH):raise RuntimeError('ANALYSIS_STARTED_DURING_DRAIN')
                with ro() as c:
                    if snap(c)['presence']:raise RuntimeError('NEW_PLAYBACK')
                for u in (COMPUTE,WEB):
                    cmd('restart',u)
                    if not active(u):raise RuntimeError('UNIT_NOT_ACTIVE:'+u)
                if not health('http://127.0.0.1:8790/health'):
                    raise RuntimeError('REMOTE_WORKER_HEALTH_FAILED')
                if not health('http://127.0.0.1:8787/health'):
                    raise RuntimeError('CONTROLLER_HEALTH_FAILED')
        finally:
            cmd('start',TIMER)
            if not active(TIMER):raise RuntimeError('TIMER_NOT_RESTORED')

def check(base,seconds=900,poll=15,kick=False):
    if kick and not base['presence'] and not active(BATCH):
        cmd('start','--no-block',BATCH)
    end=time.monotonic()+seconds
    while True:
        with ro() as c:
            current=snap(c)
            outcomes,heartbeats=progress(c,base)
        needed=[pid for pid in LANES if base['waiting'][pid]>0]
        verified=[pid for pid in needed if outcomes[pid]['completions'] and
                  outcomes[pid]['successful_jobs']]
        ok=(bool(needed) and heartbeats>0 and len(verified)==len(needed)
            and active(TIMER) and active(COMPUTE) and active(WEB))
        if ok or time.monotonic()>=end:
            return dict(status='PASS' if ok else 'FAIL_NO_CONFIRMED_PROGRESS',
              required_lanes=needed,verified_lanes=verified,
              heartbeat_events=heartbeats,new_events=outcomes,
              timer_active=active(TIMER),marker_changes=0)
        time.sleep(min(poll,max(0,end-time.monotonic())))

def run(args):
    with ro() as c:base=snap(c)
    print('BEFORE '+json.dumps(dict(waiting=base['waiting'],
      playback_leases=base['presence'],timer_active=active(TIMER)),sort_keys=True),flush=True)
    if args.restart:
        guarded_restart(base,drain=args.drain)
        print('RESTART_HEALTH_OK (timer restored)',flush=True)
    result=check(base,args.timeout,args.poll,args.kick)
    print('RESULT '+json.dumps(result,sort_keys=True),flush=True)
    return 0 if result['status']=='PASS' else 3

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--diagnose',action='store_true',help='read-only schema/service report')
    p.add_argument('--restart',action='store_true')
    p.add_argument('--kick',action='store_true')
    p.add_argument('--timeout',type=int,default=900)
    p.add_argument('--poll',type=int,default=15)
    p.add_argument('--drain',type=int,default=600)
    args=p.parse_args()
    if not (0<=args.timeout<=1800 and 1<=args.poll<=60 and 0<=args.drain<=1800):
        p.error('invalid time budget')
    if args.diagnose and (args.restart or args.kick):
        p.error('--diagnose cannot be combined with --restart or --kick')
    try:
        if args.diagnose:return diagnosis()
        return run(args)
    except (OSError,RuntimeError,sqlite3.Error,subprocess.SubprocessError) as e:
        print('BLOCKED '+str(e),flush=True)
        return 2

if __name__=='__main__':sys.exit(main())
