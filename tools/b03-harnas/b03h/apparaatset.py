"""De afgesproken sets voor B03-060. De opgeslagen manifesten bevatten alleen identificatie en SHA-256."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .baseline import A5_SET, EVIDENCE_MAP, EXTRA_SET
from .corpus import manifest
from .corpus.generator import BEVROREN, RECEPTEN, setnaam
from .stock import KOPPELINGEN

BEWIJS = EVIDENCE_MAP / "b03-060-meetsets.json"
ASS_MAP = "/media/b03-ass"


def setmap(sets: Path, recept: str) -> Path:
    r = RECEPTEN[recept]
    return sets / setnaam(r, "vol", r.seed)


def media_pad(serverpad: str, corpus: Path) -> Path:
    for doel, bron in KOPPELINGEN.items():
        if serverpad.startswith(doel + "/"):
            return corpus / bron / serverpad.removeprefix(doel + "/")
    raise ValueError(f"geen corpusbron voor {serverpad}")


def samenstellen(sets: Path, corpus: Path) -> dict:
    """Toets de gegenereerde bestanden tegen de ingecheckte B03-016-manifesten, ook vóór gebruik van een init-script."""
    recepten = {}
    for recept in ("f5-fouten", "ass"):
        bevroren = json.loads((BEVROREN / f"{recept}.v1.vol.manifest.json").read_text())
        fouten = manifest.controleer(setmap(sets, recept), bevroren)
        if fouten:
            raise ValueError(f"{recept}: {fouten[0]}")
        recepten[recept] = bevroren["set_sha256"]
    f5 = setmap(sets, "f5-fouten")
    grond = json.loads((f5 / "grondwaarheid.json").read_text())
    formaten = json.loads((corpus / "afgeleid/formaten/formaten.grondwaarheid.json").read_text())
    if len(formaten) != 11:
        raise ValueError("het formaatcorpus moet elf gevallen bevatten")
    ass = "formaten/sintel-60s-ass.mkv"
    normaal = {"a5": A5_SET, "extra": EXTRA_SET, "formaten": [f"/media/afgeleid/formaten/{n}" for n in sorted(formaten)],
               "ass": [f"{ASS_MAP}/{ass}"], "srt": ["/media/movies/blender/sintel/Sintel.2010.1080p.mkv"]}
    groepen = {g: [{"id": Path(p).name, "pad": p} for p in paden] for g, paden in normaal.items()}
    for groep in ("devset", "testset"):
        groepen[groep] = []
        for c in grond[groep]:
            bron = c["item"]
            pad = "/media/afgeleid/" + bron[9:] if bron.startswith("afgeleid:") else "/media/movies/" + bron
            regel = {"id": c["id"], "pad": pad, "client": c["client"]}
            middel = c.get("middel") or (f"init-scripts/{c['id']}.js" if c["liegt_over"] else None)
            if middel:
                regel.update(middel=middel, middel_sha256=manifest.sha256_bestand(f5 / middel))
            groepen[groep].append(regel)
    uit = {}
    hashes = {}
    for groep, gevallen in groepen.items():
        for geval in gevallen:
            p = geval["pad"]
            if p not in hashes:
                bronpad = setmap(sets, "ass") / ass if p.startswith(ASS_MAP + "/") else media_pad(p, corpus)
                hashes[p] = manifest.sha256_bestand(bronpad)
            geval["media_sha256"] = hashes[p]
        inhoud = json.dumps(gevallen, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        uit[groep] = {"sha256": hashlib.sha256(inhoud).hexdigest(), "gevallen": gevallen}
    return {"schema": "b03-060/meetsets/1", "seed": RECEPTEN["f5-fouten"].seed, "recepten": recepten, "groepen": uit}


def controleer(sets: Path, corpus: Path) -> dict:
    bevroren = json.loads(BEWIJS.read_text())
    if samenstellen(sets, corpus) != bevroren:
        raise ValueError("de media, foutmiddelen of indeling wijken af van de bevroren B03-060-meetsets")
    return bevroren
