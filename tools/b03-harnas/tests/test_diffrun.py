"""Differentiële controle-run: vergelijking van twee datamappen (synthetische 12.x-achtige tabellen)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

from b03h.diffrun import scenario, vergelijk, zet_alle_modules_aan
from b03h.jfapi import Http


def _db(pad: Path, *, laatste_activiteit: str, favoriet: int = 0, extra_item: bool = False, token: str = "geheim-a") -> Path:
    pad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(pad)
    con.executescript("""
        CREATE TABLE Users (Id TEXT, Username TEXT, LastActivityDate TEXT, LastLoginDate TEXT);
        CREATE TABLE BaseItems (Id TEXT, Name TEXT, DateLastSaved TEXT);
        CREATE TABLE UserData (ItemId TEXT, UserId TEXT, IsFavorite INTEGER, Played INTEGER, PlaybackPositionTicks INTEGER,
                               LastPlayedDate TEXT);
        CREATE TABLE Devices (Id INTEGER, DeviceId TEXT, AccessToken TEXT, DateLastActivity TEXT);
    """)
    con.execute("INSERT INTO Users VALUES ('u1','beheer',?,?)", (laatste_activiteit, laatste_activiteit))
    con.execute("INSERT INTO BaseItems VALUES ('i1','Hero',?)", (laatste_activiteit,))
    if extra_item:
        con.execute("INSERT INTO BaseItems VALUES ('i2','Sintel','x')")
    con.execute("INSERT INTO UserData VALUES ('i1','u1',?,1,123450000,?)", (favoriet, laatste_activiteit))
    con.execute("INSERT INTO Devices VALUES (1,'harnas',?,?)", (token, laatste_activiteit))
    con.commit()
    con.close()
    return pad


def test_stock_tegen_stock_alleen_uitzonderingen(tmp_path: Path):
    a = _db(tmp_path / "a/jellyfin.db", laatste_activiteit="2026-11-09T10:00:00Z", token="geheim-a")
    b = _db(tmp_path / "b/jellyfin.db", laatste_activiteit="2026-11-09T10:05:00Z", token="geheim-b")
    r = vergelijk(a, b)
    assert r["verschillen_buiten_uitzonderingen"] == 0
    assert set(r["uitzonderingen_geraakt"]["Users"]) == {"LastActivityDate", "LastLoginDate"}
    assert "AccessToken" in r["uitzonderingen_geraakt"]["Devices"]


def test_echt_verschil_gevonden_zonder_geheimen(tmp_path: Path):
    a = _db(tmp_path / "a/jellyfin.db", laatste_activiteit="t1", favoriet=0, token="geheim-a")
    b = _db(tmp_path / "b/jellyfin.db", laatste_activiteit="t2", favoriet=1, token="geheim-b")
    r = vergelijk(a, b)
    assert r["verschillen_buiten_uitzonderingen"] == 2
    assert r["tabellen"]["UserData"]["verschil_rijen"] == 2
    assert "geheim" not in str(r)


def test_toegestane_wijzigingslijst_per_module(tmp_path: Path):
    a = _db(tmp_path / "a/jellyfin.db", laatste_activiteit="t1", favoriet=0)
    b = _db(tmp_path / "b/jellyfin.db", laatste_activiteit="t1", favoriet=1)
    assert vergelijk(a, b, {"UserData": {"IsFavorite"}})["verschillen_buiten_uitzonderingen"] == 0


def test_extra_rij_telt(tmp_path: Path):
    a = _db(tmp_path / "a/jellyfin.db", laatste_activiteit="t1")
    b = _db(tmp_path / "b/jellyfin.db", laatste_activiteit="t1", extra_item=True)
    r = vergelijk(a, b)
    assert r["verschillen_buiten_uitzonderingen"] == 1


def test_dubbele_beschermde_rij_telt(tmp_path: Path):
    a = _db(tmp_path / "a/jellyfin.db", laatste_activiteit="t1")
    b = _db(tmp_path / "b/jellyfin.db", laatste_activiteit="t1")
    with sqlite3.connect(b) as db:
        db.execute("INSERT INTO UserData SELECT * FROM UserData")
    assert vergelijk(a, b)["tabellen"]["UserData"]["verschil_rijen"] == 1


@pytest.mark.parametrize(("gebruikers", "items"), [([], [{"Path": "film"}]), ([{"Id": "beheer"}], [])])
def test_scenario_weigert_lege_meting(gebruikers, items):
    server = Mock()
    server.jf.admin_id = "beheer"
    server.jf.items.return_value = items
    server.jf.a.doe.return_value = gebruikers
    with pytest.raises(ValueError, match="proefgebruiker"):
        scenario(server)


def _lijst(*standen: tuple[str, bool], etag: str = "stand") -> tuple[int, bytes, dict[str, str]]:
    items = [{"slug": slug, "enabled": aan} for slug, aan in standen]
    return 200, json.dumps({"items": items}).encode(), {"ETag": etag}


def test_ontdekt_alle_modules_en_controleert_elke_wijziging():
    api = Mock(spec=Http)
    begin = _lijst(("eerste", False), ("andere", False))
    tussen = _lijst(("eerste", True), ("andere", False), etag="gewijzigd")
    eind = _lijst(("eerste", True), ("andere", True), etag="laatste")
    api.ruw.side_effect = [begin, tussen, eind, eind]
    assert zet_alle_modules_aan(api) == ["andere", "eerste"]
    eerste, tweede = api.doe.call_args_list
    assert eerste.args == ("PUT", "/media/v1/modules/eerste")
    assert tweede.args == ("PUT", "/media/v1/modules/andere")
    assert eerste.kwargs["headers"]["If-Match"] == "stand"
    assert tweede.kwargs["headers"]["If-Match"] == "gewijzigd"
    assert eerste.kwargs["headers"]["Idempotency-Key"] != tweede.kwargs["headers"]["Idempotency-Key"]


def test_weigert_lege_modulelijst_en_schakelaar_die_uit_blijft():
    api = Mock(spec=Http)
    api.ruw.return_value = _lijst()
    with pytest.raises(ValueError, match="nul modules"):
        zet_alle_modules_aan(api)
    api.ruw.return_value = _lijst(("extra", False))
    with pytest.raises(ValueError, match="nog uit"):
        zet_alle_modules_aan(api)
