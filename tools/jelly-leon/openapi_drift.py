#!/usr/bin/env python3
"""OpenAPI-driftcontrole van de upstream-API (CI-job *server*): wijkt de gegenereerde `openapi.json` af van de
vastgelegde `docs/openapi/jelly-leon.openapi.json`?

Gemeten op 2026-11-09: upstream (`ApiServiceCollectionExtensions`) laadt de XML-docbestanden met
`Directory.EnumerateFiles` — zonder sortering, dus in de volgorde van het bestandssysteem. Bij eigenschappen die naar
een ander schema verwijzen ($ref) bepaalt die volgorde welke XML-tekst als `description` wint ("Gets or sets the user."
of "Class UserDto."). Dezelfde broncode, SDK en pakketten gaven in de oude sandbox en op de Ubuntu-machine daardoor
een ander bestand (22 beschrijvingen verschillend, verder identiek). Byte-vergelijking is dus omgevingsafhankelijk.

Daarom vergelijkt dit hulpmiddel in twee lagen:
  1. byte-gelijk → in orde;
  2. structureel gelijk (paden, operaties, parameters, schema's, typen, enums, verplichte velden, …) en alleen
     `description`-teksten anders → in orde met een waarschuwing (bekend upstream-nondeterminisme, geen API-wijziging);
  3. elke andere afwijking → API-wijziging = core-patch → falen (exitcode 1).
Upstream-code wordt NIET gepatcht (geen core-patch voor documentatievolgorde; ADR-0010).

Exitcodes: 0 = geen API-drift, 1 = API-drift, 3 = bestand ontbreekt of is geen geldige JSON.
Alleen standaardbibliotheek.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# In deze subbomen zijn sleutels gegevens (voorbeeldwaarden, standaardwaarden), geen OpenAPI-velden.
DATA_KEYS = frozenset({"example", "examples", "default", "enum", "x-enum-varnames"})
MAX_LISTED = 20


def strip_descriptions(node: object, *, in_data: bool = False) -> object:
    """Kopie zonder `description`-teksten van OpenAPI-objecten (niet binnen voorbeeld-/standaardwaarden)."""
    if isinstance(node, dict):
        result = {}
        for key, value in node.items():
            if not in_data and key == "description" and isinstance(value, str):
                continue
            result[key] = strip_descriptions(value, in_data=in_data or key in DATA_KEYS)
        return result
    if isinstance(node, list):
        return [strip_descriptions(item, in_data=in_data) for item in node]
    return node


def diff_paths(left: object, right: object, path: str = "$") -> list[str]:
    """JSON-paden waar twee documenten verschillen (diepte-eerst, in documentvolgorde)."""
    if isinstance(left, dict) and isinstance(right, dict):
        found: list[str] = []
        for key in list(left) + [k for k in right if k not in left]:
            child = f"{path}[{json.dumps(key, ensure_ascii=False)}]"
            if key not in left:
                found.append(f"{child} (alleen in gegenereerd)")
            elif key not in right:
                found.append(f"{child} (ontbreekt in gegenereerd)")
            else:
                found += diff_paths(left[key], right[key], child)
        return found
    if isinstance(left, list) and isinstance(right, list):
        found = []
        for index, (a, b) in enumerate(zip(left, right, strict=False)):
            found += diff_paths(a, b, f"{path}[{index}]")
        if len(left) != len(right):
            found.append(f"{path} (lengte {len(left)} ≠ {len(right)})")
        return found
    return [] if left == right else [path]


def load(path: Path) -> tuple[bytes, object]:
    raw = path.read_bytes()
    return raw, json.loads(raw)


def compare(expected_path: Path, generated_path: Path) -> tuple[int, list[str]]:
    """Geeft (exitcode, meldingen). Meldingen beginnen met 'OK', 'WAARSCHUWING' of 'FOUT'."""
    try:
        expected_raw, expected = load(expected_path)
        generated_raw, generated = load(generated_path)
    except FileNotFoundError as exc:
        return 3, [f"FOUT: bestand ontbreekt: {exc.filename}"]
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return 3, [f"FOUT: geen geldige JSON: {exc}"]
    if not generated_raw.strip():
        return 3, [f"FOUT: {generated_path} is leeg (openapi.json niet gegenereerd)"]
    if expected_raw == generated_raw:
        return 0, [f"OK: OpenAPI byte-gelijk aan {expected_path}"]

    structural = diff_paths(strip_descriptions(expected), strip_descriptions(generated))
    if structural:
        lines = [
            f"FOUT: OpenAPI wijkt structureel af van {expected_path} ({len(structural)} plaatsen). Een API-wijziging is een "
            "core-patch: registreer hem in docs/platform-v2/PATCHES.md en werk het OpenAPI-bestand bewust bij.",
        ]
        lines += [f"  - {item}" for item in structural[:MAX_LISTED]]
        if len(structural) > MAX_LISTED:
            lines.append(f"  … en nog {len(structural) - MAX_LISTED}")
        return 1, lines

    texts = diff_paths(expected, generated)
    if not texts:
        return 0, [f"WAARSCHUWING: OpenAPI inhoudelijk gelijk aan {expected_path}; alleen opmaak of sleutelvolgorde verschilt."]
    lines = [
        f"WAARSCHUWING: OpenAPI structureel gelijk aan {expected_path}; alleen {len(texts)} description-teksten verschillen "
        "(bekend upstream-nondeterminisme: volgorde van de XML-docbestanden uit Directory.EnumerateFiles). "
        "Geen API-wijziging.",
    ]
    lines += [f"  - {item}" for item in texts[:5]]
    if len(texts) > 5:
        lines.append(f"  … en nog {len(texts) - 5}")
    return 0, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAPI-driftcontrole (structureel; beschrijvingen alleen gemeld).")
    parser.add_argument("--verwacht", dest="expected", type=Path, required=True, help="vastgelegde OpenAPI (docs/openapi)")
    parser.add_argument("--gegenereerd", dest="generated", type=Path, required=True, help="door de tests gegenereerde openapi.json")
    parser.add_argument("--github", action="store_true", help="meldingen ook als GitHub-annotatie (::error/::warning)")
    args = parser.parse_args(argv)
    code, lines = compare(args.expected, args.generated)
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    if args.github and lines:
        level = "error" if code else ("warning" if lines[0].startswith("WAARSCHUWING") else "")
        if level:
            print(f"::{level}::{lines[0]}")
    return code


if __name__ == "__main__":
    sys.exit(main())
