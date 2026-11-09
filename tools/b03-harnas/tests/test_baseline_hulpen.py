"""Losse delen van baseline/legacy/rapport zonder Docker: transcodelog lezen, legacy-meting tegen een nepserver, rapport."""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

import pytest

from b03h import baseline, bewijs, legacy, meetslot, rapport, statistiek

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
