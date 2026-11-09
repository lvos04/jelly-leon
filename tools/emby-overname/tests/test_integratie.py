"""Integratietests van de hele tool tegen de simulators (Sim-getest; de echte containers draaien in e2e/proefrun.py)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from emby_overname.__main__ import main
from emby_overname.hulp import datum_naar_ticks
from emby_overname.model import Kijkgegevens

TOOL = Path(__file__).resolve().parent.parent
FILMS_E, SERIES_E = "aaaa0000aaaa0000aaaa0000aaaa0001", "aaaa0000aaaa0000aaaa0000aaaa0002"
FILMS_J, SERIES_J = "f" * 32, "e" * 32


def jl_id(n: int) -> str:
    return f"{n:032x}"


def vul(emby, jl):
    """Bibliotheek met opzettelijke gaten (JLT-72) en vijf gebruikers (JLT-70)."""
    m = "/mnt/emby/media"
    d = "/data/media"
    for e_id, j_id, naam, pad_e, pad_j, ids, waarde, grootte_j in (
        ("10", 1, "Sintel", "Films/Sintel/Sintel.mkv", "Films/Sintel/Sintel.mkv", {"Imdb": "tt1727587"}, 7, 1000),
        ("11", 2, "Llama", "Films/Llama/Llama.mp4", "Films/Llama/Llama.mp4", {}, 0, 1000),
        ("12", 3, "Hero", "Films/Hero/Hero.mp4", "Films/Hero Blender/Hero.mp4", {}, 0, 1000),
        ("13", None, "Cosmos", "Films/Cosmos/Cosmos.mp4", None, {"Imdb": "tt4957236"}, 0, 1000),
        ("14", 4, "Spring", "Films/Spring/Spring.mkv", "Films/Spring A/Spring.mkv", {"Imdb": "tt10200208"}, 0, 1000),
        ("15", 6, "Kort", "Films/Kort/Kort.mkv", "Films/Kort/Kort.mkv", {"Imdb": "tt0000009"}, 0, 2000),
    ):
        emby.voeg_item(e_id, "Movie", naam, f"{m}/{pad_e}", FILMS_E, ids, _waarde=waarde)
        if j_id:
            jl.voeg_item(jl_id(j_id), "Movie", naam, f"{d}/{pad_j}", FILMS_J, ids, grootte=grootte_j, _waarde=waarde)
    jl.voeg_item(jl_id(5), "Movie", "Spring B", f"{d}/Films/Spring B/Spring.mkv", FILMS_J, {"Imdb": "tt10200208"})
    emby.voeg_item("20", "Series", "Serie", f"{m}/Series/Serie", SERIES_E, {"Tvdb": "990001"})
    jl.voeg_item(jl_id(20), "Series", "Serie", f"{d}/Series/Serie", SERIES_J, {"Tvdb": "990001"})
    for n in (1, 2):
        emby.voeg_item(f"2{n}", "Episode", f"E{n}", f"{m}/Series/Serie/S01/E{n}.mkv", SERIES_E, SeriesId="20",
                       SeriesName="Serie", ParentIndexNumber=1, IndexNumber=n)
        jl.voeg_item(jl_id(20 + n), "Episode", f"E{n}", f"{d}/Series/Serie/Season 01/E{n}.mkv", SERIES_J,
                     SeriesId=jl_id(20), SeriesName="Serie", ParentIndexNumber=1, IndexNumber=n)
    u = {
        "beheerder": emby.voeg_gebruiker("beheerder", {"IsAdministrator": True}),
        "anna": emby.voeg_gebruiker("Anna", config={"AudioLanguagePreference": "dut", "SubtitleMode": "Always"}),
        "bram": emby.voeg_gebruiker("Bram"),
        "kind": emby.voeg_gebruiker("Kim", {"EnableAllFolders": False, "EnabledFolders": [SERIES_E], "MaxParentalRating": 5,
                                            "BlockedTags": ["Horror"], "EnableRemoteAccess": False,
                                            "EnableContentDownloading": False}),
        "gast": emby.voeg_gebruiker("Gast", {"EnableAllFolders": False, "EnabledFolders": [FILMS_E]}),
    }
    emby.zet(u["beheerder"], "10", Played=True, PlayCount=2, LastPlayedDate="2026-10-01T20:15:42.0000000Z")
    emby.zet(u["beheerder"], "11", PlaybackPositionTicks=1_234_567_891, PlayCount=1, LastPlayedDate="2026-10-02T21:00:00.0000000Z")
    emby.zet(u["beheerder"], "12", Played=True, PlayCount=1, LastPlayedDate="2026-09-01T19:00:00.0000000Z")
    emby.zet(u["beheerder"], "13", Played=True, PlayCount=1, LastPlayedDate="2026-09-02T19:00:00.0000000Z")
    emby.zet(u["beheerder"], "14", IsFavorite=True)
    emby.zet(u["beheerder"], "20", IsFavorite=True)
    emby.zet(u["beheerder"], "21", Played=True, PlayCount=1, LastPlayedDate="2026-10-03T18:00:00.0000000Z")
    emby.zet(u["anna"], "10", PlaybackPositionTicks=600_000_001, PlayCount=0, LastPlayedDate="2026-10-04T20:00:00.0000000Z")
    emby.zet(u["anna"], "15", Played=True, PlayCount=3, LastPlayedDate="2026-10-05T20:00:00.0000000Z")
    emby.zet(u["anna"], "22", PlaybackPositionTicks=42, LastPlayedDate="2026-10-06T20:00:00.0000000Z")
    emby.spoorkeuzes[(u["anna"], "10")] = (2, 3)
    emby.spoorkeuzes[(u["anna"], "15")] = (2, None)
    emby.zet(u["bram"], "11", Played=True, PlayCount=4, LastPlayedDate="2026-10-07T20:00:00.0000000Z", IsFavorite=True)
    emby.zet(u["kind"], "21", Played=True, PlayCount=5, LastPlayedDate="2026-10-08T08:00:00.0000000Z")
    emby.zet(u["kind"], "22", PlaybackPositionTicks=99_999, LastPlayedDate="2026-10-08T09:00:00.0000000Z")
    emby.zet(u["gast"], "10", Played=True, PlayCount=1, LastPlayedDate="2026-10-09T20:00:00.0000000Z")
    return u


def basis_args(emby, jl, sleutels, werkmap):
    return ["--emby-url", emby.url, "--emby-sleutel-bestand", str(sleutels["emby"]), "--jl-url", jl.url,
            "--jl-sleutel-bestand", str(sleutels["jl"]), "--werkmap", str(werkmap), "--pad", "/mnt/emby/media=/data/media",
            "--gebruiker", "beheerder=jlbeheer"]


def draai(args, capsys):
    code = main(args)
    uit = capsys.readouterr().out.strip().splitlines()
    return code, (json.loads(uit[-1]) if uit else {})


def akkoord_voor(samenvatting: dict, soort: str, pad: Path, weglaten: int = 0) -> Path:
    rapport = json.loads(Path(samenvatting["rapport"]).read_text(encoding="utf-8"))
    verschillen = rapport["akkoord"]["verschillen"]
    akkoord = {"schema": "jelly-leon/emby-overname-akkoord/1", "soort": soort, "rapport_inhoud_sha256": rapport["inhoud_sha256"],
               "plan_sha256": rapport["plan_sha256"], "akkoord_door": "test (simulatie van de gebruiker)",
               "datum": "2026-11-09T12:00:00Z", "verschillen": verschillen[weglaten:]}
    pad.write_text(json.dumps(akkoord), encoding="utf-8")
    return pad


def proef_en_over(emby, jl, sleutels, werkmap, tmp_path, capsys, naam="a"):
    code, proef = draai(["proefrun", *basis_args(emby, jl, sleutels, werkmap)], capsys)
    assert code == 0
    akkoord = akkoord_voor(proef, "plan", tmp_path / f"akkoord-{naam}.json")
    code, over = draai(["overzetten", *basis_args(emby, jl, sleutels, werkmap), "--akkoord", str(akkoord)], capsys)
    assert code == 0
    return proef, over


def redenen(rapport_pad: str, gebruiker: str) -> Counter:
    rapport = json.loads(Path(rapport_pad).read_text(encoding="utf-8"))
    g = next(x for x in rapport["toestand"]["gebruikers"] if x["emby_naam"] == gebruiker)
    return Counter(p["reden"] for p in g["afhandellijst"])


def jl_uid(jl, naam):
    return next(u["Id"] for u in jl.gebruikers.values() if u["Name"] == naam)


def test_proefrun_schrijft_niets_en_verantwoordt_alles(emby, jl, sleutels, tmp_path, capsys):
    vul(emby, jl)
    code, proef = draai(["proefrun", *basis_args(emby, jl, sleutels, tmp_path / "werk")], capsys)
    assert code == 0
    assert jl.schrijfacties == []
    assert {m for m, _ in emby.verzoeken} == {"GET"}
    assert proef["verantwoord"] is True and proef["plan_schrijfacties"] > 0
    beheer = redenen(proef["rapport"], "beheerder")
    assert beheer["geen_id"] == 1 and beheer["ontbreekt"] == 1 and beheer["dubbel"] == 1
    for bestand in ("rapport.json", "rapport.json.sha256", "rapport.md", "rapport.html", "emby-export.json", "emby-export.json.sha256"):
        assert (Path(proef["map"]) / bestand).is_file()


def test_overname_100_procent_idempotent_en_rechten(emby, jl, sleutels, tmp_path, capsys):
    u = vul(emby, jl)
    werkmap = tmp_path / "werk"
    _, over = proef_en_over(emby, jl, sleutels, werkmap, tmp_path, capsys)
    assert over["schrijfacties"] > 0
    # Gezien (datum en aantal) en hervatpunten exact; favorieten.
    beheer = jl_uid(jl, "jlbeheer")
    assert jl.kijk(beheer, jl_id(1)) == Kijkgegevens(gezien=True, aantal=2, laatst=datum_naar_ticks("2026-10-01T20:15:42Z"))
    assert jl.kijk(beheer, jl_id(2)).positie == 1_234_567_891
    assert jl.kijk(beheer, jl_id(20)).favoriet is True
    anna = jl_uid(jl, "Anna")
    assert jl.kijk(anna, jl_id(22)).positie == 42
    assert jl.kijk(jl_uid(jl, "Kim"), jl_id(21)).aantal == 5
    for t in over["totaal"].values():
        assert t["gekoppeld"] == t["gelijk"] + t["jelly_leon_nieuwer"] or t is over["totaal"]["spoorkeuzes"]
    # Rechten: kind en gast nooit ruimer; wachtwoorden niet overgezet (willekeurig, niet bekend).
    kim = jl.gebruikers[jl_uid(jl, "Kim")]["Policy"]
    assert kim["EnableAllFolders"] is False and kim["EnabledFolders"] == [SERIES_J]
    assert kim["MaxParentalRating"] == 10 and kim["BlockedTags"] == ["Horror"] and kim["EnableRemoteAccess"] is False
    assert jl.gebruikers[jl_uid(jl, "Gast")]["Policy"]["EnabledFolders"] == [FILMS_J]
    assert jl.gebruikers[anna]["Configuration"]["AudioLanguagePreference"] == "dut"
    assert all(len(w) >= 40 for w in jl.wachtwoorden.values())
    rapport = json.loads(Path(over["rapport"]).read_text(encoding="utf-8"))
    for g in rapport["toestand"]["gebruikers"]:
        assert g["verantwoord"]["klopt"]
        assert g["zichtbaarheid"]["ruimer"] in (0, None)
    assert redenen(over["rapport"], "Anna")["spoorkeuze_niet_overzetbaar"] == 1
    assert redenen(over["rapport"], "Anna")["ander_bestand"] == 1
    assert redenen(over["rapport"], "Kim")["wachtwoord_niet_overgezet"] == 1
    # Tweede run zonder wijziging: 0 schrijfacties en inhoudelijk identiek rapport.
    voor = len(jl.schrijfacties)
    _, over2 = proef_en_over(emby, jl, sleutels, werkmap, tmp_path, capsys, "b")
    assert over2["schrijfacties"] == 0 and len(jl.schrijfacties) == voor
    assert over2["inhoud_sha256"] == over["inhoud_sha256"]
    assert {m for m, _ in emby.verzoeken} == {"GET"}
    del u


def test_delta_neemt_precies_de_wijzigingen_over(emby, jl, sleutels, tmp_path, capsys):
    u = vul(emby, jl)
    werkmap = tmp_path / "werk"
    proef_en_over(emby, jl, sleutels, werkmap, tmp_path, capsys)
    # Emby-wijzigingen bij twee gebruikers; een eigen, nieuwere Jelly Leon-wijziging bij een derde.
    emby.zet(u["anna"], "21", Played=True, PlayCount=1, LastPlayedDate="2026-11-01T20:00:00.0000000Z")
    emby.zet(u["anna"], "22", PlaybackPositionTicks=84, LastPlayedDate="2026-11-01T21:00:00.0000000Z")
    emby.zet(u["beheerder"], "20", IsFavorite=False)
    emby.zet(u["beheerder"], "10", IsFavorite=True)
    emby.zet(u["kind"], "22", PlaybackPositionTicks=150_000, LastPlayedDate="2026-11-02T09:00:00.0000000Z")
    kim = jl_uid(jl, "Kim")
    jl.userdata[(kim, jl_id(22))].update({"PlaybackPositionTicks": 777, "LastPlayedDate": "2026-11-03T09:00:00.0000000Z"})
    voor = len(jl.schrijfacties)
    proef, over = proef_en_over(emby, jl, sleutels, werkmap, tmp_path, capsys, "delta")
    geschreven = jl.schrijfacties[voor:]
    assert sorted(p for _, p in geschreven) == sorted([f"/UserItems/{jl_id(21)}/UserData", f"/UserItems/{jl_id(22)}/UserData",
                                                       f"/UserItems/{jl_id(1)}/UserData"])
    anna = jl_uid(jl, "Anna")
    assert jl.kijk(anna, jl_id(22)).positie == 84
    assert jl.kijk(kim, jl_id(22)).positie == 777  # Jelly Leon nieuwer: nooit stil overschreven
    assert jl.kijk(jl_uid(jl, "jlbeheer"), jl_id(20)).favoriet is True  # verwijderde favoriet: ter beslissing
    assert redenen(over["rapport"], "beheerder")["favoriet_verwijderd_in_emby"] == 1
    assert redenen(over["rapport"], "Kim")["hervatpunt_jelly_leon_nieuwer"] == 1
    # Een openstaande beslissing blijft staan tot de gebruiker haar oplost; de volgende run is inhoudelijk identiek.
    _, opnieuw = proef_en_over(emby, jl, sleutels, werkmap, tmp_path, capsys, "delta2")
    assert opnieuw["schrijfacties"] == 0 and opnieuw["inhoud_sha256"] == over["inhoud_sha256"]
    assert redenen(opnieuw["rapport"], "beheerder")["favoriet_verwijderd_in_emby"] == 1


def test_afgebroken_run_hervat_zonder_dubbele_schrijfacties(emby, jl, sleutels, tmp_path, capsys):
    vul(emby, jl)
    werkmap = tmp_path / "werk"
    code, proef = draai(["proefrun", *basis_args(emby, jl, sleutels, werkmap)], capsys)
    akkoord = akkoord_voor(proef, "plan", tmp_path / "akkoord.json")
    omgeving = {**os.environ, "PYTHONPATH": str(TOOL)}
    proces = subprocess.run([sys.executable, "-m", "emby_overname", "overzetten", *basis_args(emby, jl, sleutels, werkmap),
                             "--akkoord", str(akkoord), "--testhaak-afbreken", "3"],
                            capture_output=True, text=True, env=omgeving, timeout=120, check=False)
    assert proces.returncode == 137, proces.stderr
    na_kill = Counter(p for _, p in jl.schrijfacties if p.endswith("/UserData"))
    assert sum(na_kill.values()) == 3
    code, over = draai(["overzetten", *basis_args(emby, jl, sleutels, werkmap), "--akkoord", str(akkoord)], capsys)
    assert code == 0
    assert over["verantwoord"] is True
    staat = json.loads((werkmap / "staat" / "staat.json").read_text(encoding="utf-8"))
    assert staat["laatste_herstel"]["al_uitgevoerd"] == 1  # het verzoek vóór de kill werd herkend, niet herhaald
    per_item_gebruiker = Counter((m, p) for m, p in jl.schrijfacties if p.endswith("/UserData"))
    del per_item_gebruiker
    # Geen aantal dubbel opgeteld: elk gekoppeld item heeft exact de Emby-waarde.
    assert jl.kijk(jl_uid(jl, "jlbeheer"), jl_id(1)).aantal == 2
    assert jl.kijk(jl_uid(jl, "Kim"), jl_id(21)).aantal == 5
    assert not (werkmap / "staat" / "journaal.jsonl").read_text(encoding="utf-8").strip()


def test_akkoord_verplicht_en_plan_moet_gelijk_zijn(emby, jl, sleutels, tmp_path, capsys):
    u = vul(emby, jl)
    werkmap = tmp_path / "werk"
    code, proef = draai(["proefrun", *basis_args(emby, jl, sleutels, werkmap)], capsys)
    onvolledig = akkoord_voor(proef, "plan", tmp_path / "onvolledig.json", weglaten=1)
    code, _ = draai(["overzetten", *basis_args(emby, jl, sleutels, werkmap), "--akkoord", str(onvolledig)], capsys)
    assert code == 3 and jl.schrijfacties == []
    volledig = akkoord_voor(proef, "plan", tmp_path / "volledig.json")
    emby.zet(u["bram"], "10", Played=True, PlayCount=1, LastPlayedDate="2026-11-05T20:00:00.0000000Z")
    code, _ = draai(["overzetten", *basis_args(emby, jl, sleutels, werkmap), "--akkoord", str(volledig)], capsys)
    assert code == 4 and jl.schrijfacties == []


def test_archief_herimport_op_lege_kopie_en_manipulatie(emby, jl, sleutels, tmp_path, capsys):
    from nep_servers import NepJellyfin

    vul(emby, jl)
    archief = tmp_path / "archief" / "emby-kijkgegevens.json"
    code, export = draai(["export", "--emby-url", emby.url, "--emby-sleutel-bestand", str(sleutels["emby"]),
                          "--uitvoer", str(archief)], capsys)
    assert code == 0 and export["items_met_kijkgegevens"] > 0
    leeg = NepJellyfin()
    try:
        for item_id, item in jl.items.items():
            leeg.items[item_id] = dict(item)
        args = ["--bron-archief", str(archief), "--jl-url", leeg.url, "--jl-sleutel-bestand", str(sleutels["jl"]),
                "--werkmap", str(tmp_path / "werk2"), "--pad", "/mnt/emby/media=/data/media", "--gebruiker", "beheerder=jlbeheer"]
        aantal_emby = len(emby.verzoeken)
        code, proef = draai(["proefrun", *args], capsys)
        akkoord = akkoord_voor(proef, "plan", tmp_path / "akkoord-archief.json")
        code, over = draai(["overzetten", *args, "--akkoord", str(akkoord)], capsys)
        assert code == 0 and over["verantwoord"] is True
        assert len(emby.verzoeken) == aantal_emby  # Emby niet benaderd
        assert leeg.kijk(jl_uid(leeg, "jlbeheer"), jl_id(2)).positie == 1_234_567_891
        rapport = json.loads(Path(over["rapport"]).read_text(encoding="utf-8"))
        assert rapport["bron"]["archief"] is True
    finally:
        leeg.stop()
    inhoud = json.loads(archief.read_text(encoding="utf-8"))
    inhoud["gebruikers"][0]["kijkgegevens"] = {}
    archief.write_text(json.dumps(inhoud), encoding="utf-8")
    code, _ = draai(["proefrun", "--bron-archief", str(archief), "--jl-url", jl.url, "--jl-sleutel-bestand", str(sleutels["jl"]),
                     "--werkmap", str(tmp_path / "werk3")], capsys)
    assert code != 0


def test_cutover_alleen_met_akkoord_op_elk_verschil(emby, jl, sleutels, tmp_path, capsys):
    vul(emby, jl)
    _, over = proef_en_over(emby, jl, sleutels, tmp_path / "werk", tmp_path, capsys)
    volledig = akkoord_voor(over, "cutover", tmp_path / "cutover.json")
    code, uit = draai(["akkoord-controle", "--rapport", over["rapport"], "--akkoord", str(volledig)], capsys)
    assert code == 0 and uit["overstap_toegestaan"] is True
    onvolledig = akkoord_voor(over, "cutover", tmp_path / "cutover-onvolledig.json", weglaten=1)
    code, uit = draai(["akkoord-controle", "--rapport", over["rapport"], "--akkoord", str(onvolledig)], capsys)
    assert code == 6 and uit["overstap_toegestaan"] is False


def test_emby_identiek_voor_en_na_en_sleutels_nergens(emby, jl, sleutels, tmp_path, capsys):
    vul(emby, jl)
    voor, na = tmp_path / "voor.json", tmp_path / "na.json"
    draai(["export", "--emby-url", emby.url, "--emby-sleutel-bestand", str(sleutels["emby"]), "--uitvoer", str(voor)], capsys)
    proef_en_over(emby, jl, sleutels, tmp_path / "werk", tmp_path, capsys)
    draai(["export", "--emby-url", emby.url, "--emby-sleutel-bestand", str(sleutels["emby"]), "--uitvoer", str(na)], capsys)
    code, uit = draai(["vergelijk-export", str(voor), str(na)], capsys)
    assert code == 0 and uit["identiek"] is True
    assert {m for m, _ in emby.verzoeken} == {"GET"}
    for pad in [*tmp_path.rglob("*")]:
        if pad.is_file() and "secrets" not in pad.parts:
            tekst = pad.read_bytes()
            assert emby.SLEUTEL.encode() not in tekst and jl.SLEUTEL.encode() not in tekst, pad


def test_testhaak_schrijfpoging_geweigerd_voor_het_netwerk(emby, sleutels, capsys):
    code, uit = draai(["testhaak-schrijfpoging", "--emby-url", emby.url, "--emby-sleutel-bestand", str(sleutels["emby"])], capsys)
    assert code == 0
    assert all(p["geweigerd"] for p in uit["pogingen"]) and uit["netwerkverzoeken"] == 0
    assert emby.verzoeken == []


@pytest.mark.parametrize("modus", [0o640, 0o604])
def test_sleutel_met_ruime_rechten_geweigerd(emby, jl, sleutels, tmp_path, capsys, modus):
    os.chmod(sleutels["emby"], modus)
    code, _ = draai(["proefrun", *basis_args(emby, jl, sleutels, tmp_path / "werk")], capsys)
    assert code == 7 and emby.verzoeken == []
