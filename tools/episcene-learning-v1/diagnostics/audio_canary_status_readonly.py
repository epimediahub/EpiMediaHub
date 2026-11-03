#!/usr/bin/env python3
"""EpiScene audio cache recovery canary status (database READ-ONLY).
Only aggregate statuses, counts, and original-vs-current availability.
Never prints provider URLs, customer names, asset keys, or raw log messages.
"""
from collections import Counter
import sqlite3
from pathlib import Path

DB = Path('/var/lib/epimediahub/provisioning.db')
LEDGER = 'episcene_audio_cache_canary_v1'
NAMES = {8:'4K ANALYSE', 10:'THE BEST'}

def main():
    if DB.is_symlink() or not DB.is_file():
        raise SystemExit('STOP: database missing or symlink')
    con = sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=20)
    try:
        con.row_factory=sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        found = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (LEDGER,)).fetchone()
        if not found:
            print('NO_CANARY_LEDGER: no recorded canary run; database unchanged')
            return
        rows = con.execute("""
            SELECT l.playlist_id,l.original_status,l.queued_at, j.status AS current_status,
              EXISTS(SELECT 1 FROM skip_auto_windows w WHERE w.asset_key=l.asset_key AND w.kind='intro') intro_window,
              EXISTS(SELECT 1 FROM skip_auto_windows w WHERE w.asset_key=l.asset_key AND w.kind='outro') outro_window
            FROM episcene_audio_cache_canary_v1 l
            LEFT JOIN skip_jobs j ON j.asset_key=l.asset_key
            ORDER BY l.playlist_id,l.queued_at
        """).fetchall()
        print('EPISCENE AUDIO-CANARY STATUS / NUR LESEN')
        print('Cache window availability is a necessary step, NOT a proof of matching fingerprint or gate approval.')
        for pid, name in NAMES.items():
            selected=[r for r in rows if r['playlist_id']==pid]
            statuses=Counter(r['current_status'] or 'missing_job' for r in selected)
            print('\\n'+name)
            print('  canary_jobs:',len(selected))
            for status,count in sorted(statuses.items()):
                print('  status_'+str(status)[:24]+':',count)
            print('  intro_windows_now:',sum(int(r['intro_window']) for r in selected))
            print('  outro_windows_now:',sum(int(r['outro_window']) for r in selected))
            print('  both_segment_windows_now:',sum(bool(r['intro_window'] and r['outro_window']) for r in selected))
        n=con.execute("SELECT COUNT(*) FROM skip_auto_windows").fetchone()[0]
        print('\\nTotal audio cache windows:',n)
        print('No marker approvals, no worker restarts, no queue modifications.')
    finally:
        con.close()

if __name__=='__main__':
    main()
