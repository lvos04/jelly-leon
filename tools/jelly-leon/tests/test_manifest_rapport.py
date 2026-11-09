"""Beoordeling van het rapport van de manifestvalidator van appstore-en-fork (CI-job manifest)."""

from __future__ import annotations

import json

import pytest

import manifest_rapport


def report(*findings: tuple[str, str], valid: bool = True, app_id: str = "jelly-leon") -> dict:
    return {
        "valid": valid, "app_id": app_id, "version": "10.11.11-jl.0", "validator_version": "0.1.0",
        "schema_sha256": "sha256:" + "a" * 64, "errors": sum(s == "error" for _, s in findings),
        "warnings": sum(s == "warning" for _, s in findings),
        "findings": [{"code": c, "severity": s, "path": "x", "message": "m"} for c, s in findings],
    }


def test_only_pending_digest_warning_passes():
    assert manifest_rapport.beoordeel(report(("digest_pending_release", "warning")), {"digest_pending_release"}) == []


@pytest.mark.parametrize(
    "findings",
    [
        (("deprecated_field", "warning"),),  # vervallen veld uit 1.1 telt als fout (zoals --strict)
        (("gpu_decision_missing", "error"),),
        (("digest_pending_release", "error"),),  # dezelfde code als fout mag nooit
    ],
)
def test_other_findings_fail(findings):
    assert manifest_rapport.beoordeel(report(*findings), {"digest_pending_release"})


def test_invalid_or_foreign_manifest_fails():
    assert manifest_rapport.beoordeel(report(valid=False), set())
    assert manifest_rapport.beoordeel(report(app_id="jellyfin"), set())
    assert manifest_rapport.beoordeel({"valid": True}, set()) == ["rapport bevat geen lijst 'findings'"]


def test_main_exit_codes(tmp_path):
    good = tmp_path / "goed.json"
    good.write_text(json.dumps(report(("digest_pending_release", "warning"))), encoding="utf-8")
    assert manifest_rapport.main(["--rapport", str(good)]) == 0
    # zonder toegestane waarschuwingen (zoals straks de release-CI) faalt hetzelfde rapport
    assert manifest_rapport.main(["--rapport", str(good), "--toegestaan", ""]) == 1
    bad = tmp_path / "fout.json"
    bad.write_text(json.dumps(report(("deprecated_field", "warning"))), encoding="utf-8")
    assert manifest_rapport.main(["--rapport", str(bad), "--github"]) == 1
    broken = tmp_path / "kapot.json"
    broken.write_text("geen json", encoding="utf-8")
    assert manifest_rapport.main(["--rapport", str(broken)]) == 3
    assert manifest_rapport.main(["--rapport", str(tmp_path / "bestaat-niet.json")]) == 3
