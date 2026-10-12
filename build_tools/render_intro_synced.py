#!/usr/bin/env python3
"""Render an original 17.5-second orchestral soundtrack proposal.

Instrument recordings: VSCO 2 CE (Versilian Studios / Sam Gossner), CC0.
https://github.com/sgossner/VSCO-2-CE
Pass the selectively downloaded sample directory and an output WAV path.
This is a preview; it does not replace the approved in-app video.
"""
import argparse
import json
import subprocess
import warnings
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

RATE = 48000
DURATION = 17.5
N = round(RATE * DURATION)
SAMPLES = {
    'bass': ('Strings/Cello Section/susvib/susvib_C1_v1_1.wav', 36),
    'cello_d': ('Strings/Cello Section/susvib/susvib_D2_v1_1.wav', 50),
    'cello_f': ('Strings/Cello Section/susvib/susvib_F2_v1_1.wav', 53),
    'cello_a': ('Strings/Cello Section/susvib/susvib_A2_v1_1.wav', 57),
    'viola': ('Strings/Viola Section/susvib/ViolaEns_susvib_D2_v1_1.wav', 50),
    'violin': ('Strings/Violin Section/susVib/VlnEns_susVib_D3_v1.wav', 62),
    'violin_a': ('Strings/Violin Section/susVib/VlnEns_susVib_A3_v1.wav', 69),
    'horn_d': ('Brass/F Horn/sus/MOHorn_sus_D2_v2_1.wav', 50),
    'horn_f': ('Brass/F Horn/sus/MOHorn_sus_F2_v2_1.wav', 53),
    'horn_a': ('Brass/F Horn/sus/MOHorn_sus_A2_v2_1.wav', 57),
    'drum': ('Percussion/BDrumNewhit_v4_rr1_Sum.wav', None),
    'timpani': ('Percussion/Timpani/Timpani3_Hit_v3_rr1_Sum.wav', None),
    'cymbal': ('Percussion/susCymb1-hit_mp_rr1.wav', None),
    'swell': ('Percussion/susCymb1-cresc-Median_v1.wav', None),
}


def visual_pulse_times(video: Path, anchors):
    """Snap audio impacts to local visual brightness peaks in the approved video.

    A peak must be sufficiently brighter than its immediate surroundings. When
    there is no reliable flash nearby, keep the verified feature-section time.
    This limits timing corrections to 0.46s and never extrapolates a new cue.
    """
    if video is None:
        return list(anchors), []
    width, height, fps = 96, 54, 30
    pixels = subprocess.check_output([
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', str(video),
        '-vf', f'fps={fps},scale={width}:{height}:flags=area,format=gray',
        '-f', 'rawvideo', '-pix_fmt', 'gray', '-'])
    count = len(pixels) // (width * height)
    if count < 300:
        raise RuntimeError('Not enough decoded intro frames to synchronize beats')
    frames = np.frombuffer(pixels[:count * width * height], dtype=np.uint8)
    frames = frames.reshape(count, height, width)
    # Content and accents are in the safe middle of the frame; avoid letterbox edges.
    center = frames[:, 9:45, 10:86]
    light = np.percentile(center, 86, axis=(1, 2))
    light = np.convolve(light, np.array([1., 2., 3., 2., 1.]) / 9., mode='same')
    peaks = []
    diagnostics = []
    for anchor in anchors:
        lo = max(5, int(round((anchor - .46) * fps)))
        hi = min(count - 5, int(round((anchor + .46) * fps)))
        if hi <= lo:
            peaks.append(anchor)
            diagnostics.append({'reference': anchor, 'impact': anchor, 'detected': False})
            continue
        # High-pass temporal luminance: accent pulse vs nearby scene baseline.
        candidates = np.arange(lo, hi + 1)
        baseline = (light[candidates - 5] + light[candidates + 5]) / 2
        flare = light[candidates] - baseline
        best = int(np.argmax(flare))
        frame = int(candidates[best])
        delta = float(flare[best])
        # Only lock onto an actual visible pulse rather than an ordinary cut.
        reliable = delta >= 3.0
        timing = frame / fps if reliable else anchor
        peaks.append(timing)
        diagnostics.append({'reference': anchor, 'impact': round(timing, 3),
                            'detected': bool(reliable), 'visual_contrast': round(delta, 2)})
    return peaks, diagnostics


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('samples', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--sync-map', type=Path, required=True)
    args = parser.parse_args()
    feature_anchors = [2.78, 5.00, 7.10, 9.82, 12.04, 13.02, 14.04, 15.04]
    synced, sync_details = visual_pulse_times(args.video, feature_anchors)
    assert len(synced) == len(feature_anchors)
    assert all(abs(a - b) <= .47 for a, b in zip(feature_anchors, synced))
    args.sync_map.parent.mkdir(parents=True, exist_ok=True)
    args.sync_map.write_text(json.dumps({'fps': 30, 'events': sync_details}, indent=2) + '\\n')
    rng = np.random.default_rng(165)
    cache = {}
    strings = np.zeros((N, 2))
    brass = np.zeros_like(strings)
    percussion = np.zeros_like(strings)
    atmosphere = np.zeros_like(strings)

    def load(name):
        if name not in cache:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                sr, signal = wavfile.read(args.samples / SAMPLES[name][0])
            signal = signal.astype(np.float64) / np.iinfo(signal.dtype).max
            if signal.ndim == 1:
                signal = np.column_stack((signal, signal))
            signal = resample_poly(signal, RATE, sr, axis=0)
            # Trim only the leading recording silence; preserve natural attacks.
            active = np.flatnonzero(np.max(np.abs(signal), axis=1) > np.max(np.abs(signal)) * .012)
            signal = signal[max(0, int(active[0]) - round(.035 * RATE)):]
            rms = np.sqrt(np.mean(signal[:min(len(signal), RATE * 3)] ** 2))
            cache[name] = signal * (.11 / max(rms, .0001))
        return cache[name].copy()

    def add(stem, name, start, duration, gain, midi=None, attack=.35, release=.8, pan=0):
        signal = load(name)
        root = SAMPLES[name][1]
        if midi is not None and root is not None and midi != root:
            ratio = 2 ** ((midi - root) / 12)
            signal = resample_poly(signal, 1000, round(1000 * ratio), axis=0)
        length = min(len(signal), round(duration * RATE))
        signal = signal[:length]
        t = np.arange(length) / RATE
        envelope = smooth(t / max(attack, .003)) * smooth((length / RATE - t) / release)
        # A gentle dynamic rise, with the acoustic attack still audible.
        envelope *= .73 + .27 * smooth(t / max(duration - release, .1))
        signal *= envelope[:, None] * gain
        mid = signal.mean(axis=1)
        signal = mid[:, None] + .7 * (signal - mid[:, None])
        signal[:, 0] *= np.sqrt(1 - pan)
        signal[:, 1] *= np.sqrt(1 + pan)
        offset = round(start * RATE)
        stop = min(N, offset + length)
        if stop > offset:
            stem[offset:stop] += signal[:stop - offset]

    # D minor -> Bb -> G minor -> F -> A suspended -> D minor.
    # Section changes follow the existing feature cards in the video.
    sections = [
        (0.0, 4.0, [38, 50, 53, 57, 64], .27),
        (2.78, 4.2, [46, 50, 53, 58, 62], .38),
        (5.00, 4.0, [43, 50, 55, 58, 62], .46),
        (7.10, 4.7, [41, 53, 57, 60, 65], .49),
        (9.82, 4.1, [45, 52, 57, 62, 64], .53),
        (12.04, 4.4, [38, 50, 53, 57, 62], .63),
        (15.04, 2.46, [38, 50, 53, 57, 62, 64, 69], .87),
    ]
    for start, duration, notes, strength in sections:
        add(strings, 'bass', start, duration, strength * .80, notes[0], .32, .9, .10)
        for index, note in enumerate(notes[1:]):
            name = 'cello_d' if note < 53 else 'cello_f' if note <= 55 else 'cello_a' if note <= 59 else 'violin_a' if note >= 67 else 'violin'
            add(strings, name, start + .035 * index, duration - .035 * index,
                strength * (.57 if note < 60 else .37), note, .52, .9,
                -.32 if index % 2 else .22)

    # Warm horn harmony arrives gradually; the logo gets a broad resolving chord.
    for start, duration, notes, strength in [
        (7.14, 3.8, [53, 57, 60], .16),
        (9.88, 3.4, [52, 57, 62], .20),
        (12.08, 3.0, [50, 53, 57], .26),
        (15.04, 2.46, [50, 53, 57, 62], .50),
    ]:
        for index, note in enumerate(notes):
            name = 'horn_d' if note <= 51 else 'horn_f' if note <= 55 else 'horn_a'
            add(brass, name, start + .02 * index, duration - .02 * index,
                strength, note, .18 if start > 15 else .75, .90, .12)

    def heartbeat(start, gain):
        # Two organic low-drum impulses with an almost inaudible sub-body.
        for delay, weight, length in [(0, 1, .38), (.21, .62, .29)]:
            signal = sosfilt(butter(3, 420, fs=RATE, output='sos'), load('drum'), axis=0)
            count = round(length * RATE)
            signal = signal[:count]
            t = np.arange(count) / RATE
            sub = np.sin(2 * np.pi * (52 * t + 1.1 * (1 - np.exp(-t / .025))))
            envelope = smooth(t / .007) * np.exp(-t / .095) * smooth((length - t) / .07)
            signal = signal * .56 + (sub * envelope * .17)[:, None]
            signal *= weight * gain * smooth((length - t) / .07)[:, None]
            offset = round((start + delay) * RATE)
            percussion[offset:offset + count] += signal

    # The audible first impulse is locked to a measured visual feature pulse,
    # not merely the nominal beginning of the soundtrack section.
    for start, strength in zip(synced, [.65, .69, .74, .78, .81, .43, .49, 1.25]):
        heartbeat(max(0., start - .018), strength)
    add(percussion, 'timpani', synced[-1], max(.1, 17.5 - synced[-1]), .38, attack=.004, release=.85)
    add(percussion, 'cymbal', synced[-1], max(.1, 17.5 - synced[-1]), .24, attack=.004, release=.9, pan=-.17)

    # Soft, filtered air and acoustic cymbal swells preserve the rushing texture.
    noise = sosfilt(butter(2, [380, 4200], btype='bandpass', fs=RATE, output='sos'), rng.normal(0, 1, N))
    t = np.arange(N) / RATE
    envelope = .006 * smooth(t / 1.3) * smooth((DURATION - t) / 1.2)
    for point in [synced[i] for i in (0, 1, 2, 3, 4, 7)]:
        envelope += .018 * np.exp(-((t - (point - .13)) / .28) ** 2)
    atmosphere += (noise * envelope)[:, None]
    swell = load('swell')
    for start, length, gain in [(max(0., synced[3] - .77), .77, .032), (max(0., synced[7] - .99), .99, .095)]:
        count = round(length * RATE)
        segment = swell[-count:].copy()
        z = np.arange(count) / RATE
        segment *= (smooth(z / length) * gain * smooth((length - z) / .05))[:, None]
        offset = round(start * RATE)
        atmosphere[offset:offset + count] += segment

    # A restrained stereo concert-hall tail joins the recordings into one room.
    size = round(1.6 * RATE)
    ir = np.zeros((size, 2))
    for channel in range(2):
        tail = rng.normal(size=size)
        tail = sosfilt(butter(2, 3600, fs=RATE, output='sos'), tail)
        tail *= np.exp(-np.arange(size) / RATE / .36) * smooth(np.arange(size) / RATE / .07)
        tail *= .008
        for delay, gain in [(0.023, .22), (.041, .16), (.067, .11), (.101, .07)]:
            tail[round((delay + channel * .0037) * RATE)] += gain
        ir[:, channel] = tail
    orchestra = strings + brass
    wet = np.column_stack([fftconvolve(orchestra[:, c], ir[:, c])[:N] for c in range(2)])
    mix = orchestra + .23 * wet + percussion + atmosphere
    mix = sosfilt(butter(2, 28, btype='highpass', fs=RATE, output='sos'), mix, axis=0)
    mix *= smooth((DURATION - t) / .85)[:, None] * smooth(t / .07)[:, None]
    peak = np.max(np.abs(mix))
    mix *= 10 ** (-2.5 / 20) / peak
    args.output.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(args.output, RATE, np.round(mix * 32767).astype(np.int16))
    print(f'{args.output.name}: pulse-synced score, {DURATION}s, 48 kHz stereo, peak -2.5 dBFS')
    print('Visual event synchronization:', json.dumps(sync_details, ensure_ascii=False))


if __name__ == '__main__':
    main()
