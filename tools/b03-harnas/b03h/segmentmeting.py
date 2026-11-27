"""Meetlat B03-070. Ticks blijven geheel tot de rapportage, ook bij vergelijking met de publicatie."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from .corpus.r_f6_jlt50 import STREEF
from .statistiek import gate_label, kwantiel, wilson

TICKS = 10_000_000
SOORTEN = ("intro", "outro", "recap", "preview")
SKIP = {*SOORTEN, "commercial"}
BESCHERMD = {"post_credit", "mid_credit", "preview"}
INHOUD = {"inhoud", "cold_open", "terugkerend", *BESCHERMD}
# Pre-registratie F6.1.3–4. Wilson-ondergrenzen voor precisie en recall, grens-p95 in seconden.
DREMPELS = {"intro": (0.90, 0.80), "outro": (0.90, 0.75), "recap": (0.85, 0.65), "preview": (0.80, 0.50)}
GROEPEN = {"intro_buiten_is_venster": "intro_buiten_is_venster", "seizoensvariant_nieuwe_op": "nieuwe_op"}


@dataclass(frozen=True, order=True)
class Vak:
    soort: str
    start: int
    eind: int

    def overlap(self, ander: Vak) -> int:
        return max(0, min(self.eind, ander.eind) - max(self.start, ander.start))


def ticks(sec: float) -> int:
    if type(sec) not in (float, int) or not math.isfinite(sec):
        raise ValueError("tijd in seconden moet eindig zijn")
    return round(sec * TICKS)


def tijdvak(soort: str, start: int, eind: int, duur: int) -> Vak:
    if type(start) is not int or type(eind) is not int or not 0 <= start < eind <= duur:
        raise ValueError("tijdvak buiten mediaduur of ongeldige ticks")
    return Vak(soort, start, eind)


def waarheid(item: dict) -> list[Vak]:
    duur = ticks(item["duur_s"])
    labels = []
    positie = 0
    for s in item["segmenten"]:
        soort = "outro" if s["label"] == "aftiteling" else s["label"]
        vak = tijdvak(soort, ticks(s["start"]), ticks(s["eind"]), duur)
        if soort not in SKIP | INHOUD or vak.start != positie:
            raise ValueError("onbekend label, overlap of gat in grondwaarheid")
        if labels and labels[-1].soort == soort:
            vak = Vak(soort, labels.pop().start, vak.eind)
        labels.append(vak)
        positie = vak.eind
    if not labels or positie != duur:
        raise ValueError("onvolledige grondwaarheid")
    return labels


def koppels(labels: list[Vak], voorspeld: list[Vak]) -> list[tuple[Vak, Vak]]:
    """Maximaal aantal één-op-éénmatches bij IoU ≥ 0,5. Bij meerdere buren eerst de grootste IoU."""
    buren = []
    for p in voorspeld:
        scores = []
        for i, g in enumerate(labels):
            overlap = p.overlap(g)
            unie = p.eind - p.start + g.eind - g.start - overlap
            if p.soort == g.soort and 2 * overlap >= unie:
                scores.append((-overlap / unie, i))
        buren.append([i for _, i in sorted(scores)])
    eigenaar: dict[int, int] = {}

    def plaats(p: int, gezien: set[int]) -> bool:
        for i in buren[p]:
            if i in gezien:
                continue
            gezien.add(i)
            if i not in eigenaar or plaats(eigenaar[i], gezien):
                eigenaar[i] = p
                return True
        return False

    for p in range(len(voorspeld)):
        plaats(p, set())
    return [(labels[i], voorspeld[p]) for i, p in sorted(eigenaar.items())]


def bedekt(label: Vak, voorspeld: Iterable[Vak]) -> int:
    eind, totaal = label.start, 0
    for begin, stop in sorted((max(label.start, p.start), min(label.eind, p.eind)) for p in voorspeld if label.overlap(p)):
        totaal += max(0, stop - max(begin, eind))
        eind = max(eind, stop)
    return totaal


@dataclass
class Telling:
    tp: int = 0
    voorspeld: int = 0
    n: int = 0
    startfout: list[int] = field(default_factory=list)
    eindfout: list[int] = field(default_factory=list)

    def tel(self, paren: list[tuple[Vak, Vak]], n: int, voorspeld: int) -> None:
        self.tp += len(paren)
        self.voorspeld += voorspeld
        self.n += n
        self.startfout.extend(abs(p.start - g.start) for g, p in paren)
        self.eindfout.extend(abs(p.eind - g.eind) for g, p in paren)

    def score(self, soort: str) -> dict:
        precisie = wilson(self.tp, self.voorspeld) if self.voorspeld else None
        recall = wilson(self.tp, self.n) if self.n else None
        grens = self.startfout + self.eindfout
        def fouten(reeks: list[int]) -> dict | None:
            if not reeks:
                return None
            return {"mediaan_s": kwantiel(reeks, 0.5) / TICKS, "p95_s": kwantiel(reeks, 0.95) / TICKS,
                    "aandeel_binnen_1s": sum(f <= TICKS for f in reeks) / len(reeks)}
        gate = gate_label(self.n, STREEF[soort])
        if soort in GROEPEN:
            voldoet = bool(recall and recall.onder >= 0.65)
        else:
            p_min, r_min = DREMPELS[soort]
            voldoet = bool(precisie and recall and precisie.onder >= p_min and recall.onder >= r_min)
            if soort == "intro":
                voldoet = voldoet and kwantiel(grens, 0.95) <= 1.5 * TICKS
            if soort == "outro":
                voldoet = voldoet and kwantiel(self.eindfout, 0.95) <= 2 * TICKS
        noemer = self.voorspeld + self.n
        return {"n": self.n, "voorspeld": self.voorspeld, "tp": self.tp, "fp": self.voorspeld - self.tp, "fn": self.n - self.tp,
                "precisie": precisie.als_dict() if precisie else None, "recall": recall.als_dict() if recall else None,
                "f1": 2 * self.tp / noemer if noemer else None, "grensfout": fouten(grens),
                "startfout": fouten(self.startfout), "eindfout": fouten(self.eindfout),
                "gate": gate, "voldoet": voldoet if gate == "gate" else None}


def evalueer(items: list[dict], kandidaten: dict[str, list[Vak]], gepubliceerd: dict[str, list[Vak]]) -> tuple[dict, dict]:
    paden = {item["bestand"] for item in items}
    if not items or len(items) != len(paden) or kandidaten.keys() != paden or gepubliceerd.keys() != paden:
        raise ValueError("lege, dubbele of onvolledige afleveringenset")
    totaal = defaultdict(Telling)
    per_item = defaultdict(dict)
    per_variant = defaultdict(lambda: defaultdict(Telling))
    duur = fout = beschermd = geschonden = schade = 0
    for item in items:
        pad = item["bestand"]
        labels = waarheid(item)
        duur += ticks(item["duur_s"])
        groepen = [*SOORTEN, *(k for k, vlag in GROEPEN.items() if item[vlag])]
        for groep in groepen:
            soort = "intro" if groep in GROEPEN else groep
            refs = [g for g in labels if g.soort == soort]
            ps = [p for p in kandidaten[pad] if p.soort == soort]
            paren = koppels(refs, sorted(ps))
            per_item[groep][pad] = (len(paren), len(refs) + len(ps))
            totaal[groep].tel(paren, len(refs), len(ps))
            if groep in SOORTEN:
                per_variant[item["augmentatie"]][soort].tel(paren, len(refs), len(ps))
        for g in labels:
            if g.soort not in INHOUD:
                continue
            pub = gepubliceerd[pad]
            fout += bedekt(g, (p for p in pub if g.soort != "preview" or p.soort != "preview"))
            if g.soort in BESCHERMD:
                beschermd += 1
                overlap = bedekt(g, (p for p in pub if p.soort != "preview"))
                schade += overlap
                geschonden += int(overlap >= TICKS // 10)
    per_uur = fout * 3600 / duur
    rapport = {"items": len(items), "duur_s": duur / TICKS, "per_type": {s: totaal[s].score(s) for s in SOORTEN},
               "deelgroepen": {s: totaal[s].score(s) for s in GROEPEN},
               "per_augmentatie": {v: {s: t.score(s) for s, t in types.items()} for v, types in per_variant.items()},
               "onterecht_overgeslagen_s_per_uur": per_uur, "binnen_2s_per_uur": per_uur <= 2,
               "beschermd": {"n": beschermd, "geschonden_scenes": geschonden, "overlap_s": schade / TICKS,
                             "wilson": wilson(geschonden, beschermd).als_dict() if beschermd else None,
                             "gate": gate_label(beschermd, STREEF["beschermd"]), "nultolerantie": schade == 0}}
    return rapport, per_item


def gepaard(jl: dict, basis: dict, trekkingen: int = 10_000, seed: int = 20261127) -> dict:
    """Micro-F1-verschil JL − IS. Dezelfde afleveringen worden aan beide kanten met teruglegging getrokken."""
    uit = {}
    for groep in (*SOORTEN, *GROEPEN):
        a, b = jl.get(groep, {}), basis.get(groep, {})
        if a.keys() != b.keys():
            raise ValueError("afleveringen niet gepaard")
        rijen = [(*a[k], *b[k]) for k in sorted(a)]
        if not rijen:
            uit[groep] = None
            continue
        rng = random.Random(seed)
        def verschil(steekproef: list[tuple]) -> float | None:
            jtp, jn, btp, bn = map(sum, zip(*steekproef, strict=True))
            return 2 * jtp / jn - 2 * btp / bn if jn and bn else None
        waarden = []
        for _ in range(trekkingen):
            d = verschil(rng.choices(rijen, k=len(rijen)))
            if d is not None:
                waarden.append(d)
        uit[groep] = {"verschil_f1": verschil(rijen), "onder": kwantiel(waarden, 0.025) if waarden else None,
                      "boven": kwantiel(waarden, 0.975) if waarden else None, "geldige_trekkingen": len(waarden),
                      "trekkingen": trekkingen, "seed": seed}
    return uit
