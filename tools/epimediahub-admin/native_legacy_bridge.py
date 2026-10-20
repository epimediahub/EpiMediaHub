"""Strict native JSON bridge to existing production admin handlers.

This module intentionally never recreates the business SQL. The legacy Flask
handlers remain the authority. Only known, redacted-AST-audited form inputs
are accepted, and an independent DB postcondition must prove success.

The replay journal is intentionally fail-closed. A crash between invoking a
legacy handler and recording its result leaves the UUID pending; repeating
that UUID cannot execute a second write. An operator must reconcile it.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid

from flask import current_app, request

from native_management_actions import _device_lock
from native_management_data import SchemaUnavailable

# 2026-10-20 redacted production flow audit. No guessed playlist form keys.
ACTIONS = {
    "create-customer": ("v070_create_customer", ("name",)),
    "create-reseller": ("v080_create_reseller", (
        "name", "username", "password", "branding_name", "customer_limit",
        "device_limit"
    )),
    "rename-device": ("v074_rename_device", ("name",)),
    "sync-device": ("v070_sync_device", ()),
    "move-device": ("v070_move_device", ("customer_id",)),
    "assign-reseller": ("v080_assign_customer_reseller", ("reseller_id",)),
    "delete-playlist": ("v076_delete_customer_playlist", ()),
    "add-playlist": ("v076_add_customer_playlist", (
        "playlist_name", "playlist_type", "playlist_url", "xtream_server",
        "xtream_username", "xtream_password", "xtream_output"
    )),
    "edit-playlist": ("v076_update_customer_playlist", (
        "playlist_name", "playlist_type", "playlist_url", "xtream_server",
        "xtream_username", "xtream_password", "xtream_output"
    )),
}
CREATE_ACTIONS = {"create-customer", "create-reseller"}
IDENTIFIER = re.compile(r"^[1-9][0-9]{0,17}$")
NAME = re.compile(r"^[^\x00-\x1f\x7f<>]{1,120}$")
USERNAME = re.compile(r"^[a-zA-Z0-9_.-]{3,60}$")


class LegacyUnavailable(RuntimeError):
    pass


def _safe_name(value):
    if not isinstance(value, str):
        raise ValueError("invalid name")
    value = value.strip()
    if not NAME.fullmatch(value):
        raise ValueError("invalid name")
    return value


def _number(value, optional=False):
    if optional and value == "":
        return None
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("invalid id")
    number = int(value)
    if number >= 2**63:
        raise ValueError("id out of range")
    return number


def _fields(action, values):
    if action not in ACTIONS:
        raise ValueError("action unavailable")
    if set(values) != set(ACTIONS[action][1]) | {"request_id", "confirm"}:
        raise ValueError("unexpected form fields")
    if values["confirm"] != "true":
        raise ValueError("explicit confirmation required")
    key = values["request_id"]
    if not isinstance(key, str) or len(key) > 50:
        raise ValueError("invalid request id")
    try:
        if str(uuid.UUID(key)) != key:
            raise ValueError("invalid request id")
    except (TypeError, ValueError, AttributeError):
        raise ValueError("invalid request id")
    fields = {}
    if "name" in ACTIONS[action][1]:
        fields["name"] = _safe_name(values["name"])
    if action == "create-reseller":
        login = values["username"].strip().lower()
        if not USERNAME.fullmatch(login):
            raise ValueError("invalid reseller username")
        passwd = values["password"]
        if not isinstance(passwd, str) or not 8 <= len(passwd) <= 256:
            raise ValueError("invalid reseller password")
        branding = values["branding_name"].strip()
        if branding and (not NAME.fullmatch(branding) or len(branding) > 120):
            raise ValueError("invalid branding")
        fields.update(username=login, password=passwd, branding_name=branding)
        for item in ("customer_limit", "device_limit"):
            v = values[item]
            if not isinstance(v, str) or not v.isascii() or not v.isdecimal():
                raise ValueError("invalid limit")
            limit = int(v)
            if limit > 100000:
                raise ValueError("limit too high")
            fields[item] = str(limit)
    if action == "move-device":
        fields["customer_id"] = str(_number(values["customer_id"]))
    if action == "assign-reseller":
        dest = _number(values["reseller_id"], optional=True)
        fields["reseller_id"] = str(dest) if dest is not None else ""
    return key, fields


def _read(path, query, params=()):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise SchemaUnavailable("provisioning database unavailable")
    con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True, timeout=6)
    try:
        con.execute("PRAGMA query_only=ON")
        return con.execute(query, params).fetchall()
    finally:
        con.close()


def _snapshot(path, action, identifier, fields):
    if action == "create-customer":
        return int(_read(path, "SELECT COALESCE(MAX(id),0) FROM customers")[0][0])
    if action == "create-reseller":
        duplicates = _read(path, "SELECT id FROM resellers WHERE username=?",
                           (fields["username"],))
        if duplicates:
            raise ValueError("username already exists")
        return int(_read(path, "SELECT COALESCE(MAX(id),0) FROM resellers")[0][0])
    if action == "delete-playlist":
        rows = _read(path,
            "SELECT id FROM customer_playlists WHERE id=?", (identifier,))
    elif action == "rename-device":
        rows = _read(path, "SELECT display_name FROM devices WHERE id=?", (identifier,))
    elif action == "sync-device":
        rows = _read(path, "SELECT config_version FROM devices WHERE id=?", (identifier,))
    elif action == "move-device":
        rows = _read(path, "SELECT customer_id FROM devices WHERE id=?", (identifier,))
        if not _read(path, "SELECT id FROM customers WHERE id=?",
                     (int(fields["customer_id"]),)):
            raise ValueError("destination customer unavailable")
    elif action == "assign-reseller":
        rows = _read(path, "SELECT reseller_id FROM customers WHERE id=?", (identifier,))
        if fields["reseller_id"] and not _read(
            path, "SELECT id FROM resellers WHERE id=?", (int(fields["reseller_id"]),)
        ):
            raise ValueError("destination reseller unavailable")
    else:
        raise ValueError("unsupported action")
    if not rows:
        raise ValueError("entity unavailable")
    value = rows[0][0]
    if action == "rename-device" and value == fields["name"]:
        raise ValueError("unchanged name")
    if action == "move-device" and value == int(fields["customer_id"]):
        raise ValueError("unchanged customer")
    if action == "assign-reseller":
        new = int(fields["reseller_id"]) if fields["reseller_id"] else None
        if value == new:
            raise ValueError("unchanged reseller")
    return value


def _postcondition(path, action, identifier, fields, previous):
    if action == "create-customer":
        rows = _read(path,
            "SELECT id FROM customers WHERE id>? AND name=? ORDER BY id",
            (previous, fields["name"]))
        return int(rows[0][0]) if len(rows) == 1 else None
    if action == "create-reseller":
        rows = _read(path,
            "SELECT id FROM resellers WHERE id>? AND name=? AND username=?",
            (previous, fields["name"], fields["username"]))
        return int(rows[0][0]) if len(rows) == 1 else None
    if action == "delete-playlist":
        rows = _read(path,
            "SELECT id FROM customer_playlists WHERE id=?", (identifier,))
        return identifier if not rows else None
    if action == "rename-device":
        rows = _read(path, "SELECT display_name FROM devices WHERE id=?", (identifier,))
        return identifier if rows and rows[0][0] == fields["name"] else None
    if action == "sync-device":
        rows = _read(path, "SELECT config_version FROM devices WHERE id=?", (identifier,))
        before = previous if isinstance(previous, int) else -1
        return identifier if rows and isinstance(rows[0][0], int) and rows[0][0] > before else None
    if action == "move-device":
        rows = _read(path, "SELECT customer_id FROM devices WHERE id=?", (identifier,))
        return identifier if rows and rows[0][0] == int(fields["customer_id"]) else None
    if action == "assign-reseller":
        rows = _read(path, "SELECT reseller_id FROM customers WHERE id=?", (identifier,))
        dest = int(fields["reseller_id"]) if fields["reseller_id"] else None
        return identifier if rows and rows[0][0] == dest else None
    return None


@contextmanager
def _journal_file(path):
    root = Path(path).parent / "admin-mobile"
    if root.is_symlink():
        raise LegacyUnavailable("unsafe journal folder")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = root.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise LegacyUnavailable("journal folder must be private")
    journal = root / "native-legacy-requests.sqlite3"
    if journal.is_symlink():
        raise LegacyUnavailable("unsafe journal file")
    old_umask = os.umask(0o077)
    try:
        con = sqlite3.connect(journal, timeout=7)
    finally:
        os.umask(old_umask)
    try:
        info = journal.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077):
            raise LegacyUnavailable("journal must be private")
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=6000")
        con.execute("""CREATE TABLE IF NOT EXISTS requests (
            request_id TEXT PRIMARY KEY, action TEXT NOT NULL,
            entity_id INTEGER NOT NULL, state TEXT NOT NULL,
            result_id INTEGER, created_at TEXT NOT NULL
        )""")
        yield con
    finally:
        con.close()


def _claim(journal, request_id, action, identifier):
    row = journal.execute(
        "SELECT action,entity_id,state,result_id FROM requests WHERE request_id=?",
        (request_id,)).fetchone()
    if row:
        if (row["action"], row["entity_id"]) != (action, identifier):
            return {"applied":False,"error":"request_id_conflict"},409
        if row["state"] == "applied":
            return {"applied":True,"replayed":True,
                    "id":str(row["result_id"])},200
        return {"applied":False,"error":"unconfirmed_prior_request"},409
    journal.execute("""INSERT INTO requests
        (request_id,action,entity_id,state,result_id,created_at)
        VALUES (?,?,?,'pending',NULL,?)""",
        (request_id,action,identifier,datetime.now(timezone.utc).isoformat()))
    journal.commit()
    return None


def invoke_legacy(path, action, identifier, submitted):
    if action not in ACTIONS:
        raise ValueError("unsupported action")
    if type(identifier) is not int or identifier < 0 or identifier >= 2**63:
        raise ValueError("invalid entity id")
    if (identifier == 0) != (action in CREATE_ACTIONS):
        raise ValueError("invalid action id")
    request_id, fields = _fields(action, submitted)
    handler = current_app.view_functions.get(ACTIONS[action][0])
    if not callable(handler):
        raise LegacyUnavailable("audited legacy business handler is missing")
    # The endpoint receives URL-encoded form fields directly, ensuring that
    # the original legacy handler sees exactly the same request.form values.
    # No replacement of request contexts, session, or SQL is performed.
    for key, value in fields.items():
        if request.form.get(key) != value:
            raise ValueError("noncanonical request fields")
    with _device_lock(path, identifier, "legacy-"+action):
        with _journal_file(path) as journal:
            prior = _claim(journal, request_id, action, identifier)
            if prior is not None:
                return prior
            try:
                previous = _snapshot(path,action,identifier,fields)
            except ValueError:
                journal.execute("UPDATE requests SET state='rejected' WHERE request_id=?",
                                (request_id,))
                journal.commit()
                raise
            # The legacy business handler enforces its own validation,
            # auditing, quotas, migration and device config propagation.
            # A redirect or flash is never itself considered successful.
            arg_names = {
                "rename-device":"device_id", "sync-device":"device_id",
                "move-device":"device_id", "assign-reseller":"customer_id",
                "delete-playlist":"playlist_id",
            }
            handler(**({} if action in CREATE_ACTIONS else
                {arg_names[action]:identifier}))
            result_id = _postcondition(path,action,identifier,fields,previous)
            if result_id is None:
                # Maybe original handler rejected the request; never retry
                # blindly with this request UUID.
                return {"applied":False,"error":"not_confirmed"},409
            journal.execute(
                "UPDATE requests SET state='applied',result_id=? WHERE request_id=?",
                (result_id,request_id))
            journal.commit()
            return {"applied":True,"id":str(result_id),"action":action},200
