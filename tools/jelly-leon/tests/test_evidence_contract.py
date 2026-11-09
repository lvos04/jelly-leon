"""§11 van het platformcontract (conformiteitspunt A4): EVIDENCE.json gebruikt alleen de vaste statuslijsten en de
vaste validatiewaarden (meerdere gescheiden door "; "), nooit `Gereed`/`Geslaagd`; toelichting hoort in `opmerking`."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
EVIDENCE = REPO / "docs" / "platform-v2" / "EVIDENCE.json"
EXCEL_TAKEN = REPO / "docs" / "platform-v2" / "EXCEL_TAKEN.json"

STATUS_WORK = {"Niet gestart", "Bezig", "Geblokkeerd", "N.v.t."}  # 'Gereed' nooit in deze bouwomgeving
STATUS_TEST = {"Niet gestart", "Bezig", "Mislukt", "Geblokkeerd", "N.v.t."}  # 'Geslaagd' nooit
STATUS_DECISION = {"Open", "Ingevuld", "Getest", "Geblokkeerd", "N.v.t."}
VALIDATION = {
    "Sim-getest",
    "Unit-getest",
    "NIET GEVALIDEERD (echte NAS)",
    "NIET GEVALIDEERD (hardware)",
    "NIET GEVALIDEERD (account)",
    "NIET GEVALIDEERD (Mac/Xcode)",
}
VALIDATION_TEST = {"Sim-geslaagd", "Sim-mislukt"}
FIELDS = {"id", "status", "validatie", "bewijs", "blokkade", "opmerking", "repo", "bijgewerkt"}
# JLT-NN = testrijen van de B03-testmatrix (B03 2.0 §10.17: bewijs voor een JLT-rij mag met het eigen ID).
ID_RE = re.compile(r"B\d{2}-\d{3}|I\d{2}-\d{2}-\d{2}|A\d{2}-\d{2}-\d{2}|APP-\d{2}|EX\d{2}|JLT-\d{2}|D\d{2}")


def classify(ident: str) -> tuple[set[str], set[str]]:
    if re.fullmatch(r"EX\d{2}|JLT-\d{2}", ident):
        return STATUS_TEST, VALIDATION | VALIDATION_TEST
    if re.fullmatch(r"D\d{2}", ident):
        return STATUS_DECISION, VALIDATION
    return STATUS_WORK, VALIDATION


def problems(item: dict) -> list[str]:
    found: list[str] = []
    ident = item.get("id", "?")
    if set(item) != FIELDS:
        found.append(f"{ident}: velden {sorted(set(item) ^ FIELDS)} wijken af van §11")
    if not ID_RE.fullmatch(str(ident)):
        found.append(f"{ident}: geen Excel-ID")
    statuses, values = classify(str(ident))
    if item.get("status") not in statuses:
        found.append(f"{ident}: status {item.get('status')!r} niet toegestaan (nooit Gereed/Geslaagd)")
    if item.get("validatie"):
        bad = [part for part in str(item["validatie"]).split("; ") if part not in values]
        if bad:
            found.append(f"{ident}: validatie bevat {bad} (alleen vaste waarden; toelichting in 'opmerking')")
    if item.get("repo") != "jelly-leon":
        found.append(f"{ident}: repo {item.get('repo')!r}")
    try:
        date.fromisoformat(str(item.get("bijgewerkt")))
    except ValueError:
        found.append(f"{ident}: bijgewerkt {item.get('bijgewerkt')!r} is geen datum JJJJ-MM-DD")
    return found


def test_evidence_follows_section_11():
    items = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert isinstance(items, list) and items
    errors = [p for item in items for p in problems(item)]
    assert errors == []
    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids)), "elke ID hoort één keer in EVIDENCE.json"


def test_b_and_jlt_ids_in_evidence_are_excel_rows_of_this_repo():
    tasks = {task["ID"] for task in json.loads(EXCEL_TAKEN.read_text(encoding="utf-8"))}
    items = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    unknown = [item["id"] for item in items if item["id"].startswith(("B", "JLT-")) and item["id"] not in tasks]
    assert unknown == []


def test_niet_gevalideerd_entries_explain_the_blockade():
    for item in json.loads(EVIDENCE.read_text(encoding="utf-8")):
        if "NIET GEVALIDEERD" in item["validatie"] or item["status"] == "Geblokkeerd":
            assert item["blokkade"].strip(), f"{item['id']}: zonder blokkade-uitleg"


@pytest.mark.parametrize(
    ("item", "fragment"),
    [
        ({"status": "Gereed"}, "status 'Gereed'"),
        ({"id": "EX48", "status": "Geslaagd"}, "status 'Geslaagd'"),
        ({"id": "JLT-70", "status": "Geslaagd", "validatie": "Sim-geslaagd"}, "status 'Geslaagd'"),
        ({"id": "JLT-7", "validatie": "Sim-geslaagd"}, "geen Excel-ID"),
        ({"validatie": "Sim-getest (lokaal 18/18)"}, "validatie bevat"),
        ({"validatie": "Sim-getest;NIET GEVALIDEERD (echte NAS)"}, "validatie bevat"),
        ({"repo": "jelly-leon-web"}, "repo"),
        ({"bijgewerkt": "9 november"}, "geen datum"),
        ({"id": "B3-1"}, "geen Excel-ID"),
    ],
)
def test_rule_violations_are_detected(item, fragment):
    base = {
        "id": "B03-001", "status": "Bezig", "validatie": "Sim-getest; NIET GEVALIDEERD (hardware)", "bewijs": "x",
        "blokkade": "x", "opmerking": "", "repo": "jelly-leon", "bijgewerkt": "2026-11-09",
    }
    assert problems(base) == []
    found = problems({**base, **item})
    assert any(fragment in p for p in found), found
