"""Unit-tests (geen netwerk): alleen-lezen-garantie, tijdstempels, geheimen, samenvoegregels, koppelen en rechten."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from emby_overname.emby import controleer_alleen_lezen
from emby_overname.fouten import AlleenLezenFout, GeheimFout, NietToegestaneRoute
from emby_overname.hulp import datum_naar_ticks, lees_geheim, ticks_naar_datum
from emby_overname.jellyfin import controleer_route
from emby_overname.koppelen import JellyLeonIndex, Koppelaar, Padvertaling, vertaal_pad
from emby_overname.model import ItemInfo, Kijkgegevens, Spoor
from emby_overname.rechten import (
    Bibliotheekkoppeling,
    koppel_bibliotheken,
    vergelijk_beleid,
    vertaal_beleid,
    vertaal_leeftijdsgrens,
)
from emby_overname.samenvoegen import samenvoegen, toepassen, velden_toegepast, verschillen_item

# --- alleen lezen -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("methode", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "get"])
def test_emby_weigert_elke_methode_behalve_get(methode):
    with pytest.raises(AlleenLezenFout):
        controleer_alleen_lezen(methode, "/Users")


@pytest.mark.parametrize("pad", ["/Users/abc/PlayedItems/1", "/Library/Refresh", "/Items/1/Refresh", "/Users/x/Items/Latest",
                                 "/Users?api_key=x", "/Sessions", "/System/Configuration", "/Auth/Keys", "/../Users"])
def test_emby_weigert_routes_buiten_de_witte_lijst(pad):
    with pytest.raises(AlleenLezenFout):
        controleer_alleen_lezen("GET", pad)


@pytest.mark.parametrize("pad", ["/System/Info", "/Users", "/Users/7cb0d13b786f42fb917b8d8f7954f905", "/Users/1/Items",
                                 "/Items/12/PlaybackInfo", "/Library/VirtualFolders/Query", "/Persons"])
def test_emby_staat_leesroutes_toe(pad):
    controleer_alleen_lezen("GET", pad)


@pytest.mark.parametrize(("methode", "pad"), [("DELETE", "/Users/" + "a" * 32), ("POST", "/Items/" + "a" * 32),
                                               ("POST", "/Library/Refresh"), ("POST", "/Users/" + "a" * 32 + "/Password"),
                                               ("GET", "/Auth/Keys"), ("POST", "/UserPlayedItems/" + "a" * 32)])
def test_jelly_leon_alleen_officiele_overnameroutes(methode, pad):
    with pytest.raises(NietToegestaneRoute):
        controleer_route(methode, pad)


def test_jelly_leon_overnameroutes_toegestaan():
    for methode, pad in (("POST", "/Users/New"), ("POST", "/Users/" + "a" * 32 + "/Policy"), ("POST", "/Users/Configuration"),
                         ("POST", "/UserItems/" + "a" * 32 + "/UserData"), ("GET", "/Items")):
        controleer_route(methode, pad)


# --- tijd en geheimen ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tekst", ["2026-10-01T20:15:42.0000000Z", "2026-10-01T20:15:42.1234567Z", "1999-12-31T23:59:59.0000001Z"])
def test_datum_exact_heen_en_terug(tekst):
    assert ticks_naar_datum(datum_naar_ticks(tekst)) == tekst


def test_datum_varianten_en_volgorde():
    assert datum_naar_ticks("2026-10-01T20:15:42Z") == datum_naar_ticks("2026-10-01T20:15:42.0000000Z")
    assert datum_naar_ticks("2026-10-01T22:15:42+02:00") == datum_naar_ticks("2026-10-01T20:15:42Z")
    assert datum_naar_ticks("2026-10-01T20:15:42.0000001Z") - datum_naar_ticks("2026-10-01T20:15:42Z") == 1
    assert datum_naar_ticks(None) is None


def test_geheim_weigert_ruime_rechten(tmp_path: Path):
    pad = tmp_path / "sleutel"
    pad.write_text("abc123\n")
    os.chmod(pad, 0o644)
    with pytest.raises(GeheimFout) as fout:
        lees_geheim(pad, "Emby-API-sleutel")
    assert "abc123" not in str(fout.value)
    os.chmod(pad, 0o600)
    assert lees_geheim(pad, "Emby-API-sleutel") == "abc123"


def test_geheim_ontbreekt_of_ongeldig(tmp_path: Path):
    with pytest.raises(GeheimFout):
        lees_geheim(tmp_path / "bestaat-niet", "x")
    pad = tmp_path / "leeg"
    pad.write_text("twee woorden\n")
    os.chmod(pad, 0o600)
    with pytest.raises(GeheimFout):
        lees_geheim(pad, "x")


# --- samenvoegregels ----------------------------------------------------------------------------------------------

T = datum_naar_ticks


def k(**velden):
    return Kijkgegevens(**velden)


def test_eerste_run_neemt_alles_exact_over():
    e = k(gezien=True, aantal=3, laatst=T("2026-10-01T20:15:42Z"), positie=0, favoriet=True)
    velden, doel = samenvoegen(e, Kijkgegevens(), None, "Movie")
    assert velden == {"Played": True, "PlayCount": 3, "LastPlayedDate": "2026-10-01T20:15:42.0000000Z", "IsFavorite": True}
    assert doel == e


def test_hervatpunt_ticks_exact_eerste_run():
    e = k(positie=1_234_567_891, aantal=1, laatst=T("2026-10-02T10:00:00Z"))
    velden, doel = samenvoegen(e, Kijkgegevens(), None, "Episode")
    assert velden["PlaybackPositionTicks"] == 1_234_567_891
    assert doel.positie == 1_234_567_891


def test_tweede_run_zonder_wijziging_schrijft_niets():
    e = k(gezien=True, aantal=2, laatst=T("2026-10-01T20:15:42Z"), positie=5, favoriet=True, beoordeling=8.0)
    _, j = samenvoegen(e, Kijkgegevens(), None, "Movie")
    velden, _ = samenvoegen(e, j, e, "Movie")
    assert velden == {}
    velden_zonder_staat, _ = samenvoegen(e, j, None, "Movie")
    assert velden_zonder_staat == {}  # ook idempotent als de staat verloren is


def test_delta_telt_alleen_nieuwe_keren_op():
    p = k(gezien=True, aantal=2, laatst=T("2026-10-01T20:00:00Z"))
    j = k(gezien=True, aantal=3, laatst=T("2026-10-05T20:00:00Z"))  # 1× in Jelly Leon gekeken
    e = k(gezien=True, aantal=3, laatst=T("2026-10-03T20:00:00Z"))  # 1× extra in Emby
    velden, doel = samenvoegen(e, j, p, "Movie")
    assert velden == {"PlayCount": 4}
    assert doel.laatst == j.laatst


def test_eens_gezien_blijft_gezien():
    p = k(gezien=True, aantal=1, laatst=T("2026-10-01T20:00:00Z"))
    j = p
    e = k(gezien=False, aantal=1, laatst=T("2026-10-01T20:00:00Z"))
    velden, _ = samenvoegen(e, j, p, "Movie")
    assert "Played" not in velden
    redenen = {v["reden"] for v in verschillen_item(e, j, p, "Movie")}
    assert "gezien_teruggezet_in_emby" in redenen


def test_hervatpunt_volgens_nieuwste_moment():
    p = k(positie=100, laatst=T("2026-10-01T20:00:00Z"))
    e = k(positie=200, laatst=T("2026-10-02T20:00:00Z"))
    jl_nieuwer = k(positie=150, laatst=T("2026-10-03T20:00:00Z"))
    velden, _ = samenvoegen(e, jl_nieuwer, p, "Movie")
    assert "PlaybackPositionTicks" not in velden
    assert [v["reden"] for v in verschillen_item(e, jl_nieuwer, p, "Movie")] == ["hervatpunt_jelly_leon_nieuwer"]
    jl_ouder = k(positie=100, laatst=T("2026-10-01T20:00:00Z"))
    velden, doel = samenvoegen(e, jl_ouder, p, "Movie")
    assert velden["PlaybackPositionTicks"] == 200 and doel.positie == 200


def test_eigen_jelly_leon_wijziging_wordt_niet_overschreven():
    p = k(positie=100, laatst=T("2026-10-01T20:00:00Z"), favoriet=True)
    e = p  # Emby ongewijzigd
    j = k(positie=0, laatst=T("2026-10-01T20:00:00Z"), favoriet=False)  # in Jelly Leon hervatpunt gewist en favoriet weg
    velden, _ = samenvoegen(e, j, p, "Movie")
    assert velden == {}


def test_verwijderde_favoriet_in_emby_ter_beslissing():
    p = k(favoriet=True)
    e = k(favoriet=False)
    j = k(favoriet=True)
    velden, _ = samenvoegen(e, j, p, "Series")
    assert velden == {}
    assert [v["reden"] for v in verschillen_item(e, j, p, "Series")] == ["favoriet_verwijderd_in_emby"]


def test_container_krijgt_alleen_favoriet_en_beoordeling():
    e = k(gezien=True, aantal=0, favoriet=True)
    velden, _ = samenvoegen(e, Kijkgegevens(), None, "Series")
    assert velden == {"IsFavorite": True}


def test_beoordeling_nooit_stil_overschreven():
    velden, _ = samenvoegen(k(beoordeling=8.0), k(beoordeling=3.0), None, "Movie")
    assert "Rating" not in velden
    assert verschillen_item(k(beoordeling=8.0), k(beoordeling=3.0), None, "Movie")[0]["reden"] == "conflict_beoordeling"


def test_hervatten_herkent_al_uitgevoerde_schrijfactie():
    j = Kijkgegevens()
    velden = {"Played": True, "PlayCount": 2}
    assert not velden_toegepast(j, velden)
    assert velden_toegepast(toepassen(j, velden), velden)


# --- koppelen -----------------------------------------------------------------------------------------------------


def _jl_item(i, t, naam, pad, provider=None, **extra):
    return {"Id": i, "Type": t, "Name": naam, "Path": pad, "ProviderIds": provider or {}, **extra}


def _emby(i, t, naam, pad, provider=None, **extra):
    return ItemInfo.uit_api({"Id": i, "Type": t, "Name": naam, "Path": pad, "ProviderIds": provider or {}, **extra})


PADEN = [Padvertaling.uit_tekst("/mnt/emby/media=/data/media")]


def test_padvertaling_langste_prefix_en_grenzen():
    regels = [Padvertaling.uit_tekst("/mnt/a=/x"), Padvertaling.uit_tekst("/mnt/a/b=/y")]
    assert vertaal_pad("/mnt/a/b/c.mkv", regels) == "/y/c.mkv"
    assert vertaal_pad("/mnt/a/c.mkv", regels) == "/x/c.mkv"
    assert vertaal_pad("/mnt/ab/c.mkv", regels) == "/mnt/ab/c.mkv"
    with pytest.raises(ValueError):
        Padvertaling.uit_tekst("relatief=/x")


def test_koppelvolgorde_provider_dan_pad_en_redenen():
    jl = JellyLeonIndex([
        _jl_item("j1", "Movie", "Sintel", "/data/media/Films/Sintel/Sintel.mkv", {"Imdb": "tt1727587"}),
        _jl_item("j2", "Movie", "ToS", "/data/media/Films/ToS/ToS.mov", {"Imdb": "tt2285752"}),
        _jl_item("j3", "Movie", "ToS multi", "/data/media/Films/ToS multi/ToS.mkv", {"Imdb": "tt2285752"}),
        _jl_item("j4", "Movie", "Llama", "/data/media/Films/Llama/Llama.mp4"),
        _jl_item("j5", "Movie", "Spring A", "/data/media/Films/Spring A/s.mkv", {"Imdb": "tt10200208"}),
        _jl_item("j6", "Movie", "Spring B", "/data/media/Films/Spring B/s.mkv", {"Imdb": "tt10200208"}),
        _jl_item("j7", "Movie", "Conflict", "/data/media/Films/C/c.mkv", {"Imdb": "tt1", "Tmdb": "2"}),
    ])
    emby = {e.id: e for e in [
        _emby("e1", "Movie", "Sintel", "/mnt/emby/media/Andere map/Sintel.mkv", {"Imdb": "tt1727587"}),
        _emby("e2", "Movie", "ToS multi", "/mnt/emby/media/Films/ToS multi/ToS.mkv", {"Imdb": "tt2285752"}),
        _emby("e3", "Movie", "Llama", "/mnt/emby/media/Films/Llama/Llama.mp4"),
        _emby("e4", "Movie", "Hero", "/mnt/emby/media/Films/Hero/Hero.mp4"),
        _emby("e5", "Movie", "Spring", "/mnt/emby/media/Films/Spring/s.mkv", {"Imdb": "tt10200208"}),
        _emby("e6", "Movie", "Cosmos", "/mnt/emby/media/Films/Cosmos/c.mp4", {"Imdb": "tt4957236"}),
        _emby("e7", "Movie", "Conflict", "/mnt/emby/media/Films/X/c.mkv", {"Imdb": "tt1", "Tmdb": "999"}),
        _emby("e8", "BoxSet", "Collectie", None),
        _emby("e9", "Playlist", "Lijst", None),
    ]}
    koppelaar = Koppelaar(emby, jl, PADEN)
    uit = {i: koppelaar.koppel(i) for i in emby}
    assert (uit["e1"].jl_id, uit["e1"].methode) == ("j1", "provider_id")
    assert (uit["e2"].jl_id, uit["e2"].methode) == ("j3", "pad_bij_dubbel_id")
    assert (uit["e3"].jl_id, uit["e3"].methode) == ("j4", "pad")
    assert (uit["e4"].jl_id, uit["e4"].reden) == (None, "geen_id")
    assert (uit["e5"].jl_id, uit["e5"].reden, len(uit["e5"].kandidaten)) == (None, "dubbel", 2)
    assert (uit["e6"].jl_id, uit["e6"].reden) == (None, "ontbreekt")
    assert (uit["e7"].jl_id, uit["e7"].reden) == (None, "ontbreekt")  # zelfde IMDb, andere TMDb: geen gok
    assert uit["e8"].reden == "geen_id"
    assert uit["e9"].reden == "type_niet_ondersteund"


def test_aflevering_via_serie_seizoen_aflevering_zonder_gok():
    jl = JellyLeonIndex([
        _jl_item("s", "Series", "Serie", "/data/media/Series/Serie", {"Tvdb": "990001"}),
        _jl_item("a1", "Episode", "E1", "/data/media/Series/Serie/S01/E1.mkv", SeriesId="s", ParentIndexNumber=1, IndexNumber=1),
        _jl_item("a3", "Episode", "E3", "/data/media/Series/Serie/S02/E1.mkv", SeriesId="s", ParentIndexNumber=2, IndexNumber=1),
    ])
    emby = {e.id: e for e in [
        _emby("es", "Series", "Serie", "/mnt/emby/media/Series/Serie", {"Tvdb": "990001"}),
        _emby("ea1", "Episode", "E1", "/mnt/emby/media/Series/Serie/anders-01.mkv", SeriesId="es", ParentIndexNumber=1, IndexNumber=1),
        _emby("ea3", "Episode", "E3", "/mnt/emby/media/Series/Serie/- 03.mkv", SeriesId="es", ParentIndexNumber=1, IndexNumber=3),
        _emby("eabs", "Episode", "E7", "/mnt/emby/media/Series/Serie/- 07.mkv", SeriesId="es", IndexNumber=7),
    ]}
    koppelaar = Koppelaar(emby, jl, PADEN)
    assert (koppelaar.koppel("es").jl_id, koppelaar.koppel("es").methode) == ("s", "provider_id")
    assert (koppelaar.koppel("ea1").jl_id, koppelaar.koppel("ea1").methode) == ("a1", "serie_seizoen_aflevering")
    assert koppelaar.koppel("ea3").reden == "ontbreekt"
    assert koppelaar.koppel("eabs").reden == "ontbreekt"  # geen seizoennummer → niets aangenomen


# --- rechten ------------------------------------------------------------------------------------------------------

EMBY_BIB = [{"id": "g1", "item_id": "3", "naam": "Films", "locaties": ["/mnt/emby/media/Films"]},
            {"id": "g2", "item_id": "5", "naam": "Series", "locaties": ["/mnt/emby/media/Series"]}]
JL_BIB = [{"Name": "Films", "ItemId": "f" * 32, "Locations": ["/data/media/Films"]},
          {"Name": "Series", "ItemId": "e" * 32, "Locations": ["/data/media/Series"]}]
EMBY_CLASS = [{"naam": "G", "waarde": 1}, {"naam": "PG", "waarde": 5}, {"naam": "TV-PG", "waarde": 5}, {"naam": "R", "waarde": 9}]
JL_CLASS = [{"Name": "G", "Value": 0}, {"Name": "PG", "Value": 10}, {"Name": "TV-PG", "Value": 10}, {"Name": "R", "Value": 17}]


def test_bibliotheken_op_locatie_gekoppeld():
    bib = koppel_bibliotheken(EMBY_BIB, JL_BIB, PADEN)
    assert bib.emby_naar_jl["g1"] == "f" * 32 and bib.emby_naar_jl["5"] == "e" * 32
    assert bib.niet_gekoppeld == []


def test_leeftijdsgrens_via_naam_of_strenger():
    doel, regel = vertaal_leeftijdsgrens(5, EMBY_CLASS, JL_CLASS)
    assert (doel, regel.status) == (10, "gelijk")
    doel, regel = vertaal_leeftijdsgrens(5, EMBY_CLASS, [{"Name": "AL", "Value": 0}, {"Name": "12", "Value": 12}])
    assert (doel, regel.status) == (0, "strenger")
    assert vertaal_leeftijdsgrens(None, EMBY_CLASS, JL_CLASS)[0] is None


def test_kind_nooit_ruimer_dan_emby():
    bib = koppel_bibliotheken(EMBY_BIB, JL_BIB, PADEN)
    kind = {"IsAdministrator": False, "EnableAllFolders": False, "EnabledFolders": ["g2"], "MaxParentalRating": 5,
            "BlockedTags": ["Horror"], "EnableRemoteAccess": False, "EnableContentDownloading": False,
            "EnableAllDevices": False, "EnabledDevices": ["tv-1"], "ExcludedSubFolders": [], "AccessSchedules": [
                {"DayOfWeek": "Weekday", "StartHour": 7.0, "EndHour": 19.0}]}
    doel, regels = vertaal_beleid(kind, {}, bib, EMBY_CLASS, JL_CLASS, "u1")
    assert doel["EnableAllFolders"] is False and doel["EnabledFolders"] == ["e" * 32]
    assert doel["MaxParentalRating"] == 10 and doel["BlockedTags"] == ["Horror"]
    assert doel["EnableRemoteAccess"] is False and doel["EnableContentDownloading"] is False
    assert doel["EnableAllDevices"] is False and doel["EnabledDevices"] == []  # strenger: apparaat-ID's verschillen
    assert doel["AccessSchedules"] == [{"DayOfWeek": "Weekday", "StartHour": 7.0, "EndHour": 19.0, "UserId": "u1"}]
    assert all(r.status in ("gelijk", "strenger", "niet_van_toepassing") for r in regels)
    # Een Jelly Leon-beleid dat ruimer is, wordt herkend.
    ruim = {**doel, "EnableAllFolders": True, "MaxParentalRating": None, "BlockedTags": []}
    statussen = {r.veld: r.status for r in vergelijk_beleid(doel, ruim, bib)}
    assert statussen["Bibliotheektoegang"] == "ruimer"
    assert statussen["MaxParentalRating"] == "ruimer"
    assert statussen["Geblokkeerde tags"] == "ruimer"


def test_uitgesloten_submappen_maken_strenger():
    bib = koppel_bibliotheken(EMBY_BIB, JL_BIB, PADEN)
    doel, regels = vertaal_beleid({"EnableAllFolders": True, "ExcludedSubFolders": ["onbekend-formaat"]}, {}, bib,
                                  EMBY_CLASS, JL_CLASS, None)
    assert doel["EnableAllFolders"] is False and doel["EnabledFolders"] == []
    assert any(r.veld == "Bibliotheektoegang" and r.status == "strenger" for r in regels)


def test_extra_jelly_leon_bibliotheek_niet_toegekend():
    bib = Bibliotheekkoppeling({"g1": "f" * 32, "3": "f" * 32}, [], {"g1": "Films", "3": "Films"},
                               {"f" * 32: "Films", "d" * 32: "Alleen Jelly Leon"})
    doel, regels = vertaal_beleid({"EnableAllFolders": True}, {}, bib, EMBY_CLASS, JL_CLASS, None)
    assert doel["EnableAllFolders"] is False and doel["EnabledFolders"] == ["f" * 32]


def test_spoor_vergelijking_los_van_index():
    a = Spoor("Subtitle", "subrip", "dut", None)
    assert a.gelijk_aan(Spoor("Subtitle", "SUBRIP", "nld", "Nederlands"))
    assert not a.gelijk_aan(Spoor("Subtitle", "subrip", "eng", None))
    assert not a.gelijk_aan(None)


def test_emby_versies_in_een_item_naar_aparte_items_is_dubbel():
    jl = JellyLeonIndex([
        _jl_item("t1", "Movie", "ToS", "/data/media/Films/ToS/ToS.mov", {"Imdb": "tt2285752"}),
        _jl_item("t2", "Movie", "ToS multi", "/data/media/Films/ToS multi/ToS.mkv", {"Imdb": "tt2285752"}),
        _jl_item("s1", "Movie", "Samen", "/data/media/Films/Samen/a.mkv", {"Imdb": "tt1"},
                 MediaSources=[{"Path": "/data/media/Films/Samen/a.mkv"}, {"Path": "/data/media/Films/Samen/b.mkv"}]),
    ])
    emby = {e.id: e for e in [
        _emby("e1", "Movie", "ToS", "/mnt/emby/media/Films/ToS multi/ToS.mkv", {"Imdb": "tt2285752"},
              MediaSources=[{"Path": "/mnt/emby/media/Films/ToS/ToS.mov"}, {"Path": "/mnt/emby/media/Films/ToS multi/ToS.mkv"}]),
        _emby("e2", "Movie", "Samen", "/mnt/emby/media/Films/Samen/a.mkv", {"Imdb": "tt1"},
              MediaSources=[{"Path": "/mnt/emby/media/Films/Samen/a.mkv"}, {"Path": "/mnt/emby/media/Films/Samen/b.mkv"}]),
    ]}
    koppelaar = Koppelaar(emby, jl, PADEN)
    assert (koppelaar.koppel("e1").reden, len(koppelaar.koppel("e1").kandidaten)) == ("dubbel", 2)
    assert (koppelaar.koppel("e2").jl_id, koppelaar.koppel("e2").methode) == ("s1", "provider_id")  # ook in Jelly Leon één item
