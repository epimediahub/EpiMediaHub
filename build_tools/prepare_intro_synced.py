#!/usr/bin/env python3
"""Lock the new soundtrack heartbeat to actual V5 visual pulse frames."""
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
manifest = json.loads((repo / 'android/v1.0.64/orchestral_samples.json').read_text())
samples = repo / '.ci-intro-samples'
samples.mkdir(exist_ok=True)
for name, expected in manifest['files'].items():
    path = samples / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        url = 'https://raw.githubusercontent.com/sgossner/VSCO-2-CE/' + manifest['commit'] + '/' + urllib.parse.quote(name)
        with urllib.request.urlopen(url, timeout=30) as response:
            path.write_bytes(response.read())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name

original = repo / 'android/v1.0.61/epimedia_intro_v5.mp4'
assert hashlib.sha256(original.read_bytes()).hexdigest() == '4b3556a5da85560f2c2668f6a32b6cdafef220b535b16ae6f807684817350a51'
target = repo / 'android/v1.0.65/epimedia_intro_v7.mp4'
target.parent.mkdir(parents=True, exist_ok=True)
sync_map = repo / 'android/v1.0.65/heartbeat_sync.json'
with tempfile.TemporaryDirectory() as temporary:
    raw = Path(temporary) / 'score.wav'
    master = Path(temporary) / 'master.wav'
    subprocess.run([sys.executable, str(repo / 'build_tools/render_intro_synced.py'), str(samples), str(raw), '--video', str(original), '--sync-map', str(sync_map)], check=True)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(raw), '-af',
        'loudnorm=I=-18:TP=-1.5:LRA=9:measured_I=-21.70:measured_TP=-2.50:measured_LRA=7.90:measured_thresh=-32.18:offset=0:linear=true',
        '-ar', '48000', str(master)], check=True)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(original), '-i', str(master),
        '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
        '-ar', '48000', '-t', '17.5', '-movflags', '+faststart', '-y', str(target)], check=True)

def picture_hash(path):
    return subprocess.check_output(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(path),
        '-map', '0:v:0', '-c:v', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], text=True).strip()

assert picture_hash(original) == picture_hash(target), 'The approved picture must remain byte-identical'
info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(target)]))
assert abs(float(info['format']['duration']) - 17.5) < .02
audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
assert audio['codec_name'] == 'aac' and audio['channels'] == 2 and audio['sample_rate'] == '48000'
print('Orchestral intro verified: same picture, 17.5 seconds, AAC stereo 48 kHz; SHA256:', hashlib.sha256(target.read_bytes()).hexdigest())

# Synchronization is real visual analysis, not an estimated music tempo.
report = json.loads(sync_map.read_text())
assert len(report['events']) == 8
assert all(abs(row['reference'] - row['impact']) <= .47 for row in report['events'])
print('Pulse/feature timings verified:', sync_map)
