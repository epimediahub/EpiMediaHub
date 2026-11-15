#!/usr/bin/env python3
"""Original 5.8-second heartbeat / cinematic ident. Standard library only.

The four heartbeats follow V121IntroTimeline; the logo blooms at 3.52 seconds.
No downloaded music, samples or runtime synthesis are required by the app.
"""
import math
import random
import sys
import wave
from array import array
from pathlib import Path

RATE = 48000
DURATION = 5.8
HEARTBEATS = (0.46, 1.10, 2.21, 2.82)
COUNT = round(RATE * DURATION)
left = array("d", [0.0]) * COUNT
right = array("d", [0.0]) * COUNT
random.seed(121)


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def put(index, value, pan=0.0):
    left[index] += value * math.sqrt((1.0 - pan) / 2.0)
    right[index] += value * math.sqrt((1.0 + pan) / 2.0)


def heartbeat(at, strength):
    start = at - 0.034
    for index in range(round(start * RATE), min(COUNT, round((start + .36) * RATE))):
        t = index / RATE - start
        envelope = smooth(t / .020) * math.exp(-t / .078) * smooth((.36 - t) / .12)
        # A falling, rounded body, with enough low midrange for TV speakers.
        phase = 2 * math.pi * (47 * t + 2.0 * (1.0 - math.exp(-t * 18)))
        body = math.sin(phase) + .32 * math.sin(phase * 2) + .11 * math.sin(phase * 3)
        put(index, strength * envelope * body)


def tone(frequency, start, end, strength, attack=.35, release=.7, pan=0.0, detune=0.0):
    for index in range(max(0, round(start * RATE)), min(COUNT, round(end * RATE))):
        t = index / RATE - start
        envelope = smooth(t / attack) * smooth((end - start - t) / release)
        phase = 2 * math.pi * frequency * t + detune * math.sin(2 * math.pi * 4.3 * t)
        sample = math.sin(phase) + .19 * math.sin(2 * phase) + .045 * math.sin(3 * phase)
        put(index, sample * strength * envelope, pan)


def piano(frequency, start, strength, pan=0.0):
    for index in range(round(start * RATE), COUNT):
        t = index / RATE - start
        envelope = smooth(t / .016) * math.exp(-t / 1.12)
        sample = math.sin(2 * math.pi * frequency * t)
        sample += .26 * math.sin(2 * math.pi * frequency * 2.005 * t) * math.exp(-t / .48)
        sample += .075 * math.sin(2 * math.pi * frequency * 3.014 * t) * math.exp(-t / .25)
        put(index, sample * strength * envelope, pan)


# A very quiet tonal room gives the text space without masking the double beats.
tone(73.4162, .10, 3.58, .028, .75, .8, -.08)
tone(110.0, .32, 3.6, .013, .9, .7, .08)
for start in HEARTBEATS:
    heartbeat(start, .30)
    heartbeat(start + .17, .20)

# Air rises into the logo; low-pass filtered noise avoids a harsh hiss.
noise = 0.0
for index in range(round(2.95 * RATE), round(4.15 * RATE)):
    t = index / RATE
    noise = noise * .955 + random.uniform(-1.0, 1.0) * .045
    envelope = smooth((t - 2.95) / .7) * smooth((4.15 - t) / .5)
    put(index, noise * envelope * .12, math.sin(t * 3) * .4)

# A warm D-major/add9 logo hit, followed by a broad string and piano tail.
tone(36.7081, 3.51, 5.38, .16, .07, .9)
tone(73.4162, 3.53, 5.52, .11, .12, 1.1, -.05)
for frequency, strength, pan in ((146.8324, .075, -.35), (220., .061, .32),
                                 (293.6648, .040, -.12), (369.9944, .033, .19),
                                 (440., .027, -.25), (659.2551, .018, .4)):
    tone(frequency, 3.46, 5.70, strength, .44, 1.08, pan, .013)
    piano(frequency, 3.70, strength * .92, pan)
piano(880., 3.88, .027, -.34)
piano(1174.659, 4.03, .015, .30)

# Short diffuse reflections, and a controlled tail rather than an abrupt cutoff.
dry_left, dry_right = array("d", left), array("d", right)
for seconds, gain in ((.047, .13), (.089, .09), (.151, .07), (.233, .048), (.337, .030)):
    offset = round(seconds * RATE)
    for index in range(offset, COUNT):
        left[index] += dry_right[index - offset] * gain
        right[index] += dry_left[index - offset] * gain
for index in range(COUNT):
    t = index / RATE
    fade = smooth(t / .018) * smooth((DURATION - t) / .43)
    left[index] *= fade
    right[index] *= fade

peak = max(max(abs(x) for x in left), max(abs(x) for x in right))
gain = (10 ** (-3.0 / 20.0)) / max(peak, .001)
pcm = array("h")
for l, r in zip(left, right):
    pcm.append(round(max(-1.0, min(1.0, l * gain)) * 32767))
    pcm.append(round(max(-1.0, min(1.0, r * gain)) * 32767))
if sys.byteorder != "little":
    pcm.byteswap()
destination = Path(sys.argv[1])
destination.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(destination), "wb") as wav:
    wav.setnchannels(2)
    wav.setsampwidth(2)
    wav.setframerate(RATE)
    wav.writeframes(pcm.tobytes())
print(f"Heartbeat/cinematic ident: {DURATION:.2f}s, stereo {RATE}Hz, peak -3.0 dBFS")
