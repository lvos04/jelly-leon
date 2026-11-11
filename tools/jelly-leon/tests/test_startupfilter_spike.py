"""De beoordeling van de IStartupFilter-spike (ADR-0033): zuivere functies, zonder containers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

import startupfilter_spike as spike  # noqa: E402


def _antwoord(status: int, code: str | None = None, reden: str | None = None) -> dict:
    fout = code is not None
    return {"status": status, "code": code, "reden": reden,
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
    import json
    for lengte in (64, spike.MIB, spike.MIB + 1):
        body = spike.vulling(lengte)
        assert len(body) == lengte
        assert json.loads(body) == {"Username": "jl-spike", "Pw": "x"}


def test_spike_slaagt_alleen_met_413_voor_401_en_verder_gelijke_antwoorden() -> None:
    uit = _run(_antwoord(401, "unauthorized", "not_linked"))
    aan = _run(_antwoord(413, "payload_too_large"))
    assert all(ok for _naam, ok, _detail in spike.beoordeel(uit, aan))


def test_spike_mislukt_als_de_laag_niets_doet() -> None:
    uit = _run(_antwoord(401, "unauthorized", "not_linked"))
    regels = spike.beoordeel(uit, _run(_antwoord(401, "unauthorized", "not_linked")))
    mislukt = [naam for naam, ok, _detail in regels if not ok]
    assert len(mislukt) == len(spike.TE_GROOT_OP_PLUGIN)
    assert all("413 payload_too_large" in naam for naam in mislukt)


def test_spike_mislukt_als_een_upstream_route_verandert_of_de_log_een_fout_toont() -> None:
    uit = _run(_antwoord(401, "unauthorized", "not_linked"))
    aan = _run(_antwoord(413, "payload_too_large"))
    aan["antwoorden"]["upstream_te_groot"] = _antwoord(413, "payload_too_large")
    aan["foutregels"] = ["[ERR] JellyLeon: fout"]
    mislukt = [naam for naam, ok, _detail in spike.beoordeel(uit, aan) if not ok]
    assert any(naam.startswith("upstream_te_groot: zelfde antwoord") for naam in mislukt)
    assert any("krijgt geen 413 van de plugin" in naam for naam in mislukt)
    assert any(naam.startswith("met schakelaar: geen foutregel") for naam in mislukt)


def test_foutregel_herkent_alleen_fouten_over_de_plugin_of_het_filter() -> None:
    assert spike.FOUTREGEL.search("[10:00:00] [ERR] [1] Jellyfin.Plugin.JellyLeon.Core: mislukt")
    assert spike.FOUTREGEL.search("[10:00:00] [FTL] [1] Main: IStartupFilter gooide een fout")
    assert not spike.FOUTREGEL.search("[10:00:00] [INF] [1] Jellyfin.Plugin.JellyLeon: geladen")
    assert not spike.FOUTREGEL.search("[10:00:00] [ERR] [1] Emby.Server: iets anders")
