"""Vaste gereedschappen en uitvoerkanalen uit ADR-0017."""

import re
import subprocess
from pathlib import Path

FFMPEG_MAP = Path("/usr/lib/jellyfin-ffmpeg")
PYTHON = Path("/opt/jelly-leon/python/bin/python3")
VERSIEOPTIES = {"python": "--version", "ffmpeg": "-version", "ffprobe": "-version", "ffsubsync": "--version"}


def bouw_opdracht(tool: str, *argumenten: str) -> list[str]:
    """Accepteer uitsluitend deze volledige opdrachtvormen. Alle media-uitvoer gaat naar stdout."""
    if tool not in VERSIEOPTIES:
        raise ValueError("onbekend gereedschap")
    if tool == "ffsubsync":
        programma = [str(PYTHON), "-IB", str(PYTHON.with_name("ffsubsync")), "--vad", "webrtc"]
    elif tool == "python":
        programma = [str(PYTHON), "-IB"]
    else:
        programma = [str(FFMPEG_MAP / tool)]
    if argumenten == (VERSIEOPTIES[tool],):
        return [*programma, *argumenten]
    match (tool, *argumenten):
        case ("ffmpeg", "-i", bron, "-f", formaat, doel) if Path(bron).is_absolute():
            if (formaat, doel) in {("null", "-"), ("s16le", "pipe:1")}:
                return [*programma, "-nostdin", "-protocol_whitelist", "file,pipe", *argumenten]
        case ("ffsubsync", bron, "-i", ondertitels) if all(Path(p).is_absolute() for p in (bron, ondertitels)):
            # Eén expliciet ondertitelbestand: ffsubsync gebruikt stdout, zonder automatische detectie van buur-bestanden.
            return [*programma, *argumenten]
    raise ValueError("opdracht of uitvoer geweigerd")


def versies() -> dict[str, str]:
    resultaat = {}
    for tool, optie in VERSIEOPTIES.items():
        proces = subprocess.run(
            bouw_opdracht(tool, optie),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            check=True, timeout=15, start_new_session=True,
            env={"PATH": f"{FFMPEG_MAP}:/usr/bin:/bin", "LC_ALL": "C", "OPENBLAS_NUM_THREADS": "1"},
        )
        # FFmpeg en FFprobe tonen na hun versienummer ook bouwopties en bibliotheken.
        banner = proces.stdout.splitlines()
        patroon = rf"{re.escape(tool)} (?:version )?([^\s]+)(?: .*|$)"
        match = banner and re.fullmatch(patroon, banner[0], flags=re.IGNORECASE)
        if not match:
            raise ValueError("versie ontbreekt")
        resultaat[tool] = match[1]
    return resultaat
