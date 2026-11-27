"""Controleert het eindoordeel van JLT-65 met drie wegwerpdatabases en bestandsbomen."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

import plugin_proef as proef  # noqa: E402


@pytest.fixture
def servers(tmp_path: Path) -> list[proef.Server]:
    runs = [proef.Server(naam, "", tmp_path / naam, tmp_path / "media") for naam in ("a1", "a2", "b")]
    for server in runs:
        (server.config / "data").mkdir(parents=True)
        with sqlite3.connect(server.config / "data/jellyfin.db") as db:
            db.execute("CREATE TABLE UserData(ItemId INTEGER, PlaybackPositionTicks INTEGER)")
            db.execute("INSERT INTO UserData VALUES (1, 15000000)")
            for tabel in set(proef.BESCHERMD) - {"UserData"}:
                db.execute(f'CREATE TABLE "{tabel}"(Id INTEGER)')  # noqa: S608 - vaste lijst uit de proef
                db.execute(f'INSERT INTO "{tabel}" VALUES (1)')  # noqa: S608
    return runs


def test_gewist_hervatpunt_maakt_tabel_en_eindoordeel_rood(tmp_path: Path, servers: list[proef.Server]) -> None:
    controle = proef.Verslag()
    proef.vergelijk_databases(controle, tmp_path / "voor", *servers)
    assert controle.geslaagd
    with sqlite3.connect(servers[2].config / "data/jellyfin.db") as db:
        db.execute("UPDATE UserData SET PlaybackPositionTicks = 0")
    verslag = proef.Verslag()
    tabellen = proef.vergelijk_databases(verslag, tmp_path / "na", *servers)
    assert tabellen["data/jellyfin.db"]["UserData"]["afwijkende_kolommen"] == ["PlaybackPositionTicks"]
    assert not verslag.geslaagd
    assert {r["test"] for r in verslag.regels if not r["geslaagd"]} == {
        "data/jellyfin.db: geen tabel wijkt af van de controle-run",
        "UserData (kijkgeschiedenis) exact gelijk, zonder masker",
    }


def test_geen_uitspraak_over_beschermde_tabel_keurt_proef_af(tmp_path: Path, servers: list[proef.Server]) -> None:
    with sqlite3.connect(servers[1].config / "data/jellyfin.db") as db:
        db.execute("INSERT INTO Preferences VALUES (2)")
    verslag = proef.Verslag()
    proef.vergelijk_databases(verslag, tmp_path, *servers)
    assert not verslag.geslaagd
    assert any("beschermde tabellen" in r["test"] and not r["geslaagd"] for r in verslag.regels)


def test_userdata_met_ruismasker_wordt_geweigerd(tmp_path: Path, servers: list[proef.Server]) -> None:
    with sqlite3.connect(servers[1].config / "data/jellyfin.db") as db:
        db.execute("UPDATE UserData SET PlaybackPositionTicks = 1")
    verslag = proef.Verslag()
    proef.vergelijk_databases(verslag, tmp_path, *servers)
    assert not verslag.geslaagd
    assert any("zonder masker" in r["test"] and not r["geslaagd"] for r in verslag.regels)


def test_extra_bestand_buiten_plugindata_keurt_proef_af(servers: list[proef.Server]) -> None:
    controle = proef.Verslag()
    proef.vergelijk_bomen(controle, *servers)
    assert controle.geslaagd
    (servers[2].config / "data/onverwacht").write_bytes(b"test")
    verslag = proef.Verslag()
    proef.vergelijk_bomen(verslag, *servers)
    assert not verslag.geslaagd
    assert any("toegestane plekken" in r["test"] and not r["geslaagd"] for r in verslag.regels)
