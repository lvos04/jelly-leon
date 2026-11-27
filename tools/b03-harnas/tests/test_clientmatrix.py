from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest

from b03h import clientmatrix, matrixvergelijk


@pytest.mark.parametrize(("vorm", "route", "status"), [
    (None, None, None),
    ("x_emby_token", "system_info", 200),
    ("query_api_key", "gebruiker_items", 200),
    ("authorization_mediabrowser_token", "gebruiker_items", 401),
    ("query_apikey_hoofdletter", "system_info", 401),
    ("zonder_token", "stream_statisch", 401),
    ("x_mediabrowser_token", "gebruiker_items", None),
])
def test_legacy_matrix_checks_each_measured_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, vorm: str | None, route: str | None, status: int | None,
) -> None:
    statussen = {naam: {"system_info": api, "gebruiker_items": api, "stream_statisch": 206} for naam, api in {
        "authorization_mediabrowser_token": 200, "x_emby_token": 401, "x_mediabrowser_token": 401,
        "x_emby_authorization": 401, "query_api_key": 401, "query_apikey_hoofdletter": 200, "zonder_token": 401,
    }.items()}
    if vorm is not None:
        if status is None:
            del statussen[vorm][route]
        else:
            statussen[vorm][route] = status
    server = Mock()
    server.digest.return_value = "testimage"
    server.jf.items.return_value = [{"Id": "film", "Path": clientmatrix.HERO}]
    monkeypatch.setattr(clientmatrix, "StockServer", Mock(return_value=Mock(start=Mock(return_value=server))))
    monkeypatch.setattr(clientmatrix.meetslot, "exclusief_slot", lambda **_kwargs: nullcontext())
    monkeypatch.setattr(clientmatrix.legacy, "meet", Mock(return_value=statussen))
    uitvoer = tmp_path / "clientmatrix.json"
    code = clientmatrix.main(["--onderdelen", "legacy", "--uit", str(uitvoer)])
    rij, = json.loads(uitvoer.read_text(encoding="utf-8"))["clients"]
    assert rij["status_per_vorm"] == statussen
    if vorm is None:
        assert code == 0
        assert rij["status"].startswith("Sim-getest")
    else:
        assert code == 1
        assert rij["status"] == "Sim-mislukt"
        assert any(f"{vorm}/{route}" in afwijking for afwijking in rij["afwijkingen"])


def test_negatieve_matrix_vindt_regressie_ook_als_een_andere_rol_ontbreekt() -> None:
    rollen = [{"id": "web-firefox", "orakel_ok": True}, {"id": "web-chromium", "orakel_ok": True}]
    basis = {"begin": "2026-11-27T10:00:00Z", "testitem": "proeffilm"}
    stock = {**basis, "server": clientmatrix.STOCK_IMAGE, "clients": rollen}
    eind = {**basis, "server": "testimage", "alle_modules": True, "actieve_modules": {
        "ingebouwde_webclient": ["proefmodule"], "stock_webdir": ["proefmodule"],
    }, "clients": [dict(rij) for rij in reversed(rollen)]}
    code, meting = matrixvergelijk.vergelijk(stock, eind)
    assert code == 2 and "tv" in meting["onbeslist"] and not meting["regressies"]
    eind["clients"][0]["orakel_ok"] = False
    code, meting = matrixvergelijk.vergelijk(stock, eind)
    assert code == 1 and meting["regressies"] == ["web-chromium"]
    with pytest.raises(ValueError, match="UTC-dag"):
        matrixvergelijk.vergelijk(stock, {**eind, "eerdere_sessies": [{"begin": "2026-11-26T23:59:00Z"}]})
    eind["actieve_modules"]["stock_webdir"] = []
    with pytest.raises(ValueError, match="modulemeting"):
        matrixvergelijk.vergelijk(stock, eind)


def test_matrix_controleert_stand_na_de_laatste_client(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Mock()
    monkeypatch.setattr(clientmatrix, "modulelijst", lambda _api: ({"proefmodule": False}, "etag"))
    with pytest.raises(ValueError, match="veranderd"):
        clientmatrix.controleer_modules(server, ["proefmodule"])


def test_browsercrash_bewaart_pogingen_en_overige_clients(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    server = Mock()
    server.digest.return_value = "testimage"
    server.jf.items.return_value = [{"Id": "film", "Path": clientmatrix.HERO}]
    monkeypatch.setattr(clientmatrix, "StockServer", Mock(return_value=Mock(start=Mock(return_value=server))))
    monkeypatch.setattr(clientmatrix.meetslot, "exclusief_slot", lambda **_kwargs: nullcontext())
    fout = clientmatrix.WebFout("Page crashed")
    fout.pogingen = 2
    antwoord = {"items": [{"orakel_ok": True}], "harnaspogingen": 1}
    monkeypatch.setattr(clientmatrix, "harnas", Mock(side_effect=[fout, antwoord, antwoord]))
    pad = tmp_path / "matrix.json"
    assert clientmatrix.main(["--onderdelen", "web", "--uit", str(pad)]) == 1
    rijen = json.loads(pad.read_text())["clients"]
    assert [rij["aantal_pogingen"] for rij in rijen] == [2, 1, 1]
    assert [rij["orakel_ok"] for rij in rijen] == [None, True, True]
