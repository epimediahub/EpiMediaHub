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
    props = [
        'PrivateNetwork=yes', 'ProtectSystem=strict', 'ReadWritePaths=/tmp',
        'ProtectHome=yes', 'NoNewPrivileges=yes', 'CapabilityBoundingSet=',
        'PrivateDevices=yes', 'ProtectKernelTunables=yes',
        'ProtectKernelModules=yes', 'ProtectControlGroups=yes',
        'RestrictAddressFamilies=AF_UNIX', 'TemporaryFileSystem=/run'
    ]
    cmd = ['systemd-run','--pipe','--wait','--collect']
    for prop in props:
        cmd.extend(['-p', prop])
    cmd.extend(['--setenv=EPISCENE_REPLAY_SANDBOX=YES',
                sys.executable, '-I', '-B', str(Path(__file__).resolve())])
    print('Starte nur-lesenden Replay mit Netzwerk- und Dateisystem-Sandbox...', flush=True)
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

def replay():
    for f in (DB,APP/'skip_release.py',APP/'skip_automation.py',APP/'skip_scene.py'):
        if not f.is_file() or f.is_symlink():
            raise SystemExit('ABBRUCH: benötigte Datei fehlt oder Symlink: '+str(f))
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()[:12]
            for p in (APP/'skip_release.py',APP/'skip_automation.py',APP/'skip_scene.py')}
    temp=tempfile.mkdtemp(prefix='episcene_replay_')
    try:
        source=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=60)
        target=sqlite3.connect(str(Path(temp)/'snapshot.db'),timeout=60)
        try:
            source.execute('PRAGMA query_only=ON')
            source.backup(target)
        finally:
            source.close()
        try:
            target.row_factory=sqlite3.Row
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
                if failed==['visual_evidence']:counts[(p,'visual_only')]+=1
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
