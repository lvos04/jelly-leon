"""Herhaal de stockroutes op dezelfde stubs en vergelijk gepaard per gebruiker (G-F2-2)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, replace

from . import meetslot
from .f2_evaluatie import METRIEKEN, SCENARIOS, WARM, cijfers, controleer_rij, opname, samenvatting, scenario, uitvoer
from .f2_metrieken import SEED, beoordeel_ranglijsten, gepaard, kandidaten
from .f2_stock import controleer_historie, gebruiker, ranglijsten, zaai
from .statistiek import gemiddelde

STOCK = ("S-REC", "S-SIM", "S-LAT", "S-RND", "POP", "S-REC-best", "S-BEST")


def intervallen(bewijs: dict, dataset: str, sha: str, image: str) -> dict:
    # B03-030 bewaart de meetpogingen per dataset. Ook het losse baseline-f2-rapport is bruikbaar.
    bron = bewijs.get(dataset, bewijs)
    if bron.get("dataset_sha256") != sha or bewijs.get("aangevraagde_image", bewijs.get("image")) != image:
        raise ValueError("voormeting heeft een andere dataset of forkbasisdigest")
    stock = bron.get("stock", bron)
    runs = stock.get("runs", [])
    if stock.get("geldige_runs", 0) < 2 or len(runs) < 2 or not all(r.get("last", {}).get("geldig") is True for r in runs):
        raise ValueError("B03-030 heeft geen twee geldige stockruns met voormetingsinterval")
    eerste = runs[0]["systemen"]
    for systeem in STOCK:
        for m in METRIEKEN:
            iv = eerste[systeem][m]
            if not 0 <= iv["onder"] <= iv["punt"] <= iv["boven"] <= 1:
                raise ValueError("ongeldig voormetingsinterval")
    return eerste


def buiten_interval(herhaling: dict, eerste: dict) -> list[str]:
    return [f"{s} {m}" for s in STOCK for m in METRIEKEN
            if not eerste[s][m]["onder"] <= herhaling[s][m]["punt"] <= eerste[s][m]["boven"]]


def snapshot(beheer, ids: dict[str, str]) -> list[dict]:
    omgekeerd = {v: k for k, v in ids.items()}
    rijen = beheer.items({"includeItemTypes": "Movie,Series", "limit": len(ids) + 1,
                          "fields": "Genres,Tags,Studios,People,DateCreated,ProductionLocations"})
    catalogus = []
    for r in rijen:
        item = omgekeerd[r["Id"]]
        personen = r.get("People", [])
        catalogus.append({"id": item, "soort": r["Type"], "genres": r.get("Genres", []), "tags": r.get("Tags", []),
                          "studios": [s["Name"] for s in r.get("Studios", [])], "keur": r.get("OfficialRating"),
                          "regisseurs": [p["Name"] for p in personen if p["Type"] == "Director"],
                          "schrijvers": [p["Name"] for p in personen if p["Type"] == "Writer"],
                          "acteurs": [p["Name"] for p in personen if p["Type"] == "Actor"][:5],
                          "jaar": r.get("ProductionYear"), "waardering": r.get("CommunityRating"), "toegevoegd": r.get("DateCreated"),
                          "landen": r.get("ProductionLocations", []), "serie": item if r["Type"] == "Series" else None})
    if len(catalogus) != len(ids) or {r["id"] for r in catalogus} != ids.keys():
        raise ValueError("onvolledige catalogusopname op de stockserver")
    return catalogus


def vergelijk(d, rijen: dict, stockruns: list[dict]) -> dict:
    """Per gebruiker eerst het gemiddelde over runs. Gebruikers blijven de onafhankelijke bootstrap-eenheid."""
    uit = {}
    for naam in SCENARIOS:
        soort = naam.removesuffix("-opt-in")
        profielen = {u: scenario(p, naam) for u, p in d.profielen.items()}
        f2 = cijfers({u: controleer_rij(rijen[u][naam], d, p) for u, p in profielen.items()}, d)
        scores = defaultdict(list)
        systemen = sorted({s for run in stockruns for rij in run[soort].values() for s in rij})
        for systeem in systemen:
            for run in stockruns:
                tops = {u: kandidaten(run[soort][u].get(systeem, []), d.catalogus, p) for u, p in profielen.items()}
                scores[systeem].append(cijfers(tops, d))
        referenties = {}
        for systeem, runs in scores.items():
            referenties[systeem] = {m: {u: gemiddelde([r[m][u] for r in runs]) for u in profielen} for m in METRIEKEN}
        verschillen = {}
        for m in METRIEKEN:
            waarden = f2[m]
            verschil = {s: asdict(gepaard(waarden, r[m], SEED)) for s, r in referenties.items()}
            voorraad = ["S-REC", "S-SIM", "S-LAT"] if soort == WARM else ["S-LAT", "S-RND", *(["POP"] if soort != "koud-0" else [])]
            volledig = [*voorraad, *(s for s in systemen if s.startswith("categorie/") or s == "S-TMDB")]
            for label, opties in (("stock_a", voorraad), ("S-BEST", volledig)):
                beste = max(opties, key=lambda s: gemiddelde(list(referenties[s][m].values())))
                verschil[label] = {**verschil[beste], "gekozen": beste, "baseline": gemiddelde(list(referenties[beste][m].values()))}
            verschillen[m] = verschil
        uit[naam] = verschillen
    return uit


def gate(d, functies: dict, vergelijking: dict) -> dict:
    warm = vergelijking[WARM]
    lekvrij = functies[WARM]["geschud_min_POP"]["onder"] <= 0

    def boven(label):
        for m, factor in (("NDCG@10", 1.25), ("Recall@10", 1.20)):
            verschil = warm[m][label]
            if (functies[WARM][m]["punt"] < factor * verschil["baseline"]
                    or min(verschil["onder"], warm[m]["POP"]["onder"], warm[m]["S-LAT"]["onder"]) <= 0):
                return False
        return True

    functioneel = lekvrij and all(functies[s]["volledige_rijen"] for s in SCENARIOS)
    claim = ("rangschikkingswinst niet aangetoond; functioneel aangetoond (synthetisch)"
             if d.naam == "D-SYN" and functioneel else "niet aangetoond")
    rangschikking = d.naam == "D-ML" and len(d.profielen) >= 100 and functioneel
    if rangschikking:
        if "S-TMDB" in warm["NDCG@10"] and boven("S-BEST"):
            claim = "aantoonbaar beter"
        elif boven("stock_a"):
            claim = "beter dan de standaardinstelling"
    koud = {}
    for naam in SCENARIOS[1:]:
        scores = vergelijking[naam]["NDCG@10"]
        kwaliteit = scores["POP"]["onder"] >= -0.02 if naam == "koud-0-opt-in" else scores["stock_a"]["onder"] > 0
        koud[naam] = kwaliteit if rangschikking else None
    return {"M1": claim, "M2": koud, "lektest": lekvrij, "functioneel": functioneel,
            "ILD_ten_minste_S_REC": warm["ILD"]["S-REC"]["punt"] >= 0}


def meetsessie(cli, dsyn, eerste):
    def meet(beheer, d, ids, container):
        omgekeerd = {v: k for k, v in ids.items()}
        invoer = opname(d, dsyn, titels=snapshot(beheer, ids))
        kijkers, datasets = {}, {}
        for naam in [WARM, "koud-0", "koud-1", "koud-2"]:
            dataset = replace(d, profielen={u: scenario(p, naam) for u, p in d.profielen.items()})
            datasets[naam] = dataset
            kijkers[naam] = {}
            for u, p in dataset.profielen.items():
                k = gebruiker(beheer, f"{naam}-{u}", kind=d.naam == "D-SYN" and u == "kind")
                zaai(k, p, ids)
                controleer_historie(k, p, ids, dataset)
                kijkers[naam][u] = k
        stockruns, lasten, vorige = [], [], None
        for nummer in range(1, 4):
            with meetslot.run("G-F2-2-stock", nummer, [container]) as last:
                stock = {naam: {u: ranglijsten(k, datasets[naam], u, ids, omgekeerd) | {"POP": d.pop(u)}
                                for u, k in groep.items()} for naam, groep in kijkers.items()}
            lasten.append(last.als_dict())
            if not last.geldig:
                return {"status": "NIET GEMETEN (machinelast)", "reden": last.reden, "geldige_runs": len(stockruns), "last": lasten}
            herhaling = beoordeel_ranglijsten(stock[WARM], d.profielen, d.catalogus, SEED)
            afwijkend = buiten_interval(herhaling["systemen"], eerste)
            if afwijkend:
                return {"status": "GESTOPT", "reden": "stock buiten het voormetingsinterval", "afwijkend": afwijkend,
                        "geldige_runs": len(stockruns), "stock": herhaling, "last": lasten}
            with meetslot.run("G-F2-2-engine", nummer, [container]) as last:
                rijen = uitvoer(cli, "rangschik", invoer)
            lasten.append(last.als_dict())
            if not last.geldig:
                return {"status": "NIET GEMETEN (machinelast)", "reden": last.reden, "geldige_runs": len(stockruns), "last": lasten}
            if vorige is not None and vorige != rijen:
                raise ValueError("de ranglijsten met dezelfde klok verschillen")
            vorige = rijen
            stockruns.append(stock)
        voor_na = sum(controleer_historie(k, datasets[naam].profielen[u], ids, datasets[naam])
                      for naam, groep in kijkers.items() for u, k in groep.items())
        functies = samenvatting(d, vorige)
        vergelijking = vergelijk(d, vorige, stockruns)
        toets = gate(d, functies, vergelijking)
        return {"status": "Sim-getest" if toets["functioneel"] else "Sim-mislukt", "geldige_runs": len(stockruns),
                "last": lasten, "trainingsitems_herlezen": voor_na, "functies": functies, "vergelijking": vergelijking, "toets": toets}
    return meet
