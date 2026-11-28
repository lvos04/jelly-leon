"""Eén JSON-object per regel. Elke aanvaarde regel krijgt één antwoord."""

import json
import os
import subprocess
import sys
from typing import BinaryIO, TextIO

from .opdrachten import versies

MAX_BERICHT = 1024 * 1024


def bedien(invoer: BinaryIO, uitvoer: TextIO) -> None:
    while regel := invoer.readline(MAX_BERICHT + 2):
        inhoud = regel.removesuffix(b"\n")
        if len(inhoud) > MAX_BERICHT:
            while regel and not regel.endswith(b"\n"):
                regel = invoer.readline(MAX_BERICHT + 2)
            antwoord = {"fout": "bericht_te_groot"}
        else:
            try:
                verzoek = json.loads(inhoud.decode("utf-8"))
            except (ValueError, RecursionError):
                verzoek = None
            try:
                if verzoek == {"taak": "ping"}:
                    antwoord = {"antwoord": "pong"}
                elif verzoek == {"taak": "versies"}:
                    antwoord = {"versies": versies()}
                else:
                    antwoord = {"fout": "ongeldig_verzoek"}
            except (OSError, ValueError, subprocess.SubprocessError):
                antwoord = {"fout": "gereedschap_onbeschikbaar"}
        print(json.dumps(antwoord), file=uitvoer, flush=True)


def main() -> int:
    if (os.geteuid(), os.getegid()) != (568, 568):
        print("De analysewerker vereist gebruiker en groep 568.", file=sys.stderr)
        return 1
    bedien(sys.stdin.buffer, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
