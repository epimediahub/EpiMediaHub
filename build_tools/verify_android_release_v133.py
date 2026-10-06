#!/usr/bin/env python3
"""Check regression reports and the actual public updater APK bytes."""
import concurrent.futures
import hashlib
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

expected = json.loads(Path('dist/android-latest.json').read_text())
assert expected['version'] == '1.0.33' and expected['versionCode'] == 1033
counts = {'unit_tests': 0, 'native_tests': 0, 'failures': 0, 'errors': 0}
for file in Path('reports').rglob('TEST-*.xml'):
    root = ET.parse(file).getroot()
    kind = 'native_tests' if 'androidTest-results' in str(file) else 'unit_tests'
    counts[kind] += int(root.attrib.get('tests', 0))
    for key in ('failures', 'errors'):
        counts[key] += int(root.attrib.get(key, 0))
assert counts['unit_tests'] > 150 and counts['native_tests'] >= 9, counts
assert counts['failures'] == counts['errors'] == 0, counts
print('RELEASE TESTS:', json.dumps(counts), flush=True)

base = 'https://download.epimediahub.com/android/'
headers = {'Cache-Control': 'no-cache', 'User-Agent': 'EpiMediaHub-Release-Verification/1.0.33'}
for attempt in range(30):
    try:
        request = urllib.request.Request(base + 'latest.json', headers=headers)
        with urllib.request.urlopen(request, timeout=25) as response:
            live = json.load(response)
        if live.get('version') == '1.0.33' and live.get('versionCode') == 1033:
            break
        print('Waiting for download mirror:', live.get('version'), flush=True)
    except Exception as error:
        print('Waiting for download mirror:', type(error).__name__, flush=True)
    time.sleep(5)
else:
    raise SystemExit('Public updater has not reached 1.0.33')

def check(abi):
    item = live['apks'][abi]
    pinned = expected['apks'][abi]
    assert item == pinned, abi
    assert item['url'].startswith(base + 'EpiMediaHub_Android_v1.0.33-'), abi
    digest = hashlib.sha256()
    received = 0
    with urllib.request.urlopen(urllib.request.Request(item['url'], headers=headers), timeout=45) as response:
        assert response.status == 200
        while True:
            data = response.read(1024 * 1024)
            if not data:
                break
            received += len(data)
            digest.update(data)
    assert received == item['size'] and digest.hexdigest() == item['sha256'], abi
    print('LIVE APK VERIFIED:', abi, received, digest.hexdigest(), flush=True)
    return {'abi': abi, 'bytes': received, 'sha256': digest.hexdigest(), 'http': 200}

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    verified = list(pool.map(check, expected['apks']))
report = {'version': '1.0.33', 'versionCode': 1033, 'tests': counts, 'downloads': verified}
Path('android-v1033-live-verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('LIVE UPDATER VERIFIED:', json.dumps(report), flush=True)

