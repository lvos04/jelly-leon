"""Eén corpusgenerator voor alle recepten van F1–F6 (B03-016 deel a).

    python -m b03h corpus lijst
    python -m b03h corpus maak <recept> [--schaal klein|vol] [--seed N] [--ffmpeg docker|host] [--param k=v …] [--bevries]
    python -m b03h corpus controleer <setmap>          # = sha256sum -c SHA256SUMS + extra/ontbrekende bestanden
    python -m b03h corpus bron-controle                # sha256sum -c voor bron/ en afgeleid/ van het corpus
    python -m b03h corpus opruimen <setmap>|--alles    # BG-38: testset weg, recept en bevroren manifest blijven

Uitvoer staat buiten de repo (``B03_UITVOER``). Een set wordt in ``.bouw-…`` gemaakt en pas na het manifest atomair
hernoemd naar ``<recept>-v<versie>-<schaal>-s<seed>``. ``--bevries`` legt het manifest vast in
``docs/platform-v2/test-evidence/b03-016-corpus/`` (alleen sha256's); bestaat dat al, dan moet de nieuwe generatie
exact gelijk zijn (reproduceerbaarheid).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..guard import MARKERING
from . import CORPUS, UITVOER, manifest
from .basis import Context
from .ffmpeg import Ffmpeg
from .r_ass_groot import maak_ass, maak_groot
from .r_f1_framecode import maak as f1
from .r_f2_dsyn import maak as f2
from .r_f3_ondertitels import maak as f3
from .r_f4_tqc import maak as f4
from .r_f5_fouten import maak as f5
from .r_f6_segmenten import maak as f6

REPO = Path(__file__).resolve().parents[4]
BEVROREN = REPO / "docs" / "platform-v2" / "test-evidence" / "b03-016-corpus"


@dataclass(frozen=True)
class Recept:
    naam: str
    versie: str
    functie: str
    omschrijving: str
    maak: Callable[[Context], None]
    seed: int = 20261109


RECEPTEN = {r.naam: r for r in [
    Recept("f1-framecode", "1", "F1", "framecode-raster over hero.mp4 (16 binaire blokken + tijdcode)", f1),
    Recept("f2-dsyn", "1", "F2", "D-SYN: 300 stub-items met NFO en 3 huishoudens met verborgen voorkeur", f2),
    Recept("f3-ondertitels", "1", "F3", "ondertitelgenerators per fouttype, kalibratie- en testsplit", f3),
    Recept("f4-tqc", "1", "F4", "T-QC (gate) en N-QC-rommelig met framemd5-grondwaarheid", f4),
    Recept("f5-fouten", "1", "F5", "gecontroleerde-foutenset (liegende codecs, geforceerd Android-profiel) + ASS", f5),
    Recept("f6-segmenten", "1", "F6", "segmenttestset met augmentatie en post-credit-varianten", f6),
    Recept("ass", "1", "F5", "Sintel 120–180 s met NL-ondertitel als ASS", maak_ass),
    Recept("groot-bestand", "1", "F4/F5", "groot testbestand via stream-copy (≤ 20 GB, standaard klein)", maak_groot),
]}


def setnaam(recept: Recept, schaal: str, seed: int) -> str:
    return f"{recept.naam}-v{recept.versie}-{schaal}-s{seed}"


def _markeer_beperkt(map_: Path) -> None:
    """Elke JSON in een beperkte set krijgt de markering, zodat de CI-guard hem ook hernoemd herkent."""
    for pad in map_.rglob("*.json"):
        data = json.loads(pad.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["markering"] = MARKERING + " — afgeleid van beperkt gelicentieerde bron; nooit committen (BG-37)"
            pad.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (map_ / "LICENTIE-BEPERKT.txt").write_text(
        f"{MARKERING}\nDeze testset bevat materiaal of labels van een bron met een beperkende licentie (BG-37).\n"
        "Alleen lokaal gebruiken; nooit in een repo of image. Na de test opruimen (BG-38).\n", encoding="utf-8")


def maak(naam: str, *, schaal: str = "klein", seed: int | None = None, ffmpeg: str = "docker",
         parameters: dict | None = None, uitvoer: Path = UITVOER, corpus: Path = CORPUS, bevries: bool = False,
         vervang: bool = False, map_bevroren: Path = BEVROREN) -> tuple[Path, dict]:
    recept = RECEPTEN[naam]
    seed = recept.seed if seed is None else seed
    uitvoer.mkdir(parents=True, exist_ok=True)
    doel = uitvoer / setnaam(recept, schaal, seed)
    if doel.exists():
        if not vervang:
            raise FileExistsError(f"{doel} bestaat al (gebruik --vervang of ruim eerst op)")
        shutil.rmtree(doel)
    bouw = uitvoer / f".bouw-{doel.name}-{os.getpid()}"
    shutil.rmtree(bouw, ignore_errors=True)
    bouw.mkdir(parents=True)
    ff = Ffmpeg(ffmpeg, alleen_lezen=[corpus], schrijfbaar=[bouw])
    ctx = Context(corpus=corpus, uit=bouw, seed=seed, schaal=schaal, ff=ff, parameters=dict(parameters or {}))
    begin = time.monotonic()
    try:
        recept.maak(ctx)
        if ctx.beperkt:
            _markeer_beperkt(bouw)
        m = manifest.maak(bouw, recept=recept.naam, versie=recept.versie, seed=seed, schaal=schaal,
                          parameters=ctx.parameters, ffmpeg=ff.versie(), bronnen=sorted(ctx.bronnen.values(), key=lambda b: b["pad"]),
                          licenties=sorted(ctx.licenties), beperkt=ctx.beperkt, aantallen=dict(sorted(ctx.aantallen.items())))
        m["duur_s"] = round(time.monotonic() - begin, 1)
        manifest.schrijf(bouw, m)
        os.replace(bouw, doel)
    except BaseException:
        shutil.rmtree(bouw, ignore_errors=True)
        raise
    if bevries:
        pad, uitkomst = manifest.bevries(m, map_bevroren)
        m["bevroren"] = {"pad": str(pad.relative_to(REPO)) if pad.is_relative_to(REPO) else str(pad), "uitkomst": uitkomst}
    return doel, m


def sha256sum_c(map_: Path, sommen: Path) -> tuple[bool, str]:
    """Draait het echte `sha256sum -c` (acceptatie B03-016: 'sha256sum -c groen voor bron en afgeleid')."""
    uit = subprocess.run(["sha256sum", "--quiet", "-c", str(sommen)], cwd=map_, capture_output=True, text=True, check=False)
    return uit.returncode == 0, (uit.stdout + uit.stderr).strip()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h corpus")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lijst")
    pm = sub.add_parser("maak")
    pm.add_argument("recept", choices=sorted(RECEPTEN))
    pm.add_argument("--schaal", choices=["klein", "vol"], default="klein")
    pm.add_argument("--seed", type=int)
    pm.add_argument("--ffmpeg", choices=["docker", "host"], default="docker")
    pm.add_argument("--param", action="append", default=[], metavar="k=v")
    pm.add_argument("--uitvoer", type=Path, default=UITVOER)
    pm.add_argument("--bevries", action="store_true")
    pm.add_argument("--vervang", action="store_true")
    pc = sub.add_parser("controleer")
    pc.add_argument("set", type=Path)
    sub.add_parser("bron-controle")
    po = sub.add_parser("opruimen")
    po.add_argument("set", type=Path, nargs="?")
    po.add_argument("--alles", action="store_true")
    a = p.parse_args(argv)

    if a.cmd == "lijst":
        for r in RECEPTEN.values():
            print(f"{r.naam:16} v{r.versie}  {r.functie:6} {r.omschrijving}")
        return 0
    if a.cmd == "maak":
        params = {}
        for kv in a.param:
            k, _, v = kv.partition("=")
            params[k] = json.loads(v) if v[:1] in "[{0123456789-tf" and v not in ("", "-") else v
        doel, m = maak(a.recept, schaal=a.schaal, seed=a.seed, ffmpeg=a.ffmpeg, parameters=params, uitvoer=a.uitvoer,
                       bevries=a.bevries, vervang=a.vervang)
        print(json.dumps({"set": str(doel), "set_sha256": m["set_sha256"], "bestanden": len(m["bestanden"]),
                          "totaal_bytes": m["totaal_bytes"], "aantallen": m["aantallen"], "beperkt": m["licentie_beperkt"],
                          "duur_s": m["duur_s"], "bevroren": m.get("bevroren")}, ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "controleer":
        m = json.loads((a.set / "manifest.json").read_text(encoding="utf-8"))
        fouten = manifest.controleer(a.set, m)
        ok, uit = sha256sum_c(a.set, a.set / "SHA256SUMS")
        print(json.dumps({"set": str(a.set), "sha256sum_c": "OK" if ok else uit[-500:], "fouten": fouten}, ensure_ascii=False))
        return 0 if ok and not fouten else 1
    if a.cmd == "bron-controle":
        resultaat, ok_alles = {}, True
        for map_, sommen in (("bron", "SHA256SUMS.bron.txt"), ("bron", "SHA256SUMS.ondertitels.txt"),
                             ("afgeleid", "SHA256SUMS.afgeleid.txt")):
            ok, uit = sha256sum_c(CORPUS / map_, CORPUS / sommen)
            regels = sum(1 for r in (CORPUS / sommen).read_text(encoding="utf-8").splitlines() if r.strip())
            resultaat[sommen] = {"ok": ok, "bestanden": regels, **({} if ok else {"uitvoer": uit[-800:]})}
            ok_alles &= ok
        print(json.dumps(resultaat, ensure_ascii=False, indent=1))
        return 0 if ok_alles else 1
    if a.cmd == "opruimen":
        doelen = sorted(UITVOER.glob("*")) if a.alles else [a.set]
        for d in doelen:
            if d and d.exists() and d.resolve().is_relative_to(UITVOER.resolve()):
                shutil.rmtree(d)
                print(f"opgeruimd: {d}")
            elif d:
                print(f"geweigerd (niet onder {UITVOER}): {d}", file=sys.stderr)
                return 1
        return 0
    return 2
