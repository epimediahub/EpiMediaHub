#!/usr/bin/env python3
"""EpiScene SAME-STAFFEL AUDIO FINGERPRINTS / SHADOW-ONLY, no releases.

Uses stored skip_auto_windows.words_json; no IPTV/media requests.
Original production gates run only on a transactional copy in systemd sandbox.
No DB writes in production, no approvals, no requeues, no worker restarts.
Only aggregate diagnostics, NEVER raw fingerprints or identifying IDs.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
if not (HERE / 'fingerprint_cohort_v2.py').is_file() or (HERE / 'fingerprint_cohort_v2.py').is_symlink():
    raise RuntimeError('Fingerprint matcher fehlt oder ist Symlink')
sys.path.insert(0,str(HERE))
from fingerprint_cohort_v2 import decode, match, near_record, inspect_cohort, Fingerprint

sys.dont_write_bytecode = True
APP=Path('/opt/epimediahub/provisioning')
DB=Path('/var/lib/epimediahub/provisioning.db')
PYTHON=APP/'.venv/bin/python'
MAX_ROWS=15000
MAX_TARGETS_PER_PLAYLIST_AND_KIND=6
MAX_PEERS_PER_TARGET=5
MAX_CROSS_SERIES_CONTROLS=2

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

AUDIO_SOURCES=('audio','audio_repetition','auto_audio','episcene')


def isolated_launch():
    if not shutil.which('systemd-run'):
        raise SystemExit('ABBRUCH: sandbox systemd-run fehlt')
    for path in (DB,APP/'skip_release.py',APP/'skip_automation.py',APP/'skip_scene.py'):
        if not path.is_file() or path.is_symlink():
            raise SystemExit('ABBRUCH: vertrauenswürdige Originaldatei fehlt')
    if not PYTHON.is_file() or not os.access(PYTHON,os.X_OK) or not (APP/'.venv/pyvenv.cfg').is_file():
        raise SystemExit('ABBRUCH: Provisioning-Venv nicht verfügbar')
    with tempfile.TemporaryDirectory(prefix='episcene_fp_shadow_',dir='/tmp') as d:
        snapshot=Path(d)/'snapshot.db'
        source=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=60)
        target=None
        try:
            source.execute('PRAGMA query_only=ON')
            target=sqlite3.connect(snapshot,timeout=60)
            source.backup(target,pages=2048,sleep=0.1)
        finally:
            source.close()
            if target is not None:target.close()
        os.chmod(snapshot,0o600)
        properties=(
            'PrivateNetwork=yes','ProtectSystem=strict','ReadWritePaths=/tmp',
            'ProtectHome=yes','NoNewPrivileges=yes','CapabilityBoundingSet=',
            'PrivateDevices=yes','ProtectKernelTunables=yes',
            'ProtectKernelModules=yes','ProtectControlGroups=yes',
            'RestrictAddressFamilies=AF_UNIX','TemporaryFileSystem=/run',
            'PrivateTmp=no','MemoryMax=1G','CPUQuota=100%',
            'RuntimeMaxSec=240s',
        )
        command=['systemd-run','--pipe','--wait','--collect']
        for prop in properties:
            command += ['-p',prop]
        command += [
            '--setenv=EPISCENE_FP_SHADOW=YES',
            '--setenv=EPISCENE_FP_SNAPSHOT='+str(snapshot),
            str(PYTHON),'-I','-B',str(Path(__file__).resolve())]
        print('Fingerprint-Staffelabgleich auf isolierter DB-Kopie. Keine Freigaben.',flush=True)
        status=subprocess.run(command,check=False).returncode
        if status:raise SystemExit(f'ABBRUCH: Sandbox-Fehler exit={status}')


def as_json(value):
    try:
        d=json.loads(value or '{}')
        return d if isinstance(d,dict) else {}
    except (TypeError, ValueError):return {}


def valid_asset(record):
    return (record['source_key']==record['asset_source_key']
            and record['season']==record['asset_season']
            and record['episode']==record['asset_episode']
            and record['media_type']=='episode'
            and record['asset_media_type']=='episode'
            and type(record['duration_ms']) is int
            and type(record['asset_duration_ms']) is int
            and record['asset_duration_ms']>=300_000
            and abs(record['duration_ms']-record['asset_duration_ms'])<=500)


def human_approved(record):
    return (record['source']=='device' and record['status']=='approved'
            and record['disabled']==0 and valid_asset(record)
            and record['device_id'] is not None
            and record['customer_id'] is not None
            and record['device_customer_id']==record['customer_id']
            and record['device_enabled']==1
            and record['customer_enabled']==1)


def audio_confirmed(record):
    ev=as_json(record['evidence_json'])
    return (record['source'] in AUDIO_SOURCES and record['status'] in ('pending','approved')
            and record['human_review']==0 and record['disabled']==0
            and valid_asset(record)
            and ev.get('episcene_required') is True
            and ev.get('status')=='AUTO_CONFIRMED'
            and ev.get('method')!='episcene_consensus'
            and ev.get('audio_visual_disagreement') is not True)


def schema(con):
    tables={
       'skip_auto_windows':{'asset_key','kind','words_json','offset_ms','length_ms','step_ms','duration_ms','created_at'},
       'skip_assets':{'asset_key','source_key','playlist_id','season','episode','duration_ms'},
       'skip_records':{'id','asset_key','source','status','source_key','media_type','season','episode','duration_ms','segment_type','disabled'},
       'skip_auto_evidence':{'record_id','evidence_json','human_review'},
       'skip_auto_blocks':{'asset_key','kind','duration_ms'},
       'devices':{'id','customer_id','enabled'},
       'customers':{'id','enabled'},
    }
    for table,expected in tables.items():
        actual={r[1] for r in con.execute('PRAGMA table_info('+table+')')}
        if not expected <= actual:
            raise RuntimeError('Schema fehlt oder abweichend: '+table)


# Error messages are fixed, controlled strings from fingerprint_cohort.decode.
# Classify only their *type*; never print raw words, source IDs or exceptions.
def fingerprint_error_code(error):
    reasons = {
        'bad fingerprint sampling step': 'STEP_UNSUPPORTED',
        'bad fingerprint offset': 'OFFSET_INVALID',
        'fingerprint payload too large / invalid': 'ENCODING_OR_SIZE_UNSUPPORTED',
        'invalid fingerprint json': 'NOT_VALID_JSON',
        'invalid fingerprint shape': 'NOT_ARRAY_OR_WORD_COUNT',
        'invalid fingerprint word': 'WORD_TYPE_OR_RANGE',
    }
    return reasons.get(str(error), 'OTHER')


def fingerprint_storage_shape(raw):
    """Identify JSON container type only; never return content or field names."""
    if raw is None:
        return 'NULL'
    if not isinstance(raw, str):
        return 'NON_TEXT'
    if len(raw) > 8640:
        return 'OVERSIZED_TEXT'
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return 'INVALID_JSON'
    if isinstance(value, list):
        if not value:
            return 'EMPTY_LIST'
        if len(value) > 720:
            return 'TOO_MANY_WORDS'
        if all(type(x) is int for x in value):
            return 'INTEGER_LIST'
        if all(type(x) is str for x in value):
            return 'STRING_LIST'
        return 'MIXED_LIST'
    if isinstance(value, dict):
        return 'JSON_OBJECT'
    if isinstance(value, str):
        return 'JSON_STRING'
    return 'OTHER_JSON_TYPE'


def audio_cache_key(record):
    """An asset has separate intro and outro windows; never share them."""
    return (record['playlist_id'], record['asset_key'], record['segment_type'])


def unrelated_control_cohort(target, cohort_key):
    """A negative control must be another series in the same playlist/kind."""
    return (target['playlist_id'] == cohort_key[0]
            and target['source_key'] != cohort_key[1]
            and target['segment_type'] == cohort_key[3])


def cached(con, record, counts):
    """Only use current-duration saved cache windows; no provider fetches."""
    w=con.execute("""
       SELECT words_json, offset_ms, length_ms, step_ms, duration_ms
       FROM skip_auto_windows
       WHERE asset_key=? AND kind=? AND duration_ms=?
       ORDER BY created_at DESC LIMIT 1
    """,(record['asset_key'],record['segment_type'],record['asset_duration_ms'])).fetchone()
    if w is None:
        counts['MISSING_CACHED_AUDIO_WINDOW']+=1
        return None
    if (type(w['offset_ms']) is not int
            or type(w['length_ms']) is not int
            or w['length_ms']<15000
            or w['offset_ms']+w['length_ms']>record['asset_duration_ms']+2000):
        counts['INVALID_CACHED_AUDIO_WINDOW']+=1
        return None
    try:
        return decode(w['words_json'],step_ms=w['step_ms'],offset_ms=w['offset_ms'])
    except ValueError as exc:
        counts['UNSUPPORTED_OR_INVALID_FINGERPRINT_PAYLOAD']+=1
        counts['FINGERPRINT_FORMAT_'+fingerprint_error_code(exc)]+=1
        counts['FINGERPRINT_STORAGE_'+fingerprint_storage_shape(w['words_json'])]+=1
        return None


def original_visual_only(con, release, record):
    failed=[]
    con.execute('SAVEPOINT fp_gate')
    try:
        for title,fn,args in (
          ('enabled',release.enabled,(con,record['playlist_id'])),
          ('visual',release.scene_release_ready,(con,record)),
          ('reference',release.current_reference,(con,record)),
          ('audio',release.reviewed_release_ready,(record,)),
          ('detector',release.detector_release_ready,(con,record)),
        ):
            try:
                if not bool(fn(*args)):failed.append(title)
            except Exception:failed.append(title+'_error')
    finally:
        con.execute('ROLLBACK TO fp_gate')
        con.execute('RELEASE fp_gate')
    return failed==['visual']


def is_protected(con, row):
    if con.execute("""SELECT 1 FROM skip_auto_blocks
        WHERE asset_key=? AND kind=? AND ABS(duration_ms-?)<=2000 LIMIT 1""",
        (row['asset_key'],row['segment_type'],row['duration_ms'])).fetchone():
        return True
    if con.execute("""SELECT 1 FROM skip_records r
        LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
        WHERE r.asset_key=? AND r.segment_type=? AND r.id<>?
          AND ABS(r.duration_ms-?)<=2000
          AND (r.status IN ('approved','rejected')
               OR (r.status='pending' AND
                   (r.source='device' OR COALESCE(e.human_review,0)=1)))
        LIMIT 1""",(row['asset_key'],row['segment_type'],row['id'],
                     row['duration_ms'])).fetchone():
        return True
    return False


def playlist_summary_lines(counts, playlist_id):
    """Report only (playlist_id, reason) counters, never global string keys.

    The cache diagnostics intentionally share a Counter with tuple-keyed
    per-playlist results. Sorting mixed str/tuple keys raises TypeError.
    This formatter keeps the two namespaces separate.
    """
    entries = [
        (reason, count)
        for key, count in counts.items()
        if isinstance(key, tuple) and len(key) == 2
        for pid, reason in (key,)
        if pid == playlist_id and isinstance(reason, str)
    ]
    return [f'  {reason}: {count}' for reason, count in sorted(entries)]


def review_label(key):
    """Opaque stable series label, never print source IDs or stream URLs."""
    return hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:10]


def fmt(ms):
    if type(ms) not in (int,float) or ms < 0:
        return "?"
    n=round(ms/1000)
    return f"{n//60:02d}:{n%60:02d}"


def safe_title(con, asset_key, cols):
    """Best effort title from local metadata, no URLs or original keys."""
    for field in ("series_title", "series_name", "title", "name"):
        if field not in cols:
            continue
        row=con.execute("SELECT "+field+" FROM skip_assets WHERE asset_key=? LIMIT 1",
                        (asset_key,)).fetchone()
        if not row or not isinstance(row[0],str):
            continue
        title=" ".join(row[0].split())
        if (2<=len(title)<=100 and "://" not in title
                and not title.startswith(("/", "magnet:", "xtream:"))):
            return title
    return None


def audit():
    raw=os.environ.get('EPISCENE_FP_SNAPSHOT','')
    snapshot=Path(raw)
    if not raw.startswith('/tmp/') or not snapshot.is_file() or snapshot.is_symlink():
        raise RuntimeError('Untrusted or missing DB snapshot')
    src=sqlite3.connect(snapshot.resolve().as_uri()+'?mode=ro',uri=True,timeout=60)
    with tempfile.TemporaryDirectory(prefix='episcene_fp_probe_',dir='/tmp') as dir_:
        con=sqlite3.connect(str(Path(dir_)/'copy.db'),timeout=60)
        try:src.backup(con)
        finally:src.close()
        try:
            con.row_factory=sqlite3.Row
            schema(con)
            os.chdir(APP.resolve())
            sys.path.insert(0,str(APP.resolve()))
            import skip_automation  # noqa: F401 - original patch layer
            import skip_release as release
            if Path(release.__file__).resolve().parent!=APP.resolve():
                raise RuntimeError('Wrong original release module')
            for name in ('enabled','scene_release_ready','current_reference',
                         'reviewed_release_ready','detector_release_ready'):
                if not callable(getattr(release,name,None)):
                    raise RuntimeError('Original gate unavailable')
            rows=con.execute(SQL).fetchall()
            if len(rows)>MAX_ROWS:raise RuntimeError('Sample too large')
            cohorts=defaultdict(list)
            for row in rows:
                if valid_asset(row):
                    key=(row['playlist_id'],row['source_key'],row['season'],row['segment_type'])
                    cohorts[key].append(row)
            counts=Counter()
            sampled=Counter()
            asset_cols={r[1] for r in con.execute("PRAGMA table_info(skip_assets)")}
            report=[]
            cached_by_window={}
            for key,members in cohorts.items():
                playlist=key[0]
                for target in members:
                    if sampled[(playlist, target['segment_type'])]>=MAX_TARGETS_PER_PLAYLIST_AND_KIND:
                        break
                    if not audio_confirmed(target) or target['status']!='pending':
                        continue
                    if is_protected(con,target):
                        counts[(playlist,'BLOCKED_OR_HUMAN_CORRECTION')]+=1
                        continue
                    if not original_visual_only(con,release,target):
                        continue
                    sampled[(playlist,target['segment_type'])]+=1
                    counts[(playlist,'VISUAL_ONLY_SAMPLED')]+=1
                    ev=as_json(target['evidence_json'])
                    if ev.get('audio_visual_disagreement') is True:
                        counts[(playlist,'VISUAL_DISAGREEMENT')]+=1
                        continue
                    target_cache_key=audio_cache_key(target)
                    if target_cache_key not in cached_by_window:
                        cached_by_window[target_cache_key]=cached(
                            con,target,counts)
                    own=cached_by_window[target_cache_key]
                    if own is None:
                        counts[(playlist,'NO_TARGET_AUDIO_FINGERPRINT')]+=1
                        continue
                    # Clip the positive target once, and reuse exactly the
                    # same snippet for all positive and negative controls.
                    import math
                    first=max(0,int((target['start_ms']-own.offset_ms)/own.step_ms))
                    last=min(len(own.words),math.ceil((
                        min(target['end_ms'],target['start_ms']+30000)
                        -own.offset_ms)/own.step_ms))
                    if last-first < math.ceil(15000/own.step_ms):
                        counts[(playlist,'TARGET_CLIP_TOO_SHORT')]+=1
                        continue
                    clipped=Fingerprint(
                        own.words[first:last],own.step_ms,
                        own.offset_ms+round(first*own.step_ms))
                    used={target['episode']}
                    peers=[]
                    peer_locations=[]
                    manual_proof_found=False
                    possible=sorted(
                        (p for p in members if p['episode']!=target['episode']
                         and (human_approved(p) or audio_confirmed(p))
                         and not is_protected(con,p)),
                        key=lambda p:(0 if human_approved(p) else 1, p['episode'],p['id']))
                    for peer in possible:
                        if peer['episode'] in used:
                            continue
                        used.add(peer['episode'])
                        if len(used)-1>MAX_PEERS_PER_TARGET:
                            break
                        manual=human_approved(peer)
                        manual_proof_found|=manual
                        peer_cache_key=audio_cache_key(peer)
                        if peer_cache_key not in cached_by_window:
                            cached_by_window[peer_cache_key]=cached(con,peer,counts)
                        partner=cached_by_window[peer_cache_key]
                        if partner is None:
                            continue
                        found=match(clipped,partner)
                        if found is None:
                            continue
                        counts[(playlist,'MATCHED_CONTENT_ANY_SHIFT')]+=1
                        if not near_record(found,start_ms=peer['start_ms'],
                                           end_ms=peer['end_ms'],target=False):
                            counts[(playlist,'MATCH_OUTSIDE_PEER_MARKER')]+=1
                            continue
                        peers.append((peer['episode'],found,manual))
                        peer_locations.append({
                            "episode":peer['episode'],
                            "marker_start":fmt(peer['start_ms']),
                            "marker_end":fmt(peer['end_ms']),
                            "audio_position":fmt(found.reference_start_ms),
                            "verified_manual":bool(manual),
                        })
                    # Real-cache negative controls: different series in the
                    # same playlist and segment kind, not the same family.
                    # A hit is a warning requiring human investigation,
                    # never evidence for auto-release.
                    controls=0
                    false_controls=0
                    tested_series=set()
                    for other_key,other_members in cohorts.items():
                        if controls>=MAX_CROSS_SERIES_CONTROLS:
                            break
                        if not unrelated_control_cohort(target,other_key):
                            continue
                        if other_key[1] in tested_series:
                            continue
                        other=next((x for x in other_members
                                    if audio_confirmed(x)
                                    and not is_protected(con,x)),None)
                        if other is None:
                            continue
                        other_cache_key=audio_cache_key(other)
                        if other_cache_key not in cached_by_window:
                            cached_by_window[other_cache_key]=cached(
                                con,other,counts)
                        other_window=cached_by_window[other_cache_key]
                        if other_window is None:
                            continue
                        tested_series.add(other_key[1])
                        controls+=1
                        suspect=match(clipped,other_window)
                        counts[(playlist,'NEGATIVE_CONTROL_CHECKED')]+=1
                        if suspect is not None:
                            false_controls+=1
                            counts[(playlist,'NEGATIVE_CONTROL_POSSIBLE_FALSE_MATCH')]+=1
                    if controls==0:
                        counts[(playlist,'NEGATIVE_CONTROL_UNAVAILABLE')]+=1
                    counts[(playlist,'MATCHED_INDEPENDENT_PEERS_'+str(len(peers)))]+=1
                    if len(peers)>=3:
                        counts[(playlist,'THREE_OR_MORE_PEER_PROOFS')]+=1
                        report.append({
                            "playlist":"4K ANALYSE" if playlist==8 else "THE BEST",
                            "series_code":review_label(target['source_key']),
                            "series_title_if_available":safe_title(con,target['asset_key'],asset_cols),
                            "season":target['season'],
                            "episode":target['episode'],
                            "segment":target['segment_type'],
                            "marker_start":fmt(target['start_ms']),
                            "marker_end":fmt(target['end_ms']),
                            "independent_audio_peers":len(peers),
                            "peer_details":peer_locations,
                            "negative_controls":controls,
                            "suspected_cross_series_matches":false_controls,
                            "has_confirmed_manual_anchor":any(x[2] for x in peers),
                            "decision":"MANUAL_REVIEW_ONLY",
                        })
                    if any(human for _,_,human in peers):
                        counts[(playlist,'MATCHED_MANUAL_ANCHOR')]+=1
                    result=inspect_cohort(target,peers)
                    counts[(playlist,result)]+=1
                    if manual_proof_found:
                        counts[(playlist,'AVAILABLE_APPROVED_HUMAN_PEER')]+=1
            print('EPISCENE – FINGERPRINT / REVIEW REPORT V4, READ-ONLY')
            print('Version: read-only; original release gates unchanged.')
            print('Kriterien: >=15s Fingerprint-Overlap, >=90% passende Frames, diverse Wörter.')
            print('No media requests, no approvals, no server/worker changes.')
            for pid,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
                print('\n'+name)
                print('  sampled visual-only intro:',sampled[(pid,'intro')])
                print('  sampled visual-only outro:',sampled[(pid,'outro')])
                for line in playlist_summary_lines(counts, pid):
                    print(line)
            for key in sorted(k for k in counts if isinstance(k,str)):
                if key in ('MISSING_CACHED_AUDIO_WINDOW',
                           'INVALID_CACHED_AUDIO_WINDOW',
                           'UNSUPPORTED_OR_INVALID_FINGERPRINT_PAYLOAD') or key.startswith(('FINGERPRINT_FORMAT_', 'FINGERPRINT_STORAGE_')):
                    print('  '+key+':',counts[key])
            print('\nSTAERKSTE AUDIOKANDIDATEN – NUR MANUELL PRUEFEN')
            for i,entry in enumerate(report,1):
                name=entry['series_title_if_available'] or ('Serie '+entry['series_code'])
                print(f"{i}. {entry['playlist']} | {name} | S{entry['season']} E{entry['episode']} "
                      f"| {entry['segment']} {entry['marker_start']}-{entry['marker_end']}"
                      f" | Audio-Peers: {entry['independent_audio_peers']}"
                      f" | Negativtests: {entry['negative_controls']}"
                      f" | Fremdtreffer: {entry['suspected_cross_series_matches']}"
                      f" | Manuell bestaetigt: {entry['has_confirmed_manual_anchor']}")
                positions=', '.join(
                    f"E{p['episode']} {p['marker_start']}-{p['marker_end']}"
                    f" (Audio bei {p['audio_position']})"
                    for p in entry['peer_details'])
                print('   Vergleichsfolgen: '+positions)
            print('Die Audiofundstelle beweist NICHT automatisch exakte Intro/Outro-Grenzen.')
            print('SHADOW_FINGERPRINT_PLUS_MANUAL_NOT_RELEASED is NOT a release approval.')
            print('Do not install any release/worker patch based solely on this diagnostic.')
        finally:con.close()


if __name__=='__main__':
    if os.environ.get('EPISCENE_FP_SHADOW')=='YES':
        audit()
    else:
        isolated_launch()
