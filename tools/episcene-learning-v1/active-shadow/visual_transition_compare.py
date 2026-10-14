#!/usr/bin/env python3
"""Compare EpiScene shadow MobLand outro image signatures against human boundaries.

Exploratory visual similarity only. No semantic credits verification or autoapproval.
Original analyzer, reference and shadow capture databases are all opened read-only.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path
from statistics import median

import visual_progress_report as progress

KEYS=("brightness_shift","contrast_shift","motion_change","immediate_frame_change")
# Small scale floors prevent the distance of an invariant (e.g. same frame
# across a true boundary) from dividing by zero. These are not acceptance gates.
SCALE_FLOORS=(5.0,5.0,0.025,0.05)


def distance(candidate, others):
    center={k:median(float(x[k]) for x in others) for k in KEYS}
    mad={k:median(abs(float(x[k])-center[k]) for x in others) for k in KEYS}
    normalized={}
    for i,k in enumerate(KEYS):
        normalized[k]=round(abs(float(candidate[k])-center[k]) /
                            max(SCALE_FLOORS[i],mad[k]*1.4826),3)
    return round(sum(normalized.values())/len(KEYS),3),normalized


def assess(observed):
    allrows=observed["results"]
    refs=[r for r in allrows if r["kind"]=="reference" and r["status"]=="VISUAL_HASHES_READY"]
    cands=[r for r in allrows if r["kind"]=="candidate" and r["status"]=="VISUAL_HASHES_READY"]
    result={
        "mode":"SHADOW_DESCRIPTIVE_COMPARISON",
        "reference_ready":len(refs),"reference_expected":sum(r["kind"]=="reference" for r in allrows),
        "candidate_ready":len(cands),"candidate_expected":sum(r["kind"]=="candidate" for r in allrows),
        "source_capture_complete":observed["completed"]==observed["expected_targets"],
        "missing_or_stale_record_ids":observed["pending_ids"],
        "new_verified_labels":0,"new_auto_approvals":0,
        "production_changes":0,
        "scope":"MobLand S1 playlist 8; start-boundary image hashes only",
        "qualification":"Fingerprint statistics do not identify credits. A large or small signature distance is NOT a decision to skip, approve, or release.",
    }
    if len(refs)<3:
        result["status"]="WAITING_FOR_AT_LEAST_3_REFERENCE_WINDOWS"
        result["candidates"]=[{"id":r["id"],"status":"WAITING_FOR_REFERENCE_PROFILE"} for r in cands]
        return result
    center={k:round(median(float(x[k]) for x in refs),4) for k in KEYS}
    loocv=[]
    for r in refs:
        others=[x for x in refs if x["id"]!=r["id"]]
        score,_=distance(r,others)
        loocv.append(score)
    result["status"]="COMPARISON_AVAILABLE" if cands else "WAITING_FOR_CANDIDATE_WINDOWS"
    result["reference_feature_medians"]=center
    result["reference_leave_one_out_distance_median"]=round(median(loocv),3)
    result["reference_leave_one_out_distance_range"]=[min(loocv),max(loocv)]
    result["reference_ids"]=[r["id"] for r in refs]
    result["candidates"]=[]
    for c in cands:
        value,features=distance(c,refs)
        result["candidates"].append({
            "id":c["id"],
            "distance_from_reference_profile":value,
            "normalized_feature_differences":features,
            "visual_similarity_only":True,
            "credits_start_verified":False,
            "eligible_for_automatic_release":False,
        })
    result["candidates"].sort(key=lambda x:-x["distance_from_reference_profile"])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original',type=Path,default=progress.ORIGINAL)
    p.add_argument('--shadow',type=Path,default=progress.SOURCE)
    p.add_argument('--captures',type=Path,default=progress.CAPTURE)
    args=p.parse_args()
    for path in (args.original,args.shadow):
        if not path.is_file() or path.is_symlink():
            raise SystemExit("Missing/unexpected source database path")
    if args.captures.is_symlink():
        raise SystemExit("Unexpected capture database symlink")
    captures=None
    try:
        with sqlite3.connect(args.original.resolve().as_uri()+'?mode=ro',uri=True) as src, \
             sqlite3.connect(args.shadow.resolve().as_uri()+'?mode=ro',uri=True) as sh:
            if args.captures.is_file():
                captures=sqlite3.connect(args.captures.resolve().as_uri()+'?mode=ro',uri=True)
            status=progress.compare(src,sh,captures)
        print(json.dumps(assess(status),ensure_ascii=False,indent=2))
    finally:
        if captures:captures.close()


if __name__=="__main__":
    main()
