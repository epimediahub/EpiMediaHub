#!/usr/bin/env python3
"""v1.0.80: approved 34s EpiScene+VPN cinematic and v1.0.79 SmartTube.

FAIL-CLOSED: 34-second render candidate is generated from the v1.0.78 original-logo footage.
Local rendering/hash verification does NOT authorize public customer distribution.
Real-device and audiovisual acceptance remains mandatory in RELEASE_GATE.json.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

root=Path(os.environ["PROJECT_ROOT"])
here=Path(__file__).resolve().parent
src=here/"epimedia_intro_v10.mp4"
checksum_file=here/"epimedia_intro_v10.sha256"
if not checksum_file.is_file():
    raise SystemExit("STOP_V180_RENDER_CHECKSUM_MISSING")
expected=checksum_file.read_text(encoding="ascii").strip()
if not re.fullmatch(r"[0-9a-f]{64}",expected):
    raise SystemExit("STOP_V180_RENDER_CHECKSUM_INVALID")
if not src.is_file() or src.is_symlink() or src.stat().st_size<2_000_000:
    raise SystemExit("STOP_RENDERED_34S_VIDEO_MISSING")
if hashlib.sha256(src.read_bytes()).hexdigest()!=expected:
    raise SystemExit("STOP_RENDERED_34S_VIDEO_CHECKSUM_MISMATCH")
info=json.loads(subprocess.check_output([
    "ffprobe","-v","error","-show_format","-show_streams",
    "-of","json",str(src)],text=True))
if abs(float(info["format"]["duration"])-34.0)>.05:
    raise SystemExit("STOP_INTRO_DURATION_NOT_34_SECONDS")
v=next((s for s in info["streams"] if s["codec_type"]=="video"),None)
a=next((s for s in info["streams"] if s["codec_type"]=="audio"),None)
if not v or not a or v["codec_name"]!="h264" or a["codec_name"]!="aac" or v["width"]!=1280 or v["height"]!=720:
    raise SystemExit("STOP_APPROVED_INTRO_DECODER_FORMAT_MISMATCH")
if a.get("sample_rate")!="48000" or abs(float(v.get("start_time","0")))>.05:
    raise SystemExit("STOP_APPROVED_INTRO_AUDIO_VIDEO_TIMEBASE_MISMATCH")

def once(path,old,new):
    content=path.read_text(encoding="utf-8")
    if content.count(old)!=1:
        raise SystemExit("STOP_ANDROID_BASELINE_DRIFT: "+str(path)+" : "+old[:90])
    path.write_text(content.replace(old,new,1),encoding="utf-8")

gradle=root/"app/build.gradle.kts"
once(gradle,"versionCode = 1079","versionCode = 1080")
once(gradle,'versionName = "1.0.79"','versionName = "1.0.80"')
main=root/"app/src/main"
video=main/"res/raw/epimedia_intro_v5.mp4"
if not video.is_file():
    raise SystemExit("STOP_PACKAGED_INTRO_RESOURCE_MISSING")
shutil.copy2(src,video)
intro=main/"java/de/epimediahub/app/ui/V161IntroVideo.kt"
# End on Media3 STATE_ENDED. Only on decoder failure, fall back after 38s.
once(intro,"delay(23_000L)","delay(38_000L)")
assert "Player.STATE_ENDED" in intro.read_text()
assert "V161IntroVideoScreen" in (main/"java/de/epimediahub/app/ui/V070Intro.kt").read_text()
assert "onCreatorChannel" in (main/"java/de/epimediahub/app/ui/V112SmartTubePlayer.kt").read_text()
assert "V176SmartTubeQuality" in (main/"java/de/epimediahub/app/ui/V112SmartTubePlayer.kt").read_text()
print("V180_34S_CANDIDATE_PLUS_CREATOR_AND_QUALITY_INSTALLED")
print("SHA256", expected, "duration", info["format"]["duration"])
print("NO_SERVER_OR_FIRETV_LICENSING_CHANGES")
