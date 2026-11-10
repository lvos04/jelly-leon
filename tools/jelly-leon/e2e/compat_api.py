#!/usr/bin/env python3
"""API- en gedragsregressie Jelly Leon tegen stock 12.x (JLT-64 met de bestaande plugin; PlaybackInfo-deel van JLT-63).

B03-019 (c): "OpenAPI-diff tegen upstream alleen additief onder /media/v1 en /connector/v1" en "module uit / plugin
verwijderd byte-gelijk aan stock (vaste veldenlijst)". In P4-0 bestaat alleen de basisplugin; deze proef legt het
raamwerk vast en draait het nu met die plugin:

  1. stock 12.x (op digest) richt een datamap in: wizard, bibliotheken "Films" (zelfgemaakte testfilm met 2 audio- en
     2 ondertitelsporen) en "Muziek" (WAV), een tweede gebruiker, kijkgegevens; stoppen; twee kopieën;
  2. stock op kopie A en de jelly-leon-image op kopie B (om de beurt, zelfde verzoeken als dezelfde gebruiker);
  3. vergeleken (na het weghalen van vluchtige velden: sessie-ID's, tijdstempels van het verzoek, servernaam):
     /System/Info/Public, /UserViews, /Items (+ per item), /Items/{id}/Similar, /Shows/NextUp, /UserItems/Resume,
     /MediaSegments/{id}, /SyncPlay/List en PlaybackInfo per item met drie apparaatprofielen (Direct Play, transcode,
     alleen audio; mét MediaSourceId en AudioStreamIndex zoals de webclient);
  4. de door de server geserveerde OpenAPI: Jelly Leon mag alleen paden toevoegen onder /media/v1 of /connector/v1;
     gedeelde paden en schema's gelijk (description-teksten tellen niet, ADR-0010).

Exitcode 0 = geen enkele afwijking buiten de toegestane uitbreiding. Sim; geen echte clients.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

E2E = Path(__file__).resolve().parent
REPO = E2E.parents[2]
sys.path.insert(0, str(REPO / "tools" / "b03-harnas"))
sys.path.insert(0, str(REPO / "tools" / "jelly-leon"))

from b03h.jfapi import Http, wacht_klaar  # noqa: E402
from upgrade_proef import FILM_REL, FILMS, MUSIC, OLD_IMAGE, STOCK_NEW_IMAGE, differences, docker  # noqa: E402

from openapi_drift import strip_descriptions  # noqa: E402

CLIENT = 'MediaBrowser Client="jelly-leon-compat", Device="compat", DeviceId="jl-compat", Version="1.0"'
ADDITIEF = ("/media/v1/", "/connector/v1/")
# Vluchtig per verzoek of per installatie-run (geen gedrag): weggehaald vóór de vergelijking.
VLUCHTIG = {"PlaySessionId", "ServerName", "LocalAddress", "ETag", "DateLastSaved", "LastActivityDate", "LastLoginDate"}
PROFIELEN: dict[str, dict[str, Any]] = {
    "web-directplay": {
        "MaxStreamingBitrate": 120000000, "MaxStaticBitrate": 100000000,
        "DirectPlayProfiles": [{"Container": "mp4,m4v,mkv,webm", "Type": "Video", "VideoCodec": "h264,vp9,av1",
                                "AudioCodec": "aac,mp3,opus,flac"},
                               {"Container": "wav,mp3,flac,aac", "Type": "Audio"}],
        "TranscodingProfiles": [{"Container": "ts", "Type": "Video", "VideoCodec": "h264", "AudioCodec": "aac",
                                 "Protocol": "hls", "Context": "Streaming"},
                                {"Container": "mp3", "Type": "Audio", "AudioCodec": "mp3", "Protocol": "http", "Context": "Streaming"}],
        "SubtitleProfiles": [{"Format": "vtt", "Method": "External"}, {"Format": "srt", "Method": "External"}],
    },
    "tv-transcode": {
        "MaxStreamingBitrate": 20000000,
        "DirectPlayProfiles": [{"Container": "mp4", "Type": "Video", "VideoCodec": "hevc", "AudioCodec": "ac3"}],
        "TranscodingProfiles": [{"Container": "ts", "Type": "Video", "VideoCodec": "h264", "AudioCodec": "aac",
                                 "Protocol": "hls", "Context": "Streaming", "BreakOnNonKeyFrames": True}],
        "SubtitleProfiles": [{"Format": "srt", "Method": "Encode"}],
    },
    "alleen-audio": {
        "MaxStreamingBitrate": 320000,
        "DirectPlayProfiles": [{"Container": "mp3", "Type": "Audio"}],
        "TranscodingProfiles": [{"Container": "mp3", "Type": "Audio", "AudioCodec": "mp3", "Protocol": "http",
                                 "Context": "Streaming"}],
    },
}


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize(node: Any) -> Any:
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in VLUCHTIG:
                continue
            if key == "TranscodingUrl" and isinstance(value, str):
                # ApiKey = het sessietoken van deze aanmelding (upstream zet het in de transcode-URL); nooit in het rapport.
                value = re.sub(r"(PlaySessionId|DeviceId|ApiKey|api_key)=[^&]*", r"\1=<x>", value)
            out[key] = normalize(value)
        return out
    if isinstance(node, list):
        return [normalize(v) for v in node]
    return node


class Kant:
    def __init__(self, label: str, image: str, config: Path, work: Path, music: Path, films: Path) -> None:
        self.label, self.image, self.config = label, image, config
        self.work, self.music, self.films = work, music, films
        self.name = f"jl-compat-{os.getpid()}-{label}"
        self.port = 0

    def start(self) -> str:
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        cache = self.work / f"cache-{self.label}"
        cache.mkdir(exist_ok=True)
        docker("rm", "-f", self.name, check=False)
        docker("run", "-d", "--name", self.name, "--user", f"{os.getuid()}:{os.getgid()}", "--memory", "3g",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "-e", "TZ=UTC",
               "-p", f"127.0.0.1:{self.port}:8096", "-v", f"{self.config}:/config", "-v", f"{cache}:/cache",
               "-v", f"{self.music}:{MUSIC}:ro", "-v", f"{self.films}:{FILMS}:ro", self.image)
        return wacht_klaar(self.url, timeout=300).get("Version", "")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        docker("stop", "-t", "30", self.name, check=False, timeout=120)
        docker("rm", "-f", self.name, check=False)


def login(url: str, user: str, password: str) -> tuple[Http, str]:
    auth = Http(url, {"Authorization": CLIENT}).doe("POST", "/Users/AuthenticateByName",
                                                     body={"Username": user, "Pw": password})
    return Http(url, {"Authorization": CLIENT + f', Token="{auth["AccessToken"]}"'}), auth["User"]["Id"]


def collect(kant: Kant, password: str) -> dict[str, Any]:
    api, uid = login(kant.url, "jl-compat-beheer", password)
    out: dict[str, Any] = {}
    info = Http(kant.url).doe("GET", "/System/Info/Public")
    out["/System/Info/Public"] = {k: info.get(k) for k in ("ProductName", "Version", "Id", "StartupWizardCompleted")}
    out["/UserViews"] = api.doe("GET", "/UserViews", {"userId": uid})
    items = api.doe("GET", "/Items", {"userId": uid, "recursive": "true", "includeItemTypes": "Movie,Audio",
                                      "fields": "Path,MediaStreams,MediaSources,ProviderIds,Tags", "sortBy": "SortName"})
    out["/Items"] = items
    for item in items.get("Items", []):
        iid = item["Id"]
        out[f"/Items/{iid}"] = api.doe("GET", f"/Items/{iid}", {"userId": uid})
        out[f"/Items/{iid}/Similar"] = api.doe("GET", f"/Items/{iid}/Similar", {"userId": uid, "limit": "12"})
        out[f"/MediaSegments/{iid}"] = api.doe("GET", f"/MediaSegments/{iid}")
        source = (item.get("MediaSources") or [{}])[0]
        audio = next((s["Index"] for s in source.get("MediaStreams", []) if s.get("Type") == "Audio"), None)
        for naam, profiel in PROFIELEN.items():
            body = {"UserId": uid, "DeviceProfile": profiel, "MediaSourceId": source.get("Id"), "AudioStreamIndex": audio,
                    "EnableDirectPlay": True, "EnableDirectStream": True, "EnableTranscoding": True,
                    "AllowVideoStreamCopy": True, "AllowAudioStreamCopy": True, "AutoOpenLiveStream": False}
            out[f"PlaybackInfo {item.get('Path', iid).rsplit('/', 1)[-1]} [{naam}]"] = api.doe(
                "POST", f"/Items/{iid}/PlaybackInfo", {"userId": uid}, body=body)
    out["/Shows/NextUp"] = api.doe("GET", "/Shows/NextUp", {"userId": uid})
    out["/UserItems/Resume"] = api.doe("GET", "/UserItems/Resume", {"userId": uid})
    out["/SyncPlay/List"] = api.doe("GET", "/SyncPlay/List")
    openapi = api.doe("GET", "/api-docs/openapi.json")
    return {"antwoorden": normalize(out), "openapi": openapi}


def compare_openapi(stock: dict[str, Any], fork: dict[str, Any]) -> tuple[list[str], list[str]]:
    sp, fp = stock.get("paths", {}), fork.get("paths", {})
    added = sorted(p for p in fp if p not in sp)
    problems = [f"pad alleen in Jelly Leon buiten {ADDITIEF}: {p}" for p in added if not p.startswith(ADDITIEF)]
    problems += [f"pad van stock ontbreekt in Jelly Leon: {p}" for p in sorted(sp) if p not in fp]
    a = strip_descriptions({k: v for k, v in sp.items()})
    b = strip_descriptions({k: v for k, v in fp.items() if k in sp})
    if a != b:
        problems += [f"gedeeld pad gewijzigd: {d}" for d in differences(a, b)[:10]]
    ss = stock.get("components", {}).get("schemas", {})
    fs = fork.get("components", {}).get("schemas", {})
    extra_schemas = sorted(set(fs) - set(ss))
    if strip_descriptions(ss) != strip_descriptions({k: fs.get(k) for k in ss}):
        problems += [f"gedeeld schema gewijzigd: {d}" for d in differences(strip_descriptions(ss), strip_descriptions(
            {k: fs.get(k) for k in ss}))[:10]]
    return problems, added + [f"schema {s}" for s in extra_schemas]


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0915 - één doorlopend scenario
    parser = argparse.ArgumentParser(description="API- en gedragsregressie Jelly Leon tegen stock 12.x (JLT-64, JLT-63).")
    parser.add_argument("--image", required=True, help="jelly-leon-image (lokaal gebouwd)")
    parser.add_argument("--stock-image", default=STOCK_NEW_IMAGE)
    parser.add_argument("--werkmap", default=None)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="jl-compat-", dir=args.werkmap))
    music, films, base = work / "media-muziek", work / "media-films", work / "config-basis"
    for d in (music, films, base):
        d.mkdir(parents=True)
    subprocess.run([sys.executable, str(E2E / "make_test_media.py"), str(music)], check=True, capture_output=True)
    target = films / FILM_REL
    target.parent.mkdir(parents=True)
    docker("run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
           "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffmpeg", "-v", f"{target.parent}:/out", OLD_IMAGE, "-hide_banner",
           "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=4", "-f", "lavfi", "-i",
           "sine=frequency=440:duration=4", "-f", "lavfi", "-i", "sine=frequency=880:duration=4",
           "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
           "-b:a", "32k", "-metadata:s:a:0", "language=nld", "-metadata:s:a:1", "language=eng",
           "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", f"/out/{target.name}")
    password = uuid.uuid4().hex
    steps: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> bool:
        steps.append({"stap": name, "geslaagd": ok, "detail": detail.replace(password, "<geheim>"), "tijd": utc_now()})
        print(f"[{'OK  ' if ok else 'FOUT'}] {name}: {detail[:400]}", flush=True)
        return ok

    result: dict[str, Any] = {}
    try:
        basis = Kant("basis", args.stock_image, base, work, music, films)
        basis.start()
        anon = Http(basis.url, {"Authorization": CLIENT})
        for attempt in range(30):
            if anon.ruw("POST", "/Startup/Configuration", body={"UICulture": "nl", "MetadataCountryCode": "NL",
                                                                "PreferredMetadataLanguage": "nl"})[0] in (200, 204):
                break
            time.sleep(2)
            if attempt == 29:
                raise RuntimeError("startwizard niet beschikbaar")
        anon.doe("GET", "/Startup/User")
        anon.doe("POST", "/Startup/User", body={"Name": "jl-compat-beheer", "Password": password})
        anon.doe("POST", "/Startup/RemoteAccess", body={"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False})
        anon.doe("POST", "/Startup/Complete")
        api, uid = login(basis.url, "jl-compat-beheer", password)
        for naam, soort, pad in (("Films", "movies", FILMS), ("Muziek", "music", MUSIC)):
            api.doe("POST", "/Library/VirtualFolders", {"name": naam, "collectionType": soort, "paths": pad,
                                                        "refreshLibrary": "false"}, body={"LibraryOptions": {
                                                            "EnableRealtimeMonitor": False, "SaveLocalMetadata": False,
                                                            "EnableTrickplayImageExtraction": False,
                                                            "EnableChapterImageExtraction": False}})
        api.doe("POST", "/Library/Refresh")
        deadline = time.monotonic() + 180
        items: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            items = api.doe("GET", "/Items", {"userId": uid, "recursive": "true", "includeItemTypes": "Movie,Audio"})["Items"]
            tasks = api.doe("GET", "/ScheduledTasks", {"isHidden": "false"})
            if len(items) >= 2 and not any(t.get("State") == "Running" for t in tasks):
                break
            time.sleep(2)
        api.doe("POST", "/Users/New", body={"Name": "jl-compat-gebruiker", "Password": password})
        for item in items:
            api.doe("POST", f"/UserItems/{item['Id']}/UserData", {"userId": uid},
                    body={"Played": True, "PlayCount": 1, "IsFavorite": True})
        basis.stop()
        add("datamap ingericht met stock 12.x", len(items) >= 2, f"{len(items)} items (testfilm + WAV)")
        kanten = {}
        for label, image in (("stock", args.stock_image), ("jelly-leon", args.image)):
            config = work / f"config-{label}"
            shutil.copytree(base, config, symlinks=True)
            kant = Kant(label, image, config, work, music, films)
            versie = kant.start()
            try:
                kanten[label] = collect(kant, password)
                kanten[label]["versie"] = versie
            finally:
                kant.stop()
        add("zelfde serverversie", kanten["stock"]["versie"] == kanten["jelly-leon"]["versie"],
            f"stock {kanten['stock']['versie']}, Jelly Leon {kanten['jelly-leon']['versie']}")
        verschillen = differences(kanten["stock"]["antwoorden"], kanten["jelly-leon"]["antwoorden"])
        pbi = [k for k in kanten["stock"]["antwoorden"] if k.startswith("PlaybackInfo")]
        besluiten = {k: [(s.get("SupportsDirectPlay"), s.get("SupportsTranscoding"), bool(s.get("TranscodingUrl")))
                         for s in kanten["jelly-leon"]["antwoorden"][k].get("MediaSources", [])] for k in pbi}
        add("Jellyfin-antwoorden Jelly Leon = stock (vaste veldenlijst, vluchtige velden weg)", not verschillen,
            f"{len(kanten['stock']['antwoorden'])} antwoorden vergeleken, {len(verschillen)} verschillen"
            + ("; " + "; ".join(verschillen[:6]) if verschillen else ""))
        dp = any(v and v[0][0] for v in besluiten.values())
        tc = any(v and v[0][2] for v in besluiten.values())
        add("PlaybackInfo dekt Direct Play én transcode", dp and tc, json.dumps(besluiten, ensure_ascii=False))
        problemen, toegevoegd = compare_openapi(kanten["stock"]["openapi"], kanten["jelly-leon"]["openapi"])
        add("OpenAPI van de server: alleen additief onder /media/v1 en /connector/v1", not problemen,
            f"toegevoegd: {toegevoegd}" + ("; " + "; ".join(problemen[:6]) if problemen else ""))
        result = {"verschillen": verschillen, "playbackinfo_besluiten": besluiten, "openapi_toegevoegd": toegevoegd,
                  "openapi_problemen": problemen, "vergeleken": sorted(kanten["stock"]["antwoorden"])}
    except (RuntimeError, subprocess.TimeoutExpired, OSError, KeyError) as exc:
        add("uitvoering", False, f"{type(exc).__name__}: {str(exc)[:400]}")
    finally:
        for label in ("basis", "stock", "jelly-leon"):
            docker("rm", "-f", f"jl-compat-{os.getpid()}-{label}", check=False)
        shutil.rmtree(work, ignore_errors=True)
    passed = bool(steps) and all(s["geslaagd"] for s in steps)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({
            "schema": "jelly-leon/compat-api/1", "soort": "Sim-getest (twee wegwerpcontainers op kopieën van één datamap)",
            "images": {"stock": args.stock_image, "jelly_leon": args.image}, "geslaagd": passed, "stappen": steps,
            **copy.deepcopy(result)}, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"RESULTAAT: {'GESLAAGD' if passed else 'MISLUKT'} ({sum(s['geslaagd'] for s in steps)}/{len(steps)})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
