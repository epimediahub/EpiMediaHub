#!/usr/bin/env python3
"""Patch *specific functions*, not a fragile whole-file revision fingerprint.

The live analyzer has accumulated independent performance fixes. Adapt only
the SQL inside three existing scene functions and the optional outro visual
search start. Refuse any unknown query shape before writing production code.
Approval gates and all other functions are byte-for-byte preserved.
"""
from __future__ import annotations
import ast
import re

OLD_JOIN=("JOIN customer_playlists p ON p.id=a.playlist_id "
          "JOIN customers c ON c.id=p.customer_id AND c.enabled=1")
NEW_JOIN=("JOIN skip_analysis_playlists p ON p.id=a.playlist_id "
          "AND p.archived=0")
OLD_PLAYLIST="SELECT * FROM customer_playlists WHERE id=?"
NEW_PLAYLIST="SELECT * FROM skip_analysis_playlists WHERE id=?"
OLD_WINDOW="        begin, end = audio[0]['start_ms'] - 6000, audio[0]['end_ms'] + 6000"
NEW_WINDOW="""        # Human postprocessing found that some actual end credits begin
        # significantly before a high-confidence audio repetition. Expand
        # the *visual inspection* window only; do not shift or approve a marker.
        begin, end = audio[0]['start_ms'] - 6000, audio[0]['end_ms'] + 6000
        if kind == 'outro':
            begin -= 55000"""

_JOIN_RE=re.compile(
    r"JOIN\s+customer_playlists\s+p\s+ON\s+p\.id\s*=\s*a\.playlist_id"
    r"\s+JOIN\s+customers\s+c\s+ON\s+c\.id\s*=\s*p\.customer_id"
    r"\s+AND\s+c\.enabled\s*=\s*1"
)
_SELECT_RE=re.compile(
    r"SELECT\s+\*\s+FROM\s+customer_playlists\s+WHERE\s+id\s*=\s*\?"
)
_ANALYSIS_RE=re.compile(r"JOIN\s+skip_analysis_playlists\s+p\s+ON\s+p\.id\s*=\s*a\.playlist_id")
_ARCHIVED_RE=re.compile(r"p\.archived\s*=\s*0")
_AUDIO_RE=re.compile(
    r"^([ \t]+)(begin,\s*end\s*=\s*audio\[0\]\['start_ms'\]\s*-\s*6000"
    r"\s*,\s*audio\[0\]\['end_ms'\]\s*\+\s*6000)[ \t]*$",
    re.MULTILINE
)


def source_shape(source):
    """Safe structural counts for failure diagnostics (no source lines/credentials)."""
    try:
        tree=ast.parse(source)
        names={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    except SyntaxError:
        names=set()
    return {k:{
        'function_present':k in names,
        'old_customer_joins':source.count(OLD_JOIN) if k=='_cached_rows' else None
    } for k in ('capture','_cached_rows','release_ready','analyze')}


def _target_functions(source):
    lines=source.splitlines(keepends=True)
    parsed=ast.parse(source)
    nodes={}
    for node in parsed.body:
        if isinstance(node,ast.FunctionDef):
            if node.name in nodes:
                raise ValueError('Multiple top-level functions with the same name')
            nodes[node.name]=node
    wanted=('capture','_cached_rows','release_ready','analyze')
    if not all(k in nodes for k in wanted):
        absent=[k for k in wanted if k not in nodes]
        raise ValueError('Missing expected visual functions: '+','.join(absent))
    return lines,nodes


def _join(text,method):
    matches=list(_JOIN_RE.finditer(text))
    if len(matches)==1:
        result=_JOIN_RE.sub(NEW_JOIN,text,count=1)
        if _JOIN_RE.search(result):
            raise ValueError('Customer join still present: '+method)
        return result,True
    if matches:
        raise ValueError('Ambiguous customer JOIN count in '+method)
    # Already converted is safe only when this function uses the independent
    # analysis inventory AND excludes archived sources.
    if (_ANALYSIS_RE.search(text) and _ARCHIVED_RE.search(text)
            and not re.search(r'JOIN\s+customer_playlists\b',text)):
        return text,False
    raise ValueError('Unrecognized playlist JOIN in '+method)


def _capture(text):
    hits=list(_SELECT_RE.finditer(text))
    if len(hits)==1:
        return _SELECT_RE.sub(NEW_PLAYLIST,text,count=1),True
    if hits:
        raise ValueError('Ambiguous customer-playlist lookup in capture')
    if (re.search(r'FROM\s+skip_analysis_playlists\s+WHERE\s+id\s*=\s*\?',text)
            or re.search(r'\banalysis_playlist\s*\(',text)):
        return text,False
    raise ValueError('Unrecognized capture playlist resolution')


def _analyze(text):
    # The audio window is strictly a read scope, never a proposed marker
    # time. Existing audio-window tweaks must not be clobbered.
    if 'begin -= 55000' in text and "if kind == 'outro':" in text:
        return text,False
    candidates=list(_AUDIO_RE.finditer(text))
    if len(candidates)==1:
        if not re.search(r'(?m)^[ \t]*if audio:[ \t]*$',text):
            raise ValueError('Unexpected audio-condition shape; no time-window change')
        match=candidates[0]
        indent=match.group(1)
        original=match.group(2)
        replacement=(
            indent+'# Expand the visual inspection 55s earlier for outro only; no approval or time shift\n'
            +indent+original+'\n'
            +indent+"if kind == 'outro':\n"
            +indent+'    begin -= 55000')
        return text[:match.start()]+replacement+text[match.end():],True
    if len(candidates)>1:
        raise ValueError('Ambiguous audio search assignment in analyze')
    # Existing customized search logic is preserved. Crucially, the SQL
    # repair can still go live without overwriting other performance patches.
    return text,False


def patch(source):
    lines,nodes=_target_functions(source)
    stages={}
    flags={}
    for name in ('capture','_cached_rows','release_ready','analyze'):
        node=nodes[name]
        block=''.join(lines[node.lineno-1:node.end_lineno])
        if name=='capture':
            updated,modified=_capture(block)
        elif name in ('_cached_rows','release_ready'):
            updated,modified=_join(block,name)
        else:
            updated,modified=_analyze(block)
        stages[name]=(node.lineno-1,node.end_lineno,updated)
        flags[name]=modified
    updated=list(lines)
    # Apply bottom-up to preserve the original AST line ranges.
    for start,end,block in sorted(stages.values(),key=lambda x:-x[0]):
        replacement=block.splitlines(keepends=True)
        if updated[end-1].endswith('\n') and not replacement[-1].endswith('\n'):
            replacement[-1]+='\n'
        updated[start:end]=replacement
    patched=''.join(updated)
    ast.parse(patched)
    patched_lines,patched_nodes=_target_functions(patched)
    for name in ('_cached_rows','release_ready'):
        node=patched_nodes[name]
        block=''.join(patched_lines[node.lineno-1:node.end_lineno])
        if re.search(r'JOIN\s+customer_playlists\b',block):
            raise ValueError('Unconverted legacy customer source join in '+name)
    # Verify no other functions changed: parse ASTs and compare all untouched
    # top-level definitions (including other security/auto-release functions).
    initial=ast.parse(source)
    final=ast.parse(patched)
    before={n.name:ast.dump(n,include_attributes=False)
            for n in initial.body if isinstance(n,ast.FunctionDef)
            and n.name not in stages}
    after={n.name:ast.dump(n,include_attributes=False)
           for n in final.body if isinstance(n,ast.FunctionDef)
           and n.name not in stages}
    if before!=after:
        raise ValueError('Unexpected change outside allowlisted scene functions')
    return patched,patched!=source


if __name__=='__main__':
    raise SystemExit('Import and call patch(); this helper never writes a file.')
