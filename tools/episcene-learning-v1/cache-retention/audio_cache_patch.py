#!/usr/bin/env python3
"""Patch only the verified legacy 256-row EpiScene audio cache prune call.

Release gates and the catalogue's necessary changed-media invalidation remain
untouched. This is intentionally a fail-closed source-to-source transformation.
"""
from __future__ import annotations

import ast
import hashlib

LEGACY_SQL = (
    "DELETE FROM skip_auto_windows WHERE rowid NOT IN ("
    "SELECT rowid FROM skip_auto_windows ORDER BY created_at DESC LIMIT 256)"
)
HELPER_NAME = "episcene_prune_audio_window_cache"
PATCH_ID = "episcene-audio-pinned-retention-v1"
HELPER = '''def episcene_prune_audio_window_cache(con):
    """Retain all pending-proposal evidence plus a bounded unpinned LRU tail.

    Retention, not authorization: never approve, requeue, or alter markers.
    Skip cleanup if the evidence table is not trustworthy.
    """
    import json as _episcene_json

    _target = 8192
    _slack = 512
    _min_unpinned = 1024
    _count = con.execute("SELECT COUNT(*) FROM skip_auto_windows").fetchone()[0]
    if _count <= _target + _slack:
        return

    _pinned = set()
    _records = con.execute(
        "SELECT r.segment_type, e.evidence_json FROM skip_records r "
        "LEFT JOIN skip_auto_evidence e ON e.record_id=r.id "
        "WHERE r.status='pending'"
    ).fetchall()
    for _kind, _raw in _records:
        # Fail CLOSED if some proposal's evidence cannot be inspected.
        if _raw is None:
            continue
        try:
            _ev = _episcene_json.loads(_raw)
        except (ValueError, TypeError):
            return
        if not isinstance(_ev, dict):
            return
        _items = _ev.get('windows')
        if _items is None:
            continue
        if not isinstance(_items, list):
            return
        for _item in _items:
            if not isinstance(_item, dict):
                return
            if _item.get('origin', 'server') != 'server':
                continue
            _key = _item.get('asset_key')
            if not isinstance(_key, str) or not _key:
                return
            _pinned.add((_key, _kind))

    _rows = con.execute(
        "SELECT rowid, asset_key, kind FROM skip_auto_windows "
        "ORDER BY created_at DESC, rowid DESC"
    ).fetchall()
    _actual_pinned = sum(
        1 for _rowid, _asset, _kind in _rows if (_asset, _kind) in _pinned
    )
    _keep_unpinned = max(_min_unpinned, _target - _actual_pinned)
    _seen_unpinned = 0
    _victims = []
    for _rowid, _asset, _kind in _rows:
        if (_asset, _kind) in _pinned:
            continue
        _seen_unpinned += 1
        if _seen_unpinned > _keep_unpinned:
            _victims.append((_rowid,))
    if _victims:
        con.executemany(
            "DELETE FROM skip_auto_windows WHERE rowid=?",
            _victims
        )


'''

def patch(source: str) -> tuple[str, bool]:
    if not isinstance(source, str):
        raise ValueError('Expected UTF-8 Python source')
    if PATCH_ID in source:
        tree = ast.parse(source)
        if len([x for x in tree.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
                and x.name == HELPER_NAME]) != 1:
            raise ValueError('Partially installed cache patch')
        return source, False

    tree = ast.parse(source)
    fn = [x for x in tree.body if isinstance(x, ast.FunctionDef)
          and x.name == 'save_window']
    if len(fn) != 1:
        raise ValueError('Expected exactly one save_window function')
    targets = []
    for node in ast.walk(fn[0]):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if len(call.args) != 1 or not isinstance(call.args[0], ast.Constant):
            continue
        if call.args[0].value == LEGACY_SQL:
            targets.append(node)
    if len(targets) != 1:
        raise ValueError('Legacy cache cleanup differs; refusing blind patch')
    if any(isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
           and x.name == HELPER_NAME for x in tree.body):
        raise ValueError('Unexpected existing cache helper')
    target = targets[0]
    lines = source.splitlines(keepends=True)
    start = target.lineno - 1
    end = target.end_lineno
    original = ''.join(lines[start:end])
    if not original.strip().startswith('con.execute(') or not original.strip().endswith(')'):
        raise ValueError('Legacy prune statement has unsupported layout')
    indentation = original[:len(original) - len(original.lstrip())]
    ending = '\n' if original.endswith('\n') else ''
    lines[start:end] = [indentation + HELPER_NAME + '(con)' + ending]
    insert_at = fn[0].lineno - 1
    lines[insert_at:insert_at] = [
        '# ' + PATCH_ID + '\n',
        HELPER,
        '\n',
    ]
    updated = ''.join(lines)
    compile(updated, '<episcene-cache-patched>', 'exec')
    if updated.count(HELPER_NAME+'(con)') != 2:
        raise ValueError('Unexpected patched helper call count')
    return updated, True


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
