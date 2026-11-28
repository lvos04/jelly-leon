"""Controleert het eindoordeel van JLT-65 met drie wegwerpdatabases en bestandsbomen."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

import plugin_proef as proef  # noqa: E402


def test_grensantwoord_vraagt_de_hele_contractfout() -> None:
    inhoud = {"code": "payload_too_large", "message": "Te groot", "details": {"max_bytes": 1048576}, "trace_id": str(uuid.uuid4())}
    kop = {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"}
    assert proef.is_grensantwoord(413, inhoud, kop)
    for fout in (None, {}, {**inhoud, "details": {}}, {**inhoud, "trace_id": None}, {**inhoud, "message": ""}):
        assert not proef.is_grensantwoord(413, fout, kop)
    assert not proef.is_grensantwoord(200, inhoud, kop)
    assert not proef.is_grensantwoord(413, inhoud, {})


def test_jl4_proef_meldt_een_opstartfout_zonder_verzoekgegevens(tmp_path: Path, monkeypatch) -> None:
    rapport = tmp_path / "jl4.json"
    opgeruimd = []

    def zonder_server(_server):
        raise OSError("testwaarde_uit_de_aanvraag")

    monkeypatch.setattr(proef.Server, "start", zonder_server)
    monkeypatch.setattr(proef.Server, "ruim_op", lambda server: opgeruimd.append(server.naam))
    assert proef.main(["--alleen-hub", "--image", "proef", "--werkmap", str(tmp_path), "--rapport", str(rapport)]) == 1
    inhoud = json.loads(rapport.read_text())
    assert inhoud["schema"] == "jelly-leon/jl4-proef/1"
    assert not inhoud["geslaagd"]
    assert inhoud["openapi_sha256"] == hashlib.sha256(proef.OPENAPI.read_bytes()).hexdigest()
    assert len(opgeruimd) == 1 and not (tmp_path / opgeruimd[0]).exists()
    assert "testwaarde_uit_de_aanvraag" not in rapport.read_text()


@pytest.mark.parametrize("afwijkende_revisie", [False, True])
def test_rapport_identificeert_exact_het_gekozen_plugincontract(tmp_path: Path, monkeypatch, afwijkende_revisie: bool) -> None:
    rapport = tmp_path / "rapport.json"
    args = ["--image", "proef", "--werkmap", str(tmp_path), "--rapport", str(rapport)]
    contract = proef.OPENAPI
    if afwijkende_revisie:
        contract = tmp_path / "prototype.json"
        contract.write_text('{"paths": {}}')
        args.extend(["--openapi-bestand", str(contract)])

    def zonder_server(*args, **kwargs):
        raise OSError("deze unittestrun heeft geen server")

    monkeypatch.setattr(proef.subprocess, "run", zonder_server)
    assert proef.main(args) == 1
    uitkomst = json.loads(rapport.read_text())
    assert uitkomst["openapi_sha256"] == hashlib.sha256(contract.read_bytes()).hexdigest()
    assert not uitkomst["geslaagd"]


def test_zaaien_voegt_hoofdstuk_en_segment_toe_naast_bestaande_rijen(tmp_path: Path) -> None:
    film = uuid.uuid4()
    item = str(film).upper()
    (tmp_path / "data").mkdir()
    with sqlite3.connect(tmp_path / "data/jellyfin.db") as db:
        db.executescript("""
            CREATE TABLE BaseItems(Id TEXT PRIMARY KEY);
            CREATE TABLE Chapters(ItemId TEXT REFERENCES BaseItems, ChapterIndex INTEGER, StartPositionTicks INTEGER, Name TEXT,
                                  PRIMARY KEY(ItemId, ChapterIndex));
            CREATE TABLE MediaSegments(Id TEXT PRIMARY KEY, ItemId TEXT REFERENCES BaseItems, Type INTEGER,
                                       StartTicks INTEGER, EndTicks INTEGER, SegmentProviderId TEXT);
            """)
        db.execute("INSERT INTO BaseItems VALUES (?)", (item,))
        db.execute("INSERT INTO Chapters VALUES (?, 0, 0, 'Bestaand')", (item,))
        db.execute("INSERT INTO MediaSegments VALUES ('bestaand', ?, 4, 20000000, 30000000, 'andere bron')", (item,))
        db.commit()
        proef.zaai_hoofdstuk_en_segment(tmp_path, film.hex)
        assert db.execute("SELECT ChapterIndex, Name FROM Chapters WHERE ItemId = ? ORDER BY ChapterIndex",
                          (item,)).fetchall() == [(0, "Bestaand"), (1, "Proefhoofdstuk")]
        assert db.execute("SELECT SegmentProviderId, StartTicks FROM MediaSegments WHERE ItemId = ? ORDER BY SegmentProviderId",
                          (item,)).fetchall() == [("andere bron", 20000000), ("proefbron", 10000000)]


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


@pytest.mark.parametrize("opdracht", ["DELETE FROM MediaSegments", "DROP TABLE MediaSegments"])
def test_lege_of_ontbrekende_referentie_keurt_proef_af(tmp_path: Path, servers: list[proef.Server], opdracht: str) -> None:
    for server in servers:
        with sqlite3.connect(server.config / "data/jellyfin.db") as db:
            db.execute(opdracht)
    verslag = proef.Verslag()
    proef.vergelijk_databases(verslag, tmp_path, *servers)
    assert not verslag.geslaagd
    assert any("referentierijen" in r["test"] and "MediaSegments" in r["detail"] and not r["geslaagd"] for r in verslag.regels)


def test_extra_bestand_buiten_plugindata_keurt_proef_af(servers: list[proef.Server]) -> None:
    controle = proef.Verslag()
    proef.vergelijk_bomen(controle, *servers)
    assert controle.geslaagd
    (servers[2].config / "data/onverwacht").write_bytes(b"test")
    verslag = proef.Verslag()
    proef.vergelijk_bomen(verslag, *servers)
    assert not verslag.geslaagd
    assert any("toegestane plekken" in r["test"] and not r["geslaagd"] for r in verslag.regels)
