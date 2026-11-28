"""jl-rec-eval op de bevroren F2-datasets. Publiceer uitsluitend geaggregeerde uitkomsten."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from . import meetslot
from .baseline_f2 import MAP, schrijf, stockproef, voorwaarde
from .corpus.generator import REPO
from .f2_data import MIN_GEBRUIKERS, lees_dml, lees_dsyn, lokaal, tijd
from .f2_evaluatie import WARM, opname, samenvatting, uitvoer, validatiewinnaar
from .f2_metrieken import SEED
from .f2_vergelijking import intervallen, meetsessie
from .stock import STOCK_IMAGE, WERK


def functie(cli, d, dsyn) -> dict:
    invoer = opname(d, dsyn)
    vorige, lasten = None, []
    for nummer in range(1, 4):
        with meetslot.run("F2-offline", nummer) as last:
            rijen = uitvoer(cli, "rangschik", invoer)
        lasten.append(last.als_dict())
        if vorige is not None and vorige != rijen:
            raise ValueError("de ranglijsten verschillen met dezelfde klok")
        vorige = rijen
    functies = samenvatting(d, vorige)
    lekvrij = functies[WARM]["geschud_min_POP"]["onder"] <= 0
    return {"status": "Sim-getest" if lekvrij else "Sim-mislukt", "herhalingen": len(lasten),
            "geldige_meetruns": sum(r["geldig"] for r in lasten), "last": lasten, "functies": functies,
            "determinisme": True, "lektest": lekvrij,
            "claim": "rangschikkingswinst niet aangetoond; functioneel aangetoond (synthetisch)"
            if d.naam == "D-SYN" and lekvrij else "niet aangetoond"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h eval-f2")
    sub = p.add_subparsers(dest="actie", required=True)
    val = sub.add_parser("valideer", help="kies de gewichten alleen op de laatste 10 procent vóór T")
    val.add_argument("--dml-archief", type=Path, required=True)
    fun = sub.add_parser("functie", help="drie offline herhalingen, zonder stockclaim")
    groep = fun.add_mutually_exclusive_group(required=True)
    groep.add_argument("--dsyn", type=Path)
    groep.add_argument("--dml-archief", type=Path)
    meet = sub.add_parser("meet", help="stock op de forkbasisdigest en drie gepaarde runs")
    meet.add_argument("--dsyn", type=Path, required=True)
    meet.add_argument("--dml-archief", type=Path)
    meet.add_argument("--basis", type=Path, required=True)
    meet.add_argument("--voormeting", type=Path, required=True)
    for actie in (val, fun, meet):
        actie.add_argument("--cli", type=Path, required=True, help="uitvoerbaar jl-rec-eval")
        actie.add_argument("--uit", type=Path, required=True, help="lokaal geaggregeerd rapport buiten Git")
    a = p.parse_args(argv)
    uit = lokaal(a.uit)
    protocol = json.loads((MAP / "b03-032-meetprotocol.json").read_text())
    valideren = a.actie == "valideer"
    d = (lees_dml(a.dml_archief, validatie_voor=tijd(protocol["T"]) if valideren else None)
         if a.dml_archief else lees_dsyn(a.dsyn))
    dsyn = json.loads((a.dsyn / "grondwaarheid.json").read_text()) if d.naam == "D-SYN" else None
    doc = {**d.samenvatting(), "seed": SEED, "commit": subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()}
    if valideren:
        if d.sha256 != protocol["dataset_sha256"] or d.globaal_t != tijd(protocol["V"]):
            raise ValueError("de validatiesplit wijkt af van het preregistratiebewijs")
        # Deze kleine afstelling vóór T kiest coëfficiënten. De drie testruns en de stockproeven nemen het meetslot.
        keuze = validatiewinnaar(d, uitvoer(a.cli, "valideer", opname(d, None, valideren=True)))
        doc.update({"validatie": keuze, "testmoment": protocol["T"]})
        slot = f"validatie n={keuze['n']}, keuze={keuze['keuze']}"
        code = 0
    elif a.actie == "functie":
        with meetslot.exclusief_slot():
            doc.update(functie(a.cli, d, dsyn))
        slot = f"n={doc['n']}, herhalingen={doc['herhalingen']}, determinisme={doc['determinisme']}, lektest={doc['lektest']}"
        code = 0 if doc["lektest"] else 1
    else:
        doc["image"] = STOCK_IMAGE

        def voorwaarden():
            redenen = voorwaarde(a.basis, meetslot.loadavg()[0])
            if d.naam == "D-ML" and len(d.profielen) < MIN_GEBRUIKERS:
                redenen.append(f"D-ML: {len(d.profielen)} van minstens {MIN_GEBRUIKERS} gebruikers")
            try:
                eerste = intervallen(json.loads(a.voormeting.read_text()), d.naam, d.sha256, STOCK_IMAGE)
            except (FileNotFoundError, KeyError, ValueError) as fout:
                eerste = {}
                redenen.append(str(fout))
            return eerste, redenen

        eerste, redenen = voorwaarden()
        if not redenen:
            if d.naam == "D-ML":
                lees_dsyn(a.dsyn)
            with meetslot.exclusief_slot():
                eerste, redenen = voorwaarden()
                if not redenen:
                    doc.update(stockproef(d, a.dsyn, WERK, meetsessie=meetsessie(a.cli, dsyn, eerste)))
        if redenen:
            doc.update({"status": "NIET GEMETEN", "geldige_runs": 0, "reden": " / ".join(redenen)})
        slot = f"{doc['status']} — {doc.get('reden', 'drie gepaarde runs')} ({doc['geldige_runs']} geldige runs)"
        code = 0 if doc.get("toets", {}).get("lektest") else (1 if doc["status"] in ("Sim-getest", "GESTOPT") else 3)
    schrijf(uit, doc)
    print(slot)
    return code
