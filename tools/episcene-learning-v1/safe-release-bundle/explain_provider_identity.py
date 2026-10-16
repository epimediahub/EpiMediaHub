#!/usr/bin/env python3
"""Read-only reason breakdown for old EpiScene provider-key mismatches.

No URLs, usernames, passwords, source keys, asset keys, titles or customer IDs
are printed. This tool does not approve markers, access the network or write
to either EpiScene database. The production resolver is used only to rederive
an ephemeral provider asset hash and compare it with the stored asset key.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

DB=Path('/var/lib/epimediahub/provisioning.db')
CODE=Path('/opt/epimediahub/provisioning')
MAX_ITEMS=250_000
EXTENSIONS={'mp4','mkv','m4v','avi','ts','mpeg','mpg'}


def reason(record, source_url, provider_asset_key):
    stream=record['mapped_stream']
    extension=record['mapped_extension']
    config=record['config_json']
    if not isinstance(stream,str) or not re.fullmatch(r'[0-9]{1,12}',stream):
        return 'STREAM_ID_UNUSABLE'
    if extension not in EXTENSIONS:
        return 'EXTENSION_UNSUPPORTED'
    if not isinstance(config,str) or not config.strip():
        return 'ANALYSIS_PROVIDER_CONFIG_UNAVAILABLE'
    try:
        actual=provider_asset_key(
            source_url({'config_json':config},record),record['media_type']
        )
    except (TypeError,ValueError,KeyError,IndexError,AttributeError):
        return 'PROVIDER_RESOLVER_REJECTED'
    except Exception:
        # Do not leak exception text: may contain credential-bearing URL.
        return 'PROVIDER_RESOLVER_ERROR'
    return 'MATCH' if actual==record['asset_key'] else 'PROVIDER_IDENTITY_CHANGED'


def audit(con, source_url, provider_asset_key):
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    con.execute('BEGIN')
    rows=con.execute("""
        SELECT r.id,r.asset_key,r.media_type,r.source_key,r.season,r.episode,
               r.duration_ms,r.title,r.start_ms,r.end_ms,r.segment_type,r.disabled,
               r.device_id,r.customer_id,
               a.playlist_id,a.asset_key AS matched_asset,a.media_type AS asset_media,
               a.source_key AS asset_source,a.season AS asset_season,
               a.episode AS asset_episode,a.duration_ms AS asset_duration,
               a.title AS asset_title,
               a.stream_id AS mapped_stream,a.extension AS mapped_extension,
               d.customer_id AS device_owner,d.enabled AS device_active,
               c.enabled AS customer_active,
               p.customer_id AS customer_playlist_owner,
               ap.id AS analysis_playlist,ap.archived AS analysis_archived,
               ap.config_json,ss.enabled AS analysis_source_on
        FROM skip_records r
        LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
        LEFT JOIN devices d ON d.id=r.device_id
        LEFT JOIN customers c ON c.id=d.customer_id
        LEFT JOIN customer_playlists p ON p.id=a.playlist_id
        LEFT JOIN skip_analysis_playlists ap ON ap.id=a.playlist_id
        LEFT JOIN skip_analysis_sources ss ON ss.playlist_id=a.playlist_id
        WHERE r.status='pending' AND r.source='device'
        ORDER BY r.id LIMIT ?
    """,(MAX_ITEMS+1,)).fetchall()
    if len(rows)>MAX_ITEMS:
        raise RuntimeError('STOP: Unexpectedly large manual backlog')
    outcomes=Counter()
    eligible_proof=Counter()
    for raw in rows:
        record=dict(raw)
        if record['id']==2282:
            outcomes['KNOWN_INVALID_REFERENCE']+=1
            continue
        if (record['device_id'] is None or record['customer_id'] is None
            or record['device_active']!=1 or record['customer_active']!=1
            or record['device_owner']!=record['customer_id']
            or record['matched_asset'] is None):
            outcomes['MISSING_VERIFIABLE_DEVICE_OR_ASSET']+=1
            continue
        owned=record['customer_playlist_owner']==record['customer_id']
        independent=(record['playlist_id'] in (8,10)
                     and record['customer_playlist_owner'] is None
                     and record['analysis_playlist']==record['playlist_id']
                     and record['analysis_archived']==0
                     and record['analysis_source_on']==1)
        if not (owned or independent):
            outcomes['NO_ACTIVE_OWNED_OR_ANALYSIS_SOURCE']+=1
            continue
        if (record['source_key']!=record['asset_source']
            or record['media_type']!=record['asset_media']
            or record['season']!=record['asset_season']
            or record['episode']!=record['asset_episode']
            or not isinstance(record['asset_title'],str)
            or not isinstance(record['title'],str)
            or record['asset_title'].strip().casefold()!=record['title'].strip().casefold()
            or not isinstance(record['asset_duration'],int)
            or not isinstance(record['duration_ms'],int)
            or abs(record['asset_duration']-record['duration_ms'])>500):
            outcomes['EPISODE_OR_DURATION_CHANGED']+=1
            continue
        # We do not claim these rows can be released: conflicting / protected
        # decisions and timing checks remain the original production guards.
        result=reason(record,source_url,provider_asset_key)
        outcomes[result]+=1
        if result=='PROVIDER_IDENTITY_CHANGED':
            eligible_proof['stable_episode_fields_still_match']+=1
    return dict(
        mode='READ_ONLY_PROVIDER_IDENTITY_CLASSIFICATION',
        pending=len(rows),
        counts=dict(sorted(outcomes.items())),
        provider_identity_mismatch_with_same_episode_metadata=
            eligible_proof['stable_episode_fields_still_match'],
        provider_urls_or_credentials_printed=False,
        marker_approvals=0, database_changes=0,
        note='A provider hash mismatch alone is NOT proof that the '
             'underlying video is unchanged. No marker may be published '
             'without independent content verification.'
    )


def main():
    if not DB.is_file() or DB.is_symlink():
        raise RuntimeError('STOP: production database missing or symlink')
    if str(CODE) not in sys.path:
        sys.path.insert(0,str(CODE))
    from skip_analysis import source_url,provider_asset_key
    uri=DB.resolve().as_uri()+'?mode=ro'
    with sqlite3.connect(uri,uri=True,timeout=20) as con:
        result=audit(con,source_url,provider_asset_key)
    print(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False))


if __name__=='__main__':
    main()
