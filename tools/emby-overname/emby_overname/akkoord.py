"""Akkoord van de gebruiker: op het plan (vóór het schrijven) en op elk verschil (vóór de overstap).

Zonder volledig akkoord geen overzetting en geen cutover (HARDE EIS, §10.9 punt 1). Een akkoord hoort bij precies één
rapport (inhoud-sha256) en — bij het plan — bij precies één plan (plan-sha256).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .fouten import AkkoordFout

SCHEMA = "jelly-leon/emby-overname-akkoord/1"


def lees_akkoord(pad: Path) -> dict[str, Any]:
    try:
        akkoord = json.loads(pad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as fout:
        raise AkkoordFout(f"akkoord-bestand {pad} is niet leesbaar: {fout}") from fout
    if akkoord.get("schema") != SCHEMA:
        raise AkkoordFout(f"akkoord-bestand {pad}: onbekend schema {akkoord.get('schema')!r}")
    if not str(akkoord.get("akkoord_door") or "").strip():
        raise AkkoordFout("akkoord-bestand: 'akkoord_door' (wie gaf akkoord) ontbreekt")
    if not isinstance(akkoord.get("verschillen"), list):
        raise AkkoordFout("akkoord-bestand: 'verschillen' moet een lijst met verschil-ID's zijn")
    return akkoord


def controleer_verschillen(akkoord: dict[str, Any], vereist: list[str]) -> list[str]:
    """Geeft de verschil-ID's terug waarop nog geen akkoord is gegeven (leeg = volledig akkoord)."""
    gegeven = {str(v) for v in akkoord.get("verschillen") or []}
    return sorted(set(vereist) - gegeven)


def controleer_cutover(rapport: dict[str, Any], akkoord: dict[str, Any]) -> list[str]:
    """Akkoord voor de overstap: zelfde rapportinhoud en elk verschil akkoord. Geeft de problemen (leeg = in orde)."""
    problemen: list[str] = []
    if akkoord.get("soort") != "cutover":
        problemen.append(f"akkoord is van soort {akkoord.get('soort')!r}, verwacht 'cutover'")
    if rapport.get("soort") != "overzetting":
        problemen.append(f"rapport is van soort {rapport.get('soort')!r}; voor de overstap telt alleen een vóór/na-rapport")
    if akkoord.get("rapport_inhoud_sha256") != rapport.get("inhoud_sha256"):
        problemen.append("akkoord hoort bij een ander rapport (inhoud-sha256 verschilt)")
    if not rapport.get("toestand", {}).get("verantwoord"):
        problemen.append("niet alle Emby-kijkgegevens zijn verantwoord (overgezet of op de afhandellijst)")
    ontbrekend = controleer_verschillen(akkoord, rapport.get("akkoord", {}).get("verschillen") or [])
    if ontbrekend:
        problemen.append(f"geen akkoord op {len(ontbrekend)} verschil(len): {', '.join(ontbrekend[:20])}")
    return problemen
