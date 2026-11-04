#!/usr/bin/env python3
"""Snapshot-only EpiScene audio-anchor shadow replay.

The original production gates run on a disposable SQLite copy in an OS
sandbox, then a strict proposed audio+human policy is counted. NEVER calls
accept_pending, approve_rows, review_record, downloads or worker restarts.
Prints aggregate categories only; no asset IDs, personal data, URLs or hashes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

# -I deliberately omits the script directory from sys.path. Load only the
# companion policy from the exact directory of this pinned downloaded script.
_POLICY_FILE = Path(__file__).resolve().with_name('audio_anchor_policy.py')
if not _POLICY_FILE.is_file() or _POLICY_FILE.is_symlink():
    raise RuntimeError('Shadow-Policy nicht vorhanden oder Symlink')
sys.path.insert(0, str(_POLICY_FILE.parent))
from audio_anchor_policy import Evidence, nominate, AUDIO_SOURCES

sys.dont_write_bytecode = True
APP = Path('/opt/epimediahub/provisioning')
DB = Path('/var/lib/epimediahub/provisioning.db')
PYTHON = APP / '.venv/bin/python'
MAX_ROWS = 15000
ALLOWED = ('audio', 'audio_repetition', 'auto_audio', 'episcene', 'device')

SQL = """
SELECT r.*,a.playlist_id,a.source_key asset_source_key,
       a.season asset_season,a.episode asset_episode,
       a.media_type asset_media_type,a.duration_ms asset_duration_ms,
       e.evidence_json,COALESCE(e.human_review,0) human_review,
       d.customer_id device_customer_id,d.enabled device_enabled,
       c.enabled customer_enabled
FROM skip_records r
JOIN skip_assets a ON a.asset_key=r.asset_key
LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
LEFT JOIN devices d ON d.id=r.device_id
LEFT JOIN customers c ON c.id=d.customer_id
WHERE a.playlist_id IN (8,10)
  AND r.segment_type IN ('intro','outro')
  AND r.source IN ('audio','audio_repetition','auto_audio','episcene','device')
  AND r.status IN ('pending','approved','rejected')
ORDER BY a.playlist_id,r.source_key,r.season,r.segment_type,r.id
"""


def isolated_launch() -> None:
    if not shutil.which('systemd-run'):
        raise SystemExit('ABBRUCH: Isolierung systemd-run nicht vorhanden.')
    for path in (DB, APP/'skip_release.py', APP/'skip_automation.py', APP/'skip_scene.py'):
        if not path.is_file() or path.is_symlink():
            raise SystemExit('ABBRUCH: benötigte Quelldatei fehlt oder ist Symlink.')
    if (not PYTHON.is_file() or not os.access(PYTHON, os.X_OK)
            or not (APP/'.venv/pyvenv.cfg').is_file()):
        raise SystemExit('ABBRUCH: Provisioning-Venv nicht vorhanden.')
    with tempfile.TemporaryDirectory(prefix='episcene_audio_shadow_',dir='/tmp') as dir_:
        snapshot = Path(dir_)/'snapshot.db'
        src = sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=60)
        dst = None
        try:
            src.execute('PRAGMA query_only=ON')
            dst = sqlite3.connect(snapshot,timeout=60)
            src.backup(dst,pages=2048,sleep=0.1)
        finally:
            src.close()
            if dst is not None:
                dst.close()
        os.chmod(snapshot,0o600)
        props = (
            'PrivateNetwork=yes','ProtectSystem=strict','ReadWritePaths=/tmp',
            'ProtectHome=yes','NoNewPrivileges=yes','CapabilityBoundingSet=',
            'PrivateDevices=yes','ProtectKernelTunables=yes',
            'ProtectKernelModules=yes','ProtectControlGroups=yes',
            'RestrictAddressFamilies=AF_UNIX','TemporaryFileSystem=/run',
            'PrivateTmp=no','MemoryMax=1G','CPUQuota=100%',
            'RuntimeMaxSec=180s',
        )
        cmd = ['systemd-run','--pipe','--wait','--collect']
        for prop in props:
            cmd += ['-p',prop]
        cmd += [
            '--setenv=EPISCENE_AUDIO_SHADOW=YES',
            '--setenv=EPISCENE_AUDIO_SHADOW_SNAPSHOT='+str(snapshot),
            str(PYTHON),'-I','-B',str(Path(__file__).resolve()),
        ]
        print('EpiScene Audio-Freigabe SHADOW auf DB-Kopie; keine Freigaben.',flush=True)
        code = subprocess.run(cmd,check=False).returncode
        if code:
            raise SystemExit(f'ABBRUCH: sandbox replay exit={code}')


def as_json(value) -> dict:
    try:
        parsed = json.loads(value or '{}')
        return parsed if isinstance(parsed,dict) else {}
    except (ValueError,TypeError):
        return {}


def schemas_ok(con) -> bool:
    required = {
        'skip_assets':{'asset_key','playlist_id','source_key','season','episode','media_type','duration_ms'},
        'skip_records':{'asset_key','source_key','season','episode','media_type','duration_ms','segment_type',
                        'source','status','start_ms','end_ms','disabled','device_id','customer_id'},
        'skip_auto_evidence':{'record_id','evidence_json','human_review'},
        'skip_auto_blocks':{'asset_key','kind','duration_ms'},
        'devices':{'id','customer_id','enabled'},
        'customers':{'id','enabled'},
    }
    for table,fields in required.items():
        cols={x[1] for x in con.execute('PRAGMA table_info('+table+')')}
        if not fields<=cols:
            return False
    return True


def mapped(row) -> bool:
    return (
        row['source_key']==row['asset_source_key']
        and row['season']==row['asset_season']
        and row['episode']==row['asset_episode']
        and row['media_type']==row['asset_media_type']
        and row['asset_duration_ms'] is not None
        and type(row['duration_ms']) is int
        and abs(row['asset_duration_ms']-row['duration_ms']) <= 500
    )


def evidence(row) -> Evidence:
    ev = as_json(row['evidence_json'])
    decision=ev.get('decision')
    status = decision.get('status','') if isinstance(decision,dict) else ''
    human_verified = (
        row['source']=='device' and row['status']=='approved'
        and row['disabled']==0 and mapped(row)
        and row['device_id'] is not None
        and row['customer_id'] is not None
        and row['device_customer_id']==row['customer_id']
        and row['device_enabled']==1 and row['customer_enabled']==1
    )
    audio_confirmed = (
        row['source'] in AUDIO_SOURCES
        and row['human_review']==0
        and ev.get('episcene_required') is True
        and ev.get('status')=='AUTO_CONFIRMED'
        and ev.get('method')!='episcene_consensus'
        and ev.get('audio_visual_disagreement') is not True
    )
    return Evidence(
        asset_key=str(row['asset_key'] or ''),
        playlist_id=row['playlist_id'],
        source_key=str(row['source_key'] or ''),
        season=row['season'],episode=row['episode'],
        media_type=row['media_type'],kind=row['segment_type'],
        source=row['source'],state=row['status'],
        start_ms=row['start_ms'],end_ms=row['end_ms'],
        duration_ms=row['duration_ms'],
        disabled=bool(row['disabled']),
        audio_confirmed=audio_confirmed,
        human_verified=human_verified,
        visual_disagreement=(ev.get('audio_visual_disagreement') is True),
        visual_decision=str(status),
    )


def replay():
    raw = os.environ.get('EPISCENE_AUDIO_SHADOW_SNAPSHOT','')
    snapshot = Path(raw)
    if not raw.startswith('/tmp/') or not snapshot.is_file() or snapshot.is_symlink():
        raise RuntimeError('Snapshot unverfügbar')
    source = sqlite3.connect(snapshot.resolve().as_uri()+'?mode=ro',uri=True,timeout=60)
    with tempfile.TemporaryDirectory(prefix='episcene_audio_shadow_test_') as dir_:
        con = sqlite3.connect(str(Path(dir_)/'sandbox.db'),timeout=60)
        try:
            source.backup(con)
        finally:
            source.close()
        try:
            con.row_factory=sqlite3.Row
            if not schemas_ok(con):
                raise RuntimeError('Schema abweichend, sichere Abbruchbedingung')
            os.chdir(APP.resolve())
            sys.path.insert(0,str(APP.resolve()))
            import skip_automation  # noqa: F401: install same original patch layer
            import skip_release as release
            if Path(release.__file__).resolve().parent != APP.resolve():
                raise RuntimeError('Unbekanntes release Modul')
            for f in ('enabled','scene_release_ready','current_reference',
                      'reviewed_release_ready','detector_release_ready'):
                if not callable(getattr(release,f,None)):
                    raise RuntimeError('Original gate fehlt')
            rows=con.execute(SQL).fetchall()
            if len(rows)>MAX_ROWS:
                raise RuntimeError('Zu viele Daten für sicheren Test')
            grouped=defaultdict(list)
            for row in rows:
                if mapped(row):
                    grouped[(row['playlist_id'],row['source_key'],row['season'],
                             row['segment_type'])].append((row,evidence(row)))
            counts=Counter()
            per_playlist=Counter()
            for key, members in grouped.items():
                for row, marker in members:
                    if row['source'] not in AUDIO_SOURCES or row['status']!='pending':
                        continue
                    if not marker.audio_confirmed:
                        continue
                    counts['audio_confirmed_pending']+=1
                    if marker.visual_disagreement:
                        counts['contradicting_visual']+=1
                        continue
                    # Original gates run against disposable DB only. Revert
                    # any DB changes even if future modules become write-capable.
                    con.execute('SAVEPOINT original_release_gates')
                    failed=[]
                    try:
                        for name,fn,args in (
                            ('enabled',release.enabled,(con,row['playlist_id'])),
                            ('visual',release.scene_release_ready,(con,row)),
                            ('reference',release.current_reference,(con,row)),
                            ('audio',release.reviewed_release_ready,(row,)),
                            ('detector',release.detector_release_ready,(con,row)),
                        ):
                            try:
                                if not bool(fn(*args)):
                                    failed.append(name)
                            except Exception:
                                failed.append(name+'_error')
                    finally:
                        con.execute('ROLLBACK TO original_release_gates')
                        con.execute('RELEASE original_release_gates')
                    if failed!=['visual']:
                        counts['not_visual_only_gate']+=1
                        continue
                    counts['original_visual_only_gate']+=1
                    blocked=bool(con.execute("""SELECT 1 FROM skip_auto_blocks
                        WHERE asset_key=? AND kind=? AND ABS(duration_ms-?)<=2000 LIMIT 1""",
                        (row['asset_key'],row['segment_type'],row['duration_ms'])).fetchone())
                    blocked |= bool(con.execute("""SELECT 1 FROM skip_records
                        WHERE asset_key=? AND segment_type=?
                          AND status IN ('approved','rejected')
                          AND ABS(duration_ms-?)<=2000 LIMIT 1""",
                        (row['asset_key'],row['segment_type'],row['duration_ms'])).fetchone())
                    pending_manual=bool(con.execute("""SELECT 1 FROM skip_records r
                        LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
                        WHERE r.asset_key=? AND r.segment_type=? AND r.status='pending'
                          AND (r.source='device' OR COALESCE(e.human_review,0)=1)
                          AND ABS(r.duration_ms-?)<=2000 LIMIT 1""",
                        (row['asset_key'],row['segment_type'],row['duration_ms'])).fetchone())
                    related=[p for r,p in members if r['id']!=row['id']]
                    reason=nominate(
                        marker,related,blocked=blocked,
                        owner_correction_pending=pending_manual,
                        source_version_current=True, # Proven original current_reference() gate above
                    )
                    counts[reason]+=1
                    per_playlist[(row['playlist_id'],reason)]+=1
            print('EPISCENE AUDIO+MANUAL SHADOW-REPLAY (KEINE AUTOMATISCHE FREIGABE)')
            print('Prüfbedingungen: 3 unabhängige Audiofolgen, 1 geprüfte manuelle Folge, <=1,5s Grenzabweichung.')
            for key,count in sorted(counts.items()):
                print(f'  {key}: {count}')
            for pid,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
                print(name+':')
                for (p,status),n in sorted(per_playlist.items()):
                    if p==pid:print(f'  {status}: {n}')
            print('Auch SHADOW_ELIGIBLE ist keine Freigabeentscheidung.')
            print('Snapshot wird gelöscht; keine Änderungen am Live-Betrieb.')
        finally:
            con.close()


if __name__=='__main__':
    if os.environ.get('EPISCENE_AUDIO_SHADOW')=='YES':
        replay()
    else:
        isolated_launch()
