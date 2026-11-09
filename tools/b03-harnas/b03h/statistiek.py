"""Statistiek van het meetprotocol (B03 2.0 §10.15): Wilson-95 %-interval, smoke-gate-label, kwantielen,
t-interval over runs, bootstrap en de herhaalbaarheidscontrole ("een herhaalde run valt binnen het interval").

Bewust zonder numpy/scipy: de getallen moeten in CI en op de ontwikkelmachine exact gelijk uitkomen.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Z95 = 1.959963984540054  # tweezijdig 95 %

# Tweezijdige 95 %-kwantielen van de t-verdeling (df 1…30); daarboven benadert z voldoende.
_T95 = [12.706204736, 4.302652730, 3.182446305, 2.776445105, 2.570581836, 2.446911851, 2.364624252, 2.306004135,
        2.262157163, 2.228138852, 2.200985160, 2.178812830, 2.160368656, 2.144786688, 2.131449546, 2.119905299,
        2.109815578, 2.100922040, 2.093024054, 2.085963447, 2.079613845, 2.073873068, 2.068657610, 2.063898562,
        2.059538553, 2.055529439, 2.051830516, 2.048407142, 2.045229642, 2.042272456]


@dataclass(frozen=True)
class Interval:
    """Puntschatting met 95 %-interval. ``methode`` zegt hoe het interval berekend is."""

    punt: float
    onder: float
    boven: float
    methode: str

    def bevat(self, waarde: float, marge: float = 0.0) -> bool:
        return self.onder - marge <= waarde <= self.boven + marge

    def als_dict(self) -> dict[str, float | str]:
        return {"punt": round(self.punt, 6), "onder": round(self.onder, 6), "boven": round(self.boven, 6),
                "methode": self.methode}


def wilson(k: int, n: int, z: float = Z95) -> Interval:
    """Wilson-scoreinterval voor een proportie k/n (ook correct bij k = 0 of k = n)."""
    if n <= 0:
        raise ValueError("n moet ≥ 1 zijn voor een Wilson-interval")
    if not 0 <= k <= n:
        raise ValueError(f"k = {k} ligt niet tussen 0 en n = {n}")
    p = k / n
    noemer = 1 + z * z / n
    midden = (p + z * z / (2 * n)) / noemer
    halve = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / noemer
    # Afronden op de grenzen: bij k = 0 is de ondergrens exact 0, bij k = n de bovengrens exact 1.
    onder = 0.0 if k == 0 else max(0.0, midden - halve)
    boven = 1.0 if k == n else min(1.0, midden + halve)
    return Interval(p, onder, boven, "wilson-95")


def gate_label(n: int, n_min: int) -> str:
    """Het plan: gate op de ondergrens alleen bij voldoende n; anders heet het expliciet 'smoke-gate (n = …)'."""
    return "gate" if n >= n_min else f"smoke-gate (n = {n})"


def kwantiel(waarden: Sequence[float], q: float) -> float:
    """Lineaire interpolatie (Hyndman-Fan type 7, gelijk aan numpy's standaard)."""
    if not waarden:
        raise ValueError("lege reeks")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q buiten [0, 1]")
    s = sorted(waarden)
    h = (len(s) - 1) * q
    laag = math.floor(h)
    hoog = min(laag + 1, len(s) - 1)
    return s[laag] + (h - laag) * (s[hoog] - s[laag])


def gemiddelde(waarden: Sequence[float]) -> float:
    if not waarden:
        raise ValueError("lege reeks")
    return sum(waarden) / len(waarden)


def standaardafwijking(waarden: Sequence[float]) -> float:
    if len(waarden) < 2:
        return 0.0
    m = gemiddelde(waarden)
    return math.sqrt(sum((x - m) ** 2 for x in waarden) / (len(waarden) - 1))


def t95(df: int) -> float:
    if df < 1:
        raise ValueError("df moet ≥ 1 zijn")
    return _T95[df - 1] if df <= len(_T95) else Z95


def t_interval(waarden: Sequence[float]) -> Interval:
    """95 %-interval van het gemiddelde over runs (t-verdeling). Bij één run is er geen interval (onder = boven)."""
    m = gemiddelde(waarden)
    if len(waarden) < 2:
        return Interval(m, m, m, "t-95 (1 run: geen spreiding)")
    halve = t95(len(waarden) - 1) * standaardafwijking(waarden) / math.sqrt(len(waarden))
    return Interval(m, m - halve, m + halve, f"t-95 (n = {len(waarden)} runs)")


def voorspellingsinterval(waarden: Sequence[float]) -> Interval:
    """95 %-voorspellingsinterval voor één nieuwe run: gemiddelde ± t·s·√(1 + 1/n). Hiermee wordt getoetst of een
    herhaalde run (een nieuwe meetsessie) 'binnen het interval valt' (acceptatie B03-016)."""
    m = gemiddelde(waarden)
    if len(waarden) < 2:
        return Interval(m, m, m, "voorspelling-95 (1 run: geen spreiding)")
    halve = t95(len(waarden) - 1) * standaardafwijking(waarden) * math.sqrt(1 + 1 / len(waarden))
    return Interval(m, m - halve, m + halve, f"voorspelling-95 (n = {len(waarden)} runs)")


def bootstrap(waarden: Sequence[float], statistiek: Callable[[Sequence[float]], float] = gemiddelde,
              trekkingen: int = 10_000, seed: int = 20261109) -> Interval:
    """Percentiel-bootstrap met vaste seed (herhaalbaar)."""
    if not waarden:
        raise ValueError("lege reeks")
    rng = random.Random(seed)
    n = len(waarden)
    schattingen = sorted(statistiek([waarden[rng.randrange(n)] for _ in range(n)]) for _ in range(trekkingen))
    return Interval(statistiek(waarden), kwantiel(schattingen, 0.025), kwantiel(schattingen, 0.975),
                    f"bootstrap-95 ({trekkingen} trekkingen, seed {seed})")


def bootstrap_verschil(a: Sequence[float], b: Sequence[float], statistiek: Callable[[Sequence[float]], float] = gemiddelde,
                       trekkingen: int = 10_000, seed: int = 20261109) -> Interval:
    """95 %-interval van statistiek(b) − statistiek(a) met onafhankelijke hertrekking per groep (F1: JL − baseline)."""
    if not a or not b:
        raise ValueError("lege reeks")
    rng = random.Random(seed)
    verschillen = []
    for _ in range(trekkingen):
        sa = [a[rng.randrange(len(a))] for _ in range(len(a))]
        sb = [b[rng.randrange(len(b))] for _ in range(len(b))]
        verschillen.append(statistiek(sb) - statistiek(sa))
    verschillen.sort()
    return Interval(statistiek(b) - statistiek(a), kwantiel(verschillen, 0.025), kwantiel(verschillen, 0.975),
                    f"bootstrap-verschil-95 ({trekkingen} trekkingen, seed {seed})")


def herhaling_binnen(eerste: Interval, herhaling: float, marge: float = 0.0) -> bool:
    """Acceptatie B03-016: 'een herhaalde run valt binnen het interval' van de eerste meting."""
    return eerste.bevat(herhaling, marge)
