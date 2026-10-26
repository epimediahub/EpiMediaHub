#!/usr/bin/env python3
"""Read-only smoke check of real public APIs; prints summaries, never raw data."""
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SAMPLES = [
    ('Breaking Bad', 'tt0903747', 1396), ('Dark', 'tt5753856', 70523),
    ('Suits', 'tt1632701', 37680), ('Stranger Things', 'tt4574334', 66732),
    ('Game of Thrones', 'tt0944947', 1399), ('The Office (US)', 'tt0386676', 2316),
]


def read(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'EpiMediaHub/1.0.15 Android', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read(300_000))
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None


def inspect(sample):
    name, imdb, tmdb = sample
    base = f'https://api.theintrodb.org/v3/media?tmdb_id={tmdb}&season=1&episode=1'
    versions = read(base + '&list_versions=true') or {}
    known = [v for v in versions.get('versions', []) if v.get('duration_ms', 0) > 0]
    duration = max(known, key=lambda v: v.get('submission_count', 0))['duration_ms'] if known else None
    result = {'series': name, 'known_versions': len(known), 'duration_ms': duration, 'providers': {}}
    if not duration:
        return result
    urls = {
        'SkipDB': f'https://api.skipdb.tv/api/segments?imdb_id={imdb}&season=1&episode=1&duration={duration // 1000}&adjust=none',
        'TheIntroDB': base + f'&duration_ms={duration}&merge_unknown=false',
        'IntroDB': f'https://api.introdb.app/segments?imdb_id={imdb}&season=1&episode=1',
    }
    for provider, url in urls.items():
        data = read(url)
        if data is None:
            result['providers'][provider] = {'available': False}
            continue
        if provider == 'SkipDB':
            segments = data.get('segments', {})
            exact = [key for key, value in segments.items() if value and value.get('match') == 'exact' and value.get('confidence', 0) >= .85]
        else:
            exact = [key for key in ('intro', 'recap', 'credits', 'outro') if data.get(key)]
        result['providers'][provider] = {'available': True, 'segment_types_returned': exact}
    return result


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(inspect, SAMPLES))
    print(json.dumps({'samples': results}, ensure_ascii=False, indent=2))
