"""ffmpeg/ffprobe voor de recepten.

Standaard de **jellyfin-ffmpeg uit de vastgezette stock-image** (``--ffmpeg docker``): dezelfde binary op de
ontwikkelmachine en in CI, dus dezelfde sha256 bij dezelfde seed. ``--ffmpeg host`` is alleen voor snelle unittests
(reproduceerbaar binnen dezelfde binary; het manifest legt de versie vast). De container draait zonder netwerk, als de
eigen gebruiker en met de bron alleen-lezen gekoppeld op hetzelfde pad.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

JL_IMAGE = "docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771"
JF_BIN = "/usr/lib/jellyfin-ffmpeg"
# Bitexact: geen encoderversie/willekeurige UID's in de container, geen metadata of hoofdstukken uit de bron.
# '-threads 1' (encoders): gemeten op 2026-11-09 gaf libx264 met meerdere threads per run een andere uitvoer.
# '-max_interleave_delta 0': de muxer wacht altijd op alle stromen; anders kan audio die > 10 s voorloopt (snelle
# audio-encoder, trage video-encoder) per run anders verweven worden en verschilt de sha256.
BITEXACT = ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1",
            "-map_chapters", "-1", "-threads", "1", "-max_interleave_delta", "0"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


class FfmpegFout(RuntimeError):
    pass


class Ffmpeg:
    def __init__(self, modus: str = "docker", image: str = JL_IMAGE, alleen_lezen: Sequence[Path] = (),
                 schrijfbaar: Sequence[Path] = (), cpus: int = 4, geheugen: str = "2g") -> None:
        if modus not in ("docker", "host"):
            raise ValueError("modus is docker of host")
        if modus == "host" and not shutil.which("ffmpeg"):
            raise FfmpegFout("geen ffmpeg op de host")
        self.modus, self.image, self.cpus, self.geheugen = modus, image, cpus, geheugen
        self.alleen_lezen = [Path(p).resolve() for p in alleen_lezen]
        self.schrijfbaar = [Path(p).resolve() for p in schrijfbaar]
        self._versie: str | None = None

    def _cmd(self, programma: str, args: Sequence[str]) -> list[str]:
        if self.modus == "host":
            return [programma, *args]
        cmd = ["docker", "run", "--rm", "-i", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
               "--cpus", str(self.cpus), "--memory", self.geheugen, "--security-opt", "no-new-privileges",
               "--cap-drop", "ALL", "--entrypoint", f"{JF_BIN}/{programma}"]
        for p in self.alleen_lezen:
            cmd += ["-v", f"{p}:{p}:ro"]
        for p in self.schrijfbaar:
            cmd += ["-v", f"{p}:{p}"]
        return [*cmd, self.image, *args]

    def ffmpeg(self, args: Sequence[str], timeout: float = 3600) -> str:
        volledig = ["-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args]
        uit = subprocess.run(self._cmd("ffmpeg", volledig), capture_output=True, text=True, timeout=timeout, check=False)
        if uit.returncode != 0:
            raise FfmpegFout(f"ffmpeg faalde ({uit.returncode}): {uit.stderr.strip()[-800:]}\nargs: {' '.join(args)[:600]}")
        return uit.stderr

    def ffmpeg_ruw(self, args: Sequence[str], timeout: float = 3600) -> subprocess.CompletedProcess[bytes]:
        """Zonder controle op de exitcode (voor decodeerproeven van beschadigde bestanden) en met bytes-uitvoer."""
        return subprocess.run(self._cmd("ffmpeg", ["-hide_banner", "-nostdin", *args]), capture_output=True,
                              timeout=timeout, check=False)

    def ffprobe(self, pad: Path, *extra: str) -> dict[str, Any]:
        args = ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", *extra, str(pad)]
        uit = subprocess.run(self._cmd("ffprobe", args), capture_output=True, text=True, timeout=600, check=False)
        if uit.returncode != 0:
            raise FfmpegFout(f"ffprobe faalde op {pad}: {uit.stderr.strip()[-400:]}")
        return json.loads(uit.stdout or "{}")

    def pakketten(self, pad: Path, stroom: str) -> list[dict[str, Any]]:
        """Pakketten (pts_time, pos, size) van één stroom, bv. 'v:0' of 'a:0'."""
        data = self.ffprobe(pad, "-select_streams", stroom, "-show_entries", "packet=pts_time,dts_time,pos,size,flags",
                            "-show_packets")
        return [p for p in data.get("packets", []) if p.get("pos") not in (None, "N/A")]

    def versie(self) -> dict[str, str]:
        if self._versie is None:
            uit = subprocess.run(self._cmd("ffmpeg", ["-hide_banner", "-version"]), capture_output=True, text=True,
                                 timeout=120, check=False)
            self._versie = (uit.stdout.splitlines() or ["onbekend"])[0]
        info = {"modus": self.modus, "versie": self._versie}
        if self.modus == "docker":
            info["image"] = self.image
        return info

    def framemd5(self, pad: Path, stroom: str = "v:0") -> list[str]:
        """Decodeert en geeft per frame de md5 (grondwaarheid 'effectief beschadigd' = afwijking van de referentie)."""
        uit = self.ffmpeg_ruw(["-loglevel", "quiet", "-err_detect", "ignore_err", "-i", str(pad), "-map", f"0:{stroom}",
                               "-f", "framemd5", "-"])
        return [r.split(",")[-1].strip() for r in uit.stdout.decode("utf-8", "replace").splitlines()
                if r and not r.startswith("#")]
