"""De desktoprooktest beoordeelt alle afspeelmeldingen, ook bij een mislukte start."""

import json

import pytest

from b03h import desktop


@pytest.fixture
def meting():
    return {
        "webclient_geladen": True, "ingelogd": True, "chunkloaderror": False, "beginpunt_s": 0,
        "afspelen": [[1, 0], [18, 17]], "hervatpunt_s": 18, "hervatten": [[1, 18], [4, 21]], "eindpunt_s": 22,
        "voortgang_hervatten_s": [18, 21],
    }


@pytest.mark.parametrize(("wijziging", "reden"), [
    ({"hervatten": [[0.1, 0], [1, 18], [4, 21]]}, "positie 0"),
    ({"voortgang_hervatten_s": [0, 18, 21]}, "positie 0"),
    ({"voortgang_hervatten_s": []}, "geen voortgangsmelding"),
    ({"webclient_geladen": False}, "webclient"),
    ({"ingelogd": False}, "ingelogd"),
    ({"chunkloaderror": True}, "ChunkLoadError"),
    ({"chunkloaderror": None}, "onvolledig"),
    ({"hervatten": [[1, 3], [4, 6]]}, "buiten het opgeslagen hervatpunt"),
    ({"hervatten": [[1, 18], [4, 18]]}, "geen oplopende"),
    ({"eindpunt_s": 0}, "niet bewaard"),
])
def test_rooktest_keurt_ontbrekend_of_strijdig_bewijs_af(tmp_path, monkeypatch, meting, wijziging, reden):
    binary = tmp_path / desktop.BINARY
    binary.parent.mkdir(parents=True)
    binary.touch(mode=0o700)
    cdp = {**meting, **wijziging}
    monkeypatch.setattr(desktop, "draai", lambda build, image, app, uitmap, resultaat: resultaat.update(cdp=cdp))
    uit = tmp_path / "bewijs.json"

    assert desktop.main(["--stap", "alles", "--build", str(tmp_path), "--uit", str(uit)]) == 1
    bewijs = json.loads(uit.read_text())
    assert bewijs["status"] == "Sim-mislukt"
    assert reden in bewijs["reden"]
    assert bewijs["cdp"] == cdp


def test_oplopend_afspelen_en_hervatten_mogen_door(meting):
    assert desktop.beoordeel(meting) == ""


def test_ontbrekende_build_start_geen_proef(tmp_path):
    uit = tmp_path / "bewijs.json"
    assert desktop.main(["--build", str(tmp_path), "--uit", str(uit)]) == 1
    bewijs = json.loads(uit.read_text())
    assert "desktopbuild ontbreekt" in bewijs["reden"]
    assert "cdp" not in bewijs
