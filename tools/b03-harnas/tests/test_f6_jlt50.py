from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from b03h.corpus import generator, manifest
from b03h.corpus import r_f6_jlt50 as recept


def test_bewijs_verwijst_naar_dezelfde_bevroren_set_als_de_meetlat():
    bewijsmap = generator.BEVROREN.parent
    bewijs = json.loads((bewijsmap / "b03-070.json").read_text())
    pad = bewijsmap / bewijs["manifest"]
    assert pad == generator.BEVROREN / "f6-segmenten.v2.vol.manifest.json"
    assert manifest.sha256_bestand(pad) == bewijs["manifest_sha256"]
    vast = json.loads(pad.read_text())
    assert manifest.inhoud_sha256(vast["bestanden"]) == vast["set_sha256"] == bewijs["set_sha256"]
    assert bewijs["seed"] == vast["seed"] and bewijs["aantallen"] == vast["aantallen"]
    assert bewijs["herhaling"]["n_per_type"] == {k: vast["aantallen"][k] for k in ("intro", "outro", "recap", "preview")}


def test_lange_montage_en_aantallen(tmp_path, monkeypatch):
    def fragment(self, spec, lab, variant="referentie"):
        return recept.Fragment(self.werk / (spec[0] + variant), 0, spec[2], lab)

    duren = {}
    def ffmpeg(self, args):
        pad = Path(args[-1])
        pad.touch()
        duren[pad] = args[args.index("-t") + 1]

    monkeypatch.setattr(recept.Montage, "fragment", fragment)
    monkeypatch.setattr(generator.Ffmpeg, "ffmpeg", ffmpeg)
    monkeypatch.setattr(generator.Ffmpeg, "ffprobe", lambda self, pad, *args: {"format": {"duration": duren[pad]}})
    monkeypatch.setattr(generator.Ffmpeg, "versie", lambda _: {})
    pad, m = generator.maak("f6-segmenten", versie="2", schaal="vol", uitvoer=tmp_path, corpus=tmp_path)
    items = json.loads((pad / "grondwaarheid.json").read_text())["afleveringen"]
    assert m["seed"] == 20261127 and m["versie"] == "2" and len({i["bestand"] for i in items}) == 62
    types = Counter()
    for i in items:
        labels = i["segmenten"]
        soorten = ["outro" if v["label"] == "aftiteling" else v["label"] for v in labels]
        types.update(soorten)
        if i["familie"] == "film":
            assert "intro" not in soorten and soorten.count("outro") == 2
        elif i["augmentatie"] == "zonder_intro":
            assert "intro" not in soorten and "post_credit" in soorten and i["duur_s"] == 1320
        else:
            assert i["duur_s"] == 22 * 60
            intro = next(v for v in labels if v["label"] == "intro")
            assert i["intro_buiten_is_venster"] == (intro["start"] > 660)
    assert all(types[s] == m["aantallen"][s] for s in ("intro", "outro", "recap", "preview", "mid_credit", "post_credit"))
    assert all(m["aantallen"][s] >= n for s, n in recept.STREEF.items())
    assert len({i["augmentatie"] for i in items}) >= len(recept.VARIANTEN)


def test_receptversie_verkeerd(tmp_path):
    with pytest.raises(ValueError, match="onbekende versie"):
        generator.maak("f6-segmenten", versie="onbekend", uitvoer=tmp_path)


def test_broncontrole_weigert_devfragment_en_onbekende_audiobron(tmp_path):
    series = tmp_path / "afgeleid" / "series"
    series.mkdir(parents=True)
    for nummer in range(8):
        pad = series / f"{nummer}.grondwaarheid.json"
        pad.write_text(json.dumps({"segmenten": [{"bron": "BB 0-1s"}]}))
    assert recept.bronscheiding(tmp_path)["overlap"] == 0
    for bron, reden in [("BB 101-102s", "overlapt"), ("BB 0-1s + audio onbekend", "onbekend")]:
        pad.write_text(json.dumps({"segmenten": [{"bron": bron}]}))
        with pytest.raises(ValueError, match=reden):
            recept.bronscheiding(tmp_path)
