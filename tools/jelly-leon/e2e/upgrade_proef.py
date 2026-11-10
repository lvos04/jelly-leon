#!/usr/bin/env python3
"""Upgradeproef 10.11.11 → Jelly Leon 12.x met behoud van kijkgegevens (JLT-60, JLT-61 a/b; Sim, geen NAS).

HARDE EIS van de gebruiker (B03 §10.9): alle kijkgeschiedenis — gezien-status (met aantal en datum), hervatpunten,
favorieten, beoordelingen, onthouden spoorkeuzes, gebruikers, rechten — blijft behouden. Deze proef doet dat voor de
jelly-leon-IMAGE (server + echte web-build + plugin), het serverdeel van JLT-60/61. Het webdeel (browser in Modern en
Legacy) staat in lvos04/jelly-leon-web (tools/jelly-leon-web/e2e/upgrade_proef.py).

  1. oude server: stock jellyfin/jellyfin:10.11.11 op digest, lege datamap; wizard, bibliotheken "Muziek" (WAV) en
     "Films" (zelfgemaakte testfilm met 2 audio- en 2 ondertitelsporen, nld/eng), vijf gebruikers (beheerder, ouder,
     tiener met leeftijdsgrens en geblokkeerde tag, gast met alleen "Films", kind zonder bibliotheken) en via de
     officiële API: gezien met datum en aantal, hervatpunt, favorieten, beoordeling, taal-/ondertitelvoorkeuren, een
     onthouden spoorkeuze (afspeelmeldingen zoals een client, tegen de taalvoorkeur in), apparaten (één per
     gebruiker), een metadata-override met vergrendeling en een afspeellijst;
  2. VÓÓR-rapport per gebruiker (genormaliseerd, sha256) + apparaten, overrides en afspeellijsten; server stoppen;
     twee kopieën van /config (= ZFS-snapshot; één voor het terugzetten, één voor de stock-vergelijking);
  3. jelly-leon-image op dezelfde /config → migraties → NA-rapport; elk verschil is een mislukte stap (een verklaard
     verschil zou per gebruiker akkoord vragen, §10.9 — hier wordt niets stil geaccepteerd); hervatten op het juiste
     punt (PlaybackInfo + UserData van de gast) en de onthouden spoorkeuze blijven; EnableLegacyAuthorization staat
     na de migratie uit (X-Emby-Token en ?api_key= → 401, Authorization: MediaBrowser Token=… → 200);
  4. differentiële controle-run (B03-016, gedeeld gereedschap b03h.diffrun): stock 12.x op de tweede kopie met
     hetzelfde scenario; de tabellen van jellyfin.db (BaseItems, UserData, Users, Permissions, Preferences, …) zijn
     gelijk buiten de vaste uitzonderingen (tijdstempels, tokens) — Jelly Leon migreert dus precies als upstream;
  5. JLT-61 (a): container weg, /config ← kopie van vóór de migratie, oude image → jellyfin.db byte-gelijk aan vóór,
     kijkgegevens = VÓÓR, stream 200;
  6. JLT-61 (b), negatieve proef: alleen de oude image op de gemigreerde /config. Gemeten wordt of hij zichtbaar
     faalt; daarna moet er in elk geval geen stille schade zijn: dezelfde map opnieuw met de jelly-leon-image = NA.
     (De downgradeweigering van de jelly-leon-image zelf — een oudere Jelly Leon op een nieuwere datamap — meet
     image_lifecycle.py; de stock-image 10.11.11 kent die weigering niet.)

Wachtwoorden worden per run gemaakt en nooit gerapporteerd; tokens worden geredigeerd. Media zijn zelfgemaakt.
Exitcodes: 0 = alle stappen geslaagd (of alleen de vooraf aangekondigde gemeten afwijking van 6, zie
--negatief-verwacht), 1 = een stap mislukt, 3 = omgevingsfout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

E2E = Path(__file__).resolve().parent
REPO = E2E.parents[2]
sys.path.insert(0, str(REPO / "tools" / "b03-harnas"))

from b03h.diffrun import vergelijk  # noqa: E402
from b03h.jfapi import Http, HttpFout, wacht_klaar  # noqa: E402

OLD_IMAGE = "docker.io/jellyfin/jellyfin:10.11.11@sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db"
STOCK_NEW_IMAGE = "docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771"
TICKS = 10_000_000
CLIENT = 'MediaBrowser Client="jelly-leon-upgradeproef", Device="proef", DeviceId="{device}", Version="1.0"'
ADMIN, PARENT, TEEN, GUEST, KID = "jl-beheer", "jl-ouder", "jl-tiener", "jl-gast", "jl-kind"
MUSIC = "/media/muziek"
FILMS = "/media/films"
WAV_REL = "Jelly Leon Test/Smoketest/01 - Sinus 440 Hz.wav"
FILM_REL = "Jelly Leon Testfilm (2026)/Jelly Leon Testfilm (2026).mkv"
FILM_TRACKS = {1: "Audio", 2: "Audio", 3: "Subtitle", 4: "Subtitle"}
GUEST_TRACKS = {"DefaultAudioStreamIndex": 2, "DefaultSubtitleStreamIndex": 4}
GUEST_PREFS = {"AudioLanguagePreference": "nld", "SubtitleLanguagePreference": "nld", "SubtitleMode": "Always",
               "RememberAudioSelections": True, "RememberSubtitleSelections": True}
USERDATA_FIELDS = ("Played", "PlayCount", "PlaybackPositionTicks", "IsFavorite", "Rating", "Likes", "LastPlayedDate")
POLICY_FIELDS = ("IsAdministrator", "IsDisabled", "IsHidden", "EnableAllFolders", "EnabledFolders", "MaxParentalRating",
                 "BlockedTags", "AllowedTags", "EnableContentDownloading", "EnableRemoteAccess", "EnableMediaPlayback",
                 "EnableAllDevices", "EnableSyncTranscoding", "EnableVideoPlaybackTranscoding")
OVERRIDE = {"Name": "Testfilm (eigen titel)", "OfficialRating": "PG-13", "Tags": ["eigen-tag"], "LockData": True}
OVERRIDE_FIELDS = ("Name", "OfficialRating", "Tags", "LockData")


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def docker(*args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, check=False, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:3])} … → {proc.returncode}: {proc.stderr.strip()[:400]}")
    return proc


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def digest(data: object) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def iso_seconds(value: object) -> object:
    """Datums op de seconde in UTC vergelijken (12.x schrijft soms een andere notatie van hetzelfde moment)."""
    if not isinstance(value, str) or not value:
        return value
    text = value.rstrip("Z").split(".")[0]
    try:
        return datetime.fromisoformat(text).replace(tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return value


def differences(before: object, after: object, path: str = "") -> list[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        found: list[str] = []
        for key in sorted(set(before) | set(after)):
            where = f"{path}/{key}" if path else str(key)
            if key not in before:
                found.append(f"{where}: nieuw na de upgrade ({after[key]!r})")
            elif key not in after:
                found.append(f"{where}: VERDWENEN na de upgrade (was {before[key]!r})")
            else:
                found += differences(before[key], after[key], where)
        return found
    return [] if before == after else [f"{path}: {before!r} → {after!r}"]


class Report:
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self.secrets: list[str] = []

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "<geheim>")
        return text

    def add(self, name: str, ok: bool, detail: str) -> bool:
        detail = self.redact(detail)
        self.steps.append({"stap": name, "geslaagd": bool(ok), "detail": detail, "tijd": utc_now()})
        print(f"[{'OK  ' if ok else 'FOUT'}] {name}: {detail[:400]}", flush=True)
        return bool(ok)


class Server:
    """Eén container op een datamap (als de aanroeper, zonder capabilities, alleen 127.0.0.1)."""

    def __init__(self, proef: Proef, image: str, label: str) -> None:
        self.proef = proef
        self.image = image
        self.label = label
        self.name = f"jl-upgrade-{os.getpid()}-{label}"
        self.port = 0
        self.info: dict[str, Any] = {}

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, config: Path, *, wait: bool = True) -> Server:
        docker("rm", "-f", self.name, check=False)
        self.port = self.proef.free_port()
        cache = self.proef.work / f"cache-{self.label}"
        cache.mkdir(exist_ok=True)
        docker(
            "run", "-d", "--name", self.name, "--user", f"{os.getuid()}:{os.getgid()}", "--memory", "3g",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "-e", "TZ=UTC",
            "-p", f"127.0.0.1:{self.port}:8096", "-v", f"{config}:/config", "-v", f"{cache}:/cache",
            "-v", f"{self.proef.music}:{MUSIC}:ro", "-v", f"{self.proef.films}:{FILMS}:ro", self.image,
        )
        if wait:
            self.info = wacht_klaar(self.url, timeout=self.proef.args.health_timeout)
        return self

    def stop(self) -> None:
        docker("stop", "-t", "30", self.name, check=False, timeout=120)
        docker("rm", "-f", self.name, check=False)

    def logs(self, lines: int = 40) -> str:
        proc = docker("logs", "--tail", str(lines), self.name, check=False)
        return self.proef.report.redact((proc.stdout + proc.stderr)[-4000:])


class Proef:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.report = Report()
        self.work = Path(tempfile.mkdtemp(prefix="jl-upgrade-", dir=args.werkmap))
        self.music = self.work / "media-muziek"
        self.films = self.work / "media-films"
        self.config = self.work / "config"
        self.backup = self.work / "kopie-voor-migratie"
        self.stock_copy = self.work / "kopie-stock-vergelijking"
        self.negative = self.work / "kopie-negatief"
        self.diff_stock = self.work / "kopie-diff-stock"
        self.diff_jl = self.work / "kopie-diff-jellyleon"
        self.password = secrets.token_urlsafe(18)
        self.report.secrets.append(self.password)
        self.ids: dict[str, str] = {}
        self.result: dict[str, Any] = {}

    # ------------------------------------------------------------------ hulpmiddelen
    @staticmethod
    def free_port() -> int:
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def http(self, server: Server, token: str | None = None, device: str = "jl-upgrade-beheer") -> Http:
        header = CLIENT.format(device=device) + (f', Token="{token}"' if token else "")
        return Http(server.url, {"Authorization": header})

    def login(self, server: Server, user: str, device: str) -> tuple[str, str]:
        auth = self.http(server, device=device).doe("POST", "/Users/AuthenticateByName",
                                                   body={"Username": user, "Pw": self.password})
        self.report.secrets.append(auth["AccessToken"])
        return auth["AccessToken"], auth["User"]["Id"]

    def make_media(self) -> None:
        subprocess.run([sys.executable, str(E2E / "make_test_media.py"), str(self.music)], check=True, capture_output=True)
        target = self.films / FILM_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        subs = self.work / "ondertitelbron"
        subs.mkdir()
        (subs / "nl.srt").write_text("1\n00:00:00,000 --> 00:00:02,500\nOndertitel een\n", encoding="utf-8")
        (subs / "en.srt").write_text("1\n00:00:00,000 --> 00:00:02,500\nSubtitle one\n", encoding="utf-8")
        # Deterministisch (bitexact) met de ffmpeg uit de oude image; geen netwerk, geen rechten, geen eigen materiaal.
        docker(
            "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffmpeg",
            "-v", f"{subs}:/in:ro", "-v", f"{target.parent}:/out", OLD_IMAGE, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-f", "lavfi", "-i", "sine=frequency=880:duration=4",
            "-i", "/in/nl.srt", "-i", "/in/en.srt",
            "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s", "-map", "4:s",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "32k", "-c:s", "srt",
            "-metadata:s:a:0", "language=nld", "-metadata:s:a:1", "language=eng",
            "-metadata:s:s:0", "language=nld", "-metadata:s:s:1", "language=eng",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", f"/out/{target.name}",
        )

    def media_hashes(self) -> dict[str, str]:
        return {str(p.relative_to(self.work)): sha256(p) for root in (self.music, self.films)
                for p in sorted(root.rglob("*")) if p.is_file()}

    def copy_config(self, target: Path) -> None:
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(self.config, target, symlinks=True)

    def restore(self, source: Path) -> None:
        shutil.rmtree(self.config)
        shutil.copytree(source, self.config, symlinks=True)

    # ------------------------------------------------------------------ inrichten (oude server)
    def wait_scan(self, api: Http, expected: int) -> list[dict[str, Any]]:
        deadline = time.monotonic() + self.args.scan_timeout
        items: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            body = api.doe("GET", "/Items", {"recursive": "true", "includeItemTypes": "Audio,Movie", "fields": "Path",
                                             "userId": self.ids["admin"]})
            items = body.get("Items", [])
            tasks = api.doe("GET", "/ScheduledTasks", {"isHidden": "false"})
            if len(items) >= expected and not any(t.get("State") == "Running" for t in tasks):
                return items
            time.sleep(2)
        return items

    def library(self, api: Http, name: str, kind: str, path: str) -> None:
        options = {"EnableRealtimeMonitor": False, "SaveLocalMetadata": False, "EnableChapterImageExtraction": False,
                   "ExtractChapterImagesDuringLibraryScan": False, "EnableTrickplayImageExtraction": False,
                   "SaveSubtitlesWithMedia": False, "PathInfos": [{"Path": path}], "MetadataSavers": [],
                   "TypeOptions": [{"Type": t, "MetadataFetchers": [], "ImageFetchers": []}
                                   for t in (["Movie"] if kind == "movies" else ["MusicAlbum", "Audio"])]}
        api.doe("POST", "/Library/VirtualFolders", {"name": name, "collectionType": kind, "refreshLibrary": "false"},
                body={"LibraryOptions": options})

    def seed(self, server: Server) -> bool:
        anon = self.http(server)
        for attempt in range(30):
            try:
                anon.doe("POST", "/Startup/Configuration",
                         body={"UICulture": "nl", "MetadataCountryCode": "NL", "PreferredMetadataLanguage": "nl"})
                break
            except HttpFout as exc:
                if exc.status != 503 or attempt == 29:
                    raise
                time.sleep(2)
        anon.doe("GET", "/Startup/User")
        anon.doe("POST", "/Startup/User", body={"Name": ADMIN, "Password": self.password})
        anon.doe("POST", "/Startup/RemoteAccess", body={"EnableRemoteAccess": True, "EnableAutomaticPortMapping": False})
        anon.doe("POST", "/Startup/Complete")
        token, admin_id = self.login(server, ADMIN, "jl-upgrade-beheer")
        self.ids.update(admin=admin_id)
        api = self.http(server, token)
        self.library(api, "Muziek", "music", MUSIC)
        self.library(api, "Films", "movies", FILMS)
        api.doe("POST", "/Library/Refresh")
        items = self.wait_scan(api, 2)
        paths = {i.get("Path"): i["Id"] for i in items}
        wav, film = paths.get(f"{MUSIC}/{WAV_REL}"), paths.get(f"{FILMS}/{FILM_REL}")
        folders = {f["Name"]: f["ItemId"] for f in api.doe("GET", "/Library/VirtualFolders")}
        if not self.report.add("oude server: bibliotheken gescand", bool(wav and film),
                               f"{len(items)} items; muziek {bool(wav)}, film {bool(film)}; bibliotheken {sorted(folders)}"):
            return False
        self.ids.update(wav=wav, film=film)
        info = api.doe("POST", f"/Items/{film}/PlaybackInfo", {"userId": admin_id}, body={"UserId": admin_id})
        source = info["MediaSources"][0]
        streams = {s.get("Index"): s.get("Type") for s in source.get("MediaStreams") or []}
        if not self.report.add("testfilm met 2 audio- en 2 ondertitelsporen", all(streams.get(i) == t for i, t in FILM_TRACKS.items()),
                               f"sporen {streams}"):
            return False

        policies = {
            PARENT: {},
            TEEN: {"MaxParentalRating": 13, "BlockedTags": ["horror"]},
            GUEST: {"EnableAllFolders": False, "EnabledFolders": [folders["Films"]], "EnableContentDownloading": False,
                    "EnableRemoteAccess": False},
            KID: {"EnableAllFolders": False, "EnabledFolders": [], "MaxParentalRating": 7, "EnableRemoteAccess": False},
        }
        for name, policy in policies.items():
            user = api.doe("POST", "/Users/New", body={"Name": name, "Password": self.password})
            self.ids[name] = user["Id"]
            if policy:
                current = api.doe("GET", f"/Users/{user['Id']}")["Policy"]
                api.doe("POST", f"/Users/{user['Id']}/Policy", body={**current, **policy})
        guest_cfg = api.doe("GET", f"/Users/{self.ids[GUEST]}")["Configuration"]
        api.doe("POST", f"/Users/{self.ids[GUEST]}/Configuration", body={**guest_cfg, **GUEST_PREFS})

        data = [
            (admin_id, film, {"Played": True, "PlayCount": 2, "IsFavorite": True, "Rating": 8.0,
                              "LastPlayedDate": "2026-11-01T20:15:00.0000000Z"}),
            (admin_id, wav, {"Played": True, "PlayCount": 5, "LastPlayedDate": "2026-10-02T08:00:00.0000000Z"}),
            (self.ids[PARENT], wav, {"IsFavorite": True, "Likes": True}),
            (self.ids[PARENT], film, {"PlaybackPositionTicks": 25 * TICKS // 10, "Played": False}),
            (self.ids[TEEN], wav, {"Played": True, "PlayCount": 1, "LastPlayedDate": "2026-10-30T19:00:00.0000000Z"}),
            (self.ids[GUEST], film, {"IsFavorite": True}),
        ]
        for uid, item, body in data:
            api.doe("POST", f"/UserItems/{item}/UserData", {"userId": uid}, body=body)

        # Onthouden spoorkeuze + hervatpunt van de gast zoals een client dat zet (afspeelmeldingen; eng tegen voorkeur nld).
        g_token, _ = self.login(server, GUEST, "jl-upgrade-gast")
        guest = self.http(server, g_token, device="jl-upgrade-gast")
        play = {"ItemId": film, "MediaSourceId": source["Id"], "PlaySessionId": "jl-upgrade-gast", "PlayMethod": "DirectPlay",
                "CanSeek": True, "IsPaused": False, "AudioStreamIndex": 2, "SubtitleStreamIndex": 4}
        guest.doe("POST", "/Sessions/Playing", body={**play, "PositionTicks": 0})
        guest.doe("POST", "/Sessions/Playing/Progress", body={**play, "PositionTicks": 15 * TICKS // 10})
        guest.doe("POST", "/Sessions/Playing/Stopped", body={**play, "PositionTicks": 15 * TICKS // 10})
        # De testfilm duurt 4 s (< MinResumeDurationSeconds = 300): bij "Stopped" zet upstream hem op gezien zonder
        # hervatpunt. Het hervatpunt (zoals bij een echte, lange film) daarom via de UserData-route; de onthouden
        # spoorkeuze uit de afspeelmeldingen blijft staan (die zit niet in de DTO).
        api.doe("POST", f"/UserItems/{film}/UserData", {"userId": self.ids[GUEST]},
                body={"Played": False, "PlaybackPositionTicks": 15 * TICKS // 10})
        for name in (PARENT, TEEN, KID):
            self.login(server, name, f"jl-upgrade-{name.removeprefix('jl-')}")  # één apparaat per gebruiker

        # Metadata-override met vergrendeling en een afspeellijst van de beheerder.
        item = api.doe("GET", f"/Items/{film}", {"userId": admin_id})
        api.doe("POST", f"/Items/{film}", body={**item, **OVERRIDE})
        created = api.doe("POST", "/Playlists", body={"Name": "Proeflijst", "Ids": [film, wav], "UserId": admin_id,
                                                      "MediaType": "Video"})
        self.ids["playlist"] = created["Id"]
        time.sleep(2)
        return self.report.add("kijkgegevens, rechten, apparaten, override en afspeellijst gezet (officiële API)", True,
                               "beheerder film 2× gezien + favoriet + beoordeling 8, wav 5× gezien; ouder wav favoriet + "
                               "vind-ik-leuk, film hervatpunt 2,5 s; tiener wav gezien, grens 13 + tag horror; gast alleen "
                               "Films, favoriet, hervatpunt 1,5 s en spoorkeuze eng/eng (voorkeur nld); kind geen "
                               "bibliotheken; 5 apparaten; override titel/rating/tag/LockData; afspeellijst 2 items")

    # ------------------------------------------------------------------ rapporten
    def track_choice(self, api: Http, item: str, uid: str) -> dict[str, Any]:
        status, raw, _ = api.ruw("POST", f"/Items/{item}/PlaybackInfo", {"userId": uid}, body={"UserId": uid})
        if status != 200:
            return {"geen_toegang": status}
        source = (json.loads(raw.decode("utf-8-sig")).get("MediaSources") or [{}])[0]
        return {k: source.get(k) for k in GUEST_TRACKS}

    def snapshot(self, server: Server) -> dict[str, Any]:
        token, admin_id = self.login(server, ADMIN, "jl-upgrade-beheer")
        api = self.http(server, token)
        users = sorted(api.doe("GET", "/Users"), key=lambda u: u["Name"])
        names = {u["Id"]: u["Name"] for u in users}
        folders = {f["ItemId"]: f["Name"] for f in api.doe("GET", "/Library/VirtualFolders")}
        items = api.doe("GET", "/Items", {"recursive": "true", "includeItemTypes": "Audio,Movie", "fields": "Path",
                                          "userId": admin_id})["Items"]
        by_path = {i["Path"]: i["Id"] for i in items}
        result: dict[str, Any] = {"gebruikers": {}, "items": sorted(by_path)}
        for user in users:
            policy, config = user.get("Policy") or {}, user.get("Configuration") or {}
            entry: dict[str, Any] = {"beleid": {k: policy.get(k) for k in POLICY_FIELDS},
                                     "voorkeuren": {k: config.get(k) for k in GUEST_PREFS}, "kijkgegevens": {},
                                     "spoorkeuzes": {}, "zichtbaar": []}
            entry["beleid"]["EnabledFolders"] = sorted(folders.get(f, f) for f in policy.get("EnabledFolders") or [])
            entry["beleid"]["BlockedTags"] = sorted(policy.get("BlockedTags") or [])
            for path, item in sorted(by_path.items()):
                status, raw, _ = api.ruw("GET", f"/UserItems/{item}/UserData", {"userId": user["Id"]})
                if status == 404:  # geen toegang tot dit item (kind, gast): ook dat moet gelijk blijven
                    entry["kijkgegevens"][path] = {"geen_toegang": True}
                    continue
                if status != 200:
                    raise RuntimeError(f"UserData {user['Name']} {path}: HTTP {status}")
                data = json.loads(raw.decode("utf-8-sig"))
                norm = {k: data.get(k) for k in USERDATA_FIELDS}
                norm["LastPlayedDate"] = iso_seconds(norm["LastPlayedDate"])
                if isinstance(norm["Rating"], (int, float)):
                    norm["Rating"] = float(norm["Rating"])
                entry["kijkgegevens"][path] = norm
            entry["spoorkeuzes"][f"{FILMS}/{FILM_REL}"] = self.track_choice(api, by_path[f"{FILMS}/{FILM_REL}"], user["Id"])
            visible = api.doe("GET", "/Items", {"recursive": "true", "includeItemTypes": "Audio,Movie", "fields": "Path",
                                                "userId": user["Id"]})["Items"]
            entry["zichtbaar"] = sorted(i["Path"] for i in visible)
            result["gebruikers"][user["Name"]] = entry
        devices = api.doe("GET", "/Devices").get("Items", [])
        result["apparaten"] = sorted(
            (names.get(d.get("LastUserId"), d.get("LastUserName")), d.get("Id"), d.get("AppName")) for d in devices
            if str(d.get("Id", "")).startswith("jl-upgrade-")
        )
        film = api.doe("GET", f"/Items/{by_path[f'{FILMS}/{FILM_REL}']}", {"userId": admin_id})
        result["override_film"] = {k: film.get(k) for k in OVERRIDE_FIELDS}
        lists = api.doe("GET", "/Items", {"recursive": "true", "includeItemTypes": "Playlist", "userId": admin_id})["Items"]
        result["afspeellijsten"] = {}
        for pl in lists:
            entries = api.doe("GET", f"/Playlists/{pl['Id']}/Items", {"userId": admin_id, "fields": "Path"}).get("Items", [])
            result["afspeellijsten"][pl["Name"]] = [e.get("Path") for e in entries]
        return result

    def expected_present(self, snap: dict[str, Any], label: str) -> bool:
        users = snap["gebruikers"]
        film, wav = f"{FILMS}/{FILM_REL}", f"{MUSIC}/{WAV_REL}"
        admin = users.get(ADMIN, {}).get("kijkgegevens", {}).get(film, {})
        guest = users.get(GUEST, {})
        checks = {
            "5 gebruikers": len(users) == 5,
            "beheerder film 2× gezien, datum, favoriet, 8": admin.get("Played") is True and admin.get("PlayCount") == 2
            and admin.get("IsFavorite") is True and admin.get("Rating") == 8.0
            and admin.get("LastPlayedDate") == "2026-11-01T20:15:00Z",
            "beheerder wav 5×": users.get(ADMIN, {}).get("kijkgegevens", {}).get(wav, {}).get("PlayCount") == 5,
            "ouder hervatpunt 2,5 s": users.get(PARENT, {}).get("kijkgegevens", {}).get(film, {}).get("PlaybackPositionTicks")
            == 25 * TICKS // 10,
            "ouder vind-ik-leuk": users.get(PARENT, {}).get("kijkgegevens", {}).get(wav, {}).get("Likes") is True,
            "gast hervatpunt 1,5 s": guest.get("kijkgegevens", {}).get(film, {}).get("PlaybackPositionTicks") == 15 * TICKS // 10,
            "gast spoorkeuze eng/eng": guest.get("spoorkeuzes", {}).get(film) == GUEST_TRACKS,
            "gast voorkeuren nld": all(guest.get("voorkeuren", {}).get(k) == v for k, v in GUEST_PREFS.items()),
            "gast ziet alleen Films": guest.get("zichtbaar") == [film],
            "kind ziet niets": users.get(KID, {}).get("zichtbaar") == [],
            "tiener grens + tag": users.get(TEEN, {}).get("beleid", {}).get("BlockedTags") == ["horror"]
            and users.get(TEEN, {}).get("beleid", {}).get("MaxParentalRating") is not None,
            "5 apparaten": len(snap.get("apparaten", [])) >= 5,
            "override": snap.get("override_film") == {k: OVERRIDE[k] for k in OVERRIDE_FIELDS},
            "afspeellijst 2 items": snap.get("afspeellijsten", {}).get("Proeflijst") == [film, wav],
        }
        failed = [k for k, v in checks.items() if not v]
        return self.report.add(f"{label}: gezette gegevens aanwezig ({len(checks) - len(failed)}/{len(checks)})", not failed,
                               "ontbreekt: " + "; ".join(failed) if failed else "alle controles aanwezig")

    # ------------------------------------------------------------------ verloop
    def legacy_auth(self, server: Server) -> bool:
        token, _ = self.login(server, ADMIN, "jl-upgrade-beheer")
        api = self.http(server, token)
        cfg = api.doe("GET", "/System/Configuration")
        codes = {}
        codes["X-Emby-Token"] = Http(server.url, {"X-Emby-Token": token}).ruw("GET", "/Users/Me")[0]
        codes["api_key"] = Http(server.url).ruw("GET", "/Users/Me", {"api_key": token})[0]
        codes["MediaBrowser Token"] = Http(server.url, {"Authorization": f'MediaBrowser Token="{token}"'}).ruw("GET", "/Users/Me")[0]
        ok = cfg.get("EnableLegacyAuthorization") is False and codes == {"X-Emby-Token": 401, "api_key": 401,
                                                                         "MediaBrowser Token": 200}
        return self.report.add("EnableLegacyAuthorization uit na de migratie (12.x-standaard, BG-01)", ok,
                               f"EnableLegacyAuthorization={cfg.get('EnableLegacyAuthorization')}; HTTP {codes}")

    def resume(self, server: Server, snap: dict[str, Any], label: str) -> bool:
        """Hervatten op het juiste punt: wat een client krijgt (UserData + PlaybackInfo + streambare bron)."""
        token, uid = self.login(server, GUEST, "jl-upgrade-gast")
        api = self.http(server, token, device="jl-upgrade-gast")
        film = self.ids["film"]
        data = api.doe("GET", f"/UserItems/{film}/UserData", {"userId": uid})
        resume = api.doe("GET", "/UserItems/Resume", {"userId": uid, "mediaTypes": "Video"}).get("Items", [])
        info = api.doe("POST", f"/Items/{film}/PlaybackInfo", {"userId": uid}, body={"UserId": uid})
        source = info["MediaSources"][0]
        status, body, _ = api.ruw("GET", f"/Videos/{film}/stream", {"static": "true", "mediaSourceId": source["Id"]},
                                  headers={"Range": "bytes=0-1023"})
        ok = (data.get("PlaybackPositionTicks") == 15 * TICKS // 10 and any(i["Id"] == film for i in resume)
              and source.get("DefaultAudioStreamIndex") == 2 and source.get("DefaultSubtitleStreamIndex") == 4
              and status in (200, 206) and len(body) > 0)
        return self.report.add(f"{label}: gast hervat op het juiste punt met de onthouden sporen", ok,
                               f"hervatpunt {data.get('PlaybackPositionTicks')} ticks; in 'Verder kijken' "
                               f"{any(i['Id'] == film for i in resume)}; sporen {source.get('DefaultAudioStreamIndex')}/"
                               f"{source.get('DefaultSubtitleStreamIndex')}; stream HTTP {status} ({len(body)} bytes)")

    def run(self) -> bool:
        r = self.report
        self.music.mkdir(parents=True)
        self.films.mkdir(parents=True)
        self.config.mkdir()
        self.make_media()
        media_before = self.media_hashes()
        old = Server(self, OLD_IMAGE, "oud")
        new = Server(self, self.args.image, "jellyleon")
        stock = Server(self, self.args.stock_image, "stock")
        try:
            # 1-2. oude server vullen, VÓÓR-rapport, kopieën
            old.start(self.config)
            r.add("oude server gestart", old.info.get("Version") == "10.11.11", f"versie {old.info.get('Version')}")
            if not self.seed(old):
                return False
            before = self.snapshot(old)
            self.expected_present(before, "VÓÓR (10.11.11)")
            old.stop()
            for target in (self.backup, self.stock_copy, self.diff_stock, self.diff_jl):
                self.copy_config(target)
            db_before = sha256(self.backup / "data" / "jellyfin.db")
            self.result["voor"] = {"sha256": digest(before), "rapport": before}

            # 3. jelly-leon-image op dezelfde datamap
            new.start(self.config)
            ver = new.info.get("Version")
            r.add("jelly-leon-image start op de gevulde 10.11.11-datamap (migraties zonder handwerk)",
                  ver == self.args.expected_version and new.info.get("ProductName") == "Jellyfin Server",
                  f"versie {ver}, product {new.info.get('ProductName')}, server {new.info.get('ServerName')}")
            after = self.snapshot(new)
            diff = differences(before, after)
            self.result["na"] = {"sha256": digest(after), "rapport": after, "verschillen": diff}
            r.add("VÓÓR = NA per gebruiker (gezien, aantal, datum, hervatpunt, favoriet, beoordeling, spoorkeuze, "
                  "voorkeuren, rechten, zichtbaarheid, apparaten, override, afspeellijst)", not diff,
                  f"{len(diff)} verschillen" + (": " + "; ".join(diff[:8]) if diff else f"; sha256 {digest(after)[:16]}…"))
            self.expected_present(after, "NA (Jelly Leon 12.x)")
            self.resume(new, after, "NA")
            self.legacy_auth(new)
            token, _ = self.login(new, ADMIN, "jl-upgrade-beheer")
            plugin = self.http(new, token).ruw("GET", "/media/v1/version")
            r.add("Jelly Leon-plugin laadt op de gemigreerde datamap", plugin[0] == 200 and b'"compatibel"' in plugin[1],
                  f"GET /media/v1/version HTTP {plugin[0]}: {plugin[1][:160]!r}")
            new.stop()

            # 4. differentiële controle-run: stock 12.x op de tweede kopie, hetzelfde scenario
            stock.start(self.stock_copy)
            stock_after = self.snapshot(stock)
            stock.stop()
            r.add("stock 12.x op een kopie geeft hetzelfde NA-rapport", digest(stock_after) == digest(after),
                  "; ".join(differences(stock_after, after)[:6]) or f"sha256 {digest(stock_after)[:16]}…")
            # Alleen de migratie vergelijken: elke kant start één keer op een eigen kopie en stopt (geen API-scenario,
            # zodat lui aangemaakte rijen met hun eigen tijdstempel niet meetellen).
            for server, target in ((Server(self, self.args.stock_image, "diffstock"), self.diff_stock),
                                   (Server(self, self.args.image, "diffjl"), self.diff_jl)):
                server.start(target)
                time.sleep(5)
                server.stop()
            cmp = vergelijk(self.diff_stock / "data" / "jellyfin.db", self.diff_jl / "data" / "jellyfin.db")
            self.result["diffrun"] = cmp
            n = cmp["verschillen_buiten_uitzonderingen"]
            details = {t: v for t, v in cmp["tabellen"].items() if v.get("verschil_rijen") or v.get("fout")}
            r.add("differentiële controle-run jellyfin.db na de migratie: stock 12.x = Jelly Leon 12.x", n == 0,
                  f"{n} verschillen buiten de vaste uitzonderingen; {len(cmp['tabellen'])} tabellen; "
                  f"uitzonderingen geraakt: {cmp['uitzonderingen_geraakt']}"
                  + (f"; {json.dumps(details, default=str)[:400]}" if details else ""))

            # 5. JLT-61 (a): terugzetten = kopie + oude image
            self.copy_config(self.negative)
            self.restore(self.backup)
            db_restored = sha256(self.config / "data" / "jellyfin.db")
            r.add("JLT-61 a: jellyfin.db na terugzetten byte-gelijk aan vóór de migratie", db_restored == db_before,
                  f"sha256 vóór {db_before[:16]}…, teruggezet {db_restored[:16]}…")
            old.start(self.config)
            restored = self.snapshot(old)
            rdiff = differences(before, restored)
            token, _ = self.login(old, ADMIN, "jl-upgrade-beheer")
            stream = self.http(old, token).ruw("GET", f"/Audio/{self.ids['wav']}/stream", {"static": "true"},
                                               headers={"Range": "bytes=0-1023"})
            r.add("JLT-61 a: oude image + kopie: kijkgegevens = VÓÓR en afspelen werkt", not rdiff and stream[0] in (200, 206),
                  f"{len(rdiff)} verschillen; stream HTTP {stream[0]}" + ("; " + "; ".join(rdiff[:4]) if rdiff else ""))
            old.stop()

            # 6. JLT-61 (b): alleen de oude image op de gemigreerde datamap
            self.negative_old_image(old, new, after)
            r.add("mediabestanden onaangeroerd (sha256 vóór = na)", self.media_hashes() == media_before,
                  f"{len(media_before)} bestanden")
        finally:
            for server in (old, new, stock):
                server.stop()
        return all(s["geslaagd"] for s in r.steps)

    def negative_old_image(self, old: Server, new: Server, after: dict[str, Any]) -> None:
        r = self.report
        old.start(self.negative, wait=False)
        healthy, login_status, detail = False, None, ""
        try:
            info = wacht_klaar(old.url, timeout=120)
            healthy = True
            status, body, _ = self.http(old).ruw("POST", "/Users/AuthenticateByName",
                                                 body={"Username": ADMIN, "Pw": self.password})
            login_status = status
            detail = f"versie {info.get('Version')}; aanmelden HTTP {status}"
        except RuntimeError as exc:
            state = docker("inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}", old.name, check=False).stdout.strip()
            detail = f"niet klaar: {str(exc)[:120]}; container {state}"
        log = old.logs(30)
        old.stop()
        visible = not healthy or login_status in (None,)
        self.result["negatief_oude_image"] = {"gezond": healthy, "aanmelden_http": login_status, "log_staart": log[-1500:]}
        verwacht = self.args.negatief_verwacht
        if verwacht == "weigert":
            r.add("JLT-61 b: oude image alleen op de gemigreerde datamap faalt zichtbaar", visible, detail)
        else:
            # Alleen een meting (de stap telt als uitgevoerd); het oordeel staat apart in het rapport (jlt_61_b).
            r.add("JLT-61 b meting: oude stock-image 10.11.11 alleen op de gemigreerde datamap", True,
                  f"{detail}; zichtbare weigering={visible} — de stock-image kent geen downgradeweigering; "
                  "de weigering van de jelly-leon-image zelf meet image_lifecycle.py")
        self.result["jlt_61_b"] = (
            "Sim-geslaagd: zichtbare weigering" if visible else
            f"Sim-mislukt voor de stock-image 10.11.11: geen zichtbare weigering ({detail})"
        )
        # Geen stille schade: dezelfde map weer met de jelly-leon-image = NA.
        new.start(self.negative)
        again = self.snapshot(new)
        new.stop()
        d = differences(after, again)
        # De extra aanmeldpogingen van de oude image laten alleen apparaten/activiteit achter; die vergelijkt het
        # rapport niet (alleen jl-upgrade-apparaten), dus elk verschil hier is echte schade.
        r.add("JLT-61 b: geen stille schade (gemigreerde datamap na de oude image weer = NA)", not d,
              f"{len(d)} verschillen" + ("; " + "; ".join(d[:4]) if d else ""))

    def cleanup(self) -> bool:
        shutil.rmtree(self.work, ignore_errors=True)
        return not self.work.exists()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upgradeproef 10.11.11 → Jelly Leon 12.x (JLT-60/61, Sim).")
    parser.add_argument("--image", required=True, help="jelly-leon-image (lokaal gebouwd)")
    parser.add_argument("--expected-version", required=True, help="upstream-versie die de nieuwe server moet melden")
    parser.add_argument("--stock-image", default=STOCK_NEW_IMAGE, help="stock 12.x op digest voor de controle-run")
    parser.add_argument("--werkmap", default=None)
    parser.add_argument("--health-timeout", type=float, default=300)
    parser.add_argument("--scan-timeout", type=float, default=180)
    parser.add_argument("--negatief-verwacht", choices=("weigert", "start"), default="start",
                        help="JLT-61 b met de stock-image 10.11.11: 'start' legt het gemeten gedrag vast (geen weigering)")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--opmerking", default="")
    parser.add_argument("--behoud-werkmap", dest="keep", action="store_true")
    args = parser.parse_args(argv)
    if "@sha256:" not in args.stock_image:
        print("FOUT: --stock-image moet op @sha256-digest staan", file=sys.stderr)
        return 3
    proef = Proef(args)
    started = utc_now()
    try:
        passed = proef.run()
    except (RuntimeError, HttpFout, subprocess.TimeoutExpired, OSError, KeyError) as exc:
        proef.report.add("uitvoering", False, f"{type(exc).__name__}: {str(exc)[:400]}")
        passed = False
    document = {
        "schema": "jelly-leon/upgradeproef/1",
        "soort": "Sim-getest (Docker op de ontwikkelmachine; kopie van de datamap i.p.v. ZFS-snapshot; geen NAS)",
        "images": {"oud": OLD_IMAGE, "jelly_leon": args.image, "stock_12x": args.stock_image},
        "opmerking": args.opmerking, "gestart": started, "klaar": utc_now(), "geslaagd": passed,
        "stappen": proef.report.steps,
        "voor_sha256": proef.result.get("voor", {}).get("sha256"),
        "na_sha256": proef.result.get("na", {}).get("sha256"),
        "verschillen_voor_na": proef.result.get("na", {}).get("verschillen"),
        "rapport_voor": proef.result.get("voor", {}).get("rapport"),
        "diffrun": proef.result.get("diffrun"),
        "negatief_oude_image": proef.result.get("negatief_oude_image"),
        "jlt_61_b": proef.result.get("jlt_61_b"),
        "werkmap": str(proef.work),
    }
    if passed and not args.keep:
        document["werkmap"] += " (opgeruimd)" if proef.cleanup() else " (opruimen mislukt)"
    text = proef.report.redact(json.dumps(document, indent=1, ensure_ascii=False, default=str))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    ok = sum(s["geslaagd"] for s in proef.report.steps)
    print(f"RESULTAAT: {'GESLAAGD' if passed else 'MISLUKT'} ({ok}/{len(proef.report.steps)})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
