#!/usr/bin/env python3
"""Find the production branch producing repeated EpiScene job failures.

Read-only. No raw job details, tokens, URLs, asset names, source text, or
individual IDs are emitted. Only allowlisted technical words and validated
source locations are printed.
"""
from __future__ import annotations
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3

DB=Path('/var/lib/epimediahub/provisioning.db')
ROOT=Path('/opt/epimediahub/provisioning')
MODULES=('skip_analysis_worker.py','skip_remote_worker.py','skip_scene.py','skip_schedule.py')
STATUSES=('failed','partial','review')
WORDS=frozenset("""
abbruch abgebrochen abgelaufen abgelehnt ablehnung abspielen aktiv anfragen anbieter
anwendung arbeit audio aufnahme ausgabe ausstehend automatischen
bearbeitung berechtigung beschränkt bild bildanalyse bildfenster bilder blockiert
cached cache connection connections concurrent corrupted dauer decode decoder
denied detail download empty ende endpoint error expired failed failure fehler
fehlende fehlenden fehlt fehlgeschlagen files fingerprint finished fertig frame
frames forbidden freigabe gefunden gestartet gesperrt grenze gültig hash
http import invalid job jobs kein keine keinen konnte können laufzeit lesen
limit limited locked login match matching maximale max memory meta metadata
missing nicht no offline open out of parallel partial permission playlist
provider queued rate read reference references rejected release remote request
requests resource retry review running scheduler scene schema segment server
session sessions skip source sourcekey sqlite start status stop stream streaming
success synchronisierung temporär temporary time timeout timed token too
unable unavailable unreachable unsupported update ungültig verbindung
verbindungen verbot verboten verarbeitet verarbeitung versuch video visual
vorhanden wait waiting warning watchdog worker zeit zeitlimit zugang
zugriff zurückgewiesen zurückgestellt überschritten überlastet
auth authentication authorization batch chapter client clips code connect
database db duration ffmpeg ffprobe httpstatus invalid login marker markers
network not open queue quota refused response result scan segment selected
service setup session state stream timeout too many requests denied access
paused retryable disabled account network stream source failed
""".split())

def allowlisted(detail):
    scrubbed=re.sub(r'(?i)\b(?:[a-z][a-z0-9+.-]*://|www\.)\S+', ' ', str(detail or ''))
    scrubbed=re.sub(r'(?i)\b(?:[a-z0-9-]+\.)+[a-z]{2,24}(?:/\S+)?', ' ', scrubbed)
    words=re.findall(r'[^\W\d_]+',scrubbed.casefold(),flags=re.UNICODE)
    return [word for word in words if word in WORDS][:24]

def function_map(tree):
    scopes={}
    def walk(node, scope='<module>'):
        for child in ast.iter_child_nodes(node):
            current=child.name if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef)) else scope
            scopes[id(child)]=current
            walk(child,current)
    walk(tree)
    return scopes

def make_pattern(nodes):
    parts=[]; fixed=0
    for n in nodes:
        if isinstance(n,ast.Constant) and isinstance(n.value,str):
            fixed+=len(n.value.strip())
            parts.append(re.escape(n.value))
        elif isinstance(n,ast.FormattedValue):
            parts.append(r'.{0,350}')
    if fixed<12: return None
    try:return re.compile(''.join(parts),re.S|re.I)
    except re.error:return None

def sites(source, needle, filename):
    """Matches literals and f-string templates without exporting source text."""
    if not needle or len(needle)>2000:return []
    try:tree=ast.parse(source)
    except SyntaxError:return []
    scopes=function_map(tree)
    items=[]
    for node in ast.walk(tree):
        method=None
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value.strip())>=12:
            if node.value.strip()==needle.strip():
                method='EXACT_LITERAL'
        elif isinstance(node,ast.JoinedStr):
            pat=make_pattern(node.values)
            if pat is not None and pat.fullmatch(needle):
                method='FORMATTED_TEMPLATE'
        if method is None:continue
        fn=scopes.get(id(node),'<module>')
        # Restrict output to code-shaped function names only.
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9]{0,63}|<module>',fn):
            fn='<unknown>'
        items.append(dict(file=filename,function=fn,line=node.lineno,match=method))
    return items[:8]

def database_report(db, code_directory):
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    if not db.in_transaction:db.execute('BEGIN')
    cols=lambda t:{r[1] for r in db.execute('PRAGMA table_info('+t+')')}
    if not {'asset_key','status','detail'}.issubset(cols('skip_jobs')) or not {
            'asset_key','playlist_id'}.issubset(cols('skip_assets')):
        raise RuntimeError('Unexpected production schema')
    details={}
    for r in db.execute('''SELECT a.playlist_id,j.status,j.detail,COUNT(*) n
        FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
        WHERE a.playlist_id IN (8,10) AND j.status IN ('failed','partial','review')
        GROUP BY a.playlist_id,j.status,j.detail'''):
        details.setdefault((r['playlist_id'],r['status']),[]).append(
            (str(r['detail'] or ''),int(r['n'])))
    sources={}
    for f in MODULES:
        path=code_directory/f
        if not path.is_file() or path.is_symlink() or path.stat().st_size>750000:
            continue
        try:sources[f]=path.read_text(encoding='utf-8')
        except (OSError,UnicodeError):pass
    result={}
    for pid in (8,10):
        result[str(pid)]={}
        for status in STATUSES:
            patterns=sorted(details.get((pid,status),[]),key=lambda t:(-t[1],t[0]))
            dominant,n=patterns[0] if patterns else ('',0)
            locations=[]
            for f,source in sources.items():
                locations+=sites(source,dominant,f)
            result[str(pid)][status]=dict(
                total=sum(x[1] for x in patterns),
                distinct_reasons=len(patterns),
                dominant_count=n,
                dominant_length=len(dominant),
                dominant_sha256_prefix=hashlib.sha256(dominant.encode()).hexdigest()[:12] if dominant else None,
                allowlisted_technical_words=allowlisted(dominant),
                corresponding_source_locations=locations[:12]
            )
    return dict(mode='EPISCENE_LOCAL_FAILURE_TEMPLATE_TRIAGE',
                source_files_read=list(sources),
                jobs=result,
                root_cause_proven=False,
                note='No raw details or source text leave this host. A template match is a lead, not an executed stack trace.',
                database_modified=False,service_restarted=False,markers_released=0)

def main():
    if DB.is_symlink() or not DB.is_file() or ROOT.is_symlink() or not ROOT.is_dir():
        raise SystemExit('STOP: expected local EpiScene deployment missing')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=15) as con:
        print(json.dumps(database_report(con,ROOT),indent=2,ensure_ascii=False))

if __name__=='__main__':main()
