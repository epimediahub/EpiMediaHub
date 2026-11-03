#!/usr/bin/env python3
"""Read-only function-level compatibility audit of live EpiScene release code.

Compares the previous reviewed public source, proposed public source, and
private installed source by AST *without exporting source code, string constants,
secrets, URLs or customer data*. Does not change any files or permissions.
A green audit is NEVER deployment authorization; service/DB/stream safety,
manifest, backups, installer and rollback are separate required gates.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

LIVE = Path("/opt/episcene-learning/safe_release_rollout_v2.py")
MAX_CODE_BYTES = 2_000_000
ALLOWED = frozenset({
    "function:protected",
    "function:collect",
    "function:plan",
    "assignment:MAX_NEW_PER_RUN",
    "assignment:MAX_DAILY",
    "assignment:MAX_PER_PLAYLIST",
    "assignment:MAX_PER_FAMILY_PER_RUN",
    "assignment:MAX_PER_FAMILY_PER_DAY",
})
CORE = frozenset({"function:protected","function:collect","function:plan"})
NEW_CONFIG = frozenset({
    "assignment:MAX_PER_FAMILY_PER_RUN",
    "assignment:MAX_PER_FAMILY_PER_DAY",
})


def parse_file(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>MAX_CODE_BYTES:
        raise ValueError("SOURCE_MISSING_OR_UNEXPECTED")
    src=p.read_bytes()
    try:
        tree=ast.parse(src.decode("utf-8"))
    except (SyntaxError,UnicodeError) as error:
        raise ValueError("INVALID_PYTHON_SOURCE") from error
    return tree,hashlib.sha256(src).hexdigest()[:16]


def index(tree):
    """Index only named top-level functions and simple constant assignments."""
    result={}
    for node in tree.body:
        label=None
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            label="function:"+node.name
        elif isinstance(node,ast.Assign) and len(node.targets)==1:
            target=node.targets[0]
            if isinstance(target,ast.Name):
                label="assignment:"+target.id
        elif isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name):
            label="assignment:"+node.target.id
        if label:
            if label in result:
                raise ValueError("DUPLICATED_TOP_LEVEL_DEFINITION")
            result[label]=hashlib.sha256(
                ast.dump(node,include_attributes=False).encode("utf-8")
            ).hexdigest()
    return result


def audit(baseline,candidate,live):
    base,base_hash=parse_file(baseline)
    new,new_hash=parse_file(candidate)
    installed,live_hash=parse_file(live)
    old=index(base);proposed=index(new);actual=index(installed)
    diff={name for name in set(old)|set(proposed)
          if old.get(name)!=proposed.get(name)}
    if not CORE <= diff or not diff <= ALLOWED:
        raise ValueError("UNRECOGNIZED_PUBLIC_PATCH_SCOPE")
    if not NEW_CONFIG <= (set(proposed)-set(old)):
        raise ValueError("UNEXPECTED_NEW_CONFIG_SHAPE")
    if not CORE <= set(actual):
        raise ValueError("MISSING_INSTALLED_REQUIRED_FUNCTIONS")
    status={};overlaps=[];missing=[]
    for name in sorted(diff):
        a=old.get(name);b=proposed.get(name);current=actual.get(name)
        if current==b:
            state="CANDIDATE_ALREADY_PRESENT"
        elif a is not None and current==a:
            state="SAFE_TO_MERGE_IN_PRINCIPLE"
        elif a is None and current is None:
            state="NEW_CONFIG_NOT_YET_INSTALLED"
        elif current is None:
            state="EXPECTED_COMPONENT_ABSENT"
            missing.append(name)
        else:
            state="CUSTOM_LIVE_MODIFICATION_REQUIRES_REVIEW"
            overlaps.append(name)
        status[name]=state
    # Report if other installed functions differ, but never include the
    # function source or any private values. The installer must preserve them.
    untouched={name for name in old if name not in diff}
    custom_preserved=sum(old.get(name)!=actual.get(name) for name in untouched)
    return {
        "mode":"EPISCENE_PUBLIC_DIFF_VS_PRIVATE_LIVE_READ_ONLY",
        "live_sha16":live_hash,
        "baseline_sha16":base_hash,
        "candidate_sha16":new_hash,
        "proposed_changed_entries":status,
        "overlapping_changes_requiring_review":overlaps,
        "missing_expected_components":missing,
        "other_live_custom_entries_to_preserve_count":custom_preserved,
        "limited_function_level_merge_looks_possible":not overlaps and not missing,
        "requires_explicit_reviewed_installer_before_any_deployment":True,
        "deployment_authorized":False,
        "provider_requests":0,"production_writes":0,"service_restarts":0,
        "marker_approvals":0,"private_source_exported":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--baseline",type=Path,required=True)
    p.add_argument("--candidate",type=Path,required=True)
    p.add_argument("--installed",type=Path,default=LIVE)
    args=p.parse_args()
    try:
        print(json.dumps(audit(args.baseline,args.candidate,args.installed),
                         sort_keys=True,indent=2))
    except (ValueError,OSError) as exc:
        print(json.dumps({"mode":"EPISCENE_MERGE_AUDIT_READ_ONLY",
                          "status":"STOP_REVIEW_REQUIRED",
                          "reason":str(exc),
                          "deployment_authorized":False},sort_keys=True))
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
