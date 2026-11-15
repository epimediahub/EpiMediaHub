#!/usr/bin/env python3
"""Preserve the existing ident; give the final heartbeat a rounded, forceful accent."""
import math
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

RATE = 48000
destination = Path(sys.argv[1])
with tempfile.TemporaryDirectory() as temporary:
    previous = Path(temporary) / 'previous.wav'
    subprocess.run([sys.executable, str(Path(__file__).with_name('generate_intro_sound_v127.py')), str(previous)], check=True)
    with wave.open(str(previous), 'rb') as source:
        original = array('h', source.readframes(source.getnframes()))
        if sys.byteorder != 'little': original.byteswap()

count = len(original) // 2
accent = array('d', [0.0]) * count
start = round(4.42 * RATE)
def smooth(value):
    x = max(0.0, min(1.0, value))
    return x * x * (3.0 - 2.0 * x)

for index in range(start, min(count, start + round(.76 * RATE))):
    t = (index - start) / RATE
    envelope = smooth(t / .008) * math.exp(-t / .16) * smooth((.76 - t) / .18)
    phase = 2 * math.pi * (54 * t + 1.52 * (1 - math.exp(-t / .038)))
    # Strong low body and audible harmonics, including on small television speakers.
    accent[index] = envelope * (math.sin(phase) + .48 * math.sin(2 * phase) + .20 * math.sin(3 * phase))

dry = array('d', accent)
for seconds, gain in ((.043, .075), (.097, .035), (.183, .018)):
    offset = round(seconds * RATE)
    for index in range(start + offset, count):
        accent[index] += dry[index - offset] * gain

target = 32767 * 10 ** (-1.0 / 20)
lower, upper = 0.0, 40000.0
for _ in range(30):
    gain = (lower + upper) / 2
    peak = max(abs(original[index * 2 + channel] + accent[index] * gain)
               for index in range(start, count) for channel in (0, 1))
    if peak > target: upper = gain
    else: lower = gain
pcm = array('h', original)
for index in range(start, count):
    for channel in (0, 1):
        pcm[index * 2 + channel] = round(original[index * 2 + channel] + accent[index] * lower)
assert pcm[:start * 2] == original[:start * 2]
assert max(map(abs, pcm)) < 30000
assert all(value == 0 for value in pcm[-200:])
if sys.byteorder != 'little': pcm.byteswap()
destination.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(destination), 'wb') as output:
    output.setnchannels(2); output.setsampwidth(2); output.setframerate(RATE); output.writeframes(pcm.tobytes())
print('Final heartbeat strengthened: first 4.42s unchanged, peak -1.0 dBFS, clean original 5.8s timeline')
