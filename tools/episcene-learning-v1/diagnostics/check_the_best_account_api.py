#!/usr/bin/env python3
"""Read-only account metadata test for an EpiScene analysis playlist.

Checks the standard Xtream player_api.php login result without opening
any video stream, sharing credentials, or writing production state.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
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
    with closing(sqlite3.connect(DATABASE.resolve().as_uri()+'?mode=ro',uri=True,timeout=8)) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        yield db

@contextmanager
def regular_slot(lane):
    path = DATABASE.with_name('skip-analysis.lock')
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('STOP_ANALYSIS_LOCK_MISSING')
    with path.open('rb') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f'{lane} | Warte auf den regulären Analyseslot ...', flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def request_account(analysis, url, *, proxy=None, busy=None):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    if proxy is None:
        proxy = analysis._provider_proxy_local
    if busy is None:
        busy = lambda: False
    if busy():
        return {'api_result':'ANALYSIS_DEFERRED'}
    try:
        with proxy(url,busy) as relay_url:
            try:
                req=urllib.request.Request(relay_url,method='GET',headers={'Accept':'application/json'})
                with opener.open(req,timeout=8) as response:
                    status=response.status
                    data=response.read(MAX_JSON_BYTES+1)
            except urllib.error.HTTPError as error:
                code=error.code
                error.close()
                if code==502:
                    raise ValueError('analysis_failed') from None
                return {'api_result':'LOCAL_HTTP_'+str(code)}
    except (analysis.ProviderFailure, ValueError) as error:
        reason=str(error)
        if reason == 'analysis_deferred':
            return {'api_result':'ANALYSIS_DEFERRED'}
        return {'api_result': reason.upper() if re.fullmatch(
            r'provider_http_[1-5][0-9]{2}|provider_timeout|provider_dns|provider_tls|provider_connection',
            reason) else 'PROVIDER_OTHER'}
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        return {'api_result': 'HTTP_' + str(code)}
    except OSError:
        return {'api_result': 'CONNECTION_ERROR'}
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
    raw_auth = info.get('auth')
    if raw_auth in (1, '1'):
        auth = 'ACCEPTED'
    elif raw_auth in (0, '0'):
        auth = 'NOT_ACCEPTED'
    else:
        auth = 'NOT_REPORTED'
    status_value=str(info.get('status','')).casefold()
    status_labels={'active':'ACTIVE','expired':'EXPIRED','disabled':'DISABLED','banned':'BANNED','trial':'TRIAL'}
    state=status_labels.get(status_value,'UNKNOWN')
    def safe_count(field):
        raw=str(info.get(field,''))
        return int(raw) if re.fullmatch(r'[0-9]{1,3}',raw) and int(raw)<=100 else 'NOT_REPORTED'
    result = {
        'api_result':'XTREAM_ACCOUNT_RESPONSE',
        'auth':auth,
        'account_status':state,
        'active_connections':safe_count('active_cons'),
        'maximum_connections':safe_count('max_connections')
    }
    expiry = str(info.get('exp_date', ''))
    if re.fullmatch(r'[1-9][0-9]{8,9}', expiry):
        result['expires_utc'] = datetime.fromtimestamp(int(expiry), timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    return result

def main(playlist_id=None):
    legacy = playlist_id is None
    lane = 10 if legacy else playlist_id
    label = {8:'4K ANALYSE', 10:'THE BEST'}[lane]
    if DATABASE.is_symlink() or not DATABASE.is_file() or (legacy and (BASE.is_symlink() or not BASE.is_dir())):
        raise RuntimeError('STOP_EXPECTED_DEPLOYMENT_MISSING')
    if legacy:
        sys.path.insert(0, str(BASE))
    else:
        sys.path[:0] = ['/opt/epimediahub/provisioning', '/opt/episcene-learning/unified']
    import skip_analysis as analysis
    from skip_analysis_accounts import using
    slot = load_previous().idle() if legacy else regular_slot(label)
    with slot:
        with using(readonly_db):
            with readonly_db() as db:
                row=db.execute("SELECT * FROM skip_analysis_playlists WHERE id=? AND archived=0", (lane,)).fetchone()
                if row is None:
                    raise RuntimeError('STOP_THE_BEST_ANALYSIS_LINE_UNAVAILABLE' if legacy else 'STOP_PLAYLIST_UNAVAILABLE')
                if not legacy:
                    from skip_analysis_accounts import unavailable
                    if lane in unavailable(db):
                        print(f'{label} | Analysezugang lokal pausiert oder nicht verfügbar.')
                        return
            cfg=analysis.configured_source(row)
            parts=urllib.parse.urlsplit(cfg['xtream_server'])
            if legacy and parts.path not in ('','/'):
                raise RuntimeError('STOP_UNEXPECTED_SERVER_PATH')
            if (parts.scheme not in ('http','https') or not parts.hostname or parts.username is not None
                    or parts.query or parts.fragment):
                raise RuntimeError('STOP_INVALID_CONFIGURED_SERVER')
            username, password = cfg['xtream_username'], cfg['xtream_password']
            if not username or not password:
                raise RuntimeError('STOP_CONFIGURED_LOGIN_INCOMPLETE')
            endpoint = parts.path.rstrip('/')
            if not endpoint.endswith('/player_api.php'):
                endpoint += '/player_api.php'
            query = urllib.parse.urlencode({'username': username, 'password': password})
            api_url = urllib.parse.urlunsplit((parts.scheme,parts.netloc,endpoint,query,''))
            if legacy:
                result=request_account(analysis,api_url)
            else:
                from skip_analysis_worker import busy_check
                result=request_account(analysis,api_url,proxy=analysis.provider_proxy,busy=busy_check(readonly_db,[row]))
    if legacy:
        print('THE_BEST_API_CHECK:',json.dumps(result,sort_keys=True))
        print('NO_MEDIA_STREAM_OPENED; NO_DATABASE_OR_MARKER_CHANGES')
    elif result['api_result'] == 'XTREAM_ACCOUNT_RESPONSE':
        print(f"{label} | Anbieter-Login {result['auth']} | Konto {result['account_status']} | "
              f"Verbindungen {result['active_connections']}/{result['maximum_connections']} | "
              f"Ablauf {result.get('expires_utc', 'nicht gemeldet')}")
    else:
        print(f"{label} | Konto-API | {result['api_result']}")

if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--playlist', type=int, choices=(8,10), help='Analyse-Playlist im regulären Analyseslot prüfen')
    try:main(parser.parse_args().playlist)
    except Exception as error:
        safe=str(error) if str(error).startswith('STOP_') else 'UNEXPECTED_'+type(error).__name__
        print('SAFE_STOP:',safe)
        raise SystemExit(1)
