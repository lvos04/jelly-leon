#!/usr/bin/env python3
"""Beoordeelt het JSON-rapport van de manifestvalidator van `appstore-en-fork` (eigenaar manifeststandaard §9, B08-001).

De validator zelf wordt niet gekopieerd (geen tweede waarheid): CI haalt hem uit de publieke repo op een vastgezette
commit en draait `python -m appstore.manifest.cli validate <manifest> --format json`. Dit hulpmiddel leest dat rapport:

  geslaagd = `valid` is true, 0 fouten, `app_id` is jelly-leon, en elke waarschuwing staat in `--toegestaan`
             (standaard alleen `digest_pending_release`: zolang er geen release is heeft de eigen image nog geen
             digest; de release-CI vult die). Vervallen velden (`deprecated_field`) tellen dus altijd als fout,
             zoals in `--strict` van de release-CI.

Alleen standaardbibliotheek. Exitcodes: 0 = geslaagd, 1 = niet geslaagd, 3 = rapport onleesbaar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP_ID = "jelly-leon"
STANDAARD_TOEGESTAAN = ("digest_pending_release",)


def beoordeel(report: dict, toegestaan: set[str], app_id: str = APP_ID) -> list[str]:
    problemen: list[str] = []
    findings = report.get("findings")
    if not isinstance(findings, list):
        return ["rapport bevat geen lijst 'findings'"]
    if report.get("app_id") != app_id:
        problemen.append(f"app_id {report.get('app_id')!r} ≠ {app_id!r}")
    if report.get("valid") is not True:
        problemen.append("validator meldt het manifest als ongeldig")
    for finding in findings:
        code, severity = finding.get("code", "?"), finding.get("severity", "?")
        where = f"{finding.get('path', '?')}: {code} — {finding.get('message', '')}"
        if severity == "warning" and code in toegestaan:
            continue
        problemen.append(f"{'fout' if severity == 'error' else 'waarschuwing (niet toegestaan)'} {where}")
    return problemen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Beoordeel het rapport van de manifestvalidator (contract 1.2 §9).")
    parser.add_argument("--rapport", type=Path, required=True, help="JSON-uitvoer van 'appstore.manifest.cli validate'")
    parser.add_argument(
        "--toegestaan", action="append", default=None,
        help="waarschuwingscode die mag (herhaalbaar); standaard alleen digest_pending_release",
    )
    parser.add_argument("--github", action="store_true", help="problemen als ::error:: voor GitHub Actions")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.rapport.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FOUT: rapport {args.rapport} onleesbaar: {exc}", file=sys.stderr)
        return 3
    if not isinstance(report, dict):
        print("FOUT: rapport is geen JSON-object", file=sys.stderr)
        return 3
    toegestaan = set(args.toegestaan if args.toegestaan is not None else STANDAARD_TOEGESTAAN)
    problemen = beoordeel(report, toegestaan)
    for finding in report.get("findings") or []:
        print(f"  {finding.get('severity', '?'):8} {finding.get('path', '?'):32} {finding.get('code', '?')}")
    if problemen:
        print(f"MANIFEST NIET CONFORM ({len(problemen)} problemen):", file=sys.stderr)
        for line in problemen:
            print(f"::error::{line}" if args.github else f"  - {line}", file=sys.stderr)
        return 1
    print(
        f"Manifest {report.get('app_id')} {report.get('version')} conform manifeststandaard §9 volgens validator "
        f"{report.get('validator_version')} (schema {str(report.get('schema_sha256'))[:19]}…); "
        f"toegestane waarschuwingen: {', '.join(sorted(toegestaan)) or 'geen'}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
