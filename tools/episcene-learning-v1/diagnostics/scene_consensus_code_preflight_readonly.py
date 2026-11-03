#!/usr/bin/env python3
"""EpiScene scene-consensus control-flow preflight (no imports or DB writes).

Read deployed source AST and report bounded structural evidence useful for
planning a cached-window re-evaluation without weakening approval gates.
Never prints source code, SQL, provider addresses, or identifiers.
"""
import ast
import hashlib
from pathlib import Path

ROOT=Path('/opt/epimediahub/provisioning')
FILES=('skip_scene.py','skip_release.py','skip_automation.py')
FUNCTIONS={
 'skip_scene.py':('analyze','_cached_rows','release_ready','capture','_window','validate_result','_consensus'),
 'skip_release.py':('scene_release_ready','accept_pending','approve_rows'),
 'skip_automation.py':('accept_pending','save_window','cached_window')
}
WATCH=('analyze','_cached_rows','release_ready','capture','validate_result',
       'scene_release_ready','accept_pending')
CALLEE_ALLOWLIST={
  'analyze','_cached_rows','_window','capture','release_ready','validate_result',
  'consensus','store_proposal','publish','accept_pending','approve_rows',
  'current_reference','requests','execute','fetchone','fetchall',
  'cached_window','save_window','_compare','_similarity','_match',
  'detector_windows','audio_windows','detect','score','_visual_consensus'
}

def report_file(name):
    path=ROOT/name
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(name+' unavailable or symlink')
    data=path.read_bytes()
    if len(data)>3000000:raise RuntimeError('Unexpected oversized source '+name)
    source=ast.parse(data.decode('utf-8'),filename=name)
    top=[x for x in source.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))]
    print('\n'+name)
    print('  sha256_16:',hashlib.sha256(data).hexdigest()[:16])
    for fn in FUNCTIONS[name]:
        matches=[n for n in top if n.name==fn]
        if len(matches)!=1:
            print('  '+fn+':','missing' if not matches else 'duplicate')
            continue
        node=matches[0]
        args=[a.arg for a in node.args.posonlyargs+node.args.args+node.args.kwonlyargs]
        print('  '+fn+'_line:',node.lineno)
        print('  '+fn+'_size_lines:',node.end_lineno-node.lineno+1)
        print('  '+fn+'_args:',','.join(args)[:150])
        if fn not in WATCH:continue
        called=[]
        for n in ast.walk(node):
            if not isinstance(n,ast.Call):continue
            f=n.func
            callee=f.id if isinstance(f,ast.Name) else f.attr if isinstance(f,ast.Attribute) else '?'
            if callee in CALLEE_ALLOWLIST:
                called.append(callee)
        print('  '+fn+'_recognized_calls:',','.join(sorted(set(called)))[:200] or 'none')
        if fn in ('analyze','release_ready','scene_release_ready'):
            refs=set()
            for n in ast.walk(node):
                if not isinstance(n,ast.Constant) or not isinstance(n.value,str):continue
                s=n.value
                for marker in ('episcene_consensus','AUTO_CONFIRMED','REVIEW',
                               'skip_scene_windows','skip_scene_window_versions',
                               'visual','confidence','boundaries_consistent',
                               'skip_auto_windows','approved','pending','superseded'):
                    if marker in s: refs.add(marker)
            print('  '+fn+'_tokens_present:',','.join(sorted(refs)) or 'none')
    return

def main():
    print('EPISCENE SCENE CONSENSUS CODE PREFLIGHT / NUR LESEN')
    print('AST metadata only, no production modules imported, no provider calls.')
    for name in FILES:report_file(name)
    print('NO RESTARTS, NO RELEASES, NO DB CHANGES')

if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,UnicodeDecodeError,SyntaxError) as e:
        print('PREFLIGHT_STOP:',type(e).__name__,str(e)[:160])
        raise SystemExit(1)
