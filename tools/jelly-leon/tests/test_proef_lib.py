"""De zuivere hulpfuncties van de pluginproef: schemacontrole, ruismasker, tabel- en bestandsvergelijking."""
from __future__ import annotations

import base64
import sqlite3
import sys
import uuid
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

import plugin_proef as pp  # noqa: E402
import proef_lib as pl  # noqa: E402

DOC = {
    "paths": {
        "/connector/v1/health": {"get": {"responses": {"200": {"content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/Ding"}}}}, "401": {}}}},
        "/Items": {"get": {"responses": {}}, "parameters": []},
    },
    "components": {"schemas": {"Ding": {
        "type": "object", "additionalProperties": False, "required": ["id", "soort"],
        "properties": {
            "id": {"type": "string", "format": "uuid"}, "soort": {"type": "string", "enum": ["a", "b"]},
            "wanneer": {"type": "string", "format": "date-time", "nullable": True},
            "dagen": {"type": "integer", "minimum": 1, "maximum": 365},
            "naam": {"type": "string", "pattern": "^[a-z]+\\.[a-z]+$"},
            "lijst": {"type": "array", "items": {"type": "boolean"}},
        }}}},
}
GOED = {"id": "5b0f1d0a-6c1e-4f67-9d5e-0a1b2c3d4e5f", "soort": "a", "wanneer": "2026-01-02T03:04:05.123Z", "dagen": 30,
        "naam": "media.klaar", "lijst": [True, False]}


def _fouten(**wijziging: object) -> list[str]:
    return pl.valideer({**GOED, **wijziging}, {"$ref": "#/components/schemas/Ding"}, DOC)


def test_schema_goed_en_elke_soort_fout() -> None:
    assert _fouten() == []
    assert _fouten(wanneer=None) == []
    assert any("null" in f for f in _fouten(soort=None))
    assert any("staat niet in" in f for f in _fouten(soort="c"))
    assert any("geen uuid" in f for f in _fouten(id="x"))
    assert any("geen date-time" in f for f in _fouten(wanneer="gisteren"))
    assert any("kleiner" in f for f in _fouten(dagen=0)) and any("groter" in f for f in _fouten(dagen=366))
    assert any("verwacht integer" in f for f in _fouten(dagen=True))
    assert any("past niet" in f for f in _fouten(naam="media"))
    assert any("verwacht boolean" in f for f in _fouten(lijst=[1]))
    assert any("onbekend veld" in f for f in _fouten(extra=1))
    assert any("verplicht veld id" in f for f in pl.valideer({"soort": "a"}, {"$ref": "#/components/schemas/Ding"}, DOC))


def test_antwoordschema_en_routes() -> None:
    assert pl.antwoordschema(DOC, "GET", "/connector/v1/health", 200) == {"$ref": "#/components/schemas/Ding"}
    assert pl.antwoordschema(DOC, "GET", "/connector/v1/health", 401) == {}
    assert pl.antwoordschema(DOC, "GET", "/connector/v1/health", 500) is None
    assert pl.routes(DOC, ("/connector/v1", "/media/v1")) == {("GET", "/connector/v1/health")}
    assert pl.routes(DOC, ("/",)) == {("GET", "/connector/v1/health"), ("GET", "/Items")}


def test_ruismasker_verbergt_alleen_wat_tussen_controle_runs_wisselt() -> None:
    a1 = {"Items": [{"Id": "1", "Sessie": "aaa", "Gespeeld": True}], "Totaal": 1}
    a2 = {"Items": [{"Id": "1", "Sessie": "bbb", "Gespeeld": True}], "Totaal": 1}
    ruis = pl.verschillen(a1, a2)
    assert ruis == {("Items", 0, "Sessie")} and pl.pad_tekst(next(iter(ruis))) == "$.Items[0].Sessie"
    zelfde = {"Items": [{"Id": "1", "Sessie": "ccc", "Gespeeld": True}], "Totaal": 1}
    anders = {"Items": [{"Id": "1", "Sessie": "ccc", "Gespeeld": False}], "Totaal": 1}
    assert pl.masker(zelfde, ruis) == pl.masker(a1, ruis)
    assert pl.masker(anders, ruis) != pl.masker(a1, ruis)
    # Een ruisveld telt niet mee, ook niet als het in de testrun ontbreekt; een nieuw veld blijft wel zichtbaar.
    assert pl.masker({"Items": [{"Id": "1", "Gespeeld": True}], "Totaal": 1}, ruis) == pl.masker(a1, ruis)
    assert pl.masker({**zelfde, "Nieuw": 1}, ruis) != pl.masker(a1, ruis)
    assert pl.verschillen([1, 2], [1]) == {()} and pl.verschillen(1, True) == {()}


def test_tabelvergelijking() -> None:
    kolommen = ["id", "waarde", "tijd"]
    a1 = [(1, "x", 100), (2, "y", 101)]
    assert pl.vergelijk_tabel(kolommen, a1, list(a1), list(a1))["oordeel"] == "gelijk"
    assert pl.vergelijk_tabel(kolommen, a1, list(a1), [(1, "x", 100), (2, "z", 101)])["oordeel"] == "afwijking"
    assert pl.vergelijk_tabel(kolommen, a1, list(a1), a1[:1])["oordeel"] == "afwijking"
    a2 = [(1, "x", 200), (2, "y", 201)]
    met_ruis = pl.vergelijk_tabel(kolommen, a1, a2, [(1, "x", 300), (2, "y", 301)])
    assert met_ruis["oordeel"] == "gelijk_na_masker" and met_ruis["masker"] == ["tijd"]
    assert pl.vergelijk_tabel(kolommen, a1, a2, [(1, "x", 300), (2, "GEWIJZIGD", 301)])["oordeel"] == "afwijking"
    assert pl.vergelijk_tabel(kolommen, a1, a2, [(1, "x", 300)])["oordeel"] == "afwijking"
    assert pl.vergelijk_tabel(kolommen, a1, a2[:1], a1)["oordeel"] == "ruis_onvergelijkbaar"


def _db(pad: Path, waarde: str, tijd: int, extra_tabel: bool = False) -> Path:
    v = sqlite3.connect(str(pad))
    v.execute("CREATE TABLE UserData(ItemId TEXT, Gespeeld INTEGER)")
    v.execute("CREATE TABLE Log(id INTEGER, tijd INTEGER)")
    v.execute("INSERT INTO UserData VALUES('item', ?)", (waarde,))
    v.execute("INSERT INTO Log VALUES(1, ?)", (tijd,))
    if extra_tabel:
        v.execute("CREATE TABLE Vreemd(x)")
    v.commit()
    v.close()
    return pad


def test_databasevergelijking(tmp_path: Path) -> None:
    a1, a2 = _db(tmp_path / "a1.db", "1", 10), _db(tmp_path / "a2.db", "1", 20)
    goed = pl.vergelijk_db(a1, a2, _db(tmp_path / "b.db", "1", 30))
    assert goed["UserData"]["oordeel"] == "gelijk" and goed["Log"]["oordeel"] == "gelijk_na_masker"
    fout = pl.vergelijk_db(a1, a2, _db(tmp_path / "c.db", "0", 30, extra_tabel=True))
    assert fout["UserData"]["oordeel"] == "afwijking" and fout["Vreemd"]["oordeel"] == "afwijking"
    assert fout["UserData"]["afwijkende_kolommen"] == ["Gespeeld"]
    kopie = pl.kopieer_db(a1, tmp_path / "kopie" / "a1.db")
    assert pl.lees_db(kopie)["UserData"] == (["ItemId", "Gespeeld"], [("item", 1)])


def test_schema_afwijking_bij_hernoemde_kolom_of_tabel_in_alleen_tweede_controle(tmp_path: Path) -> None:
    a1, a2, b = [_db(tmp_path / naam, "1", 10) for naam in ("a1.db", "a2.db", "b.db")]
    with sqlite3.connect(b) as db:
        db.execute("ALTER TABLE UserData RENAME COLUMN Gespeeld TO Hervatpunt")
    with sqlite3.connect(a2) as db:
        db.execute("CREATE TABLE Extra(Id INTEGER)")
    oordelen = pl.vergelijk_db(a1, a2, b)
    assert oordelen["UserData"]["oordeel"] == "afwijking"
    assert oordelen["UserData"]["reden"] == "kolommen verschillen"
    assert oordelen["Extra"]["oordeel"] == "afwijking"


def test_gewisselde_rijkoppeling_in_stock_geeft_geen_uitspraak() -> None:
    a1 = [(1, "a"), (2, "b")]
    a2 = [(1, "b"), (2, "a")]
    assert pl.vergelijk_tabel(["id", "waarde"], a1, a2, a1)["oordeel"] == "ruis_onvergelijkbaar"


def test_boom_en_ruwe_treffers(tmp_path: Path) -> None:
    gebruiker = "5b0f1d0a-6c1e-4f67-9d5e-0a1b2c3d4e5f"
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.db").write_bytes(b"xx" + gebruiker.replace("-", "").encode() + b"yy")
    (tmp_path / "b.bin").write_bytes(b"niets")
    (tmp_path / "geheim").mkdir()
    (tmp_path / "geheim" / "c").write_bytes(gebruiker.encode())
    assert set(pl.boom(tmp_path)) == {"sub/a.db", "b.bin", "geheim/c"}
    vormen = pl.guid_vormen(gebruiker)
    assert set(vormen) == {"N", "D", "N-hoofdletters", "D-hoofdletters", "bytes", "bytes-le"}
    assert pl.ruwe_treffers(tmp_path, vormen) == {"N": ["sub/a.db"], "D": ["geheim/c"]}
    assert pl.ruwe_treffers(tmp_path, vormen, overslaan=("geheim/",)) == {"N": ["sub/a.db"]}
    assert pl.ruwe_treffers(tmp_path / "bestaat-niet", vormen) == {}
    account = uuid.UUID(gebruiker)
    (tmp_path / "logboek.bin").write_bytes(b"\xff" + account.bytes_le + b"\x00" + account.bytes)
    treffers = pl.ruwe_treffers(tmp_path, vormen)
    assert treffers["bytes-le"] == treffers["bytes"] == ["logboek.bin"]
    assert pl.IPV4.search("adres 192.0.2.20 hier") and not pl.IPV4.search("2026-11-11T10:00:00.123Z 12.4.0-jl.0")


def test_gebruikerssporen_vindt_dezelfde_guid_in_wal_en_featurecache(tmp_path: Path) -> None:
    data, cache = tmp_path / "data", tmp_path / "cache"
    data.mkdir()
    (cache / "features").mkdir(parents=True)
    vormen = pl.guid_vormen("abcdef01-abcd-4bcd-abcd-abcdef012345")
    (data / "proef.db-wal").write_bytes(vormen["N-hoofdletters"])
    (cache / "features" / "proef.db-shm").write_bytes(vormen["N-hoofdletters"] + vormen["bytes"])
    assert pl.gebruikerssporen(data, cache, vormen) == {
        "N-hoofdletters": ["data/proef.db-wal", "cache/features/proef.db-shm"],
        "bytes": ["cache/features/proef.db-shm"],
    }


def test_log_handtekeningen() -> None:
    a = (
        '[08:09:35] [INF] [12] Emby.Server.Implementations.Session.SessionManager: Logging out access token "tok-a1"\n'
        "[08:09:36] [INF] [7] Jellyfin.Api.Iets: gebruiker 5b0f1d0a6c1e4f679d5e0a1b2c3d4e5f meldt zich aan\n"
    )
    b = (
        '[2026-11-11 08:10:01.120 +00:00] [INF] [31] Emby.Server.Implementations.Session.SessionManager: Logging out access token "tok-b"\n'
        "[08:10:02] [WRN] [4] Jellyfin.Plugin.JellyLeon.Iets: token tok-b geweigerd na 3 pogingen\n"
        "losse regel met wachtwoord ww-b\n"
    )
    stock = pl.log_handtekeningen(a, {"sessietoken:a1": "tok-a1", "wachtwoord:a1": "ww-a1"})
    assert stock == {("sessietoken", "Emby.Server.Implementations.Session.SessionManager", 'Logging out access token "<geheim>"'): 1}
    test = pl.log_handtekeningen(b, {"sessietoken:b": "tok-b", "wachtwoord:b": "ww-b", "leeg": ""})
    assert set(test) - set(stock) == {
        ("sessietoken", "Jellyfin.Plugin.JellyLeon.Iets", "token <geheim> geweigerd na # pogingen"),
        ("wachtwoord", "?", "losse regel met wachtwoord <geheim>"),
    }
    assert not any("tok-" in deel or "ww-" in deel for sleutel in [*stock, *test] for deel in sleutel)

def test_lekcontrole_herkent_de_waarde_in_log_xml_configuratie_en_export(tmp_path: Path, capsys) -> None:
    verslag = pp.Verslag()
    marker = verslag.geheim("proef:waarde", uuid.uuid4().hex)
    zouten = {"kernzout": uuid.uuid4().bytes, "watchzout": uuid.uuid4().bytes}
    map_ = tmp_path / "data" / "jelly-leon" / "secrets"
    map_.mkdir(parents=True, mode=0o700)
    xml = tmp_path / "plugins" / "configurations" / "Jellyfin.Plugin.JellyLeon.xml"
    xml.parent.mkdir(parents=True)
    xml.write_text(marker)
    server = Mock(config=tmp_path)
    server.logtekst.return_value = ("meetregel\n" * 21) + base64.b64encode(zouten["watchzout"]).decode()
    exports = {"bundel-devices": zouten["kernzout"], "bundel-quality": b"{}", "archief-devices": b"{}", "archief-quality": b"{}"}
    pp.geheimen_scan(verslag, server, Mock(tokens=[]), zouten, marker, exports, {})
    mislukt = [r["test"] for r in verslag.regels if not r["geslaagd"]]
    assert any(naam.startswith("logs:") for naam in mislukt)
    assert any(naam.startswith("pluginconfiguratie") for naam in mislukt)
    assert any(naam.startswith("modulebundels") for naam in mislukt)
    assert marker not in capsys.readouterr().out
    assert zouten["watchzout"].hex() not in str(verslag.regels)
