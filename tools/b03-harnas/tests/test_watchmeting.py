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


def test_meetpoging_zonder_baseline_laat_bestaand_bewijs_staan(monkeypatch, tmp_path):
    import json

    from b03h import watchtogether

    monkeypatch.setattr(meetslot, "loadavg", lambda: (1, 2, 3))
    monkeypatch.setattr(watchtogether, "meet", lambda *args: pytest.fail("geen server starten"))
    uit = tmp_path / "meting.json"
    uit.write_text("vorige meting")
    assert watchtogether.main(["--baseline", str(tmp_path / "ontbreekt"), "--uit", str(uit)]) == 3
    doc = json.loads((tmp_path / "meting-meetpoging.json").read_text())
    assert doc["status"] == "NIET GEMETEN (machinelast)" and doc["metingen"] == []
    assert doc["startcontrole"]["baseline_s_p40_50"] == "ontbreekt"
    assert uit.read_text() == "vorige meting"


def test_definitieve_baseline_beide_profielen_en_digest(tmp_path):
    import json

    from b03h import watchtogether

    pad = tmp_path / "baseline.json"
    runs = [{"last": {"loadavg_voor": [1, 2, 3], "run": i, "geldig": True}} for i in range(3)]
    ms = [bewijs.metriek(id="F5-B1-dp-beslissing-" + browser, functie="F5", omschrijving="proef", methode="tellen", systeem=s,
                         soort="telling", image=STOCK_IMAGE, seed=None, runs=runs, waarde={"k": 3}, interval=None, n=3)
          for s in watchmeting.SYSTEMEN for browser in ("chromium", "firefox")]
    d = {"schema": bewijs.SCHEMA, "label": "definitief-forkbasis", "images": {"stock": STOCK_IMAGE}, "metingen": ms}
    pad.write_text(json.dumps(d))
    assert watchtogether.controle_baseline(pad)
    for wijziging in ({"label": "voormeting-12.4"}, {"images": {"stock": "stock:12.4"}}, {"metingen": ms[:1]}, {"metingen": []}):
        pad.write_text(json.dumps(d | wijziging))
        with pytest.raises(ValueError):
            watchtogether.controle_baseline(pad)
    runs[2]["last"]["geldig"] = False
    pad.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        watchtogether.controle_baseline(pad)


def test_begin_en_eindlast_weigeren_run(monkeypatch, tmp_path):
    from b03h import watchtogether

    monkeypatch.setattr(meetslot, "LOCK_DIR", tmp_path)
    monkeypatch.setattr(meetslot, "actieve_zware_sloten", lambda *_: [])
    for lasten, start in [([4.1, 1], False), ([1, 4.1], True)]:
        reeks = iter(lasten)
        monkeypatch.setattr(meetslot, "loadavg", lambda reeks=reeks: (next(reeks), 1, 1))
        last, spoor = watchtogether.meet_run("stock-best", 0, [], lambda: {"gestart": True}, 4)
        assert not last["geldig"] and bool(spoor) == start


def test_gedeeld_slot_twee_sluit_de_meting_uit(monkeypatch, tmp_path):
    import fcntl

    from b03h import watchtogether

    monkeypatch.setattr(meetslot, "LOCK_DIR", tmp_path)
    with (tmp_path / "stack2.lock").open("w") as ander:
        fcntl.flock(ander, fcntl.LOCK_EX)
        with watchtogether.meetvenster() as bezet:
            assert bezet == "stack2.lock"
    with watchtogether.meetvenster() as bezet:
        assert bezet is None


def test_rollen_tellen_alleen_bekende_groep_geen_namen_in_bewijs():
    import json

    from b03h.watchrollen import tel

    rij = {"GroupId": "eigen", "Participants": ["testlid-a", "testlid-b"]}
    body = json.dumps([rij, {**rij, "GroupId": "andere"}]).encode()
    zichtbaar = tel((200, body, {}), "eigen", True, True)
    gast = tel((200, body, {}), "eigen", False, True)
    assert zichtbaar["gelekte_groepen"] == 0
    assert (gast["gelekte_groepen"], gast["gelekte_namen"]) == (1, 2)
    assert "testlid" not in json.dumps(gast)
    assert tel((403, b"", {}), "eigen", False, False)["gelekte_namen"] == 0
    with pytest.raises(ValueError):
        tel((500, b"", {}), "eigen", False, True)


def test_adb_bekende_frameklok_en_ongeldig_pixelformaat():
    import struct

    from b03h.watchomgeving import adb_klok

    frame, breedte, hoogte = 1301, 320, 180
    ruw = bytearray(breedte * hoogte * 4)
    for i in range(16):
        if frame & (1 << i):
            ruw[((hoogte // 2) * breedte + int((i + .45) * breedte / 16)) * 4] = 255
    tijd = (65536 + frame) * 1001 / 24
    assert adb_klok(struct.pack("<IIII", breedte, hoogte, 1, 0) + ruw, tijd, tijd + 10)["klok_ms"] == pytest.approx(tijd)
    with pytest.raises(ValueError):
        adb_klok(struct.pack("<III", breedte, hoogte, 5) + ruw, tijd, tijd + 10)


def test_s2_weigert_software_en_twee_transcodes(tmp_path):
    from b03h.watchtogether import vereis_afspeelpad

    p = tmp_path / "transcode.log"
    sessies = [{"methode": "DirectPlay", "video_transcode": False}, {"methode": "Transcode", "video_transcode": True}]
    p.write_text("ffmpeg -i bron -c:v libx264 doel")
    with pytest.raises(ValueError, match="QSV"):
        vereis_afspeelpad("S2", sessies, [p])
    p.write_text("ffmpeg -i bron -c:v h264_qsv doel")
    vereis_afspeelpad("S2", sessies, [p])
    with pytest.raises(ValueError, match="QSV"):
        vereis_afspeelpad("S2", [sessies[1], sessies[1]], [p])


def test_matrices_en_bewijs_via_normale_ingang(monkeypatch, tmp_path, spoor):
    """Stuur alleen de eigen simulators aan en controleer de volledige JSON vanuit de gewone CLI."""
    import json
    from contextlib import nullcontext
    from pathlib import Path
    from types import SimpleNamespace

    from b03h import watchtogether as wt

    schema = {"datum": "synthetisch", "loadavg": [1, 1, 1], "lastgrens": 4, "baseline_s_p40_50": "aanwezig", "meten": True}
    monkeypatch.setattr(wt, "startcontrole", lambda _: schema)
    monkeypatch.setattr(wt, "meetvenster", lambda: nullcontext(None))
    monkeypatch.setattr(wt, "WERK", tmp_path)
    monkeypatch.setattr(wt, "BEWIJSMAP", tmp_path)
    (tmp_path / "b03-016-desktop-spike.json").write_text(json.dumps({"status": "Sim-getest"}))
    monkeypatch.setattr(wt, "bronmedia", lambda *_: ({}, {}, 236000))
    jf = SimpleNamespace(zet_encoding=lambda e: e, a=SimpleNamespace(headers={"Authorization": "synthetisch"}),
                         items=lambda: [{"Path": k, "Id": k} for k in ("hero", "sintel", "hevc", "framecode")])
    server = SimpleNamespace(jf=jf, start=lambda: None, inrichten=lambda _: None, verwijder=lambda: None,
                             info={"Version": "12.4"}, digest=lambda: "simulator", container_id="sim", url="http://localhost",
                             transcodelogs=lambda: [])
    monkeypatch.setattr(wt, "StockServer", lambda *args, **kw: server)
    monkeypatch.setattr(wt, "maak_kijkers", lambda s, w, prefix: [prefix + "-a", prefix + "-b"])
    monkeypatch.setattr(wt, "rollenproef", lambda *_: {"rollen": {}})
    monkeypatch.setattr(wt.watchomgeving, "netwerk", lambda *_: nullcontext("testnet"))
    monkeypatch.setattr(wt.watchomgeving, "desktop", lambda *_: nullcontext({"cid": "desktop", "cdp": "sim"}))
    monkeypatch.setattr(wt.watchomgeving, "netem", lambda *_: nullcontext(("http://localhost", {})))
    monkeypatch.setattr(wt.watchomgeving, "adb_nulproef", lambda *_: {"max_ms": 15})
    logbestanden = []
    monkeypatch.setattr(wt, "bewaar", lambda p, d: logbestanden.append(p.name))
    monkeypatch.setattr(wt, "vereis_afspeelpad", lambda *_: None)  # echte encodercontrole afzonderlijk getoetst
    monkeypatch.setattr(wt, "meet_run", lambda systeem, nr, containers, actie, grens: (
        {"geldig": True, "run": nr, "loadavg_voor": [1, 1, 1]}, actie()))
    matrix = []
    klok = [{"voor_ms": t, "na_ms": t + 1, "klok_ms": t} for t in range(0, 100, 10)]

    def browser(opdracht, cfg, **kwargs):
        assert kwargs["pogingen"] == 1 and cfg["namen"][0] != cfg["namen"][1]
        if opdracht == "watchklok":
            return {"currentTime": klok, "browser-screenshot": klok, **({"Xvfb": klok} if "cdp" in cfg else {})}
        matrix.append((cfg["scenario"], cfg["systeem"], tuple(cfg["namen"])))
        assert ("instellingen" in cfg) == (cfg["systeem"] == "stock-best")
        assert ("urlB" in cfg) == (cfg["scenario"] == "S3")
        assert ("cdp" in cfg) == (cfg["scenario"] == "S4")
        return {**spoor, "sessies": [], "regressies": {}}

    monkeypatch.setattr(wt.web, "harnas", browser)
    uit = tmp_path / "meting.json"
    binary = tmp_path / wt.BINARY
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"testclient")
    assert wt.main(["--uit", str(uit), "--desktopbouw", str(tmp_path)]) == 0
    d = json.loads(uit.read_text())
    assert not bewijs.controleer(d)
    assert set(d["scenarios"]) == set(wt.SCENARIOS)
    assert len(matrix) == len({namen for _, _, namen in matrix}) == len(set(logbestanden)) == 50
    assert [s for scenario, s, _ in matrix if scenario == "S1"][:4] == list(watchmeting.SYSTEMEN) + list(reversed(watchmeting.SYSTEMEN))
    assert len(d["metingen"]) == 50 and all(m["n"] == m["runs_geldig"] == 5 for m in d["metingen"])
    assert all(Path(r["log"]).name in logbestanden for m in d["metingen"] for r in m["runs"])


def test_bouwslot_tijdens_elke_leesactie_vast(monkeypatch, tmp_path):
    from b03h import watchtogether

    monkeypatch.setattr(meetslot, "LOCK_DIR", tmp_path)
    monkeypatch.setattr(meetslot, "loadavg", lambda: (1, 1, 1))
    monkeypatch.setattr(meetslot.CpuMeting, "start", lambda self: self)
    monkeypatch.setattr(meetslot.CpuMeting, "stop", lambda self: {"andere_kernen": 0.0})
    monkeypatch.setattr(meetslot, "actieve_zware_sloten", lambda *_: [])

    def actie():
        return [meetslot.slot_bezet(tmp_path / naam) for naam in meetslot.ZWARE_SLOTEN]

    last, sloten = watchtogether.meet_run("stock-best", 0, [], actie, 4)
    assert last["geldig"] and sloten == [True, True]
    assert actie() == [False, False]
