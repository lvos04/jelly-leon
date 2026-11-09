#!/usr/bin/env python3
"""Stock-client-smoketest voor Jelly Leon (B03-001, I24 stap 1) — simuleert wat stock Jellyfin-clients doen.

Dit is een SIMULATOR van het clientprotocol (HTTP-verzoeken zoals Jellyfin Web/Android/Kodi ze sturen), géén test op
echte apparaten. Resultaat telt als "Sim-getest"; echte clients/tv's blijven NIET GEVALIDEERD.

Controleert tegen een draaiende server (eigen build van deze fork, lege datamap):
  1. /health en /System/Info/Public: ProductName "Jellyfin Server" en Version == upstream-basis (technische identiteit);
  2. eerste-startwizard via de upstream-API;
  3. inloggen met de moderne `Authorization: MediaBrowser …`-header én de oude `X-Emby-Authorization`-header;
  4. negatieve tests: fout wachtwoord → 401, geen token → 401, Jelly Leon-route zonder token → 401;
     (waarneming, geen slaagcriterium: upstream-streamroutes zijn anoniem bereikbaar — zie INVENTARIS.md §7);
  5. bibliotheek aanmaken, scannen en een audio-item statisch streamen (volledig én met Range → 206), byte-gelijk;
  6. sessies zichtbaar; Jelly Leon-plugin `GET /media/v1/version` geeft status `compatibel`.

Alleen standaardbibliotheek. Schrijft een JSON-rapport (tokens geredigeerd). Exitcode 0 = alles geslaagd.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CLIENTS = {
    "web": {"Client": "Jellyfin Web", "Device": "Firefox", "DeviceId": "jl-smoke-web-0001", "Version": "10.11.11"},
    "android": {"Client": "Jellyfin Android", "Device": "Pixel", "DeviceId": "jl-smoke-android-0001", "Version": "2.6.3"},
    "kodi": {"Client": "Kodi", "Device": "Woonkamer", "DeviceId": "jl-smoke-kodi-0001", "Version": "1.0.0"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def auth_value(client: dict[str, str], token: str | None = None) -> str:
    parts = [f'{key}="{value}"' for key, value in client.items()]
    if token:
        parts.append(f'Token="{token}"')
    return "MediaBrowser " + ", ".join(parts)


@dataclass
class Report:
    base_url: str
    started_at: str = field(default_factory=utc_now)
    steps: list[dict] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "***")
        return text

    def observe(self, name: str, detail: str) -> None:
        entry = {"waarneming": name, "detail": self.redact(detail), "tijd": utc_now()}
        self.observations.append(entry)
        print(f"[INFO] {name}: {entry['detail']}")

    def add(self, name: str, ok: bool, detail: str) -> None:
        entry = {"stap": name, "geslaagd": ok, "detail": self.redact(detail), "tijd": utc_now()}
        self.steps.append(entry)
        print(f"[{'OK  ' if ok else 'FOUT'}] {name}: {entry['detail']}")

    @property
    def passed(self) -> bool:
        return bool(self.steps) and all(step["geslaagd"] for step in self.steps)


class Client:
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: object | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        data = None
        all_headers = {"Accept": "application/json"}
        if headers:
            all_headers.update(headers)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            all_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=all_headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (alleen lokale testserver)
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as err:
            return err.code, dict(err.headers or {}), err.read()

    def json(self, method: str, path: str, **kwargs) -> tuple[int, object]:
        status, _, raw = self.request(method, path, **kwargs)
        try:
            return status, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return status, raw.decode("utf-8", errors="replace")[:200]


def wait_healthy(client: Client, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            status, _, body = client.request("GET", "/health", headers={"Accept": "text/plain"})
            if status == 200 and body.strip() == b"Healthy":
                return True
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(2)
    return False


def run(args: argparse.Namespace) -> Report:
    client = Client(args.url)
    report = Report(base_url=args.url)
    media_file = Path(args.media_file)
    media_bytes = media_file.read_bytes()
    media_sha = hashlib.sha256(media_bytes).hexdigest()

    if not wait_healthy(client, args.start_timeout):
        report.add("health", False, f"/health niet 'Healthy' binnen {args.start_timeout}s")
        return report
    report.add("health", True, "/health = Healthy")

    status, info = client.json("GET", "/System/Info/Public")
    ok = (
        status == 200
        and isinstance(info, dict)
        and info.get("ProductName") == "Jellyfin Server"
        and info.get("Version") == args.expected_version
    )
    report.add(
        "technische identiteit",
        ok,
        f"HTTP {status}; ProductName={info.get('ProductName') if isinstance(info, dict) else '?'}; "
        f"Version={info.get('Version') if isinstance(info, dict) else '?'} (verwacht {args.expected_version})",
    )
    if not ok:
        return report

    # Eerste-startwizard (zoals Jellyfin Web dat doet).
    steps = [
        ("POST", "/Startup/Configuration", {"UICulture": "nl", "MetadataCountryCode": "NL", "PreferredMetadataLanguage": "nl"}),
        ("GET", "/Startup/User", None),
        ("POST", "/Startup/User", {"Name": args.username, "Password": args.password}),
        ("POST", "/Startup/RemoteAccess", {"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False}),
        ("POST", "/Startup/Complete", None),
    ]
    report.secrets.append(args.password)
    wizard_ok = True
    for method, path, body in steps:
        status, _, _ = client.request(method, path, body=body)
        if status not in (200, 204):
            wizard_ok = False
            report.add("startwizard", False, f"{method} {path} gaf HTTP {status}")
            break
    if wizard_ok:
        report.add("startwizard", True, "configuratie, eerste gebruiker en afronden via upstream-API")
    else:
        return report

    # Negatief: fout wachtwoord.
    status, _, _ = client.request(
        "POST",
        "/Users/AuthenticateByName",
        headers={"Authorization": auth_value(CLIENTS["web"])},
        body={"Username": args.username, "Pw": args.password + "-fout"},
    )
    report.add("fout wachtwoord geweigerd", status == 401, f"HTTP {status} (verwacht 401)")

    tokens: dict[str, str] = {}
    user_id = ""
    for name, header_name in (("web", "Authorization"), ("android", "Authorization"), ("kodi", "X-Emby-Authorization")):
        status, body = client.json(
            "POST",
            "/Users/AuthenticateByName",
            headers={header_name: auth_value(CLIENTS[name])},
            body={"Username": args.username, "Pw": args.password},
        )
        token = body.get("AccessToken") if isinstance(body, dict) else None
        if status == 200 and token:
            tokens[name] = token
            report.secrets.append(token)
            user_id = body["User"]["Id"]
        report.add(
            f"inloggen {CLIENTS[name]['Client']} ({header_name})",
            status == 200 and bool(token),
            f"HTTP {status}",
        )
    if len(tokens) != len(CLIENTS):
        return report

    web_auth = {"Authorization": auth_value(CLIENTS["web"], tokens["web"])}
    status, me = client.json("GET", "/Users/Me", headers=web_auth)
    report.add("gebruiker opvragen", status == 200 and isinstance(me, dict) and me.get("Id") == user_id, f"HTTP {status}")
    status, _, _ = client.request("GET", "/Users/Me")
    report.add("zonder token geweigerd", status == 401, f"HTTP {status} (verwacht 401)")
    legacy = {"X-Emby-Token": tokens["kodi"]}
    status, _ = client.json("GET", "/Users/Me", headers=legacy)
    report.add("oude X-Emby-Token-header", status == 200, f"HTTP {status}")

    # Bibliotheek aanmaken en scannen.
    query = urllib.parse.urlencode(
        {"name": "Muziek", "collectionType": "music", "paths": args.library_path, "refreshLibrary": "true"}
    )
    status, _, _ = client.request("POST", f"/Library/VirtualFolders?{query}", headers=web_auth, body={"LibraryOptions": {}})
    report.add("bibliotheek aanmaken", status in (200, 204), f"HTTP {status}")
    item_id = ""
    deadline = time.monotonic() + args.scan_timeout
    while time.monotonic() < deadline and not item_id:
        items_query = urllib.parse.urlencode({"Recursive": "true", "IncludeItemTypes": "Audio", "userId": user_id})
        status, body = client.json("GET", f"/Items?{items_query}", headers=web_auth)
        if status == 200 and isinstance(body, dict) and body.get("Items"):
            item_id = body["Items"][0]["Id"]
            break
        status, _, _ = client.request("POST", "/Library/Refresh", headers=web_auth)
        time.sleep(3)
    report.add("bibliotheekscan vindt item", bool(item_id), f"item {item_id or 'niet gevonden'}")
    if not item_id:
        return report

    android_auth = {"Authorization": auth_value(CLIENTS["android"], tokens["android"])}
    status, headers, body = client.request("GET", f"/Audio/{item_id}/stream?static=true", headers=android_auth)
    same = hashlib.sha256(body).hexdigest() == media_sha
    report.add("statisch streamen (Android)", status == 200 and same, f"HTTP {status}; {len(body)} bytes; byte-gelijk={same}")
    range_headers = dict(android_auth, Range="bytes=100-199")
    status, headers, body = client.request("GET", f"/Audio/{item_id}/stream?static=true", headers=range_headers)
    report.add(
        "streamen met Range (seek)",
        status == 206 and body == media_bytes[100:200],
        f"HTTP {status}; {len(body)} bytes",
    )
    # Waarneming (geen slaagcriterium): upstream 10.11 heeft géén [Authorize] op de stream-routes van
    # Audio-/VideosController; wie een item-ID kent, kan zonder token streamen. Dat is upstream-gedrag (bewust
    # niet gepatcht in P0) en een risico voor B03-010 (kinderprofielen) — zie INVENTARIS.md §7.
    status, _, _ = client.request("GET", f"/Audio/{item_id}/stream?static=true")
    report.observe(
        "upstream-gedrag: streamen zonder token",
        f"HTTP {status}; {'anoniem streamen mogelijk (upstream-risico, zie INVENTARIS.md §7)' if status == 200 else 'geweigerd'}",
    )

    status, sessions = client.json("GET", "/Sessions", headers=web_auth)
    device_ids = {s.get("DeviceId") for s in sessions} if isinstance(sessions, list) else set()
    expected = {c["DeviceId"] for c in CLIENTS.values()}
    report.add("sessies zichtbaar", status == 200 and expected <= device_ids, f"HTTP {status}; apparaten {sorted(device_ids)}")

    if args.expect_plugin:
        status, body = client.json("GET", "/media/v1/version", headers=web_auth)
        ok = status == 200 and isinstance(body, dict) and body.get("status") == "compatibel"
        detail = f"HTTP {status}"
        if isinstance(body, dict):
            detail += f"; status={body.get('status')}; fork_version={body.get('fork_version')}; reason={body.get('reason_code')}"
        report.add("Jelly Leon-plugin /media/v1/version", ok, detail)
        status, _, _ = client.request("GET", "/media/v1/version")
        report.add("plugin-route zonder token geweigerd", status == 401, f"HTTP {status} (verwacht 401)")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stock-client-smoketest (simulator) tegen een Jelly Leon-server.")
    parser.add_argument("--url", required=True, help="bv. http://127.0.0.1:38096")
    parser.add_argument("--expected-version", required=True, help="upstream-versie die de server moet melden")
    parser.add_argument("--media-file", required=True, help="lokaal pad van het testbestand (voor bytevergelijking)")
    parser.add_argument("--library-path", required=True, help="pad van de muziekmap zoals de server hem ziet")
    parser.add_argument("--username", default="jl-smoke-admin")
    parser.add_argument("--password", default="jl-smoke-wachtwoord-niet-geheim")
    parser.add_argument("--expect-plugin", action="store_true")
    parser.add_argument("--start-timeout", type=float, default=180)
    parser.add_argument("--scan-timeout", type=float, default=180)
    parser.add_argument("--report", help="pad voor het JSON-rapport")
    args = parser.parse_args(argv)
    report = run(args)
    result = {
        "soort": "Sim-getest (protocolsimulator, geen echte clients/apparaten)",
        "base_url": report.base_url,
        "gestart": report.started_at,
        "klaar": utc_now(),
        "geslaagd": report.passed,
        "stappen": report.steps,
        "waarnemingen": report.observations,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RESULTAAT: {'GESLAAGD' if report.passed else 'MISLUKT'} ({sum(s['geslaagd'] for s in report.steps)}/{len(report.steps)})")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
