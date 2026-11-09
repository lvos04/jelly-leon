#!/usr/bin/env python3
"""Synthetisch mini-corpus voor CI (het echte corpus blijft lokaal, BG-37): dezelfde paden als het echte corpus voor de
items die de clientmatrix-rooktest gebruikt. Alleen lavfi-materiaal, geen rechten van derden.

    python3 tools/b03-harnas/ci_mini_corpus.py <corpusmap> [--ffmpeg-docker IMAGE]
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("corpus", type=Path)
    p.add_argument("--ffmpeg-docker", help="jellyfin-ffmpeg uit deze image gebruiken (zelfde binary als lokaal)")
    a = p.parse_args()
    bron = a.corpus.resolve() / "bron"
    for sub in ("blender/hero", "blender/sintel"):
        (bron / sub).mkdir(parents=True, exist_ok=True)

    def ffmpeg(*args: str) -> None:
        if a.ffmpeg_docker:
            cmd = ["docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{bron}:{bron}",
                   "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffmpeg", a.ffmpeg_docker]
        else:
            cmd = ["ffmpeg"]
        subprocess.run([*cmd, "-v", "error", "-y", *args], check=True)

    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x536:r=24000/1001:d=40", "-f", "lavfi", "-i", "sine=f=440:r=48000:d=40",
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "aac", "-b:a", "128k",
           "-movflags", "+faststart", "-shortest", str(bron / "blender/hero/hero.mp4"))
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x544:r=24:d=40", "-f", "lavfi", "-i", "sine=f=330:r=48000:d=40",
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-af", "pan=5.1|FL=c0|FR=c0|FC=c0|LFE=c0|BL=c0|BR=c0",
           "-c:a", "ac3", "-b:a", "384k", "-shortest", str(bron / "blender/sintel/Sintel.2010.1080p.mkv"))
    print(f"mini-corpus klaar in {a.corpus}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
