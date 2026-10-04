#!/usr/bin/env python3
"""Signal checks against the shipped ident: timing, unchanged first scenes, louder logo, clean tail."""
import math
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path


def read(path):
    with wave.open(str(path), 'rb') as sound:
        assert (sound.getframerate(), sound.getnchannels(), sound.getsampwidth(), sound.getnframes()) == (48000, 2, 2, 278400)
        values = array('h', sound.readframes(sound.getnframes()))
        if sys.byteorder != 'little': values.byteswap()
        return values


values = read(Path(sys.argv[1]))
with tempfile.TemporaryDirectory() as temporary:
    old = Path(temporary) / 'old.wav'
    subprocess.run([sys.executable, str(Path(__file__).with_name('generate_intro_sound_v121.py')), str(old)], check=True)
    previous = read(old)
assert values[:round(3.30 * 48000) * 2] == previous[:round(3.30 * 48000) * 2]
assert max(map(abs, values)) < 30000
assert all(value == 0 for value in values[-200:])


def rms(start, end):
    section = values[round(start * 48000) * 2:round(end * 48000) * 2]
    return math.sqrt(sum(value * value for value in section) / len(section))


ratio = rms(3.53, 3.97) / rms(.46, .90)
assert ratio > 1.35, f'Logo heartbeat must stand out clearly: ratio={ratio}'
print(f'Ident verified: first 3.30s unchanged, logo heartbeat {20 * math.log10(ratio):.1f}dB above early beat, no clipping or abrupt tail')
