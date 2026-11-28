"""Offline proef op de opgeleverde image, inclusief de JSON-procesgrens."""

import json
import sqlite3
import ssl
import stat
import subprocess
import sys

from .inventaris import MAP, vergelijk_versies
from .opdrachten import PYTHON


def controleer_rechten() -> None:
    for pad in (MAP, *MAP.rglob("*")):
        info = pad.lstat()
        if (info.st_uid, info.st_gid) != (0, 0):
            raise ValueError("de runtime bevat een bestand met een afwijkende eigenaar")
        if stat.S_ISLNK(info.st_mode):
            if not pad.resolve(strict=True).is_relative_to(MAP):
                raise ValueError("koppeling verlaat de runtime")
        elif info.st_mode & 0o022:
            raise ValueError("de runtime bevat een beschrijfbaar bestand of een beschrijfbare map")


def rookproef(alleen_werker: bool) -> None:
    import webrtcvad  # Alleen de vastgezette runtime heeft deze extensie.

    controleer_rechten()
    ssl.create_default_context()
    with sqlite3.connect(":memory:") as db:
        db.execute("SELECT 1").fetchone()
    if webrtcvad.Vad(1).is_speech(bytes(640), 16000):
        raise ValueError("de WebRTC-proef herkende de synthetische stilte niet")
    proces = subprocess.run(
        [str(PYTHON), "-IB", "-m", "jl_werker"], input='{"taak":"ping"}\n{"taak":"versies"}\n{"taak":"ping"}\n',
        text=True, capture_output=True, check=True, timeout=65,
    )
    eerste, antwoord, laatste = map(json.loads, proces.stdout.splitlines())
    if eerste != {"antwoord": "pong"} or laatste != eerste:
        raise ValueError("de werker beantwoordde de twee pings niet")
    bestanden = ["werker.cdx.json"] if alleen_werker else ["werker.cdx.json", "image.cdx.json"]
    for bestand in bestanden:
        vergelijk_versies(json.loads((MAP / bestand).read_text()), antwoord["versies"])
    print(json.dumps(antwoord["versies"], sort_keys=True))
    print("Rookproef: twee pings, vier gereedschapsversies, WebRTC en bestandsrechten gecontroleerd.")


if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["--alleen-werker"]):
        sys.exit("Verwacht hooguit --alleen-werker.")
    rookproef(bool(sys.argv[1:]))
