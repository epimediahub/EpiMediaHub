#!/usr/bin/env python3
"""Render a 34-second EpiMediaHub cinematic QA candidate from the signed-release
v1.0.78 intro. Finale preserves ORIGINAL pixels of the existing EpiMediaHub logo.
This is a candidate; customer release remains gated by physical-device signoff.
"""
import hashlib
import json
import math
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "android/v1.0.78/epimedia_intro_v9.mp4"
DEST = ROOT / "android/v1.0.80/epimedia_intro_v10.mp4"
SIGNATURE = DEST.with_suffix(".sha256")
RATE = 48000
SECONDS = 34
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
STORY = [
  (2.0, 4.25, "EPIMEDIA PLAYER", "Live-TV, Filme und Serien", "Dein Entertainment. Einfach an einem Ort."),
  (4.25, 8.5, "DAS IST EPISCENE", "Ein intelligenter Szenen-Analysator", "Erkennt, was in deinen Serien wirklich passiert."),
  (8.5, 13.0, "EPISCENE / ERKENNEN", "Intro, Rückblick und Abspann", "Automatische Zeitmarker direkt im Player."),
  (13.0, 18.0, "EPISCENE / ÜBERSPRINGEN", "Weniger suchen. Mehr erleben.", "Intro-Skip, Recap-Skip und nächste Folge."),
  (18.0, 23.0, "EPISCENE / LERNEN", "Wird mit jeder Bestätigung besser", "Nutzt bestätigte Marker und vertrauenswürdige Quellen."),
  (23.0, 26.5, "EPISCENE / PLAYLISTEN", "Gelerntes mehrfach nutzen", "Passende Episoden auch bei anderen Anbietern erkennen."),
  (26.5, 29.0, "VPN & SMARTTUBE", "Mehr Kontrolle, wenn du sie brauchst", "VPN pro Playlist · Videoqualität · Creator-Kanäle."),
]

def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise SystemExit("STOP_V180_VIDEO_RENDER_FAILED: " + result.stderr[-1600:])

def beats(path):
    moments = [0.5, 3.6, 5.4, 8.55, 13.0, 18.0, 23.0, 26.5, 29.15, 32.25]
    pcm = array("h")
    for index in range(RATE * SECONDS):
        t = index / RATE
        value = 0.0
        for time in moments:
            for delay, volume in ((0.0, 1.0), (0.24, 0.55)):
                q = t - time - delay
                if 0 <= q < .6:
                    env = min(1.0, q / .007) * math.exp(-q / .095)
                    hz = 58 + 26 * math.exp(-q / .05)
                    value += volume * env * (math.sin(2 * math.pi * hz * q) +
                                            .3 * math.sin(4 * math.pi * hz * q))
        v = round(7300 * max(-1, min(1, value)))
        pcm.extend((v, v))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(pcm.tobytes())

def escape(path):
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

def render():
    if not SOURCE.is_file() or SOURCE.is_symlink():
        raise SystemExit("STOP_V180_SIGNED_RELEASE_SOURCE_INTRO_MISSING")
    if not all(Path(p).is_file() for p in (FONT, BOLD)):
        raise SystemExit("STOP_V180_FONT_MISSING")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="epimedia-v180-") as directory:
        temp = Path(directory)
        for name, time in (("earth.jpg", 14.35), ("logo.jpg", 17.25)):
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(time),
                 "-i", str(SOURCE), "-frames:v", "1", "-q:v", "2", str(temp / name)])
        pulse = temp / "hearts.wav"
        beats(pulse)
        video = (
          "[0:v]trim=start=0:end=15,setpts=PTS-STARTPTS,"
          "crop=1280:435:0:0,pad=1280:720:0:0:color=0x010814,setsar=1,fps=30[v0];"
          "[1:v]crop=1280:435:0:0,scale=1320:450,setsar=1,"
          "zoompan=z='min(zoom+0.00015,1.09)':"
          "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
          "d=420:s=1280x435:fps=30,trim=duration=14,setpts=PTS-STARTPTS,"
          "pad=1280:720:0:0:color=0x010814,setsar=1[v1];"
          "[2:v]scale=1280:720,crop=1280:435:0:0,loop=149:1:0,"
          "trim=duration=5,setpts=PTS-STARTPTS,"
          "pad=1280:720:0:0:color=0x010814,setsar=1,fps=30[v2];"
          "[v0][v1][v2]concat=n=3:v=1:a=0,format=yuv420p,"
          "drawbox=x=0:y=435:w=1280:h=285:color=0x010916@1:t=fill"
        )
        for n, (start, end, heading, title, detail) in enumerate(STORY):
            for i, phrase in enumerate((heading, title, detail)):
                (temp / f"scene{n}_{i}.txt").write_text(phrase, encoding="utf-8")
            enable = f"between(t,{start},{end})"
            alpha = f"max(0,min(1,min((t-{start})/0.35,({end}-t)/0.32)))"
            video += (f",drawbox=x=65:y=512:w=5:h=148:"
                      f"color=0x46E5D2@0.95:t=fill:enable='{enable}'")
            for i, (size, y, color, font) in enumerate((
                  (21, 514, "0x45E7D4", BOLD), (37, 552, "white", BOLD),
                  (21, 620, "0xDFEAF6", FONT))):
                path = escape(temp / f"scene{n}_{i}.txt")
                video += (f",drawtext=fontfile='{escape(font)}':textfile='{path}':"
                          f"fontcolor={color}:fontsize={size}:x=95:y={y}:"
                          f"alpha='{alpha}':enable='{enable}'")
        tagline = temp / "tagline.txt"
        tagline.write_text("EpiMediaHub · Intelligent schauen.", encoding="utf-8")
        video += (
          f",drawtext=fontfile='{escape(BOLD)}':textfile='{escape(tagline)}':"
          "fontcolor=0xEAF4FF:fontsize=28:x=(w-text_w)/2:y=564:"
          "alpha='max(0,min(1,(t-29.5)/0.65))':"
          "enable='between(t,29,34)'[vout]"
        )
        audio = (
          "[0:a]atrim=duration=18,asetpts=PTS-STARTPTS[a0];"
          "[0:a]atrim=duration=17,asetpts=PTS-STARTPTS[a1];"
          "[a0][a1]acrossfade=d=1:c1=tri:c2=tri,"
          "atrim=duration=34,volume=0.85[bg];"
          "[3:a]atrim=duration=34,volume=1.0[beat];"
          "[bg][beat]amix=inputs=2:duration=longest:normalize=0,"
          "alimiter=limit=0.95:level=disabled,"
          "afade=t=out:st=33.3:d=0.7,"
          "atrim=duration=34,asetpts=PTS-STARTPTS[aout]"
        )
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(SOURCE),
             "-loop", "1", "-framerate", "30", "-t", "14", "-i", str(temp / "earth.jpg"),
             "-loop", "1", "-framerate", "30", "-t", "5", "-i", str(temp / "logo.jpg"),
             "-i", str(pulse), "-filter_complex", video + ";" + audio,
             "-map", "[vout]", "-map", "[aout]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-maxrate", "2600k", "-bufsize", "5200k", "-r", "30",
             "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
             "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
             "-t", "34", "-movflags", "+faststart", str(DEST)])
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error",
                   "-show_format", "-show_streams", "-of", "json", str(DEST)],
                   text=True))
    video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert abs(float(probe["format"]["duration"]) - 34) < .09
    assert video_stream["width"] == 1280 and video_stream["height"] == 720
    assert video_stream["codec_name"] == "h264" and audio_stream["codec_name"] == "aac"
    assert audio_stream["sample_rate"] == "48000"
    digest = hashlib.sha256(DEST.read_bytes()).hexdigest()
    SIGNATURE.write_text(digest + "\n", encoding="ascii")
    print("V180_34S_INTRO_CANDIDATE_RENDERED", digest, DEST.stat().st_size)
    print("RELEASE_REQUIRES_MANUAL_QA_AND_ORIGINAL_LOGO_REVIEW")

if __name__ == "__main__":
    render()
