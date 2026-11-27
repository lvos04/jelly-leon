"""B03-030. Lokale datasetvoorbereiding, lekproef en de tweevoudige meting op stock."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from . import bewijs, meetslot
from .corpus import manifest
from .corpus.download import DownloadFout
from .corpus.generator import REPO
from .f2_data import MIN_GEBRUIKERS, Dataset, haal_archief, lees_dml, lees_dsyn, lokaal, schrijf_dml_stubs
from .f2_metrieken import SEED, beoordeel_ranglijsten, gepaard, geschudde_holdout, kandidaten, metrieken
from .f2_stock import bronproeven, controleer_historie, functieproef, gebruiker, ranglijsten, stockcatalogus, zaai
from .stock import STOCK_IMAGE, WERK, StockServer

NIET_GEMETEN = "NIET GEMETEN (machinelast)"
MAP = REPO / "docs/platform-v2/test-evidence"


def schrijf(pad: Path, document: dict) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    tekst = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    f = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=pad.parent, delete=False)
    tijdelijk = Path(f.name)
    try:
        with f:
            f.write(tekst)
        tijdelijk.replace(pad)
    finally:
        tijdelijk.unlink(missing_ok=True)


def voorwaarde(basis: Path, last: float) -> list[str]:
    redenen = []
    if last > meetslot.LASTGRENS:
        redenen.append(f"loadavg(1 min) {last:.2f} boven {meetslot.LASTGRENS:.1f}")
    if not basis.is_file():
        return [*redenen, "definitieve baseline van S-P40-50 ontbreekt"]
    doc = json.loads(basis.read_text())
    pogingen = doc.get("pogingen", [])
    if (doc.get("aangevraagd_label") == "definitief-forkbasis" and pogingen
            and all(r.get("last", {}).get("geldig") is False for r in pogingen)):
        return [*redenen, "definitieve baseline van S-P40-50 ontbreekt (alleen afgewezen pogingen)"]
    if doc.get("label") != "definitief-forkbasis" or doc.get("images", {}).get("stock") != STOCK_IMAGE:
        return [*redenen, "baseline van S-P40-50 mist het definitieve label of de forkbasisdigest"]
    if bewijs.controleer(doc) or doc.get("fasefouten"):
        return [*redenen, "baseline van S-P40-50 is onvolledig"]
    metingen = doc.get("metingen", [])
    for systeem in ("stock-standaard", "stock-best"):
        records = [m for m in metingen if m["systeem"] == systeem and m.get("interval")]
        if not records or any(m["image"] != STOCK_IMAGE or m["n"] <= 0 or len(m["runs"]) < 3
                              or not all(r.get("last", {}).get("geldig") is True for r in m["runs"]) for m in records):
            redenen.append(f"S-P40-50 mist geldige runs met interval voor {systeem}")
    return redenen


def lekproef(dataset: Dataset, seed: int) -> dict:
    """Trainingsvrije loting en een opzettelijk gelekte controle op exact dezelfde verwisselde antwoorden."""
    verwisseld = geschudde_holdout(dataset.profielen, seed)
    rng = random.Random(seed)
    scores = {"POP": {}, "loting": {}, "positieve_controle": {}}
    for u, p in sorted(dataset.profielen.items()):
        loting = sorted(dataset.catalogus)
        rng.shuffle(loting)
        holdout = verwisseld[u]
        for naam, rij in (("POP", dataset.pop(u)), ("loting", loting), ("positieve_controle", sorted(holdout))):
            top = kandidaten(rij, dataset.catalogus, p)
            scores[naam][u] = metrieken(top, holdout, dataset.catalogus)["NDCG@10"]
    controle = gepaard(scores["positieve_controle"], scores["POP"], seed)
    loting = gepaard(scores["loting"], scores["POP"], seed)
    return {"n": len(verwisseld), "seed": seed, "trekkingen": 1000,
            "loting_min_POP": loting.als_dict(), "positieve_controle_min_POP": controle.als_dict(),
            "controle_onderscheidt_lek": controle.onder > 0, "loting_significant_boven_POP": loting.onder > 0}


def schijfruimte(mappen: list[Path]) -> dict:
    bestanden = [p.stat() for map_ in mappen for p in map_.rglob("*") if p.is_file()]
    blokken = {(st.st_dev, st.st_ino): st.st_blocks for st in bestanden}
    return {"bestanden": len(bestanden), "logische_bytes": sum(st.st_size for st in bestanden), "toegewezen_bytes": 512 * sum(blokken.values())}


def twee_runs(beheer, dataset: Dataset, ids: dict[str, str], container_id: str) -> dict:
    omgekeerd = {v: k for k, v in ids.items()}
    kijkers = {u: gebruiker(beheer, u, kind=(dataset.naam == "D-SYN" and u == "kind")) for u in dataset.profielen}
    for u, kijker in kijkers.items():
        zaai(kijker, dataset.profielen[u], ids)
    vooraf = sum(controleer_historie(k, dataset.profielen[u], ids, dataset) for u, k in kijkers.items())
    runs = []
    for nummer in (1, 2):
        if meetslot.loadavg()[0] > meetslot.LASTGRENS:
            return {"status": NIET_GEMETEN, "reden": "lastgrens vóór een stockrun overschreden", "geldige_runs": len(runs)}
        with meetslot.run("stock-F2", nummer, [container_id]) as last:
            rijen = {u: ranglijsten(k, dataset, u, ids, omgekeerd) for u, k in kijkers.items()}
        if not last.geldig:
            return {"status": NIET_GEMETEN, "reden": last.reden, "last": last.als_dict(), "geldige_runs": len(runs)}
        if any(not r["S-RND"] for r in rijen.values()):
            raise ValueError("geen Suggesties voor een ingescand profiel")
        uit = beoordeel_ranglijsten(rijen, dataset.profielen, dataset.catalogus, SEED)
        runs.append({**uit, "last": last.als_dict()})
    achteraf = sum(controleer_historie(k, dataset.profielen[u], ids, dataset) for u, k in kijkers.items())
    spreiding = {}
    for s in ("S-REC", "S-REC-best", "S-SIM", "S-LAT", "S-RND", "S-BEST", "POP"):
        a, b = (r["systemen"][s] for r in runs)
        spreiding[s] = {m: abs(b[m]["punt"] - a[m]["punt"]) for m in ("NDCG@10", "Recall@10", "ILD")}
        spreiding[s]["coverage"] = abs(b["coverage"] - a["coverage"])
    return {"status": "Sim-getest", "geldige_runs": len(runs), "runs": runs, "absoluut_verschil_runs": spreiding,
            "geverifieerde_trainingsitems": {"voor": vooraf, "na": achteraf}}


def stockproef(dataset: Dataset, dsyn: Path, werk: Path) -> dict:
    werk = lokaal(werk)
    werk.mkdir(parents=True, exist_ok=True)
    # Alle serverdata en de eventuele D-ML-stubs behoren alleen toe aan deze opdracht.
    with tempfile.TemporaryDirectory(prefix="f2-", dir=werk) as eigen:
        tijdelijk = Path(eigen)
        media = dsyn
        mappen = {"Films": "movies", "Series": "tvshows"}
        if dataset.naam == "D-ML":
            media = tijdelijk
            mappen = {"Films": "movies"}
            schrijf_dml_stubs(dataset, next((dsyn / "Films").rglob("*.mkv")), media / "Films")
        ruimte = schijfruimte([media / m for m in mappen])
        mounts = {"/media/" + m: m for m in mappen}
        with StockServer("f2", corpus=media.resolve(), koppelingen=mounts, werk=tijdelijk, gpu=False, cpus="2") as srv:
            srv.start()
            assert srv.jf is not None
            with meetslot.run("stock-F2-scan", 0, [srv.container_id]) as scanlast:
                scan = srv.inrichten([(m, soort, ["/media/" + m]) for m, soort in mappen.items()])
            if not scanlast.geldig:
                return {"status": NIET_GEMETEN, "reden": scanlast.reden, "last": scanlast.als_dict(), "geldige_runs": 0}
            ids = stockcatalogus(srv.jf, dataset)
            film = next(ids[k] for k in sorted(ids) if dataset.catalogus[k].soort == "Movie")
            duur = srv.jf.a.doe("GET", f"/Items/{film}", {"userId": srv.jf.admin_id})["RunTimeTicks"] / 10_000_000
            if not 0.9 <= duur <= 1.1:
                raise ValueError("scan rapporteert geen stub van één seconde")
            instellingen = srv.jf.a.doe("GET", "/System/Configuration")
            spike = {"stubduur_s": duur, "MaxResumePct": instellingen["MaxResumePct"],
                     "MinResumeDurationSeconds": instellingen["MinResumeDurationSeconds"]}
            meting = twee_runs(srv.jf, dataset, ids, srv.container_id)
            if meting["status"] == "Sim-getest" and dataset.naam == "D-SYN":
                with meetslot.run("stock-F2-functieproef", 1, [srv.container_id]) as last:
                    functie = functieproef(srv.jf, dataset, ids)
                if last.geldig:
                    meting["functieproef"] = functie
                else:
                    meting["functieproef"] = {"status": NIET_GEMETEN, "reden": last.reden}
            return {**meting, "scan_s": scan, "scanlast": scanlast.als_dict(), "stubs": ruimte, "spike": spike,
                    "items_gescand": len(ids), "image_id_container": srv.digest()}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h baseline-f2")
    sub = p.add_subparsers(dest="actie", required=True)
    dml = sub.add_parser("dml", help="verifieer/download de lokale bron en controleer de globale split")
    dml.add_argument("--map", type=Path, required=True)
    dml.add_argument("--uit", type=Path)
    dml.add_argument("--dsyn", type=Path, help="bouw en verifieer de lokale stubs en ruim ze direct op")
    lek = sub.add_parser("lekproef", help="schud de holdout en toets een onafhankelijke loting en een bekende lekbron")
    meet = sub.add_parser("meet", help="probeer twee stockruns achter het meetslot")
    groep = lek.add_mutually_exclusive_group(required=True)
    groep.add_argument("--dsyn", type=Path)
    groep.add_argument("--dml-archief", type=Path)
    meet.add_argument("--dsyn", type=Path, required=True, help="bevroren D-SYN, ook als bron van de 1 s-stub voor D-ML")
    meet.add_argument("--dml-archief", type=Path, help="meet op het lokaal gecontroleerde D-ML-archief")
    for opdracht in (lek, meet):
        opdracht.add_argument("--uit", type=Path, required=True)
    meet.add_argument("--basis", type=Path, required=True, help="definitief baselinebewijs van S-P40-50")
    a = p.parse_args(argv)
    if a.actie == "dml":
        try:
            d = lees_dml(haal_archief(a.map))
        except DownloadFout as fout:
            melding = f"D-ML ontbreekt: {fout}"
            if a.uit:
                schrijf(a.uit, {"dataset": "D-ML", "reden": melding})
            print(melding, file=sys.stderr)
            return 1
        doc = {**d.samenvatting(), "bovengrens_n": d.bovengrens_n, "minimum_n": MIN_GEBRUIKERS,
               "cohort_voldoende": len(d.profielen) >= MIN_GEBRUIKERS}
        if a.dsyn:
            lees_dsyn(a.dsyn)
            with tempfile.TemporaryDirectory(prefix="f2-stubs-", dir=lokaal(a.map)) as tijdelijk:
                films = Path(tijdelijk) / "Films"
                schrijf_dml_stubs(d, next((a.dsyn / "Films").rglob("*.mkv")), films)
                bestanden = manifest.bestanden(films)
                if len(bestanden) != 2 * len(d.films):
                    raise ValueError("onvolledige D-ML-stubbibliotheek")
                doc["stubs"] = schijfruimte([films]) | {"set_sha256": manifest.inhoud_sha256(bestanden)}
            doc["stubs"]["opgeruimd"] = not Path(tijdelijk).exists()
        if a.uit:
            schrijf(a.uit, doc)
        print(json.dumps(doc, ensure_ascii=False))
        return 0
    d = lees_dml(a.dml_archief) if a.dml_archief else lees_dsyn(a.dsyn)
    commit = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    doc = {**d.samenvatting(), "commit": commit, "seed": SEED}
    if d.naam == "D-ML":
        doc.update({"minimum_n": MIN_GEBRUIKERS, "cohort_voldoende": len(d.profielen) >= MIN_GEBRUIKERS})
    if a.actie == "lekproef":
        toets = lekproef(d, SEED)
        schrijf(a.uit, {**doc, "proef": "offline lekbewaking", **toets})
        print(f"n={toets['n']}, loting boven POP: {toets['loting_significant_boven_POP']}, bekende lekbron herkend: "
              f"{toets['controle_onderscheidt_lek']}")
        return 0 if toets["controle_onderscheidt_lek"] and not toets["loting_significant_boven_POP"] else 1
    doc.update({"image": STOCK_IMAGE, "broncontroles": bronproeven(), "geldige_runs": 0,
                "S-TMDB": "niet gemeten: remote provider vraagt netwerkverkeer naar TMDb"})

    def meetbaar() -> bool:
        last = meetslot.loadavg()[0]
        redenen = voorwaarde(a.basis, last)
        doc.update({"loadavg_1min": round(last, 2), "lastgrens": meetslot.LASTGRENS})
        if redenen:
            doc.update({"status": NIET_GEMETEN, "reden": " / ".join(redenen)})
        elif d.naam == "D-ML" and len(d.profielen) < MIN_GEBRUIKERS:
            doc.update({"status": "NIET GEMETEN (cohort)", "reden": f"{len(d.profielen)} van minstens {MIN_GEBRUIKERS} gebruikers"})
        else:
            return True
        return False

    if meetbaar():
        if d.naam == "D-ML":
            lees_dsyn(a.dsyn)  # Gebruik uitsluitend de geverifieerde synthetische mediastub.
        with meetslot.exclusief_slot():
            if meetbaar():
                doc.update(stockproef(d, a.dsyn, WERK))
    schrijf(a.uit, doc)
    print(f"{doc['status']} — {doc.get('reden', 'twee stockruns')} ({doc['geldige_runs']} geldige runs)")
    return 0 if doc["status"] == "Sim-getest" else 3


if __name__ == "__main__":
    sys.exit(main())
