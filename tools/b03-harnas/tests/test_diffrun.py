"""Differentiële controle-run: vergelijking van twee datamappen (synthetische 12.x-achtige tabellen)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from b03h.diffrun import vergelijk


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
