#!/usr/bin/env python3
"""EpiMediaHub v185 short intro: original 17.5s film, original verified synced audio.

The old v5 picture and the existing v7 orchestral/heartbeat audio are retained
at native speed. All new graphics are timed from the SAME measured heartbeat
map that generated the soundtrack. Output is one CFR H264/AAC file, not two
independent app animations. No generic audio retiming or frame repetition.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "android/v1.0.65/epimedia_intro_v7.mp4"
SYNC = ROOT / "android/v1.0.65/heartbeat_sync.json"
DEST = ROOT / "android/v1.0.85/epimedia_intro_v185.mp4"
DURATION = 17.5
FPS = 30
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

# Short, readable, EpiScene-first narrative. The old cinematic picture plays
# throughout and the ORIGINAL logo remains visible at the finale.
CARDS = [
    (1.25, 3.70, "EPIMEDIAHUB", "Live-TV  ·  Filme  ·  Serien",
     "Alles in deinem Media Player."),
    (3.70, 7.65, "DAS IST EPISCENE", "Erkennt Intro, Rückblick & Abspann",
     "Intelligente Zeitmarker für deine Serien."),
    (7.65, 11.00, "EPISCENE  /  ÜBERSPRINGEN", "Direkt zur Handlung",
     "Mit geprüften Markern weniger vorspulen."),
    (11.00, 14.85, "EPISCENE  /  LERNEN", "Bestätigte Marker helfen weiter",
     "Die Erkennung lernt aus freigegebenen Stellen."),
    (14.85, 17.46, "EPIMEDIAHUB", "Intelligenter schauen.",
     "EpiScene  ·  Dein Serien-Assistent."),
]

def run(args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=700)
    if p.returncode:
        raise RuntimeError("FFMPEG_FAILED: " + p.stderr[-1800:])
    return p.stdout

def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                           "-of", "json", str(path)]))

def quote(path):
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

def main():
    if not SOURCE.is_file() or not SYNC.is_file() or not FONT.is_file() or not BOLD.is_file():
        raise SystemExit("STOP_V185_APPROVED_17_5_S_SOURCE_OR_SYNC_MAP_MISSING")
    report = json.loads(SYNC.read_text(encoding="utf-8"))
    events = report.get("events", [])
    if len(events) != 8 or report.get("fps") != 30:
        raise SystemExit("STOP_V185_UNEXPECTED_ORIGINAL_HEARTBEAT_MAP")
    src = probe(SOURCE)
    video = next(v for v in src["streams"] if v["codec_type"] == "video")
    audio = next(a for a in src["streams"] if a["codec_type"] == "audio")
    if (abs(float(src["format"]["duration"])-DURATION) > .07 or
        video["codec_name"] != "h264" or audio["codec_name"] != "aac" or
        audio["sample_rate"] != "48000"):
        raise SystemExit("STOP_V185_ORIGINAL_SYNC_MEDIA_DRIFT")
    if abs(float(video.get("start_time", "0"))) > .06 or abs(float(audio.get("start_time", "0"))) > .06:
        raise SystemExit("STOP_V185_SOURCE_AUDIO_VIDEO_ORIGIN_DRIFT")
    for row in events:
        if abs(float(row["reference"]) - float(row["impact"])) > .47:
            raise SystemExit("STOP_V185_HEARTBEAT_DETECTION_OUT_OF_BOUNDS")

    DEST.parent.mkdir(parents=True, exist_ok=True)
    texts = DEST.parent / ".v185_intro_text"
    texts.mkdir(parents=True, exist_ok=True)
    vf = [
        "fps=30",
        "scale=1280:720:flags=lanczos",
        "setsar=1",
        "setpts=PTS-STARTPTS",
        "format=yuv420p",
    ]
    for index, (start, end, eyebrow, heading, detail) in enumerate(CARDS):
        enabled = f"between(t,{start:.3f},{end:.3f})"
        fade = f"max(0,min(1,min((t-{start:.3f})/0.30,({end:.3f}-t)/0.28)))"
        # Keep the old picture visible. Text only occupies a dark lower band.
        vf += [
            f"drawbox=x=0:y=477:w=1280:h=243:color=0x020A16@0.84:t=fill:enable='{enabled}'",
            f"drawbox=x=70:y=508:w=5:h=149:color=0x48E5D6@0.84:t=fill:enable='{enabled}'",
        ]
        for row, (line, size, ypos, color, font) in enumerate([
            (eyebrow, 21, 510, "0x4DE7D8", BOLD),
            (heading, 34 if len(heading)>30 else 39, 548, "0xFFFFFF", BOLD),
            (detail, 21, 614, "0xE8F0FA", FONT),
        ]):
            path = texts / f"text_{index}_{row}.txt"
            path.write_text(line, encoding="utf-8")
            vf.append(
                f"drawtext=fontfile='{quote(font)}':textfile='{quote(path)}':"
                f"fontcolor={color}:fontsize={size}:x=97:y={ypos}:"
                f"alpha='{fade}':enable='{enabled}'"
            )

    # The same original synchronized soundtrack generated the cue map below.
    # Frame quantization at 30 fps is at most +/-16.7 ms. Both low-impulse
    # 'lub-dub' accents receive a narrow turquoise visual pulse.
    synced_events = []
    for idx, row in enumerate(events):
        if idx in (5,6) and not row.get("detected"):
            continue  # Original audio renderer omitted undetected optional hits.
        time = max(0.0, float(row["impact"]) - .018)
        synced_events.append(time)
        for onset, duration in ((time, .12), (time + .21, .10)):
            stop = min(DURATION - .03, onset + duration)
            if onset >= stop: continue
            vf.append(
                f"drawbox=x=70:y=484:w=155:h=6:"
                f"color=0x49F1DD@0.88:t=fill:"
                f"enable='between(t,{onset:.4f},{stop:.4f})'"
            )

    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(SOURCE),
        "-map", "0:v:0", "-map", "0:a:0",
        "-vf", ",".join(vf),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-maxrate", "3600k", "-bufsize", "7200k", "-g", "60", "-r", "30",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.0",
        "-c:a", "copy",  # Preserve exact original verified heartbeat soundtrack.
        "-t", str(DURATION), "-movflags", "+faststart", str(DEST),
    ])
    media = probe(DEST)
    v = next(x for x in media["streams"] if x["codec_type"] == "video")
    a = next(x for x in media["streams"] if x["codec_type"] == "audio")
    if not (
        abs(float(media["format"]["duration"]) - DURATION) < .07 and
        v["codec_name"] == "h264" and a["codec_name"] == "aac" and
        v["width"] == 1280 and v["height"] == 720 and
        a["sample_rate"] == "48000" and
        abs(float(v.get("start_time",0))) < .06 and
        abs(float(a.get("start_time",0))) < .06
    ):
        raise SystemExit("STOP_V185_RENDERED_INTRO_TIMING_OR_FORMAT_FAILED")
    report_path = DEST.parent / "v185_intro_sync_validation.json"
    report_path.write_text(json.dumps({
        "duration_seconds": DURATION, "video_fps": FPS,
        "audio": "Original verified v7 synced soundtrack, stream-copy",
        "audio_start_seconds": float(a.get("start_time",0)),
        "video_start_seconds": float(v.get("start_time",0)),
        "pulse_seconds": synced_events,
        "max_visual_quantization_ms": 1000/(2*FPS),
        "digest_sha256": hashlib.sha256(DEST.read_bytes()).hexdigest(),
        "note": "Device-specific HDMI/audio delay requires actual Fire TV + soundbar listening test."
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("V185_SHORT_INTRO_RENDERED_VERIFIED 17.5s 720p30 original picture + copied synchronized heartbeat soundtrack")
    print("V185_SYNC_REPORT", report_path, "PULSES", synced_events)
    print("V185_INTRO_SHA256", hashlib.sha256(DEST.read_bytes()).hexdigest())

if __name__ == "__main__":
    main()
