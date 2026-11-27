"""Negatieve proeven en statistiek voor het Watch Together-harnas, met twee synthetische sporen."""

from __future__ import annotations

import pytest

from b03h import bewijs, meetslot, watchmeting
from b03h.stock import STOCK_IMAGE


@pytest.fixture
def spoor():
    return {"begin_ms": 1000, "eind_ms": 301000, "hervat_ms": 500, "playing_ms": [700, 850],
            "paren": [[[t, t, 1], [t + 5, t + 35, 1]] for t in range(1000, 301000, 80)]}


def test_klokcorrectie_inloop_en_stilstand(spoor):
    spoor["paren"][3][1][1] += 2500
    a, b = spoor["paren"][20]
    a[2] = b[2] = 0
    a[1] = b[1]
    s1 = watchmeting.beoordeel_spoor(spoor, "S1")
    s2 = watchmeting.beoordeel_spoor(spoor, "S2")
    assert (s1["drift_p50_ms"], s1["drift_p95_ms"], s1["drift_max_ms"]) == (30, 30, 2530)
    assert (s2["drift_max_ms"], s2["iedereen_speelt_ms"], s2["stilstand_ms"], s2["stilstandperioden"]) == (30, 350, 80, 1)


@pytest.mark.parametrize("fout", ["leeg", "traag", "gat", "negatief", "nan", "playing", "vroege-melding", "einde"])
def test_geen_metriek_bij_onvolledige_meting(spoor, fout):
    if fout == "leeg":
        spoor["paren"] = []
    elif fout == "traag":
        spoor["paren"] = spoor["paren"][::2]
    elif fout == "gat":
        del spoor["paren"][100:105]
    elif fout == "negatief":
        spoor["paren"][1][1][1] = -1
    elif fout == "nan":
        spoor["paren"][1][0][1] = float("nan")
    elif fout == "playing":
        spoor["playing_ms"].pop()
    elif fout == "vroege-melding":
        spoor["playing_ms"][1] = 1
    else:
        spoor["paren"].pop(0)
        del spoor["paren"][-4:]
    with pytest.raises(ValueError):
        watchmeting.beoordeel_spoor(spoor, "S1")


def test_hoge_last_telt_niet_mee(monkeypatch, tmp_path, spoor):
    monkeypatch.setattr(meetslot, "loadavg", lambda: (4.01, 1.0, 1.0))
    with meetslot.run("stock-best", 5, lock_dir=tmp_path, grens=4.0) as last:
        pass
    uit = watchmeting.beoordeel_spoor(spoor, "S3")
    runs = [{"last": {"geldig": True, "loadavg_voor": [1, 1, 1], "run": i}, "uitkomst": uit} for i in range(5)]
    assert not last.geldig
    runs.append({"last": last.als_dict()})
    resultaat = watchmeting.metrieken("S3", "stock-best", STOCK_IMAGE, runs)
    assert all(m["n"] == m["runs_geldig"] == 5 and len(m["runs"]) == 6 for m in resultaat)
    assert resultaat[1]["interval"]["onder"] == resultaat[1]["interval"]["boven"] == 30
    with pytest.raises(ValueError, match="vijf"):
        watchmeting.metrieken("S3", "stock-best", STOCK_IMAGE, runs[1:])


def test_lege_image_en_losse_tag_geweigerd(tmp_path):
    for images in ({}, {"stock": "jellyfin/jellyfin:12.4"}):
        with pytest.raises(ValueError, match="digest"):
            bewijs.schrijf(tmp_path / "bewijs.json", {"schema": bewijs.SCHEMA, "label": "voormeting-12.4", "images": images})
    assert not (tmp_path / "bewijs.json").exists()


def test_klokvenster_en_bevroren_klok():
    opnamen = [{"voor_ms": i * 100, "na_ms": i * 100 + 12, "klok_ms": i * 100} for i in range(10)]
    assert watchmeting.nulproef(opnamen)["max_ms"] == 12
    with pytest.raises(ValueError, match="liep niet"):
        watchmeting.nulproef([{**r, "klok_ms": 1} for r in opnamen])
    with pytest.raises(ValueError, match="tien"):
        watchmeting.nulproef([])
