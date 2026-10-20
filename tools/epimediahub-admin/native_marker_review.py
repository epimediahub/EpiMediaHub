"""Gated native EpiScene review via the ORIGINAL Flask marker business handler.

No guessed SQL mutations or direct marker writes. Read-only queue only for
dedicated analysis playlist IDs 8 and 10. Existing web_auth, skip csrf,
review_record, history, proposal retirement and job wakeup remain authoritative.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
import re
import secrets
import sqlite3
import textwrap
import uuid

from flask import current_app, session

from native_management_actions import _device_lock
from native_legacy_bridge import _journal_file,_claim
from native_management_data import SchemaUnavailable

LANES=(8,10)
SESSION_KEY=re.compile(r"^[A-Za-z_][A-Za-z0-9_]{1,79}$")


class MarkerReviewUnavailable(RuntimeError):
    pass


def _original():
    handler=current_app.view_functions.get("v082_skip_review")
    if not callable(handler):
        raise MarkerReviewUnavailable("existing EpiScene review handler unavailable")
    return handler


def _csrf_key(handler):
    checker=handler.__globals__.get("csrf")
    if not callable(checker):
        raise MarkerReviewUnavailable("original review csrf unavailable")
    try:
        source=textwrap.dedent(inspect.getsource(checker))
        tree=ast.parse(source)
    except (OSError,TypeError,SyntaxError):
        raise MarkerReviewUnavailable("unverified review csrf source") from None
    keys=[]
    for item in ast.walk(tree):
        if not isinstance(item,ast.Call):
            continue
        f=item.func
        if (isinstance(f,ast.Attribute) and f.attr=="get"
            and isinstance(f.value,ast.Name) and f.value.id=="session"
            and item.args and isinstance(item.args[0],ast.Constant)
            and isinstance(item.args[0].value,str)):
            keys.append(item.args[0].value)
    if len(keys)!=1 or not SESSION_KEY.fullmatch(keys[0]):
        raise MarkerReviewUnavailable("unsupported review csrf contract")
    return keys[0]


def csrf_token():
    """Re-use EXACT original session key; never override another login guard."""
    handler=_original()
    name=_csrf_key(handler)
    saved=session.get(name)
    if not isinstance(saved,str) or len(saved)<32:
        saved=secrets.token_urlsafe(32)
        session[name]=saved
    return saved


def _connection(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file():
        raise SchemaUnavailable("missing EpiScene database")
    con=sqlite3.connect(p.resolve().as_uri()+"?mode=ro",
                        uri=True,timeout=8)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    expected={
        "skip_records":{"id","asset_key","segment_type","start_ms","end_ms","status"},
        "skip_assets":{"asset_key","playlist_id","title","season","episode"},
    }
    for table,fields in expected.items():
        available={row[1] for row in con.execute("PRAGMA table_info("+table+")")}
        if not fields<=available:
            con.close()
            raise SchemaUnavailable("incompatible original EpiScene schema")
    return con


def list_pending(path,before_id=None):
    if before_id is not None and (type(before_id) is not int or not 0<before_id<2**63):
        raise ValueError("invalid cursor")
    cursor=before_id if before_id is not None else 2**63-1
    con=_connection(path)
    try:
        rows=con.execute("""SELECT r.id,r.segment_type,r.start_ms,r.end_ms,
                               a.playlist_id,a.title,a.season,a.episode
               FROM skip_records r JOIN skip_assets a
                    ON a.asset_key=r.asset_key
               WHERE r.status='pending' AND a.playlist_id IN (8,10)
                     AND r.id<?
               ORDER BY r.id DESC LIMIT 101""",(cursor,)).fetchall()
        values=[]
        for row in rows[:100]:
            start,end=row["start_ms"],row["end_ms"]
            if (type(start) is not int or type(end) is not int
                    or not 0<=start<end<=86_400_000
                    or row["segment_type"] not in ("intro","outro","recap")):
                continue
            title=row["title"]
            if not isinstance(title,str) or not title.strip():
                continue
            values.append({
                "id":str(row["id"]),
                "playlist":("4K ANALYSE" if row["playlist_id"]==8 else "THE BEST"),
                "title":title.strip()[:150],
                "season":int(row["season"] or 0),
                "episode":int(row["episode"] or 0),
                "kind":row["segment_type"],
                "start_ms":start,
                "end_ms":end
            })
        return {"markers":values,"has_more":len(rows)>100,
                "next_before_id":str(rows[99]["id"]) if len(rows)>100 else None,
                "scope":"pending_analysis_markers_8_10_only"}
    finally:
        con.close()


def _status(path,identifier):
    con=_connection(path)
    try:
        row=con.execute("""SELECT r.status
            FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
            WHERE r.id=? AND a.playlist_id IN (8,10)""",
            (identifier,)).fetchone()
        return row["status"] if row is not None else None
    finally:
        con.close()


def invoke_review(path,identifier,decision,form):
    if decision not in ("approve","reject") or type(identifier) is not int or (
        not 0<identifier<2**63):
        raise ValueError("invalid marker")
    if set(form)!={"decision","csrf","confirm","request_id"} or (
        form.get("decision")!=decision or form.get("confirm")!="true"):
        raise ValueError("invalid review fields")
    key=form["request_id"]
    if not isinstance(key,str) or str(uuid.UUID(key))!=key:
        raise ValueError("invalid review request id")
    if form["csrf"]!=csrf_token():
        raise ValueError("original EpiScene csrf mismatch")
    handler=_original()
    with _device_lock(path,identifier,"episcene-review"):
        with _journal_file(path) as journal:
            previous=_claim(journal,key,"marker-"+decision,identifier)
            if previous is not None:
                return previous
            if _status(path,identifier)!="pending":
                return {"applied":False,"error":"marker_not_pending"},409
            # The existing Flask handler rechecks web auth + original EpiScene
            # session CSRF, parses the original times, updates skip_records and
            # maintains marker/proposal/audit history. No direct SQL mutation here.
            handler(identifier)
            if _status(path,identifier)!=("approved" if decision=="approve" else "rejected"):
                return {"applied":False,"error":"review_not_confirmed"},409
            journal.execute("UPDATE requests SET state='applied',result_id=? WHERE request_id=?",
                            (identifier,key))
            journal.commit()
            return {"applied":True,"id":str(identifier),"decision":decision},200
