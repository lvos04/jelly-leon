from __future__ import annotations

import copy
import json
import threading
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from b03h import segmentbron, segmenten
from b03h.corpus import manifest
from b03h.jfapi import Http, HttpFout, Jellyfin
from b03h.segmentmeting import TICKS, Vak, evalueer, gepaard, koppels, tijdvak, waarheid

ITEM = "00000000-0000-4000-a000-000000000001"
PAD = "series/Meetserie/Season 01/Meetserie S01E01.mkv"
LABELS = [("inhoud", 0, 10), ("intro", 10, 20), ("inhoud", 20, 30),
          ("aftiteling", 30, 40), ("mid_credit", 40, 45), ("preview", 45, 50)]
KANDIDAAT = {"view": "candidate", "item_id": ITEM, "duration_s": 50.0, "publication": "published", "analysis_state": "ok",
             "segments": [{"type": "intro", "jellyfin_type": "Intro", "start_ticks": 10 * TICKS, "end_ticks": 20 * TICKS,
                           "source": "detected", "status": "published"},
                          {"type": "credits", "jellyfin_type": "Outro", "start_ticks": 30 * TICKS, "end_ticks": 45 * TICKS,
                           "source": "confirmed", "status": "published"}], "protected": []}
PUBLIEK = {"Items": [{"ItemId": ITEM, "Type": "Outro", "StartTicks": 30 * TICKS, "EndTicks": 45 * TICKS},
                     {"ItemId": ITEM, "Type": "Intro", "StartTicks": 10 * TICKS, "EndTicks": 20 * TICKS}], "TotalRecordCount": 2}


def item():
    return {"bestand": PAD, "duur_s": 50, "segmenten": [{"label": s, "start": a, "eind": b} for s, a, b in LABELS],
            "augmentatie": "referentie", "intro_buiten_is_venster": False, "nieuwe_op": False}


class Testserver:
    __test__ = False

    def __init__(self):
        self.a = self
        self.kandidaat = copy.deepcopy(KANDIDAAT)
        self.publiek = copy.deepcopy(PUBLIEK)
        self.gets = []

    def items(self):
        return [{"Path": "/media/f6/" + PAD, "Id": ITEM, "RunTimeTicks": 50 * TICKS}]

    def doe(self, methode, pad, query=None):
        self.gets.append((methode, pad, query))
        return {f"/media/v1/segments/{ITEM}": self.kandidaat, f"/MediaSegments/{ITEM}": self.publiek}[pad]


def test_fixture_tweemaal_gelijk_en_verschoven_label_daalt():
    jf = Testserver()
    runs = []
    for _ in range(2):
        voorspeld, pub = segmentbron.lees_set(jf, [item()], True, False)
        runs.append(evalueer([item()], voorspeld, pub))
    assert runs[0] == runs[1]
    assert jf.gets == [("GET", f"/MediaSegments/{ITEM}", None), ("GET", f"/media/v1/segments/{ITEM}", {"view": "candidate"})] * 2
    meting, _ = runs[0]
    intro = meting["per_type"]["intro"]
    assert (intro["n"], intro["tp"], intro["f1"], intro["gate"]) == (1, 1, 1, "smoke-gate (n = 1)")
    assert intro["precisie"]["onder"] == intro["recall"]["onder"] == pytest.approx(0.206549)
    assert meting["per_type"]["outro"]["eindfout"]["p95_s"] == 5
    assert meting["beschermd"]["geschonden_scenes"] == 1 and meting["beschermd"]["n"] == 2
    assert meting["onterecht_overgeslagen_s_per_uur"] == 360
    verschoven = item()
    verschoven["segmenten"][:3] = [{"label": "inhoud", "start": 0, "eind": 20}, {"label": "intro", "start": 20, "eind": 30}]
    slecht, _ = evalueer([verschoven], voorspeld, pub)
    assert slecht["per_type"]["intro"]["f1"] == 0 < intro["f1"]


def test_iou_grens_een_op_een_en_gelijkstand():
    a, b = Vak("intro", 0, 10), Vak("intro", 10, 20)
    breed = Vak("intro", 0, 20)
    assert len(koppels([a, b], [breed, a])) == 2
    assert koppels([a], [Vak("intro", 0, 21)]) == []
    assert koppels([a], [Vak("recap", 0, 10)]) == []
    assert len(koppels([a], [a, a])) == 1


def test_unie_gepubliceerd_en_preview_als_preview():
    media = {PAD: [Vak("outro", 30 * TICKS, 44 * TICKS), Vak("recap", 42 * TICKS, 45 * TICKS),
                   Vak("preview", 45 * TICKS, 50 * TICKS)]}
    rapport, _ = evalueer([item()], {PAD: []}, media)
    assert rapport["beschermd"]["overlap_s"] == 5
    assert rapport["onterecht_overgeslagen_s_per_uur"] == 360
    intro = rapport["per_type"]["intro"]
    assert intro["precisie"] is None and intro["recall"]["punt"] == intro["f1"] == 0
    assert intro["grensfout"] is None and rapport["per_type"]["recap"]["f1"] is None


def test_geen_lege_of_gedeeltelijke_meting():
    for items, voorspeld, pub in [([], {}, {}), ([item()], {}, {}), ([item(), item()], {PAD: []}, {PAD: []})]:
        with pytest.raises(ValueError, match="afleveringenset"):
            evalueer(items, voorspeld, pub)
    met_gat = item()
    met_gat["segmenten"][0]["eind"] = 9
    with pytest.raises(ValueError, match="grondwaarheid"):
        waarheid(met_gat)
    for start, eind in [(False, 4), (3, 3), (-1, 2), (50, 51)]:
        with pytest.raises(ValueError, match="ticks"):
            tijdvak("intro", start, eind, 50)


@pytest.mark.parametrize(("veld", "waarde"), [("view", "published"), ("analysis_state", "pending"), ("publication", "shadow"),
                                              ("duration_s", 33), ("item_id", "00000000-0000-4000-a000-000000000002")])
def test_onbruikbaar_kandidaatantwoord_geweigerd(veld, waarde):
    jf = Testserver()
    jf.kandidaat[veld] = waarde
    with pytest.raises(ValueError):
        segmentbron.lees_set(jf, [item()], True, False)


@pytest.mark.parametrize("profiel,venster", [("is-standaard", (25, 10)), ("is-ruim", (50, 20))])
def test_is_leest_het_ingestelde_venster_en_vraagt_een_nieuwe_analyse(profiel, venster):
    config = {"AnalysisPercent": 25, "AnalysisLengthLimit": 10, "OverigeInstelling": True}
    taak = {"Id": ITEM, "Key": "IntroSkipperDetectSegmentsTask"}
    plugin = {"Id": ITEM, "Name": "Intro Skipper", "Status": "Active", "Version": segmentbron.IS_VERSIE}
    taken = []
    gestart = []

    def doe(methode, pad, *, body=None):
        if pad == f"/Plugins/{ITEM}/Configuration":
            if methode == "POST":
                assert body["OverigeInstelling"] is True
                config.update(body)
            return config.copy()
        if pad == f"/ScheduledTasks/Running/{ITEM}":
            assert methode == "POST"
            gestart.append(ITEM)
            return None
        assert methode == "GET"
        return {"/Plugins": [plugin], "/ScheduledTasks": taken,
                f"/ScheduledTasks/{ITEM}": {"State": "Idle", "LastExecutionResult": {"Status": "Completed"}}}[pad]

    jf = SimpleNamespace(a=SimpleNamespace(doe=doe))
    with pytest.raises(ValueError, match="detectietaak.*ontbreekt"):
        segmentbron._analyse(jf, profiel)
    taken.append(taak)
    resultaat = segmentbron._analyse(jf, profiel)
    assert (resultaat["venster_procent"], resultaat["venster_minuten"]) == venster
    assert gestart == [ITEM]


def test_publicatie_op_een_tick_en_schaduw_afzonderlijk():
    jf = Testserver()
    jf.publiek["Items"][0]["EndTicks"] -= 1
    with pytest.raises(ValueError, match="verschilt"):
        segmentbron.lees_set(jf, [item()], True, False)
    jf.kandidaat["publication"] = "shadow"
    jf.publiek = {"TotalRecordCount": 0, "Items": []}
    kandidaten, gepubliceerd = segmentbron.lees_set(jf, [item()], True, True)
    assert len(kandidaten[PAD]) == 2 and gepubliceerd[PAD] == []
    jf.publiek["TotalRecordCount"] = 1
    with pytest.raises(ValueError, match="onvolledig"):
        segmentbron.lees_set(jf, [item()], False, False)


def test_lezer_op_lokale_http_simulator_weigert_ontbrekend_recht():
    class Antwoord(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - callback van de standaardbibliotheek
            code, data = 200, PUBLIEK
            if self.path == f"/media/v1/segments/{ITEM}?view=candidate":
                code = 200 if self.headers.get("X-Proefrol") == "editor" else 403
                data = KANDIDAAT if code == 200 else {}
            elif self.path != f"/MediaSegments/{ITEM}":
                code, data = 404, {}
            self.send_response(code)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def log_message(self, *_):
            pass

    with HTTPServer(("localhost", 0), Antwoord) as server:
        draad = threading.Thread(target=server.serve_forever, daemon=True)
        draad.start()
        try:
            jf = Jellyfin(f"http://localhost:{server.server_port}")
            jf.admin = Http(jf.url)
            with pytest.raises(HttpFout) as fout:
                segmentbron.lees_item(jf, ITEM, 50 * TICKS, kandidaat=True)
            assert fout.value.status == 403
            jf.admin = Http(jf.url, {"X-Proefrol": "editor"})
            kandidaat, publiek = segmentbron.lees_item(jf, ITEM, 50 * TICKS, kandidaat=True)
            assert kandidaat == publiek and len(publiek) == 2
        finally:
            server.shutdown()
            draad.join()


def test_gepaarde_bootstrap_per_aflevering_en_ondergrens():
    a = {"intro": {"a": (1, 2), "b": (1, 2)}}
    b = {"intro": {"a": (1, 2), "b": (0, 2)}}
    vast = gepaard(a, b, 100)
    assert vast == gepaard(a, b, 100)
    assert (vast["intro"]["verschil_f1"], vast["intro"]["onder"], vast["intro"]["boven"]) == (0.5, 0, 1)
    assert gepaard(b, b, 100)["intro"]["boven"] == 0
    with pytest.raises(ValueError, match="gepaard"):
        gepaard(a, {"intro": {}}, 100)


def test_manifest_bindt_de_bestanden_en_weigert_vervanging(tmp_path, monkeypatch):
    data, vast = tmp_path / "set", tmp_path / "vast"
    (data / PAD).parent.mkdir(parents=True)
    (data / PAD).write_bytes(b"synthetisch")
    (data / "grondwaarheid.json").write_text(json.dumps({"afleveringen": [item()]}))
    m = manifest.maak(data, recept="f6-segmenten", versie="2", schaal="vol", seed=7, parameters={}, ffmpeg={}, bronnen=[],
                      licenties=["synthetisch"], beperkt=False, aantallen={"intro": 1})
    manifest.schrijf(data, m)
    bevroren, _ = manifest.bevries(m, vast)
    monkeypatch.setattr(segmenten, "BEVROREN", vast)
    sha = manifest.sha256_bestand(bevroren)
    assert segmenten.bevroren_set(data, sha) == [item()]
    with pytest.raises(ValueError, match="manifest-sha256"):
        segmenten.bevroren_set(data, "verkeerde selectie")
    (data / PAD).write_bytes(b"andere set")
    with pytest.raises(ValueError, match="inhoud|Inhoud"):
        segmenten.bevroren_set(data, sha)


def test_meetcommando_drie_runs_en_machinelast(tmp_path, monkeypatch):
    monkeypatch.setattr(segmenten.meetslot, "loadavg", lambda: (1.0, 1.0, 1.0))
    fout = tmp_path / "ontbreekt.json"
    uit = tmp_path / "rapport.json"
    args = ["meet", "--manifest-sha256", "fixture", "--set", str(tmp_path), "--profielen", "stock-standaard",
            "--baseline", str(fout), "--uit", str(uit)]
    assert segmenten.main(args) == 3 and not uit.exists()
    fout.write_text("{}")
    monkeypatch.setattr(segmenten, "voorwaarden", lambda _: [])
    monkeypatch.setattr(segmenten, "bevroren_set", lambda *_: [item()])
    monkeypatch.setattr(segmenten.meetslot, "exclusief_slot", nullcontext)
    monkeypatch.delenv("STACKSLOT", raising=False)
    monkeypatch.setattr(segmenten.meetslot, "actieve_zware_sloten", lambda: [])
    last = SimpleNamespace(geldig=True, loadavg_na=[1], als_dict=lambda: {"geldig": True})
    monkeypatch.setattr(segmenten.meetslot, "run", lambda *a, **kw: nullcontext(last))
    monkeypatch.setattr(segmenten, "stock_sessie", lambda *a: nullcontext((Testserver(), "test", {})))
    assert segmenten.main(args) == 0
    eerste = uit.read_bytes()
    assert segmenten.main(args) == 0 and uit.read_bytes() == eerste
    meting = json.loads(eerste)["profielen"]["stock-standaard"]
    assert len(meting["runs"]) == 3 and meting["scores"]["per_type"]["intro"]["n"] == 1
    monkeypatch.setattr(segmenten.meetslot, "loadavg", lambda: (4.01, 1, 1))
    assert segmenten.main(args) == 3
