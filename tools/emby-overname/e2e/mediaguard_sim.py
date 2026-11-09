"""MediaGuard-simulator voor JLT-73 (Δ-MG-AUTH per server en Δ-MG-DUAL): volgt Emby én Jelly Leon tegelijk.

Dit is NIET MediaGuard (eigendom van media-guard-ultimate); het bootst alleen na wat MediaGuard volgens het plan moet doen:
- Emby met `X-Emby-Token` (de bestaande koppeling, blijft ongewijzigd), Jelly Leon 12.x met
  `Authorization: MediaBrowser Token=…` (12.x zet legacy-auth uit);
- elke seconde `GET /Sessions` op beide servers; een sessie met `NowPlayingItem` = kijkpauze voor die server;
- telt per server elke mislukte poging, zodat aantoonbaar is dat de Emby-koppeling op geen moment wegvalt.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any


class MediaGuardSim:
    def __init__(self, emby_url: str, emby_sleutel: str, jl_url: str, jl_sleutel: str, interval: float = 1.0) -> None:
        self.servers = {
            "emby": (emby_url, {"X-Emby-Token": emby_sleutel}),
            "jelly_leon": (jl_url, {"Authorization": f'MediaBrowser Client="MediaGuard (simulator)", Device="mg-sim", '
                                                      f'DeviceId="mg-sim-1", Version="0.0.0", Token="{jl_sleutel}"'}),
        }
        self.interval = interval
        self.polls: dict[str, dict[str, int]] = {n: {"ok": 0, "fout": 0} for n in self.servers}
        self.fouten: list[dict[str, Any]] = []
        self.kijkpauze: dict[str, list[float]] = {n: [] for n in self.servers}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _poll(self, naam: str) -> None:
        url, headers = self.servers[naam]
        verzoek = urllib.request.Request(url + "/Sessions", headers={"Accept": "application/json", **headers})  # noqa: S310
        try:
            with urllib.request.urlopen(verzoek, timeout=5) as antwoord:  # noqa: S310 - lokaal testadres
                sessies = json.loads(antwoord.read() or b"[]")
            self.polls[naam]["ok"] += 1
            if any(s.get("NowPlayingItem") for s in sessies):
                self.kijkpauze[naam].append(time.time())
        except (urllib.error.URLError, OSError, ValueError) as fout:
            self.polls[naam]["fout"] += 1
            self.fouten.append({"server": naam, "tijd": time.time(), "fout": str(fout)[:200]})

    def _loop(self) -> None:
        while not self._stop.is_set():
            for naam in self.servers:
                self._poll(naam)
            self._stop.wait(self.interval)

    def wacht_op_kijkpauze(self, naam: str, sinds: float, timeout: float = 20.0) -> float | None:
        einde = time.time() + timeout
        while time.time() < einde:
            treffers = [t for t in self.kijkpauze[naam] if t >= sinds]
            if treffers:
                return treffers[0] - sinds
            time.sleep(0.2)
        return None

    def samenvatting(self) -> dict[str, Any]:
        return {"polls": self.polls, "fouten": self.fouten[:20],
                "kijkpauze_waarnemingen": {n: len(v) for n, v in self.kijkpauze.items()}}
