#!/usr/bin/env python3
"""Extend the existing 5.8 s cinema heartbeat to the 10.0 s intro.

Preserve the original mix unmodified as the final 5.8 s (including its strong
last heartbeat); add a restrained 4.2 s digital/cinematic prologue. No codecs,
heavy native media libraries, third-party audio files or new APK downloads.
"""
from pathlib import Path
from array import array
import math
import os
import sys
import wave

target = Path(sys.argv[1])
with wave.open(str(target), "rb") as reader:
    sr, channels, bits = reader.getframerate(), reader.getnchannels(), reader.getsampwidth()
    assert (sr, channels, bits) == (48000, 2, 2), "Unexpected intro asset format"
    assert reader.getnframes() == 278400, "Original sound duration drift"
    original = reader.readframes(reader.getnframes())

opening_frames = 201600  # 4.2 seconds
opening = array("h")
for i in range(opening_frames):
    t = i / sr
    # Film-style bass, subdued energy with two broad sub-pulses.
    start = min(1.0, t / .22)
    end = min(1.0, (4.2 - t) / .28)
    env = max(0., start * end)
    pulse = (.45 + .55 * (1 + math.cos(2 * math.pi * 1.3 * (t - .14))) / 2)
    bass = math.sin(2 * math.pi * 57 * t) * 1150
    harmonics = math.sin(2 * math.pi * 114 * t + .15 * math.sin(t * 2.5)) * 480
    shimmer = math.sin(2 * math.pi * (510 + 95 * t / 4.2) * t) * 125
    hit = sum(math.exp(-((t - at) / .17) ** 2) for at in (.55, 1.15, 2.42, 3.35))
    effect = 2100 * hit * math.sin(2 * math.pi * 84 * t)
    sample = int((bass + harmonics) * env * pulse + shimmer * env + effect)
    sample = max(-13000, min(13000, sample))
    opening.extend((sample, int(sample * .94)))
if sys.byteorder != "little":
    opening.byteswap()
tmp = target.with_suffix(".v160.tmp")
with wave.open(str(tmp), "wb") as writer:
    writer.setnchannels(channels)
    writer.setsampwidth(bits)
    writer.setframerate(sr)
    writer.writeframes(opening.tobytes())
    writer.writeframes(original)
os.replace(tmp, target)

with wave.open(str(target), "rb") as written:
    assert written.getnframes() == 480000, "Intro must be exactly ten seconds"
    assert written.getframerate() == sr and written.getnchannels() == 2
print("v1.0.60 10-second intro: 4.2s new light prologue + original 5.8s heartbeat ending; original final accent preserved.")
