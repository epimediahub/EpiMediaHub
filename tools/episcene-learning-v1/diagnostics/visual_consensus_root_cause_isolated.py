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
