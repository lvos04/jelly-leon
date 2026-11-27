"""Losse delen van baseline/legacy/rapport zonder Docker: transcodelog lezen, legacy-meting tegen een nepserver, rapport."""

from __future__ import annotations

import http.server
import json
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from b03h import baseline, bewijs, legacy, meetslot, rapport, statistiek, stock

LOG = "\n".join([
    '{"Protocol":0,"Id":"x"}',
    '/usr/lib/jellyfin-ffmpeg/ffmpeg -analyzeduration 200M -init_hw_device vaapi=va:/dev/dri/renderD128 -hwaccel vaapi '
    '-i file:"/media/x.mp4" -codec:v:0 h264_qsv -vf "setparams=color_primaries=bt2020,tonemap_vaapi=format=nv12" -f hls x.m3u8',
    "frame=  100 fps=0.0 q=-0.0 size=N/A time=00:00:03.20 bitrate=N/A speed=6.4x elapsed=0:00:00.50",
    "frame= 1797 fps=390 q=-0.0 Lsize=N/A time=00:00:29.95 bitrate=N/A speed=6.53x elapsed=0:00:04.58",
]) + "\n"


def test_transcodelog_lezen(tmp_path: Path):
    pad = tmp_path / "FFmpeg.Transcode-x.log"
    pad.write_text(LOG, encoding="utf-8")
    info = baseline._lees_transcodelog(pad)
    assert info["snelheid_x"] == 6.53
    assert info["media_s"] == pytest.approx(29.95)
    assert info["video_encoder"] == "h264_qsv"
    assert info["tonemap"] == "tonemap_vaapi"
    assert info["hwaccel"] == "vaapi"


def test_a5_set_heeft_25_items_en_extra_set_2():
    assert len(baseline.A5_SET) == 25 and len(set(baseline.A5_SET)) == 25
    assert len(baseline.EXTRA_SET) == 2 and not set(baseline.EXTRA_SET) & set(baseline.A5_SET)


@pytest.mark.parametrize("geldig_bij_derde", [True, False])
def test_drie_pogingen_bij_te_hoge_last(monkeypatch: pytest.MonkeyPatch, geldig_bij_derde: bool):
    uitslagen = iter([False, False, geldig_bij_derde])

    def meet(systeem, r, containers):
        geldig = next(uitslagen)
        return nullcontext(meetslot.RunLast(systeem, r, "t", geldig=geldig, reden="" if geldig else "te hoge last"))

    monkeypatch.setattr(meetslot, "wacht_op_rust", lambda max_wacht: 0)
    monkeypatch.setattr(meetslot, "run", meet)
    if geldig_bij_derde:
        last, waarde, ongeldig = baseline.geldige_run("stock-best", 0, [], lambda: 42)
        assert last.geldig and waarde == 42
        assert [p["poging"] for p in ongeldig] == [1, 2]
    else:
        with pytest.raises(baseline.GeenGeldigeRun) as fout:
            baseline.geldige_run("stock-best", 0, [], lambda: 42)
        assert [p["poging"] for p in fout.value.pogingen] == [1, 2, 3]
        assert all(p["last"]["reden"] == "te hoge last" for p in fout.value.pogingen)


def test_orakel_meet_beide_systemen_drie_keer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    volgorde = []
    items = [{"naam": Path(p).stem, "besluit": "DirectPlay", "orakel_ok": True} for p in baseline.A5_SET + baseline.EXTRA_SET]
    sessie = SimpleNamespace(s=SimpleNamespace(container_id="test", image="testimage"), systeem=volgorde.append,
                             web=lambda *args, **kwargs: {"items": items})
    monkeypatch.setattr(baseline, "BROWSERS", ["chromium"])
    monkeypatch.setattr(baseline, "geldige_run", lambda s, r, c, actie: (meetslot.RunLast(s, r, "t"), actie(), []))
    metingen = baseline.meet_orakel(sessie, 3, tmp_path)
    assert volgorde == [s for _, s in meetslot.ab_volgorde(["stock-standaard", "stock-best"], 3)]
    assert [(m["n"], m["runs_geldig"], m["image"]) for m in metingen] == [(25, 3, "testimage")] * 2
    items.pop(0)
    with pytest.raises(baseline.WebFout, match="onvolledige afspeelmeting"):
        baseline.meet_orakel(sessie, 3, tmp_path)


def test_herhaalsessie_toetst_ook_laatste_run():
    m = {"id": "F", "systeem": "stock-best", "soort": "proportie", "n": 10, "waarde": {"k": 5},
         "interval": {"onder": 0.3, "boven": 0.7}}
    nieuw = m | {"waarde": {"k": 5, "herhalingen_k": [6, 8]}, "runs": []}
    assert baseline.voeg_herhaalsessie_toe({"metingen": [m]}, [nieuw], {}) == ["F (stock-best)"]
    assert m["waarde"]["herhaalsessie"]["binnen_wilson_interval"] is False


def test_verplichte_rendernode_en_opruiming_bij_startfout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    opdrachten = []

    def docker(*args, **kwargs):
        opdrachten.append(args)
        if args[0] == "start":
            raise RuntimeError("testapparaat ontbreekt")
        return SimpleNamespace(stdout="eigen-testcontainer")

    monkeypatch.setattr(stock, "docker", docker)
    with stock.StockServer("proef", werk=tmp_path, koppelingen={}, gpu_verplicht=True) as server:
        with pytest.raises(RuntimeError, match="testapparaat ontbreekt"):
            server.start()
    aanmaak, start, opruimen = opdrachten
    assert aanmaak[0] == "create" and aanmaak[aanmaak.index("--device") + 1] == f"{stock.RENDER}:{stock.RENDER}"
    assert start == ("start", "eigen-testcontainer")
    assert opruimen == ("rm", "-f", "-v", "eigen-testcontainer")
    assert not server.map.exists()


class _Nep(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802 - http.server-API
        goed = 'Token="T"' in self.headers.get("Authorization", "") or "ApiKey=T" in self.path
        if "/stream" in self.path:
            self.send_response(206)
        else:
            self.send_response(200 if goed else 401)
        self.end_headers()


def test_legacy_meet_status_per_vorm():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Nep)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        uit = legacy.meet(f"http://127.0.0.1:{srv.server_address[1]}", "T", "u", "i")
    finally:
        srv.shutdown()
    assert uit["authorization_mediabrowser_token"]["system_info"] == 200
    assert uit["x_emby_token"]["system_info"] == 401
    assert uit["query_apikey_hoofdletter"]["gebruiker_items"] == 200
    assert uit["zonder_token"]["stream_statisch"] == 206
    assert "T" not in json.dumps(uit)  # geen token in het rapport


def test_rapport_regels():
    last = meetslot.RunLast("stock-standaard", 0, "t").als_dict()
    p = bewijs.metriek(id="X", functie="F5", omschrijving="o", methode="m", systeem="stock-standaard", soort="proportie",
                       image="i@sha256:" + "0" * 64, seed=None, runs=[{"last": last}], waarde={"k": 3, "herhalingen_k": [3],
                                                                                                  "herhaling_binnen_interval": True},
                       interval=statistiek.wilson(3, 25), n=25, gate="smoke-gate (n = 25)")
    r = rapport.regel(p)
    assert "3/25" in r and "smoke-gate" in r and "| ja |" in r
    c = bewijs.metriek(id="Y", functie="F5", omschrijving="o", methode="m", systeem="stock-best", soort="continu",
                       image="i@sha256:" + "0" * 64, seed=None, runs=[{"last": last}] * 3,
                       waarde={"gemiddelde": 6.5, "waarden": [6.5, 6.4, 6.6], "herhaling_binnen_interval_eerste_runs": True},
                       interval=statistiek.t_interval([6.5, 6.4, 6.6]), n=3, eenheid="× realtime")
    assert "6,5 × realtime" in rapport.regel(c)


def test_rapport_meetomstandigheden_en_herhaling_van_telling(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    image = "stock@sha256:" + "1" * 64
    run = {"last": {"loadavg_voor": [1.25, 0, 0]}}
    m = {"id": "F2-a", "systeem": "stock-best", "soort": "telling", "image": image, "n": 1, "seed": 0,
         "runs": [run], "runs_geldig": 1, "waarde": {"aantal": 2}}
    assert rapport.regel(m).endswith("| — |")
    m["waarde"]["herhaalsessie"] = {"waarde": {"aantal": 2, "herhalingen": [{"aantal": 3}]},
                                 "runs": [{"last": {"loadavg_voor": [2.5, 0, 0]}}]}
    pad = tmp_path / "baseline.json"
    pad.write_text(json.dumps({"label": "voormeting-12.4", "images": {"stock": image}, "server": {"versie": "12.4"},
                               "begin": "a", "eind": "b", "metingen": [m]}), encoding="utf-8")
    assert rapport.main([str(pad)]) == 0
    uitvoer = capsys.readouterr().out
    assert image in uitvoer
    assert "| **nee** |" in uitvoer
    assert "| F2-a | stock-best | stock | 1 | 0 | 1,25 | 2,5 |" in uitvoer
