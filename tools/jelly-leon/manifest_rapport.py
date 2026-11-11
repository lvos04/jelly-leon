#!/usr/bin/env python3
"""Beoordeelt het JSON-rapport van de manifestvalidator van `appstore-en-fork` (eigenaar manifeststandaard §9, B08-001).

De validator zelf wordt niet gekopieerd (geen tweede waarheid): CI haalt hem uit de publieke repo op een vastgezette
commit en draait `python -m appstore.manifest.cli validate --strict <manifest> --format json`. Dit hulpmiddel leest
dat rapport (contract 1.3 §9, C1.3-JL-04):

  geslaagd = `app_id` is jelly-leon, het rapport komt van een validator die contract 1.3 kent (`strict_valid`
             aanwezig) en is met `--strict` gemaakt, `valid` en `strict_valid` zijn true, er zijn 0 fouten, en elke
             waarschuwing is door de validator als geaccepteerd gemarkeerd met de reden uit `accepted_findings` van
             het manifest zelf.

Er is geen losse uitzonderingenlijst meer buiten het manifest (vervallen in contract 1.3 §9): wat mag, staat met reden
in het manifest en de validator van de eigenaar bepaalt of dat klopt. Als extra controle weigert dit hulpmiddel een
geaccepteerde code buiten de vaste lijst van het contract; een vervallen veld (`deprecated_field`) of een
geaccepteerde code die niet meer optreedt (`accepted_finding_unused`) telt dus altijd als fout.

Alleen standaardbibliotheek. Exitcodes: 0 = geslaagd, 1 = niet geslaagd, 3 = rapport onleesbaar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP_ID = "jelly-leon"
# Vaste lijst van contract 1.3 §9 (`accepted_findings`); geen eigen uitzonderingen van deze repo.
CONTRACT_ACCEPTEERBAAR = frozenset({"backup_db_export_none", "secret_in_form", "digest_pending_release"})


def geaccepteerd(report: dict) -> list[str]:
    """Codes van de waarschuwingen die de validator als geaccepteerd heeft gemarkeerd (voor de samenvatting)."""
    return sorted(
        {
            str(f.get("code"))
            for f in report.get("findings") or []
            if isinstance(f, dict) and f.get("severity") == "warning" and f.get("accepted") is True
        }
    )


def beoordeel(report: dict, app_id: str = APP_ID) -> list[str]:
    problemen: list[str] = []
    findings = report.get("findings")
    if not isinstance(findings, list):
        return ["rapport bevat geen lijst 'findings'"]
    if report.get("app_id") != app_id:
        problemen.append(f"app_id {report.get('app_id')!r} ≠ {app_id!r}")
    if report.get("valid") is not True:
        problemen.append("validator meldt het manifest als ongeldig")
    if "strict_valid" not in report:
        problemen.append(
            "rapport heeft geen 'strict_valid': de validator kent contract 1.3 §9 niet (vastgezette commit te oud?)"
        )
    elif report.get("strict_valid") is not True:
        problemen.append("validator meldt het manifest als ongeldig in --strict (contract 1.3 §9)")
    if report.get("strict") is not True:
        problemen.append("rapport is niet met --strict gemaakt (contract 1.3 §9: CI valideert altijd strikt)")
    for finding in findings:
        if not isinstance(finding, dict):
            problemen.append(f"bevinding is geen object: {finding!r}")
            continue
        code, severity = finding.get("code", "?"), finding.get("severity", "?")
        where = f"{finding.get('path', '?')}: {code} — {finding.get('message', '')}"
        if severity == "warning" and finding.get("accepted") is True:
            if code not in CONTRACT_ACCEPTEERBAAR:
                problemen.append(f"waarschuwing geaccepteerd buiten de vaste lijst van contract 1.3 §9: {where}")
            elif not str(finding.get("accepted_reden_nl") or "").strip():
                problemen.append(f"waarschuwing geaccepteerd zonder reden (accepted_findings.reden_nl): {where}")
            continue
        problemen.append(
            f"{'fout' if severity == 'error' else 'waarschuwing (niet met reden in accepted_findings)'} {where}"
        )
    return problemen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Beoordeel het rapport van de manifestvalidator (contract 1.3 §9).")
    parser.add_argument(
        "--rapport", type=Path, required=True, help="JSON-uitvoer van 'appstore.manifest.cli validate --strict'"
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
    problemen = beoordeel(report)
    for finding in report.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        soort = "geaccepteerd" if finding.get("accepted") is True else str(finding.get("severity", "?"))
        print(f"  {soort:12} {finding.get('path', '?'):32} {finding.get('code', '?')}")
    if problemen:
        print(f"MANIFEST NIET CONFORM ({len(problemen)} problemen):", file=sys.stderr)
        for line in problemen:
            print(f"::error::{line}" if args.github else f"  - {line}", file=sys.stderr)
        return 1
    print(
        f"Manifest {report.get('app_id')} {report.get('version')} conform manifeststandaard §9 in --strict volgens "
        f"validator {report.get('validator_version')} (schema {str(report.get('schema_sha256'))[:19]}…); "
        f"met reden geaccepteerd in het manifest: {', '.join(geaccepteerd(report)) or 'niets'}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
