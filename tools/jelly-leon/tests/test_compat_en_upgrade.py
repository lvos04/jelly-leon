"""Hulpfuncties van de P4-0-proeven: compat_api.py (JLT-64) en upgrade_proef.py (JLT-60/61), zonder Docker."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "e2e"))

import compat_api  # noqa: E402
import upgrade_proef  # noqa: E402


def test_normalize_removes_volatile_fields_and_masks_tokens_in_transcoding_url() -> None:
    raw = {"PlaySessionId": "abc", "ServerName": "x", "MediaSources": [{
        "TranscodingUrl": "/videos/1/master.m3u8?DeviceId=d1&ApiKey=0123456789abcdef&PlaySessionId=p1&Tag=t",
        "Id": "1"}]}
    norm = compat_api.normalize(raw)
    assert "PlaySessionId" not in norm and "ServerName" not in norm
    url = norm["MediaSources"][0]["TranscodingUrl"]
    assert "0123456789abcdef" not in url and "ApiKey=<x>" in url and "Tag=t" in url


def test_openapi_only_additive_under_media_and_connector() -> None:
    stock = {"paths": {"/Items": {"get": {"description": "a"}}}, "components": {"schemas": {"Dto": {"type": "object"}}}}
    fork = {"paths": {"/Items": {"get": {"description": "andere tekst"}}, "/media/v1/version": {"get": {}}},
            "components": {"schemas": {"Dto": {"type": "object"}, "ForkVersionInfo": {"type": "object"}}}}
    problems, added = compat_api.compare_openapi(stock, fork)
    assert problems == [] and added == ["/media/v1/version", "schema ForkVersionInfo"]
    fork["paths"]["/Extra"] = {"get": {}}
    del fork["paths"]["/Items"]
    problems, _ = compat_api.compare_openapi(stock, fork)
    assert any("buiten" in p and "/Extra" in p for p in problems)
    assert any("ontbreekt in Jelly Leon: /Items" in p for p in problems)


def test_upgrade_differences_and_dates() -> None:
    assert upgrade_proef.iso_seconds("2026-11-01T20:15:00.0000000Z") == "2026-11-01T20:15:00Z"
    assert upgrade_proef.iso_seconds("2026-11-01T20:15:00.123Z") == "2026-11-01T20:15:00Z"
    before = {"gast": {"hervat": 15000000, "fav": True}, "kind": {}}
    after = {"gast": {"hervat": 0, "fav": True}, "nieuw": {}}
    diff = upgrade_proef.differences(before, after)
    assert "gast/hervat: 15000000 → 0" in diff
    assert any(d.startswith("kind: VERDWENEN") for d in diff) and any(d.startswith("nieuw: nieuw na de upgrade") for d in diff)
    assert upgrade_proef.differences(before, before) == []


def test_report_redacts_secrets() -> None:
    report = upgrade_proef.Report()
    report.secrets.append("geheim-wachtwoord")
    report.add("stap", True, "aanmelden met geheim-wachtwoord gelukt")
    assert "geheim-wachtwoord" not in report.steps[0]["detail"] and "<geheim>" in report.steps[0]["detail"]
