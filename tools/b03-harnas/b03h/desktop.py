"""Desktoprooktest met een bestaande clientbuild, Xvfb en een eigen Jellyfin-testserver (B03-016, JLT-63)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import uuid
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from . import meetslot
from .stock import STOCK_IMAGE, WERK, StockServer, docker

REPO = Path(__file__).resolve().parents[3]
BINARY = Path("build/src/jellyfin-desktop")
CLIENTBUILD = REPO.parent / "jelly-leon-clients/.bouw/desktop"
DESKTOP_IMAGE = "jelly-leon-clients/desktop-test:dev"
# Dezelfde gepinde Node-runtime als de webbouw in deploy/allinone/Dockerfile.
NODE_IMAGE = "docker.io/library/node:24.22.2-bookworm-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9"
HERO = "/media/movies/hero/hero.mp4"
CDP_JS = REPO / "tools/b03-harnas/desktop/cdp.mjs"
APP = ("Xvfb :99 -screen 0 1600x900x24 >/dev/null 2>&1 & sleep 2; "
       "exec /out/build/src/jellyfin-desktop --remote-debugging-port 9222")


class DesktopFout(RuntimeError):
    """Diagnose zonder accountgegevens of ruwe serveruitvoer, geschikt voor het bewijs."""


def beoordeel(cdp: dict[str, Any]) -> str:
    """Geef de eerste ontbrekende of onjuiste meting terug. Alle posities zijn in seconden."""
    if cdp.get("chunkloaderror") is True:
        return "ChunkLoadError waargenomen"
    if not cdp.get("webclient_geladen"):
        return cdp.get("fout") or "webclient van de testserver niet geladen"
    if not cdp.get("ingelogd"):
        return cdp.get("fout") or "niet ingelogd"
    if 0 in cdp.get("voortgang_hervatten_s", []) or any(p == 0 for _, p in cdp.get("hervatten", [])):
        return "positie 0 gemeld bij hervatten"
    if cdp.get("fout"):
        return cdp["fout"]
    if cdp.get("beginpunt_s") != 0:
        return "beginpositie van het nieuwe testaccount niet bevestigd"
    if not cdp.get("voortgang_hervatten_s"):
        return "geen voortgangsmelding van de desktop bij hervatten"
    for fase in ("afspelen", "hervatten"):
        rij = cdp.get(fase, [])
        if len(rij) < 2 or rij[-1][1] - rij[0][1] < 2 or any(b[1] < a[1] for a, b in zip(rij, rij[1:], strict=False)):
            return f"{fase}: geen oplopende afspeelpositie van minstens twee seconden"
    punt = cdp.get("hervatpunt_s")
    na = cdp.get("eindpunt_s")
    if punt is None or punt <= 0 or abs(punt - cdp["afspelen"][-1][1]) > 5:
        return "opgeslagen hervatpunt wijkt af van de eerste afspeelsessie"
    tijd, eerste = cdp["hervatten"][0]
    if not punt - 3 <= eerste <= punt + tijd + 3:
        return "desktop begon buiten het opgeslagen hervatpunt"
    if na is None or na <= punt or abs(na - cdp["hervatten"][-1][1]) > 5:
        return "voortgang na hervatten niet bewaard"
    if cdp.get("chunkloaderror") is not False:
        return "controle op ChunkLoadError onvolledig"
    return ""


def draai(build: Path, image: str, desktop_image: str, uitmap: Path, resultaat: dict[str, Any]) -> None:
    WERK.mkdir(parents=True, exist_ok=True)
    with meetslot.exclusief_slot(bij_wachten=lambda s: print(s, flush=True)), ExitStack() as stapel:
        werk = Path(stapel.enter_context(tempfile.TemporaryDirectory(dir=WERK)))
        netwerk = docker("network", "create", "--internal", "--ipv6=false", "--opt", "com.docker.network.bridge.inhibit_ipv4=true",
                         f"b03016-desktop-{uuid.uuid4().hex}").stdout.strip()
        stapel.callback(docker, "network", "rm", netwerk)
        server = stapel.enter_context(StockServer("desktop", image=image, werk=werk, gpu=False, cpus="2",
                                                  koppelingen={"/media/movies/hero": "bron/blender/hero"}))
        # De fork controleert de opslagrechten. Elke run heeft al een eigen lege werkmap.
        for sub in ("config", "cache"):
            (server.map / sub).mkdir(parents=True, mode=0o700)
        server.start(schoon=False)
        server.inrichten([("Films", "movies", ["/media/movies"])])
        assert server.jf
        jf = server.jf
        hero = next((i for i in jf.items() if i.get("Path") == HERO), None)
        if not hero:
            raise DesktopFout("hero.mp4 niet gevonden in het testcorpus")
        # hero.mp4 duurt korter dan de standaard ondergrens van vijf minuten voor het bewaren van hervatpunten.
        config = jf.a.doe("GET", "/System/Configuration")
        jf.a.doe("POST", "/System/Configuration", body={**config, "MinResumeDurationSeconds": 0})
        kijker = "desktopkijker"
        wachtwoord = secrets.token_urlsafe(24)
        uid = jf.gebruiker(kijker, wachtwoord)
        resultaat.update(server_image_id=server.digest(), server_versie=server.info["Version"], min_hervatduur_s=0)
        docker("network", "connect", "--alias", "testserver", netwerk, server.container_id)
        beperkt = ["--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
        app = docker("run", "-d", "--network", netwerk, *beperkt, "--shm-size", "1g", "--memory", "2g", "--cpus", "2",
                     "-e", "HOME=/tmp", "-e", "DISPLAY=:99", "-e", "QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox",
                     "-v", f"{build}:/out:ro", desktop_image, "sh", "-c", APP).stdout.strip()
        stapel.callback(docker, "rm", "-f", "-v", app)
        image_id, shm_bytes = docker("inspect", "--format", "{{.Image}} {{.HostConfig.ShmSize}}", app).stdout.split()
        resultaat.update(desktop_image_id=image_id, shm_bytes=int(shm_bytes))
        # De besturing deelt uitsluitend de netwerkruimte van de desktop. CDP heeft geen hostpoort.
        stuurder = docker("create", "-i", "--network", f"container:{app}", *beperkt, "--memory", "256m", "--cpus", "1",
                          "-v", f"{CDP_JS}:/cdp.mjs:ro", "-v", f"{uitmap}:/bewijs", NODE_IMAGE, "node", "/cdp.mjs").stdout.strip()
        stapel.callback(docker, "rm", "-f", "-v", stuurder)
        cfg = {"gebruiker": kijker, "wachtwoord": wachtwoord, "uid": uid, "item": hero["Id"], "autorisatie": jf.a.headers["Authorization"]}
        proces = subprocess.run(["docker", "start", "-a", "-i", stuurder], input=json.dumps(cfg), text=True,
                                capture_output=True, timeout=360, check=False)
        if proces.returncode or not proces.stdout.strip():
            raise DesktopFout(f"CDP-besturing eindigde zonder meting (exit {proces.returncode})")
        resultaat["cdp"] = json.loads(proces.stdout)
        if not resultaat["cdp"].get("webclient_geladen"):
            # Alleen herkenbare startfouten uit de app bewaren, nooit ruwe logs of adressen.
            logs = docker("logs", "--tail", "80", app, check=False)
            resultaat["app_diagnose"] = [term for term in ("Failed to parse application engine script", "error while loading shared libraries",
                                                           "Could not connect to display", "DevTools listening")
                                         if term.lower() in (logs.stdout + logs.stderr).lower()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h desktop")
    p.add_argument("--stap", choices=["bouw", "draai", "alles"], default="alles",
                   help="bouw controleert de bestaande clientbuild; draai en alles voeren de rooktest uit")
    p.add_argument("--build", type=Path, help="uitvoermap van make desktop-bouw in jelly-leon-clients")
    p.add_argument("--image", default=STOCK_IMAGE, help="image voor de wegwerptestserver")
    p.add_argument("--desktop-image", default=DESKTOP_IMAGE, help="runtime met Xvfb uit het doel test van de clientrepo")
    p.add_argument("--uit", type=Path, default=REPO / "docs/platform-v2/test-evidence/b03-016-desktop-spike.json")
    a = p.parse_args(argv)
    build = a.build or (CLIENTBUILD if (CLIENTBUILD / BINARY).is_file() else WERK / "desktop-bouw")
    document: dict[str, Any] = {"schema": "jelly-leon/b03-016-desktop-spike/2", "client": "Jellyfin Desktop onder Xvfb",
                                "server": a.image, "stap": a.stap, "begin": meetslot.nu()}
    try:
        if not (build / BINARY).is_file() or not os.access(build / BINARY, os.X_OK):
            raise DesktopFout("uitvoerbare desktopbuild ontbreekt; de clientbaan levert make desktop-bouw")
        with (build / BINARY).open("rb") as bestand:
            document["bouw"] = {"binary": str(BINARY), "sha256": hashlib.file_digest(bestand, "sha256").hexdigest()}
        if a.stap == "bouw":
            document["status"] = "Bouw gecontroleerd"
        else:
            uitmap = a.uit.resolve().with_suffix("")
            uitmap.mkdir(parents=True, exist_ok=True)
            draai(build.resolve(), a.image, a.desktop_image, uitmap, document)
            reden = beoordeel(document["cdp"])
            if reden:
                raise DesktopFout(reden)
            document["status"] = "Sim-getest"
    except DesktopFout as fout:
        document.update(status="Sim-mislukt", reden=str(fout))
    except subprocess.CalledProcessError as fout:
        document.update(status="Sim-mislukt", reden=f"Docker-opdracht {fout.cmd[1]} gaf exitcode {fout.returncode}")
    except subprocess.TimeoutExpired:
        document.update(status="Sim-mislukt", reden="tijdlimiet van de lokale proef verstreken")
    except (OSError, ValueError, RuntimeError) as fout:
        # Onverwachte API-antwoorden kunnen URL's of accountgegevens bevatten.
        document.update(status="Sim-mislukt", reden=f"lokale proef onderbroken ({type(fout).__name__})")
    document["eind"] = meetslot.nu()
    a.uit.parent.mkdir(parents=True, exist_ok=True)
    a.uit.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(document["status"], flush=True)
    return int(document["status"] == "Sim-mislukt")
