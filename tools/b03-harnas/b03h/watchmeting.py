"""Beoordeling van de nulproef en de onafhankelijke vijfminutenruns van B03-020."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from . import bewijs, statistiek

SYSTEMEN = ("stock-standaard", "stock-best")
DUUR_MS = 300_000
MIN_RUNS = 5
SEED = 20261109


def getal(x: float) -> float:
    if isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x):
        raise ValueError("ongeldige meetwaarde")
    return x


def nulproef(opnamen: Sequence[dict]) -> dict:
    """Conservatieve fout: grootst mogelijke afstand tot de bekende klok binnen het opnamevenster."""
    if len(opnamen) < 10:
        raise ValueError("minstens tien klokopnamen nodig")
    fouten = []
    for rij in opnamen:
        voor, na, gelezen = (getal(rij[k]) for k in ("voor_ms", "na_ms", "klok_ms"))
        if na < voor or gelezen < 0:
            raise ValueError("ongeldig opnamevenster")
        fouten.append(max(abs(voor - gelezen), abs(na - gelezen)))
    if any(b["voor_ms"] < a["na_ms"] for a, b in zip(opnamen, opnamen[1:], strict=False)):
        raise ValueError("opnamen lopen door elkaar")
    if opnamen[-1]["klok_ms"] <= opnamen[0]["klok_ms"]:
        raise ValueError("de referentieklok liep niet")
    return {"n": len(fouten), "p95_ms": statistiek.kwantiel(fouten, .95), "max_ms": max(fouten), "opnamen": opnamen}


def beoordeel_spoor(spoor: dict, scenario: str) -> dict:
    """Elke leesactie geeft [kloktijd ms, mediapositie ms, actuele afspeelsnelheid of nul bij stilstand]."""
    begin, eind = (getal(spoor[k]) for k in ("begin_ms", "eind_ms"))
    paren = spoor["paren"]
    if eind - begin < DUUR_MS or len(paren) < math.ceil((eind - begin) / 100):
        raise ValueError("meetvenster korter dan vijf minuten of minder dan 10 Hz")
    hervat = getal(spoor["hervat_ms"])
    speelt = [getal(t) for t in spoor["playing_ms"]]
    if len(speelt) != 2 or not all(hervat <= t <= begin for t in speelt):
        raise ValueError("playing-event na hervatten ontbreekt bij een deelnemer")
    vorige = [begin, begin]
    eerste = paren[0]
    drift, stilstand, perioden = [], 0.0, 0
    stond_stil = False
    for a, b in paren:
        for i, (tijd, positie, snelheid) in enumerate((a, b)):
            delta = getal(tijd) - vorige[i]
            if not 0 <= delta <= 250 or tijd > eind or getal(positie) < 0 or getal(snelheid) < 0:
                raise ValueError("ongeldig of onderbroken positiespoor")
        # De niet-gesmoorde deelnemer A meet de stilstand van de groep bij S5.
        if a[2] == 0:
            perioden += int(not stond_stil)
            stilstand += a[0] - vorige[0]
        stond_stil = a[2] == 0
        zelfde_tijd = max(a[0], b[0])
        if scenario != "S2" or zelfde_tijd - begin >= 30_000:
            positie_a = a[1] + (zelfde_tijd - a[0]) * a[2]
            positie_b = b[1] + (zelfde_tijd - b[0]) * b[2]
            drift.append(abs(positie_a - positie_b))
        vorige = [a[0], b[0]]
    if max(eind - t for t in vorige) > 250 or not all(paren[-1][i][1] > eerste[i][1] for i in (0, 1)):
        raise ValueError("einde van het spoor of voortgang van een deelnemer ontbreekt")
    return {"n_paren": len(paren), "drift_p50_ms": statistiek.kwantiel(drift, .5),
            "drift_p95_ms": statistiek.kwantiel(drift, .95), "drift_max_ms": max(drift),
            "iedereen_speelt_ms": max(speelt) - hervat, "stilstand_ms": stilstand, "stilstandperioden": perioden}


def metrieken(scenario: str, systeem: str, image: str, runs: list[dict[str, Any]]) -> list[dict]:
    geldig = [r for r in runs if r["last"]["geldig"]]
    if len(geldig) < MIN_RUNS or len({r["last"]["run"] for r in geldig}) != len(geldig):
        raise ValueError("minder dan vijf onafhankelijke geldige runs")
    metingen = []
    for veld in ("drift_p50_ms", "drift_p95_ms", "drift_max_ms", "iedereen_speelt_ms", "stilstand_ms"):
        waarden = [r["uitkomst"][veld] for r in geldig]
        schatter = statistiek.gemiddelde
        if veld == "iedereen_speelt_ms":
            def schatter(reeks: Sequence[float]) -> float:
                return statistiek.kwantiel(reeks, .95)
        elif veld == "drift_max_ms":
            schatter = max
        interval = statistiek.bootstrap(waarden, schatter, seed=SEED)
        metingen.append(bewijs.metriek(
            id=f"F1-{scenario}-{veld}", functie="F1", omschrijving=f"{scenario} {veld}", systeem=systeem,
            methode="Twee verschillende sessies, klokcorrectie per paar, playing-events na groepshervatting. "
                    "95%-bootstrap over zelfstandige runs. Voor p50/p95 het gemiddelde van de runkwantielen.",
            soort="continu", image=image, seed=SEED, runs=runs, waarde={"per_run": waarden},
            interval=interval, n=len(geldig), eenheid="ms"))
    return metingen
