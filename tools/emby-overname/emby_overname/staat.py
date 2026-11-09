"""Staat en journaal in de werkmap (op de NAS: onder `/config/data/jelly-leon/overname/`).

- `staat/staat.json`: per Emby-gebruiker de Jelly Leon-gebruiker, of de tool die aanmaakte, de sha van het laatst
  geschreven beleid en per item de Emby-waarden bij de laatste geslaagde overzetting (P, voor de laatste delta).
- `staat/journaal.jsonl`: write-ahead-journaal. Vóór elke schrijfactie een `voornemen` (met basis en doel), erna `klaar`.
  Na een afbreking (kill) bepaalt `herstel` per open voornemen in Jelly Leon zelf of het al is uitgevoerd: zo wordt niets
  dubbel geschreven en geen aantal dubbel opgeteld.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .fouten import ControleFout
from .hulp import nu_utc, schrijf_atomisch

STAAT_SCHEMA = "jelly-leon/emby-overname-staat/1"


class Werkmap:
    def __init__(self, pad: Path) -> None:
        self.pad = pad
        self.staat_pad = pad / "staat" / "staat.json"
        self.journaal_pad = pad / "staat" / "journaal.jsonl"
        self.plannen = pad / "plannen"
        self.runs = pad / "runs"
        for map_pad in (self.staat_pad.parent, self.plannen, self.runs):
            map_pad.mkdir(parents=True, exist_ok=True)
            os.chmod(map_pad, 0o700)

    def lees_staat(self) -> dict[str, Any]:
        if not self.staat_pad.is_file():
            return {"schema": STAAT_SCHEMA, "gebruikers": {}, "runs": []}
        staat = json.loads(self.staat_pad.read_text(encoding="utf-8"))
        if staat.get("schema") != STAAT_SCHEMA:
            raise ControleFout(f"onbekend staatschema in {self.staat_pad}")
        return staat

    def schrijf_staat(self, staat: dict[str, Any]) -> None:
        staat["bijgewerkt"] = nu_utc()
        schrijf_atomisch(self.staat_pad, json.dumps(staat, ensure_ascii=False, sort_keys=True, indent=1) + "\n")

    def journaal_regels(self) -> list[dict[str, Any]]:
        if not self.journaal_pad.is_file():
            return []
        regels = []
        for regel in self.journaal_pad.read_text(encoding="utf-8").splitlines():
            if not regel.strip():
                continue
            try:
                regels.append(json.loads(regel))
            except json.JSONDecodeError:
                break  # een half geschreven laatste regel (kill tijdens schrijven) telt niet
        return regels

    def journaal(self, record: dict[str, Any]) -> None:
        """Voegt één record toe en wacht tot het op schijf staat (fsync) voordat de tool verdergaat."""
        regel = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        fd = os.open(self.journaal_pad, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            os.write(fd, regel.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def wis_journaal(self) -> None:
        if self.journaal_pad.exists():
            schrijf_atomisch(self.journaal_pad, "")


def open_run(regels: list[dict[str, Any]]) -> str | None:
    """Het run-ID van een niet afgeronde overzetting in het journaal (of None)."""
    gestart: dict[str, dict[str, Any]] = {}
    for r in regels:
        if r.get("t") == "run_begin":
            gestart[r["run"]] = r
        elif r.get("t") == "run_einde":
            gestart.pop(r["run"], None)
    return next(iter(gestart), None)


def plan_van_run(regels: list[dict[str, Any]], run: str) -> str | None:
    for r in regels:
        if r.get("t") == "run_begin" and r.get("run") == run:
            return r.get("plan_sha256")
    return None
