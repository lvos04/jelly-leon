"""Wegwerp-stockserver (officiële image op vaste digest) voor de baselines stock-standaard en stock-best.

Alleen op 127.0.0.1, media alleen-lezen, geen root (eigen uid + render-groep), geen Docker-socket, geen --privileged; de
GPU alleen via ``--device /dev/dri/renderD128`` (analyse 5 §7). Datamap en cache staan in een werkmap buiten de repo.
"""

from __future__ import annotations

import grp
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .corpus import CORPUS
from .jfapi import Jellyfin, wacht_klaar

STOCK_IMAGE = "docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771"
# Standaard: <WERKMAP>/.lokaal/jelly-leon-b03-016, naast de repo (parents[4] = <WERKMAP>).
WERK = Path(os.environ.get("B03_WERK", str(Path(__file__).resolve().parents[4] / ".lokaal" / "jelly-leon-b03-016")))
PROFIELEN = Path(__file__).resolve().parents[1] / "profielen"
GEBRUIKER, WACHTWOORD = "b03beheer", "B03-016-alleen-lokaal!"  # wegwerpaccount in een wegwerpcontainer op 127.0.0.1
RENDER = "/dev/dri/renderD128"

# Zelfde mediaset als analyse 5 §6.1 (25 items), plus de afgeleide gevallen voor F4/F6.
KOPPELINGEN = {
    "/media/movies/blender": "bron/blender",
    "/media/movies/jellyfin-testvideos": "bron/jellyfin-testvideos",
    "/media/series/Pioneer One": "bron/pioneer-one",
    "/media/afgeleid/series": "afgeleid/series",
    "/media/afgeleid/kwaliteit": "afgeleid/kwaliteit",
    "/media/afgeleid/formaten": "afgeleid/formaten",
}
BIBLIOTHEKEN = [
    ("Films", "movies", ["/media/movies"]),
    ("Series", "tvshows", ["/media/series"]),
    ("Afgeleid series", "tvshows", ["/media/afgeleid/series"]),
    ("Afgeleid kwaliteit", "movies", ["/media/afgeleid/kwaliteit", "/media/afgeleid/formaten"]),
]


def vrije_poort() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def render_gid() -> int | None:
    try:
        return grp.getgrnam("render").gr_gid
    except KeyError:
        return None


def docker(*args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


def profiel(naam: str) -> dict[str, Any]:
    return json.loads((PROFIELEN / f"{naam}.json").read_text(encoding="utf-8"))


class StockServer:
    def __init__(self, naam: str, *, image: str = STOCK_IMAGE, gpu: bool = True, corpus: Path = CORPUS,
                 koppelingen: dict[str, str] | None = None, werk: Path = WERK, geheugen: str = "3g",
                 webdir: Path | None = None, cpus: str | None = None, web_over: Path | None = None) -> None:
        self.naam = f"b03016-{naam}"
        self.image = image
        self.gpu = gpu and os.path.exists(RENDER)
        self.corpus = corpus
        self.koppelingen = KOPPELINGEN if koppelingen is None else koppelingen
        self.map = werk / "servers" / naam
        self.geheugen = geheugen
        self.webdir = webdir
        # Alternatief voor --webdir bij de jelly-leon-image (die weigert padopties): een webclient over de ingebouwde
        # /jellyfin/jellyfin-web heen koppelen (alleen-lezen; alleen in tests, nooit in een Custom App).
        self.web_over = web_over
        self.cpus = cpus
        self.poort = 0
        self.container_id = ""
        self.jf: Jellyfin | None = None
        self.info: dict[str, Any] = {}
        self.gekoppeld: list[str] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.poort}"

    def start(self, schoon: bool = True) -> StockServer:
        if schoon:
            shutil.rmtree(self.map, ignore_errors=True)
        for sub in ("config", "cache"):
            (self.map / sub).mkdir(parents=True, exist_ok=True)
        docker("rm", "-f", self.naam, check=False)
        self.poort = vrije_poort()
        cmd = ["run", "-d", "--name", self.naam, "--user", f"{os.getuid()}:{os.getgid()}", "--memory", self.geheugen,
               "--security-opt", "no-new-privileges", "--cap-drop", "ALL", "-p", f"127.0.0.1:{self.poort}:8096",
               "-v", f"{self.map / 'config'}:/config", "-v", f"{self.map / 'cache'}:/cache", "-e", "TZ=UTC"]
        if self.cpus:
            cmd += ["--cpus", self.cpus]
        if self.gpu:
            gid = render_gid()
            cmd += ["--device", f"{RENDER}:{RENDER}"] + (["--group-add", str(gid)] if gid is not None else [])
        self.gekoppeld = []
        for doel, bron in self.koppelingen.items():
            if (self.corpus / bron).exists():
                cmd += ["-v", f"{self.corpus / bron}:{doel}:ro"]
                self.gekoppeld.append(doel)
        if self.webdir:
            cmd += ["-v", f"{self.webdir}:/stockweb:ro"]
        if self.web_over:
            cmd += ["-v", f"{self.web_over}:/jellyfin/jellyfin-web:ro"]
        cmd.append(self.image)
        if self.webdir:
            cmd += ["--webdir", "/stockweb"]
        self.container_id = docker(*cmd).stdout.strip()
        self.info = wacht_klaar(self.url)
        self.jf = Jellyfin(self.url)
        return self

    def inrichten(self, bibliotheken: list[tuple[str, str, list[str]]] | None = None) -> float:
        assert self.jf
        self.jf.wizard(GEBRUIKER, WACHTWOORD)
        for naam, soort, paden in (BIBLIOTHEKEN if bibliotheken is None else bibliotheken):
            # Alleen paden waaronder echt iets gekoppeld is (in CI ontbreken delen van het corpus; 12.4 weigert dan met 400).
            bestaand = [p for p in paden if any(g == p or g.startswith(p.rstrip("/") + "/") for g in self.gekoppeld)]
            if bestaand:
                self.jf.bibliotheek(naam, soort, bestaand)
        return self.jf.scan()

    def herstart(self) -> None:
        docker("restart", self.naam)
        wacht_klaar(self.url)
        assert self.jf
        self.jf.login(GEBRUIKER, WACHTWOORD)

    def stop(self) -> None:
        docker("stop", "-t", "20", self.naam, check=False)

    def verwijder(self, data: bool = True) -> None:
        docker("rm", "-f", self.naam, check=False)
        if data:
            shutil.rmtree(self.map, ignore_errors=True)

    def logs(self, regels: int = 200) -> str:
        return docker("logs", "--tail", str(regels), self.naam, check=False).stdout

    def transcodelogs(self) -> list[Path]:
        return sorted((self.map / "config" / "log").glob("FFmpeg.Transcode-*.log"), key=lambda p: p.stat().st_mtime)

    def digest(self) -> str:
        """Het image-ID van de draaiende container (bewijs dat de vastgezette digest echt gebruikt is)."""
        uit = docker("inspect", "--format", "{{.Image}}", self.naam, check=False).stdout.strip()
        return uit

    def __enter__(self) -> StockServer:
        return self

    def __exit__(self, *_: object) -> None:
        self.verwijder(data=os.environ.get("B03_HOUD_DATA") != "1")


def wacht(seconden: float) -> None:
    time.sleep(seconden)
