"""Gezamenlijke desktop-spike (B03 2.0 §10.14, analyse 5 §4): jellyfin-desktop 2.0.0 onder Xvfb in een container.

De broncode komt **alleen-lezen** uit ``jelly-leon-clients/desktop`` (forkversie 2.0.0-jl.0) en wordt gebouwd met de
bouwomgeving van die repo (``tools/clients/bouwverificatie/desktop.Dockerfile``) onder ``docker-build.lock``; de uitvoer
staat buiten elke repo. Daarna draait de app in een container met Xvfb, libmpv op ``vaapi-copy`` en
``--remote-debugging-port``; ``desktop/cdp.mjs`` bestuurt hem via ruwe CDP. Geslaagd = de server ziet de desktop-sessie
hero.mp4 afspelen (PositionTicks ≥ 2 s). Anders: **Geblokkeerd** met de gemeten reden (acceptatie B03-016).

    python -m b03h desktop [--uit …json] [--stap bouw|draai|alles]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import traceback
import urllib.request
from pathlib import Path
from typing import Any

from . import meetslot
from .stock import GEBRUIKER, STOCK_IMAGE, WACHTWOORD, WERK, StockServer, docker, render_gid

REPO = Path(__file__).resolve().parents[3]
CLIENTS = REPO.parent / "jelly-leon-clients"
DOCKERFILE = CLIENTS / "tools/clients/bouwverificatie/desktop.Dockerfile"
IMAGE = "jelly-leon-b03-016/desktop-spike:dev"
UIT = WERK / "desktop-bouw"
CDP_POORT = 9333
APP_LOG = "/tmp/app.log"  # noqa: S108 - pad binnen de wegwerpcontainer
HERO = "/media/movies/hero/hero.mp4"


def log(tekst: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {tekst}", flush=True)


def bouw() -> dict[str, Any]:
    if not DOCKERFILE.exists():
        raise RuntimeError(f"{DOCKERFILE} ontbreekt (jelly-leon-clients niet naast deze repo)")
    commit = subprocess.run(["git", "-C", str(CLIENTS), "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    t0 = time.monotonic()
    with meetslot.exclusief_slot("docker-build.lock", bij_wachten=log):
        b = subprocess.run(["nice", "-n", "10", "docker", "buildx", "build", "--load", "-f", str(DOCKERFILE), "-t", IMAGE,
                            str(CLIENTS / "desktop")], capture_output=True, text=True, check=False, timeout=3600)
    if b.returncode != 0:
        raise RuntimeError(f"bouwimage faalde: {b.stderr[-800:]}")
    UIT.mkdir(parents=True, exist_ok=True)
    c = subprocess.run(["nice", "-n", "10", "docker", "run", "--rm", "--network", "none", "--cpus", "4", "--memory", "6g",
                        "--security-opt", "no-new-privileges", "--cap-drop", "ALL", "--user", f"{os.getuid()}:{os.getgid()}",
                        "-v", f"{CLIENTS / 'desktop'}:/src:ro", "-v", f"{UIT}:/out", IMAGE, "bash", "-euo", "pipefail", "-c",
                        "cmake -S /src -B /out/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DUSE_STATIC_MPVQT=ON >/out/cmake.log 2>&1 && "
                        "cmake --build /out/build -j 4 >/out/build.log 2>&1"],
                       capture_output=True, text=True, check=False, timeout=5400)
    binary = next(iter(UIT.glob("build/**/jellyfin-desktop")), None)
    if c.returncode != 0 or binary is None:
        staart = (UIT / "build.log").read_text(errors="replace")[-800:] if (UIT / "build.log").exists() else c.stderr[-800:]
        raise RuntimeError(f"compileren faalde: {staart}")
    return {"clients_commit": commit, "bouw_s": round(time.monotonic() - t0), "binary": str(binary.relative_to(UIT))}


def draai(uitmap: Path, resultaat: dict[str, Any]) -> dict[str, Any]:
    binary = next(iter(UIT.glob("build/**/jellyfin-desktop")), None)
    if binary is None:
        raise RuntimeError("geen gebouwde jellyfin-desktop; eerst --stap bouw")
    koppelingen = {"/media/movies/hero": "bron/blender/hero"}
    with meetslot.exclusief_slot(bij_wachten=log):
        server = StockServer("desktop", koppelingen=koppelingen, gpu=False).start()
        naam = "b03016-desktop-app"  # niet gelijk aan de stockserver (die heet b03016-desktop)
        try:
            server.inrichten([("Films", "movies", ["/media/movies"])])
            assert server.jf
            hero = next(i for i in server.jf.items() if i["Path"] == HERO)
            docker("rm", "-f", naam, check=False)
            gid = render_gid()
            docker("run", "-d", "--name", naam, "--network", "host", "--memory", "3g", "--security-opt", "no-new-privileges",
                   "--device", "/dev/dri/renderD128", *(["--group-add", str(gid)] if gid else []), "-v", f"{UIT}:/out:ro",
                   "-e", "HOME=/tmp", IMAGE, "sleep", "infinity")
            apt = docker("exec", "-u", "0", naam, "sh", "-c", "apt-get update -qq >/dev/null && DEBIAN_FRONTEND=noninteractive "
                         "apt-get install -y -qq --no-install-recommends xvfb xauth mesa-va-drivers intel-media-va-driver "
                         "fonts-dejavu-core qml6-module-qtwebengine qml6-module-qtwebchannel qml6-module-qtquick-controls "
                         "qml6-module-qtquick-window qml6-module-qtqml-workerscript qml6-module-qtquick-templates >/dev/null",
                         check=False, timeout=900)
            # Runtime-QML-modules uit desktop/debian/control (Depends); zonder deze faalt de app met
            # "Failed to parse application engine script" (gemeten in de eerste spike-poging).
            resultaat["runtime_apt"] = "ok" if apt.returncode == 0 else apt.stderr[-300:]
            app = (f"Xvfb :99 -screen 0 1600x900x24 >/tmp/xvfb.log 2>&1 & sleep 2; "
                   f"DISPLAY=:99 QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox LIBVA_DRIVER_NAME=iHD "
                   f"/out/{binary.relative_to(UIT)} --remote-debugging-port {CDP_POORT} >{APP_LOG} 2>&1")
            subprocess.run(["docker", "exec", "-d", "-u", f"{os.getuid()}:{os.getgid()}", naam, "sh", "-c", app], check=True)
            cdp = f"http://127.0.0.1:{CDP_POORT}"
            klaar = False
            for _ in range(60):
                try:
                    with urllib.request.urlopen(f"{cdp}/json/version", timeout=2) as r:  # noqa: S310 - lokaal
                        resultaat["cdp_versie"] = json.loads(r.read()).get("Browser")
                        klaar = True
                        break
                except OSError:
                    time.sleep(2)
            if not klaar:
                raise RuntimeError("CDP antwoordt niet: " + docker("exec", naam, "tail", "-30", APP_LOG, check=False).stdout[-800:])
            web = Path(__file__).resolve().parents[1] / "desktop" / "cdp.mjs"
            cfg = {"cdp": cdp, "server": server.url, "gebruiker": GEBRUIKER, "wachtwoord": WACHTWOORD, "item": hero["Id"],
                   "scherm": str(uitmap / "desktop-spike.png")}
            try:
                r = subprocess.run(["node", str(web), json.dumps(cfg)], capture_output=True, text=True, timeout=420, check=False)
                resultaat["cdp"] = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"fout": r.stderr[-400:]}
            except subprocess.TimeoutExpired as fout:
                staart = fout.stderr.decode(errors="replace") if isinstance(fout.stderr, bytes) else (fout.stderr or "")
                resultaat["cdp"] = {"ok": False, "fout": "CDP-besturing liep vast (420 s)", "stappen_tot_dan": staart[-800:]}
            # Afspelen aan de serverkant controleren (de desktop speelt via libmpv, niet via een <video>-element).
            pos = []
            for _ in range(40):
                for s in server.jf.a.doe("GET", "/Sessions"):
                    if (s.get("NowPlayingItem") or {}).get("Id") == hero["Id"]:
                        pos.append(round(((s.get("PlayState") or {}).get("PositionTicks") or 0) / 1e7, 2))
                        resultaat["sessie"] = {"client": s.get("Client"), "versie": s.get("ApplicationVersion"),
                                               "methode": (s.get("PlayState") or {}).get("PlayMethod")}
                if pos and pos[-1] >= 2:
                    break
                time.sleep(1)
            resultaat["posities_s"] = pos[-5:]
        finally:
            resultaat["app_log"] = docker("exec", naam, "tail", "-25", APP_LOG, check=False).stdout[-2000:]
            staat = docker("inspect", "--format", "{{json .State}}", server.naam, check=False).stdout.strip()
            resultaat["server_staat"] = staat[:400]
            resultaat["server_log"] = server.logs(25)[-1500:]
            docker("rm", "-f", naam, check=False)
            server.verwijder()
    ok = bool(resultaat.get("posities_s")) and resultaat["posities_s"][-1] >= 2
    resultaat["status"] = "Sim-getest (spike geslaagd: hero.mp4 speelt)" if ok else "Geblokkeerd (spike niet geslaagd)"
    return resultaat


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h desktop")
    p.add_argument("--stap", choices=["bouw", "draai", "alles"], default="alles")
    p.add_argument("--uit", type=Path, default=REPO / "docs/platform-v2/test-evidence/b03-016-desktop-spike.json")
    a = p.parse_args(argv)
    uitmap = a.uit.with_suffix("")
    uitmap.mkdir(parents=True, exist_ok=True)
    document: dict[str, Any] = {"schema": "jelly-leon/b03-016-desktop-spike/1", "client": "jellyfin-desktop 2.0.0 (forkbron 2.0.0-jl.0, "
                                "jelly-leon-clients/desktop) onder Xvfb", "server": STOCK_IMAGE}
    try:
        if a.stap in ("bouw", "alles"):
            document["bouw"] = bouw()
        if a.stap in ("draai", "alles"):
            draai(uitmap, document)
    except Exception as fout:  # noqa: BLE001 - de spike rapporteert elke fout eerlijk als blokkade
        document["status"] = "Geblokkeerd (spike niet geslaagd)"
        document["reden"] = str(fout)[:1500]
        document["traceback"] = traceback.format_exc()[-1500:]
    a.uit.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(document["status"])
    return 0
