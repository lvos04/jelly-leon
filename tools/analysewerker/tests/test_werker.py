import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import zipfile

import pytest
from jl_werker import __main__ as werker
from jl_werker.inventaris import controleer_componenten, lees_lock, vergelijk_versies
from jl_werker.opdrachten import bouw_opdracht
from meet_groei import GRENS, main


def antwoorden(invoer):
    uitvoer = io.StringIO()
    werker.bedien(io.BytesIO(invoer), uitvoer)
    return [json.loads(regel) for regel in uitvoer.getvalue().splitlines()]


def test_berichten_en_lengtegrens(monkeypatch):
    monkeypatch.setattr(werker, "versies", lambda: {"ffmpeg": "proef"})
    ping = b'{"taak":"ping"}'
    grens = ping.ljust(werker.MAX_BERICHT)
    assert antwoorden(grens + b"\n" + grens + b" \n" + b'{"taak":"versies"}\n' + ping) == [
        {"antwoord": "pong"}, {"fout": "bericht_te_groot"}, {"versies": {"ffmpeg": "proef"}}, {"antwoord": "pong"},
    ]


@pytest.mark.parametrize("regel", [b"\xff", b"[]", b'{"taak":"analyse"}', b'{"taak":"versies","opties":[]}', b"[" * 2048])
def test_ongeldige_invoer_wordt_geweigerd_en_de_werker_blijft_lezen(regel):
    assert antwoorden(regel + b'\n{"taak":"ping"}\n') == [{"fout": "ongeldig_verzoek"}, {"antwoord": "pong"}]


def test_gereedschapsfout_breekt_de_lus_niet(monkeypatch):
    def onderbroken():
        raise subprocess.TimeoutExpired("proef", 1)
    monkeypatch.setattr(werker, "versies", onderbroken)
    assert antwoorden(b'{"taak":"versies"}\n{"taak":"ping"}') == [{"fout": "gereedschap_onbeschikbaar"}, {"antwoord": "pong"}]


def test_verkeerde_gebruiker_stopt_voor_het_eerste_bericht(monkeypatch):
    monkeypatch.setattr(werker.os, "geteuid", lambda: 0)
    assert werker.main() == 1


@pytest.mark.parametrize("extra", [
    ("--serialize-speech",), ("--serialize-speech=true",), ("--make-test-case",),
    ("--overwrite-input",), ("-o", "/bibliotheek/uit.srt"), ("--srtout=/bibliotheek/uit.srt",),
    ("--vad", "auditok"),
])
def test_ffsubsync_weigert_schrijfopties_en_andere_detector(extra):
    with pytest.raises(ValueError, match="geweigerd"):
        bouw_opdracht("ffsubsync", "/bibliotheek/film", "-i", "/bibliotheek/in.srt", *extra)


def test_ffsubsync_kiest_webrtc_en_standaarduitvoer():
    assert bouw_opdracht("ffsubsync", "/bibliotheek/met spatie", "-i", "/bibliotheek/in.srt")[-5:] == [
        "--vad", "webrtc", "/bibliotheek/met spatie", "-i", "/bibliotheek/in.srt",
    ]


@pytest.mark.parametrize(("formaat", "doel"), [("null", "-"), ("s16le", "pipe:1")])
def test_ffmpeg_kan_alleen_naar_de_toegestane_uitvoer(formaat, doel):
    assert bouw_opdracht("ffmpeg", "-i", "/bibliotheek/film", "-f", formaat, doel)[-2:] == [formaat, doel]


@pytest.mark.parametrize("opties", [
    ("-i", "/bibliotheek/film", "-f", "null", "/bibliotheek/uit"),
    ("-i", "/bibliotheek/film", "-f", "s16le", "/bibliotheek/uit"),
    ("-i", "/bibliotheek/film", "-f", "s16le", "pipe:5"),
    ("-i", "/bibliotheek/film", "-f", "null", "-", "-y", "/bibliotheek/uit"),
])
def test_ffmpeg_weigert_andere_uitvoer(opties):
    with pytest.raises(ValueError):
        bouw_opdracht("ffmpeg", *opties)


@pytest.mark.parametrize("pakket", ["auditok", "torch", "ctranslate2", "TRANSFORMERS"])
def test_synthetische_sbom_met_verboden_pakket_wordt_geweigerd(tmp_path, pakket):
    pad = tmp_path / "proef.cdx.json"
    pad.write_text(json.dumps({"components": [{"name": "proef", "components": [{"name": pakket}]}]}))
    with pytest.raises(ValueError, match="verboden component"):
        controleer_componenten(json.loads(pad.read_text())["components"])


def test_versieafwijking_in_sbom_wordt_geweigerd():
    versies = dict.fromkeys(["python", "ffsubsync", "ffmpeg", "ffprobe"], "1")
    componenten = [{"bom-ref": f"jl-gereedschap:{k}", "version": "1", "name": k} for k in versies]
    componenten[1]["purl"] = "pkg:pypi/ffsubsync@1"
    vergelijk_versies({"components": componenten}, versies)
    componenten[-1]["version"] = "2"
    with pytest.raises(ValueError, match="ffprobe"):
        vergelijk_versies({"components": componenten}, versies)


def test_echte_pip_weigert_regel_zonder_hash(tmp_path):
    # Een lokale wheel sluit netwerk- en resolutiefouten als verklaring uit.
    wiel = tmp_path / "proefpakket-1-py3-none-any.whl"
    info = "proefpakket-1.dist-info"
    with zipfile.ZipFile(wiel, "w") as archief:
        archief.writestr(info + "/METADATA", "Metadata-Version: 2.1\nName: proefpakket\nVersion: 1\n")
        archief.writestr(info + "/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archief.writestr(info + "/RECORD", "")
    lock = tmp_path / "requirements.lock"
    opdracht = [sys.executable, "-m", "pip", "install", "--no-index", "--find-links", str(tmp_path), "--no-deps", "--require-hashes",
                "--ignore-installed", "--target", str(tmp_path / "doel"), "-r", str(lock)]
    lock.write_text("proefpakket==1\n")
    fout = subprocess.run(opdracht, capture_output=True, text=True)
    assert fout.returncode != 0 and "Hashes are required" in fout.stderr
    with pytest.raises(ValueError, match="pakketregel"):
        lees_lock(lock)
    lock.write_text(f"proefpakket==1 --hash=sha256:{hashlib.sha256(wiel.read_bytes()).hexdigest()}\n")
    subprocess.run(opdracht, check=True, capture_output=True)


def test_groeigrens_is_inclusief():
    assert main(123, 123 + GRENS) == 0
    assert main(123, 124 + GRENS) == 1


def test_kijkgeschiedenis_en_voortgang_blijven_leesbaar_na_geweigerde_uitvoer(tmp_path):
    bestanden = [(tmp_path / "kijkgeschiedenis.db", 15_000_000), (tmp_path / "mediaguard-voortgang.db", 37)]
    for pad, waarde in bestanden:
        with sqlite3.connect(pad) as db:
            db.execute("CREATE TABLE proef (positie INTEGER)")
            db.execute("INSERT INTO proef VALUES (?)", (waarde,))
        db.close()
    voor = [pad.read_bytes() for pad, _ in bestanden]
    for pad, _ in bestanden:
        verzoek = json.dumps({"taak": "versies", "uitvoer": str(pad)}).encode()
        assert antwoorden(verzoek + b'\n{"taak":"ping"}') == [{"fout": "ongeldig_verzoek"}, {"antwoord": "pong"}]
        with pytest.raises(ValueError, match="geweigerd"):
            bouw_opdracht("ffsubsync", "/bibliotheek/film", "-i", "/bibliotheek/in.srt", "-o", str(pad))
    assert [pad.read_bytes() for pad, _ in bestanden] == voor
    for pad, verwacht in bestanden:
        with sqlite3.connect(f"{pad.as_uri()}?mode=ro", uri=True) as db:
            assert db.execute("SELECT positie FROM proef").fetchone() == (verwacht,)
        db.close()
