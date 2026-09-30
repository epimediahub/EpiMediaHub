#!/usr/bin/env python3
import math
import random
import struct
import sys
import wave
from pathlib import Path

SR = 48000
DURATION = 2.85
N = int(SR * DURATION)
random.seed(108)

left = [0.0] * N
right = [0.0] * N

def smoothstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)

def add_tone(freq, start, end, amp, attack, release, harmonics, pan=0.0, vibrato=0.0):
    i0 = max(0, int(start * SR))
    i1 = min(N, int(end * SR))
    lg = math.sqrt((1.0 - pan) * 0.5)
    rg = math.sqrt((1.0 + pan) * 0.5)
    for i in range(i0, i1):
        local = i / SR - start
        dur = end - start
        env = smoothstep(local / attack) * smoothstep((dur - local) / release)
        phase_t = local
        if vibrato:
            phase_t += (vibrato / (2.0 * math.pi * 5.0)) * math.sin(2.0 * math.pi * 5.0 * local)
        sample = 0.0
        for mult, rel in harmonics:
            sample += rel * math.sin(2.0 * math.pi * freq * mult * phase_t)
        sample *= amp * env
        left[i] += sample * lg
        right[i] += sample * rg

def add_piano(freq, start, amp, pan=0.0, decay=1.0):
    i0 = int(start * SR)
    lg = math.sqrt((1.0 - pan) * 0.5)
    rg = math.sqrt((1.0 + pan) * 0.5)
    partials = [(1.0, 1.0), (2.01, 0.33), (3.02, 0.16), (4.04, 0.08), (5.07, 0.035)]
    for i in range(i0, N):
        local = i / SR - start
        env = (1.0 - math.exp(-local / 0.012)) * math.exp(-local / decay)
        sample = 0.14 * math.exp(-local / 0.040) * math.sin(2.0 * math.pi * (freq * 2.6) * local)
        for mult, rel in partials:
            sample += rel * math.sin(2.0 * math.pi * freq * mult * local)
        sample *= amp * env
        left[i] += sample * lg
        right[i] += sample * rg

def add_glass(freq, start, amp, pan=0.0, decay=0.65):
    i0 = int(start * SR)
    lg = math.sqrt((1.0 - pan) * 0.5)
    rg = math.sqrt((1.0 + pan) * 0.5)
    partials = [(1.0, 1.0), (2.72, 0.42), (4.11, 0.20), (5.43, 0.09)]
    for i in range(i0, N):
        local = i / SR - start
        env = (1.0 - math.exp(-local / 0.006)) * math.exp(-local / decay)
        sample = 0.0
        for mult, rel in partials:
            sample += rel * math.sin(2.0 * math.pi * freq * mult * local)
        sample *= amp * env
        left[i] += sample * lg
        right[i] += sample * rg

# Organic cello and string swell.
cello_h = [(1, 1.0), (2, 0.42), (3, 0.18), (4, 0.07), (5, 0.03)]
add_tone(73.416, 0.02, 1.95, 0.27, 0.48, 0.75, cello_h, -0.03, 0.003)
add_tone(110.0, 0.14, 1.85, 0.13, 0.42, 0.72, [(1, 1.0), (2, 0.25), (3, 0.09)], 0.05, 0.002)
add_tone(146.832, 0.24, 1.72, 0.075, 0.34, 0.65, [(1, 1.0), (2, 0.18)], 0.0, 0.0)
add_tone(49.0, 0.12, 1.45, 0.045, 0.55, 0.55, [(1, 1.0)], 0.0, 0.0)

# D major add9 soft piano chord.
for freq, start, amp, pan in [
    (146.832, 0.60, 0.11, -0.10),
    (220.000, 0.60, 0.09, -0.04),
    (293.665, 0.60, 0.085, 0.02),
    (369.994, 0.60, 0.075, 0.08),
    (440.000, 0.60, 0.060, 0.12),
    (659.255, 0.60, 0.040, 0.18),
]:
    add_piano(freq, start, amp, pan, 1.06 if freq < 300 else 0.92)

# Mid string bloom.
for freq, pan, amp in [
    (146.832, -0.25, 0.038),
    (220.000, 0.20, 0.032),
    (369.994, -0.10, 0.025),
    (440.000, 0.18, 0.022),
]:
    add_tone(freq, 0.42, 2.10, amp, 0.45, 0.70, [(1, 1.0), (2, 0.16)], pan, 0.0018)

# Crystal finish.
add_glass(880.000, 1.34, 0.050, -0.22, 0.72)
add_glass(1174.659, 1.61, 0.040, 0.18, 0.64)
add_glass(1318.510, 1.86, 0.032, 0.30, 0.58)

# Stronger v2 final cinematic bloom chosen for the app.
# Add a second low orchestral anchor just before the logo locks in so the
# ending has noticeably more weight on soundbars, while the upper harmonics
# keep the same punch audible on phone speakers.
add_tone(73.416, 1.70, 2.63, 0.105, 0.08, 0.43,
         [(1, 1.0), (2, 0.50), (3, 0.20), (4, 0.08)], -0.02, 0.0)
add_tone(110.000, 1.76, 2.58, 0.060, 0.07, 0.38,
         [(1, 1.0), (2, 0.35), (3, 0.12)], 0.03, 0.0)

# Stronger D-major-add9 punctuation at the end.
for freq, amp, pan in [
    (146.832, 0.060, -0.10),
    (220.000, 0.050, -0.04),
    (293.665, 0.047, 0.03),
    (369.994, 0.039, 0.08),
    (659.255, 0.025, 0.14),
]:
    add_piano(freq, 1.82, amp, pan, 0.65)

# Extra low-mid orchestral body for physical impact without relying on sub-bass.
for freq, amp, pan in [
    (196.000, 0.032, -0.18),
    (246.940, 0.028, 0.15),
    (329.630, 0.020, 0.22),
]:
    add_tone(freq, 1.58, 2.72, amp, 0.17, 0.48,
             [(1, 1.0), (2, 0.12)], pan, 0.0)

# Slightly brighter final glass shimmer, still soft rather than metallic.
add_glass(1174.659, 2.00, 0.020, -0.25, 0.48)
add_glass(1318.510, 2.12, 0.017, 0.28, 0.44)

# Subtle air bloom.
last = 0.0
for i in range(int(0.65 * SR), int(1.45 * SR)):
    now = i / SR
    noise = random.uniform(-1.0, 1.0)
    last = 0.94 * last + 0.06 * noise
    high = noise - last
    env = smoothstep((now - 0.65) / 0.18) * smoothstep((1.45 - now) / 0.45)
    air = high * 0.0085 * env
    left[i] += air * 0.92
    right[i] += air * 1.08

# Warm stereo room / shimmer taps.
dry_l = left[:]
dry_r = right[:]
for delay_s, gain in [(0.031, 0.15), (0.067, 0.10), (0.113, 0.075), (0.167, 0.055), (0.241, 0.035)]:
    delay = int(delay_s * SR)
    for i in range(delay, N):
        left[i] += dry_r[i - delay] * gain
        right[i] += dry_l[i - delay] * gain

# Gentle 30 Hz high-pass.
rc = 1.0 / (2.0 * math.pi * 30.0)
dt = 1.0 / SR
alpha = rc / (rc + dt)
def highpass(sig):
    out = [0.0] * len(sig)
    prev_y = 0.0
    prev_x = sig[0]
    for i, x in enumerate(sig):
        y = alpha * (prev_y + x - prev_x)
        out[i] = y
        prev_y = y
        prev_x = x
    return out

left = highpass(left)
right = highpass(right)

# Mild parallel glue in the final second so the stronger ending feels like
# one coherent orchestral hit rather than stacked tones.
den_glue = math.tanh(1.35)
for i in range(N):
    mix = smoothstep((i / SR - 1.55) / 0.40) * 0.16
    if mix <= 0.0:
        continue
    sat_l = math.tanh(left[i] * 1.35) / den_glue
    sat_r = math.tanh(right[i] * 1.35) / den_glue
    left[i] = left[i] * (1.0 - mix) + sat_l * mix
    right[i] = right[i] * (1.0 - mix) + sat_r * mix

# End cleanly at the 2.85 second visual cut.
fade_start = int(2.67 * SR)
for i in range(fade_start, N):
    k = smoothstep((N - i) / (N - fade_start))
    left[i] *= k
    right[i] *= k

# Soft saturation then normalize to about -1 dBFS peak.
den = math.tanh(1.25)
left = [math.tanh(v * 1.25) / den for v in left]
right = [math.tanh(v * 1.25) / den for v in right]
peak = max(max(abs(v) for v in left), max(abs(v) for v in right))
gain = (10.0 ** (-1.0 / 20.0)) / peak if peak else 1.0

output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("epimedia_intro_organic_orchestral_chime.wav")
output.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(output), "wb") as wav:
    wav.setnchannels(2)
    wav.setsampwidth(2)
    wav.setframerate(SR)
    frames = bytearray()
    for l, r in zip(left, right):
        frames.extend(struct.pack(
            "<hh",
            int(max(-1.0, min(1.0, l * gain)) * 32767),
            int(max(-1.0, min(1.0, r * gain)) * 32767),
        ))
    wav.writeframes(frames)

print(f"Generated {output} ({DURATION:.2f}s, {SR} Hz stereo)")
