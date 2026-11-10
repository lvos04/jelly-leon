#!/usr/bin/env python3
"""Runtime-contracttests van het register van upstream-gedrag (B03-019 a/d, §10.11) tegen een draaiende 12.x-server.

Het register `docs/platform-v2/UPSTREAM_GEDRAG.md` koppelt elke regel `UG-<functie>-<n>` aan een anker in de
upstream-bron (statisch, tools/jelly-leon/upstream_gedrag_check.py) en waar nodig aan een runtime-test hier
(`runtime:<naam>`). Deze runner start één wegwerpcontainer van `--image` (standaard: de `JL_RUNTIME_IMAGE` van de
CI, stock jellyfin/jellyfin:12.x op digest; ook te gebruiken op de jelly-leon-image), richt hem in met een
zelfgemaakt WAV-bestand en meet het gedrag. Een afwijking laat de build (en de upstream-sync, JLT-67) falen met de
betrokken UG-regel in de melding — nooit stil aanpassen: eerst het gedrag opnieuw beoordelen.

Alleen 127.0.0.1, als de aanroeper, zonder capabilities, media alleen-lezen. Exitcode 0 = alle tests geslaagd.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

E2E = Path(__file__).resolve().parent
REPO = E2E.parents[2]
sys.path.insert(0, str(REPO / "tools" / "b03-harnas"))

from b03h.jfapi import Http, wacht_klaar  # noqa: E402

CLIENT = 'MediaBrowser Client="jelly-leon-ug", Device="ug", DeviceId="jl-ug-runtime", Version="1.0"'
USER = "jl-ug-beheer"
MUSIC = "/media/muziek"


class Ctx:
    def __init__(self, url: str, password: str) -> None:
        self.url = url
        self.password = password
        self.anon = Http(url, {"Authorization": CLIENT})
        self.token = ""
        self.api: Http | None = None
        self.openapi: dict[str, Any] = {}
        self.audio_id = ""

    @property
    def a(self) -> Http:
        assert self.api is not None
        return self.api


# ----------------------------------------------------------------------------------------------- tests
def legacy_auth_uit(c: Ctx) -> tuple[bool, str]:
    """UG-GEM-1: EnableLegacyAuthorization staat uit; X-Emby-*, api_key werken niet, de moderne header wel."""
    cfg = c.a.doe("GET", "/System/Configuration")
    codes = {
        "login X-Emby-Authorization": Http(c.url).ruw(
            "POST", "/Users/AuthenticateByName", body={"Username": USER, "Pw": c.password},
            headers={"X-Emby-Authorization": CLIENT})[0],
        "X-Emby-Token": Http(c.url, {"X-Emby-Token": c.token}).ruw("GET", "/Users/Me")[0],
        "api_key": Http(c.url).ruw("GET", "/Users/Me", {"api_key": c.token})[0],
        "Authorization MediaBrowser Token": c.a.ruw("GET", "/Users/Me")[0],
    }
    ok = cfg.get("EnableLegacyAuthorization") is False and codes == {
        "login X-Emby-Authorization": 400, "X-Emby-Token": 401, "api_key": 401, "Authorization MediaBrowser Token": 200}
    return ok, f"EnableLegacyAuthorization={cfg.get('EnableLegacyAuthorization')}; HTTP {codes}"


def stream_zonder_token(c: Ctx) -> tuple[bool, str]:
    """UG-GEM-2: statische stream-routes vragen geen token (upstream-risico; B03-010 houdt dit bij)."""
    status, body, _ = Http(c.url).ruw("GET", f"/Audio/{c.audio_id}/stream", {"static": "true"},
                                      headers={"Range": "bytes=0-99"})
    return status in (200, 206) and len(body) > 0, f"zonder token: HTTP {status}, {len(body)} bytes"


def hls_verborgen_maar_actief(c: Ctx) -> tuple[bool, str]:
    """UG-GEM-3: HLS-playlists staan niet meer in de OpenAPI (IgnoreApi) maar de routes bestaan (401, niet 404)."""
    paths = set(c.openapi.get("paths", {}))
    hidden = [p for p in ("/Videos/{itemId}/master.m3u8", "/Videos/{itemId}/main.m3u8", "/Audio/{itemId}/master.m3u8")
              if p not in paths]
    fake = uuid.uuid4().hex
    codes = {p: Http(c.url).ruw("GET", p.format(itemId=fake))[0] for p in
             ("/Videos/{itemId}/master.m3u8", "/Videos/{itemId}/main.m3u8", "/Audio/{itemId}/master.m3u8")}
    ok = len(hidden) == 3 and all(code == 401 for code in codes.values())
    return ok, f"niet in OpenAPI: {len(hidden)}/3; zonder token HTTP {codes} (404 = route verdwenen)"


def mediasegmenten_alleen_lezen(c: Ctx) -> tuple[bool, str]:
    """UG-GEM-4: MediaSegments-REST is alleen GET; segmenttypen ongewijzigd (F6 publiceert via eigen opslag)."""
    ops = {k: sorted(v) for k, v in c.openapi.get("paths", {}).items() if k.startswith("/MediaSegments")}
    enum = c.openapi.get("components", {}).get("schemas", {}).get("MediaSegmentType", {}).get("enum")
    ok = ops == {"/MediaSegments/{itemId}": ["get"]} and enum == ["Unknown", "Commercial", "Preview", "Recap", "Outro", "Intro"]
    return ok, f"routes {ops}; MediaSegmentType {enum}"


def syncplay_routes(c: Ctx) -> tuple[bool, str]:
    """UG-GEM-5: 22 SyncPlay-routes (F1 bouwt erop als decorator; een nieuwe/verdwenen route vraagt herbeoordeling)."""
    ops = sorted(f"{m.upper()} {p}" for p, v in c.openapi.get("paths", {}).items() if p.startswith("/SyncPlay")
                 for m in v)
    return len(ops) == 22, f"{len(ops)} operaties"


def hardwareversnelling_standaard_uit(c: Ctx) -> tuple[bool, str]:
    """UG-GEM-6: hardwareversnelling staat standaard uit (F5 hardwareversnelling-assistent, B03-062)."""
    enc = c.a.doe("GET", "/System/Configuration/encoding")
    return enc.get("HardwareAccelerationType") == "none", f"HardwareAccelerationType={enc.get('HardwareAccelerationType')}"


CHECKS: dict[str, Callable[[Ctx], tuple[bool, str]]] = {
    "legacy_auth_uit": legacy_auth_uit,
    "stream_zonder_token": stream_zonder_token,
    "hls_verborgen_maar_actief": hls_verborgen_maar_actief,
    "mediasegmenten_alleen_lezen": mediasegmenten_alleen_lezen,
    "syncplay_routes": syncplay_routes,
    "hardwareversnelling_standaard_uit": hardwareversnelling_standaard_uit,
}


# ----------------------------------------------------------------------------------------------- opzet
def docker(*args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, check=False, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:3])} … → {proc.returncode}: {proc.stderr.strip()[:300]}")
    return proc


def free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def prepare(c: Ctx) -> None:
    for attempt in range(30):
        status = c.anon.ruw("POST", "/Startup/Configuration",
                            body={"UICulture": "nl", "MetadataCountryCode": "NL", "PreferredMetadataLanguage": "nl"})[0]
        if status in (200, 204):
            break
        if attempt == 29:
            raise RuntimeError(f"startwizard niet beschikbaar (HTTP {status})")
        time.sleep(2)
    c.anon.doe("GET", "/Startup/User")
    c.anon.doe("POST", "/Startup/User", body={"Name": USER, "Password": c.password})
    c.anon.doe("POST", "/Startup/RemoteAccess", body={"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False})
    c.anon.doe("POST", "/Startup/Complete")
    auth = c.anon.doe("POST", "/Users/AuthenticateByName", body={"Username": USER, "Pw": c.password})
    c.token = auth["AccessToken"]
    c.api = Http(c.url, {"Authorization": CLIENT + f', Token="{c.token}"'})
    c.a.doe("POST", "/Library/VirtualFolders", {"name": "Muziek", "collectionType": "music", "paths": MUSIC,
                                                "refreshLibrary": "true"}, body={"LibraryOptions": {}})
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline and not c.audio_id:
        items = c.a.doe("GET", "/Items", {"recursive": "true", "includeItemTypes": "Audio"}).get("Items", [])
        c.audio_id = items[0]["Id"] if items else ""
        if not c.audio_id:
            c.a.doe("POST", "/Library/Refresh")
            time.sleep(3)
    if not c.audio_id:
        raise RuntimeError("bibliotheekscan vond het testbestand niet")
    status, raw, _ = c.a.ruw("GET", "/api-docs/openapi.json")
    if status != 200:
        raise RuntimeError(f"/api-docs/openapi.json gaf HTTP {status}")
    c.openapi = json.loads(raw.decode("utf-8-sig"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Runtime-contracttests van UPSTREAM_GEDRAG.md (B03-019).")
    parser.add_argument("--image", required=True, help="server-image op digest (JL_RUNTIME_IMAGE) of een lokale build")
    parser.add_argument("--werkmap", default=None)
    parser.add_argument("--rapport", type=Path)
    parser.add_argument("--alleen", action="append", choices=sorted(CHECKS), help="alleen deze test(s)")
    args = parser.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="jl-ug-", dir=args.werkmap))
    for sub in ("config", "cache", "media"):
        (work / sub).mkdir()
    subprocess.run([sys.executable, str(E2E / "make_test_media.py"), str(work / "media")], check=True, capture_output=True)
    name, port = f"jl-ug-{os.getpid()}", free_port()
    password = uuid.uuid4().hex
    results: list[dict[str, Any]] = []
    try:
        docker("run", "-d", "--name", name, "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--memory", "2g", "-e", "TZ=UTC", "-p", f"127.0.0.1:{port}:8096",
               "-v", f"{work / 'config'}:/config", "-v", f"{work / 'cache'}:/cache",
               "-v", f"{work / 'media'}:{MUSIC}:ro", args.image)
        info = wacht_klaar(f"http://127.0.0.1:{port}", timeout=300)
        ctx = Ctx(f"http://127.0.0.1:{port}", password)
        prepare(ctx)
        for check_name in args.alleen or sorted(CHECKS):
            try:
                ok, detail = CHECKS[check_name](ctx)
            except Exception as exc:  # noqa: BLE001 - elke fout = test mislukt, met melding
                ok, detail = False, f"{type(exc).__name__}: {str(exc)[:200]}"
            detail = detail.replace(ctx.token, "<geheim>") if ctx.token else detail
            results.append({"test": f"runtime:{check_name}", "geslaagd": ok, "detail": detail})
            print(f"[{'OK  ' if ok else 'FOUT'}] runtime:{check_name}: {detail}", flush=True)
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        results.append({"test": "opzet", "geslaagd": False, "detail": str(exc)[:400]})
        print(f"[FOUT] opzet: {exc}", file=sys.stderr)
        info = {}
    finally:
        docker("rm", "-f", name, check=False)
        shutil.rmtree(work, ignore_errors=True)
    passed = bool(results) and all(r["geslaagd"] for r in results)
    if args.rapport:
        args.rapport.parent.mkdir(parents=True, exist_ok=True)
        args.rapport.write_text(json.dumps({
            "schema": "jelly-leon/upstream-gedrag-runtime/1", "image": args.image,
            "server": {"versie": info.get("Version"), "product": info.get("ProductName")},
            "tijd": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "geslaagd": passed, "tests": results,
            "soort": "Sim-getest (wegwerpcontainer op 127.0.0.1)"}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RESULTAAT: {'GESLAAGD' if passed else 'MISLUKT'} ({sum(r['geslaagd'] for r in results)}/{len(results)})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
