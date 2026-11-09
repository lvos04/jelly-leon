"""Meetbewijs (acceptatie B03-016): per metriek methode, n, interval, image-digest, seed en loadavg; voormeting 12.4 en
definitieve meting op de forkbasis-digest apart gelabeld; validatie volgens contract §11 (Intel-iGPU in de opmerking).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .statistiek import Interval

SCHEMA = "jelly-leon/b03-016-baseline/1"
LABELS = {"voormeting-12.4", "definitief-forkbasis"}
SYSTEMEN = {"stock-standaard", "stock-best", "jelly-leon"}
SOORTEN = {"proportie", "continu", "telling"}
VALIDATIE = {"Sim-getest", "NIET GEVALIDEERD (echte NAS)", "NIET GEVALIDEERD (hardware)", "NIET GEVALIDEERD (Mac/Xcode)"}
DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")


def metriek(*, id: str, functie: str, omschrijving: str, methode: str, systeem: str, soort: str, image: str, seed: int | None,
            runs: list[dict[str, Any]], waarde: dict[str, Any], interval: Interval | None, n: int, eenheid: str = "",
            gate: str = "", validatie: str = "Sim-getest", opmerking: str = "") -> dict[str, Any]:
    """Eén meetrecord. ``runs`` bevat per run de lastgegevens (RunLast.als_dict) en de ruwe waarde(n)."""
    return {
        "id": id, "functie": functie, "omschrijving": omschrijving, "methode": methode, "systeem": systeem,
        "soort": soort, "eenheid": eenheid, "image": image, "seed": seed, "n": n, "waarde": waarde,
        "interval": interval.als_dict() if interval else None, "gate": gate, "runs": runs,
        "runs_geldig": sum(1 for r in runs if r.get("last", {}).get("geldig", True)),
        "validatie": validatie, "opmerking": opmerking,
    }


def controleer(document: dict[str, Any]) -> list[str]:
    """Problemen in een baselinedocument (leeg = in orde). Wordt in de tests en vóór het schrijven gebruikt."""
    fouten: list[str] = []
    if document.get("schema") != SCHEMA:
        fouten.append(f"schema {document.get('schema')!r} ≠ {SCHEMA}")
    if document.get("label") not in LABELS:
        fouten.append(f"label {document.get('label')!r} niet in {sorted(LABELS)}")
    images = document.get("images") or {}
    for naam, ref in images.items():
        if not DIGEST_RE.search(str(ref)):
            fouten.append(f"image {naam} zonder vaste digest: {ref}")
    for m in document.get("metingen", []):
        mid = m.get("id", "?")
        for veld in ("methode", "systeem", "soort", "image", "n", "runs", "validatie"):
            if m.get(veld) in (None, "", []):
                fouten.append(f"{mid}: veld {veld} ontbreekt")
        if "seed" not in m:
            fouten.append(f"{mid}: seed ontbreekt (null mag als de meting geen toeval kent)")
        if m.get("systeem") not in SYSTEMEN:
            fouten.append(f"{mid}: systeem {m.get('systeem')!r}")
        if m.get("soort") not in SOORTEN:
            fouten.append(f"{mid}: soort {m.get('soort')!r}")
        if m.get("image") and not DIGEST_RE.search(str(m["image"])):
            fouten.append(f"{mid}: image zonder digest")
        if m.get("soort") in ("proportie", "continu") and not m.get("interval"):
            fouten.append(f"{mid}: interval ontbreekt")
        for deel in str(m.get("validatie", "")).split("; "):
            if deel and deel not in VALIDATIE:
                fouten.append(f"{mid}: validatie {deel!r} niet uit contract §11 (Intel-iGPU hoort in de opmerking)")
        for r in m.get("runs", []):
            last = r.get("last", {})
            if "loadavg_voor" not in last or "geldig" not in last:
                fouten.append(f"{mid}: run zonder loadavg/geldigheid")
                break
    return fouten


def schrijf(pad: Path, document: dict[str, Any]) -> None:
    fouten = controleer(document)
    if fouten:
        raise ValueError("baselinebewijs onvolledig: " + "; ".join(fouten[:10]))
    pad.parent.mkdir(parents=True, exist_ok=True)
    tijdelijk = pad.with_suffix(pad.suffix + ".tmp")
    tijdelijk.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tijdelijk.replace(pad)
