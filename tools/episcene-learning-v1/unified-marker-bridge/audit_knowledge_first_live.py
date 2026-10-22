#!/usr/bin/env python3
"""Read-only sample of Knowledge First decisions on queued analysis episodes.

No streaming requests, marker approvals, code replacement or secret output.
Predicted eligibility is not an actual saved-job count.
"""
from __future__ import annotations
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess

DB=Path('/var/lib/epimediahub/provisioning.db')
WORKER=Path('/opt/epimediahub/provisioning/skip_analysis_worker.py')
HELPER=Path('/opt/epimediahub/provisioning/episcene_knowledge_first_runtime.py')
KINDS=('intro','recap','outro')
PLAYLISTS=(8,10)

def _open(db):
    con=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True,timeout=8)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    return con

def _systemd():
    try:
        p=subprocess.run(['systemctl','show','epimediahub-skip-analysis.service',
          '-p','ActiveState','-p','SubState','-p','MainPID',
          '-p','ExecMainStartTimestamp','-p','Result','--no-pager'],
          capture_output=True,text=True,timeout=5,check=False)
        names={'ActiveState','SubState','MainPID','ExecMainStartTimestamp','Result'}
        return dict(line.split('=',1) for line in p.stdout.splitlines()
                    if '=' in line and line.split('=',1)[0] in names)
    except (OSError,subprocess.TimeoutExpired):
        return {'status':'SYSTEMD_UNAVAILABLE'}

def _load_helper(helper):
    if helper.is_symlink() or not helper.is_file() or helper.stat().st_size>50000:
        return None
    spec=importlib.util.spec_from_file_location(
        'episcene_knowledge_first_runtime_audit',helper)
    if spec is None or spec.loader is None:
        return None
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod if callable(getattr(mod,'decide',None)) else None

def inspect(db=DB,worker=WORKER,helper=HELPER,limit=15):
    out={'mode':'KNOWLEDGE_FIRST_READ_ONLY_COVERAGE',
         'production_writes':0,'provider_requests':0,
         'customer_identifiers_exported':False,
         'service':_systemd(),
         'installed_worker_hook':False,
         'helper_available':False,
         'preview_is_not_completed_job_count':True,
         'per_playlist':{str(p):{} for p in PLAYLISTS}}
    if type(limit) is not int or not 1<=limit<=25:
        return dict(out,status='STOP_INVALID_LIMIT')
    if db.is_symlink() or not db.is_file() or worker.is_symlink() or not worker.is_file():
        return dict(out,status='STOP_EXPECTED_INSTALL_MISSING')
    try:
        code=worker.read_text(encoding='utf-8')
        out['installed_worker_hook']=('_epi_kf_install(_epi_sys.modules[__name__])' in code)
        out['worker_file_modified_utc']=datetime.fromtimestamp(
            worker.stat().st_mtime,timezone.utc).isoformat(timespec='seconds')
        if not out['installed_worker_hook']:
            return dict(out,status='STOP_WORKER_HOOK_ABSENT')
        module=_load_helper(helper)
        out['helper_available']=module is not None
        if module is None:
            return dict(out,status='STOP_HELPER_MISSING')

        @contextmanager
        def readonly_db():
            con=_open(db)
            try:
                yield con
            finally:
                con.close()
        with _open(db) as con:
            for pid in PLAYLISTS:
                rows=con.execute("""SELECT j.asset_key
                    FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                    WHERE a.playlist_id=? AND a.media_type='episode' AND j.status='queued'
                    GROUP BY j.asset_key ORDER BY MIN(j.id) LIMIT ?""",
                    (pid,limit)).fetchall()
                counts=Counter()
                counts['episodes_sampled']=len(rows)
                for row in rows:
                    for kind in KINDS:
                        source=module.decide(
                            readonly_db,{'asset_key':row['asset_key'],'kind':kind})
                        counts['kind_eligibility_checks']+=1
                        if source in ('own','introdb','theintrodb'):
                            counts[kind+'_'+source]+=1
                out['per_playlist'][str(pid)]={
                    'episodes_sampled':counts['episodes_sampled'],
                    'kind_eligibility_checks':counts['kind_eligibility_checks'],
                    'eligible_preview_by_kind':{
                        kind:{source:counts[kind+'_'+source] for source in
                              ('own','introdb','theintrodb')} for kind in KINDS}}
    except (OSError,sqlite3.Error,ImportError,TypeError,ValueError) as error:
        return dict(out,status='STOP_READ_ONLY_CHECK_FAILED',
                    error_type=type(error).__name__)
    out['status']='PREVIEW_COMPLETE'
    out['note']='This is a bounded prediction for queued episodes, not proof of completed savings or the worker executing the hook.'
    return out

if __name__=='__main__':
    print(json.dumps(inspect(),ensure_ascii=False,indent=2))
