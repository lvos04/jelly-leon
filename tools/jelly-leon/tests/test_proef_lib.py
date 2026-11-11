"""De zuivere hulpfuncties van de pluginproef: schemacontrole, ruismasker, tabel- en bestandsvergelijking."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

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
    kopie = pl.kopieer_db(a1, tmp_path / "kopie" / "a1.db")
    assert pl.lees_db(kopie)["UserData"] == (["ItemId", "Gespeeld"], [("item", 1)])


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
    assert pl.IPV4.search("adres 192.168.1.20 hier") and not pl.IPV4.search("2026-11-11T10:00:00.123Z 12.4.0-jl.0")


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
