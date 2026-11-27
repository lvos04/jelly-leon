"""Offline meetlat voor B03-030. Alle ranglijsten doorlopen hetzelfde filter vóór de meting."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations, zip_longest

from .statistiek import Interval, bootstrap, gemiddelde

K = 10
TREKKINGEN = 1000
SEED = 20261109


@dataclass(frozen=True)
class Item:
    soort: str
    genres: frozenset[str]


@dataclass(frozen=True)
class Interactie:
    item: str
    tijd: int
    favoriet: bool = False


@dataclass(frozen=True)
class Profiel:
    splitsing: int
    training: tuple[Interactie, ...]
    holdout: frozenset[str]
    toegang: frozenset[str]

    def __post_init__(self) -> None:
        if any(i.tijd >= self.splitsing for i in self.training):
            raise ValueError("training bevat een interactie op of na T")
        if not self.holdout:
            raise ValueError("lege holdout")
        if self.gezien & self.holdout:
            raise ValueError("overlap tussen training en holdout")

    @property
    def gezien(self) -> set[str]:
        return {i.item for i in self.training}


def rondgaand(lijsten: Iterable[Sequence[str]]) -> Iterable[str]:
    for ronde in zip_longest(*lijsten):
        yield from (item for item in ronde if item is not None)


def kandidaten(ranglijst: Iterable[str], catalogus: Mapping[str, Item], profiel: Profiel) -> list[str]:
    uitgesloten = profiel.gezien
    top = []
    for item in ranglijst:
        if item not in profiel.toegang or item in uitgesloten or item not in catalogus:
            continue
        if catalogus[item].soort in ("Movie", "Series"):
            top.append(item)
            uitgesloten.add(item)
            if len(top) == K:
                break
    return top


def metrieken(top: Sequence[str], holdout: frozenset[str], catalogus: Mapping[str, Item]) -> dict[str, float]:
    if not holdout:
        raise ValueError("lege holdout")
    if len(top) > K or len(set(top)) != len(top):
        raise ValueError("meting verwacht de ontdubbelde top 10")
    treffers = [rang for rang, item in enumerate(top, 1) if item in holdout]
    dcg = sum(1 / math.log2(rang + 1) for rang in treffers)
    ideaal = sum(1 / math.log2(rang + 1) for rang in range(1, min(K, len(holdout)) + 1))
    afstanden = []
    for a, b in combinations(top, 2):
        ga, gb = catalogus[a].genres, catalogus[b].genres
        unie = ga | gb
        afstanden.append(1 - len(ga & gb) / len(unie) if unie else 0.0)
    return {"NDCG@10": dcg / ideaal, "Recall@10": len(treffers) / len(holdout),
            "ILD": gemiddelde(afstanden) if afstanden else 0.0}


def coverage(toplijsten: Iterable[Sequence[str]], catalogus: Mapping[str, Item]) -> float:
    omvang = sum(item.soort in ("Movie", "Series") for item in catalogus.values())
    if not omvang:
        raise ValueError("lege catalogus")
    return len({item for top in toplijsten for item in top}) / omvang


def geschudde_holdout(profielen: Mapping[str, Profiel], seed: int) -> dict[str, frozenset[str]]:
    """Eén willekeurige cyclus zonder vaste punten. Ook bij twee gebruikers wisselt iedereen."""
    volgorde = sorted(profielen)
    if len(volgorde) < 2:
        raise ValueError("schudden vraagt minstens twee gebruikers")
    random.Random(seed).shuffle(volgorde)
    return {naam: profielen[volgorde[(i + 1) % len(volgorde)]].holdout for i, naam in enumerate(volgorde)}


def gepaard(links: Mapping[str, float], rechts: Mapping[str, float], seed: int) -> Interval:
    """Percentielinterval van links min rechts met de gebruiker als steekproefeenheid."""
    if not links or links.keys() != rechts.keys():
        raise ValueError("gepaard vergelijken vraagt dezelfde niet-lege groep gebruikers")
    return bootstrap([links[u] - rechts[u] for u in sorted(links)], trekkingen=TREKKINGEN, seed=seed)


def beoordeel_ranglijsten(ranglijsten: Mapping[str, Mapping[str, Sequence[str]]], profielen: Mapping[str, Profiel],
                          catalogus: Mapping[str, Item], seed: int) -> dict:
    """Middelen over gebruikers. Beste categorie en beste systeem worden per metriek op de hele testgroep gekozen."""
    if not profielen or ranglijsten.keys() != profielen.keys():
        raise ValueError("ranglijsten en gebruikers komen niet overeen")
    vast = {"S-REC", "S-SIM", "S-LAT", "S-RND", "POP"}
    if any(not vast.issubset(rijen) for rijen in ranglijsten.values()):
        raise ValueError("stock-baseline ontbreekt")
    categorieen = sorted({s for rijen in ranglijsten.values() for s in rijen if s.startswith("categorie/")})
    systemen = sorted(vast) + categorieen
    verwisseld = geschudde_holdout(profielen, seed)
    rapport, punten, geschud = {}, {}, {}
    for systeem in systemen:
        tops = {u: kandidaten(ranglijsten[u].get(systeem, ()), catalogus, p) for u, p in profielen.items()}
        scores = {u: metrieken(top, profielen[u].holdout, catalogus) for u, top in tops.items()}
        punten[systeem] = {m: {u: scores[u][m] for u in sorted(scores)} for m in ("NDCG@10", "Recall@10", "ILD")}
        geschud[systeem] = {u: metrieken(top, verwisseld[u], catalogus)["NDCG@10"] for u, top in tops.items()}
        rapport[systeem] = {
            m: bootstrap(list(waarden.values()), trekkingen=TREKKINGEN, seed=seed).als_dict()
            for m, waarden in punten[systeem].items()
        }
        rapport[systeem]["coverage"] = coverage(tops.values(), catalogus)
    # Een lege /Movies/Recommendations levert voor elke gebruiker een lege S-REC-lijst.
    beste_cat, beste_stock = {}, {}
    for m in ("NDCG@10", "Recall@10"):
        beste_cat[m] = max(categorieen or ["S-REC"], key=lambda s: gemiddelde(list(punten[s][m].values())))
        beste_stock[m] = max(["S-REC", beste_cat[m], "S-SIM", "S-LAT"], key=lambda s: gemiddelde(list(punten[s][m].values())))
    for naam, keuze in (("S-REC-best", beste_cat), ("S-BEST", beste_stock)):
        rapport[naam] = {**rapport[keuze["NDCG@10"]], **{m: rapport[s][m] for m, s in keuze.items()}, "gekozen": keuze}
    rapport["S-TMDB"] = {"status": "niet gemeten", "reden": "remote provider vraagt netwerkverkeer naar TMDb"}
    rapport["S-BEST"]["volledig"] = False
    for systeem in [*sorted(vast), "S-REC-best", "S-BEST"]:
        keuze = rapport[systeem].get("gekozen", {})
        rapport[systeem]["verschil_met_POP"] = {
            m: gepaard(punten[keuze.get(m, systeem)][m], punten["POP"][m], seed).als_dict() for m in ("NDCG@10", "Recall@10")
        }
        geschudde_rij = geschud[keuze.get("NDCG@10", systeem)]
        rapport[systeem]["geschud_NDCG_verschil_met_POP"] = gepaard(geschudde_rij, geschud["POP"], seed).als_dict()
    return {"n": len(profielen), "systemen": rapport}
