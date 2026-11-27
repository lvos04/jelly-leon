"""Privéoverdracht van een lokale JLT-70-proef aan het Android-harnas."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from emby_overname.hulp import schrijf_atomisch

SCHEMA = "jelly-leon/clientproef/1"


def bereid_uitvoer_voor(uitvoer: Path, repo: Path) -> None:
    """Reserveer een lege werkmap voordat de proef containers of geheimen aanmaakt."""
    if uitvoer.is_relative_to(repo) or any((p / ".git").is_file() or (p / ".git/HEAD").is_file()
                                          for p in (uitvoer, *uitvoer.parents)):
        raise ValueError("De uitvoermap voor de clientproef moet buiten een Git-werkboom liggen.")
    uitvoer.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(uitvoer.iterdir()):
        raise ValueError("Kies een lege uitvoermap voor de clientproef.")
    (uitvoer / "werk").mkdir(mode=0o700)


def controleer_overdracht(data: dict[str, Any]) -> None:
    if (set(data) != {"schema", "image", "datamap", "media", "gebruikers"} or data["schema"] != SCHEMA
            or data["datamap"] != "config" or data["media"] != "media" or not isinstance(data["image"], str) or not data["image"]):
        raise ValueError("Onbekend veld of ongeldig formaat in de clientoverdracht.")
    gebruikers = data["gebruikers"]
    if not isinstance(gebruikers, list) or not gebruikers:
        raise ValueError("De clientoverdracht mist de proefgebruikers.")
    for g in gebruikers:
        if (not isinstance(g, dict) or set(g) != {"naam", "wachtwoord", "item_id", "verwacht_ticks"}
                or not all(isinstance(g[k], str) and g[k] for k in ("naam", "wachtwoord", "item_id"))
                or type(g["verwacht_ticks"]) is not int or g["verwacht_ticks"] <= 0):
            raise ValueError("Onbekend veld of ongeldige gebruiker in de clientoverdracht.")
    if any(len({g[k] for g in gebruikers}) != len(gebruikers) for k in ("naam", "wachtwoord")):
        raise ValueError("Elke proefgebruiker heeft een eigen naam en wegwerpwachtwoord nodig.")


def publiceer(uitvoer: Path, gegevens: dict[str, Any], geheimen: Iterable[str]) -> None:
    """De gestopte doelserver, media en inloggegevens worden samen zichtbaar."""
    controleer_overdracht(gegevens)
    inhoud = json.dumps(gegevens, ensure_ascii=False, indent=2) + "\n"
    if any(waarde in inhoud for waarde in geheimen):
        raise ValueError("Een servergeheim komt voor in de clientoverdracht.")
    werk = uitvoer / "werk"
    pakket = werk / "clientproef"
    pakket.mkdir(mode=0o700)
    (werk / "client-config").rename(pakket / "config")
    (werk / "bib" / "jl").rename(pakket / "media")
    schrijf_atomisch(pakket / "clientproef.json", inhoud, modus=0o600)
    pakket.rename(uitvoer / "clientproef")
