#!/usr/bin/env python3
"""Diagnostic replay of EpiScene's real release gates on a disposable SQLite copy.
No accept_pending, approve_rows, downloads or worker restarts.
Run as root: python3 /tmp/episcene_replay.py (self-launches an isolated systemd service).
Fails closed if OS sandbox cannot start. No production-module imports outside sandbox.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
DB = Path('/var/lib/epimediahub/provisioning.db')
APP = Path('/opt/epimediahub/provisioning')
VENV_PYTHON = APP / '.venv/bin/python'
COMPUTE = Path('/opt/epimediahub/analysis')
MAX_LOCAL_DETECT_PER_SOURCE = 3
SQL = """SELECT r.*,COALESCE(e.human_review,0) human_review,
       e.evidence_json,a.playlist_id
FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
WHERE r.status='pending' AND a.playlist_id IN (8,10)
AND r.source IN ('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene')
AND COALESCE(e.human_review,0)=0 AND a.source_key=r.source_key
AND a.media_type=r.media_type AND a.season=r.season
AND a.episode=r.episode AND a.duration_ms>0
AND ABS(a.duration_ms-r.duration_ms)<=2000"""

def isolated_launch():
    if not shutil.which('systemd-run'):
        raise SystemExit('ABBRUCH: systemd-run fehlt; keine unsandboxierten Importe.')
    if not DB.is_file() or DB.is_symlink():
        raise SystemExit('ABBRUCH: Originaldatenbank fehlt oder ist ein Symlink.')
    if not VENV_PYTHON.is_file() or not os.access(VENV_PYTHON, os.X_OK):
        raise SystemExit('ABBRUCH: EpiScene Python-Venv nicht gefunden: '+str(VENV_PYTHON))
    props = [
        'PrivateNetwork=yes', 'ProtectSystem=strict', 'ReadWritePaths=/tmp',
        'RuntimeMaxSec=90', 'MemoryMax=1500M',
        'ProtectHome=yes', 'NoNewPrivileges=yes', 'CapabilityBoundingSet=',
        'PrivateDevices=yes', 'ProtectKernelTunables=yes',
        'ProtectKernelModules=yes', 'ProtectControlGroups=yes',
        'RestrictAddressFamilies=AF_UNIX', 'TemporaryFileSystem=/run',
        'PrivateTmp=no'
    ]
    # Take a consistent, transactional SQLite backup BEFORE entering the
    # sandbox. The sandbox must never access the production DB directly.
    with tempfile.TemporaryDirectory(prefix='episcene_snapshot_', dir='/tmp') as dirname:
        snapshot = Path(dirname) / 'snapshot.db'
        src = sqlite3.connect(DB.resolve().as_uri() + '?mode=ro', uri=True, timeout=60)
        dst = None
        try:
            src.execute('PRAGMA query_only=ON')
            dst = sqlite3.connect(str(snapshot), timeout=60)
            src.backup(dst, pages=2048, sleep=0.1)
        finally:
            src.close()
            if dst is not None:
                dst.close()
        os.chmod(snapshot, 0o600)
        cmd = ['systemd-run', '--pipe', '--wait', '--collect']
        for prop in props:
            cmd.extend(['-p', prop])
        cmd.extend([
            '--setenv=EPISCENE_REPLAY_SANDBOX=YES',
            '--setenv=EPISCENE_REPLAY_SNAPSHOT=' + str(snapshot),
            str(VENV_PYTHON), '-I', '-B', str(Path(__file__).resolve())
        ])
        print('Datenbank-Snapshot erstellt; starte isolierten Freigabe-Test ...', flush=True)
        rc = subprocess.run(cmd, check=False).returncode
        if rc:
            raise SystemExit('Sandbox oder Replay fehlgeschlagen; keine Freigaben: exit '+str(rc))


def parsed(v):
    try:
        out=json.loads(v or '{}')
        return out if isinstance(out,dict) else {}
    except (ValueError,TypeError):
        return {}

def gates(R, con, row):
    failed=[]; errors=[]
    if row['media_type']=='episode' and (type(row['duration_ms']) is not int or row['duration_ms']<300000):
        failed.append('short_episode')
    tasks=(
        ('source_disabled',R.enabled,(con,row['playlist_id'])),
        ('visual_evidence',R.scene_release_ready,(con,row)),
        ('stale_reference',R.current_reference,(con,row)),
        ('audio_boundaries',R.reviewed_release_ready,(row,)),
        ('detector_evidence',R.detector_release_ready,(con,row)),
    )
    for name,fn,args in tasks:
        try:
            if not bool(fn(*args)): failed.append(name)
        except Exception as ex:
            failed.append(name); errors.append(name+':'+type(ex).__name__)
    return failed,errors


VISUAL_VERSION_FIELDS=('asset_key','source_key','playlist_id','stream_id','extension',
    'duration_ms','season','episode','updated_at','content_version','etag')

def visual_version(asset):
    return hashlib.sha256(json.dumps(
        {key:asset[key] if key in asset.keys() else None for key in VISUAL_VERSION_FIELDS},
        sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def visual_profile(con,row,has_versions):
    """Classify failed visual gate by existing cache coverage only."""
    asset=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',
                      (row['asset_key'],)).fetchone()
    if asset is None:return 'NO_ASSET'
    own=con.execute("""SELECT w.id,w.duration_ms
        FROM skip_scene_windows w WHERE w.asset_key=? AND w.kind=?""",
        (row['asset_key'],row['segment_type'])).fetchall()
    if not own:return 'NO_OWN_VISUAL_WINDOW'
    duration=[w for w in own if w['duration_ms']==asset['duration_ms']]
    if not duration:return 'OWN_WINDOW_DURATION_MISMATCH'
    if not has_versions:return 'OWN_WINDOW_REVISION_UNVERIFIED'
    ver=visual_version(asset)
    valid=con.execute("""SELECT 1 FROM skip_scene_windows w
      JOIN skip_scene_window_versions v ON v.window_id=w.id
      WHERE w.asset_key=? AND w.kind=? AND w.duration_ms=? AND v.version=?
      LIMIT 1""",(row['asset_key'],row['segment_type'],asset['duration_ms'],ver)).fetchone()
    if not valid:return 'OWN_WINDOW_REVISION_MISMATCH'
    if asset['source_key'] is None or asset['season'] is None or asset['episode'] is None:
        return 'OWN_WINDOW_VALID_BUT_FAMILY_UNKNOWN'
    peers=con.execute("""SELECT DISTINCT a.episode
      FROM skip_scene_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
      WHERE a.playlist_id=? AND a.source_key=? AND a.season=?
        AND a.episode<>? AND w.kind=? AND w.duration_ms=a.duration_ms""",
        (asset['playlist_id'],asset['source_key'],asset['season'],
         asset['episode'],row['segment_type'])).fetchall()
    if len(peers)<2:return 'OWN_WINDOW_VALID_BUT_FEWER_THAN_2_PEERS'
    return 'OWN_WINDOW_AND_2PLUS_PEERS_CONSENSUS_STILL_MISSING'



def consensus_link_profile(con, row):
    """Read-only classify same-asset/kind scene consensus proposals and boundaries."""
    linked=con.execute("""SELECT r.status,r.start_ms,r.end_ms,e.evidence_json
       FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
       WHERE r.asset_key=? AND r.segment_type=? AND r.id<>?
       LIMIT 200""",(row['asset_key'],row['segment_type'],row['id'])).fetchall()
    matches=[]
    for other in linked:
        ev=parsed(other['evidence_json'])
        if ev.get('method')!='episcene_consensus':
            continue
        exact=(other['start_ms']==row['start_ms'] and other['end_ms']==row['end_ms'])
        near=(type(other['start_ms']) is int and type(other['end_ms']) is int
              and type(row['start_ms']) is int and type(row['end_ms']) is int
              and abs(other['start_ms']-row['start_ms'])<=2000
              and abs(other['end_ms']-row['end_ms'])<=2000)
        decision=ev.get('decision')
        state=str(decision.get('status','missing') if isinstance(decision,dict) else 'missing')
        key=('EXACT' if exact else 'NEAR_2S' if near else 'BOUNDARIES_DIFFER',
             str(other['status'])[:18],state[:22])
        matches.append(key)
    if not matches:
        return 'NO_SAME_ASSET_SCENE_CONSENSUS', 'NONE'
    first=next((x for x in matches if x[0]=='EXACT'), None)
    if first is None:
        first=next((x for x in matches if x[0]=='NEAR_2S'),matches[0])
    return first[0], 'record_'+first[1]+'_decision_'+first[2]



def more_visual_evidence(con,row):
    """Metadata-only root-cause indicators. Never treats matches as approval."""
    asset=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',
                      (row['asset_key'],)).fetchone()
    if asset is None:return 'NO_ASSET', 'NOT_APPLICABLE', 'NOT_APPLICABLE', 'NO_ASSET'
    peer_rows=con.execute("""SELECT a.*,v.version AS saved_version
        FROM skip_assets a
        JOIN skip_scene_windows w ON w.asset_key=a.asset_key
        LEFT JOIN skip_scene_window_versions v ON v.window_id=w.id
        WHERE a.playlist_id=? AND a.source_key=? AND a.season=?
          AND a.episode<>? AND w.kind=? AND w.duration_ms=a.duration_ms""",
        (asset['playlist_id'],asset['source_key'],asset['season'],
         asset['episode'],row['segment_type'])).fetchall()
    peer_all=set()
    peer_current=set()
    for p in peer_rows:
        if p['episode'] is None:
            continue
        peer_all.add(p['episode'])
        if p['saved_version']==visual_version(p):
            peer_current.add(p['episode'])
    if len(peer_current)>=2:
        peer_state='TWO_PLUS_VERSION_VALID_PEERS'
    elif len(peer_all)>=2:
        peer_state='PEERS_EXIST_BUT_FEWER_THAN_TWO_VERSION_VALID'
    else:
        peer_state='FEWER_THAN_TWO_STORED_PEERS'
    other=con.execute("""SELECT r.start_ms,r.end_ms,r.status,e.evidence_json
          FROM skip_records r
          LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
          WHERE r.asset_key=? AND r.segment_type=? AND r.id<>?
          LIMIT 250""",(row['asset_key'],row['segment_type'],row['id'])).fetchall()
    candidates=[]
    for r in other:
        ev=parsed(r['evidence_json'])
        if ev.get('method')!='episcene_consensus':
            continue
        if any(type(value) is not int for value in
               (r['start_ms'],r['end_ms'],row['start_ms'],row['end_ms'])):
            continue
        ds=r['start_ms']-row['start_ms']
        de=r['end_ms']-row['end_ms']
        decision=ev.get('decision') if isinstance(ev.get('decision'),dict) else {}
        candidates.append((max(abs(ds),abs(de)),abs(ds)+abs(de),ds,de,
                           str(r['status'])[:18],str(decision.get('status','missing'))[:20],
                           str(decision.get('reason','unspecified'))[:40]))
    if not candidates:
        return peer_state,'NO_SAME_ASSET_CONSENSUS', 'NO_CONSENSUS_DECISION','NO_CONSENSUS_REASON'
    best=min(candidates,key=lambda v:(v[0],v[1]))
    difference=best[0]
    if difference<=2000:boundary='MATCH_WITHIN_2_SECONDS'
    elif difference<=5000:boundary='OFFSET_2_TO_5_SECONDS'
    elif difference<=15000:boundary='OFFSET_5_TO_15_SECONDS'
    elif difference<=60000:boundary='OFFSET_15_TO_60_SECONDS'
    else:boundary='OFFSET_OVER_60_SECONDS'
    return peer_state,boundary,'record_'+best[4]+'_decision_'+best[5],best[6]



def selected_peer_profile(con, scene, row):
    """Read actual cached-window rows and resolve their parent assets, as analyze() does.

    The production _cached_rows() returns individual sqlite3.Row cache records,
    NOT (window, parent) pairs. analyze() builds those pairs after resolving
    skip_assets. Only aggregate counts leave the isolated environment.
    """
    asset=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',(row['asset_key'],)).fetchone()
    if asset is None:
        return 'ASSET_MISSING'
    selection=scene._cached_rows(con,asset,row['segment_type'])
    if selection is None:
        return 'SELECTOR_RESULT_UNKNOWN'
    try:
        entries=iter(selection)
    except TypeError:
        return 'SELECTOR_RESULT_UNKNOWN'
    distinct=set()
    own_seen=False
    window_count=0
    for entry in entries:
        window_count+=1
        if window_count>10000:
            return 'SELECTOR_UNEXPECTED_SIZE'
        if not hasattr(entry,'keys') or 'asset_key' not in entry.keys():
            return 'SELECTOR_UNEXPECTED_CACHE_ROW'
        cache_key=entry['asset_key']
        if not isinstance(cache_key,str) or not cache_key:
            return 'SELECTOR_EMPTY_CACHE_ASSET_KEY'
        parent=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',
                           (cache_key,)).fetchone()
        if parent is None:
            return 'SELECTOR_PARENT_ASSET_MISSING'
        if parent['source_key']!=asset['source_key'] or parent['season']!=asset['season']:
            return 'SELECTOR_CROSS_SERIES_OR_SEASON'
        if parent['asset_key']==asset['asset_key'] or parent['episode']==asset['episode']:
            # Production _compare() filters these out. Counting them as a
            # fatal selection error hid any valid peers after the own row.
            own_seen=True
            continue
        if parent['episode'] is None:
            return 'SELECTOR_PEER_EPISODE_MISSING'
        distinct.add((parent['season'],parent['episode']))
    # These counts are selected cache peers only, NOT validated frame matches.
    prefix='SELECTOR_WITH_SELF_' if own_seen else 'SELECTOR_WITHOUT_SELF_'
    if len(distinct)==0:return prefix+'NO_PEERS'
    if len(distinct)==1:return prefix+'ONE_PEER'
    if len(distinct)==2:return prefix+'TWO_PEERS'
    if len(distinct)==3:return prefix+'THREE_PEERS'
    return prefix+'FOUR_PLUS_PEERS'


def offline_detect_from_cache(con,Scene,visual,row):
    """Call pure local visual detector over saved cache data; no media requests."""
    asset=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',
                      (row['asset_key'],)).fetchone()
    if not asset:
        return 'ASSET_MISSING'
    kind=row['segment_type']
    own=con.execute("""SELECT * FROM skip_scene_windows
       WHERE asset_key=? AND kind=? AND duration_ms=?
       ORDER BY created_at DESC LIMIT 1""",
       (row['asset_key'],kind,asset['duration_ms'])).fetchone()
    if own is None:
        return 'OWN_WINDOW_MISSING'
    entries=Scene._cached_rows(con,asset,kind)
    if entries is None:return 'SELECTOR_NONE'
    partners=[]
    used={asset['episode']}
    for cache_row in entries:
        peer=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',
                         (cache_row['asset_key'],)).fetchone()
        if peer is None:continue
        if peer['source_key']!=asset['source_key'] or peer['season']!=asset['season']:
            continue
        if peer['episode'] in used or peer['asset_key']==asset['asset_key']:
            continue
        trusted=Scene._human_markers(con,peer,kind)
        partners.append(Scene._window(cache_row,peer,trusted))
        used.add(peer['episode'])
        if len(partners)==4:break
    if not partners:return 'NO_PEERS'
    own_window=Scene._window(own,asset)
    output=visual.detect(own_window,partners,kind,busy=lambda:False,cache=None)
    if not isinstance(output,dict):return 'INVALID_RESULT'
    state=output.get('status')
    if state not in ('NO_MATCH','REVIEW','AUTO_CONFIRMED'):
        return 'INVALID_STATUS'
    # Never promote any result: a valid standalone offline detection must
    # still pass original live gates, including audio boundary agreement.
    if state=='AUTO_CONFIRMED':
        difference=max(abs(output['start_ms']-row['start_ms']),
                       abs(output['end_ms']-row['end_ms']))
        if difference<=2000:return 'LOCAL_AUTO_CONFIRMED_ALIGNED_NOT_RELEASED'
        return 'LOCAL_AUTO_CONFIRMED_BOUNDARIES_DIFFER_NOT_RELEASED'
    if state=='REVIEW':
        return ('LOCAL_REVIEW_AMBIGUOUS' if output.get('ambiguous') else
                'LOCAL_REVIEW_UNCONFIRMED')
    return 'LOCAL_NO_MATCH'


def replay():
    raw_snapshot = os.environ.get('EPISCENE_REPLAY_SNAPSHOT', '')
    snapshot = Path(raw_snapshot)
    if not raw_snapshot.startswith('/tmp/'):
        raise SystemExit('ABBRUCH: unerwarteter Snapshot-Pfad')
    for f in (snapshot,APP/'skip_release.py',APP/'skip_automation.py',APP/'skip_scene.py'):
        if not f.is_file() or f.is_symlink():
            raise SystemExit('ABBRUCH: benötigte Datei fehlt oder Symlink: '+str(f))
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()[:12]
            for p in (APP/'skip_release.py',APP/'skip_automation.py',APP/'skip_scene.py')}
    temp=tempfile.mkdtemp(prefix='episcene_replay_')
    try:
        source=sqlite3.connect(snapshot.resolve().as_uri()+'?mode=ro',uri=True,timeout=60)
        target=sqlite3.connect(str(Path(temp)/'snapshot.db'),timeout=60)
        try:
            source.execute('PRAGMA query_only=ON')
            source.backup(target)
        finally:
            source.close()
        try:
            target.row_factory=sqlite3.Row
            os.chdir(APP.resolve())
            sys.path.insert(0,str(APP.resolve()))
            import skip_automation  # same patch layer as production, ONLY in OS sandbox
            import skip_release as R
            import skip_scene as Scene
            if not COMPUTE.is_dir() or COMPUTE.is_symlink():
                raise RuntimeError('Private local compute source unavailable')
            sys.path.insert(0,str(COMPUTE.resolve()))
            import skip_visual as Visual
            if Path(Visual.__file__).resolve()!=COMPUTE.resolve()/'skip_visual.py':
                raise RuntimeError('Unexpected visual module location')
            if getattr(Visual,'POLICY',None)!='episcene_visual_v1':
                raise RuntimeError('Unexpected local visual policy')
            if not callable(getattr(Visual,'detect',None)):
                raise RuntimeError('Local visual detect function missing')
            if Path(Scene.__file__).resolve().parent != APP.resolve():
                raise RuntimeError('Unexpected skip_scene module location')
            if not callable(getattr(Scene,'_cached_rows',None)):
                raise RuntimeError('Real _cached_rows selector unavailable')
            if Path(R.__file__).resolve().parent != APP.resolve():
                raise RuntimeError('Wrong skip_release module loaded')
            for fn in ('enabled','scene_release_ready','current_reference',
                       'reviewed_release_ready','detector_release_ready'):
                if not callable(getattr(R,fn,None)):
                    raise RuntimeError('Expected release gate absent: '+fn)
            allrows=target.execute(SQL).fetchall()
            selected=[]
            for row in allrows:
                ev=parsed(row['evidence_json'])
                if (ev.get('episcene_required') is True
                    and ev.get('method')!='episcene_consensus'
                    and ev.get('status')=='AUTO_CONFIRMED'):
                    selected.append(row)
            if len(selected)>3000:
                raise RuntimeError('Too many candidates; refusing incomplete audit')
            counts=collections.Counter()
            patterns=collections.Counter()
            issues=collections.Counter()
            segments=collections.Counter()
            visual_only_reasons=collections.Counter()
            visual_only_by_segment=collections.Counter()
            consensus_evidence=collections.Counter()
            visual_consensus_links=collections.Counter()
            visual_consensus_status=collections.Counter()
            root_peer_revisions=collections.Counter()
            root_boundary_gaps=collections.Counter()
            root_consensus_status=collections.Counter()
            root_decision_reasons=collections.Counter()
            selector_reasons=collections.Counter()
            no_scene_selector_reasons=collections.Counter()
            offline_detect_reasons=collections.Counter()
            offline_detect_samples=collections.Counter()
            has_visual_versions=bool(target.execute("""SELECT 1 FROM sqlite_master
                 WHERE type='table' AND name='skip_scene_window_versions'""").fetchone())
            for row in allrows:
                ev=parsed(row['evidence_json'])
                if ev.get('method')=='episcene_consensus':
                    decision=ev.get('decision')
                    status=decision.get('status','missing') if isinstance(decision,dict) else 'missing'
                    consensus_evidence[(row['playlist_id'],str(status)[:25])]+=1
            for row in selected:
                target.execute('SAVEPOINT safe_eval')
                try:
                    failed,errors=gates(R,target,row)
                finally:
                    try:
                        target.execute('ROLLBACK TO safe_eval')
                        target.execute('RELEASE safe_eval')
                    except sqlite3.Error as err:
                        raise RuntimeError('Gate changed transaction state; aborted') from err
                p=row['playlist_id']
                counts[(p,'candidates')]+=1
                segments[(p,row['segment_type'])]+=1
                for g in failed: issues[(p,g)]+=1
                if errors: counts[(p,'errors')]+=1
                if failed==['visual_evidence']:
                    counts[(p,'visual_only')]+=1
                    visual_only_reasons[(p,visual_profile(target,row,has_visual_versions))]+=1
                    visual_only_by_segment[(p,row['segment_type'])]+=1
                    link,detail=consensus_link_profile(target,row)
                    visual_consensus_links[(p,link)]+=1
                    visual_consensus_status[(p,link,detail)]+=1
                    peer_state,gap,decision,reason=more_visual_evidence(target,row)
                    try:
                        selected_reason=selected_peer_profile(target,Scene,row)
                    except (ValueError,TypeError,KeyError,sqlite3.Error,IndexError) as err:
                        selected_reason='SELECTOR_ERROR_'+type(err).__name__
                    selector_reasons[(p,selected_reason)]+=1
                    if link=='NO_SAME_ASSET_SCENE_CONSENSUS':
                        no_scene_selector_reasons[(p,selected_reason)]+=1
                        if offline_detect_samples[p]<MAX_LOCAL_DETECT_PER_SOURCE:
                            offline_detect_samples[p]+=1
                            # Snapshot is a disposable DB copy. Even if a
                            # future module starts writing it cannot affect
                            # real jobs, approvals, or the production DB.
                            target.execute('SAVEPOINT isolated_visual_detect')
                            try:
                                try:
                                    outcome=offline_detect_from_cache(target,Scene,Visual,row)
                                except (ValueError,TypeError,KeyError,IndexError,sqlite3.Error) as ex:
                                    outcome='LOCAL_TEST_ERROR_'+type(ex).__name__
                            finally:
                                target.execute('ROLLBACK TO isolated_visual_detect')
                                target.execute('RELEASE isolated_visual_detect')
                            offline_detect_reasons[(p,outcome)]+=1
                    root_peer_revisions[(p,peer_state)]+=1
                    root_boundary_gaps[(p,gap)]+=1
                    root_consensus_status[(p,decision)]+=1
                    # "reason" can contain internal free text in some versions,
                    # so export only a small explicit reason-code allowlist.
                    allowed={'no_peers','low_support','no_consensus','ambiguous',
                             'low_confidence','boundary_disagreement',
                             'no_visual_evidence','insufficient_evidence',
                             'no_match','missing','unspecified'}
                    safe_reason=reason if reason in allowed else 'OTHER_OR_FREEFORM'
                    root_decision_reasons[(p,safe_reason)]+=1
                if 'visual_evidence' in failed and len(failed)>1:counts[(p,'visual_and_other')]+=1
                if not failed:counts[(p,'no_gates_failed')]+=1
                patterns[(p, ' + '.join(failed) if failed else 'none')]+=1
            print('EPISCENE FULL-GATE-REPLAY AUF DATENBANKKOPIE')
            print('Module SHA256 (12 Stellen):',' '.join(k+'='+v for k,v in hashes.items()))
            print('Geprüfte Ausstehende:',len(allrows),'davon Audio AUTO_CONFIRMED:',len(selected))
            for p,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
                print('\\n'+name)
                for key in ('candidates','visual_only','visual_and_other','no_gates_failed','errors'):
                    print('  %-23s %d'%(key,counts[(p,key)]))
                print('  Segmenttypen:', ', '.join(k+'='+str(n) for (i,k),n in sorted(segments.items()) if i==p) or '-')
                print('  Einzelne blockierende Gates:')
                for (i,k),n in sorted(issues.items()):
                    if i==p:print('    %-25s %d'%(k,n))
                print('  Gate-Kombinationen:')
                for (i,k),n in patterns.most_common():
                    if i==p:print('    %-54s %d'%(k,n))
            print('\nVISUAL-ONLY GATE FAILURE BREAKDOWN (AUDIO AUTO_CONFIRMED)')
            print('Revision table present:',has_visual_versions)
            for p,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
                print('\n'+name)
                print('  visual_only_count:',counts[(p,'visual_only')])
                print('  by_segment_type:',
                    ', '.join(k+'='+str(n) for (pid,k),n in sorted(visual_only_by_segment.items())
                              if pid==p) or '-')
                print('  VISUAL-ONLY CACHE CATEGORIES:')
                for (pid,reason),n in sorted(visual_only_reasons.items()):
                    if pid==p:print('    '+reason+':',n)
                print('  SAME ASSET/KIND CONSENSUS LINKS FOR VISUAL-ONLY:')
                for (pid,link),n in sorted(visual_consensus_links.items()):
                    if pid==p:print('    '+link+':',n)
                print('  LINKED CONSENSUS RECORD STATUS AND DECISIONS:')
                for (pid,link,detail),n in sorted(visual_consensus_status.items()):
                    if pid==p:print('    '+link+' / '+detail+':',n)
                print('  ACTUAL _cached_rows SELECTOR RESULTS FOR VISUAL-ONLY:')
                for (pid,reason),n in sorted(selector_reasons.items()):
                    if pid==p:print('    '+reason+':',n)
                print('  ACTUAL SELECTOR WHEN NO SCENE PROPOSAL EXISTS:')
                for (pid,reason),n in sorted(no_scene_selector_reasons.items()):
                    if pid==p:print('    '+reason+':',n)
                print('  ISOLATED LOCAL VISUAL_DETECT, EXISTING CACHE ONLY:')
                print('    sampled:',offline_detect_samples[p])
                for (pid,reason),n in sorted(offline_detect_reasons.items()):
                    if pid==p:print('    '+reason+':',n)
                print('  PEER VISUAL WINDOW REVISION VALIDITY:')
                for (pid,state),n in sorted(root_peer_revisions.items()):
                    if pid==p:print('    '+state+':',n)
                print('  CLOSEST SAME-ASSET CONSENSUS BOUNDARY GAP:')
                for (pid,gap),n in sorted(root_boundary_gaps.items()):
                    if pid==p:print('    '+gap+':',n)
                print('  CLOSEST CONSENSUS DECISION:')
                for (pid,decision),n in sorted(root_consensus_status.items()):
                    if pid==p:print('    '+decision+':',n)
                print('  CONSENSUS DECISION REASON CODE (SAFE ALLOWLIST):')
                for (pid,reason),n in sorted(root_decision_reasons.items()):
                    if pid==p:print('    '+reason+':',n)
                print('  EXISTING EPISCENE_CONSENSUS PENDING EVIDENCE:')
                for (pid,status),n in sorted(consensus_evidence.items()):
                    if pid==p:print('    '+status+':',n)
            print('Same-asset proposals are not automatically accepted by the strict original record gate.')
            print('These visual-only candidates are NOT approved visual consensus.')
            print('Real cache selector rows resolved to parent assets; own rows are skipped for peer count.')
            print('Only up to 3 no-consensus cases per source run pure local visual_detect.')
            print('Results can differ from remote health/version; never publish offline findings.')
            print('No media fetching, remote calls, or approval from this diagnostic.')
            print('SELECTOR PEER COUNT DOES NOT PROVE VISUAL_DETECT MATCH OR APPROVAL.')
            print('PEER REVISION AND GAP RESULTS ARE METADATA ONLY; NOT A RELEASE VALIDATION.')
            print('Peer counts are only cache prerequisites; no release is asserted.')
            print('\\nKEINE Freigaben oder Downloads. Snapshot wird gelöscht.')
            print('Ergebnis ist keine Qualitätsgarantie und prüft keine nachgelagerte approve_rows-Logik.')
        finally:
            target.close()
    finally:
        shutil.rmtree(temp,ignore_errors=True)

if __name__=='__main__':
    if os.environ.get('EPISCENE_REPLAY_SANDBOX')=='YES':
        replay()
    else:
        isolated_launch()
