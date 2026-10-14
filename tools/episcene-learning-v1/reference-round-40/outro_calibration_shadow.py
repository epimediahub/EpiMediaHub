#!/usr/bin/env python3
"""EpiScene outro onset: shadow-only, no DB writes, no verified labels or approval."""
import sqlite3, json, hashlib
from pathlib import Path
from collections import defaultdict
from statistics import median

DB=Path("/var/lib/epimediahub/provisioning.db")
ROOT=Path("/var/lib/episcene-learning/reference-round-40")
USERS={"device","manual","app","user"}
SKIP={2282}

def norm(s): return " ".join(str(s or "").casefold().split())

def fingerprint(r):
    d=[norm(r["segment_type"]),int(r["start_ms"]),int(r["end_ms"]),
       str(r["status"]),str(r["source"]),str(r["created_at"])]
    return hashlib.sha256(json.dumps(d,ensure_ascii=False).encode()).hexdigest()

def pairs(rows,plan,base):
    allowed={(norm(x["series"]),int(x["season"]),int(x["episode"]),int(x["playlist_id"])):x["id"]
             for x in plan["episodes"]}
    auto=defaultdict(list); human=defaultdict(list)
    for r in rows:
        try:
            if norm(r["segment_type"])!="outro" or norm(r["status"])=="superseded":continue
            start,end=int(r["start_ms"]),int(r["end_ms"])
            if not 0<=start<end<=86400000:continue
            key=(norm(r["title"]),int(r["season"]),int(r["episode"]),int(r["playlist_id"]))
            ref=allowed.get(key)
            if not ref:continue
            asset=str(r["asset_key"])
            if norm(r["source"]) in USERS:
                if int(r["id"]) in SKIP:continue
                before=base.get("existing_marker_signatures",{}).get(ref,{}).get(str(r["id"]))
                if before==fingerprint(r):continue
                human[(ref,asset)].append(r)
            else:auto[asset].append(r)
        except (TypeError,ValueError,KeyError):continue
    result=[]
    for (ref,asset),hs in human.items():
        if len(hs)!=1:continue
        m=hs[0]
        a_list=auto.get(asset,[])
        if not a_list:continue
        a=min(a_list,key=lambda a:abs(int(a["start_ms"])-int(m["start_ms"]))+
              abs(int(a["end_ms"])-int(m["end_ms"])))
        if abs(int(a["end_ms"])-int(m["end_ms"]))>20000:continue
        late=(int(a["start_ms"])-int(m["start_ms"]))/1000
        if abs(late)>240:continue
        result.append(dict(ref=ref,series=norm(m["title"]),season=int(m["season"]),
            episode=int(m["episode"]),playlist=int(m["playlist_id"]),method=norm(a["source"]),
            diff_s=late,manual_id=int(m["id"]),auto_id=int(a["id"])))
    return result

def evaluate(pairs):
    groups=defaultdict(list)
    for p in pairs:
        groups[(p["series"],p["season"],p["playlist"],p["method"])].append(p)
    models=[]
    for key,xs in sorted(groups.items(),key=lambda v:tuple(map(str,v[0]))):
        if len(xs)<4 or len({x["ref"] for x in xs})!=len(xs):continue
        original=[]; corrected=[]
        for holdout in xs:
            other=[p["diff_s"] for p in xs if p["ref"]!=holdout["ref"]]
            if len(other)<3:break
            original.append(abs(holdout["diff_s"]))
            corrected.append(abs(holdout["diff_s"]-median(other)))
        if len(corrected)!=len(xs):continue
        offsets=[p["diff_s"] for p in xs]
        proposed=median(offsets);mad=median(abs(v-proposed) for v in offsets)
        stable=(8<=proposed<=120 and mad<=3 and max(offsets)-min(offsets)<=10)
        models.append({"series":key[0],"season":key[1],"playlist":key[2],
           "detector":key[3],"reference_episodes":len(xs),
           "proposed_start_shift_earlier_seconds":round(proposed,3),
           "spread_seconds":round(max(offsets)-min(offsets),3),
           "median_absolute_deviation_seconds":round(mad,3),
           "median_start_error_before_seconds":round(median(original),3),
           "leave_one_out_median_start_error_after_seconds":round(median(corrected),3),
           "stable_for_further_testing":stable,"production_eligible":False,
           "reference_ids":sorted(p["ref"] for p in xs)})
    return models

def selftest():
    examples=[35.13,34.16,35.33,34.47,37.02]
    ps=[{"ref":str(i),"series":"mobland","season":1,"playlist":8,
       "method":"audio_repetition","diff_s":v} for i,v in enumerate(examples)]
    results=evaluate(ps)
    assert len(results)==1
    assert results[0]["proposed_start_shift_earlier_seconds"]==35.13
    assert results[0]["leave_one_out_median_start_error_after_seconds"]==0.76
    assert results[0]["stable_for_further_testing"] and not results[0]["production_eligible"]
    ps[0]["method"]="theintrodb";ps[1]["method"]="theintrodb"
    assert not evaluate(ps)
    print("SELFTEST_PASS: leave-one-out, detector-specific, no auto-release")

def main():
    import sys
    if sys.argv[1:]==["--self-test"]:return selftest()
    if len(sys.argv)!=1:raise SystemExit("Usage: outro_calibration_shadow.py [--self-test]")
    if DB.is_symlink() or not DB.is_file():raise RuntimeError("Original DB missing/unsafe")
    plan=json.loads((ROOT/"plan.json").read_text())
    base=json.loads((ROOT/"baseline.json").read_text())
    if len(plan.get("episodes",[]))!=40:raise RuntimeError("Invalid reference round")
    with sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True,timeout=10) as db:
        db.row_factory=sqlite3.Row;db.execute("PRAGMA query_only=ON")
        raw=[dict(r) for r in db.execute("""SELECT r.id,r.asset_key,
            COALESCE(a.title,r.title) title,COALESCE(a.season,r.season) season,
            COALESCE(a.episode,r.episode) episode,a.playlist_id,
            r.segment_type,r.start_ms,r.end_ms,r.source,r.status,r.created_at
            FROM skip_records r INNER JOIN skip_assets a ON a.asset_key=r.asset_key
            WHERE a.playlist_id IN (8,10) AND lower(r.segment_type)='outro'""")]
    refs=pairs(raw,plan,base)
    models=evaluate(refs)
    print(json.dumps({"mode":"SHADOW_ONLY","auto_publish":False,
       "verified_labels_added":0,"same_asset_outro_pairs":len(refs),
       "stability_candidates":sum(m["stable_for_further_testing"] for m in models),
       "models":models},ensure_ascii=False,indent=2))
    print("NOTE: User-attested candidate data are NOT authenticated server-approved labels.")
    print("NO changes to analyzer, app, playlists, or original database.")

if __name__=="__main__":main()
