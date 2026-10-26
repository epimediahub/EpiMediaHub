#!/usr/bin/env python3
"""Preserve the existing text ident; replace the logo chord with an original deep heartbeat."""
import math
import runpy
import sys
import tempfile
import wave
from array import array
from pathlib import Path

RATE = 48000
DURATION = 5.8
COUNT = round(RATE * DURATION)
destination = Path(sys.argv[1])

# Reuse the shipped first scenes sample-for-sample, including their four quiet heartbeats.
with tempfile.TemporaryDirectory() as temporary:
    previous = Path(temporary) / 'previous.wav'
    arguments = sys.argv
    try:
        sys.argv = [str(Path(__file__).with_name('generate_intro_sound_v121.py')), str(previous)]
        runpy.run_path(sys.argv[0], run_name='__main__')
    finally:
        sys.argv = arguments
    with wave.open(str(previous), 'rb') as source:
        original = array('h', source.readframes(source.getnframes()))
        if sys.byteorder != 'little': original.byteswap()

left, right = array('d', [0.0]) * COUNT, array('d', [0.0]) * COUNT


def smooth(value):
    x = min(1.0, max(0.0, value))
    return x * x * (3.0 - 2.0 * x)


def beat(at, strength):
    start = round(at * RATE)
    for index in range(start, min(COUNT, start + round(.64 * RATE))):
        t = (index - start) / RATE
        envelope = smooth(t / .014) * math.exp(-t / .115) * smooth((.64 - t) / .16)
        # Bass plus low mids: the double beat also reads on TV speakers without a subwoofer.
        phase = 2 * math.pi * (54 * t + 1.52 * (1 - math.exp(-t / .038)))
        body = math.sin(phase) + .38 * math.sin(2 * phase) + .15 * math.sin(3 * phase)
        value = strength * envelope * body
        left[index] += value
        right[index] += value


# Main lub-dub begins as the logo appears at 3.52s; a quieter second pulse lets it settle.
for at, strength in ((3.53, 1.0), (3.72, .68), (4.23, .48), (4.42, .32)):
    beat(at, strength)

dry_left, dry_right = array('d', left), array('d', right)
for seconds, gain in ((.043, .10), (.097, .055), (.183, .033), (.291, .017)):
    offset = round(seconds * RATE)
    for index in range(offset, COUNT):
        left[index] += dry_right[index - offset] * gain
        right[index] += dry_left[index - offset] * gain

peak = max(max(map(abs, left)), max(map(abs, right)))
logo_gain = 10 ** (-1.5 / 20) / peak
pcm = array('h')
for index in range(COUNT):
    time = index / RATE
    original_gain = 1.0 if time <= 3.30 else smooth((3.52 - time) / .22)
    tail = smooth((DURATION - time) / .45)
    for channel, replacement in ((0, left), (1, right)):
        # Original ends before the new hit, so no overlapping chord or global normalization.
        value = original[index * 2 + channel] * original_gain + replacement[index] * logo_gain * tail * 32767
        assert abs(value) < 32767, 'Ident unexpectedly clipped'
        pcm.append(round(value))
if sys.byteorder != 'little': pcm.byteswap()
destination.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(destination), 'wb') as output:
    output.setnchannels(2)
    output.setsampwidth(2)
    output.setframerate(RATE)
    output.writeframes(pcm.tobytes())
print(f'Original logo heartbeat: {DURATION:.2f}s, stereo {RATE}Hz, logo peak -1.5 dBFS')
