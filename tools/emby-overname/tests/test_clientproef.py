"""JLT-70: alleen een volledige clientproef publiceert herbruikbare testdata."""

import io
import json
import secrets
import stat
import urllib.error
from subprocess import CompletedProcess

import pytest
from e2e import clientproef, proefrun


@pytest.fixture
def overdracht():
    return {"schema": "jelly-leon/clientproef/1", "image": "jelly-leon:proef", "datamap": "config", "media": "media",
            "gebruikers": [{"naam": "Gast", "wachtwoord": secrets.token_urlsafe(24), "item_id": "proefitem", "verwacht_ticks": 47_000_007}]}


def test_schema_paden_en_rechten(tmp_path, overdracht):
    uitvoer = tmp_path / "proef"
    clientproef.bereid_uitvoer_voor(uitvoer, tmp_path / "repo")
    werk = uitvoer / "werk"
    for mapnaam in ("client-config", "bib/jl", "emby-config", "geheimen", "client-cache"):
        (werk / mapnaam).mkdir(parents=True)
    (werk / "client-config" / "doelbestand").touch()
    (werk / "bib/jl" / "proeffilm").touch()
    clientproef.publiceer(uitvoer, overdracht, [])
    pakket = uitvoer / "clientproef"
    bestand = pakket / "clientproef.json"
    data = json.loads(bestand.read_text())
    assert data == overdracht
    assert set(data) == {"schema", "image", "datamap", "media", "gebruikers"}
    assert set(data["gebruikers"][0]) == {"naam", "wachtwoord", "item_id", "verwacht_ticks"}
    assert (pakket / data["datamap"] / "doelbestand").is_file()
    assert (pakket / data["media"] / "proeffilm").is_file()
    assert {p.name for p in pakket.iterdir()} == {"config", "media", "clientproef.json"}
    assert stat.S_IMODE(bestand.stat().st_mode) == 0o600
    assert stat.S_IMODE(pakket.stat().st_mode) == 0o700


@pytest.mark.parametrize("veld", ["emby_sleutel", "beheerToken", "api_key"])
@pytest.mark.parametrize("plaats", ["document", "gebruiker", "item"])
def test_geheim_veld_geweigerd(tmp_path, overdracht, veld, plaats):
    gebruiker = overdracht["gebruikers"][0]
    if plaats == "item":
        gebruiker["item_id"] = {veld: "test"}
    else:
        (overdracht if plaats == "document" else gebruiker)[veld] = "test"
    with pytest.raises(ValueError, match="Onbekend veld"):
        clientproef.publiceer(tmp_path, overdracht, [])
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("waarde", [0, -1, True, "47"])
def test_hervatpunt_moet_positieve_ticks_bevatten(overdracht, waarde):
    overdracht["gebruikers"][0]["verwacht_ticks"] = waarde
    with pytest.raises(ValueError):
        clientproef.controleer_overdracht(overdracht)


def test_bekend_servergeheim_geweigerd_in_toegestaan_veld(tmp_path, overdracht):
    with pytest.raises(ValueError, match="servergeheim"):
        clientproef.publiceer(tmp_path, overdracht, [overdracht["gebruikers"][0]["wachtwoord"]])
    assert not list(tmp_path.iterdir())


def test_uitvoer_in_werkboom_of_bestaande_overdracht_geweigerd(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    link = tmp_path / "omweg"
    link.symlink_to(repo, target_is_directory=True)
    with pytest.raises(ValueError, match="Git-werkboom"):
        clientproef.bereid_uitvoer_voor((link / "uit").resolve(), repo)
    assert not (repo / "uit").exists()
    uitvoer = tmp_path / "uit"
    clientproef.bereid_uitvoer_voor(uitvoer, repo)
    with pytest.raises(ValueError, match="lege uitvoermap"):
        clientproef.bereid_uitvoer_voor(uitvoer, repo)
    assert (uitvoer / "werk").is_dir()


@pytest.mark.parametrize("opties", [[], ["--clientproef"]], ids=["zonder-optie", "mislukte-clientproef"])
def test_proefrun_ruimt_testdata_op_zonder_overdracht(tmp_path, monkeypatch, opties):
    def onderbroken_bouw(modus, basis, corpus, ffmpeg):
        (basis / "jl").mkdir(parents=True)
        (basis / "jl" / "testfilm").touch()
        raise RuntimeError("onderbroken test")

    monkeypatch.setattr(proefrun, "docker", lambda *_args, **_kwargs: CompletedProcess([], 0))
    monkeypatch.setattr(proefrun.subprocess, "run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(proefrun, "bouw", onderbroken_bouw)
    assert proefrun.main(["--uitvoer", str(tmp_path), *opties]) == 1
    assert {p.name for p in tmp_path.iterdir()} == {"bewijs.json"}


@pytest.mark.parametrize("code,heeft_overdracht", [(0, False), (1, True)], ids=["gewone-proef", "afgekeurde-proef"])
def test_geen_clientpakket_zonder_optie_of_bij_afkeuring(tmp_path, monkeypatch, overdracht, code, heeft_overdracht):
    werk = tmp_path / "werk"
    (werk / "bib/jl").mkdir(parents=True)
    (werk / "client-config").mkdir()
    monkeypatch.setattr(proefrun.subprocess, "run", lambda *_args, **_kwargs: None)
    bewijs = proefrun.Bewijs("synthetisch")
    assert proefrun.rond_proef_af(tmp_path, bewijs, [], False, code, overdracht if heeft_overdracht else None, {}) == code
    assert {p.name for p in tmp_path.iterdir()} == {"bewijs.json"}


def test_geweigerde_login_toont_geen_teruggekaatst_wachtwoord(monkeypatch):
    wachtwoord = secrets.token_urlsafe(24)
    url = "http://localhost"

    def weigering(*_args, **_kwargs):
        raise urllib.error.HTTPError(url, 401, "test", {}, io.BytesIO(wachtwoord.encode()))

    monkeypatch.setattr(proefrun.urllib.request, "urlopen", weigering)
    with pytest.raises(RuntimeError) as fout:
        proefrun.Http(url, {}).doe("POST", "/Users/AuthenticateByName", body={"Pw": wachtwoord})
    assert str(fout.value) == "POST /Users/AuthenticateByName → HTTP 401"
