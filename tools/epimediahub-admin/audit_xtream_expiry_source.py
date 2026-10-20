#!/usr/bin/env python3
"""Read-only proof of where provider expiry actually originates on Hetzner.

Exports only aggregate provider TYPE counts, safe config KEY names and names
of source modules/functions that reference expiry fields. Never exports a
customer, playlist URL, Xtream username/password, device ID, or row ID.
"""
from __future__ import annotations
import ast
from collections import Counter,defaultdict
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

BASE=Path("/opt/epimediahub/provisioning")
DATABASE=Path("/var/lib/epimediahub/provisioning.db")
OUTPUT=Path("/root/epimediahub-xtream-ablauf-quellen.json")
KEY=re.compile(r"^[A-Za-z_][A-Za-z_0-9-]{0,55}$")
FUNC=re.compile(r"^[A-Za-z_][A-Za-z_0-9]{0,70}$")
KNOWN_FIELDS={"exp_date","user_info","expires_at","expiration","expiry",
              "player_api.php","xtream","Xtream"}

def inspect_database(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("database unavailable")
    types=Counter()
    keys=defaultdict(Counter)
    expiry_keys=defaultdict(Counter)
    with sqlite3.connect(path.resolve().as_uri()+"?mode=ro",
                         uri=True,timeout=12) as db:
        db.execute("PRAGMA query_only=ON")
        cols={r[1] for r in db.execute(
            "PRAGMA table_info(customer_playlists)")}
        if not {"config_json","enabled"} <= cols:
            raise ValueError("customer playlist schema not verified")
        rows=db.execute("""SELECT config_json FROM customer_playlists
            WHERE enabled=1 LIMIT 10001""").fetchall()
        if len(rows)>10000:
            raise ValueError("too many records for safe inventory")
        for (raw,) in rows:
            try:
                config=json.loads(raw or "{}")
            except (TypeError,ValueError):
                config={}
            if not isinstance(config,dict):
                config={}
            kind=config.get("type")
            if not isinstance(kind,str) or kind.upper() not in {"M3U","XTREAM"}:
                kind="OTHER_OR_UNKNOWN"
            else:
                kind=kind.upper()
            types[kind]+=1
            for key,value in config.items():
                if not isinstance(key,str) or not KEY.fullmatch(key):
                    continue
                keys[kind][key]+=1
                if key.lower() in {"exp_date","expires_at","expiration","expiry"}:
                    expiry_keys[kind][key]+=int(value not in (None,"","0",0))
    return {
        "active_playlist_type_counts":dict(sorted(types.items())),
        "config_key_presence_counts":{t:dict(sorted(c.items())) for t,c in sorted(keys.items())},
        "expiry_value_presence_counts":{t:dict(sorted(c.items())) for t,c in sorted(expiry_keys.items())},
        "total_active_playlists":sum(types.values()),
        "private_values_exported":False
    }

def source_refs(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("source unavailable")
    out=[]
    files=sorted(root.glob("*.py"))
    if len(files)>500:
        raise ValueError("too many source files")
    for file in files:
        if file.is_symlink() or file.stat().st_size>2000000:
            continue
        tree=ast.parse(file.read_text(encoding="utf-8",errors="replace"))
        refs=[]
        for n in ast.walk(tree):
            if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                continue
            if not FUNC.fullmatch(n.name):
                continue
            hit=False
            for part in ast.walk(n):
                if isinstance(part,ast.Constant) and isinstance(part.value,str):
                    if any(field.lower() in part.value.lower() for field in KNOWN_FIELDS):
                        hit=True
                        break
            if hit:
                refs.append(n.name)
        if refs:
            out.append({"module":file.name,"functions":sorted(set(refs))[:30]})
    return out[:100]

def main():
    if os.geteuid()!=0:
        raise ValueError("root-only read audit")
    result={
        "format":"epimediahub-xtream-provider-expiry-source-v1",
        "scope":"aggregate counts, source symbol names and config key names only",
        "data":inspect_database(DATABASE),
        "provider_related_functions":source_refs(BASE)
    }
    raw=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if len(raw)>150000:
        raise ValueError("report too large")
    flags=os.O_CREAT|os.O_TRUNC|os.O_WRONLY
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(OUTPUT,flags,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        os.fchmod(f.fileno(),0o600)
        f.write(raw)
    print("XTREAM_EXPIRY_SOURCE_AUDIT_READY")
    print("OUTPUT="+str(OUTPUT))
    print("CUSTOMER_NAMES_OR_PROVIDER_CREDENTIALS_EXPORTED=false")

if __name__=="__main__":
    try:
        main()
    except (OSError,ValueError,sqlite3.Error,SyntaxError,RuntimeError):
        print("XTREAM_EXPIRY_SOURCE_AUDIT_FAILED")
        sys.exit(2)
