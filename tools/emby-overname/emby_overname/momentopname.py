"""Momentopname van alle Emby-kijkgegevens = het blijvende JSON-exportarchief (§10.9.2 stap 4).

Elke run begint met een momentopname (alleen-lezen); het plan wordt daarop gebaseerd. Hetzelfde bestand is het archief dat
de gebruiker bewaart vóór Emby wordt verwijderd en waaruit later opnieuw geïmporteerd kan worden (`--bron-archief`).

Inhoud per gebruiker: beleid (rechten, ouderlijk toezicht) en configuratie (taal- en ondertitelvoorkeuren), de zichtbare
items, per item met kijkgegevens: gezien (met datum en aantal), hervatpunt (ticks), favoriet, beoordeling, en de effectieve
spoorkeuze; per item: provider-ID's, pad en grootte. `inhoud_sha256` hangt niet af van het tijdstip van de export.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import TOOL_NAAM, __version__
from .emby import EmbyLezer
from .fouten import ControleFout
from .hulp import controleer_sha_bestand, nu_utc, schrijf_json_met_sha, sha256_json
from .model import AFSPEELBAAR, ItemInfo, Kijkgegevens, effectieve_spoorkeuze

SCHEMA = "jelly-leon/emby-kijkgegevens-export/1"
VLUCHTIGE_BELEIDSVELDEN = {"InvalidLoginAttemptCount", "LockedOutDate"}


def maak_momentopname(lezer: EmbyLezer, met_spoorkeuzes: bool = True,
                      voortgang: Callable[[str], None] | None = None) -> dict[str, Any]:
    melden = voortgang or (lambda _tekst: None)
    info = lezer.systeeminfo()
    bibliotheken = [
        {
            "id": str(b.get("Guid") or b.get("Id") or b.get("ItemId")), "item_id": str(b.get("ItemId") or b.get("Id")),
            "naam": b.get("Name"), "type": b.get("CollectionType"), "locaties": sorted(b.get("Locations") or []),
        }
        for b in lezer.bibliotheken()
    ]
    classificaties = [{"naam": r.get("Name"), "waarde": r.get("Value")} for r in lezer.leeftijdsclassificaties()]
    plugins = sorted(({"naam": p.get("Name"), "versie": p.get("Version")} for p in lezer.plugins()),
                     key=lambda p: (str(p["naam"]), str(p["versie"])))

    items: dict[str, dict[str, Any]] = {}
    gebruikers: list[dict[str, Any]] = []
    for gebruiker in sorted(lezer.gebruikers(), key=lambda g: str(g.get("Name"))):
        uid = str(gebruiker["Id"])
        melden(f"Emby: kijkgegevens van {gebruiker.get('Name')} lezen")
        zichtbaar: list[str] = []
        kijk: dict[str, dict[str, Any]] = {}
        for ruw in lezer.items_van_gebruiker(uid):
            info_item = ItemInfo.uit_api(ruw)
            zichtbaar.append(info_item.id)
            items.setdefault(info_item.id, info_item.naar_json())
            gegevens = Kijkgegevens.uit_userdata(ruw.get("UserData"))
            if gegevens.heeft_gegevens(info_item.type):
                kijk[info_item.id] = gegevens.naar_json()
        # Pad en grootte van de mediabronnen voor items met kijkgegevens (spoorkeuzes, "ander bestand").
        for ruw in lezer.details(uid, sorted(kijk)):
            detail = ItemInfo.uit_api(ruw)
            bestaand = items.setdefault(detail.id, detail.naar_json())
            if detail.grootte is not None:
                bestaand["grootte"] = detail.grootte
            if detail.pad and not bestaand.get("pad"):
                bestaand["pad"] = detail.pad
            if detail.bron_paden:
                bestaand["bron_paden"] = detail.bron_paden
        benoemd = []
        for ruw in lezer.benoemde_favorieten(uid):
            info_item = ItemInfo.uit_api(ruw)
            items.setdefault(info_item.id, info_item.naar_json())
            gegevens = Kijkgegevens.uit_userdata(ruw.get("UserData") or {"IsFavorite": True})
            if not gegevens.favoriet:
                gegevens = Kijkgegevens(favoriet=True)
            kijk.setdefault(info_item.id, gegevens.naar_json())
            benoemd.append(info_item.id)
        configuratie = dict(gebruiker.get("Configuration") or {})
        spoorkeuzes: dict[str, Any] = {}
        niet_gelezen: list[str] = []
        onthoudt = configuratie.get("RememberAudioSelections") or configuratie.get("RememberSubtitleSelections")
        if met_spoorkeuzes and onthoudt:
            for item_id in sorted(kijk):
                if items[item_id]["type"] in AFSPEELBAAR and items[item_id]["type"] != "Audio":
                    if items[item_id].get("grootte") == 0:
                        # Gemeten (Emby 4.10.2.0, QA-review): een bestand dat Emby nog niet heeft geanalyseerd heeft grootte 0
                        # en geen streams; een GET PlaybackInfo laat Emby het dan alsnog analyseren en die mediagegevens
                        # opslaan. Alleen lezen betekent: dan geen PlaybackInfo. Zo'n bestand is in Emby nooit afgespeeld
                        # (afspelen analyseert het), dus er is geen onthouden spoorkeuze; het staat wel in de export.
                        niet_gelezen.append(item_id)
                        continue
                    keuze = effectieve_spoorkeuze(lezer.afspeelinfo(item_id, uid))
                    if keuze:
                        spoorkeuzes[item_id] = keuze
        beleid = {k: v for k, v in (gebruiker.get("Policy") or {}).items() if k not in VLUCHTIGE_BELEIDSVELDEN}
        gebruikers.append(
            {
                "id": uid, "naam": gebruiker.get("Name"), "beleid": beleid, "configuratie": configuratie,
                "heeft_wachtwoord": bool(gebruiker.get("HasConfiguredPassword") or gebruiker.get("HasPassword")),
                "zichtbaar": sorted(set(zichtbaar)), "kijkgegevens": dict(sorted(kijk.items())),
                "spoorkeuzes": spoorkeuzes, "spoorkeuzes_niet_gelezen": niet_gelezen,
                "benoemde_favorieten": sorted(set(benoemd)),
            }
        )
    opname: dict[str, Any] = {
        "schema": SCHEMA,
        "gemaakt": nu_utc(),
        "tool": {"naam": TOOL_NAAM, "versie": __version__},
        "bron": {"server_id": info.get("Id"), "server_naam": info.get("ServerName"), "versie": info.get("Version"),
                 "product": "Emby Server"},
        "bibliotheken": sorted(bibliotheken, key=lambda b: str(b["naam"])),
        "classificaties": classificaties,
        "plugins": plugins,
        "items": dict(sorted(items.items())),
        "gebruikers": gebruikers,
    }
    opname["inhoud_sha256"] = inhoud_sha256(opname)
    return opname


def inhoud_sha256(opname: dict[str, Any]) -> str:
    return sha256_json({k: v for k, v in opname.items() if k not in ("gemaakt", "inhoud_sha256")})


def schrijf_archief(opname: dict[str, Any], pad: Path) -> str:
    return schrijf_json_met_sha(pad, opname)


def laad_archief(pad: Path) -> dict[str, Any]:
    """Laadt een exportarchief; de sha256 van het bestand én van de inhoud moeten kloppen (anders geen import)."""
    controleer_sha_bestand(pad)
    opname = json.loads(pad.read_text(encoding="utf-8"))
    if opname.get("schema") != SCHEMA:
        raise ControleFout(f"onbekend archiefschema {opname.get('schema')!r} in {pad.name}")
    if inhoud_sha256(opname) != opname.get("inhoud_sha256"):
        raise ControleFout(f"inhoud_sha256 van {pad.name} klopt niet: het archief is gewijzigd")
    return opname


def vergelijk_opnames(voor: dict[str, Any], na: dict[str, Any]) -> list[str]:
    """Verschillen in kijkgegevens, beleid, configuratie en spoorkeuzes per gebruiker (voor 'Emby vóór en na identiek')."""
    verschillen: list[str] = []
    per_naam_na = {g["naam"]: g for g in na["gebruikers"]}
    for g in voor["gebruikers"]:
        ander = per_naam_na.pop(g["naam"], None)
        if ander is None:
            verschillen.append(f"gebruiker {g['naam']} ontbreekt in de tweede opname")
            continue
        for sleutel in ("kijkgegevens", "beleid", "configuratie", "spoorkeuzes", "zichtbaar", "benoemde_favorieten"):
            if g.get(sleutel) != ander.get(sleutel):
                a, b = g.get(sleutel) or {}, ander.get(sleutel) or {}
                if isinstance(a, dict) and isinstance(b, dict):
                    sleutels = sorted({k for k in set(a) | set(b) if a.get(k) != b.get(k)})
                    verschillen.append(f"{g['naam']}: {sleutel} verschilt voor {len(sleutels)} sleutel(s): {sleutels[:10]}")
                else:
                    verschillen.append(f"{g['naam']}: {sleutel} verschilt")
    for naam in per_naam_na:
        verschillen.append(f"gebruiker {naam} is nieuw in de tweede opname")
    return verschillen
