#!/usr/bin/env python3
"""Private QA candidate: lighter 17.5-second cinematic launch intro.

V7 is the exact frame-linked orchestral soundtrack approved in earlier tests.
Render a decoder-friendly H.264/AAC CFR transport with common zero-based
timestamps. Add short explanatory feature captions; never change app preload,
intro duration, playlist playback, logo or licensing.
"""
from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"android/v1.0.65/epimedia_intro_v7.mp4"
DEST=ROOT/"android/v1.0.76/epimedia_intro_v8.mp4"
DURATION=17.5
FONT=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

def info(path):
    output=subprocess.check_output(["ffprobe","-v","error","-show_streams",
                  "-show_format","-of","json",str(path)],text=True)
    return json.loads(output)

def main():
    if not SOURCE.is_file() or SOURCE.is_symlink():
        raise SystemExit("STOP_EXPECTED_SYNCED_V7_MISSING")
    if not FONT.is_file() or shutil.which("ffmpeg") is None:
        raise SystemExit("STOP_FFMPEG_OR_VERIFIED_FONT_MISSING")
    meta=info(SOURCE)
    v=next((s for s in meta["streams"] if s.get("codec_type")=="video"),None)
    a=next((s for s in meta["streams"] if s.get("codec_type")=="audio"),None)
    if v is None or a is None or abs(float(meta["format"]["duration"])-DURATION)>.05:
        raise SystemExit("STOP_UNEXPECTED_V7_MEDIA")
    original_rate=Fraction(v.get("avg_frame_rate","0/1"))
    fps=str(original_rate) if Fraction(20,1)<=original_rate<=Fraction(30,1) else "30"
    # Text is a secondary subtitle band; original EpiMediaHub logo remains intact.
    features=(
        ("LIVE TV  -  EPG & SENDER",1.0,4.4),
        ("FILME & SERIEN  -  INTRO SKIP",4.6,8.3),
        ("SMARTTUBE & SMARTTUBE KIDS",8.5,12.1),
        ("EPISCENE  -  INTELLIGENTE SZENEN",12.3,15.5),
    )
    filters=[f"fps={fps}",
        "scale=1920:1080:force_original_aspect_ratio=decrease",
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "format=yuv420p",
        "setpts=PTS-STARTPTS"]
    for title,start,end in features:
        filters.append(
            "drawtext=fontfile="+str(FONT)+":text='"+title+
            "':fontcolor=white:fontsize=33:bordercolor=black:borderw=2:"
            "x=(w-text_w)/2:y=h*0.84:"
            "enable='between(t,"+str(start)+","+str(end)+")'"
        )
    DEST.parent.mkdir(parents=True,exist_ok=True)
    result=subprocess.run([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-i",str(SOURCE),
        "-map","0:v:0","-map","0:a:0",
        "-vf",",".join(filters),
        "-af","aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS",
        "-c:v","libx264","-preset","medium","-crf","21",
        "-maxrate","4500k","-bufsize","9000k","-g","50",
        "-pix_fmt","yuv420p","-profile:v","high","-level:v","4.1",
        "-c:a","aac","-b:a","192k","-ar","48000","-ac","2",
        "-t","17.5","-movflags","+faststart",
        str(DEST)
    ],capture_output=True,text=True,timeout=600,check=False)
    if result.returncode!=0 or not DEST.is_file():
        raise SystemExit("STOP_PRIVATE_INTRO_ENCODING_FAILED")
    rendered=info(DEST)
    streams=rendered["streams"]
    video=next(s for s in streams if s.get("codec_type")=="video")
    sound=next(s for s in streams if s.get("codec_type")=="audio")
    if (video["codec_name"]!="h264" or sound["codec_name"]!="aac" or
        video["width"]!=1920 or video["height"]!=1080 or
        sound["sample_rate"]!="48000" or
        abs(float(rendered["format"]["duration"])-DURATION)>.07 or
        abs(float(video.get("start_time",0)))>.07 or
        abs(float(sound.get("start_time",0)))>.07):
        DEST.unlink(missing_ok=True)
        raise SystemExit("STOP_INTRO_TRANSPORT_VALIDATION_FAILED")
    print("INTRO_V176_CANDIDATE_VALIDATED: 17.5s 1080p H264 AAC, common start time")
    print("DECODER_COMPATIBILITY_ONLY; PHYSICAL_GALABOX_AV_SYNC_UNVERIFIED")
    print("CAPTIONS: LIVE TV; FILME/SERIEN; SMARTTUBE KIDS; EPISCENE")

if __name__=="__main__":
    main()
