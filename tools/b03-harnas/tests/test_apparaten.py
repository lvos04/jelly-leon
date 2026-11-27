"""B03-060: bevroren splits, afspeelfout, noemers, herhaalbaarheid en het normale JLT-40-commando."""

from __future__ import annotations

import copy
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from b03h import apparaatrapport as rapport
from b03h import apparaatset, apparaten, baseline, meetslot
from b03h.corpus.r_f5_fouten import TEST_COMBOS, init_script
from b03h.web import WebFout


def observatie(besluit="DirectPlay", ok=True):
    return {"besluit": besluit, "besluit_gemeten": True, "orakel_ok": ok, "geforceerd_ok": ok, "start": 1,
            "videobereik": "SDR", "foutmiddel_actief": True, "fouten": [] if ok else [{"err": 4}],
            "laatste": {"t": 2400 if ok else 60020}, "herstel_ms": None, "eerste_frame_ms": 500 if ok else None,
            "tijd_tot_2s_ms": 2400 if ok else None,
            "redenen": "", "hls": besluit == "Transcode", "transcoding_info": None, "cpu_kernen": None,
            "ingebrand": False, "ondertitel": None, "extern_mogelijk": False, "audio_niet_stil": "niet gemeten"}


def test_liegende_codec_blijft_een_onterechte_direct_play():
    combo = next(c for c in TEST_COMBOS if c["id"] == "mpeg2-ts")
    assert "mp2t" in init_script(combo["liegt_over"])
    c = {"id": "test-chromium-mpeg2-ts", "middel": "init-scripts/test-chromium-mpeg2-ts.js"}
    i = observatie(ok=False)
    r = apparaten.lees_start(c, "testset", i)
    k = rapport.metrieken([r])
    assert r["classificatie"] == "onterechte Direct Play" and r["foutcodes"] == [4]
    assert k["K1"]["gevallen"] == [c["id"]]
    assert k["K2"][c["id"]] == "> 60 s (geen automatisch herstel)"
    assert k["K3"]["k"] == 0 and k["K3"]["n"] == 1
    with pytest.raises(WebFout, match="vóór de grens van 60 s"):
        apparaten.lees_start(c, "testset", {**i, "laatste": {"t": 10000}})
    with pytest.raises(WebFout, match="niet actief"):
        apparaten.lees_start(c, "testset", {**i, "foutmiddel_actief": False})
    with pytest.raises(WebFout, match="PlaybackInfo"):
        apparaten.lees_start(c, "testset", {**i, "besluit_gemeten": False})


def test_geforceerde_proef_telemetrie_en_ontbrekende_waarden():
    def rij(naam, **wijzigingen):
        return apparaten.lees_start({"id": naam}, "formaten", {**observatie(), **wijzigingen})

    rijen = [rij("sdr"), rij("hdr", videobereik="HDR10"),
             rij("mkv", besluit="Transcode", hls=True, ondertitel="ass", extern_mogelijk=True, ingebrand=True,
                 transcoding_info={"hardware": "qsv", "video_direct": False}, cpu_kernen=0.61),
             rij("hls", besluit="DirectStream", hls=True, geforceerd_ok=False),
             rij("fout", orakel_ok=False, geforceerd_ok=False, herstel_ms=12400)]
    k = rapport.metrieken(rijen)
    assert set(k) == set(rapport.OMSCHRIJVING)
    assert k["K2"] == {"fout": 12400} and k["K3"]["k"] == 2 and k["K3"]["n"] == 5
    assert k["K4"]["k"] == 1 and k["K4"]["n"] == 2 and k["K4"]["geforceerd_speelt_zonder_hdr_bevestiging"] == 1
    assert k["K5"] == {"aantal": 1, "transcodes": 1}
    assert k["K6"]["hardware"]["k"] == 1 and k["K6"]["hls_zonder_sessieinfo"] == 1
    assert k["K6"]["cpu_kernen_per_transcode"] == {"mkv": 0.61}
    assert k["K7"] == {"actieve_sporen": 1, "ingebrand": 1, "onnodig": 1}
    with pytest.raises(WebFout, match="ondertitelspoor"):
        apparaten.lees_start({"id": "ass"}, "ass", observatie())


def test_herhalingen_vergelijken_besluit_en_tijd_per_item_en_start():
    rijen = [apparaten.lees_start({"id": "a"}, "devset", {**observatie(), "start": s}) for s in (1, 2)]
    runs = [{"last": {"run": n, "geldig": True}, "rijen": copy.deepcopy(rijen)} for n in range(3)]
    runs[1]["rijen"][0]["eerste_frame_ms"] = 550
    assert rapport.herhaalbaarheid(runs)["geldig"]
    runs[1]["rijen"][0]["eerste_frame_ms"] = 551
    runs[2]["rijen"][1]["besluit"] = "Transcode"
    assert [d["veld"] for d in rapport.herhaalbaarheid(runs)["verschillen"]] == ["eerste_frame_ms", "besluit"]
    runs[2]["rijen"].pop()
    with pytest.raises(ValueError, match="start"):
        rapport.herhaalbaarheid(runs)


def test_verwisselde_a5_besluiten_ondanks_hetzelfde_totaal():
    rijen = []
    oud = {}
    for n, pad in enumerate(baseline.A5_SET):
        naam = Path(pad).name
        oud[naam] = "DirectPlay" if n < 16 else "Transcode"
        besluit = "Transcode" if n == 0 else "DirectPlay" if n == 24 else oud[naam]
        rijen.append(apparaten.lees_start({"id": naam}, "a5", observatie(besluit)))
    a = rapport.vergelijking(rijen, "chromium", oud)
    assert a["gekozen_dp"] == a["verwacht_dp"] == 16 and len(a["verschillen_ter_beoordeling"]) == 2


def test_meetpoging_zonder_basis_start_geen_server(tmp_path, monkeypatch):
    monkeypatch.setattr(apparaten, "meet", lambda *a: pytest.fail("er mag geen server starten"))
    monkeypatch.setattr(meetslot, "loadavg", lambda: (4.01, 3, 2))
    uit = tmp_path / "bewijs.json"
    assert apparaten.main(["--basis", str(tmp_path / "ontbreekt"), "--uit", str(uit)]) == 1
    d = json.loads(uit.read_text())
    assert len(d["redenen"]) == 2 and d["status"] == "NIET GEMETEN (machinelast)"
    assert all(not v["runs"] and set(v["metingen"].values()) == {None} for clients in d["systemen"].values() for v in clients.values())
    assert d["status"] in uit.with_suffix(".md").read_text()
    assert apparaten.basisprobleem(baseline.EVIDENCE_MAP / "b03-016-baseline-voormeting-12.4.json")
    basis = tmp_path / "basis.json"
    basis.write_text("{")
    assert "onleesbaar" in apparaten.basisprobleem(basis)
    basis.write_text(json.dumps({"label": "definitief-forkbasis", "images": {"stock": apparaten.STOCK_IMAGE}}))
    assert "onvolledig" in apparaten.basisprobleem(basis)


def test_cli_drie_afwisselende_systemen_en_gescheiden_splits(tmp_path, monkeypatch):
    c = {"id": "test-chromium-mpeg2-ts", "pad": "/media/afgeleid/formaten/sintel-30s-mpeg2-ac3.ts", "client": "chromium",
         "middel": "init-scripts/test-chromium-mpeg2-ts.js"}
    groepen = {g: {"gevallen": gevallen, "sha256": "test"} for g, gevallen in {
        "a5": [{"id": Path(p).name, "pad": p} for p in baseline.A5_SET], "devset": [dict(c, id="dev")], "testset": [c]}.items()}
    hist = json.loads((baseline.EVIDENCE_MAP / "b03-016-baseline-voormeting-12.4/dp-matrix.json").read_text())["stock-standaard#0"]
    volgorde = []

    class Sessie:
        def __init__(self, server):
            self.s = server
            self.config_hash = {}
            self.items = {p: {"Id": str(i)} for i, p in enumerate([*baseline.A5_SET, c["pad"]])}
            self.jf = SimpleNamespace(a=SimpleNamespace(doe=lambda *args, **kwargs: {"Configuration": {}}))

        def systeem(self, naam):
            self.config_hash[naam] = "test"
            volgorde.append(naam)

        def web(self, browser, paden, opdracht, **opties):
            assert opdracht == "apparaten"
            items = []
            for p in paden:
                naam = Path(p).name
                dp = hist["zoals_webclient"][browser].get(naam, "DirectPlay").split(" (")[0]
                ok = p != c["pad"] and not (browser == "webkit" and naam == "Sintel.2010.1080p.mkv")
                for start in (1, 2):
                    items.append({**observatie(dp, ok), "id": self.items[p]["Id"], "start": start})
            return {"versie": "unit", "items": items}

    def server(naam, **kwargs):
        return nullcontext(SimpleNamespace(map=tmp_path / naam, start=lambda **_: None, inrichten=lambda _: None, digest=lambda: "test",
                                           info={"Version": "12.4"}, container_id=naam))

    monkeypatch.setattr(apparaten, "basisprobleem", lambda _: None)
    monkeypatch.setattr(apparaten, "StockServer", server)
    monkeypatch.setattr(apparaten, "devices_aan", lambda _: None)
    monkeypatch.setattr(apparaten, "WERK", tmp_path)
    monkeypatch.setattr(apparaatset, "controleer", lambda *_: {"groepen": groepen})
    monkeypatch.setattr(baseline, "Sessie", Sessie)
    monkeypatch.setattr(meetslot, "exclusief_slot", lambda **kwargs: nullcontext(0))
    monkeypatch.setattr(meetslot, "loadavg", lambda: (1, 1, 1))
    monkeypatch.setattr(baseline, "geldige_run", lambda s, r, ids, actie: (meetslot.RunLast(s, r, "t"), actie(), []))
    uit = tmp_path / "vergelijking.json"
    basis = tmp_path / "basis.json"
    basis.write_text("{}")
    assert apparaten.main(["--basis", str(basis), "--fork-image", "lokale-testimage", "--split", "testset", "--uit", str(uit)]) == 0
    d = json.loads(uit.read_text())
    assert volgorde == [s for _, s in meetslot.ab_volgorde(list(d["systemen"]), 3)]
    assert len(d["systemen"]["stock-best"]) == 5
    for profiel in d["systemen"].values():
        assert all(c["herhaalbaarheid"]["aantal_runs"] == 3 for c in profiel.values())
        for run in profiel["chromium"]["runs"]:
            assert "devset" not in run["metingen"]
            assert run["metingen"]["testset"]["1"]["K1"]["gevallen"] == [c["id"]]
    assert "onterechte Direct Play" in uit.with_suffix(".md").read_text()


def test_bevroren_v1_heeft_aparte_hashes_en_receptmiddelen(tmp_path):
    import hashlib

    from b03h.corpus.generator import BEVROREN
    from b03h.corpus.r_f5_fouten import DEV, TEST_CLIENTS

    d = json.loads(apparaatset.BEWIJS.read_text())
    groepen = d["groepen"]
    assert {g: len(p["gevallen"]) for g, p in groepen.items()} == {
        "a5": 25, "extra": 2, "formaten": 11, "ass": 1, "srt": 1, "devset": 3, "testset": 18}
    for groep in groepen.values():
        inhoud = json.dumps(groep["gevallen"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        assert hashlib.sha256(inhoud).hexdigest() == groep["sha256"]
    for recept, sha in d["recepten"].items():
        assert json.loads((BEVROREN / f"{recept}.v1.vol.manifest.json").read_text())["set_sha256"] == sha
    assert {r["id"] for r in groepen["devset"]["gevallen"]} == {c["id"] for c in DEV}
    assert {r["id"] for r in groepen["testset"]["gevallen"]} == {f"test-{b}-{c['id']}" for c in TEST_COMBOS for b in TEST_CLIENTS}
    with pytest.raises(ValueError, match="ontbreekt"):
        apparaatset.controleer(tmp_path, tmp_path)


def test_meetslot_herkent_alleen_de_geerfde_vergrendeling(tmp_path):
    import os
    import subprocess
    import sys

    slot = tmp_path / meetslot.STACK_LOCK
    slot.touch()
    script = ('from b03h.meetslot import exclusief_slot; from pathlib import Path; import sys\n'
              'with exclusief_slot(lock_dir=Path(sys.argv[1]), timeout=0) as wacht: assert wacht == 0')
    subprocess.run(["bash", "-c", 'exec 9<"$1"; flock -x 9 && "$2" -c "$3" "$4"', "slot", str(slot),
                    sys.executable, script, str(tmp_path)], check=True, env={**os.environ, "STACKSLOT": "1",
                                                                          "PYTHONPATH": str(Path(apparaten.__file__).parents[1])})
