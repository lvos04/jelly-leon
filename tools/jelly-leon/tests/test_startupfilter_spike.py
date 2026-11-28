"""De beoordeling van de IStartupFilter-spike (ADR-0033): beoordeling en lokaal HTTP-vervoer."""

from __future__ import annotations

import json
import sys
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

import startupfilter_spike as spike  # noqa: E402


def _antwoord(status: int, code: str | None = None, reden: str | None = None) -> dict:
    fout = code is not None
    return {"status": status, "code": code, "reden": reden,
            "grensantwoord": status == 413 and code == "payload_too_large",
            "sleutels": ["code", "details", "message", "trace_id"] if fout else None,
            "content_type": "application/json; charset=utf-8" if fout else None,
            "cache_control": "no-store" if fout else None}


def _run(te_groot: dict) -> dict:
    antwoorden = {}
    for id_, _methode, pad, _lengte in spike.VERZOEKEN:
        if id_ in spike.TE_GROOT_OP_PLUGIN:
            antwoorden[id_] = dict(te_groot)
        elif id_ == "upstream_publiek":
            antwoorden[id_] = _antwoord(200)
        elif pad.startswith("/Users"):
            antwoorden[id_] = _antwoord(401)
        else:
            antwoorden[id_] = _antwoord(401, "unauthorized", "not_linked")
    return {"server": {}, "antwoorden": antwoorden, "foutregels": []}


def test_vulling_is_geldige_json_van_precies_de_gevraagde_lengte() -> None:
    for lengte in (64, spike.MIB, spike.MIB + 1):
        body = spike.vulling(lengte)
        assert len(body) == lengte
        assert json.loads(body) == {"Username": "jl-spike", "Pw": "x"}


def test_spike_slaagt_alleen_met_413_voor_401_en_verder_gelijke_antwoorden() -> None:
    uit = _run(_antwoord(401, "unauthorized", "not_linked"))
    aan = _run(_antwoord(413, "payload_too_large"))
    assert all(ok for _naam, ok, _detail in spike.beoordeel(uit, aan, uit))


def test_spike_mislukt_als_de_laag_niets_doet() -> None:
    uit = _run(_antwoord(401, "unauthorized", "not_linked"))
    regels = spike.beoordeel(uit, _run(_antwoord(401, "unauthorized", "not_linked")), uit)
    mislukt = [naam for naam, ok, _detail in regels if not ok]
    assert len(mislukt) == len(spike.TE_GROOT_OP_PLUGIN)
    assert all("413 payload_too_large" in naam for naam in mislukt)


def test_spike_mislukt_als_een_upstream_route_verandert_of_de_log_een_fout_toont() -> None:
    uit = _run(_antwoord(401, "unauthorized", "not_linked"))
    aan = _run(_antwoord(413, "payload_too_large"))
    aan["antwoorden"]["upstream_te_groot"] = _antwoord(413, "payload_too_large")
    aan["foutregels"] = ["[ERR] JellyLeon: fout"]
    mislukt = [naam for naam, ok, _detail in spike.beoordeel(uit, aan, uit) if not ok]
    assert any(naam.startswith("upstream_te_groot: zelfde antwoord") for naam in mislukt)
    assert any("krijgt geen 413 van de plugin" in naam for naam in mislukt)
    assert any(naam.startswith("met schakelaar: geen foutregel") for naam in mislukt)


def test_foutregel_herkent_alleen_fouten_over_de_plugin_of_het_filter() -> None:
    assert spike.FOUTREGEL.search("[10:00:00] [ERR] [1] Jellyfin.Plugin.JellyLeon.Core: mislukt")
    assert spike.FOUTREGEL.search("[10:00:00] [FTL] [1] Main: IStartupFilter gooide een fout")
    assert not spike.FOUTREGEL.search("[10:00:00] [INF] [1] Jellyfin.Plugin.JellyLeon: geladen")
    assert not spike.FOUTREGEL.search("[10:00:00] [ERR] [1] Emby.Server: iets anders")


def test_basis_url_en_chunked_worden_afzonderlijk_getoetst() -> None:
    uit = _run(_antwoord(401, "unauthorized", "not_linked"))
    aan = _run(_antwoord(413, "payload_too_large"))
    aan["antwoorden"]["connector_chunked_te_groot"] = _antwoord(404)
    regels = spike.beoordeel(uit, aan, aan)
    assert any("connector_chunked_te_groot" in naam and not ok for naam, ok, _ in regels)
    assert any("met basis-URL en schakelaar: media_te_groot" in naam and not ok for naam, ok, _ in regels)


def test_verbroken_verbinding_telt_als_mislukte_meting(monkeypatch) -> None:
    def verbroken(*args, **kwargs):
        raise ConnectionResetError

    monkeypatch.setattr(spike, "meet_http_body", verbroken)
    uit = _run(_antwoord(401, "unauthorized", "not_linked"))
    aan = _run(_antwoord(413, "payload_too_large"))
    for run in (uit, aan):
        run["antwoorden"]["upstream_klein"] = spike.vraag(spike.Http("http://localhost"), "POST", "/proef", b"{}")
    regels = spike.beoordeel(uit, aan, uit)
    assert any(not ok and "volledig HTTP-antwoord" in naam and "upstream_klein" in detail for naam, ok, detail in regels)


def test_httpclient_stuurt_dezelfde_bytes_met_lengte_en_met_chunked() -> None:
    body = spike.vulling(spike.MIB + 1)
    ontvangen = []

    class Ontvanger(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            lengte = self.headers.get("Content-Length")
            overdracht = self.headers.get("Transfer-Encoding")
            if overdracht == "chunked":
                stukken = []
                while aantal := int(self.rfile.readline(), 16):
                    stukken.append(self.rfile.read(aantal))
                    assert self.rfile.readline() == b"\r\n"
                assert self.rfile.readline() == b"\r\n"
                data = b"".join(stukken)
            else:
                data = self.rfile.read(int(lengte))
            ontvangen.append((self.path, lengte, overdracht, data))
            antwoord = json.dumps({"code": "payload_too_large", "message": "Te groot.",
                                   "details": {"max_bytes": spike.MIB}, "trace_id": str(uuid.uuid4())}).encode()
            self.send_response(413)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(antwoord)))
            self.end_headers()
            self.wfile.write(antwoord)

        def log_message(self, *args) -> None:
            pass

    with HTTPServer(("localhost", 0), Ontvanger) as server:
        draad = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        draad.start()
        try:
            http = spike.Http(f"http://localhost:{server.server_port}/jl-proef")
            for chunked in (False, True):
                assert spike.vraag(http, "POST", "/proef", body, chunked)["grensantwoord"]
        finally:
            server.shutdown()
            draad.join()
    assert ontvangen == [("/jl-proef/proef", str(len(body)), None, body), ("/jl-proef/proef", None, "chunked", body)]
