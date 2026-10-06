#!/usr/bin/env python3
"""Measure local dashboard reads against the live DB opened in read-only mode.

No public HTTP server, login changes, provider calls or database mutations.
Network/Cloudflare time is intentionally outside this local measurement.
"""
import contextlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import types
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def check(database):
    from flask import Flask, jsonify
    import skip_markers
    @contextlib.contextmanager
    def db():
        con=sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=.05)
        con.row_factory=sqlite3.Row
        con.create_function('epi_casefold',1,lambda value:str(value or '').casefold(),deterministic=True)
        try:yield con
        finally:con.close()
    site=Flask('local-latency-check',template_folder=str(ROOT/'templates'),static_folder=str(ROOT/'static'))
    site.secret_key='private-local-check'
    site.testing=True
    site.add_url_rule('/dashboard','dashboard',lambda:'Dashboard')
    site.add_url_rule('/health','health',lambda:jsonify(status='ok'))
    backend=types.ModuleType('app')
    backend.digest=lambda value:value
    backend.web_auth=lambda:None
    with mock.patch.dict(sys.modules,{'app':backend}),mock.patch.object(skip_markers,'migrate'):
        skip_markers.install(site,db)
    rows=[]
    client=site.test_client()
    for label,path in [('page_first','/admin/skip'),('page_warm','/admin/skip'),
                       ('filter','/admin/skip/progress?progress_filter=missing_intro'),
                       ('search','/admin/skip/progress?progress_search=Serie')]:
        start=time.perf_counter()
        response=client.get(path)
        assert response.status_code==200, 'Dashboard-Abfrage fehlgeschlagen'
        phases={item.split(';dur=')[0]+'_ms':float(item.split(';dur=')[1])
                for item in response.headers.get('Server-Timing','').split(', ') if ';dur=' in item}
        rows.append(dict(view=label,local_ms=round((time.perf_counter()-start)*1000,2),**phases))
    return rows


if __name__=='__main__':
    try:value=check(sys.argv[1])
    except Exception as error:raise SystemExit('Lokale Dashboard-Messung fehlgeschlagen: '+type(error).__name__) from None
    print(json.dumps(dict(local_dashboard=value,network_time_included=False),ensure_ascii=False,indent=2))
