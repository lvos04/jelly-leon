"""Hulpfuncties van de P4-0-proeven: compat_api.py (JLT-64) en upgrade_proef.py (JLT-60/61), zonder Docker."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "e2e"))

import compat_api  # noqa: E402
import upgrade_proef  # noqa: E402
import upstream_gedrag_runtime  # noqa: E402


def test_normalize_removes_volatile_fields_and_masks_tokens_in_transcoding_url() -> None:
    raw = {"PlaySessionId": "abc", "ServerName": "x", "MediaSources": [{
        "TranscodingUrl": "/videos/1/master.m3u8?DeviceId=d1&ApiKey=0123456789abcdef&PlaySessionId=p1&Tag=t",
        "Id": "1"}]}
    norm = compat_api.normalize(raw)
    assert "PlaySessionId" not in norm and "ServerName" not in norm
    url = norm["MediaSources"][0]["TranscodingUrl"]
    assert "0123456789abcdef" not in url and "ApiKey=<x>" in url and "Tag=t" in url


def test_apikey_in_url_is_masked_in_nested_responses_and_error_messages() -> None:
    url = "/Videos/1/master.m3u8?aPIkEy=proefwaarde&API_KEY=andere-proefwaarde&Tag=t"
    expected = "/Videos/1/master.m3u8?aPIkEy=<x>&API_KEY=<x>&Tag=t"
    raw = {"MediaSources": [{"TranscodingUrl": url}]}
    assert compat_api.normalize(raw) == {"MediaSources": [{"TranscodingUrl": expected}]}
    error = f"PlaybackInfo gaf een fout: {raw!r}"
    assert upstream_gedrag_runtime.maskeer_url_geheimen(error) == error.replace(url, expected)


@pytest.mark.parametrize("prefix", ["/video?", "/video?link=/proxy?"])
def test_normalize_masks_percent_encoded_query_names(prefix: str) -> None:
    raw = {"TranscodingUrl": f"{prefix}%41piKey=proefwaarde&api%5Fkey=andere-proefwaarde&Tag=t"}
    expected = {"TranscodingUrl": f"{prefix}%41piKey=<x>&api%5Fkey=<x>&Tag=t"}
    assert compat_api.normalize(raw) == expected
    assert compat_api.normalize(expected) == expected


@pytest.fixture
def compat_proef(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    http = Mock()
    http.ruw.return_value = (204, b"", {})
    http.doe.side_effect = lambda _methode, pad, *args, **kwargs: {
        "/Items": {"Items": [{"Id": "film"}, {"Id": "muziek"}]}, "/ScheduledTasks": [],
    }.get(pad, {})
    monkeypatch.setattr(compat_api, "Http", Mock(return_value=http))
    monkeypatch.setattr(compat_api, "login", Mock(return_value=(http, "proefgebruiker")))
    monkeypatch.setattr(compat_api, "Kant", lambda label, *args: Mock(
        label=label, url="http://proefserver.test:19096", start=Mock(return_value="12.4"),
    ))
    monkeypatch.setattr(compat_api.subprocess, "run", Mock())
    monkeypatch.setattr(compat_api, "docker", Mock())
    return ["--image", "fork", "--stock-image", "stock", "--werkmap", str(tmp_path),
            "--report", str(tmp_path / "compat.json")]


def test_compat_redacts_terminal_and_json_on_api_difference(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], compat_proef: list[str],
) -> None:
    proefwaarde = "proefwaarde"

    def collect(kant: Mock, _password: str) -> dict:
        url = f"/video?%41piKey={proefwaarde}&Tag={kant.label}"
        return {"antwoorden": {"PlaybackInfo film": {"MediaSources": [{
            "SupportsDirectPlay": True, "SupportsTranscoding": True, "TranscodingUrl": url,
            "ExtraInfo": [url],
        }]}}, "openapi": {"paths": {}}}

    monkeypatch.setattr(compat_api, "collect", collect)
    assert compat_api.main(compat_proef) == 1
    terminal = capsys.readouterr()
    bestand = (tmp_path / "compat.json").read_text(encoding="utf-8")
    rapport = json.loads(bestand)
    assert "Tag=jelly-leon" in terminal.out and "Tag=jelly-leon" in rapport["verschillen"][0]
    assert "ExtraInfo" in rapport["verschillen"][0]
    if any(proefwaarde in tekst for tekst in (terminal.out, terminal.err, bestand)):
        pytest.fail("Synthetische sleutelwaarde zichtbaar in de uitvoer")


def test_compat_redacts_terminal_and_json_on_runtime_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], compat_proef: list[str],
) -> None:
    proefwaarde = "proefwaarde"
    fout = RuntimeError(f"PlaybackInfo gaf een fout: /video?ApiKey={proefwaarde}&Tag=t")
    monkeypatch.setattr(compat_api, "collect", Mock(side_effect=fout))

    assert compat_api.main(compat_proef) == 1
    terminal = capsys.readouterr()
    bestand = (tmp_path / "compat.json").read_text(encoding="utf-8")
    laatste_stap = json.loads(bestand)["stappen"][-1]
    detail = "RuntimeError: PlaybackInfo gaf een fout: /video?ApiKey=<x>&Tag=t"
    assert detail in terminal.out
    assert laatste_stap["detail"] == detail
    assert laatste_stap["geslaagd"] is False
    if any(proefwaarde in tekst for tekst in (terminal.out, terminal.err, bestand)):
        pytest.fail("Synthetische sleutelwaarde zichtbaar in de uitvoer")


@pytest.mark.parametrize(("negatief", "code"), [(False, 0), (True, 1)])
def test_compat_productnaam_bepaalt_de_exitcode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compat_proef: list[str], negatief: bool, code: int,
) -> None:
    antwoorden = {"/System/Info/Public": {"ProductName": "Proefserver"}, "PlaybackInfo film": {
        "MediaSources": [{"SupportsDirectPlay": True, "SupportsTranscoding": True, "TranscodingUrl": "/film"}],
    }}
    monkeypatch.setattr(compat_api, "collect", lambda *_: {"antwoorden": deepcopy(antwoorden), "openapi": {"paths": {}}})
    assert compat_api.main([*compat_proef, *(["--negatieve-proef"] if negatief else [])]) == code
    rapport = json.loads((tmp_path / "compat.json").read_text())
    assert rapport["negatieve_proef"] is negatief
    assert len(rapport["verschillen"]) == int(negatief)
    if negatief:
        assert "/System/Info/Public/ProductName" in rapport["verschillen"][0]


def test_zonder_plugin_vereist_eerst_de_gekopieerde_dll(tmp_path: Path) -> None:
    kant = Mock(config=tmp_path)
    with pytest.raises(ValueError, match="precies één"):
        compat_api.meet_zonder_plugin(kant, "test", {})
    kant.start.assert_not_called()


def test_modulestand_en_antwoorden_gebruiken_dezelfde_sessie(monkeypatch: pytest.MonkeyPatch) -> None:
    sessie = Mock(), "beheer"
    aanmelden = Mock(return_value=sessie)
    monkeypatch.setattr(compat_api, "login", aanmelden)
    api_stand = {"proef": False}
    monkeypatch.setattr(compat_api, "modulelijst", lambda _api: (api_stand.copy(), "stand"))

    def instellen(_api: Mock, gewenst: set[str]) -> list[str]:
        api_stand["proef"] = "proef" in gewenst
        return sorted(gewenst)

    monkeypatch.setattr(compat_api, "stel_modules_in", instellen)
    lezen = Mock(return_value={"antwoorden": {"route": []}})
    monkeypatch.setattr(compat_api, "collect", lezen)
    kant = Mock()
    metingen = compat_api.meet_modulestanden(kant, "proef", {"route": []})
    assert set(metingen) == {"alleen proef", "alle aan", "weer uit"}
    aanmelden.assert_called_once()
    assert all(aanroep.args == (kant, "proef", sessie) for aanroep in lezen.call_args_list)


@pytest.mark.parametrize("direct_play_zonder_spoor, verwacht", [(True, True), (False, False)])
def test_playbackinfo_requires_explicit_track_to_transcode_it(
    monkeypatch: pytest.MonkeyPatch, direct_play_zonder_spoor: bool, verwacht: bool,
) -> None:
    ctx = upstream_gedrag_runtime.Ctx("http://127.0.0.1", "niet-gebruikt")
    ctx.video_id, ctx.video_source_id, ctx.ac3_index = "film", "bron", 1
    bodies = []

    def playbackinfo(_ctx: upstream_gedrag_runtime.Ctx, selectie: dict) -> dict:
        bodies.append(selectie)
        return {"SupportsDirectPlay": False, "TranscodingUrl": "/voorbeeld"} if selectie else {
            "SupportsDirectPlay": direct_play_zonder_spoor,
        }

    monkeypatch.setattr(upstream_gedrag_runtime, "_playbackinfo", playbackinfo, raising=False)
    assert upstream_gedrag_runtime.playbackinfo_zonder_spoorselectie(ctx)[0] is verwacht
    assert bodies == [{}, {"MediaSourceId": "bron", "AudioStreamIndex": 1}]


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


def test_compat_fails_when_global_openapi_security_is_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compat_proef: list[str],
) -> None:
    stock = {"paths": {"/Items": {"get": {}}}, "security": [{"Auth": []}],
             "components": {"securitySchemes": {"Auth": {"type": "http", "scheme": "bearer"}}}}
    fork = {naam: waarde for naam, waarde in stock.items() if naam != "security"}
    antwoorden = {"PlaybackInfo film": {"MediaSources": [{"SupportsDirectPlay": True, "TranscodingUrl": "/video"}]}}
    monkeypatch.setattr(compat_api, "collect", lambda kant, _password: {
        "antwoorden": antwoorden, "openapi": stock if kant.label == "stock" else fork,
    })
    assert compat_api.main(compat_proef) == 1
    rapport = json.loads((tmp_path / "compat.json").read_text(encoding="utf-8"))
    assert not rapport["geslaagd"]
    assert any("globale security" in probleem for probleem in rapport["openapi_problemen"])


@pytest.mark.parametrize("fork_basispad, exitcode", [("/gewijzigd", 1), ("/mediahub", 0)])
def test_compat_checks_global_openapi_server_base_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compat_proef: list[str], fork_basispad: str, exitcode: int,
) -> None:
    test_urls = {"basis": "http://basis.test:19095", "stock": "http://stock.test:19096",
                 "jelly-leon": "http://fork.test:29096"}
    monkeypatch.setattr(compat_api, "Kant", lambda label, *args: Mock(
        label=label, url=test_urls[label], start=Mock(return_value="12.4"),
    ))
    antwoorden = {"PlaybackInfo film": {"MediaSources": [{"SupportsDirectPlay": True, "TranscodingUrl": "/video"}]}}

    def collect(kant: Mock, _password: str) -> dict:
        basispad = "/mediahub" if kant.label == "stock" else fork_basispad
        return {"antwoorden": antwoorden, "openapi": {
            "paths": {"/Items": {"get": {}}}, "servers": [{"url": f"{kant.url}{basispad}"}],
        }}

    monkeypatch.setattr(compat_api, "collect", collect)
    assert compat_api.main(compat_proef) == exitcode
    rapport = json.loads((tmp_path / "compat.json").read_text(encoding="utf-8"))
    assert rapport["geslaagd"] is (exitcode == 0)
    assert rapport["openapi_problemen"] == (
        ['globaal OpenAPI-serverbasispad gewijzigd: $[0]["url"]'] if exitcode else []
    )
    assert rapport["verschillen"] == rapport["openapi_toegevoegd"] == []


def test_openapi_detects_changes_in_shared_components() -> None:
    stock = {"paths": {}, "components": {
        "securitySchemes": {"Auth": {"type": "http", "scheme": "bearer", "description": "tekst"}},
        "parameters": {"Limit": {"name": "Limit", "in": "query", "schema": {"type": "integer"}}},
    }}
    fork = deepcopy(stock)
    fork["components"]["securitySchemes"]["Auth"]["description"] = "andere tekst"
    assert compat_api.compare_openapi(stock, fork) == ([], [])
    fork["components"]["securitySchemes"]["Auth"]["scheme"] = "basic"
    del fork["components"]["parameters"]["Limit"]
    problems, added = compat_api.compare_openapi(stock, fork)
    assert any("securitySchemes" in probleem for probleem in problems)
    assert any("parameters" in probleem for probleem in problems)
    assert added == []


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
@pytest.mark.parametrize(("gebruikers", "items"), [({}, ["film"]), ({"gast": {}}, [])])
def test_gebruikershashes_weigeren_lege_opname(gebruikers, items):
    with pytest.raises(RuntimeError, match="nul gebruikers of nul items"):
        upgrade_proef.gebruikershashes({"gebruikers": gebruikers, "items": items})


def test_hervatpunt_verandert_alleen_de_hash_van_de_betrokken_gebruiker():
    opname = {"gebruikers": {"ouder": {"Played": True}, "gast": {"PlaybackPositionTicks": 30}}, "items": ["film"]}
    voor = upgrade_proef.gebruikershashes(opname)
    opname["gebruikers"]["gast"]["PlaybackPositionTicks"] += 1
    na = upgrade_proef.gebruikershashes(opname)
    assert voor["ouder"] == na["ouder"]
    assert voor["gast"] != na["gast"]


def test_mediahash_telt_beide_bibliotheken_en_ziet_een_gewijzigde_byte(tmp_path: Path):
    proef = upgrade_proef.Proef(Namespace(werkmap=tmp_path))
    proef.music.mkdir()
    proef.films.mkdir()
    (proef.music / "item").write_bytes(b"abc")
    film = proef.films / "item"
    film.write_bytes(b"def")
    voor = proef.media_hashes()
    film.write_bytes(b"deg")
    na = proef.media_hashes()
    assert voor.keys() == na.keys() == {"media-muziek/item", "media-films/item"}
    assert voor["media-muziek/item"] == na["media-muziek/item"]
    assert voor["media-films/item"] != na["media-films/item"]
    assert upgrade_proef.digest(voor) != upgrade_proef.digest(na)
