#!/usr/bin/env python3
"""Publish the complete corresponding audio-library source and rebuild recipe."""
from pathlib import Path
import os
import shutil
import tarfile
import tempfile

project = Path(os.environ["PROJECT_ROOT"])
repo = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as temporary:
    package = Path(temporary) / "EpiMediaHub-Audio-1.0.26"
    package.mkdir()
    shutil.copytree(project / "ffmpeg-audio", package / "ffmpeg-audio",
                    ignore=shutil.ignore_patterns("build", ".cxx", "android-libs"))
    shutil.copytree(project / "app/src/main/assets/licenses", package / "licenses")
    for name in ("AUDIO_SOURCES.md", "upstream.json"):
        shutil.copyfile(repo / "android/v1.0.23" / name, package / name)
    shutil.copyfile(repo / "build_tools/build_android_audio_v123.sh", package / "build_android_audio_v123.sh")
    shutil.copyfile(project / "ffmpeg-6.1.6.tar.xz", package / "ffmpeg-6.1.6.tar.xz")
    shutil.copyfile(project / "chromaprint-1.5.1.tar.gz", package / "chromaprint-1.5.1.tar.gz")
    shutil.copyfile(repo / "build_tools/prepare_chromaprint_v126.sh", package / "prepare_chromaprint_v126.sh")
    (package / "build.gradle.kts").write_text('plugins { id("com.android.library") version "8.5.2" apply false }\n')
    (package / "settings.gradle.kts").write_text('''pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }
rootProject.name = "EpiMediaHub-Audio-1.0.26"
include(":ffmpeg-audio")
''')
    destination = repo / "dist/EpiMediaHub_Audio_Sources_v1.0.26.tar.xz"
    destination.parent.mkdir(exist_ok=True)
    with tarfile.open(destination, "w:xz") as archive:
        archive.add(package, arcname=package.name)
    print(f"Corresponding audio source: {destination.name} ({destination.stat().st_size} bytes)")
