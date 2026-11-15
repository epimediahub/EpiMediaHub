#!/usr/bin/env python3
"""Set the release version and install the approved 10-second launch video."""

import hashlib
import os
import shutil
from pathlib import Path


APP = Path(os.environ["PROJECT_ROOT"]) / "app"
INTRO = Path(__file__).with_name("EpiMediaHub_Intro_10s.mp4")
INTRO_SHA256 = "465d8d9af4f1989dd11f8174538b89f791916a3b810d89a80f5a046ce3dc2d54"
INTRO_RESOURCE = APP / "src/main/res/raw/epimedia_intro_v5.mp4"

if hashlib.sha256(INTRO.read_bytes()).hexdigest() != INTRO_SHA256:
    raise SystemExit("The 10-second video differs from the approved intro.")
if not INTRO_RESOURCE.is_file():
    raise SystemExit(f"Missing launch video resource: {INTRO_RESOURCE}")

gradle = APP / "build.gradle.kts"
build_config = gradle.read_text(encoding="utf-8")
for old, new in (
    ("versionCode = 1093", "versionCode = 1094"),
    ('versionName = "1.0.93"', 'versionName = "1.0.94"'),
):
    if build_config.count(old) != 1:
        raise SystemExit(f"Expected one {old!r} in {gradle}")
    build_config = build_config.replace(old, new, 1)

shutil.copyfile(INTRO, INTRO_RESOURCE)
gradle.write_text(build_config, encoding="utf-8")
