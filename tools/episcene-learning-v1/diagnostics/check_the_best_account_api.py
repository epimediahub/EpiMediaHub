#!/usr/bin/env python3
"""Read-only account metadata test for the dedicated THE BEST analysis line.

Checks the standard Xtream player_api.php login result without opening
any video stream, sharing credentials, or writing production state.
"""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE=Path('/opt/epimediahub/analysis')
DATABASE=Path('/var/lib/epimediahub/provisioning.db')
PREVIOUS=Path('/tmp/episcene-range-check.py')
MAX_JSON_BYTES=32768

def load_previous():
    if PREVIOUS.is_symlink() or not PREVIOUS.is_file():
        raise RuntimeError('STOP_PREVIOUS_SAFE_IDLE_HELPER_MISSING')
    spec=importlib.util.spec_from_file_location('episcene_safe_idle',str(PREVIOUS))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not callable(getattr(mod,'idle',None)):
        raise RuntimeError('STOP_SAFE_IDLE_HELPER_INVALID')
    return mod

@contextmanager
def readonly_db():
    with sqlite3.connect(DATABASE.resolve().as_uri()+'?mode=ro',uri=True,timeout=8) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        yield db

def request_account(analysis, url):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with analysis._provider_proxy_local(url,lambda:False) as proxy:
            try:
                req=urllib.request.Request(proxy,method='GET',headers={'Accept':'application/json'})
                with opener.open(req,timeout=8) as response:
                    status=response.status
                    data=response.read(MAX_JSON_BYTES+1)
            except urllib.error.HTTPError as error:
                code=error.code
                error.close()
                if code==502:
                    raise ValueError('analysis_failed') from None
                return {'api_result':'LOCAL_HTTP_'+str(code)}
    except analysis.ProviderFailure as error:
        reason=str(error)
        return {'api_result': reason.upper() if re.fullmatch(
            r'provider_http_[1-5][0-9]{2}|provider_timeout|provider_dns|provider_tls|provider_connection',
            reason) else 'PROVIDER_OTHER'}
    if status!=200:
        return {'api_result':'HTTP_'+str(status)}
    if len(data)>MAX_JSON_BYTES:
        return {'api_result':'API_RESPONSE_EXCEEDS_32KB'}
    try:
        decoded=json.loads(data)
        info=decoded['user_info']
    except (ValueError,TypeError,KeyError):
        return {'api_result':'HTTP_200_NOT_STANDARD_XTREAM_ACCOUNT_JSON'}
    if not isinstance(info,dict):
        return {'api_result':'HTTP_200_UNEXPECTED_ACCOUNT_SHAPE'}
    valid_auth=info.get('auth') in (1,'1',True)
    status_value=str(info.get('status','')).casefold()
    status_labels={'active':'ACTIVE','expired':'EXPIRED','disabled':'DISABLED','banned':'BANNED','trial':'TRIAL'}
    state=status_labels.get(status_value,'UNKNOWN')
    def safe_count(field):
        raw=str(info.get(field,''))
        return int(raw) if re.fullmatch(r'[0-9]{1,3}',raw) and int(raw)<=100 else 'NOT_REPORTED'
    return {
        'api_result':'XTREAM_ACCOUNT_RESPONSE',
        'auth':'ACCEPTED' if valid_auth else 'NOT_ACCEPTED',
        'account_status':state,
        'active_connections':safe_count('active_cons'),
        'maximum_connections':safe_count('max_connections')
    }

def main():
    if DATABASE.is_symlink() or not DATABASE.is_file() or BASE.is_symlink() or not BASE.is_dir():
        raise RuntimeError('STOP_EXPECTED_DEPLOYMENT_MISSING')
    sys.path.insert(0,str(BASE))
    import skip_analysis as analysis
    from skip_analysis_accounts import using
    idle=load_previous()
    with idle.idle():
        with using(readonly_db):
            with readonly_db() as db:
                row=db.execute("SELECT * FROM skip_analysis_playlists WHERE id=10 AND archived=0").fetchone()
                if row is None:raise RuntimeError('STOP_THE_BEST_ANALYSIS_LINE_UNAVAILABLE')
            cfg=analysis.configured_source(row)
            parts=urllib.parse.urlsplit(cfg['xtream_server'])
            # Paths in this project must be bare Xtream server roots.
            if parts.path not in ('','/'):
                raise RuntimeError('STOP_UNEXPECTED_SERVER_PATH')
            api_url=cfg['xtream_server'].rstrip('/')+'/player_api.php?'+urllib.parse.urlencode({
                'username':cfg['xtream_username'],'password':cfg['xtream_password']})
            result=request_account(analysis,api_url)
    print('THE_BEST_API_CHECK:',json.dumps(result,sort_keys=True))
    print('NO_MEDIA_STREAM_OPENED; NO_DATABASE_OR_MARKER_CHANGES')

if __name__=='__main__':
    try:main()
    except Exception as error:
        safe=str(error) if str(error).startswith('STOP_') else 'UNEXPECTED_'+type(error).__name__
        print('SAFE_STOP:',safe)
        raise SystemExit(1)
