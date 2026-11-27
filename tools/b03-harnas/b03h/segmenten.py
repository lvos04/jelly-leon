"""JLT-50 op de bevroren F6-testset. Alleen de proefcontainers van het lokale harnas."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path

from . import bewijs, meetslot
from .corpus import CORPUS, manifest
from .corpus.generator import BEVROREN
from .jfapi import HttpFout
from .segmentbron import IS_VERSIE, IS_ZIP_SHA, PROFIELEN, lees_set, lokale_jelly, stock_sessie
from .segmentmeting import GROEPEN, SOORTEN, evalueer, gepaard
from .stock import STOCK_IMAGE


def bevroren_set(setmap: Path, verwacht: str) -> list[dict]:
    vast = BEVROREN / "f6-segmenten.v2.vol.manifest.json"
    if manifest.sha256_bestand(vast) != verwacht:
        raise ValueError("manifest-sha256 wijkt af van de bevroren testset")
    m = json.loads(vast.read_text())
    lokaal = json.loads((setmap / "manifest.json").read_text())
    for veld in ("recept", "versie", "schaal", "seed", "parameters", "set_sha256", "bestanden", "bronnen", "licentie_beperkt"):
        if m[veld] != lokaal[veld]:
            raise ValueError("lokale set wijkt af van het bevroren manifest")
    if m["licentie_beperkt"] or m["set_sha256"] != manifest.inhoud_sha256(m["bestanden"]) or manifest.controleer(setmap, m):
        raise ValueError("inhoud van de bevroren set is ongeldig")
    items = json.loads((setmap / "grondwaarheid.json").read_text())["afleveringen"]
    verwacht_media = {b["pad"] for b in m["bestanden"] if b["pad"].endswith(".mkv")}
    if not items or len(items) != len(verwacht_media) or {i["bestand"] for i in items} != verwacht_media:
        raise ValueError("grondwaarheid dekt de testset niet")
    return items


def voorwaarden(baseline: Path) -> list[str]:
    redenen = []
    last = meetslot.loadavg()
    if last[0] > 4.0:
        redenen.append(f"loadavg {last[0]:.2f} / {last[1]:.2f} / {last[2]:.2f}, grens 4,00")
    if not baseline.is_file():
        redenen.append("definitieve baseline S-P40-50 ontbreekt")
    else:
        b = json.loads(baseline.read_text())
        if (b.get("label") != "definitief-forkbasis" or b.get("images", {}).get("stock") != STOCK_IMAGE or b.get("fasefouten")
                or bewijs.controleer(b)):
            raise ValueError("ongeldig baselinebewijs S-P40-50")
        profielen = {m["systeem"] for m in b["metingen"] if m["id"] == "F6-a-mediasegments" and m["image"] == STOCK_IMAGE
                     and sum(r["last"]["geldig"] for r in m["runs"]) >= 3}
        if not {"stock-standaard", "stock-best"} <= profielen:
            raise ValueError("definitieve F6-baseline is onvolledig")
    return redenen


def schrijf(pad: Path, data: dict) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=pad.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
            f.close()
            tmp.replace(pad)
        finally:
            tmp.unlink(missing_ok=True)


def spike(pakket: Path) -> dict:
    # De acht synthetische ontwikkelafleveringen dienen uitsluitend als laadproef. Geen labels of kwaliteitsscores.
    corpus = CORPUS / "afgeleid"
    with stock_sessie("is-standaard", corpus, pakket) as (jf, _, info):
        items = jf.items()
        if len(items) != 8 or any(Path(i["Path"]).relative_to("/media/f6/series").parts[0] not in ("B03 Testserie", "B03 Anime")
                                  for i in items):
            raise ValueError("S-IS verwacht uitsluitend de acht synthetische ontwikkelafleveringen")
        zichtbaar = 0
        for item in items:
            antwoord = jf.a.doe("GET", f"/MediaSegments/{item['Id']}")
            if len(antwoord["Items"]) != antwoord["TotalRecordCount"]:
                raise ValueError("onvolledig MediaSegments-antwoord in S-IS")
            zichtbaar += len(antwoord["Items"])
        if not zichtbaar:
            raise ValueError("S-IS geblokkeerd: plugin actief maar geen segment zichtbaar")
        return {**info, "doel": "S-IS laadproef op synthetische ontwikkelitems", "items": len(items), "zichtbare_segmenten": zichtbaar}


def vergelijk(resultaten: dict, tellingen: dict) -> dict:
    uit = {}
    if "jelly-leon" not in resultaten:
        return uit
    jl = resultaten["jelly-leon"]["scores"]
    for is_profiel in ("is-standaard", "is-ruim"):
        if is_profiel not in tellingen:
            continue
        intervallen = gepaard(tellingen["jelly-leon"], tellingen[is_profiel])
        for groep, meting in intervallen.items():
            if meting is None:
                continue
            grens = jl["per_type" if groep in SOORTEN else "deelgroepen"][groep]
            if grens["gate"] == "gate" and meting["onder"] is not None:
                meting["voldoet"] = meting["onder"] > 0 if groep in (*GROEPEN, "recap") else meting["onder"] >= -0.05
            else:
                meting["voldoet"] = None
        uit[is_profiel] = intervallen
    return uit


def meet(a: argparse.Namespace, items: list[dict], profielen: list[str]) -> int:
    resultaten, tellingen = {}, {}
    for nummer, profiel in meetslot.ab_volgorde(profielen, a.runs):
        if meetslot.loadavg()[0] > 4 or meetslot.actieve_zware_sloten():
            print("NIET GEMETEN (machinelast) — meetvoorwaarden onderbroken")
            return 3
        jl = profiel == "jelly-leon"
        sessie = nullcontext(lokale_jelly(a.jelly_container, a.set)) if jl else stock_sessie(profiel, a.set, a.intro_pakket)
        with sessie as (jf, cid, info), meetslot.run(profiel, nummer + 1, [cid], grens=4.0) as last:
            kandidaten, gepubliceerd = lees_set(jf, items, jl, a.schaduw)
            scores, per_item = evalueer(items, kandidaten, gepubliceerd)
        if not last.geldig or last.loadavg_na[0] > 4:
            print("NIET GEMETEN (machinelast) —", last.reden or "eindbelasting boven 4,00")
            return 3
        if profiel in tellingen and (tellingen[profiel] != per_item or resultaten[profiel]["scores"] != scores):
            raise ValueError("herhaalde run geeft verschillende cijfers")
        record = resultaten.setdefault(profiel, {**info, "scores": scores, "aantal_gepubliceerd": sum(map(len, gepubliceerd.values())),
                                                  "runs": []})
        record["runs"].append(last.als_dict())
        tellingen[profiel] = per_item
    verschillen = vergelijk(resultaten, tellingen)
    doc = {"manifest_sha256": a.manifest_sha256, "baseline_sha256": manifest.sha256_bestand(a.baseline),
           "profielen": resultaten, "gepaard_verschil_jl_min_is": verschillen, "schaduw": a.schaduw}
    ok = True
    if a.poort:
        jl = resultaten["jelly-leon"]["scores"]
        ok = (all(r["voldoet"] is True for r in (*jl["per_type"].values(), *jl["deelgroepen"].values()))
              and jl["beschermd"]["gate"] == "gate" and jl["beschermd"]["nultolerantie"] and jl["binnen_2s_per_uur"]
              and resultaten["stock-standaard"]["aantal_gepubliceerd"] == 0
              and all(g and g["voldoet"] is True for venster in verschillen.values() for g in venster.values()))
        doc["jlt50_binnen_drempels"] = ok
    schrijf(a.uit, doc)
    print("JLT-50: meetrapport geschreven" if ok else "JLT-50: vooraf vastgelegde drempels niet gehaald")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h segmenten")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("spike", help="S-IS: uitsluitend de laadproef op lokale synthetische ontwikkelitems")
    s.add_argument("--intro-pakket", required=True, type=Path)
    s.add_argument("--uit", required=True, type=Path)
    m = sub.add_parser("meet", help="JLT-50: lees en vergelijk de segmenten op de bevroren set")
    m.add_argument("--set", required=True, type=Path)
    m.add_argument("--manifest-sha256", required=True)
    m.add_argument("--baseline", required=True, type=Path, help="definitief-forkbasis uit S-P40-50")
    m.add_argument("--profielen", default=",".join(PROFIELEN))
    m.add_argument("--intro-pakket", type=Path)
    m.add_argument("--spike-bewijs", type=Path)
    m.add_argument("--jelly-container", help="lokale geprepareerde F6-proefcontainer in publicatie- of schaduwmodus")
    m.add_argument("--schaduw", action="store_true")
    m.add_argument("--runs", type=int, default=3)
    m.add_argument("--poort", action="store_true", help="toets alle vooraf vastgelegde drempels van JLT-50")
    m.add_argument("--uit", required=True, type=Path)
    a = p.parse_args(argv)
    try:
        if a.cmd == "spike":
            data = spike(a.intro_pakket)
            schrijf(a.uit, data)
            print(f"S-IS: versie {IS_VERSIE} actief, {data['zichtbare_segmenten']} zichtbare segmenten op {data['items']} testitems")
            return 0
        redenen = voorwaarden(a.baseline)
        if redenen:
            print("NIET GEMETEN (machinelast) — " + ", ".join(redenen))
            return 3
        profielen = a.profielen.split(",")
        if (not set(profielen) <= set(PROFIELEN) or len(set(profielen)) != len(profielen) or a.runs < 3
                or (a.poort and (a.schaduw or set(profielen) != set(PROFIELEN)))):
            raise ValueError("JLT-50 vraagt unieke geldige profielen, minstens drie runs en voor de poort alle vier in publicatiemodus")
        if "jelly-leon" in profielen and not a.jelly_container:
            raise ValueError("de lokale F6-proefcontainer ontbreekt")
        if {"is-standaard", "is-ruim"}.intersection(profielen):
            if not a.intro_pakket or not a.spike_bewijs:
                raise ValueError("Intro Skipper vraagt het ongewijzigde pakket en een S-IS-laadproef")
            s = json.loads(a.spike_bewijs.read_text())
            if (s["image"] != STOCK_IMAGE or s["intro_skipper"]["pakket_sha256"] != IS_ZIP_SHA
                    or s["intro_skipper"]["versie"] != IS_VERSIE or s["zichtbare_segmenten"] < 1):
                raise ValueError("S-IS-bewijs wijkt af van de meetbasis")
        items = bevroren_set(a.set, a.manifest_sha256)
        if os.environ.get("STACKSLOT") == "1" and os.path.samestat(os.fstat(9), (meetslot.LOCK_DIR / meetslot.STACK_LOCK).stat()):
            return meet(a, items, profielen)
        with meetslot.exclusief_slot():
            return meet(a, items, profielen)
    except HttpFout as fout:
        print(f"Segmentproef afgebroken bij HTTP {fout.status}", file=sys.stderr)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as fout:
        print(f"Segmentproef afgebroken: {fout}", file=sys.stderr)
    return 1
