"""Hulpfuncties: canonieke JSON en sha256, atomisch schrijven, tijdstempels exact (100-ns-ticks), geheimen lezen."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .fouten import GeheimFout

_DATUM_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,7}))?(Z|[+-]\d{2}:\d{2})?$")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def canoniek(data: Any) -> bytes:
    """Canonieke JSON-bytes (gesorteerde sleutels, geen witruimte, UTF-8) als basis voor elke sha256."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(data: Any) -> str:
    return sha256_bytes(canoniek(data))


def sha256_bestand(pad: Path) -> str:
    h = hashlib.sha256()
    with pad.open("rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def nu_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def map_stempel() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def schrijf_atomisch(pad: Path, inhoud: bytes | str, modus: int = 0o640) -> None:
    """Schrijft via een tijdelijk bestand + fsync + hernoemen, zodat een afgebroken run nooit een half bestand achterlaat."""
    pad.parent.mkdir(parents=True, exist_ok=True)
    data = inhoud.encode("utf-8") if isinstance(inhoud, str) else inhoud
    tijdelijk = pad.with_name(f".{pad.name}.{os.getpid()}.tmp")
    fd = os.open(tijdelijk, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, modus)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tijdelijk, pad)
    finally:
        if tijdelijk.exists():
            tijdelijk.unlink()
    _fsync_map(pad.parent)


def _fsync_map(map_pad: Path) -> None:
    try:
        fd = os.open(map_pad, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def schrijf_json_met_sha(pad: Path, data: Any) -> str:
    """Schrijft JSON (leesbaar ingesprongen) en een `<naam>.sha256` in sha256sum-formaat; geeft de sha256 terug."""
    tekst = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    schrijf_atomisch(pad, tekst)
    som = sha256_bytes(tekst.encode("utf-8"))
    schrijf_atomisch(pad.with_name(pad.name + ".sha256"), f"{som}  {pad.name}\n")
    return som


def controleer_sha_bestand(pad: Path) -> str:
    """Controleert `<pad>.sha256`; geeft de sha256 terug of gooit een fout als het niet klopt."""
    som_pad = pad.with_name(pad.name + ".sha256")
    if not som_pad.is_file():
        raise GeheimFout(f"controlesom ontbreekt: {som_pad}")
    verwacht = som_pad.read_text(encoding="utf-8").split()[0]
    werkelijk = sha256_bestand(pad)
    if verwacht != werkelijk:
        raise GeheimFout(f"sha256 klopt niet voor {pad.name}: verwacht {verwacht}, gemeten {werkelijk}")
    return werkelijk


# --- tijdstempels -------------------------------------------------------------------------------------------------

def datum_naar_ticks(waarde: str | None) -> int | None:
    """Emby/Jellyfin-datum ("2026-10-01T20:15:42.0000000Z") → 100-ns-ticks sinds 1970, exact (geen float)."""
    if not waarde:
        return None
    m = _DATUM_RE.match(waarde.strip())
    if not m:
        raise ValueError(f"onbekend datumformaat: {waarde!r}")
    jaar, maand, dag, uur, minuut, seconde = (int(m.group(i)) for i in range(1, 7))
    fractie = int((m.group(7) or "").ljust(7, "0"))
    zone = m.group(8) or "Z"
    basis = datetime(jaar, maand, dag, uur, minuut, seconde, tzinfo=UTC)
    seconden = int((basis - _EPOCH).total_seconds())
    if zone != "Z":
        teken = 1 if zone[0] == "+" else -1
        seconden -= teken * (int(zone[1:3]) * 3600 + int(zone[4:6]) * 60)
    return seconden * 10_000_000 + fractie


def ticks_naar_datum(ticks: int | None) -> str | None:
    """100-ns-ticks → canonieke tekst met 7 decimalen en `Z` (zoals Emby en Jellyfin die teruggeven)."""
    if ticks is None:
        return None
    seconden, fractie = divmod(ticks, 10_000_000)
    basis = datetime.fromtimestamp(seconden, tz=UTC)
    return basis.strftime("%Y-%m-%dT%H:%M:%S") + f".{fractie:07d}Z"


def leesbare_datum(ticks: int | None) -> str:
    if ticks is None:
        return "—"
    seconden = ticks // 10_000_000
    return datetime.fromtimestamp(seconden, tz=UTC).strftime("%d-%m-%Y %H:%M:%S UTC")


def leesbare_positie(ticks: int | None) -> str:
    if not ticks:
        return "0:00:00"
    totaal = ticks // 10_000_000
    uren, rest = divmod(totaal, 3600)
    minuten, seconden = divmod(rest, 60)
    return f"{uren}:{minuten:02d}:{seconden:02d}"


# --- paden en namen -----------------------------------------------------------------------------------------------

def normaliseer_pad(pad: str | None) -> str | None:
    if not pad:
        return None
    return unicodedata.normalize("NFC", pad).rstrip("/") or "/"


def normaliseer_naam(naam: str) -> str:
    return unicodedata.normalize("NFC", naam).strip().casefold()


# --- geheimen -----------------------------------------------------------------------------------------------------

def lees_geheim(pad: Path, omschrijving: str) -> str:
    """Leest een API-sleutel uit de geheimenmap. Weigert bestanden die de groep of anderen kunnen lezen of schrijven.

    De sleutel komt nooit in een log, rapport, export of foutmelding: alleen het pad wordt genoemd.
    """
    try:
        info = pad.stat()
    except FileNotFoundError as fout:
        raise GeheimFout(f"{omschrijving}: bestand {pad} bestaat niet") from fout
    if not stat.S_ISREG(info.st_mode):
        raise GeheimFout(f"{omschrijving}: {pad} is geen gewoon bestand")
    if info.st_mode & 0o077:
        raise GeheimFout(
            f"{omschrijving}: {pad} is leesbaar of schrijfbaar voor groep/anderen (modus {stat.S_IMODE(info.st_mode):04o}); "
            "zet de rechten op 0600 (geheimenmap 0700)"
        )
    waarde = pad.read_text(encoding="utf-8").strip()
    if not waarde or any(c.isspace() for c in waarde) or len(waarde) > 512:
        raise GeheimFout(f"{omschrijving}: {pad} bevat geen geldige API-sleutel (één regel zonder spaties)")
    return waarde
