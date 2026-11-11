#!/usr/bin/env python3
"""Bewijst dat de analyzer van verboden API's een echte build laat falen (B03-017, ADR-0032).

De proefassembly `plugins/JellyLeon/analyzers/Jellyfin.Plugin.JellyLeon.VerbodenProef` bevat elke verboden aanroep.
Elke regel met de markering `// VERWACHT: JLxxxx` moet precies die bouwfout geven, geen enkele andere regel mag een
JL-fout geven, en de build mag om geen andere reden falen.

Gebruik:
  analyzer_proef.py --bouw                 bouwt de proefassembly met `dotnet build` en beoordeelt de uitvoer
  analyzer_proef.py --log <bouwlog>        beoordeelt een eerder opgeslagen bouwlog (bijvoorbeeld uit een container)

Alleen standaardbibliotheek. Exitcodes: 0 = in orde, 1 = afwijking, 3 = gebruiks-/omgevingsfout.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROEF_MAP = REPO_ROOT / "plugins/JellyLeon/analyzers/Jellyfin.Plugin.JellyLeon.VerbodenProef"
PROEF_BRON = PROEF_MAP / "VerbodenAanroepen.cs"
PROEF_PROJECT = PROEF_MAP / "Jellyfin.Plugin.JellyLeon.VerbodenProef.csproj"
REGELS = ("JL0001", "JL0002", "JL0003", "JL0004")
MARKERING_RE = re.compile(r"// VERWACHT: (JL\d{4})\b")
FOUT_RE = re.compile(r"(?P<bestand>[^\s(]+)\((?P<regel>\d+),\d+\): error (?P<code>[A-Z]+\d+):")
LOSSE_FOUT_RE = re.compile(r"\berror (?P<code>[A-Z]+\d+):")


def verwachte_fouten(bron: str) -> set[tuple[int, str]]:
    """Leest de markeringen uit de proefbron: (regelnummer, regel-id)."""
    verwacht: set[tuple[int, str]] = set()
    for nummer, tekst in enumerate(bron.splitlines(), start=1):
        raak = MARKERING_RE.search(tekst)
        if raak:
            verwacht.add((nummer, raak.group(1)))
    return verwacht


def gevonden_fouten(log: str, bestandsnaam: str) -> tuple[set[tuple[int, str]], set[str]]:
    """Geeft de JL-fouten in de proefbron en de codes van alle andere fouten in de bouwlog."""
    gevonden: set[tuple[int, str]] = set()
    andere: set[str] = set()
    for tekst in log.splitlines():
        raak = FOUT_RE.search(tekst)
        if raak and raak.group("code").startswith("JL") and Path(raak.group("bestand")).name == bestandsnaam:
            gevonden.add((int(raak.group("regel")), raak.group("code")))
            continue
        los = LOSSE_FOUT_RE.search(tekst)
        if los:
            andere.add(los.group("code"))
    return gevonden, andere


def beoordeel(bron: str, log: str, *, bestandsnaam: str = PROEF_BRON.name, exitcode: int | None = None) -> list[str]:
    """Geeft de lijst afwijkingen; leeg = de analyzer doet precies wat de proefbron verwacht."""
    problemen: list[str] = []
    verwacht = verwachte_fouten(bron)
    gevonden, andere = gevonden_fouten(log, bestandsnaam)
    for regel_id in REGELS:
        if not any(code == regel_id for _, code in verwacht):
            problemen.append(f"de proefbron bevat geen enkele verwachte fout voor {regel_id}")
    if exitcode == 0:
        problemen.append("de build van de proefassembly is geslaagd; hij hoort te falen")
    for nummer, code in sorted(verwacht - gevonden):
        problemen.append(f"regel {nummer}: verwachte bouwfout {code} ontbreekt")
    for nummer, code in sorted(gevonden - verwacht):
        problemen.append(f"regel {nummer}: onverwachte bouwfout {code}")
    for code in sorted(andere):
        problemen.append(f"de build faalt ook om een andere reden ({code}); alleen de eigen regels mogen hem laten falen")
    return problemen


def bouw() -> tuple[int, str]:
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise RuntimeError("dotnet niet gevonden; gebruik --log met een bouwlog uit de SDK-image")
    uitkomst = subprocess.run(
        [dotnet, "build", str(PROEF_PROJECT), "-c", "Release", "--nologo"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    return uitkomst.returncode, uitkomst.stdout + uitkomst.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    groep = parser.add_mutually_exclusive_group(required=True)
    groep.add_argument("--bouw", action="store_true", help="bouw de proefassembly en beoordeel de uitvoer")
    groep.add_argument("--log", type=Path, help="beoordeel een opgeslagen bouwlog")
    parser.add_argument("--exitcode", type=int, default=None, help="exitcode van de build die bij --log hoort")
    args = parser.parse_args(argv)

    try:
        bron = PROEF_BRON.read_text(encoding="utf-8")
        if args.bouw:
            exitcode, log = bouw()
        else:
            exitcode, log = args.exitcode, args.log.read_text(encoding="utf-8")
    except (OSError, RuntimeError) as exc:
        print(f"analyzer_proef: {exc}", file=sys.stderr)
        return 3

    problemen = beoordeel(bron, log, exitcode=exitcode)
    if problemen:
        for probleem in problemen:
            print(f"analyzer_proef: {probleem}", file=sys.stderr)
        return 1
    aantal = len(verwachte_fouten(bron))
    print(f"analyzer_proef: in orde — {aantal} verboden aanroepen geven elk precies de verwachte bouwfout; de build faalt alleen daardoor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
