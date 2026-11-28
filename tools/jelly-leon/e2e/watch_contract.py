"""WT-1 op de lokale proefserver. Bewaar alleen structurele opnamen en hashes van genormaliseerde antwoordbytes."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from b03h.jfapi import Http

SLUG = "watch"


def schakel(http: Http, aan: bool) -> None:
    status, _, kop = http.ruw("GET", "/media/v1/modules")
    etag = next((v for k, v in kop.items() if k.lower() == "etag"), None)
    if status != 200 or not etag:
        raise RuntimeError(f"modulelijst zonder bruikbare ETag (HTTP {status})")
    antwoord = http.doe("PUT", "/media/v1/modules/watch", body={"enabled": aan},
                        headers={"If-Match": etag, "Idempotency-Key": str(uuid.uuid4())})
    if not any(m["slug"] == SLUG and m["enabled"] is aan for m in antwoord["items"]):
        raise RuntimeError("Watch Together-schakelaar nam de gevraagde stand niet over")


def contract(document: dict[str, Any]) -> dict[str, Any]:
    """Ook een wijziging in een genest, door de route gerefereerd schema telt."""
    paden = {p: v for p, v in document["paths"].items() if p.startswith("/SyncPlay/") or p == "/GetUtcTime"}
    if sum(len(v) for p, v in paden.items() if p.startswith("/SyncPlay/")) != 22 or "get" not in paden.get("/GetUtcTime", {}):
        raise ValueError("verwacht 22 SyncPlay-operaties en GET /GetUtcTime")
    schemas: dict[str, Any] = {}

    def volg(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref", "")
            if ref.startswith("#/components/schemas/"):
                naam = ref.split("/")[-1]
                if naam not in schemas:
                    schemas[naam] = document["components"]["schemas"][naam]
                    volg(schemas[naam])
            for waarde in node.values():
                volg(waarde)
        elif isinstance(node, list):
            for waarde in node:
                volg(waarde)

    volg(paden)
    return {"paths": paden, "schemas": schemas}


def groepsopname(http: Http, tijdens: Callable[[str], None] | None = None) -> dict[str, str]:
    """Maak een echte, niet-lege testgroep. Vergelijk ook veldvolgorde, namen en witruimte."""
    nieuw = http.doe("POST", "/SyncPlay/New", body={"GroupName": "WT-contract"})
    groep = nieuw["GroupId"]
    uuid.UUID(groep)
    hashes = {}
    try:
        if tijdens is not None:
            tijdens(groep)
        for naam, pad in (("lijst", "/SyncPlay/List"), ("groep", "/SyncPlay/" + groep)):
            status, ruw, _ = http.ruw("GET", pad)
            if status != 200:
                raise RuntimeError(f"WT-1 {naam} HTTP {status}")
            data = json.loads(ruw)
            if naam == "lijst":
                if len(data) != 1:
                    raise RuntimeError("verwacht uitsluitend de eigen proefgroep")
                data = data[0]
            if data["GroupId"] != groep or data["GroupName"] != "WT-contract" or not data["Participants"]:
                raise RuntimeError("de gevraagde groep heeft geen herkenbare deelnemer")
            tijd = data["LastUpdatedAt"]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T[0-9:.]+Z", tijd):
                raise ValueError("onverwacht formaat van de groeptijd")
            for sleutel, waarde, vervanger in (("GroupId", groep, b"ID"), ("LastUpdatedAt", tijd, b"UTC")):
                patroon = rb'("' + sleutel.encode() + rb'"\s*:\s*")' + re.escape(waarde.encode()) + rb'(")'
                ruw, aantal = re.subn(patroon, lambda m, tekst=vervanger: m[1] + tekst + m[2], ruw)
                if aantal != 1:
                    raise ValueError("normalisatie moet precies één veld vervangen")
            hashes[naam] = hashlib.sha256(ruw).hexdigest()
    finally:
        http.doe("POST", "/SyncPlay/Leave")
    return hashes
