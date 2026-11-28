"""Offline beoordeling van de gedeelde .NET-engine. Alleen de beoordelaar heeft de holdout."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, replace
from pathlib import Path

from .f2_data import Dataset, utc
from .f2_metrieken import SEED, Profiel, coverage, gepaard, geschudde_holdout, kandidaten, metrieken
from .statistiek import bootstrap

WARM = "warm"
SCENARIOS = (WARM, *(f"koud-{k}{opt}" for k in range(3) for opt in ("", "-opt-in")))
METRIEKEN = ("NDCG@10", "Recall@10", "ILD")


def catalogus(d: Dataset, dsyn: dict | None) -> list[dict]:
    if d.films:
        return [{"id": k, "soort": "Movie", "genres": sorted(f.genres), "tags": sorted(f.tags),
                 "waardering": round(2 * f.som / f.aantal, 4), "toegevoegd": utc(f.eerste)}
                for k, f in sorted(d.films.items())]
    if dsyn is None:
        raise ValueError("D-SYN-metadata ontbreken")
    return [{"id": i["id"], "soort": i["type"], "genres": i["genres"], "tags": i["tags"], "keur": "NL-" + i["keur"],
             "jaar": i["jaar"], "regisseurs": [i["regisseur"]], "acteurs": i["acteurs"], "toegevoegd": i["toegevoegd"],
             "serie": i["id"] if i["type"] == "Series" else None} for i in dsyn["items"]]


def opname(d: Dataset, dsyn: dict | None, *, valideren: bool = False, titels: list[dict] | None = None) -> dict:
    """Geen titels van andere gebruikers, verborgen voorkeur, testantwoorden of gegevens na de klok naar de engine."""
    gezinnen = {} if dsyn is None else dsyn["gebruikers"]
    trainingen = d.deler_training or {u: p.training for u, p in d.profielen.items()}
    profielen = []
    for u, p in sorted(d.profielen.items()):
        eigen = gezinnen.get(u, {})
        huis = eigen.get("huishouden", "evaluatie")
        delers = []
        if not valideren:
            for naam, training in sorted(trainingen.items()):
                familie = gezinnen.get(naam, {})
                if naam != u and familie.get("huishouden", "evaluatie") == huis and not familie.get("kind", False):
                    delers.append({"id": naam, "volwassen": True, "deelt": True, "huishouden": huis,
                                   "bekeken": sorted({i.item for i in training if i.tijd < p.splitsing})})
        # De testserver zaait Played en favoriet. Lever dezelfde huidige toestand en geen extra beoordelingssignaal.
        toestanden = {}
        for i in sorted(p.training, key=lambda i: (i.tijd, i.item)):
            if i.tijd >= p.splitsing:
                raise ValueError("training op of na T")
            toestanden[i.item] = {"item": i.item, "tijd": utc(i.tijd), "bekeken": True,
                                  "favoriet": i.favoriet or toestanden.get(i.item, {}).get("favoriet", False)}
        profielen.append({"tijd": utc(p.splitsing), "profiel": {
            "id": u, "toegang": sorted(p.toegang), "toestand": list(toestanden.values()),
            "huishouden": huis, "volwassen": not eigen.get("kind", False), "huishoudenAan": not valideren, "delers": delers,
        }})
    return {"catalogus": catalogus(d, dsyn) if titels is None else titels, "profielen": profielen}


def uitvoer(cli: Path, actie: str, invoer: dict) -> dict:
    proces = subprocess.run([str(cli.resolve()), actie], input=json.dumps(invoer), text=True, capture_output=True, check=False)
    if proces.returncode:
        raise ValueError(f"jl-rec-eval {actie} stopte met exitcode {proces.returncode}")
    return json.loads(proces.stdout)


def scenario(p: Profiel, naam: str) -> Profiel:
    if naam == WARM:
        return p
    n = int(naam.split("-")[1])
    laatste = sorted(p.training, key=lambda i: (-i.tijd, i.item))[:n]
    return replace(p, training=tuple(laatste))


def controleer_rij(rij: list, d: Dataset, p: Profiel) -> list[str]:
    ids = [r["item"] for r in rij]
    if not ids or ids != kandidaten(ids, d.catalogus, p):
        raise ValueError("lege, ontdubbelde of toegangsgefilterde ranglijst wijkt af")
    if any(not r["redenen"] or any(not reden["code"] or (reden.get("refItemId") and reden["refItemId"] not in p.gezien)
                                   for reden in r["redenen"]) for r in rij):
        raise ValueError("ontbrekende of profielvreemde uitleg")
    if len(ids) == 10 and sum(r["exploratie"] for r in rij) != 1:
        raise ValueError("exploratieplek ontbreekt of is dubbel")
    return ids


def cijfers(top: Mapping[str, list[str]], d: Dataset) -> dict[str, dict[str, float]]:
    scores = {u: metrieken(rij, d.profielen[u].holdout, d.catalogus) for u, rij in top.items()}
    return {m: {u: waarden[m] for u, waarden in scores.items()} for m in METRIEKEN}


def validatiewinnaar(d: Dataset, antwoord: dict) -> dict:
    if antwoord.keys() != d.profielen.keys() or not antwoord:
        raise ValueError("onvolledige validatiegroep")
    ndcg = {}
    for naam in ("basis", "inhoud", "zaad"):
        tops = {u: controleer_rij(antwoord[u][naam], d, p) for u, p in d.profielen.items()}
        waarden = cijfers(tops, d)["NDCG@10"].values()
        ndcg[naam] = sum(waarden) / len(waarden)
    return {"V": utc(d.globaal_t), "n": len(d.profielen), "catalogus": len(d.catalogus),
            "NDCG@10": ndcg, "keuze": max(ndcg, key=ndcg.get)}


def samenvatting(d: Dataset, antwoord: dict) -> dict:
    if not antwoord or antwoord.keys() != d.profielen.keys() or any(r.keys() != set(SCENARIOS) for r in antwoord.values()):
        raise ValueError("onvolledige groep of koudestartscenario's")
    geschud = geschudde_holdout(d.profielen, SEED)
    resultaat = {}
    for naam in SCENARIOS:
        profielen = {u: scenario(p, naam) for u, p in d.profielen.items()}
        tops = {u: controleer_rij(antwoord[u][naam], d, p) for u, p in profielen.items()}
        pop = {u: kandidaten(d.pop(u), d.catalogus, p) for u, p in profielen.items()}
        scores = cijfers(tops, d)
        geschudde_punten = [{u: metrieken(top[u], geschud[u], d.catalogus)["NDCG@10"] for u in tops} for top in (tops, pop)]
        resultaat[naam] = {m: asdict(bootstrap(list(s.values()), seed=SEED, trekkingen=1000)) for m, s in scores.items()}
        resultaat[naam].update({"coverage": coverage(tops.values(), d.catalogus), "min_aantal": min(map(len, tops.values())),
                                "geschud_min_POP": asdict(gepaard(*geschudde_punten, SEED))})
    return resultaat
