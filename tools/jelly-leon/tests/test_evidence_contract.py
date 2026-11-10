"""§11 van het platformcontract 1.3 (C1.3-ALG-02, C1.3-JL-02): EVIDENCE.json gebruikt alleen de vaste statuslijsten per
blad en de vaste validatiewaarden (meerdere gescheiden door "; "), nooit `Gereed`/`Geslaagd`; toelichting hoort in
`opmerking`.

Nieuw in 1.3 en hier bewaakt:
- validatiewaarden `Intel-iGPU-getest (ontwikkelmachine)` en `Niet getest` (die laatste alleen bij `Niet gestart`);
- een lege `validatie` is nooit toegestaan;
- elke `NIET GEVALIDEERD (…)` die in `blokkade` staat, staat ook in `validatie`;
- contractpunten (`C1.3-<code>`, `C1.2-<code>`) en reviews (`REVIEW-jelly-leon-<onderwerp>`) mogen een eigen regel hebben,
  met de statussen van het blad Werkpakketten; een `C1.3-JL-nn` bestaat in de gekopieerde conformiteitslijst.

Testmatrix (`EX..`, `JLT-..`): `Sim-geslaagd`/`Sim-mislukt` is het simulatorresultaat van de hele rij. Is maar een deel
van de rij uitgevoerd, dan houdt deze repo `Sim-getest` aan (nooit een geslaagd voor wat niet gedraaid heeft; QA-review
2026-11-10) — alleen bij status `Bezig` en met een `opmerking` die zegt wat niet is uitgevoerd (ADR-0028, gemeld als
contractpunt: §11 heeft geen waarde voor een deels uitgevoerde testrij).
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
EVIDENCE = REPO / "docs" / "platform-v2" / "EVIDENCE.json"
EXCEL_TAKEN = REPO / "docs" / "platform-v2" / "EXCEL_TAKEN.json"
CONFORMITEIT = REPO / "docs" / "platform-v2" / "CONTRACT_1.3_CONFORMITEIT.md"

STATUS_WORK = {"Niet gestart", "Bezig", "Geblokkeerd", "N.v.t."}  # 'Gereed' nooit in deze bouwomgeving
STATUS_TEST = {"Niet gestart", "Bezig", "Mislukt", "Geblokkeerd", "N.v.t."}  # 'Geslaagd' nooit
STATUS_DECISION = {"Open", "Ingevuld", "Getest", "Geblokkeerd", "N.v.t."}
NOT_GENERAL = {
    "NIET GEVALIDEERD (echte NAS)",
    "NIET GEVALIDEERD (hardware)",
    "NIET GEVALIDEERD (account)",
    "NIET GEVALIDEERD (Mac/Xcode)",
}
VALIDATION = {
    "Sim-getest",
    "Unit-getest",
    "Intel-iGPU-getest (ontwikkelmachine)",
    "Niet getest",
    *NOT_GENERAL,
}
VALIDATION_TEST = {"Sim-geslaagd", "Sim-mislukt"}
FIELDS = {"id", "status", "validatie", "bewijs", "blokkade", "opmerking", "repo", "bijgewerkt"}
# JLT-NN = testrijen van de B03-testmatrix (B03 2.0 §10.17: bewijs voor een JLT-rij mag met het eigen ID).
EXCEL_ID = r"B\d{2}-\d{3}|I\d{2}-\d{2}-\d{2}|A\d{2}-\d{2}-\d{2}|APP-\d{2}|EX\d{2}|JLT-\d{2}|D\d{2}"
#: Contractpunten en reviews (contract 1.3 §11).
CONTRACT_ID = r"C1\.3-(?:ALG|JL)-\d{2}|C1\.2-[A-Z0-9]+"
REVIEW_ID = r"REVIEW-jelly-leon-[a-z0-9][a-z0-9.-]*"
ID_RE = re.compile(rf"{EXCEL_ID}|{CONTRACT_ID}|{REVIEW_ID}")
NIET_GEVALIDEERD = re.compile(r"NIET GEVALIDEERD \([^)]*\)")


def classify(ident: str) -> tuple[set[str], set[str]]:
    if re.fullmatch(r"EX\d{2}|JLT-\d{2}", ident):
        return STATUS_TEST, VALIDATION | VALIDATION_TEST
    if re.fullmatch(r"D\d{2}", ident):
        return STATUS_DECISION, VALIDATION
    return STATUS_WORK, VALIDATION


def problems(item: dict) -> list[str]:
    found: list[str] = []
    ident = str(item.get("id", "?"))
    if set(item) != FIELDS:
        found.append(f"{ident}: velden {sorted(set(item) ^ FIELDS)} wijken af van §11")
    if not ID_RE.fullmatch(ident):
        found.append(f"{ident}: geen Excel-ID, contractpunt of review-ID")
    statuses, values = classify(ident)
    status = item.get("status")
    if status not in statuses:
        found.append(f"{ident}: status {status!r} niet toegestaan (nooit Gereed/Geslaagd)")
    validation = str(item.get("validatie") or "")
    parts = validation.split("; ") if validation.strip() else []
    if not parts:
        found.append(f"{ident}: lege validatie is nooit toegestaan (§11, 1.3)")
    bad = [part for part in parts if part not in values]
    if bad:
        found.append(f"{ident}: validatie bevat {bad} (alleen vaste waarden; toelichting in 'opmerking')")
    if len(parts) != len(set(parts)):
        found.append(f"{ident}: validatie bevat een waarde dubbel")
    if "Niet getest" in parts and status != "Niet gestart":
        found.append(f"{ident}: 'Niet getest' alleen bij status 'Niet gestart' (§11, 1.3)")
    if "Niet getest" in parts and any(p in parts for p in ("Sim-getest", "Unit-getest", *VALIDATION_TEST)):
        found.append(f"{ident}: 'Niet getest' naast een testresultaat is tegenstrijdig")
    if {"Sim-geslaagd", "Sim-mislukt"} <= set(parts):
        found.append(f"{ident}: Sim-geslaagd én Sim-mislukt tegelijk")
    if re.fullmatch(r"EX\d{2}|JLT-\d{2}", ident) and "Sim-getest" in parts:
        if status != "Bezig" or not str(item.get("opmerking") or "").strip():
            found.append(
                f"{ident}: Sim-getest op een testrij alleen bij status Bezig met een opmerking over wat niet is "
                "uitgevoerd (anders Sim-geslaagd/Sim-mislukt, §11)"
            )
    for missing in NIET_GEVALIDEERD.findall(str(item.get("blokkade") or "")):
        if missing not in NOT_GENERAL:
            found.append(f"{ident}: {missing!r} in blokkade is geen waarde uit de vaste lijst")
        elif missing not in parts:
            found.append(f"{ident}: {missing!r} staat in blokkade maar niet in validatie (§11, 1.3)")
    if item.get("repo") != "jelly-leon":
        found.append(f"{ident}: repo {item.get('repo')!r}")
    try:
        date.fromisoformat(str(item.get("bijgewerkt")))
    except ValueError:
        found.append(f"{ident}: bijgewerkt {item.get('bijgewerkt')!r} is geen datum JJJJ-MM-DD")
    return found


def _items() -> list[dict]:
    items = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert isinstance(items, list) and items
    return items


def test_evidence_follows_section_11():
    items = _items()
    errors = [p for item in items for p in problems(item)]
    assert errors == []
    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids)), "elke ID hoort één keer in EVIDENCE.json"


def test_b_and_jlt_ids_in_evidence_are_excel_rows_of_this_repo():
    tasks = {task["ID"] for task in json.loads(EXCEL_TAKEN.read_text(encoding="utf-8"))}
    unknown = [item["id"] for item in _items() if item["id"].startswith(("B", "JLT-")) and item["id"] not in tasks]
    assert unknown == []


def test_contract_points_exist_in_the_copied_conformity_list():
    text = CONFORMITEIT.read_text(encoding="utf-8")
    unknown = [
        item["id"] for item in _items() if item["id"].startswith("C1.3-") and f"| {item['id']} |" not in text
    ]
    assert unknown == []


def test_every_nu_point_of_this_repo_has_an_evidence_row():
    """De NU-punten van §9 (jelly-leon) en de algemene NU-punten die hier gelden, staan in EVIDENCE.json."""
    ids = {item["id"] for item in _items()}
    assert {"C1.3-JL-01", "C1.3-JL-02", "C1.3-JL-03", "C1.3-JL-04"} <= ids
    assert {"C1.3-ALG-01", "C1.3-ALG-02", "C1.3-ALG-04"} <= ids


def test_niet_gevalideerd_entries_explain_the_blockade():
    for item in _items():
        if "NIET GEVALIDEERD" in item["validatie"] or item["status"] == "Geblokkeerd":
            assert item["blokkade"].strip(), f"{item['id']}: zonder blokkade-uitleg"


def test_igpu_value_is_in_validation_not_only_in_the_remark():
    """C1.3-JL-02: 'Intel-iGPU-getest (ontwikkelmachine)' is sinds 1.3 een validatiewaarde (ADR-0026)."""
    for item in _items():
        if "Intel-iGPU-getest (ontwikkelmachine)" in item["opmerking"]:
            assert "Intel-iGPU-getest (ontwikkelmachine)" in item["validatie"].split("; "), item["id"]


BASE = {
    "id": "B03-001", "status": "Bezig", "validatie": "Sim-getest; NIET GEVALIDEERD (hardware)", "bewijs": "x",
    "blokkade": "x", "opmerking": "", "repo": "jelly-leon", "bijgewerkt": "2026-11-10",
}


@pytest.mark.parametrize(
    ("item", "fragment"),
    [
        ({"status": "Gereed"}, "status 'Gereed'"),
        ({"id": "EX48", "status": "Geslaagd"}, "status 'Geslaagd'"),
        ({"id": "JLT-70", "status": "Geslaagd", "validatie": "Sim-geslaagd"}, "status 'Geslaagd'"),
        ({"id": "JLT-7", "validatie": "Sim-geslaagd"}, "geen Excel-ID"),
        ({"validatie": "Sim-getest (lokaal 18/18)"}, "validatie bevat"),
        ({"validatie": "Sim-getest;NIET GEVALIDEERD (echte NAS)"}, "validatie bevat"),
        ({"validatie": "Sim-geslaagd"}, "validatie bevat"),  # alleen voor testrijen
        ({"validatie": ""}, "lege validatie"),
        ({"validatie": "  "}, "lege validatie"),
        ({"validatie": "Sim-getest; Sim-getest"}, "dubbel"),
        ({"validatie": "Niet getest"}, "alleen bij status 'Niet gestart'"),
        ({"status": "Niet gestart", "validatie": "Niet getest; Sim-getest"}, "tegenstrijdig"),
        ({"id": "JLT-70", "validatie": "Sim-geslaagd; Sim-mislukt"}, "tegelijk"),
        ({"id": "JLT-70", "validatie": "Sim-getest", "opmerking": ""}, "Sim-getest op een testrij"),
        ({"id": "JLT-70", "status": "Geblokkeerd", "validatie": "Sim-getest", "opmerking": "x"}, "Sim-getest op een testrij"),
        ({"blokkade": "Echte tv's: NIET GEVALIDEERD (hardware); NAS: NIET GEVALIDEERD (echte NAS)"}, "niet in validatie"),
        ({"blokkade": "NIET GEVALIDEERD (iPhone)"}, "geen waarde uit de vaste lijst"),
        ({"repo": "jelly-leon-web"}, "repo"),
        ({"bijgewerkt": "9 november"}, "geen datum"),
        ({"id": "B3-1"}, "geen Excel-ID"),
        ({"id": "C1.3-JLW-01"}, "geen Excel-ID"),  # punt van een andere repo hoort daar
        ({"id": "REVIEW-andere-repo-x"}, "geen Excel-ID"),
        ({"id": "C1.3-JL-01", "status": "Mislukt"}, "status 'Mislukt'"),  # contractpunt: statussen Werkpakketten
    ],
)
def test_rule_violations_are_detected(item, fragment):
    assert problems(BASE) == []
    found = problems({**BASE, **item})
    assert any(fragment in p for p in found), found


@pytest.mark.parametrize(
    "item",
    [
        {"validatie": "Sim-getest; Intel-iGPU-getest (ontwikkelmachine); NIET GEVALIDEERD (hardware)"},
        {"status": "Niet gestart", "validatie": "Niet getest", "blokkade": ""},
        {"status": "Niet gestart", "validatie": "Niet getest; NIET GEVALIDEERD (echte NAS)"},
        {"id": "JLT-71", "validatie": "Sim-geslaagd; NIET GEVALIDEERD (echte NAS)", "blokkade": "NIET GEVALIDEERD (echte NAS)"},
        {"id": "JLT-63", "validatie": "Sim-getest", "opmerking": "Alleen het rooktestdeel is uitgevoerd."},
        {"id": "C1.3-JL-03", "validatie": "Unit-getest; Sim-getest"},
        {"id": "C1.3-ALG-02", "validatie": "Unit-getest"},
        {"id": "C1.2-JL4", "validatie": "Niet getest", "status": "Niet gestart"},
        {"id": "REVIEW-jelly-leon-contract-1.3", "validatie": "Unit-getest"},
    ],
)
def test_allowed_forms_pass(item):
    assert problems({**BASE, **item}) == []
