#!/usr/bin/env python3
"""Spike IStartupFilter (B03-017, ADR-0033): werkt een laag vóór routing en authenticatie uit een plugin op 12.x?

Twee wegwerpcontainers van dezelfde image op een lege datamap: één zonder en één met
JELLYLEON_SPIKE_STARTUPFILTER=1. Beide krijgen dezelfde verzoeken zonder aanmelding. De spike slaagt als

- met de schakelaar een verzoek van meer dan 1 MiB aan een pluginroute 413 payload_too_large krijgt (dus vóór de 401),
- zonder de schakelaar hetzelfde verzoek 401 krijgt (de bestaande volgorde, ADR-0030),
- al het andere (pluginroutes tot en met 1 MiB, upstream-routes met een grote body, /System/Info/Public) in beide
  runs hetzelfde antwoord geeft, en
- de server in beide runs zonder foutregel over de plugin start.

Alleen stdlib; containers op 127.0.0.1 met --cap-drop ALL en zonder schrijfbare media. Dit is een simulatie op de
ontwikkelmachine of in CI, geen meting op een echte NAS.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

E2E = Path(__file__).resolve().parent
REPO = E2E.parents[2]
sys.path.insert(0, str(REPO / "tools" / "b03-harnas"))
sys.path.insert(0, str(E2E))

from b03h.jfapi import Http, wacht_klaar  # noqa: E402
from plugin_proef import PLUGIN_DLL, docker, vrije_poort  # noqa: E402

SCHAKELAAR = "JELLYLEON_SPIKE_STARTUPFILTER"
MIB = 1048576
FOUTREGEL = re.compile(r"\[(ERR|FTL)\].*(JellyLeon|IStartupFilter)", re.IGNORECASE)
KOP = {"Authorization": 'MediaBrowser Client="jl-spike", Device="spike", DeviceId="jl-spike-startupfilter", Version="1.0"'}


def vulling(lengte: int) -> bytes:
    """Geldige JSON van precies `lengte` bytes (een object met spaties), zodat alleen de grootte het verschil maakt."""
    kern = b'{"Username":"jl-spike","Pw":"x"'
    return kern + b" " * (lengte - len(kern) - 1) + b"}"


def vraag(http: Http, methode: str, pad: str, body: bytes | None) -> dict[str, Any]:
    import urllib.error
    import urllib.request
    kop = {"Accept": "application/json", **KOP}
    if body is not None:
        kop["Content-Type"] = "application/json"
    verzoek = urllib.request.Request(http.basis + pad, data=body, method=methode, headers=kop)  # noqa: S310 - lokaal testadres
    try:
        with urllib.request.urlopen(verzoek, timeout=60) as antwoord:  # noqa: S310
            status, ruw, koppen = antwoord.status, antwoord.read(), dict(antwoord.headers)
    except urllib.error.HTTPError as fout:
        status, ruw, koppen = fout.code, fout.read(), dict(fout.headers or {})
    try:
        data = json.loads(ruw.decode("utf-8-sig")) if ruw else None
    except ValueError:
        data = None
    uit: dict[str, Any] = {"status": status, "code": None, "reden": None, "sleutels": None,
                           "content_type": koppen.get("Content-Type"), "cache_control": koppen.get("Cache-Control")}
    if isinstance(data, dict):
        uit["sleutels"] = sorted(data)
        if isinstance(data.get("code"), str):
            uit["code"] = data["code"]
            details = data.get("details")
            uit["reden"] = details.get("reason") if isinstance(details, dict) else None
    return uit


VERZOEKEN: tuple[tuple[str, str, str, int | None], ...] = (
    ("connector_te_groot", "POST", "/connector/v1/propose", MIB + 1),
    ("connector_precies_1mib", "POST", "/connector/v1/propose", MIB),
    ("connector_klein", "POST", "/connector/v1/propose", 64),
    ("connector_zonder_body", "GET", "/connector/v1/health", None),
    ("media_te_groot", "PUT", "/media/v1/modules/devices", MIB + 1),
    ("media_hoofdletters_te_groot", "PUT", "/MEDIA/V1/modules/devices", MIB + 1),
    ("media_klein", "PUT", "/media/v1/modules/devices", 64),
    ("upstream_te_groot", "POST", "/Users/AuthenticateByName", MIB + 1),
    ("upstream_klein", "POST", "/Users/AuthenticateByName", 64),
    ("upstream_publiek", "GET", "/System/Info/Public", None),
)
TE_GROOT_OP_PLUGIN = ("connector_te_groot", "media_te_groot", "media_hoofdletters_te_groot")


def meet(naam: str, image: str, werk: Path, plugin_map: Path | None, aan: bool) -> dict[str, Any]:
    map_ = werk / naam
    (map_ / "config").mkdir(parents=True)
    (map_ / "cache").mkdir()
    if plugin_map is not None:
        doel = map_ / "config" / "plugins" / "JellyLeon_0.1.0.0"
        doel.mkdir(parents=True)
        shutil.copy2(plugin_map / PLUGIN_DLL, doel / PLUGIN_DLL)
    poort = vrije_poort()
    container = f"jl-sf-{naam}-{os.getpid()}"
    extra = ["-e", f"{SCHAKELAAR}=1"] if aan else []
    docker("run", "-d", "--name", container, "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--memory", "2g", "-e", "TZ=UTC", *extra,
           "-p", f"127.0.0.1:{poort}:8096", "-v", f"{map_ / 'config'}:/config", "-v", f"{map_ / 'cache'}:/cache", image)
    try:
        info = wacht_klaar(f"http://127.0.0.1:{poort}", timeout=300)
        http = Http(f"http://127.0.0.1:{poort}")
        antwoorden = {id_: vraag(http, methode, pad, None if lengte is None else vulling(lengte))
                      for id_, methode, pad, lengte in VERZOEKEN}
    finally:
        docker("stop", "-t", "60", container, check=False)
        uitvoer = docker("logs", container, check=False)
        docker("rm", "-f", container, check=False)
    log = (uitvoer.stdout or "") + (uitvoer.stderr or "")
    logmap = map_ / "config" / "log"
    if logmap.exists():
        log += "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(logmap.glob("*")) if p.is_file())
    return {"server": {"versie": info.get("Version"), "naam": info.get("ProductName")}, "antwoorden": antwoorden,
            "foutregels": sorted({r.strip()[:300] for r in log.splitlines() if FOUTREGEL.search(r)})}


def beoordeel(uit: dict[str, Any], aan: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """De uitspraken van de spike: (naam, geslaagd, detail)."""
    a_uit, a_aan = uit["antwoorden"], aan["antwoorden"]
    regels: list[tuple[str, bool, str]] = []
    for id_ in TE_GROOT_OP_PLUGIN:
        u, a = a_uit[id_], a_aan[id_]
        regels.append((f"zonder schakelaar: {id_} → 401 unauthorized (volgorde ADR-0030)",
                       (u["status"], u["code"]) == (401, "unauthorized"), f"HTTP {u['status']} {u['code']} ({u['reden']})"))
        goed = (a["status"], a["code"]) == (413, "payload_too_large") and a["sleutels"] == ["code", "details", "message", "trace_id"]
        goed = goed and a["content_type"] == "application/json; charset=utf-8" and a["cache_control"] == "no-store"
        regels.append((f"met schakelaar: {id_} → 413 payload_too_large vóór de authenticatie", goed,
                       f"HTTP {a['status']} {a['code']}, velden {a['sleutels']}, {a['content_type']}, {a['cache_control']}"))
    for id_, _methode, _pad, _lengte in VERZOEKEN:
        if id_ in TE_GROOT_OP_PLUGIN:
            continue
        regels.append((f"{id_}: zelfde antwoord met en zonder schakelaar", a_uit[id_] == a_aan[id_],
                       f"uit {a_uit[id_]['status']} {a_uit[id_]['code']} / aan {a_aan[id_]['status']} {a_aan[id_]['code']}"))
    for id_ in ("connector_precies_1mib", "connector_klein", "connector_zonder_body", "media_klein"):
        a = a_aan[id_]
        regels.append((f"met schakelaar: {id_} → 401 unauthorized (de pluginroute zelf antwoordt)",
                       (a["status"], a["code"]) == (401, "unauthorized"), f"HTTP {a['status']} {a['code']} ({a['reden']})"))
    regels.append(("upstream_publiek → 200 in beide runs", a_uit["upstream_publiek"]["status"] == 200
                   and a_aan["upstream_publiek"]["status"] == 200, ""))
    regels.append(("upstream_te_groot krijgt geen 413 van de plugin", a_aan["upstream_te_groot"]["code"] != "payload_too_large",
                   f"HTTP {a_aan['upstream_te_groot']['status']}"))
    for naam, run in (("zonder", uit), ("met", aan)):
        regels.append((f"{naam} schakelaar: geen foutregel over de plugin of het filter in de log", not run["foutregels"],
                       "; ".join(run["foutregels"])[:400]))
    return regels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spike IStartupFilter (B03-017, ADR-0033) in twee wegwerpcontainers.")
    parser.add_argument("--image", required=True, help="stock 12.x met --plugin-map, of de jelly-leon-image")
    parser.add_argument("--plugin-map", type=Path, default=None, help="map met de gebouwde plugin-DLL; weglaten als de image hem meelevert")
    parser.add_argument("--werkmap", default=None)
    parser.add_argument("--rapport", type=Path)
    args = parser.parse_args(argv)
    if args.plugin_map is not None and not (args.plugin_map / PLUGIN_DLL).is_file():
        print(f"[FOUT] {args.plugin_map / PLUGIN_DLL} bestaat niet", file=sys.stderr)
        return 2
    werk = Path(tempfile.mkdtemp(prefix="jl-startupfilter-", dir=args.werkmap))
    try:
        uit = meet("uit", args.image, werk, args.plugin_map, aan=False)
        aan = meet("aan", args.image, werk, args.plugin_map, aan=True)
    finally:
        shutil.rmtree(werk, ignore_errors=True)
    regels = beoordeel(uit, aan)
    for naam, ok, detail in regels:
        print(f"[{'OK' if ok else 'FOUT'}] {naam}" + (f" — {detail}" if detail else ""), flush=True)
    geslaagd = all(ok for _naam, ok, _detail in regels)
    rapport = {"schema": "jelly-leon/startupfilter-spike/1", "image": args.image, "schakelaar": SCHAKELAAR,
               "soort": "Sim-getest (wegwerpcontainers op 127.0.0.1; geen echte NAS, Hub of clients)",
               "uit": uit, "aan": aan, "uitspraken": [{"naam": n, "geslaagd": ok, "detail": d} for n, ok, d in regels],
               "spike_geslaagd": geslaagd}
    if args.rapport:
        args.rapport.write_text(json.dumps(rapport, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RESULTAAT: {'GESLAAGD' if geslaagd else 'MISLUKT'} ({sum(ok for _n, ok, _d in regels)}/{len(regels)} uitspraken)")
    return 0 if geslaagd else 1


if __name__ == "__main__":
    raise SystemExit(main())
