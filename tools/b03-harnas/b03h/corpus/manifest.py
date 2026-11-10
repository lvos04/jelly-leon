"""sha256-manifesten: maken, `sha256sum -c`-compatibel wegschrijven, controleren en bevriezen.

Een bevroren manifest staat in de repo (alleen namen, groottes en sha256; nooit media of labels) onder
``docs/platform-v2/test-evidence/b03-016-corpus/``. Is een testset bevroren, dan moet elke nieuwe generatie met dezelfde
seed en parameters exact dezelfde sha256's geven; anders weigert ``bevries`` (nieuwe versie nodig, nooit stil overschrijven).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "jelly-leon/b03-016-testset-manifest/1"
BLOK = 1 << 20


def sha256_bestand(pad: Path) -> str:
    h = hashlib.sha256()
    with open(pad, "rb") as f:
        while blok := f.read(BLOK):
            h.update(blok)
    return h.hexdigest()


def bestanden(map_: Path) -> list[dict[str, Any]]:
    """Alle bestanden onder map_ (relatief, gesorteerd), zonder de manifestbestanden zelf."""
    uit = []
    for pad in sorted(p for p in map_.rglob("*") if p.is_file()):
        rel = pad.relative_to(map_).as_posix()
        if rel in ("SHA256SUMS", "manifest.json") or rel.endswith(".tmp"):
            continue
        uit.append({"pad": rel, "grootte": pad.stat().st_size, "sha256": sha256_bestand(pad)})
    return uit


def inhoud_sha256(lijst: list[dict[str, Any]]) -> str:
    """Eén sha256 over de hele set (pad + sha256 per bestand), onafhankelijk van tijdstempels."""
    h = hashlib.sha256()
    for b in lijst:
        h.update(f"{b['sha256']}  {b['pad']}\n".encode())
    return h.hexdigest()


def maak(map_: Path, *, recept: str, versie: str, seed: int, schaal: str, parameters: dict[str, Any],
         ffmpeg: dict[str, Any], bronnen: list[dict[str, Any]], licenties: list[str], beperkt: bool,
         aantallen: dict[str, int]) -> dict[str, Any]:
    lijst = bestanden(map_)
    return {
        "schema": SCHEMA, "recept": recept, "versie": versie, "seed": seed, "schaal": schaal, "parameters": parameters,
        "ffmpeg": ffmpeg, "bronnen": bronnen, "licenties": sorted(set(licenties)), "licentie_beperkt": beperkt,
        "aantallen": aantallen, "bestanden": lijst, "set_sha256": inhoud_sha256(lijst),
        "totaal_bytes": sum(b["grootte"] for b in lijst), "gemaakt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def schrijf(map_: Path, manifest: dict[str, Any]) -> None:
    """manifest.json + SHA256SUMS (formaat van sha256sum: '<hash>  <pad>') in de set zelf."""
    regels = "".join(f"{b['sha256']}  {b['pad']}\n" for b in manifest["bestanden"])
    (map_ / "SHA256SUMS").write_text(regels, encoding="utf-8")
    (map_ / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def controleer(map_: Path, manifest: dict[str, Any]) -> list[str]:
    """Zelfde uitkomst als `sha256sum -c SHA256SUMS`, plus onverwachte extra bestanden."""
    fouten = []
    verwacht = {b["pad"]: b for b in manifest["bestanden"]}
    for rel, b in verwacht.items():
        pad = map_ / rel
        if not pad.is_file():
            fouten.append(f"ontbreekt: {rel}")
        elif sha256_bestand(pad) != b["sha256"]:
            fouten.append(f"sha256 wijkt af: {rel}")
    for b in bestanden(map_):
        if b["pad"] not in verwacht:
            fouten.append(f"extra bestand: {b['pad']}")
    return fouten


def bevroren_pad(map_bevroren: Path, recept: str, versie: str, schaal: str) -> Path:
    return map_bevroren / f"{recept}.v{versie}.{schaal}.manifest.json"


def bevries(manifest: dict[str, Any], map_bevroren: Path) -> tuple[Path, str]:
    """Bevriest de set. Bestaat er al een bevroren manifest, dan moet de inhoud exact gelijk zijn.

    Geeft (pad, uitkomst) terug met uitkomst 'nieuw bevroren' of 'gelijk aan bevroren manifest'.
    """
    pad = bevroren_pad(map_bevroren, manifest["recept"], manifest["versie"], manifest["schaal"])
    if pad.exists():
        oud = json.loads(pad.read_text(encoding="utf-8"))
        sleutels = ("recept", "versie", "seed", "schaal", "parameters")
        if any(oud.get(k) != manifest.get(k) for k in sleutels):
            raise ValueError(f"{pad.name}: recept/seed/parameters wijken af van het bevroren manifest; maak een nieuwe versie")
        if oud["set_sha256"] != manifest["set_sha256"]:
            verschil = sorted({b["pad"] for b in oud["bestanden"]} ^ {b["pad"] for b in manifest["bestanden"]})[:5]
            raise ValueError(f"{pad.name}: niet reproduceerbaar (set_sha256 {manifest['set_sha256'][:12]} ≠ "
                             f"bevroren {oud['set_sha256'][:12]}; padverschil {verschil})")
        nieuw = {k: v for k, v in manifest.get("aantallen", {}).items() if k not in oud.get("aantallen", {})}
        if nieuw:
            # Alleen tellingen erbij (bv. 'effectief'); de inhoud (set_sha256) is aantoonbaar gelijk.
            oud["aantallen"] = dict(sorted({**oud.get("aantallen", {}), **nieuw}.items()))
            oud.setdefault("tellingen_aangevuld", []).append(manifest["gemaakt"])
            pad.write_text(json.dumps(oud, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return pad, "gelijk aan bevroren manifest (tellingen aangevuld)"
        return pad, "gelijk aan bevroren manifest"
    map_bevroren.mkdir(parents=True, exist_ok=True)
    bevroren = {k: v for k, v in manifest.items() if k != "gemaakt"}
    bevroren["bevroren_op"] = manifest["gemaakt"]
    tijdelijk = pad.with_suffix(".tmp")
    tijdelijk.write_text(json.dumps(bevroren, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tijdelijk.replace(pad)
    return pad, "nieuw bevroren"
