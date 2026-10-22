#!/usr/bin/env python3
"""Private-safe EpiScene failure fingerprint + live code-path match.

The raw job detail and source file contents NEVER leave the server. This is
read-only; does not contact IPTV providers, mutate DBs, or restart services.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3

DB = Path('/var/lib/epimediahub/provisioning.db')
APP = Path('/opt/epimediahub/provisioning')
FILES = ('skip_analysis_worker.py','skip_scene.py','skip_remote_worker.py')
STATUS = ('failed','partial','review')
RULES = (
    ('ACCESS_OR_AUTH',r'\b401\b|\b403\b|unauthori[sz]|access.denied|access.forbidden|forbidden|permission|authenticat|credential|expired|abgelaufen|zugriff'),
    ('TOO_MANY_REQUESTS_OR_SESSIONS',r'\b429\b|rate.limit|too.many.requests|concurrent|simultaneous|parallel.connection|zu.viele.anfragen|gleichzeitig|limit.erreicht'),
    ('EXPLICIT_TIMEOUT',r'time.?out|timed.out|deadline|watchdog|time.budget|exceeded.time|zeitüberschreit|zeitlimit|abbruch.nach'),
    ('EMPTY_OR_INACCESSIBLE_STREAM',r'empty.stream|no.stream|stream.unavailable|stream.not.available|missing.stream|stream.offline|no.video|no.frames|kein.bild|keine.frames'),
    ('NO_REFERENCE_OR_MATCH',r'no.reference|no.match|missing.reference|reference.not.found|keine.referenz|kein.treffer'),
    ('DECODER_OR_MEDIA_ERROR',r'ffmpeg|ffprobe|codec|decoder|demux|invalid.data|invalid.stream|failed.to.decode'),
    ('RETRY_OR_BACKOFF',r'backoff|retry|requeue|retry.later|versuch.wiederholen|erneut.versuch|zurückgestellt'),
    ('AUDIO_OR_FINGERPRINT',r'audio|fingerprint|tonspur|waveform'),
    ('VISUAL_OR_IMAGE',r'visual|scene|frame|image|bildanalyse|bildfenster'),
    ('NETWORK',r'network|connection.reset|connection.refused|dns|host.unreachable|broken.pipe|verbindungsfehler'),
    ('LANGUAGE_OR_DISABLED',r'language|sprache|disabled|deaktiviert|archived|pausiert'),
)
COMPILED=tuple((name,re.compile(exp,re.I)) for name,exp in RULES)

def categories(value):
    if value is None or not str(value).strip():
        return ['NO_DETAIL']
    found=[name for name,regex in COMPILED if regex.search(str(value)[:8000])]
    return found or ['NO_KNOWN_CLUE']

def source_refs(text, needle):
    """Return only safe function name/line; never any source literal."""
    if not needle or len(needle)>10000:
        return []
    try:
        parsed=ast.parse(text)
    except (SyntaxError,UnicodeError):
        return []
    # Build the function map once: the live files may contain thousands of literals.
    mapping={}
    def visit(n,scope):
        for child in ast.iter_child_nodes(n):
            current=scope
            if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef)):
                current=child.name
            mapping[id(child)]=current
            visit(child,current)
    visit(parsed,'<module>')
    hits=[]
    for node in ast.walk(parsed):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.strip()==needle.strip():
            name=mapping.get(id(node),'<module>')
            if not re.fullmatch(r'[a-zA-Z_][\w]{0,90}',name):
                name='KNOWN_FUNCTION'
            hits.append({'function':name,'line':node.lineno})
    return hits[:8]

def job_stats(db, *, source_directory):
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    if not db.in_transaction:
        db.execute('BEGIN')
    def cols(table):
        return {r[1] for r in db.execute('PRAGMA table_info('+table+')')}
    expected={'skip_jobs':{'asset_key','status','detail'},
              'skip_assets':{'asset_key','playlist_id'}}
    for name,fields in expected.items():
        if not fields.issubset(cols(name)):
            raise RuntimeError('Unexpected live analysis schema: '+name)
    counts=Counter()
    keycounts={}
    classes={}
    for row in db.execute('''SELECT a.playlist_id,j.status,j.detail,COUNT(*) n
        FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
        WHERE a.playlist_id IN (8,10) AND j.status IN ('failed','partial','review')
        GROUP BY a.playlist_id,j.status,j.detail'''):
        pid=int(row['playlist_id'])
        status=row['status']
        counts[(pid,status)]+=row['n']
        key=(pid,status)
        keycounts.setdefault(key,[]).append((str(row['detail'] or ''),int(row['n'])))
        for category in categories(row['detail']):
            classes[(pid,status,category)]=classes.get((pid,status,category),0)+row['n']
    output={}
    for pid in (8,10):
        part={}
        for status in STATUS:
            details=sorted(keycounts.get((pid,status),[]),key=lambda x:-x[1])
            dominant=details[0] if details else ('',0)
            matched=[]
            for file in FILES:
                path=source_directory/file
                if not path.is_file() or path.is_symlink() or path.stat().st_size>750_000:
                    continue
                try:
                    code=path.read_text(encoding='utf-8')
                except (OSError,UnicodeError):
                    continue
                hits=source_refs(code,dominant[0])
                if hits:
                    matched.append({'file':file,'locations':hits})
            part[status]={
                'total':counts[(pid,status)],
                'different_detail_patterns':len(details),
                'most_common_pattern_repetitions':dominant[1],
                'dominant_detail_characters':len(dominant[0]),
                'dominant_detail_clues':categories(dominant[0]),
                'dominant_detail_exact_match_in_worker_literals':matched,
                'all_detail_clue_counts':{
                    cat:n for (p,s,cat),n in sorted(classes.items())
                    if p==pid and s==status
                },
            }
        output[str(pid)]=part
    return {
        'mode':'EPISCENE_PRIVATE_FAILURE_ROOT_CAUSE',
        'jobs':output,
        'summary':'Literal code match is a clue, not proof of executed branch. Unknown detail text is intentionally withheld.',
        'contains_raw_errors':False,
        'contains_titles_assets_provider_urls_or_credentials':False,
        'production_db_changed':False,
        'services_restarted':False,
        'marker_approvals_triggered':0
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--database',type=Path,default=DB)
    ap.add_argument('--code-directory',type=Path,default=APP)
    args=ap.parse_args()
    path=args.database
    if path.is_symlink() or not path.is_file():
        raise SystemExit('STOP: read-only database missing')
    if args.code_directory.is_symlink() or not args.code_directory.is_dir():
        raise SystemExit('STOP: expected worker directory missing')
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=15) as db:
        print(json.dumps(job_stats(db,source_directory=args.code_directory),indent=2,ensure_ascii=False))

if __name__=='__main__':
    main()
