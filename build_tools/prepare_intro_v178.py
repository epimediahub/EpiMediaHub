#!/usr/bin/env python3
"""Render a 20s EpiMediaHub feature-first intro with consistent audio/video timing.

The existing synchronized 17.5-second source stays at ORIGINAL playback speed
(no retiming/stuttering frames or heartbeat drift). A 2.5-second final branded
hold is supported by a quiet ORIGINAL D-minor signature chord.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "android/v1.0.65/epimedia_intro_v7.mp4"
DEST = ROOT / "android/v1.0.78/epimedia_intro_v9.mp4"
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
DURATION = 20.0
ORIGINAL_DURATION = 17.5
RATE = 48000

# One meaningful function per card. Keep all claims within existing features.
# Times are local media timestamps; the first 2 seconds stay entirely visual.
SCENES = [
    (2.00, 5.00, "01  /  EPIMEDIA PLAYER",
     "Live-TV, Filme & Serien", "EPG  ·  Weiterschauen  ·  flüssige Wiedergabe"),
    (5.00, 7.70, "02  /  EPISCENE",
     "Rückblicke & Intros erkennen", "Automatische Sprungmarken für deine Serien"),
    (7.70, 10.20, "03  /  EPISCENE",
     "Abspann clever überspringen", "Outro-Skip  ·  Nächste Folge direkt starten"),
    (10.20, 13.10, "04  /  EPISCENE  ·  LERNEN",
     "Deine Markierungen helfen", "Bestätigte Marker verbessern die Erkennung"),
    (13.10, 16.45, "05  /  VPN-ANBINDUNG",
     "VPN gezielt pro Playlist", "Standort wählen  ·  VPN je Playlist steuern"),
    (16.45, 18.20, "06  /  SMARTTUBE & SPEEDTEST",
     "Mehr Kontrolle beim Streamen", "Adaptive Qualität wählen  ·  Speedtest nutzen"),
    (18.20, 19.97, "EPIMEDIAHUB",
     "Alles an einem Ort.", "Live erleben. Intelligenter schauen."),
]

def media_info(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path)], text=True))

def signature_tail(path):
    """Short original D-minor cadence; no third-party recording or licensing."""
    count = round(RATE * 2.85)
    notes = [(73.416, .16), (146.832, .11), (220.0, .08),
             (293.665, .11), (349.228, .07), (440.0, .04)]
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        for offset in range(0, count, 4096):
            frames = bytearray()
            for idx in range(offset, min(offset+4096, count)):
                t = idx/RATE
                attack = min(1., t/.28)
                decay = math.exp(-.80*max(0., t-.25))
                end = min(1., (2.85-t)/.5)
                envelope = attack*decay*max(0.,end)
                signal = sum(w*math.sin(2*math.pi*hz*t) for hz,w in notes)*envelope*.34
                left = int(max(-1.,min(1.,signal))*32767)
                right = int(max(-1.,min(1.,signal*.97))*32767)
                frames.extend(struct.pack("<hh",left,right))
            out.writeframes(frames)

def ffmpeg_path(path):
    return str(path).replace("\\","\\\\").replace(":","\\:").replace("'","\\'")

def render():
    if not SOURCE.is_file() or SOURCE.is_symlink():
        raise SystemExit("STOP_APPROVED_V7_INTRO_MISSING")
    if any(not p.is_file() for p in (FONT,BOLD)) or not shutil.which("ffmpeg"):
        raise SystemExit("STOP_RENDER_FONT_OR_FFMPEG_MISSING")
    src=media_info(SOURCE)
    audio=next((s for s in src["streams"] if s["codec_type"]=="audio"),None)
    video=next((s for s in src["streams"] if s["codec_type"]=="video"),None)
    if not audio or not video or abs(float(src["format"]["duration"])-ORIGINAL_DURATION)>.07:
        raise SystemExit("STOP_UNEXPECTED_APPROVED_INTRO")
    if len(SCENES)!=7 or not all(0<=a<b<=DURATION for a,b,*_ in SCENES):
        raise SystemExit("STOP_INVALID_FEATURE_STORYBOARD")
    with tempfile.TemporaryDirectory(prefix="epimedia-intro178-") as temp:
        stage=Path(temp)
        tail=stage/"signature.wav"
        signature_tail(tail)
        filters=[
            # Decoder-friendly CFR H.264, 720p, lower bitrate for Android/GalaBox.
            # Keep first 17.5s native paced and heartbeat-synchronized.
            "fps=30","scale=1280:720:flags=lanczos","setsar=1",
            "tpad=stop_mode=clone:stop_duration=2.5",
            "trim=duration=20","setpts=PTS-STARTPTS","format=yuv420p",
        ]
        for i,(start,end,eyebrow,title,detail) in enumerate(SCENES):
            a=f"{start:.2f}"
            b=f"{end:.2f}"
            on=f"between(t,{a},{b})"
            filters.extend([
                f"drawbox=x=0:y=476:w=iw:h=244:color=0x020917@0.80:t=fill:enable='{on}'",
                f"drawbox=x=64:y=504:w=5:h=153:color=0x4DE3CD@0.95:t=fill:enable='{on}'",
            ])
            for row,(text,size,y,font,color) in enumerate([
                (eyebrow,21,510,BOLD,"0x4DE3CD"),
                (title,38 if len(title)<33 else 35,546,BOLD,"white"),
                (detail,22,610,FONT,"0xE9F0F7"),
            ]):
                source=stage/f"scene-{i}-{row}.txt"
                source.write_text(text,encoding="utf-8")
                alpha=f"max(0,min(1,min((t-{a})/0.22,({b}-t)/0.25)))"
                filters.append(
                    f"drawtext=fontfile={ffmpeg_path(font)}:"
                    f"textfile={ffmpeg_path(source)}:reload=0:"
                    f"fontcolor={color}:fontsize={size}:x=92:y={y}:"
                    f"alpha='{alpha}':enable='{on}'"
                )
        audio_filter=(
            "[0:a:0]aresample=48000:async=1:first_pts=0,"
            "atrim=duration=17.5,asetpts=PTS-STARTPTS[original];"
            "[1:a:0]atrim=duration=2.85,asetpts=PTS-STARTPTS,"
            "adelay=17150|17150[signature];"
            "[original][signature]amix=inputs=2:duration=longest:normalize=0,"
            "atrim=duration=20,afade=t=out:st=19.50:d=0.50,"
            "aresample=48000,asetpts=PTS-STARTPTS[aout]"
        )
        DEST.parent.mkdir(parents=True,exist_ok=True)
        args=[
            "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
            "-i",str(SOURCE),"-i",str(tail),
            "-filter_complex","[0:v:0]"+",".join(filters)+"[vout];"+audio_filter,
            "-map","[vout]","-map","[aout]",
            "-c:v","libx264","-preset","medium","-crf","22",
            "-maxrate","3200k","-bufsize","6400k","-g","60",
            "-r","30","-pix_fmt","yuv420p","-profile:v","high","-level:v","4.0",
            "-c:a","aac","-b:a","160k","-ar","48000","-ac","2",
            "-t","20","-movflags","+faststart",str(DEST),
        ]
        result=subprocess.run(args,capture_output=True,text=True,timeout=600)
        if result.returncode:
            DEST.unlink(missing_ok=True)
            raise SystemExit("STOP_INTRO_ENCODING_FAILED: "+result.stderr[-1000:])
    done=media_info(DEST)
    v=next(s for s in done["streams"] if s["codec_type"]=="video")
    a=next(s for s in done["streams"] if s["codec_type"]=="audio")
    if not (
        abs(float(done["format"]["duration"])-DURATION)<.09 and
        v["codec_name"]=="h264" and a["codec_name"]=="aac" and
        v["width"]==1280 and v["height"]==720 and
        a["sample_rate"]=="48000" and
        abs(float(v.get("start_time",0)))<.05 and
        abs(float(a.get("start_time",0)))<.05
    ):
        DEST.unlink(missing_ok=True)
        raise SystemExit("STOP_INTRO_20S_MEDIA_VALIDATION_FAILED")
    print("EPIMEDIA_V178_INTRO: 20.00s, 720p 30fps H264/AAC, audio/video zero origin")
    print("STORYBOARD:", " | ".join(row[2] for row in SCENES))
    print("MEDIA_SHA256:",hashlib.sha256(DEST.read_bytes()).hexdigest())
    print("PHYSICAL_GALABOX_AUDIO_SYNC_UNVERIFIED")

if __name__=="__main__":
    render()
