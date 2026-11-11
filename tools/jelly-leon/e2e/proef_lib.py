"""Zuivere hulpfuncties van de pluginproef (JLT-64/65/68): schemacontrole, ruismasker, database- en bestandsvergelijking.

Alleen de standaardbibliotheek, zodat de proef in de CI zonder extra pakketten draait. Geen netwerk en geen Docker hier:
alles in dit bestand is met gewone unit-tests te controleren (tools/jelly-leon/tests/test_proef_lib.py).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any

DATUMTIJD = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$")
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
RUIS = "<ruis>"


# --------------------------------------------------------------------------------------------- schemacontrole
def valideer(waarde: Any, schema: dict[str, Any], doc: dict[str, Any], pad: str = "$") -> list[str]:
    """Controleert een waarde tegen een OpenAPI 3.0-schema (de trefwoorden die het pluginbestand gebruikt)."""
    if "$ref" in schema:
        schema = doc["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    if waarde is None:
        return [] if schema.get("nullable") else [f"{pad}: null is niet toegestaan"]
    fouten: list[str] = []
    soort = schema.get("type")
    past = {
        "object": isinstance(waarde, dict), "array": isinstance(waarde, list), "string": isinstance(waarde, str),
        "boolean": isinstance(waarde, bool),
        "integer": isinstance(waarde, int) and not isinstance(waarde, bool),
        "number": isinstance(waarde, (int, float)) and not isinstance(waarde, bool),
    }
    if soort is not None and not past.get(soort, False):
        return [f"{pad}: verwacht {soort}, kreeg {type(waarde).__name__}"]
    if "enum" in schema and waarde not in schema["enum"]:
        fouten.append(f"{pad}: {waarde!r} staat niet in {schema['enum']}")
    if isinstance(waarde, str):
        if "pattern" in schema and not re.search(schema["pattern"], waarde):
            fouten.append(f"{pad}: past niet op {schema['pattern']}")
        if schema.get("format") == "date-time" and not DATUMTIJD.match(waarde):
            fouten.append(f"{pad}: geen date-time")
        if schema.get("format") == "uuid":
            try:
                uuid.UUID(waarde)
            except ValueError:
                fouten.append(f"{pad}: geen uuid")
    if isinstance(waarde, (int, float)) and not isinstance(waarde, bool):
        if "minimum" in schema and waarde < schema["minimum"]:
            fouten.append(f"{pad}: kleiner dan {schema['minimum']}")
        if "maximum" in schema and waarde > schema["maximum"]:
            fouten.append(f"{pad}: groter dan {schema['maximum']}")
    if isinstance(waarde, dict):
        eigenschappen = schema.get("properties", {})
        fouten += [f"{pad}: verplicht veld {naam} ontbreekt" for naam in schema.get("required", []) if naam not in waarde]
        extra = schema.get("additionalProperties", True)
        for naam, inhoud in waarde.items():
            if naam in eigenschappen:
                fouten += valideer(inhoud, eigenschappen[naam], doc, f"{pad}.{naam}")
            elif extra is False:
                fouten.append(f"{pad}: onbekend veld {naam}")
            elif isinstance(extra, dict):
                fouten += valideer(inhoud, extra, doc, f"{pad}.{naam}")
    if isinstance(waarde, list) and "items" in schema:
        for i, inhoud in enumerate(waarde):
            fouten += valideer(inhoud, schema["items"], doc, f"{pad}[{i}]")
    return fouten


def antwoordschema(doc: dict[str, Any], methode: str, pad: str, status: int) -> dict[str, Any] | None:
    """Het JSON-schema dat het OpenAPI-bestand voor dit antwoord belooft; None als de status niet beschreven is."""
    antwoord = doc["paths"].get(pad, {}).get(methode.lower(), {}).get("responses", {}).get(str(status))
    if antwoord is None:
        return None
    return antwoord.get("content", {}).get("application/json", {}).get("schema", {})


def routes(doc: dict[str, Any], prefixen: tuple[str, ...]) -> set[tuple[str, str]]:
    """Alle (METHODE, pad) uit een OpenAPI-document onder de gegeven prefixen."""
    methoden = {"get", "put", "post", "delete", "patch", "head", "options"}
    return {(m.upper(), pad) for pad, ops in doc.get("paths", {}).items() if pad.startswith(prefixen)
            for m in ops if m in methoden}


# --------------------------------------------------------------------------------------------- ruismasker (JSON)
def verschillen(a: Any, b: Any, pad: tuple[Any, ...] = ()) -> set[tuple[Any, ...]]:
    """De paden waarop twee JSON-waarden verschillen (lijsten van ongelijke lengte tellen als één verschil)."""
    if isinstance(a, dict) and isinstance(b, dict):
        uit: set[tuple[Any, ...]] = set()
        for sleutel in set(a) | set(b):
            if sleutel not in a or sleutel not in b:
                uit.add((*pad, sleutel))
            else:
                uit |= verschillen(a[sleutel], b[sleutel], (*pad, sleutel))
        return uit
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return {pad}
        uit = set()
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            uit |= verschillen(x, y, (*pad, i))
        return uit
    return set() if a == b and type(a) is type(b) else {pad}


def masker(waarde: Any, paden: set[tuple[Any, ...]], pad: tuple[Any, ...] = ()) -> Any:
    """Vervangt de waarde op elk gegeven pad door een vast teken, zodat ruis tussen twee runs wegvalt."""
    if pad in paden:
        return RUIS
    if isinstance(waarde, dict):
        sleutels = set(waarde) | {p[len(pad)] for p in paden if len(p) == len(pad) + 1 and p[:len(pad)] == pad
                                  and isinstance(p[len(pad)], str)}
        return {s: masker(waarde.get(s), paden, (*pad, s)) for s in sorted(sleutels)}
    if isinstance(waarde, list):
        return [masker(x, paden, (*pad, i)) for i, x in enumerate(waarde)]
    return waarde


def pad_tekst(pad: tuple[Any, ...]) -> str:
    return "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in pad)


# --------------------------------------------------------------------------------------------- databases
def kopieer_db(bron: Path, doel: Path) -> Path:
    """Kopieert een SQLite-bestand met zijn WAL/SHM naar een werkmap, zodat lezen het origineel niet raakt."""
    doel.parent.mkdir(parents=True, exist_ok=True)
    for achtervoegsel in ("", "-wal", "-shm"):
        deel = Path(str(bron) + achtervoegsel)
        if deel.exists():
            shutil.copy2(deel, str(doel) + achtervoegsel)
    return doel


def lees_db(pad: Path) -> dict[str, tuple[list[str], list[tuple[Any, ...]]]]:
    """Alle tabellen van een SQLite-bestand: kolomnamen en gesorteerde rijen."""
    uit: dict[str, tuple[list[str], list[tuple[Any, ...]]]] = {}
    verbinding = sqlite3.connect(str(pad))
    try:
        namen = [r[0] for r in verbinding.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for naam in namen:
            cursor = verbinding.execute(f'SELECT * FROM "{naam}"')  # noqa: S608 - tabelnaam uit sqlite_master
            kolommen = [k[0] for k in cursor.description]
            uit[naam] = (kolommen, sorted(cursor.fetchall(), key=repr))
    finally:
        verbinding.close()
    return uit


def vergelijk_tabel(kolommen: list[str], a1: list[tuple[Any, ...]], a2: list[tuple[Any, ...]],
                    b: list[tuple[Any, ...]]) -> dict[str, Any]:
    """Vergelijkt de testrun (b) met de controle-run (a1); a2 is een tweede controle-run die alleen de ruis aanwijst.

    Uitkomst `oordeel`: gelijk | gelijk_na_masker | afwijking | ruis_onvergelijkbaar.
    """
    basis = {"rijen": {"a1": len(a1), "a2": len(a2), "b": len(b)}, "masker": []}
    if a1 == a2:
        return {**basis, "oordeel": "gelijk" if b == a1 else "afwijking"}
    if len(a1) != len(a2):
        # Het aantal rijen wisselt al tussen twee gelijke controle-runs: geen uitspraak mogelijk, wel zichtbaar gemeld.
        return {**basis, "oordeel": "ruis_onvergelijkbaar"}
    ruis = [i for i in range(len(kolommen))
            if sorted((r[i] for r in a1), key=repr) != sorted((r[i] for r in a2), key=repr)]

    def gemaskeerd(rijen: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
        return sorted((tuple(RUIS if i in ruis else w for i, w in enumerate(r)) for r in rijen), key=repr)

    basis["masker"] = [kolommen[i] for i in ruis]
    if gemaskeerd(a1) != gemaskeerd(a2):
        return {**basis, "oordeel": "ruis_onvergelijkbaar"}
    return {**basis, "oordeel": "gelijk_na_masker" if gemaskeerd(b) == gemaskeerd(a1) else "afwijking"}


def vergelijk_db(a1: Path, a2: Path, b: Path) -> dict[str, dict[str, Any]]:
    """Per tabel het oordeel van `vergelijk_tabel`; een tabel of kolom die alleen in één run bestaat is een afwijking."""
    da1, da2, db = lees_db(a1), lees_db(a2), lees_db(b)
    uit: dict[str, dict[str, Any]] = {}
    for naam in sorted(set(da1) | set(db)):
        if naam not in da1 or naam not in db or naam not in da2:
            uit[naam] = {"oordeel": "afwijking", "reden": "tabel bestaat niet in elke run", "masker": [], "rijen": {}}
        elif da1[naam][0] != db[naam][0] or da1[naam][0] != da2[naam][0]:
            uit[naam] = {"oordeel": "afwijking", "reden": "kolommen verschillen", "masker": [], "rijen": {}}
        else:
            uit[naam] = vergelijk_tabel(da1[naam][0], da1[naam][1], da2[naam][1], db[naam][1])
    return uit


# --------------------------------------------------------------------------------------------- bestanden
def boom(wortel: Path) -> dict[str, str]:
    """Relatief pad → sha256 van elk gewoon bestand onder de map."""
    uit: dict[str, str] = {}
    for pad in sorted(wortel.rglob("*")):
        if pad.is_file() and not pad.is_symlink():
            uit[pad.relative_to(wortel).as_posix()] = hashlib.sha256(pad.read_bytes()).hexdigest()
    return uit


def ruwe_treffers(wortel: Path, naalden: dict[str, bytes], overslaan: tuple[str, ...] = ()) -> dict[str, list[str]]:
    """Zoekt elke naald in de ruwe bytes van elk bestand onder de map. Uitkomst: naam van de naald → bestanden."""
    uit: dict[str, list[str]] = {}
    if not wortel.exists():
        return uit
    for pad in sorted(wortel.rglob("*")):
        relatief = pad.relative_to(wortel).as_posix()
        if not pad.is_file() or pad.is_symlink() or relatief.startswith(overslaan):
            continue
        try:
            inhoud = pad.read_bytes()
        except OSError:
            continue
        for naam, naald in naalden.items():
            if naald and naald in inhoud:
                uit.setdefault(naam, []).append(relatief)
    return uit


LOGREGEL = re.compile(r"^\[[^\]]*\] \[(\w+)\] \[\d+\] ([^ :]+): (.*)$")
_VARIABEL = re.compile(r"[0-9a-fA-F-]{8,}|\d+")


def log_handtekeningen(tekst: str, naalden: dict[str, str]) -> dict[tuple[str, str, str], int]:
    """Logregels waarin een geheim staat, teruggebracht tot (soort geheim, logcategorie, bericht-sjabloon) → aantal.

    Het geheim wordt vervangen door `<geheim>`, andere wisselende delen (ID's, getallen) door `#`. Zo is te zien of
    dezelfde regel ook in een controle-run zonder plugin voorkomt, zonder dat het geheim zelf in het rapport belandt.
    De soort is de naam van de naald tot aan de eerste dubbele punt (bijvoorbeeld `sessietoken:a1` → `sessietoken`).
    """
    uit: dict[tuple[str, str, str], int] = {}
    for regel in tekst.splitlines():
        for naam, naald in naalden.items():
            if not naald or naald not in regel:
                continue
            gemaskeerd = regel
            for andere in naalden.values():
                if andere:
                    gemaskeerd = gemaskeerd.replace(andere, "<geheim>")
            m = LOGREGEL.match(gemaskeerd)
            categorie, bericht = (m.group(2), m.group(3)) if m else ("?", gemaskeerd)
            delen = [_VARIABEL.sub("#", deel) for deel in bericht.split("<geheim>")]
            sleutel = (naam.split(":", 1)[0], categorie, "<geheim>".join(delen)[:200])
            uit[sleutel] = uit.get(sleutel, 0) + 1
    return uit


def guid_vormen(waarde: str) -> dict[str, bytes]:
    """Alle schrijfwijzen waarin een account-ID in een bestand kan staan (tekst met en zonder streepjes, bytes)."""
    g = uuid.UUID(waarde)
    return {
        "N": g.hex.encode(), "D": str(g).encode(), "N-hoofdletters": g.hex.upper().encode(),
        "D-hoofdletters": str(g).upper().encode(), "bytes": g.bytes, "bytes-le": g.bytes_le,
    }


def tekst_van(waarde: Any) -> str:
    return json.dumps(waarde, ensure_ascii=False, sort_keys=True)
