from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest

from b03h import clientmatrix


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
