"""Corpusgenerator: manifest, bevriezen, download (tijdelijk + sha256 + atomair) en elk recept reproduceerbaar
(zelfde sha256 bij dezelfde seed) met grondwaarheid en licentie — op een synthetisch mini-corpus met de host-ffmpeg."""

from __future__ import annotations

import hashlib
import http.server
import json
import subprocess
import threading
from pathlib import Path

import pytest

from b03h.corpus import generator, manifest
from b03h.corpus.basis import Cue, lees_srt, licentie_van, schrijf_srt
from b03h.corpus.download import DownloadFout, download
from b03h.corpus.r_f1_framecode import BREEDTE, HOOGTE, lees_framecode
from b03h.guard import MARKERING

KLEINE_RECEPTEN = ["f1-framecode", "f2-dsyn", "f3-ondertitels", "f5-fouten", "ass", "groot-bestand", "f4-tqc", "f6-segmenten"]


def test_licenties_en_beperkt():
    assert licentie_van("pioneer-one/Pioneer.One.S01E01.720p.x264-VODO.mp4")[1] is True
    assert licentie_van("pioneer-one/subs/x.srt")[1] is True
    assert licentie_van("blender/hero/hero.mp4") == ("CC BY 4.0 (Blender Studio, Hero)", False)
    with pytest.raises(KeyError):
        licentie_van("onbekend/bestand.mkv")


def test_srt_tolerant_en_rondreis(tmp_path: Path):
    ruw = "1\n00:00:01,000 --> 00:00:02,500 Tekst direct achter de tijd\n\n2\n00:00:03,000 --> 00:00:04,000\nregel a\nregel b\n\n"
    pad = tmp_path / "a.srt"
    pad.write_text(ruw, encoding="utf-8")
    cues = lees_srt(pad)
    assert [c.tekst for c in cues] == ["Tekst direct achter de tijd", "regel a\nregel b"]
    assert cues[0].start == 1.0 and cues[0].eind == 2.5
    pad.write_text(schrijf_srt(cues), encoding="utf-8")
    assert lees_srt(pad) == cues
    assert schrijf_srt([Cue(-1.0, 0.5, "x")]).startswith("1\n00:00:00,000 --> 00:00:00,500")


def test_manifest_controleer_en_sha256sum(tmp_path: Path):
    s = tmp_path / "set"
    (s / "a").mkdir(parents=True)
    (s / "a/x.bin").write_bytes(b"abc")
    (s / "y.json").write_text("{}", encoding="utf-8")
    m = manifest.maak(s, recept="r", versie="1", seed=1, schaal="klein", parameters={}, ffmpeg={}, bronnen=[], licenties=["x"],
                      beperkt=False, aantallen={})
    manifest.schrijf(s, m)
    assert manifest.controleer(s, m) == []
    ok, _ = generator.sha256sum_c(s, s / "SHA256SUMS")
    assert ok
    (s / "a/x.bin").write_bytes(b"abd")
    assert manifest.controleer(s, m) == ["sha256 wijkt af: a/x.bin"]
    ok, uit = generator.sha256sum_c(s, s / "SHA256SUMS")
    assert not ok and "FAILED" in uit
    (s / "extra.txt").write_text("x", encoding="utf-8")
    assert "extra bestand: extra.txt" in manifest.controleer(s, m)


def test_bevriezen_weigert_niet_reproduceerbaar(tmp_path: Path):
    m = {"recept": "r", "versie": "1", "seed": 5, "schaal": "klein", "parameters": {}, "set_sha256": "a" * 64,
         "bestanden": [{"pad": "x", "sha256": "1" * 64, "grootte": 1}], "gemaakt": "t"}
    pad, uitkomst = manifest.bevries(m, tmp_path)
    assert uitkomst == "nieuw bevroren" and "gemaakt" not in json.loads(pad.read_text())
    assert manifest.bevries(m, tmp_path)[1] == "gelijk aan bevroren manifest"
    with pytest.raises(ValueError, match="niet reproduceerbaar"):
        manifest.bevries({**m, "set_sha256": "b" * 64}, tmp_path)
    with pytest.raises(ValueError, match="nieuwe versie"):
        manifest.bevries({**m, "seed": 6}, tmp_path)


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def webserver(tmp_path: Path):
    (tmp_path / "www").mkdir()
    (tmp_path / "www/bestand.bin").write_bytes(b"corpusinhoud" * 1000)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *a: _Handler(*a, directory=str(tmp_path / "www")))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_download_tijdelijk_sha256_atomair(tmp_path: Path, webserver: str):
    goed = hashlib.sha256(b"corpusinhoud" * 1000).hexdigest()
    doel = tmp_path / "doel/bestand.bin"
    assert download(f"{webserver}/bestand.bin", doel, goed, wacht=0.01) == goed
    assert doel.read_bytes() == b"corpusinhoud" * 1000
    assert not list(doel.parent.glob(".bestand.bin.deel-*"))
    # verkeerde sha256: het doel wordt nooit (half) overschreven
    doel2 = tmp_path / "doel/ander.bin"
    with pytest.raises(DownloadFout):
        download(f"{webserver}/bestand.bin", doel2, "0" * 64, pogingen=2, wacht=0.01)
    assert not doel2.exists() and not list(doel2.parent.glob(".ander.bin.deel-*"))
    with pytest.raises(DownloadFout, match="https"):
        download("http://voorbeeld.invalid/x", tmp_path / "x", None)


@pytest.mark.parametrize("recept", KLEINE_RECEPTEN)
def test_recept_reproduceerbaar_met_grondwaarheid(recept: str, mini_corpus: Path, tmp_path: Path):
    params = {"doel_bytes": 2_000_000} if recept == "groot-bestand" else {}
    sets = []
    for i in range(2):
        doel, m = generator.maak(recept, schaal="klein", ffmpeg="host", uitvoer=tmp_path / f"uit{i}", corpus=mini_corpus,
                                 parameters=params)
        assert manifest.controleer(doel, m) == []
        assert generator.sha256sum_c(doel, doel / "SHA256SUMS")[0]
        assert m["licenties"] and m["bestanden"] and m["aantallen"]
        assert any(b["pad"].endswith("grondwaarheid.json") for b in m["bestanden"]), "grondwaarheid ontbreekt"
        assert not m["licentie_beperkt"]
        sets.append(m["set_sha256"])
    assert sets[0] == sets[1], f"{recept}: niet reproduceerbaar"
    # andere seed → andere set (behalve recepten zonder toeval)
    if recept in ("f2-dsyn", "f3-ondertitels", "f4-tqc", "f6-segmenten"):
        _, m3 = generator.maak(recept, schaal="klein", seed=7, ffmpeg="host", uitvoer=tmp_path / "uit-seed7", corpus=mini_corpus)
        assert m3["set_sha256"] != sets[0]


def test_framecode_decodeerbaar(mini_corpus: Path, tmp_path: Path):
    doel, _ = generator.maak("f1-framecode", schaal="klein", ffmpeg="host", uitvoer=tmp_path, corpus=mini_corpus)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(doel / "sync/hero-framecode.mkv"), "-f", "rawvideo", "-pix_fmt", "gray",
                          "-"], capture_output=True, check=True).stdout
    grootte = BREEDTE * HOOGTE
    waarden = [lees_framecode(raw[i * grootte:(i + 1) * grootte]) for i in range(len(raw) // grootte)]
    assert len(waarden) >= 90 and waarden == list(range(len(waarden)))


def test_beperkte_set_krijgt_markering(tmp_path: Path):
    s = tmp_path / "set"
    s.mkdir()
    (s / "grondwaarheid.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    generator._markeer_beperkt(s)
    assert MARKERING in (s / "grondwaarheid.json").read_text(encoding="utf-8")
    assert (s / "LICENTIE-BEPERKT.txt").exists()


def test_opruimen_alleen_onder_uitvoer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generator, "UITVOER", tmp_path / "uit")
    (tmp_path / "uit/set1").mkdir(parents=True)
    (tmp_path / "elders").mkdir()
    assert generator.main(["opruimen", str(tmp_path / "elders")]) == 1
    assert (tmp_path / "elders").exists()
    assert generator.main(["opruimen", str(tmp_path / "uit/set1")]) == 0
    assert not (tmp_path / "uit/set1").exists()


def test_recepten_dekken_f1_tot_f6():
    functies = {r.functie for r in generator.RECEPTEN.values()}
    assert {"F1", "F2", "F3", "F4", "F5", "F6"} <= {f.split("/")[0] for f in functies}
    assert {"ass", "groot-bestand"} <= set(generator.RECEPTEN)
