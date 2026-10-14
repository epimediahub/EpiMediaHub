#!/usr/bin/env python3
"""Review progress and coarse image-signal changes for EpiScene MobLand shadow captures.

Original and shadow SQLite databases opened READ ONLY. Never approves a marker.
The resulting visual statistics indicate changes, not semantic proof of credits.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
import statistics
from collections import Counter
from pathlib import Path

BASE=Path('/var/lib/episcene-learning/reference-round-40')
ORIGINAL=Path('/var/lib/epimediahub/provisioning.db')
SOURCE=BASE/'shadow.sqlite3'
CAPTURE=BASE/'visual_fingerprints.sqlite3'
FIELDS=('asset_key','source_key','playlist_id','stream_id','extension',
        'duration_ms','season','episode','updated_at','content_version','etag')


def version(asset):
    return hashlib.sha256(json.dumps({k:asset.get(k) for k in FIELDS},
         sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def motion_diff(left,right):
    return ((left[0]^right[0]).bit_count()/63+(left[1]^right[1]).bit_count()/64)/2


def stats(frames):
    if len(frames)!=80:
        raise ValueError('incomplete visual window')
    for frame in frames:
        if not isinstance(frame,list) or len(frame)!=4 or any(type(v)!=int for v in frame):
            raise ValueError('invalid frame payload')
    # +/-4 seconds from predicted onset (center sample at 20s).
    before=frames[32:39]
    after=frames[41:48]
    med=statistics.median
    brightness=abs(med(v[3] for v in before)-med(v[3] for v in after))
    contrast=abs(med(v[2] for v in before)-med(v[2] for v in after))
    within_before=med(motion_diff(a,b) for a,b in zip(before,before[1:]))
    within_after=med(motion_diff(a,b) for a,b in zip(after,after[1:]))
    motion_shift=abs(within_before-within_after)
    at_cut=motion_diff(frames[39],frames[40])
    return dict(brightness_shift=round(brightness,2),
                contrast_shift=round(contrast,2),
                motion_change=round(motion_shift,4),
                immediate_frame_change=round(at_cut,4))


def compare(db,shadow,frames_db=None):
    db.row_factory=sqlite3.Row;shadow.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON');shadow.execute('PRAGMA query_only=ON')
    if frames_db:
        frames_db.row_factory=sqlite3.Row
        frames_db.execute('PRAGMA query_only=ON')
    refs=shadow.execute("""SELECT marker_id id,asset_key,'reference' kind FROM owner_attested_round40
      WHERE title='mobland' AND season=1 AND playlist_id=8 AND kind='outro'
      ORDER BY marker_id""").fetchall()
    cands=shadow.execute("""SELECT auto_marker_id id,asset_key,'candidate' kind
      FROM shadow_outro_candidates WHERE series='mobland' AND season=1
        AND playlist_id=8 AND status='SHADOW_REVIEW_ONLY'
      ORDER BY auto_marker_id""").fetchall()
    pending=[]
    allitems=[]
    for item in [*refs,*cands]:
        item=dict(item)
        row=db.execute('''SELECT r.id,r.source,r.status,r.start_ms,r.end_ms,
                  a.* FROM skip_records r LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
                  WHERE r.id=?''',(item['id'],)).fetchone()
        if row is None or row['asset_key']!=item['asset_key']:
            item['status']='MISSING_OR_UNLINKED_LIVE_MARKER'
        elif frames_db is None:
            item['status']='WAITING_FOR_FIRST_CAPTURE'
        else:
            saved=frames_db.execute('''SELECT kind,asset_version,offset_ms,length_ms,step_ms,
                       frames_json,sha256,status FROM frames WHERE record_id=?''',(item['id'],)).fetchone()
            if saved is None:
                item['status']='PENDING_CAPTURE'
            elif saved['asset_version']!=version(dict(row)):
                item['status']='STALE_ASSET_VERSION'
            elif saved['status']!='SHADOW_ONLY' or saved['step_ms']!=500 or saved['length_ms']!=40000 or saved['kind']!=item['kind']:
                item['status']='INVALID_CAPTURE_METADATA'
            elif hashlib.sha256(saved['frames_json'].encode()).hexdigest()!=saved['sha256']:
                item['status']='CORRUPTED_CAPTURE'
            else:
                try:
                    item.update(stats(json.loads(saved['frames_json'])))
                    item['status']='VISUAL_HASHES_READY'
                except (ValueError,TypeError,KeyError):
                    item['status']='INVALID_CAPTURE_DATA'
        if item['status']!='VISUAL_HASHES_READY':
            pending.append(item['id'])
        allitems.append(item)
    complete=[r for r in allitems if r['status']=='VISUAL_HASHES_READY']
    refready=[r for r in complete if r['kind']=='reference']
    candidate_ready=[r for r in complete if r['kind']=='candidate']
    result=dict(mode='READ_ONLY_SHADOW_REVIEW',expected_targets=len(allitems),
         completed=len(complete),reference_completed=len(refready),
         candidate_completed=len(candidate_ready),pending_ids=pending,
         statuses=dict(Counter(r['status'] for r in allitems)),
         results=allitems,new_verified_labels=0,new_auto_approvals=0,
         note='Frame fingerprints can show structural changes but cannot by themselves prove the beginning of credits.')
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--original',type=Path,default=ORIGINAL)
    p.add_argument('--shadow',type=Path,default=SOURCE)
    p.add_argument('--captures',type=Path,default=CAPTURE)
    a=p.parse_args()
    for path in (a.original,a.shadow):
        if not path.is_file() or path.is_symlink():
            raise SystemExit('Original/Shadow database not found or symlink')
    if a.captures.exists() and a.captures.is_symlink():
        raise SystemExit('Capture database may not be a symlink')
    captures=None
    try:
        with sqlite3.connect(a.original.resolve().as_uri()+'?mode=ro',uri=True) as db,\
             sqlite3.connect(a.shadow.resolve().as_uri()+'?mode=ro',uri=True) as sh:
            if a.captures.is_file():
                captures=sqlite3.connect(a.captures.resolve().as_uri()+'?mode=ro',uri=True)
            print(json.dumps(compare(db,sh,captures),ensure_ascii=False,indent=2))
    finally:
        if captures:captures.close()


if __name__=='__main__':
    main()
