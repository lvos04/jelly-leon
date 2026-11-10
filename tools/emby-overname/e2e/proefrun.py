#!/usr/bin/env python3
"""E2E-proefrun B03-015 deel A (golf 0): echte Emby 4.10.2.0 + stock Jellyfin 12.4 in containers — JLT-70…73.

Wat er gebeurt (alles in wegwerpcontainers; media altijd alleen-lezen gekoppeld; daarna opgeruimd):
 1. testbibliotheek met opzettelijke gaten (`testbibliotheek.py`): corpus (harde links, lokaal) of synthetisch (CI);
 2. Emby: startwizard, API-sleutels, bibliotheken (zonder internetbronnen; ID's uit NFO), 5 gebruikers (beheerder, twee
    volwassenen, een kind met leeftijdsgrens en geblokkeerde tag, een gast met alleen Films) met kijkgeschiedenis,
    hervatpunten, favorieten, beoordelingen en onthouden spoorkeuzes — door deze harnas via de Emby-API gezet;
 3. Jellyfin 12.4: startwizard, API-sleutel, dezelfde media onder een andere mountroot;
 4. de overnametool praat met Emby en Jellyfin via een **loggende proxy** (verkeersmeting); een MediaGuard-simulator
    volgt intussen beide servers (Δ-MG-AUTH/Δ-MG-DUAL);
 5. proefrun → akkoord (gesimuleerd) → overzetten → controle tegen een eigen, onafhankelijke grondwaarheid;
    tweede run (0 schrijfacties, identiek rapport); delta; afgebroken run + hervatten; testhaak POST/DELETE;
    Emby vóór/na elke toolrun identiek; geen sleutel in logs/rapporten/exports; inloggen met nieuw wachtwoord en hervatten
    (stock-clientprotocol, simulator); kijkpauze op Emby én Jelly Leon; herimport uit het archief op een lege Jellyfin.
Resultaat: één JSON-bewijsbestand (+ de rapporten). Exitcode 0 = alle controles geslaagd (Sim-geslaagd, geen echte NAS).

Draaien onder het machinebrede slot: flock /home/transcode/truenas-v2/.lokaal/stack.lock python3 e2e/proefrun.py …
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HIER = Path(__file__).resolve().parent
TOOL = HIER.parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(TOOL))

from loggende_proxy import LoggendeProxy  # noqa: E402
from mediaguard_sim import MediaGuardSim  # noqa: E402
from testbibliotheek import FILMS, SERIES, Item, bouw, recept  # noqa: E402

EMBY_IMAGE = "docker.io/emby/embyserver:4.10.2.0@sha256:7082c63b10a2fcb3805a7eaebba407d5723bc57c085c9f0b29b7d0a702765cc1"
JL_IMAGE = "docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771"
# Doel van de overname: standaard stock 12.4 (golf 0); in P4-0 de jelly-leon-image (--jellyfin-image, JLT-70…73 herhaald).
DOEL_IMAGE = JL_IMAGE
CORPUS = Path("/home/transcode/truenas-v2/.lokaal/media-corpus")
EMBY_ROOT, JL_ROOT = "/mnt/emby/media", "/data/media"
WACHTWOORD_BEHEER = "Proefrun-Beheer-2026!"
EMBY_CLIENT = 'Emby Client="proefrun-harnas", Device="harnas", DeviceId="jl-b03015-harnas", Version="1.0"'
JL_CLIENT = 'MediaBrowser Client="proefrun-harnas", Device="harnas", DeviceId="jl-b03015-harnas", Version="1.0"'


def nu() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(tekst: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {tekst}", flush=True)


# --- HTTP ---------------------------------------------------------------------------------------------------------

class Http:
    def __init__(self, basis: str, headers: dict[str, str]) -> None:
        self.basis = basis.rstrip("/")
        self.headers = headers

    def doe(self, methode: str, pad: str, query: dict[str, Any] | None = None, body: Any = None,
            headers: dict[str, str] | None = None, verwacht: tuple[int, ...] = (200, 204)) -> Any:
        url = self.basis + pad + ("?" + urllib.parse.urlencode(query) if query else "")
        data = json.dumps(body).encode() if body is not None else (b"" if methode == "POST" else None)
        h = {"Accept": "application/json", **self.headers, **(headers or {})}
        if body is not None:
            h["Content-Type"] = "application/json"
        verzoek = urllib.request.Request(url, data=data, method=methode, headers=h)  # noqa: S310 - lokaal testadres
        try:
            with urllib.request.urlopen(verzoek, timeout=120) as antwoord:  # noqa: S310 - lokaal testadres
                status, ruw = antwoord.status, antwoord.read()
        except urllib.error.HTTPError as fout:
            status, ruw = fout.code, fout.read()
        if status not in verwacht:
            raise RuntimeError(f"{methode} {pad} → HTTP {status}: {ruw[:300]!r}")
        if not ruw:
            return None
        try:
            return json.loads(ruw)
        except json.JSONDecodeError:
            return ruw.decode("utf-8", "replace")

    def status(self, methode: str, pad: str, body: Any = None, headers: dict[str, str] | None = None) -> int:
        data = json.dumps(body).encode() if body is not None else b""
        h = {"Accept": "application/json", "Content-Type": "application/json", **self.headers, **(headers or {})}
        verzoek = urllib.request.Request(self.basis + pad, data=data, method=methode, headers=h)  # noqa: S310
        try:
            with urllib.request.urlopen(verzoek, timeout=60) as antwoord:  # noqa: S310 - lokaal testadres
                return antwoord.status
        except urllib.error.HTTPError as fout:
            return fout.code


def ververs(*beheer: Http | None) -> None:
    """Start de bibliotheekscan (nogmaals) als die na het aanmaken van de bibliotheken niet op gang kwam."""
    for http in beheer:
        if http is not None:
            try:
                http.doe("POST", "/Library/Refresh")
            except RuntimeError:
                pass


def wacht(url: str, timeout: float = 300) -> None:
    """Wacht tot de server echt klaar is: geldige JSON met een versie (Jellyfin 12 toont tijdens het laden een HTML-pagina)."""
    einde = time.time() + timeout
    while time.time() < einde:
        try:
            with urllib.request.urlopen(url, timeout=5) as antwoord:  # noqa: S310
                data = json.loads(antwoord.read().decode("utf-8-sig"))
                if antwoord.status == 200 and isinstance(data, dict) and data.get("Version"):
                    return
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError(f"{url} niet bereikbaar binnen {timeout} s")


def met_herhaling(functie: Any, pogingen: int = 30) -> Any:
    """Herhaalt bij HTTP 503 (server nog aan het opstarten)."""
    for poging in range(pogingen):
        try:
            return functie()
        except RuntimeError as fout:
            if "HTTP 503" not in str(fout) or poging == pogingen - 1:
                raise
            time.sleep(3)
    return None


def vrije_poort() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=900)


def ticks(tekst: str) -> str:
    return tekst.replace("Z", ".0000000Z") if "." not in tekst else tekst


# --- bewijs -------------------------------------------------------------------------------------------------------

class Bewijs:
    def __init__(self, modus: str) -> None:
        self.data: dict[str, Any] = {
            "schema": "jelly-leon/b03-015-proefrun-bewijs/1", "modus": modus, "begin": nu(),
            "images": {"emby": EMBY_IMAGE, "jellyfin": DOEL_IMAGE},
            "validatie": "Sim (echte containers op de ontwikkelmachine; NIET GEVALIDEERD op de echte NAS)",
            "controles": [], "loadavg_begin": os.getloadavg(),
        }

    def check(self, test: str, naam: str, ok: bool, detail: Any = "") -> bool:
        self.data["controles"].append({"test": test, "naam": naam, "ok": bool(ok), "detail": detail})
        log(f"{'OK  ' if ok else 'FOUT'} [{test}] {naam}{': ' + str(detail)[:200] if detail != '' else ''}")
        return bool(ok)

    def schrijf(self, pad: Path) -> None:
        self.data["einde"] = nu()
        self.data["loadavg_einde"] = os.getloadavg()
        geslaagd = sum(c["ok"] for c in self.data["controles"])
        self.data["samenvatting"] = {"controles": len(self.data["controles"]), "geslaagd": geslaagd,
                                     "mislukt": len(self.data["controles"]) - geslaagd}
        per_test: dict[str, list[bool]] = {}
        for c in self.data["controles"]:
            per_test.setdefault(c["test"], []).append(c["ok"])
        self.data["per_test"] = {t: ("Sim-geslaagd" if all(v) else "Sim-mislukt") + f" ({sum(v)}/{len(v)})"
                                 for t, v in sorted(per_test.items())}
        pad.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --- Emby ---------------------------------------------------------------------------------------------------------

class Emby:
    def __init__(self, url: str) -> None:
        self.url = url
        self.anoniem = Http(url, {"X-Emby-Authorization": EMBY_CLIENT})
        self.admin: Http | None = None
        self.admin_id = ""
        self.tokens: dict[str, str] = {}

    def wizard(self) -> None:
        self.anoniem.doe("POST", "/Startup/Configuration", body={"UICulture": "nl", "MetadataCountryCode": "US",
                                                                 "PreferredMetadataLanguage": "nl"})
        self.anoniem.doe("GET", "/Startup/User")
        self.anoniem.doe("POST", "/Startup/User", body={"Name": "beheerder", "Password": WACHTWOORD_BEHEER})
        self.anoniem.doe("POST", "/Startup/Complete")
        auth = self.anoniem.doe("POST", "/Users/AuthenticateByName", body={"Username": "beheerder", "Pw": WACHTWOORD_BEHEER})
        self.admin = Http(self.url, {"X-Emby-Token": auth["AccessToken"]})
        self.admin_id = auth["User"]["Id"]

    def sleutel(self, app: str) -> str:
        assert self.admin
        self.admin.doe("POST", "/Auth/Keys", {"App": app})
        for k in self.admin.doe("GET", "/Auth/Keys")["Items"]:
            if k.get("AppName") == app:
                return k["AccessToken"]
        raise RuntimeError(f"Emby-sleutel {app} niet gevonden")

    def bibliotheek(self, naam: str, soort: str, pad: str) -> None:
        assert self.admin
        typen = ["Movie"] if soort == "movies" else ["Series", "Season", "Episode"]
        opties = {"ContentType": soort, "EnableRealtimeMonitor": False, "SaveLocalMetadata": False,
                  "EnableChapterImageExtraction": False, "DownloadImagesInAdvance": False, "PathInfos": [{"Path": pad}],
                  "TypeOptions": [{"Type": t, "MetadataFetchers": [], "MetadataFetcherOrder": [], "ImageFetchers": [],
                                   "ImageFetcherOrder": []} for t in typen],
                  "MetadataSavers": [], "DisabledSubtitleFetchers": [], "SubtitleDownloadLanguages": []}
        self.admin.doe("POST", "/Library/VirtualFolders", {"Name": naam, "CollectionType": soort, "RefreshLibrary": "true"},
                       body={"LibraryOptions": opties})

    def items(self, uid: str, extra: str = "") -> list[dict[str, Any]]:
        assert self.admin
        data = self.admin.doe("GET", f"/Users/{uid}/Items", {
            "Recursive": "true", "Fields": "Path,ProviderIds,UserDataPlayCount,UserDataLastPlayedDate,ParentIndexNumber,IndexNumber" + extra,
            "EnableUserData": "true"})
        return data["Items"]

    def gebruiker(self, naam: str, beleid: dict[str, Any], config: dict[str, Any], wachtwoord: str) -> str:
        assert self.admin
        uid = self.admin.doe("POST", "/Users/New", body={"Name": naam})["Id"]
        huidig = self.admin.doe("GET", f"/Users/{uid}")
        self.admin.doe("POST", f"/Users/{uid}/Policy", body={**huidig["Policy"], **beleid})
        self.admin.doe("POST", f"/Users/{uid}/Configuration", body={**huidig["Configuration"], **config})
        self.admin.doe("POST", f"/Users/{uid}/Password", body={"NewPw": wachtwoord, "ResetPassword": False})
        auth = self.anoniem.doe("POST", "/Users/AuthenticateByName", body={"Username": naam, "Pw": wachtwoord})
        self.tokens[uid] = auth["AccessToken"]
        return uid

    def als(self, uid: str) -> Http:
        return Http(self.url, {"X-Emby-Token": self.tokens[uid],
                               "X-Emby-Authorization": EMBY_CLIENT.replace("Emby ", f'Emby UserId="{uid}", ')})


# --- Jellyfin -----------------------------------------------------------------------------------------------------

class Jellyfin:
    def __init__(self, url: str) -> None:
        self.url = url
        self.anoniem = Http(url, {"Authorization": JL_CLIENT})
        self.admin: Http | None = None

    def wizard(self) -> None:
        self.anoniem.doe("POST", "/Startup/Configuration", body={"UICulture": "nl", "MetadataCountryCode": "US",
                                                                 "PreferredMetadataLanguage": "nl"})
        self.anoniem.doe("GET", "/Startup/User")
        self.anoniem.doe("POST", "/Startup/User", body={"Name": "jlbeheer", "Password": WACHTWOORD_BEHEER})
        self.anoniem.doe("POST", "/Startup/RemoteAccess", body={"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False})
        self.anoniem.doe("POST", "/Startup/Complete")
        auth = self.anoniem.doe("POST", "/Users/AuthenticateByName", body={"Username": "jlbeheer", "Pw": WACHTWOORD_BEHEER})
        self.admin = Http(self.url, {"Authorization": JL_CLIENT + f', Token="{auth["AccessToken"]}"'})

    def sleutel(self, app: str) -> str:
        assert self.admin
        self.admin.doe("POST", "/Auth/Keys", {"app": app})
        for k in self.admin.doe("GET", "/Auth/Keys")["Items"]:
            if k.get("AppName") == app:
                return k["AccessToken"]
        raise RuntimeError(f"Jellyfin-sleutel {app} niet gevonden")

    def bibliotheek(self, naam: str, soort: str, pad: str) -> None:
        assert self.admin
        typen = ["Movie"] if soort == "movies" else ["Series", "Season", "Episode"]
        opties = {"EnableRealtimeMonitor": False, "SaveLocalMetadata": False, "EnableChapterImageExtraction": False,
                  "EnableTrickplayImageExtraction": False, "ExtractTrickplayImagesDuringLibraryScan": False,
                  "PathInfos": [{"Path": pad}], "MetadataSavers": [], "DisabledSubtitleFetchers": [], "SubtitleDownloadLanguages": [],
                  "SaveSubtitlesWithMedia": False, "SaveTrickplayWithMedia": False, "SaveLyricsWithMedia": False,
                  "TypeOptions": [{"Type": t, "MetadataFetchers": [], "MetadataFetcherOrder": [], "ImageFetchers": [],
                                   "ImageFetcherOrder": []} for t in typen]}
        self.admin.doe("POST", "/Library/VirtualFolders", {"name": naam, "collectionType": soort, "refreshLibrary": "true"},
                       body={"LibraryOptions": opties})

    def items(self, uid: str | None = None) -> list[dict[str, Any]]:
        assert self.admin
        query = {"recursive": "true", "fields": "Path,ProviderIds,MediaSources", "enableUserData": "true"}
        if uid:
            query["userId"] = uid
        return self.admin.doe("GET", "/Items", query)["Items"]

    def gebruikers(self) -> dict[str, dict[str, Any]]:
        assert self.admin
        return {g["Name"]: g for g in self.admin.doe("GET", "/Users")}


# --- grondwaarheid (onafhankelijk van de tool) ---------------------------------------------------------------------

def kijk(ud: dict[str, Any] | None) -> dict[str, Any]:
    ud = ud or {}
    return {"gezien": bool(ud.get("Played")), "aantal": int(ud.get("PlayCount") or 0), "laatst": ud.get("LastPlayedDate"),
            "positie": int(ud.get("PlaybackPositionTicks") or 0), "favoriet": bool(ud.get("IsFavorite")),
            "beoordeling": ud.get("Rating"), "vind_ik_leuk": ud.get("Likes")}


AFSPEELBAAR = {"Movie", "Episode", "Video", "MusicVideo", "Audio", "AudioBook", "Trailer"}


def heeft(k: dict[str, Any], container: bool) -> bool:
    eigen = k["favoriet"] or k["beoordeling"] is not None or k["vind_ik_leuk"] is not None
    return eigen if container else (eigen or k["gezien"] or k["aantal"] > 0 or k["positie"] > 0 or k["laatst"] is not None)


def emby_paden(emby: Emby, detail: bool = False) -> dict[str, dict[str, Any]]:
    """Elk mediabestand (ook de versies die Emby in één item bundelt) → het Emby-item (met RunTimeTicks).

    Met `detail` worden ook de mediabronnen uit de itemdetails van elke film gelezen (Emby toont gebundelde versies
    mogelijk alleen daar)."""
    assert emby.admin
    uit: dict[str, dict[str, Any]] = {}
    for i in emby.items(emby.admin_id, ",RunTimeTicks,MediaSources"):
        bronnen = list(i.get("MediaSources") or [])
        if detail and i.get("Type") == "Movie":
            bronnen += emby.admin.doe("GET", f"/Users/{emby.admin_id}/Items/{i['Id']}").get("MediaSources") or []
        for pad in {i.get("Path") or "", *(b.get("Path") or "" for b in bronnen)}:
            if pad.startswith(EMBY_ROOT):
                uit.setdefault(pad[len(EMBY_ROOT) + 1:], i)
    return uit


def emby_zichtbare_paden(emby: Emby, uid: str) -> set[str]:
    """Alle mediabestanden die een gebruiker in Emby ziet, ook de versies die Emby in één item bundelt."""
    assert emby.admin
    uit: set[str] = set()
    for i in emby.items(uid, ",MediaSources"):
        bronnen = list(i.get("MediaSources") or [])
        if i.get("Type") == "Movie":
            bronnen += emby.admin.doe("GET", f"/Users/{uid}/Items/{i['Id']}").get("MediaSources") or []
        for pad in {i.get("Path") or "", *(b.get("Path") or "" for b in bronnen)}:
            if pad.startswith(EMBY_ROOT):
                uit.add(pad[len(EMBY_ROOT) + 1:])
    return uit


def emby_diagnose(emby: Emby, ontbrekend: list[str]) -> dict[str, Any]:
    """Wat Emby weet over ontbrekende testbestanden (zoeken op titel; lijst- én detailweergave)."""
    assert emby.admin
    uit: dict[str, Any] = {}
    for pad in ontbrekend:
        titel = pad.rsplit("/", 1)[-1].split(" (")[0]
        data = emby.admin.doe("GET", f"/Users/{emby.admin_id}/Items", {
            "Recursive": "true", "SearchTerm": titel, "Fields": "Path,ProviderIds,MediaSources,PartCount", "IncludeItemTypes": "Movie"})
        treffers = []
        for i in data.get("Items", []):
            detail = emby.admin.doe("GET", f"/Users/{emby.admin_id}/Items/{i['Id']}")
            treffers.append({"id": i["Id"], "naam": i.get("Name"), "pad": i.get("Path"), "provider": i.get("ProviderIds"),
                             "lijst_bronnen": [b.get("Path") for b in i.get("MediaSources") or []],
                             "detail_bronnen": [b.get("Path") for b in detail.get("MediaSources") or []],
                             "PartCount": detail.get("PartCount"), "MediaSourceCount": detail.get("MediaSourceCount")})
        uit[pad] = treffers
    return uit


def emby_toestand(emby: Emby, gebruikers: dict[str, str]) -> dict[str, dict[str, dict[str, Any]]]:
    """Per gebruiker per pad (relatief) alle kijkgegevens, direct uit Emby (niet via de tool of de proxy)."""
    uit: dict[str, dict[str, dict[str, Any]]] = {}
    for naam, uid in gebruikers.items():
        per: dict[str, dict[str, Any]] = {}
        for i in emby.items(uid):
            if not i.get("Path", "").startswith(EMBY_ROOT):
                continue
            k = kijk(i.get("UserData"))
            if heeft(k, i["Type"] not in AFSPEELBAAR):
                per[i["Path"][len(EMBY_ROOT) + 1:]] = {**k, "type": i["Type"], "id": i["Id"]}
        uit[naam] = per
    return uit


def jl_toestand(jl: Jellyfin, uid: str) -> dict[str, dict[str, Any]]:
    return {i["Path"][len(JL_ROOT) + 1:]: {**kijk(i.get("UserData")), "type": i["Type"], "id": i["Id"]}
            for i in jl.items(uid) if i.get("Path", "").startswith(JL_ROOT)}


def zelfde_tijd(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return a == b
    return datetime.fromisoformat(a.replace("Z", "+00:00")[:26] + "+00:00" if "." in a else a.replace("Z", "+00:00")) == \
        datetime.fromisoformat(b.replace("Z", "+00:00")[:26] + "+00:00" if "." in b else b.replace("Z", "+00:00"))


# --- de tool ------------------------------------------------------------------------------------------------------

class Tool:
    def __init__(self, uitvoer: Path, emby_url: str, jl_url: str, sleutels: dict[str, Path]) -> None:
        self.uitvoer = uitvoer
        self.emby_url = emby_url
        self.jl_url = jl_url
        self.sleutels = sleutels
        self.werkmap = uitvoer / "werkmap"
        self.akkoorden = 0

    def basis(self, archief: Path | None = None, werkmap: Path | None = None, jl_url: str | None = None) -> list[str]:
        bron = ["--bron-archief", str(archief)] if archief else ["--emby-url", self.emby_url, "--emby-sleutel-bestand",
                                                                str(self.sleutels["emby"])]
        return [*bron, "--jl-url", jl_url or self.jl_url, "--jl-sleutel-bestand", str(self.sleutels["jl"]),
                "--werkmap", str(werkmap or self.werkmap), "--pad", f"{EMBY_ROOT}={JL_ROOT}", "--gebruiker", "beheerder=jlbeheer"]

    def draai(self, *args: str, verwacht: int | None = 0) -> tuple[int, dict[str, Any]]:
        omgeving = {**os.environ, "PYTHONPATH": str(TOOL)}
        proces = subprocess.run([sys.executable, "-m", "emby_overname", *args], capture_output=True, text=True, env=omgeving,
                                timeout=1800, check=False, cwd=str(TOOL))
        (self.uitvoer / "toolrun.log").open("a", encoding="utf-8").write(
            f"\n$ emby_overname {args[0]} (exit {proces.returncode})\n{proces.stderr}\n{proces.stdout}\n")
        if verwacht is not None and proces.returncode != verwacht:
            raise RuntimeError(f"tool {args[0]} gaf exit {proces.returncode}: {proces.stderr[-2000:]}")
        regels = proces.stdout.strip().splitlines()
        return proces.returncode, (json.loads(regels[-1]) if regels else {})

    def akkoord(self, samenvatting: dict[str, Any], soort: str) -> Path:
        rapport = json.loads(Path(samenvatting["rapport"]).read_text(encoding="utf-8"))
        self.akkoorden += 1
        pad = self.uitvoer / f"akkoord-{self.akkoorden:02d}-{soort}.json"
        pad.write_text(json.dumps({
            "schema": "jelly-leon/emby-overname-akkoord/1", "soort": soort, "rapport_inhoud_sha256": rapport["inhoud_sha256"],
            "plan_sha256": rapport["plan_sha256"], "akkoord_door": "proefrun-harnas (simulatie van de gebruiker)",
            "datum": nu(), "verschillen": rapport["akkoord"]["verschillen"]}, indent=2), encoding="utf-8")
        return pad


def rapport_van(samenvatting: dict[str, Any]) -> dict[str, Any]:
    return json.loads(Path(samenvatting["rapport"]).read_text(encoding="utf-8"))


def afhandel_per_gebruiker(rapport: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {g["emby_naam"]: g["afhandellijst"] for g in rapport["toestand"]["gebruikers"]}


# --- scenario ------------------------------------------------------------------------------------------------------

GEBRUIKERS = {
    "Anna": ({"IsAdministrator": False}, {"AudioLanguagePreference": "eng", "SubtitleLanguagePreference": "dut",
                                           "SubtitleMode": "Always"}),
    "Bram": ({"IsAdministrator": False, "EnableContentDownloading": False}, {"SubtitleMode": "OnlyForced"}),
    "Kim": ({"IsAdministrator": False, "EnableAllFolders": False, "MaxParentalRating": 5, "BlockedTags": ["Horror"],
             "EnableRemoteAccess": False, "EnableContentDownloading": False}, {"SubtitleMode": "None"}),
    "Gast": ({"IsAdministrator": False, "EnableAllFolders": False, "EnableRemoteAccess": False}, {}),
}

# (gebruiker, logische sleutel of "serie:<titel>", soort, waarde)
KIJK: list[tuple[str, str, str, Any]] = [
    ("beheerder", "sintel", "gezien", ("2026-10-01T20:15:42Z", 2)),
    ("beheerder", "bbb", "positie", (0.37, "2026-10-02T21:00:00Z", 1)),
    ("beheerder", "hero", "gezien", ("2026-09-01T19:00:00Z", 1)),
    ("beheerder", "cosmos", "gezien", ("2026-09-02T19:00:00Z", 1)),
    ("beheerder", "spring", "favoriet", True),
    ("beheerder", "serie:B03 Testserie", "favoriet", True),
    ("beheerder", "testserie_s1e1", "gezien", ("2026-10-03T18:00:00Z", 1)),
    ("beheerder", "testserie_s1e2", "gezien", ("2026-10-03T18:40:00Z", 2)),
    ("beheerder", "testserie_s1e3", "gezien", ("2026-10-03T19:20:00Z", 1)),
    ("beheerder", "testserie_s2e1", "positie", (0.5, "2026-10-04T19:00:00Z", 0)),
    ("beheerder", "anime_1", "gezien", ("2026-10-05T17:00:00Z", 1)),
    ("beheerder", "anime_2", "gezien", ("2026-10-05T17:30:00Z", 1)),
    ("beheerder", "anime_3", "gezien", ("2026-10-05T18:00:00Z", 1)),
    ("Anna", "tos", "gezien", ("2026-10-06T20:00:00Z", 1)),
    ("Anna", "tos_multi", "positie", (0.25, "2026-10-07T20:00:00Z", 0)),
    ("Anna", "sintel", "favoriet", True),
    ("Anna", "sintel", "spoor", ("ondertitel", ("dut", "nld"))),
    ("Anna", "tos_multi", "spoor", ("audio", 2)),
    # Bewust NIET de voorkeur van Anna (altijd Nederlandse ondertitels): Emby onthoudt Engels; Jelly Leon kiest zelf
    # Nederlands. Omdat het bestand in Jelly Leon anders is (zelfde pad, andere grootte) moet dit als `ander_bestand`
    # gemeld worden (JLT-72).
    ("Anna", "kort", "spoor", ("ondertitel", ("eng",))),
    ("Anna", "kort", "gezien", ("2026-10-08T20:00:00Z", 3)),
    ("Anna", "pioneer_e1", "gezien", ("2026-10-09T20:00:00Z", 1)),
    ("Anna", "pioneer_e2", "gezien", ("2026-10-10T20:00:00Z", 2)),
    ("Anna", "pioneer_e3", "positie", (0.66, "2026-10-11T20:00:00Z", 0)),
    ("Bram", "ed", "gezien", ("2026-10-12T20:00:00Z", 1)),
    ("Bram", "ed", "leuk", True),
    ("Bram", "llama", "positie", (0.42, "2026-10-13T20:00:00Z", 0)),
    ("Bram", "serie:Pioneer One", "favoriet", True),
    ("Bram", "bbb", "favoriet", True),
    *[("Bram", f"pioneer_e{n}", "gezien", (f"2026-10-{13 + n:02d}T21:00:00Z", n)) for n in range(1, 7)],
    ("Kim", "bbb", "gezien", ("2026-10-20T08:00:00Z", 3)),
    ("Kim", "llama", "positie", (0.2, "2026-10-21T08:00:00Z", 0)),
    ("Kim", "serie:B03 Anime", "favoriet", True),
    ("Kim", "anime_1", "gezien", ("2026-10-22T08:00:00Z", 1)),
    ("Kim", "testserie_s1e1", "gezien", ("2026-10-23T08:00:00Z", 1)),
    ("Gast", "hero", "gezien", ("2026-10-24T20:00:00Z", 1)),
    ("Gast", "sintel", "positie", (0.8, "2026-10-25T20:00:00Z", 0)),
]


def emby_datum(tekst: str) -> str:
    return tekst.replace("-", "").replace(":", "").replace("T", "").replace("Z", "")


def zet_kijk(emby: Emby, uid: str, item: dict[str, Any], soort: str, waarde: Any, log_regels: list[str]) -> None:
    assert emby.admin
    iid = item["Id"]
    if soort == "gezien":
        datum, aantal = waarde
        emby.admin.doe("POST", f"/Users/{uid}/PlayedItems/{iid}", {"DatePlayed": emby_datum(datum)})
        # Emby 4.10 zet bij deze route ook velden die ontbreken terug (gemeten: Played werd weer false); daarom expliciet.
        emby.admin.doe("POST", f"/Users/{uid}/Items/{iid}/UserData",
                       body={"Played": True, "PlayCount": aantal, "LastPlayedDate": ticks(datum), "PlaybackPositionTicks": 0})
    elif soort == "positie":
        fractie, datum, aantal = waarde
        positie = int(int(item.get("RunTimeTicks") or 600_000_000) * fractie) + 7  # +7: bewijst tick-exactheid
        emby.admin.doe("POST", f"/Users/{uid}/Items/{iid}/UserData",
                       body={"PlaybackPositionTicks": positie, "PlayCount": aantal, "LastPlayedDate": ticks(datum)})
    elif soort == "favoriet":
        emby.admin.doe("POST", f"/Users/{uid}/FavoriteItems/{iid}")
    elif soort == "leuk":
        emby.admin.doe("POST", f"/Users/{uid}/Items/{iid}/Rating", {"Likes": "true" if waarde else "false"})
    elif soort == "spoor":
        welk, keuze = waarde
        als = emby.als(uid)
        info = als.doe("GET", f"/Items/{iid}/PlaybackInfo", {"UserId": uid})
        bron = info["MediaSources"][0]
        streams = bron.get("MediaStreams") or []
        audio = [s for s in streams if s.get("Type") == "Audio"]
        subs = [s for s in streams if s.get("Type") == "Subtitle"]
        verzoek: dict[str, Any] = {"ItemId": iid, "MediaSourceId": bron["Id"], "PlaySessionId": info["PlaySessionId"],
                                   "PositionTicks": 50_000_000, "PlayMethod": "DirectPlay", "CanSeek": True}
        if welk == "audio" and len(audio) >= keuze:
            verzoek["AudioStreamIndex"] = audio[keuze - 1]["Index"]
        elif welk == "ondertitel" and not keuze:
            verzoek["SubtitleStreamIndex"] = -1  # ondertitels uit
        elif welk == "ondertitel":
            gekozen = [s for s in subs if (s.get("Language") or "").casefold() in keuze]
            if not gekozen:
                log_regels.append(f"spoorkeuze: geen ondertitel {keuze} in {item.get('Path')}")
                return
            verzoek["SubtitleStreamIndex"] = gekozen[0]["Index"]
        for route in ("/Sessions/Playing", "/Sessions/Playing/Progress", "/Sessions/Playing/Stopped"):
            als.doe("POST", route, body=verzoek)
        log_regels.append(f"spoorkeuze {welk} gezet voor {item.get('Path')}")


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0915 - één doorlopend scenario
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--modus", choices=("corpus", "synthetisch"), default="synthetisch")
    p.add_argument("--uitvoer", required=True)
    p.add_argument("--corpus", default=str(CORPUS))
    p.add_argument("--ffmpeg", choices=("auto", "host", "docker"), default="auto")
    p.add_argument("--behoud", action="store_true", help="containers en testset niet opruimen (alleen voor diagnose)")
    p.add_argument("--browser", choices=("geen", "chromium"), default="geen",
                   help="JLT-70 clientdeel: de webclient van de doelserver in een echte browser (Playwright-harnas van "
                        "B03-016; vraagt `npm ci` in tools/b03-harnas/playwright en Chromium)")
    p.add_argument("--jellyfin-image", default=JL_IMAGE,
                   help="doelserver: stock 12.4 op digest (golf 0) of de lokaal gebouwde jelly-leon-image (P4-0)")
    args = p.parse_args(argv)
    global DOEL_IMAGE  # noqa: PLW0603 - één doorlopend scenario; het bewijs noemt de gebruikte image
    DOEL_IMAGE = args.jellyfin_image

    uitvoer = Path(args.uitvoer).resolve()
    uitvoer.mkdir(parents=True, exist_ok=True)
    werk = uitvoer / "werk"
    bewijs = Bewijs(args.modus)
    run_id = datetime.now(UTC).strftime("%H%M%S")
    containers: list[str] = []
    proxies: list[LoggendeProxy] = []
    mg: MediaGuardSim | None = None
    code = 1
    try:
        for image in (EMBY_IMAGE, JL_IMAGE, DOEL_IMAGE):
            if docker("image", "inspect", image, check=False).returncode != 0:
                log(f"image ophalen: {image}")
                docker("pull", image)
        ffmpeg: list[str] | None = None
        if args.modus == "synthetisch":
            if args.ffmpeg == "host" or (args.ffmpeg == "auto" and shutil.which("ffmpeg")):
                ffmpeg = ["ffmpeg"]
            else:
                ffmpeg = ["docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
                          "-v", f"{werk / 'bib'}:/w", "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffmpeg", JL_IMAGE]
        log(f"testbibliotheek bouwen ({args.modus})")
        manifest = bouw(args.modus, werk / "bib", Path(args.corpus) if args.modus == "corpus" else None, ffmpeg)
        bewijs.data["testbibliotheek"] = manifest
        if args.modus == "corpus":
            bewijs.check("B03-016", "corpusbestanden kloppen met het sha256-manifest",
                         all(c["klopt"] for c in manifest["corpuscontrole"]), f"{len(manifest['corpuscontrole'])} bronbestanden")
        for sub in ("emby-config", "jl-config", "jl-cache", "geheimen"):
            (werk / sub).mkdir(parents=True, exist_ok=True)
        os.chmod(werk / "geheimen", 0o700)

        # Containers (alleen op 127.0.0.1; media alleen-lezen).
        p_emby, p_jl = vrije_poort(), vrije_poort()
        naam_emby, naam_jl = f"jlb03015-emby-{run_id}", f"jlb03015-jl-{run_id}"
        docker("run", "-d", "--name", naam_emby, "-e", f"UID={os.getuid()}", "-e", f"GID={os.getgid()}",
               "-p", f"127.0.0.1:{p_emby}:8096", "-v", f"{werk / 'emby-config'}:/config",
               "-v", f"{werk / 'bib' / 'emby'}:{EMBY_ROOT}:ro", "--memory", "1536m", "--cpus", "4", EMBY_IMAGE)
        containers.append(naam_emby)
        docker("run", "-d", "--name", naam_jl, "--user", f"{os.getuid()}:{os.getgid()}", "-p", f"127.0.0.1:{p_jl}:8096",
               "-v", f"{werk / 'jl-config'}:/config", "-v", f"{werk / 'jl-cache'}:/cache",
               "-v", f"{werk / 'bib' / 'jl'}:{JL_ROOT}:ro", "--memory", "1536m", "--cpus", "4", DOEL_IMAGE)
        containers.append(naam_jl)
        emby_url, jl_url = f"http://127.0.0.1:{p_emby}", f"http://127.0.0.1:{p_jl}"
        wacht(emby_url + "/System/Info/Public")
        wacht(jl_url + "/System/Info/Public")
        emby, jl = Emby(emby_url), Jellyfin(jl_url)
        met_herhaling(emby.wizard)
        met_herhaling(jl.wizard)
        info_emby = emby.anoniem.doe("GET", "/System/Info/Public")
        info_jl = jl.anoniem.doe("GET", "/System/Info/Public")
        bewijs.data["servers"] = {"emby": {"versie": info_emby.get("Version")}, "jellyfin": {"versie": info_jl.get("Version"),
                                                                                             "product": info_jl.get("ProductName")}}
        bewijs.check("JLT-70", f"echte Emby 4.10.2.0 en {'stock Jellyfin 12.4' if DOEL_IMAGE == JL_IMAGE else 'Jelly Leon 12.x'} draaien",
                     info_emby.get("Version") == "4.10.2.0" and str(info_jl.get("Version")).startswith("12.4"),
                     f"Emby {info_emby.get('Version')}, Jellyfin {info_jl.get('Version')}")
        sleutels_waarden = {"emby": emby.sleutel("jelly-leon-overname"), "jl": jl.sleutel("jelly-leon-overname"),
                            "mg_emby": emby.sleutel("mediaguard-sim"), "mg_jl": jl.sleutel("mediaguard-sim")}
        sleutels: dict[str, Path] = {}
        for naam in ("emby", "jl"):
            pad = werk / "geheimen" / f"{naam}-api-key"
            pad.write_text(sleutels_waarden[naam] + "\n", encoding="utf-8")
            os.chmod(pad, 0o600)
            sleutels[naam] = pad
        for naam, soort in ((FILMS, "movies"), (SERIES, "tvshows")):
            emby.bibliotheek(naam, soort, f"{EMBY_ROOT}/{naam}")
            jl.bibliotheek(naam, soort, f"{JL_ROOT}/{naam}")

        items_recept = recept()
        verwacht_emby = {i.emby.pad for i in items_recept if i.emby}
        verwacht_jl = {pl.pad for i in items_recept for pl in i.jl}
        einde = time.time() + 900
        paden_emby: dict[str, dict[str, Any]] = {}
        paden_jl: dict[str, dict[str, Any]] = {}
        volgende_scan = time.time() + 45
        while time.time() < einde:
            if time.time() > volgende_scan:
                ververs(emby.admin, jl.admin)
                volgende_scan = time.time() + 90
            paden_emby = emby_paden(emby)
            paden_jl = {i["Path"][len(JL_ROOT) + 1:]: i for i in jl.items() if i.get("Path", "").startswith(JL_ROOT)}
            klaar_jl = verwacht_jl <= set(paden_jl)
            if klaar_jl and not verwacht_emby <= set(paden_emby):
                # Door Emby gebundelde versies staan alleen in de itemdetails (QA-review: zonder deze stap wachtte de lus
                # altijd de volle 15 minuten).
                paden_emby = emby_paden(emby, detail=True)
            klaar_emby = verwacht_emby <= set(paden_emby) and all(paden_emby[pd].get("ProviderIds") for pd in verwacht_emby
                                                                  if any(i.emby and i.emby.pad == pd and i.emby.nfo for i in items_recept))
            if klaar_emby and klaar_jl:
                break
            time.sleep(5)
        time.sleep(10)  # serie-/seizoensitems en NFO's laten afronden
        paden_emby = emby_paden(emby, detail=True)
        if not verwacht_emby <= set(paden_emby):
            bewijs.data["diagnose_emby"] = emby_diagnose(emby, sorted(verwacht_emby - set(paden_emby)))
        paden_jl = {i["Path"][len(JL_ROOT) + 1:]: i for i in jl.items() if i.get("Path", "").startswith(JL_ROOT)}
        bewijs.check("JLT-70", "bibliotheken gescand (alle testbestanden aanwezig)",
                     verwacht_emby <= set(paden_emby) and verwacht_jl <= set(paden_jl),
                     {"emby_ontbrekend": sorted(verwacht_emby - set(paden_emby)), "jl_ontbrekend": sorted(verwacht_jl - set(paden_jl))})
        bewijs.data["emby_afleveringen"] = {pd: {"seizoen": i.get("ParentIndexNumber"), "aflevering": i.get("IndexNumber")}
                                            for pd, i in paden_emby.items() if i.get("Type") == "Episode" and "Anime" in pd}

        # Emby-gebruikers en kijkgeschiedenis (door de harnas, via de Emby-API).
        bib_emby = {b["Name"]: b for b in emby.admin.doe("GET", "/Library/VirtualFolders/Query")["Items"]}  # type: ignore[union-attr]
        uids = {"beheerder": emby.admin_id}
        emby.tokens[emby.admin_id] = emby.admin.headers["X-Emby-Token"]  # type: ignore[union-attr]
        for naam, (beleid, config) in GEBRUIKERS.items():
            if naam == "Kim":
                beleid = {**beleid, "EnabledFolders": [bib_emby[FILMS]["Guid"], bib_emby[SERIES]["Guid"]]}
            if naam == "Gast":
                beleid = {**beleid, "EnabledFolders": [bib_emby[FILMS]["Guid"]]}
            uids[naam] = emby.gebruiker(naam, beleid, config, f"Emby-{naam}-wachtwoord-1")
        per_sleutel = {i.sleutel: i for i in items_recept}
        series_emby = {i["Name"]: i for i in emby.items(emby.admin_id) if i["Type"] == "Series"}
        spoor_log: list[str] = []
        for volgorde in ("spoor", "rest"):
            for gebruiker, sleutel, soort, waarde in KIJK:
                if (soort == "spoor") != (volgorde == "spoor"):
                    continue
                if sleutel.startswith("serie:"):
                    item = series_emby[sleutel.split(":", 1)[1]]
                else:
                    plek = per_sleutel[sleutel].emby
                    item = paden_emby.get(plek.pad)  # type: ignore[union-attr]
                    if item is None:
                        spoor_log.append(f"overgeslagen: {plek.pad} staat niet als item in Emby")  # type: ignore[union-attr]
                        continue
                zet_kijk(emby, uids[gebruiker], item, soort, waarde, spoor_log)
        bewijs.data["spoorkeuzes_gezet"] = spoor_log
        gebruikers_emby = {n: uids[n] for n in uids}
        waarheid = emby_toestand(emby, gebruikers_emby)
        bewijs.data["emby_kijkgegevens_aantallen"] = {n: len(v) for n, v in waarheid.items()}
        bewijs.check("JLT-70", "≥ 5 Emby-gebruikers (beheerder, 2 volwassenen, kind, gast) met kijkgeschiedenis",
                     len(waarheid) >= 5 and all(waarheid.values()), bewijs.data["emby_kijkgegevens_aantallen"])
        soorten = Counter()
        for per in waarheid.values():
            for e in per.values():
                soorten["gezien"] += e["gezien"] and e["aantal"] > 0 and e["laatst"] is not None
                soorten["hervatpunt"] += e["positie"] > 0
                soorten["favoriet"] += e["favoriet"]
                soorten["beoordeling"] += e["beoordeling"] is not None or e["vind_ik_leuk"] is not None
        bewijs.data["emby_kijkgegevens_soorten"] = dict(soorten)
        ed = paden_emby.get(per_sleutel["ed"].emby.pad)  # type: ignore[union-attr]
        if ed is not None:  # Waar laat Emby een "vind ik leuk" zien? (lijst met de velden van de tool én itemdetail)
            detail = emby.admin.doe("GET", f"/Users/{uids['Bram']}/Items/{ed['Id']}")  # type: ignore[union-attr]
            lijst = emby.admin.doe("GET", f"/Users/{uids['Bram']}/Items", {  # type: ignore[union-attr]
                "Ids": ed["Id"], "Fields": "UserDataPlayCount,UserDataLastPlayedDate", "EnableUserData": "true"})["Items"]
            bewijs.data["beoordeling_diagnose"] = {"detail_userdata": detail.get("UserData"),
                                                   "lijst_userdata": lijst[0].get("UserData") if lijst else None}
        bewijs.check("JLT-70", "Emby bevat echt gezien-status (met datum en aantal), hervatpunten en favorieten",
                     soorten["gezien"] > 0 and soorten["hervatpunt"] > 0 and soorten["favoriet"] > 0, dict(soorten))

        # Proxy's en MediaGuard-simulator.
        proxy_emby = LoggendeProxy("127.0.0.1", p_emby, "emby")
        proxy_jl = LoggendeProxy("127.0.0.1", p_jl, "jelly-leon")
        proxies += [proxy_emby, proxy_jl]
        mg = MediaGuardSim(emby_url, sleutels_waarden["mg_emby"], jl_url, sleutels_waarden["mg_jl"])
        mg.start()
        tool = Tool(uitvoer, proxy_emby.url, proxy_jl.url, sleutels)

        def emby_gelijk_rond(beschrijving: str, functie: Any) -> Any:
            voor = emby_toestand(emby, gebruikers_emby)
            resultaat = functie()
            na = emby_toestand(emby, gebruikers_emby)
            bewijs.check("JLT-73", f"Emby-kijkgegevens per gebruiker identiek vóór en na: {beschrijving}", voor == na)
            return resultaat

        # 0. Inventaris (D07) en exportarchief vóór.
        _, inventaris = emby_gelijk_rond("inventaris", lambda: tool.draai("inventaris", "--emby-url", proxy_emby.url,
                                                                         "--emby-sleutel-bestand", str(sleutels["emby"]),
                                                                         "--werkmap", str(tool.werkmap)))
        bewijs.check("JLT-70", "inventaris (D07-model): versie, gebruikers, bibliotheken, plugins", inventaris.get("gebruikers") == 5,
                     inventaris)
        archief_voor = uitvoer / "archief" / "emby-kijkgegevens-voor.json"
        _, export_voor = emby_gelijk_rond("export vóór", lambda: tool.draai(
            "export", "--emby-url", proxy_emby.url, "--emby-sleutel-bestand", str(sleutels["emby"]), "--uitvoer", str(archief_voor)))

        # 1. Proefrun (droog).
        merk_jl = proxy_jl.markeer()
        _, proef1 = emby_gelijk_rond("proefrun 1", lambda: tool.draai("proefrun", *tool.basis()))
        schrijf_jl = [r for r in proxy_jl.sinds(merk_jl) if r["methode"] != "GET"]
        bewijs.check("JLT-70", "proefrun schrijft niets in Jelly Leon", not schrijf_jl, f"{len(schrijf_jl)} niet-GET-verzoeken")
        bewijs.check("JLT-72", "proefrun: alle Emby-kijkgegevens verantwoord", proef1["verantwoord"], proef1["totaal"])

        # 2. Overzetten na (gesimuleerd) akkoord op het plan.
        akkoord1 = tool.akkoord(proef1, "plan")
        merk_jl = proxy_jl.markeer()
        _, over1 = emby_gelijk_rond("overzetting 1", lambda: tool.draai("overzetten", *tool.basis(), "--akkoord", str(akkoord1)))
        rapport1 = rapport_van(over1)
        geschreven1 = [r for r in proxy_jl.sinds(merk_jl) if r["methode"] != "GET"]
        bewijs.data["overzetting_1"] = {"schrijfacties_tool": over1["schrijfacties"], "proxy_niet_get": len(geschreven1),
                                        "routes": dict(Counter(r["pad"].split("/")[1] + ("/UserData" if r["pad"].endswith("/UserData") else "")
                                                               for r in geschreven1)), "totaal": over1["totaal"]}
        bewijs.check("JLT-70", "alle Jelly Leon-schrijfacties via de officiële routes (Users/New, Policy, Configuration, UserData)",
                     all(r["pad"] == "/Users/New" or r["pad"].endswith(("/Policy", "/UserData")) or r["pad"] == "/Users/Configuration"
                         for r in geschreven1), sorted({r["pad"].rsplit("/", 1)[-1] for r in geschreven1}))

        archief_na1 = uitvoer / "archief" / "emby-kijkgegevens-na-overzetting-1.json"
        tool.draai("export", "--emby-url", proxy_emby.url, "--emby-sleutel-bestand", str(sleutels["emby"]), "--uitvoer", str(archief_na1))
        code_vgl, vgl = tool.draai("vergelijk-export", str(archief_voor), str(archief_na1), verwacht=None)
        bewijs.check("JLT-73", "exportarchief vóór en na de overzetting inhoudelijk identiek (vergelijk-export)",
                     code_vgl == 0 and vgl.get("identiek") is True, vgl.get("verschillen"))

        # 3. Onafhankelijke controle tegen de grondwaarheid.
        jl_gebruikers = jl.gebruikers()
        naar_jl = {"beheerder": "jlbeheer", "Anna": "Anna", "Bram": "Bram", "Kim": "Kim", "Gast": "Gast"}
        afhandel = afhandel_per_gebruiker(rapport1)
        controleer_overname(bewijs, "JLT-70", items_recept, waarheid, jl, jl_gebruikers, naar_jl, afhandel, paden_jl)
        controleer_rechten(bewijs, emby, jl, jl_gebruikers, uids, naar_jl, items_recept)
        controleer_rapport(bewijs, rapport1, over1)

        # 4. Tweede run zonder wijziging: 0 schrijfacties en inhoudelijk identiek rapport (JLT-71).
        merk_jl = proxy_jl.markeer()
        _, proef2 = emby_gelijk_rond("proefrun 2", lambda: tool.draai("proefrun", *tool.basis()))
        akkoord2 = tool.akkoord(proef2, "plan")
        _, over2 = emby_gelijk_rond("overzetting 2", lambda: tool.draai("overzetten", *tool.basis(), "--akkoord", str(akkoord2)))
        geschreven2 = [r for r in proxy_jl.sinds(merk_jl) if r["methode"] != "GET"]
        bewijs.check("JLT-71", "tweede run: 0 schrijfacties naar Jelly Leon (proxy) en 0 gepland",
                     not geschreven2 and over2["schrijfacties"] == 0 and proef2["plan_schrijfacties"] == 0,
                     {"proxy": len(geschreven2), "tool": over2["schrijfacties"], "gepland": proef2["plan_schrijfacties"]})
        bewijs.check("JLT-71", "tweede run: inhoudelijk identiek rapport (inhoud-sha256)",
                     over2["inhoud_sha256"] == over1["inhoud_sha256"], {"run1": over1["inhoud_sha256"], "run2": over2["inhoud_sha256"]})

        # 5. Delta: Emby-wijzigingen bij twee gebruikers + een eigen, nieuwere Jelly Leon-wijziging (JLT-71).
        delta = [("Anna", "pioneer_e4", "gezien", ("2026-11-01T20:00:00Z", 1)),
                 ("Anna", "pioneer_e3", "positie", (0.8, "2026-11-01T21:00:00Z", 0)),
                 ("Bram", "sintel", "favoriet", True),
                 ("Kim", "llama", "positie", (0.3, "2026-11-02T08:00:00Z", 0))]
        for gebruiker, sleutel, soort, waarde in delta:
            zet_kijk(emby, uids[gebruiker], paden_emby[per_sleutel[sleutel].emby.pad], soort, waarde, [])  # type: ignore[union-attr]
        emby.admin.doe("DELETE", f"/Users/{uids['Bram']}/FavoriteItems/{paden_emby[per_sleutel['bbb'].emby.pad]['Id']}")  # type: ignore[union-attr]
        kim_jl = jl_gebruikers["Kim"]["Id"]
        llama_jl = paden_jl[per_sleutel["llama"].jl[0].pad]["Id"]
        jl.admin.doe("POST", f"/UserItems/{llama_jl}/UserData", {"userId": kim_jl},  # type: ignore[union-attr]
                     body={"PlaybackPositionTicks": 123_456_789, "LastPlayedDate": "2026-11-03T08:00:00.0000000Z"})
        waarheid_delta = emby_toestand(emby, gebruikers_emby)
        merk_jl = proxy_jl.markeer()
        _, proef3 = emby_gelijk_rond("proefrun delta", lambda: tool.draai("proefrun", *tool.basis()))
        akkoord3 = tool.akkoord(proef3, "plan")
        _, over3 = emby_gelijk_rond("overzetting delta", lambda: tool.draai("overzetten", *tool.basis(), "--akkoord", str(akkoord3)))
        geschreven3 = [r for r in proxy_jl.sinds(merk_jl) if r["methode"] != "GET"]
        anna_jl, bram_jl = jl_gebruikers["Anna"]["Id"], jl_gebruikers["Bram"]["Id"]
        verwacht_delta = {(anna_jl, paden_jl[per_sleutel["pioneer_e4"].jl[0].pad]["Id"]),
                          (anna_jl, paden_jl[per_sleutel["pioneer_e3"].jl[0].pad]["Id"]),
                          (bram_jl, paden_jl[per_sleutel["sintel"].jl[0].pad]["Id"])}
        gezien_delta = {(r["query"].get("userId"), r["pad"].split("/")[2]) for r in geschreven3 if r["pad"].endswith("/UserData")}
        bewijs.check("JLT-71", "delta-run neemt precies de Emby-wijzigingen over (3 schrijfacties)",
                     gezien_delta == verwacht_delta and len(geschreven3) == 3,
                     {"verwacht": len(verwacht_delta), "geschreven": len(geschreven3)})
        kim_llama = kijk(next(i for i in jl.items(kim_jl) if i["Id"] == llama_jl)["UserData"])
        bewijs.check("JLT-71", "nieuwere Jelly Leon-waarde (hervatpunt Kim) niet overschreven", kim_llama["positie"] == 123_456_789,
                     kim_llama["positie"])
        rapport3 = rapport_van(over3)
        bram_redenen = Counter(pt["reden"] for pt in afhandel_per_gebruiker(rapport3)["Bram"])
        kim_redenen = Counter(pt["reden"] for pt in afhandel_per_gebruiker(rapport3)["Kim"])
        bewijs.check("JLT-71", "in Emby verwijderde favoriet staat ter beslissing op de afhandellijst",
                     bram_redenen["favoriet_verwijderd_in_emby"] == 1, dict(bram_redenen))
        bewijs.check("JLT-71", "hervatpunt 'Jelly Leon nieuwer' verklaard in het rapport", kim_redenen["hervatpunt_jelly_leon_nieuwer"] == 1,
                     dict(kim_redenen))
        controleer_overname(bewijs, "JLT-71", items_recept, waarheid_delta, jl, jl_gebruikers, naar_jl,
                            afhandel_per_gebruiker(rapport3), paden_jl, uitzonderingen={("Kim", per_sleutel["llama"].jl[0].pad)})

        # 6. Afgebroken run (kill na 2 schrijfacties, vóór 'klaar') en hervatten zonder dubbele schrijfacties (JLT-71).
        kill = [("Gast", "sintel", "gezien", ("2026-11-04T20:00:00Z", 1)),
                ("beheerder", "testserie_s2e2", "gezien", ("2026-11-04T21:00:00Z", 1)),
                ("Anna", "llama", "favoriet", True),
                ("Bram", "llama", "gezien", ("2026-11-05T20:00:00Z", 1)),
                ("Kim", "testserie_s1e2", "positie", (0.6, "2026-11-05T08:00:00Z", 0))]
        for gebruiker, sleutel, soort, waarde in kill:
            zet_kijk(emby, uids[gebruiker], paden_emby[per_sleutel[sleutel].emby.pad], soort, waarde, [])  # type: ignore[union-attr]
        waarheid_kill = emby_toestand(emby, gebruikers_emby)
        _, proef4 = tool.draai("proefrun", *tool.basis())
        akkoord4 = tool.akkoord(proef4, "plan")
        merk_jl = proxy_jl.markeer()
        code_kill, _ = tool.draai("overzetten", *tool.basis(), "--akkoord", str(akkoord4), "--testhaak-afbreken", "2", verwacht=None)
        na_kill = [r for r in proxy_jl.sinds(merk_jl) if r["pad"].endswith("/UserData") and r["methode"] == "POST"]
        bewijs.check("JLT-71", "afgebroken run: proces hard gestopt na 2 schrijfacties (exit 137)",
                     code_kill == 137 and len(na_kill) == 2, {"exit": code_kill, "schrijfacties": len(na_kill)})
        _, over4 = tool.draai("overzetten", *tool.basis(), "--akkoord", str(akkoord4))
        alle = [r for r in proxy_jl.sinds(merk_jl) if r["pad"].endswith("/UserData") and r["methode"] == "POST"]
        per_doel = Counter((r["query"].get("userId"), r["pad"].split("/")[2]) for r in alle)
        bewijs.check("JLT-71", "hervatten: elke schrijfactie precies één keer (geen dubbele), samen het hele plan",
                     all(v == 1 for v in per_doel.values()) and len(per_doel) == proef4["plan_schrijfacties"],
                     {"schrijfacties": len(alle), "gepland": proef4["plan_schrijfacties"], "max_per_item": max(per_doel.values() or [0])})
        rapport4 = rapport_van(over4)
        bewijs.check("JLT-71", "herstel herkende de schrijfactie van vóór de kill als al uitgevoerd",
                     (rapport4.get("run") or {}).get("herstel", {}).get("al_uitgevoerd") == 1, (rapport4.get("run") or {}).get("herstel"))
        controleer_overname(bewijs, "JLT-71", items_recept, waarheid_kill, jl, jl_gebruikers, naar_jl,
                            afhandel_per_gebruiker(rapport4), paden_jl, uitzonderingen={("Kim", per_sleutel["llama"].jl[0].pad)},
                            label="na kill en hervatten")

        # 6b. Verkeerd doel (HARDE EIS, QA-review): het Jelly Leon-adres wijst per vergissing naar Emby (via een ander adres,
        # localhost i.p.v. 127.0.0.1), met de Emby-sleutel als "Jelly Leon-sleutel". Gemeten: Emby 4.10.2.0 accepteert de
        # Jellyfin-header `Authorization: MediaBrowser Token=…`, dus alleen de doelcontrole van de tool houdt dit tegen.
        # Verwacht: proefrun en overzetten exit 9; van de doelkant alleen het anonieme GET /System/Info/Public.
        merk_emby = proxy_emby.markeer()
        verkeerd_adres = proxy_emby.url.replace("127.0.0.1", "localhost")

        def verkeerd_doel() -> tuple[int, int]:
            args = ["--emby-url", proxy_emby.url, "--emby-sleutel-bestand", str(sleutels["emby"]), "--jl-url", verkeerd_adres,
                    "--jl-sleutel-bestand", str(sleutels["emby"]), "--werkmap", str(uitvoer / "werkmap-verkeerd-doel"),
                    "--pad", f"{EMBY_ROOT}={JL_ROOT}"]
            c_proef, _ = tool.draai("proefrun", *args, verwacht=None)
            c_over, _ = tool.draai("overzetten", *args, "--akkoord", str(akkoord4), verwacht=None)
            return c_proef, c_over

        c_proef, c_over = emby_gelijk_rond("verkeerd doel (Jelly Leon-adres wijst naar Emby)", verkeerd_doel)
        doelkant = proxy_emby.sinds(merk_emby)
        bewijs.check("JLT-73", "verkeerd doel (Jelly Leon-adres wijst naar Emby): proefrun en overzetten geweigerd (exit 9), "
                     "alleen GET /System/Info/Public zonder sleutel, 0 niet-GET",
                     c_proef == 9 and c_over == 9 and [(r["methode"], r["pad"]) for r in doelkant] == [("GET", "/System/Info/Public")] * 2,
                     {"exit": [c_proef, c_over], "verzoeken": [(r["methode"], r["pad"], r["status"]) for r in doelkant]})

        # 7. Verkeersmeting en testhaak (JLT-73).
        code_haak, haak = emby_gelijk_rond("testhaak schrijfpoging", lambda: tool.draai(
            "testhaak-schrijfpoging", "--emby-url", proxy_emby.url, "--emby-sleutel-bestand", str(sleutels["emby"]), verwacht=None))
        bewijs.check("JLT-73", "opzettelijke POST/DELETE vanuit de tool geweigerd vóór het netwerk",
                     code_haak == 0 and haak.get("netwerkverzoeken") == 0 and all(x["geweigerd"] for x in haak.get("pogingen", [])),
                     haak.get("pogingen"))
        methodes = Counter(r["methode"] for r in proxy_emby.regels)
        bewijs.check("JLT-73", "0 verzoeken anders dan GET naar Emby (loggende proxy, alle runs)",
                     set(methodes) == {"GET"}, dict(methodes))
        from emby_overname.emby import WITTE_LIJST_GET  # noqa: PLC0415

        buiten = sorted({r["pad"] for r in proxy_emby.regels if not any(w.match(r["pad"]) for w in WITTE_LIJST_GET)})
        bewijs.check("JLT-73", "alleen routes van de witte lijst", not buiten, buiten[:10])
        bewijs.check("JLT-73", "geen sleutel in een URL", not any(r["sleutel_in_url"] for r in proxy_emby.regels + proxy_jl.regels))
        bewijs.data["verkeer"] = {"emby": {"verzoeken": len(proxy_emby.regels), "methodes": dict(methodes)},
                                  "jelly_leon": dict(Counter(r["methode"] for r in proxy_jl.regels))}

        # 8. Archief na, vergelijking, herimport-voorbereiding.
        archief_na = uitvoer / "archief" / "emby-kijkgegevens-na.json"
        tool.draai("export", "--emby-url", proxy_emby.url, "--emby-sleutel-bestand", str(sleutels["emby"]), "--uitvoer", str(archief_na))
        bewijs.data["archief"] = {"voor": export_voor, "na_sha256": (archief_na.with_name(archief_na.name + ".sha256")).read_text().split()[0]}

        # 9. Cutover-akkoord (alleen met akkoord op elk verschil).
        cut = tool.akkoord(over4, "cutover")
        code_cut, cutover = tool.draai("akkoord-controle", "--rapport", over4["rapport"], "--akkoord", str(cut), verwacht=None)
        onvolledig = json.loads(cut.read_text())
        onvolledig["verschillen"] = onvolledig["verschillen"][1:]
        cut2 = uitvoer / "akkoord-cutover-onvolledig.json"
        cut2.write_text(json.dumps(onvolledig))
        code_cut2, _ = tool.draai("akkoord-controle", "--rapport", over4["rapport"], "--akkoord", str(cut2), verwacht=None)
        bewijs.check("JLT-70", "overstap alleen met akkoord op elk verschil (volledig: toegestaan; één ontbreekt: geweigerd)",
                     code_cut == 0 and cutover["overstap_toegestaan"] and code_cut2 == 6, {"volledig": code_cut, "onvolledig": code_cut2})

        # 10. Clientprotocol (simulator): inloggen met een nieuw wachtwoord en hervatten (JLT-70).
        controleer_clients(bewijs, jl, jl_gebruikers, naar_jl, waarheid_kill, items_recept, paden_jl)

        # 11. MediaGuard-simulator: kijkpauze bij een sessie op Emby én op Jelly Leon; Emby-koppeling nooit weg (JLT-73).
        controleer_mediaguard(bewijs, mg, emby, jl, uids, jl_gebruikers, paden_emby, paden_jl, per_sleutel)

        # 11b. Webclient in een echte browser (alleen met --browser): inloggen met het nieuwe wachtwoord uit stap 10 en
        # hervatten op het juiste punt (JLT-70, clientdeel). De Android-emulator volgt apart (B03-016-harnas).
        if args.browser != "geen":
            controleer_browser(bewijs, jl, jl_gebruikers, naar_jl, waarheid_kill, items_recept, paden_jl, args.browser)

        # 12. Sleutels nergens (logs, rapporten, exports, proxylogs).
        proxy_emby.schrijf(str(uitvoer / "proxy-emby.jsonl"))
        proxy_jl.schrijf(str(uitvoer / "proxy-jelly-leon.jsonl"))
        lekken = []
        for pad in uitvoer.rglob("*"):
            if pad.is_file() and "geheimen" not in pad.parts and "bib" not in pad.parts and "config" not in pad.name \
                    and not any(d in pad.parts for d in ("emby-config", "jl-config", "jl-cache", "jl2-config", "jl2-cache")):
                inhoud = pad.read_bytes()
                lekken += [f"{pad.name}:{n}" for n, w in sleutels_waarden.items() if w.encode() in inhoud]
        bewijs.check("JLT-73", "geen API-sleutel in logs, rapporten, exports of proxylogs", not lekken, lekken[:10])

        # 13. Herimport uit het archief op een lege Jellyfin (Emby gestopt) — controlelijst §10.9.2 stap 4.
        mg.stop()
        docker("stop", "-t", "20", naam_emby)
        docker("stop", "-t", "20", naam_jl)
        for sub in ("jl2-config", "jl2-cache"):
            (werk / sub).mkdir(exist_ok=True)
        p_jl2 = vrije_poort()
        naam_jl2 = f"jlb03015-jl2-{run_id}"
        docker("run", "-d", "--name", naam_jl2, "--user", f"{os.getuid()}:{os.getgid()}", "-p", f"127.0.0.1:{p_jl2}:8096",
               "-v", f"{werk / 'jl2-config'}:/config", "-v", f"{werk / 'jl2-cache'}:/cache",
               "-v", f"{werk / 'bib' / 'jl'}:{JL_ROOT}:ro", "--memory", "1536m", "--cpus", "4", DOEL_IMAGE)
        containers.append(naam_jl2)
        jl2_url = f"http://127.0.0.1:{p_jl2}"
        wacht(jl2_url + "/System/Info/Public")
        jl2 = Jellyfin(jl2_url)
        met_herhaling(jl2.wizard)
        sleutel_jl2 = jl2.sleutel("jelly-leon-overname")
        (werk / "geheimen" / "jl-api-key").write_text(sleutel_jl2 + "\n")
        sleutels_waarden["jl2"] = sleutel_jl2
        for naam, soort in ((FILMS, "movies"), (SERIES, "tvshows")):
            jl2.bibliotheek(naam, soort, f"{JL_ROOT}/{naam}")
        einde = time.time() + 600
        volgende_scan = time.time() + 45
        while time.time() < einde and not verwacht_jl <= {i["Path"][len(JL_ROOT) + 1:] for i in jl2.items() if i.get("Path")}:
            if time.time() > volgende_scan:
                ververs(jl2.admin)
                volgende_scan = time.time() + 90
            time.sleep(5)
        time.sleep(10)
        gescand2 = {i["Path"][len(JL_ROOT) + 1:] for i in jl2.items() if i.get("Path")}
        bewijs.check("JLT-70", "herimport: lege Jellyfin heeft de bibliotheek gescand", verwacht_jl <= gescand2,
                     sorted(verwacht_jl - gescand2)[:10])
        tool2 = Tool(uitvoer, "", jl2_url, sleutels)
        werk2 = uitvoer / "werkmap-herimport"
        _, proef5 = tool2.draai("proefrun", *tool2.basis(archief=archief_na, werkmap=werk2))
        akkoord5 = tool2.akkoord(proef5, "plan")
        _, over5 = tool2.draai("overzetten", *tool2.basis(archief=archief_na, werkmap=werk2), "--akkoord", str(akkoord5))
        bewijs.check("JLT-70", "herimport uit het archief op een lege Jellyfin (Emby gestopt): verantwoord", over5["verantwoord"],
                     over5["totaal"])
        controleer_overname(bewijs, "JLT-70", items_recept, waarheid_kill, jl2, jl2.gebruikers(), naar_jl,
                            afhandel_per_gebruiker(rapport_van(over5)), {i["Path"][len(JL_ROOT) + 1:]: i for i in jl2.items()},
                            label="herimport uit archief")
        bewijs.data["rapporten"] = {"proefrun_1": proef1["rapport"], "overzetting_1": over1["rapport"], "delta": over3["rapport"],
                                    "na_kill": over4["rapport"], "herimport": over5["rapport"]}
        code = 0 if all(c["ok"] for c in bewijs.data["controles"]) else 1
    except Exception as fout:  # noqa: BLE001 - alles vastleggen in het bewijs
        import traceback

        bewijs.check("harnas", "proefrun zonder onverwachte fout", False, f"{fout}\n{traceback.format_exc()[-3000:]}")
        code = 1
    finally:
        if mg is not None:
            mg.stop()
            bewijs.data["mediaguard_sim"] = mg.samenvatting()
        for proxy in proxies:
            proxy.stop()
        bewijs.schrijf(uitvoer / "bewijs.json")
        if not args.behoud:
            for naam in containers:
                docker("rm", "-f", "-v", naam, check=False)
            if werk.exists():
                subprocess.run(["docker", "run", "--rm", "--user", "0:0", "--network", "none", "-v", f"{werk}:/w",
                                "--entrypoint", "/bin/rm", JL_IMAGE, "-rf", "/w/emby-config", "/w/jl-config", "/w/jl-cache",
                                "/w/jl2-config", "/w/jl2-cache"], capture_output=True, check=False, timeout=300)
                shutil.rmtree(werk, ignore_errors=True)
        log(f"klaar: {bewijs.data.get('samenvatting')} → {uitvoer / 'bewijs.json'}")
    return code


# --- controles -----------------------------------------------------------------------------------------------------

def controleer_overname(bewijs: Bewijs, test: str, items: list[Item], waarheid: dict[str, dict[str, dict[str, Any]]], jl: Jellyfin,
                        jl_gebruikers: dict[str, dict[str, Any]], naar_jl: dict[str, str], afhandel: dict[str, list[dict[str, Any]]],
                        paden_jl: dict[str, dict[str, Any]], uitzonderingen: set[tuple[str, str]] | None = None,
                        label: str = "") -> None:
    """Grondwaarheid uit het recept: elk Emby-item met kijkgegevens is exact overgezet (gekoppeld) of staat met een
    toegestane reden op de afhandellijst; geen enkele kijkwaarde belandt op een verkeerd Jelly Leon-item."""
    per_emby_pad = {i.emby.pad: i for i in items if i.emby}
    serie_naar_jl = {f"{SERIES}/{t}": f"{SERIES}/{t}" for t in ("B03 Testserie", "B03 Anime", "Pioneer One")}
    stats = Counter()
    fouten: list[str] = []
    for gebruiker, per in waarheid.items():
        jl_naam = naar_jl[gebruiker]
        jl_uid = jl_gebruikers[jl_naam]["Id"]
        jl_nu = jl_toestand(jl, jl_uid)
        afhandel_ids = {(pt.get("item") or {}).get("emby_id"): pt["reden"] for pt in afhandel.get(gebruiker, []) if pt["soort"] == "item"}
        verwachte_doelen: set[str] = set()
        for pt in afhandel.get(gebruiker, []):
            # Ter beslissing: in Emby verwijderd/teruggezet, Jelly Leon behoudt het (nooit stil gewist) — toegestaan.
            if pt["reden"] in ("favoriet_verwijderd_in_emby", "gezien_teruggezet_in_emby"):
                pad_emby = ((pt.get("item") or {}).get("pad_emby") or "")[len(EMBY_ROOT) + 1:]
                bron = per_emby_pad.get(pad_emby)
                if bron is not None:
                    verwachte_doelen.add(bron.jl_doel or bron.jl[0].pad)
                elif pad_emby in serie_naar_jl:
                    verwachte_doelen.add(serie_naar_jl[pad_emby])
        for pad, e in per.items():
            item = per_emby_pad.get(pad)
            if item is None and pad in serie_naar_jl:
                doel_pad, verwacht = serie_naar_jl[pad], "gekoppeld"
            elif item is None:
                fouten.append(f"{gebruiker}: onbekend Emby-pad {pad}")
                continue
            else:
                doel_pad = item.jl_doel or (item.jl[0].pad if item.jl else None)
                verwacht = item.verwacht
            j = jl_nu.get(doel_pad) if doel_pad else None
            gelijk = j is not None and _gelijk(e, j)
            if (gebruiker, doel_pad) in (uitzonderingen or set()):
                stats["uitzondering_jl_nieuwer"] += 1
                verwachte_doelen.add(doel_pad)  # type: ignore[arg-type]
                continue
            if verwacht == "gekoppeld" or (verwacht == "onzeker" and e["id"] not in afhandel_ids):
                if gelijk:
                    stats["exact_overgezet"] += 1
                    verwachte_doelen.add(doel_pad)  # type: ignore[arg-type]
                elif e["id"] in afhandel_ids and afhandel_ids[e["id"]] == "niet_zichtbaar_in_jelly_leon":
                    stats["afhandellijst"] += 1
                else:
                    fouten.append(f"{gebruiker}: {pad} niet exact overgezet (Emby {e}, Jelly Leon {j})")
            else:
                if e["id"] in afhandel_ids and afhandel_ids[e["id"]] in item.redenen:  # type: ignore[union-attr]
                    stats["afhandellijst"] += 1
                else:
                    fouten.append(f"{gebruiker}: {pad} niet met een verwachte reden op de afhandellijst "
                                  f"({afhandel_ids.get(e['id'])}, verwacht {item.redenen})")  # type: ignore[union-attr]
        # Geen kijkwaarde op een item dat niet als doel verwacht is (geen verkeerde koppeling).
        for pad, j in jl_nu.items():
            if heeft(j, j["type"] not in AFSPEELBAAR) and pad not in verwachte_doelen:
                fouten.append(f"{gebruiker}: onverwachte kijkgegevens op Jelly Leon-item {pad}")
    totaal = sum(len(v) for v in waarheid.values())
    bewijs.check(test, f"gezien (datum, aantal), hervatpunten (ticks exact), favorieten: 100 % van de koppelbare items {label}".strip(),
                 not fouten and stats["exact_overgezet"] > 0, {"stats": dict(stats), "emby_items_met_kijkgegevens": totaal,
                                                               "fouten": fouten[:15]})
    bewijs.check("JLT-72", f"0 stil weggelaten: overgezet + afhandellijst = alle Emby-items met kijkgegevens {label}".strip(),
                 sum(stats.values()) == totaal and not fouten, {"som": sum(stats.values()), "totaal": totaal})


def _gelijk(e: dict[str, Any], j: dict[str, Any]) -> bool:
    if e["type"] not in AFSPEELBAAR:
        return e["favoriet"] == j["favoriet"] and (e["beoordeling"] is None or e["beoordeling"] == j["beoordeling"])
    basis = (e["gezien"] == j["gezien"] and e["aantal"] == j["aantal"] and zelfde_tijd(e["laatst"], j["laatst"])
             and e["positie"] == j["positie"] and e["favoriet"] == j["favoriet"])
    if e["beoordeling"] is not None:
        basis = basis and e["beoordeling"] == j["beoordeling"]
    elif e["vind_ik_leuk"] is not None:
        basis = basis and e["vind_ik_leuk"] == j["vind_ik_leuk"]
    return basis


def controleer_rechten(bewijs: Bewijs, emby: Emby, jl: Jellyfin, jl_gebruikers: dict[str, dict[str, Any]], uids: dict[str, str],
                       naar_jl: dict[str, str], items: list[Item]) -> None:
    assert jl.admin
    bib_jl = {b["Name"]: b["ItemId"] for b in jl.admin.doe("GET", "/Library/VirtualFolders")}
    kim = jl.admin.doe("GET", f"/Users/{jl_gebruikers['Kim']['Id']}")["Policy"]
    gast = jl.admin.doe("GET", f"/Users/{jl_gebruikers['Gast']['Id']}")["Policy"]
    anna = jl.admin.doe("GET", f"/Users/{jl_gebruikers['Anna']['Id']}")
    bewijs.check("JLT-70", "kind: bibliotheken, leeftijdsgrens, geblokkeerde tag, geen toegang buitenshuis en geen downloads",
                 kim["EnableAllFolders"] is False and sorted(kim["EnabledFolders"]) == sorted(bib_jl.values())
                 and kim.get("MaxParentalRating") is not None and kim["BlockedTags"] == ["Horror"]
                 and kim["EnableRemoteAccess"] is False and kim["EnableContentDownloading"] is False,
                 {k: kim.get(k) for k in ("EnableAllFolders", "MaxParentalRating", "BlockedTags", "EnableRemoteAccess",
                                          "EnableContentDownloading")})
    bewijs.check("JLT-70", "gast: alleen Films", gast["EnableAllFolders"] is False and gast["EnabledFolders"] == [bib_jl[FILMS]],
                 gast["EnabledFolders"])
    bewijs.check("JLT-70", "taal- en ondertitelvoorkeuren overgezet (Anna)",
                 anna["Configuration"].get("SubtitleLanguagePreference") == "dut" and anna["Configuration"].get("SubtitleMode") == "Always",
                 {k: anna["Configuration"].get(k) for k in ("AudioLanguagePreference", "SubtitleLanguagePreference", "SubtitleMode")})
    beheer = jl.admin.doe("GET", f"/Users/{jl_gebruikers['jlbeheer']['Id']}")["Policy"]
    bewijs.check("JLT-70", "beheerder blijft beheerder; overige gebruikers geen beheerder",
                 beheer["IsAdministrator"] and not any(jl.admin.doe("GET", f"/Users/{jl_gebruikers[n]['Id']}")["Policy"]["IsAdministrator"]
                                                       for n in ("Anna", "Bram", "Kim", "Gast")))
    # Zichtbaarheid per gebruiker (onafhankelijk via paden): Jelly Leon nooit ruimer dan Emby.
    emby_naar_jl_pad = {}
    for i in items:
        if i.emby and i.jl:
            for pl in i.jl:
                emby_naar_jl_pad.setdefault(pl.pad, set()).add(i.emby.pad)
    ruimer: dict[str, list[str]] = {}
    for gebruiker, uid in uids.items():
        e_vis = emby_zichtbare_paden(emby, uid)
        j_uid = jl_gebruikers[naar_jl[gebruiker]]["Id"]
        j_vis = {i["Path"][len(JL_ROOT) + 1:] for i in jl.items(j_uid) if i.get("Path", "").startswith(JL_ROOT)}
        te_veel = sorted(pd for pd in j_vis if pd in emby_naar_jl_pad and not (emby_naar_jl_pad[pd] & e_vis))
        if te_veel:
            ruimer[gebruiker] = te_veel
    bewijs.check("JLT-70", "geen gebruiker (ook het kind niet) ziet in Jelly Leon iets wat hij of zij in Emby niet mocht zien",
                 not ruimer, ruimer)
    # Wachtwoorden niet overgezet: het Emby-wachtwoord werkt niet in Jelly Leon.
    status = jl.anoniem.status("POST", "/Users/AuthenticateByName", body={"Username": "Anna", "Pw": "Emby-Anna-wachtwoord-1"})
    leeg = jl.anoniem.status("POST", "/Users/AuthenticateByName", body={"Username": "Kim", "Pw": ""})
    bewijs.check("JLT-70", "wachtwoorden niet overgezet (Emby-wachtwoord en leeg wachtwoord geweigerd)", status == 401 and leeg == 401,
                 {"emby_wachtwoord": status, "leeg": leeg})


def controleer_rapport(bewijs: Bewijs, rapport: dict[str, Any], samenvatting: dict[str, Any]) -> None:
    map_pad = Path(samenvatting["map"])
    from emby_overname.hulp import sha256_bestand  # noqa: PLC0415

    som = (map_pad / "rapport.json.sha256").read_text().split()[0]
    html = (map_pad / "rapport.html").read_text(encoding="utf-8")
    bewijs.check("JLT-70", "vóór/na-rapport per gebruiker: JSON met sha256, Markdown en HTML met akkoordveld",
                 som == sha256_bestand(map_pad / "rapport.json") and (map_pad / "rapport.md").is_file()
                 and "name='verschil'" in html and "Akkoord" in html and len(rapport["toestand"]["gebruikers"]) == 5)
    wachtwoord = [g["emby_naam"] for g in rapport["toestand"]["gebruikers"]
                  if any(p["reden"] == "wachtwoord_niet_overgezet" for p in g["afhandellijst"])]
    bewijs.check("JLT-70", "rapport noemt per nieuwe gebruiker dat het wachtwoord niet is overgezet", sorted(wachtwoord) == ["Anna", "Bram",
                                                                                                                     "Gast", "Kim"], wachtwoord)
    sporen = [p for g in rapport["toestand"]["gebruikers"] for p in g["afhandellijst"] if p["soort"] == "spoorkeuze"]
    kort = [p for p in sporen if "Sintel Kort" in ((p.get("item") or {}).get("titel") or "")]
    bewijs.check("JLT-72", "spoorkeuze bij een gewijzigd bestand (zelfde pad, andere grootte) niet overgezet en wel gemeld",
                 bool(kort) and all(p["reden"] == "ander_bestand" for p in kort),
                 [(p["reden"], (p.get("item") or {}).get("titel")) for p in sporen])
    bewijs.data["spoorkeuzes_rapport"] = [{"reden": p["reden"], "titel": (p.get("item") or {}).get("titel"), "uitleg": p["uitleg"]}
                                          for p in sporen]
    beoordelingen = rapport["toestand"]["totaal"]["beoordelingen"]
    bewijs.data["beoordelingen"] = beoordelingen
    redenen = Counter(p["reden"] for g in rapport["toestand"]["gebruikers"] for p in g["afhandellijst"])
    bewijs.data["afhandellijst_redenen"] = dict(redenen)
    bewijs.check("JLT-72", "afhandellijst bevat geen_id, dubbel en ontbreekt (opzettelijke gaten)",
                 redenen["geen_id"] >= 1 and redenen["dubbel"] >= 1 and redenen["ontbreekt"] >= 1, dict(redenen))


def controleer_clients(bewijs: Bewijs, jl: Jellyfin, jl_gebruikers: dict[str, dict[str, Any]], naar_jl: dict[str, str],
                       waarheid: dict[str, dict[str, dict[str, Any]]], items: list[Item], paden_jl: dict[str, dict[str, Any]]) -> None:
    assert jl.admin
    per_emby_pad = {i.emby.pad: i for i in items if i.emby}
    resultaten = {}
    for gebruiker in ("Anna", "Bram", "Kim", "Gast"):
        uid = jl_gebruikers[naar_jl[gebruiker]]["Id"]
        nieuw = f"Nieuw-{gebruiker}-Jelly-Leon-1"
        jl.admin.doe("POST", "/Users/Password", {"userId": uid}, body={"NewPw": nieuw})
        auth = jl.anoniem.doe("POST", "/Users/AuthenticateByName", body={"Username": gebruiker, "Pw": nieuw})
        als = Http(jl.url, {"Authorization": JL_CLIENT.replace("harnas\", Version", "harnas-" + gebruiker + "\", Version")
                            + f', Token="{auth["AccessToken"]}"'})
        hervat = als.doe("GET", "/UserItems/Resume", {"userId": uid, "fields": "Path", "limit": "100"})["Items"]
        jl_pos = {i["Path"][len(JL_ROOT) + 1:]: int(i["UserData"]["PlaybackPositionTicks"]) for i in hervat if i.get("Path")}
        verwacht = {}
        for pad, e in waarheid[gebruiker].items():
            item = per_emby_pad.get(pad)
            if item and item.verwacht == "gekoppeld" and e["positie"] > 0 and not e["gezien"]:
                verwacht[item.jl_doel or item.jl[0].pad] = e["positie"]
        uitzondering = {per_emby_pad[p].jl[0].pad for p in per_emby_pad if per_emby_pad[p].sleutel == "llama"} if gebruiker == "Kim" else set()
        resultaten[gebruiker] = {"verwacht": len(verwacht), "gelijk": sum(1 for pd, t in verwacht.items()
                                                                         if pd in uitzondering or jl_pos.get(pd) == t)}
    bewijs.check("JLT-70", "stock-clientprotocol (simulator): inloggen met nieuw wachtwoord en 'Verder kijken' op de exacte tick",
                 all(r["verwacht"] == r["gelijk"] for r in resultaten.values()) and any(r["verwacht"] for r in resultaten.values()),
                 resultaten)


def controleer_browser(bewijs: Bewijs, jl: Jellyfin, jl_gebruikers: dict[str, dict[str, Any]], naar_jl: dict[str, str],
                       waarheid: dict[str, dict[str, dict[str, Any]]], items: list[Item], paden_jl: dict[str, dict[str, Any]],
                       browser: str) -> None:
    """JLT-70 clientdeel (QA-review): de webclient die de doelserver zelf serveert (stock-web bij stock 12.4, Jelly Leon-web
    bij de image) in een echte browser via het Playwright-harnas van B03-016. Een overgezette gebruiker logt in met het
    nieuwe wachtwoord (stap 10) en klikt op de detailpagina op afspelen/hervatten. Gemeten aan de serverkant (niet via de
    tool): de eerste PositionTicks van die websessie (PlaybackStart) ligt binnen 3 s van het overgezette hervatpunt, en het
    beeld loopt echt (breedte > 0, tijd loopt op, geen mediafout). Testdata met een beperkte licentie (Pioneer One) wordt
    niet gekozen; er worden geen schermafbeeldingen gemaakt."""
    sys.path.insert(0, str(TOOL.parent / "b03-harnas"))
    from b03h.web import harnas  # noqa: PLC0415 - alleen met --browser nodig

    assert jl.admin
    per_emby_pad = {i.emby.pad: i for i in items if i.emby}
    kandidaten = []
    for gebruiker in ("Anna", "Bram", "Kim", "Gast"):
        uid = jl_gebruikers[naar_jl[gebruiker]]["Id"]
        nu = jl_toestand(jl, uid)
        for pad, e in waarheid[gebruiker].items():
            item = per_emby_pad.get(pad)
            if not item or item.verwacht != "gekoppeld" or e["positie"] <= 0 or e["gezien"] or item.sleutel.startswith("pioneer"):
                continue
            jl_pad = item.jl_doel or item.jl[0].pad
            if jl_pad in paden_jl and nu.get(jl_pad, {}).get("positie") == e["positie"]:
                kandidaten.append((not jl_pad.endswith(".mp4"), gebruiker, jl_pad, e["positie"], paden_jl[jl_pad]["Id"]))
    if not kandidaten:
        bewijs.check("JLT-70", f"webclient in {browser}: hervatbaar overgezet item gevonden", False, "geen kandidaat")
        return
    _, gebruiker, jl_pad, verwacht, item_id = sorted(kandidaten)[0]
    cfg = {"browser": browser, "url": jl.url, "gebruiker": gebruiker, "wachtwoord": f"Nieuw-{gebruiker}-Jelly-Leon-1",
           "items": [{"id": item_id, "naam": "hervatten"}], "orakelMs": 30000, "duurMs": 8000, "label": f"jlt70-{browser}"}
    uitkomst: dict[str, Any] = {}

    def speel() -> None:
        try:
            uitkomst["res"] = harnas("speel", cfg, timeout=600)
        except Exception as fout:  # noqa: BLE001 - vastleggen in het bewijs
            uitkomst["fout"] = str(fout)[:600]

    draad = threading.Thread(target=speel, daemon=True)
    draad.start()
    posities: list[int] = []
    while draad.is_alive():
        try:
            sessies = jl.admin.doe("GET", "/Sessions", {"activeWithinSeconds": "300"}) or []
        except Exception:  # noqa: BLE001 - een gemiste peiling is geen fout
            sessies = []
        for sessie in sessies:
            if sessie.get("UserName") == gebruiker and (sessie.get("NowPlayingItem") or {}).get("Id") == item_id:
                pt = (sessie.get("PlayState") or {}).get("PositionTicks")
                if pt is not None and (not posities or posities[-1] != int(pt)):
                    posities.append(int(pt))
        time.sleep(0.5)
    draad.join()
    res = uitkomst.get("res") or {}
    speel_res = (res.get("items") or [{}])[0]
    spoor = speel_res.get("spoor") or []
    laatste = speel_res.get("laatste") or {}
    detail = {"gebruiker": gebruiker, "item": jl_pad, "verwacht_ticks": verwacht, "posities_sessie": posities[:10],
              "browser": res.get("browser"), "versie": res.get("versie"), "besluit": speel_res.get("besluit"),
              "laatste": laatste, "spoor": spoor[:8], "fout": uitkomst.get("fout") or res.get("fout") or speel_res.get("fout")}
    bewijs.data.setdefault("browser", []).append(detail)
    bewijs.check("JLT-70", f"webclient in {browser}: inloggen met het nieuwe wachtwoord en het item openen",
                 bool(res) and not detail["fout"], detail["fout"] or {"gebruiker": gebruiker, "versie": res.get("versie")})
    loopt = bool(laatste) and laatste.get("w", 0) > 0 and not laatste.get("err") and len(spoor) >= 2 \
        and spoor[-1][1] - spoor[0][1] >= 1.5
    bewijs.check("JLT-70", f"webclient in {browser}: beeld loopt (breedte > 0, tijd loopt op, geen mediafout)", loopt,
                 {"laatste": laatste, "spoor": spoor[:8], "besluit": speel_res.get("besluit")})
    bewijs.check("JLT-70", f"webclient in {browser}: hervat op het overgezette hervatpunt (eerste PositionTicks binnen 3 s)",
                 bool(posities) and abs(posities[0] - verwacht) <= 30_000_000,
                 {"verwacht": verwacht, "eerste": posities[0] if posities else None, "posities": posities[:10]})


def controleer_mediaguard(bewijs: Bewijs, mg: MediaGuardSim, emby: Emby, jl: Jellyfin, uids: dict[str, str],
                          jl_gebruikers: dict[str, dict[str, Any]], paden_emby: dict[str, dict[str, Any]],
                          paden_jl: dict[str, dict[str, Any]], per_sleutel: dict[str, Item]) -> None:
    # Sessie op Emby (als Anna).
    als = emby.als(uids["Anna"])
    item = paden_emby[per_sleutel["bbb"].emby.pad]  # type: ignore[union-attr]
    info = als.doe("GET", f"/Items/{item['Id']}/PlaybackInfo", {"UserId": uids["Anna"]})
    verzoek = {"ItemId": item["Id"], "MediaSourceId": info["MediaSources"][0]["Id"], "PlaySessionId": info["PlaySessionId"],
               "PositionTicks": 10_000_000, "PlayMethod": "DirectPlay", "CanSeek": True}
    begin = time.time()
    als.doe("POST", "/Sessions/Playing", body=verzoek)
    emby_pauze = mg.wacht_op_kijkpauze("emby", begin)
    als.doe("POST", "/Sessions/Playing/Stopped", body=verzoek)
    # Sessie op Jelly Leon (als Anna, nieuw wachtwoord).
    auth = jl.anoniem.doe("POST", "/Users/AuthenticateByName", body={"Username": "Anna", "Pw": "Nieuw-Anna-Jelly-Leon-1"})
    jl_als = Http(jl.url, {"Authorization": JL_CLIENT.replace("harnas\", Version", "harnas-mg\", Version") + f', Token="{auth["AccessToken"]}"'})
    jl_item = paden_jl[per_sleutel["bbb"].jl[0].pad]["Id"]
    jl_verzoek = {"ItemId": jl_item, "PositionTicks": 10_000_000, "PlayMethod": "DirectPlay", "CanSeek": True,
                  "PlaySessionId": "mg-sim-proef"}
    begin = time.time()
    jl_als.doe("POST", "/Sessions/Playing", body=jl_verzoek)
    jl_pauze = mg.wacht_op_kijkpauze("jelly_leon", begin)
    jl_als.doe("POST", "/Sessions/Playing/Stopped", body=jl_verzoek)
    s = mg.samenvatting()
    bewijs.check("JLT-73", "MediaGuard-simulator: kijkpauze bij een sessie op Emby én op Jelly Leon",
                 emby_pauze is not None and jl_pauze is not None,
                 {"emby_s": round(emby_pauze, 1) if emby_pauze is not None else None,
                  "jelly_leon_s": round(jl_pauze, 1) if jl_pauze is not None else None})
    bewijs.check("JLT-73", "Emby-koppeling (X-Emby-Token) viel tijdens de hele proef op geen enkel moment weg; Jelly Leon met "
                 "Authorization: MediaBrowser Token=…", s["polls"]["emby"]["fout"] == 0 and s["polls"]["emby"]["ok"] > 10
                 and s["polls"]["jelly_leon"]["fout"] == 0, s["polls"])


if __name__ == "__main__":
    sys.exit(main())
