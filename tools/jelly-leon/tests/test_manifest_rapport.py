"""Beoordeling van het rapport van de manifestvalidator van appstore-en-fork (CI-job manifest, contract 1.3 §9)."""

from __future__ import annotations

import json

import pytest

import manifest_rapport

REDEN = "Eigen image vóór de eerste release."


def finding(code: str, severity: str = "warning", *, accepted: bool = False, reden: str | None = REDEN) -> dict:
    out = {"code": code, "severity": severity, "path": "x", "message": "m", "accepted": accepted}
    if accepted and reden is not None:
        out["accepted_reden_nl"] = reden
    return out


def report(*findings: dict, valid: bool = True, app_id: str = "jelly-leon", strict: bool = True) -> dict:
    errors = sum(f["severity"] == "error" for f in findings)
    open_warnings = sum(f["severity"] == "warning" and not f["accepted"] for f in findings)
    return {
        "valid": valid, "app_id": app_id, "version": "12.4.0-jl.0", "validator_version": "0.1.0",
        "schema_sha256": "sha256:" + "a" * 64, "errors": errors,
        "warnings": sum(f["severity"] == "warning" for f in findings),
        "accepted": sum(f["accepted"] for f in findings),
        "strict_valid": valid and errors == 0 and open_warnings == 0,
        "findings": list(findings), "strict": strict,
    }


def test_accepted_pending_digest_passes():
    rapport = report(finding("digest_pending_release", accepted=True))
    assert manifest_rapport.beoordeel(rapport) == []
    assert manifest_rapport.geaccepteerd(rapport) == ["digest_pending_release"]


def test_manifest_without_findings_passes():
    assert manifest_rapport.beoordeel(report()) == []


@pytest.mark.parametrize(
    ("findings", "fragment"),
    [
        # dezelfde waarschuwing zonder reden in het manifest: geen losse uitzonderingenlijst meer in de CI
        ((finding("digest_pending_release"),), "niet met reden in accepted_findings"),
        ((finding("deprecated_field"),), "niet met reden in accepted_findings"),
        ((finding("accepted_finding_unused"),), "niet met reden in accepted_findings"),
        ((finding("healthcheck_monitor_missing"),), "niet met reden in accepted_findings"),
        ((finding("gpu_decision_missing", "error"),), "fout x: gpu_decision_missing"),
        ((finding("reserved_env", "error"),), "fout x: reserved_env"),
        ((finding("digest_pending_release", "error", accepted=True),), "fout x: digest_pending_release"),
        # geaccepteerd buiten de vaste lijst van het contract of zonder reden: ook dan niet conform
        ((finding("deprecated_field", accepted=True),), "buiten de vaste lijst"),
        ((finding("digest_pending_release", accepted=True, reden="  "),), "zonder reden"),
        ((finding("digest_pending_release", accepted=True, reden=None),), "zonder reden"),
    ],
)
def test_other_findings_fail(findings, fragment):
    problemen = manifest_rapport.beoordeel(report(*findings))
    assert any(fragment in p for p in problemen), problemen


def test_invalid_or_foreign_manifest_fails():
    assert manifest_rapport.beoordeel(report(valid=False))
    assert manifest_rapport.beoordeel(report(app_id="jellyfin"))
    assert manifest_rapport.beoordeel({"valid": True}) == ["rapport bevat geen lijst 'findings'"]
    assert any("geen object" in p for p in manifest_rapport.beoordeel(report() | {"findings": ["tekst"]}))


def test_report_must_be_strict_and_from_a_1_3_validator():
    niet_strikt = report(finding("digest_pending_release", accepted=True), strict=False)
    assert any("niet met --strict" in p for p in manifest_rapport.beoordeel(niet_strikt))
    # rapport van een validator van vóór contract 1.3 (geen strict_valid, geen accepted): vastgezette commit te oud
    oud = {
        "valid": True, "app_id": "jelly-leon", "version": "12.4.0-jl.0", "strict": True,
        "findings": [{"code": "digest_pending_release", "severity": "warning", "path": "image.digest", "message": "m"}],
    }
    problemen = manifest_rapport.beoordeel(oud)
    assert any("kent contract 1.3 §9 niet" in p for p in problemen), problemen
    assert any("niet met reden in accepted_findings" in p for p in problemen), problemen
    strikt_ongeldig = report() | {"strict_valid": False}
    assert any("ongeldig in --strict" in p for p in manifest_rapport.beoordeel(strikt_ongeldig))


def test_main_exit_codes(tmp_path, capsys):
    good = tmp_path / "goed.json"
    good.write_text(json.dumps(report(finding("digest_pending_release", accepted=True))), encoding="utf-8")
    assert manifest_rapport.main(["--rapport", str(good)]) == 0
    assert "met reden geaccepteerd in het manifest: digest_pending_release" in capsys.readouterr().out
    # een losse uitzonderingenlijst buiten het manifest bestaat niet meer (contract 1.3 §9)
    with pytest.raises(SystemExit):
        manifest_rapport.main(["--rapport", str(good), "--toegestaan", "digest_pending_release"])
    capsys.readouterr()
    bad = tmp_path / "fout.json"
    bad.write_text(json.dumps(report(finding("digest_pending_release"))), encoding="utf-8")
    assert manifest_rapport.main(["--rapport", str(bad), "--github"]) == 1
    assert "::error::" in capsys.readouterr().err
    broken = tmp_path / "kapot.json"
    broken.write_text("geen json", encoding="utf-8")
    assert manifest_rapport.main(["--rapport", str(broken)]) == 3
    assert manifest_rapport.main(["--rapport", str(tmp_path / "bestaat-niet.json")]) == 3
    lijst = tmp_path / "lijst.json"
    lijst.write_text("[]", encoding="utf-8")
    assert manifest_rapport.main(["--rapport", str(lijst)]) == 3
