#!/usr/bin/env python3
"""EpiScene audio-cache retention sizing. Pure read-only; aggregate counts only.
No worker imports, service changes, raw IDs, provider URLs, or marker writes.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

DB = Path('/var/lib/epimediahub/provisioning.db')
MODULE = Path('/opt/epimediahub/provisioning/skip_automation.py')

def parsed(s):
    try:
        x=json.loads(s or '{}')
        return x if isinstance(x,dict) else {}
    except (TypeError,ValueError):
        return {}

def main():
    if any(p.is_symlink() or not p.is_file() for p in (DB,MODULE)):
        raise SystemExit('ABBRUCH: Dateien fehlen oder sind Symlinks')
    src=MODULE.read_bytes()
    h=hashlib.sha256(src).hexdigest()
    db=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        cache=set()
        n=0
        total_bytes=0
        max_bytes=0
        for asset,kind,length in db.execute("SELECT asset_key,kind,LENGTH(words_json) FROM skip_auto_windows"):
            cache.add((asset,kind));n+=1;total_bytes+=(length or 0);max_bytes=max(max_bytes,length or 0)
        requests=set()
        markers=Counter()
        for kind,raw in db.execute("""SELECT r.segment_type,e.evidence_json
             FROM skip_records r JOIN skip_auto_evidence e ON e.record_id=r.id
             WHERE r.status='pending' AND r.segment_type IN ('intro','recap','outro')"""):
            ev=parsed(raw)
            windows=ev.get('windows')
            if not isinstance(windows,list):
                continue
            markers['proposals_with_windows']+=1
            for w in windows:
                if (isinstance(w,dict) and w.get('origin','server')=='server'
                    and isinstance(w.get('asset_key'),str)):
                    requests.add((w['asset_key'],kind))
        for kind, count in db.execute('SELECT kind,COUNT(*) FROM skip_auto_windows GROUP BY kind'):
            print('  Cache Segment:',str(kind)[:20],int(count))
        print('Quelle: sqlite read-only / Python-Paket: NICHT importiert')
        print('Aktueller Code SHA256:',h[:16])
        print('Expliziter alter Grenzwert LIMIT 256 vorhanden:',b'LIMIT 256' in src)
        print('Cacheeintraege:',n)
        print('Fingerprintbytes gesamt:',total_bytes)
        print('Fingerprintbytes Durchschnitt:',round(total_bytes/n) if n else 0)
        print('Fingerprintbytes Maximum:',max_bytes)
        print('Pending-Marker mit Fenstern:',markers['proposals_with_windows'])
        print('Einzigartige referenzierte Audiofenster:',len(requests))
        print('Davon vorhanden:',len(requests & cache))
        print('Davon fehlend:',len(requests-cache))
        print('Cachefenster ohne Pending-Referenz:',len(cache-requests))
        print('SQLite-Dateigroesse MiB:',round(DB.stat().st_size/1024**2,1))
        usage=shutil.disk_usage(DB.parent)
        print('Datentraeger frei GiB:',round(usage.free/1024**3,2))
        print('Datentraeger Gesamt GiB:',round(usage.total/1024**3,2))
        print('Keine Aenderungen, keine Jobstarts, keine Freigaben.')
    finally:
        db.close()

if __name__=='__main__':
    main()
