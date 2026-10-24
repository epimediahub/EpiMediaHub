#!/usr/bin/env python3
"""v1.0.78: replace caption-only intro with meaningful 20s, offline single-track film.

Only modifies version metadata, packaged intro resource, and player watchdog.
Playback, VPN routing, EpiScene skips and Fire TV licensing stay unchanged.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess

root=Path(os.environ["PROJECT_ROOT"])
here=Path(__file__).resolve().parent
src=here/"epimedia_intro_v9.mp4"
if not src.is_file() or src.is_symlink() or src.stat().st_size<128_000:
    raise SystemExit("v178 expected 20-second intro not rendered")
probe=json.loads(subprocess.check_output([
    "ffprobe","-v","error","-show_format","-show_streams",
    "-of","json",str(src)],text=True))
if abs(float(probe["format"]["duration"])-20.0)>.09:
    raise SystemExit("v178 20s duration not verified")
video=next(s for s in probe["streams"] if s["codec_type"]=="video")
audio=next(s for s in probe["streams"] if s["codec_type"]=="audio")
if video["width"]!=1280 or video["height"]!=720 or video["codec_name"]!="h264" or audio["codec_name"]!="aac":
    raise SystemExit("v178 decoder format mismatch")

def once(path,old,new):
    current=path.read_text(encoding="utf-8")
    if current.count(old)!=1:
        raise SystemExit(f"v178 unexpected {path.name} anchor {old!r}: {current.count(old)}")
    path.write_text(current.replace(old,new,1),encoding="utf-8")

gradle=root/"app/build.gradle.kts"
once(gradle,"versionCode = 1077","versionCode = 1078")
once(gradle,'versionName = "1.0.77"','versionName = "1.0.78"')
app=root/"app/src/main"
dest=app/"res/raw/epimedia_intro_v5.mp4"
if not dest.is_file():
    raise SystemExit("v178 original APK media resource missing")
shutil.copy2(src,dest)

player=app/"java/de/epimediahub/app/ui/V161IntroVideo.kt"
once(player,"delay(20_000L)","delay(23_000L)")
assert "Player.STATE_ENDED" in player.read_text()
assert "introPlayer.playWhenReady = true" in player.read_text()
assert "V161IntroVideoScreen" in (app/"java/de/epimediahub/app/ui/V070Intro.kt").read_text()
print("V178_INTRO_20S_INSTALLED: packaged resource, media-event end, 23s failure watchdog")
