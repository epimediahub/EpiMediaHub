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

def rejection_reasons(frame):
    """Classify the conditions of EXACT failed returns, read-only and ID-free."""
    line = frame.f_lineno
    ctx = frame.f_locals
    reasons = []
    if line == 316:
        cached = ctx.get('cached')
        item = ctx.get('item')
        row = ctx.get('row')
        used = ctx.get('used')
        if not cached:
            return ['cache_missing_or_filtered']
        if not isinstance(item, dict) or row is None:
            return ['unexpected_runtime_locals']
        if cached['source_key'] != row['source_key']:
            reasons.append('source_key_mismatch')
        if cached['season'] != row['season']:
            reasons.append('season_mismatch')
        if cached['episode'] in used:
            reasons.append('duplicate_episode')
        if abs(cached['duration_ms'] - cached['current_duration']) > 2000:
            reasons.append('asset_duration_changed')
        for k in ('episode','duration_ms','offset_ms','length_ms','step_ms'):
            if cached[k] != item.get(k):
                reasons.append('metadata_mismatch_'+k)
        if hashlib.sha256(cached['words_json'].encode()).hexdigest() != item.get('fingerprint_sha256'):
            reasons.append('fingerprint_hash_mismatch')
        return reasons or ['unclassified_line_316']
    if line == 289:
        def valid_num(value, low, high):
            return type(value) in (int, float) and low <= value <= high
        if not valid_num(ctx.get('mean_q'), .90, 1):
            reasons.append('mean_pair_quality')
        if not valid_num(ctx.get('spread'), 0, 2):
            reasons.append('boundary_spread_sec')
        if not valid_num(ctx.get('position'), 0, 1):
            reasons.append('position_plausibility')
        support = ctx.get('support')
        attempted = ctx.get('attempted')
        windows = ctx.get('windows')
        trusted = ctx.get('trusted')
        if type(support) is not int or not 2 <= support <= 4:
            reasons.append('support_outside_2_4')
        if type(attempted) is not int or type(support) is not int or not support <= attempted <= 4:
            reasons.append('attempted_partners_outside_limits')
        if not isinstance(windows, list) or type(attempted) is not int or len(windows) != attempted + 1:
            reasons.append('windows_count_mismatch')
        if not isinstance(trusted, list):
            reasons.append('trusted_not_list')
        else:
            if len(trusted) != len(set(trusted)):
                reasons.append('duplicate_trusted_episode')
            if any(type(x) is not int for x in trusted):
                reasons.append('trusted_episode_not_int')
            if support == 2 and not trusted:
                reasons.append('two_partners_no_trusted_episode')
        return reasons or ['unclassified_line_289']
    return ['other_return_line']


def trace_detector_return(fn, *args):
    """Capture the actual return point and the relevant condition values."""
    returns = []
    code = fn.__code__
    def tracer(frame, event, arg):
        if frame.f_code is code and event == 'return':
            try:
                details = rejection_reasons(frame) if arg is False else []
            except Exception as exc:
                details = ['diagnostic_problem_'+type(exc).__name__]
            returns.append((frame.f_lineno, details))
        return tracer
    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        result = fn(*args)
    finally:
        sys.settrace(previous)
    lineno, details = returns[-1] if returns else (-1, ['no_return_trace'])
    return bool(result), lineno, details


def gates(R, con, row):
    failed=[]; errors=[]; detector_line = None; detector_details = []
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
            if name == 'detector_evidence':
                passed, detector_line, detector_details = trace_detector_return(fn, *args)
                if not passed:
                    failed.append(name)
            elif not bool(fn(*args)):
                failed.append(name)
        except Exception as ex:
            failed.append(name)
            errors.append(name+':'+type(ex).__name__)
    return failed, errors, detector_line, detector_details

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
            detector_lines=collections.Counter()
            detector_primary=collections.Counter()
            detector_reasons=collections.Counter()
            issues=collections.Counter()
            segments=collections.Counter()
            for row in selected:
                target.execute('SAVEPOINT safe_eval')
                try:
                    failed,errors,detector_line,details=gates(R,target,row)
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
                if 'detector_evidence' in failed:
                    detector_lines[(p, detector_line)]+=1
                    detector_primary[(p, detector_line, details[0] if details else 'unknown')]+=1
                    for reason in details:
                        detector_reasons[(p, detector_line, reason)]+=1
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
                print('  Rueckgabezeilen von detector_release_ready (Code-Zeile -> Anzahl):')
                for (i, line), n in detector_lines.most_common():
                    if i == p:
                        print('    Zeile %-8s %d' % (line, n))
                print('  ERSTE Ursache je Ablehnung (exklusive Zaehler):')
                for (i, line, cause), n in detector_primary.most_common():
                    if i == p:
                        print('    Zeile %-4s %-39s %d' % (line, cause, n))
                print('  ALLE festgestellten Ursachen (Mehrfachnennungen moeglich):')
                for (i, line, cause), n in detector_reasons.most_common():
                    if i == p:
                        print('    Zeile %-4s %-39s %d' % (line, cause, n))
                print('  Gate-Kombinationen:')
                for (i,k),n in patterns.most_common():
                    if i==p:print('    %-54s %d'%(k,n))
            print('\\nKEINE Freigaben oder Downloads. Snapshot wird gelöscht.')
            print('Rueckgabezeilen stammen aus dem Produktiv-Code, nicht aus einer nachgebauten Regel.')
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
