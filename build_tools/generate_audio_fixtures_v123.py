#!/usr/bin/env python3
"""Original short sine tones: no external media, network streams or user playlists."""
from pathlib import Path
import os
import subprocess

root = Path(os.environ["PROJECT_ROOT"])
out = root / "ffmpeg-audio/src/androidTest/assets"
out.mkdir(parents=True, exist_ok=True)
for codec, muxer in (("mp2", "mp2"), ("ac3", "ac3"), ("eac3", "eac3"), ("dca", "dts")):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=997:sample_rate=48000", "-ac", "2", "-frames:a", "1", "-c:a", codec,
                    "-strict", "-2", "-b:a", "192k" if codec == "mp2" else "384k", "-f", muxer,
                    str(out / (codec + ".bin"))], check=True)
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                "sine=frequency=997:sample_rate=48000", "-ac", "2", "-frames:a", "1", "-c:a", "aac",
                "-b:a", "128k", "-f", "adts", str(out / "aac.adts")], check=True)
data = (out / "aac.adts").read_bytes()
assert data[0] == 0xFF and data[1] & 0xF0 == 0xF0
header = 7 if data[1] & 1 else 9
size = ((data[3] & 3) << 11) | (data[4] << 3) | (data[5] >> 5)
(out / "aac.bin").write_bytes(data[header:size])
# A longer MP2 transport stream also exercises Media3 extraction, renderer selection,
# its audio clock and output sink together, rather than just calling a native decoder.
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                "sine=frequency=997:sample_rate=48000", "-ac", "2", "-t", "2", "-c:a", "mp2",
                "-b:a", "192k", "-f", "mpegts", str(out / "mp2-live.ts")], check=True)
print("Generated original MP2, AC-3, E-AC-3, DTS and AAC decoder fixtures")
