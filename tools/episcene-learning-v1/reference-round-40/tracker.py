#!/usr/bin/env python3
"""Read-only EpiScene 40-episode reference-round monitor.
Records new or changed device/manual markers; NEVER verifies user identity,
alters the original database, trains a model, or auto-approves a marker.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

STATE=Path("/var/lib/episcene-learning/reference-round-40")
SOURCE=Path("/var/lib/epimediahub/provisioning.db")
ORIGINS={"device","manual","app","user"}
TYPES={"intro","recap","outro"}


def canonical(s):
    return " ".join(str(s or "").casefold().split())


def atomic_json(path,data):
    temp=path.with_name("." + path.name + ".tmp." + str(os.getpid()))
    with temp.open("x",encoding="utf-8") as fp:
        json.dump(data,fp,ensure_ascii=False,indent=2,sort_keys=True)
        fp.write("\n")
    temp.chmod(0o600)
    os.replace(temp,path)


def read_plan(state):
    filename=state/"plan.json"
    data=filename.read_bytes()
    plan=json.loads(data)
    if plan.get("schema")!=1 or len(plan.get("episodes",[]))!=40:
        raise ValueError("Missing/incorrect 40-episode manifest")
    keys=set()
    for episode in plan["episodes"]:
        key=(int(episode["playlist_id"]),canonical(episode["series"]),
             int(episode["season"]),int(episode["episode"]))
        if key in keys:raise ValueError("Duplicate reference episode")
        keys.add(key)
    return plan,hashlib.sha256(data).hexdigest()


def inspect(source,plan):
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("Read-only original database not found")
    chosen={(int(x["playlist_id"]),canonical(x["series"]),int(x["season"]),int(x["episode"])):x["id"]
            for x in plan["episodes"]}
    db=sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)
    db.row_factory=sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        for table,cols in {
            "skip_assets":{"asset_key","playlist_id","title","season","episode"},
            "skip_records":{"id","asset_key","segment_type","source","status","start_ms","end_ms","created_at"}
        }.items():
            available={r[1] for r in db.execute("PRAGMA table_info("+table+")")}
            if not cols<=available:raise RuntimeError("Analyzer schema mismatch: "+table)
        matches=defaultdict(dict)
        for row in db.execute("""SELECT r.id,a.playlist_id,a.title,a.season,a.episode,
                     r.segment_type,r.source,r.status,r.start_ms,r.end_ms,r.created_at
                     FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
                     WHERE a.playlist_id IN (8,10)
                       AND lower(r.source) IN ('device','manual','app','user')
                       AND lower(r.segment_type) IN ('intro','recap','outro')"""):
            try:
                k=(int(row["playlist_id"]),canonical(row["title"]),int(row["season"]),int(row["episode"]))
                episode_id=chosen.get(k)
                if episode_id is None:continue
                start,end=int(row["start_ms"]),int(row["end_ms"])
                if not (0<=start<end<=86400000):continue
                kind=canonical(row["segment_type"])
                if kind not in TYPES or canonical(row["source"]) not in ORIGINS:continue
                signature=json.dumps([kind,start,end,str(row["status"]),str(row["source"]),str(row["created_at"])],
                                     ensure_ascii=False)
                matches[episode_id][str(int(row["id"]))]={
                    "kind":kind,"fingerprint":hashlib.sha256(signature.encode()).hexdigest()}
            except (ValueError,TypeError,KeyError):continue
    finally:
        db.close()
    return matches


def scan(state,source,initialize=False):
    plan,sha=read_plan(state)
    current=inspect(source,plan)
    baseline_file=state/"baseline.json"
    if not baseline_file.exists():
        if not initialize:raise RuntimeError("Install/reference baseline first")
        saved={e["id"]:{rid:v["fingerprint"] for rid,v in current.get(e["id"],{}).items()}
               for e in plan["episodes"]}
        atomic_json(baseline_file,{"plan_sha256":sha,"recorded_utc":datetime.now(timezone.utc).isoformat(),
                                  "existing_marker_signatures":saved})
        print("REFERENCE BASELINE CREATED; existing markers are preserved, not counted as new")
    baseline=json.loads(baseline_file.read_text(encoding="utf-8"))
    if baseline["plan_sha256"]!=sha:raise RuntimeError("Reference plan changed after baseline")
    entries=[]
    total=0;episode_count=0
    for ep in plan["episodes"]:
        ref_id=ep["id"]
        old=baseline["existing_marker_signatures"].get(ref_id,{})
        new={rid:v for rid,v in current.get(ref_id,{}).items() if old.get(rid)!=v["fingerprint"]}
        counts={kind:sum(v["kind"]==kind for v in new.values()) for kind in ("intro","recap","outro")}
        if new:episode_count+=1
        total+=len(new)
        entries.append({**ep,"marker_ids_new_or_changed":sorted(map(int,new)),
                        "new_or_changed":len(new),"kinds":counts,"existing_at_baseline":len(old)})
    status={"batch_id":plan["batch_id"],"checked_at_utc":datetime.now(timezone.utc).isoformat(),
            "baseline_at_utc":baseline["recorded_utc"],"planned_episodes":len(entries),
            "episodes_with_new_or_changed_markers":episode_count,
            "new_or_changed_markers":total,"verified_human_labels_added":0,
            "automatic_publication_enabled":False,"episodes":entries}
    atomic_json(state/"status.json",status)
    print(json.dumps({k:v for k,v in status.items() if k!="episodes"},ensure_ascii=False))
    for x in entries:
        if x["new_or_changed"]:
            print(f'{x["id"]}: {x["series"]} S{x["season"]}E{x["episode"]} => {x["kinds"]}')
    print("NOTE: detected device markers are NOT automatically verified human labels")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("init","scan","status"))
    p.add_argument("--state",type=Path,default=STATE)
    p.add_argument("--source",type=Path,default=SOURCE)
    a=p.parse_args()
    if a.action=="status":
        x=json.loads((a.state/"status.json").read_text())
        print(json.dumps({k:v for k,v in x.items() if k!="episodes"},ensure_ascii=False))
        for e in x["episodes"]:
            if e["new_or_changed"]:
                print(f'{e["id"]} {e["series"]} S{e["season"]}E{e["episode"]} {e["kinds"]}')
    else:scan(a.state,a.source,initialize=(a.action=="init"))

if __name__=="__main__":main()
