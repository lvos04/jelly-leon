#!/usr/bin/env python3
"""Stock-client-smoketest voor Jelly Leon (B03-001, I24 stap 1) — simuleert wat stock Jellyfin-clients doen.

Dit is een SIMULATOR van het clientprotocol (HTTP-verzoeken zoals Jellyfin Web/Android/Kodi ze sturen), géén test op
echte apparaten. Resultaat telt als "Sim-getest"; echte clients/tv's blijven NIET GEVALIDEERD.

Controleert tegen een draaiende server (eigen build van deze fork):
  1. /health en /System/Info/Public: ProductName "Jellyfin Server" en Version == upstream-basis (technische identiteit);
  2. modus `nieuw` (lege datamap): eerste-startwizard via de upstream-API, daarna is de wizard niet meer anoniem
     bereikbaar; modus `herstart` (na herstart/herinstallatie met dezelfde opslag): wizard staat op afgerond en blijft
     dicht — gebruiker, bibliotheek en item-ID zijn behouden (geen dataverlies);
  3. inloggen met de moderne `Authorization: MediaBrowser …`-header; de oude headers (`X-Emby-Authorization`,
     `X-Emby-Token`, `?api_key=`) werken alleen als EnableLegacyAuthorization aan staat. Vanaf 12.x staat die
     standaard uit en blijft uit (BG-01): dan MOETEN ze geweigerd worden (`--legacy-auth auto` = uit vanaf 12.x);
  4. negatieve tests: fout wachtwoord → 401, geen token → 401, Jelly Leon-route zonder token → 401;
     (waarneming, geen slaagcriterium: upstream-streamroutes zijn anoniem bereikbaar — zie INVENTARIS.md §7);
  5. bibliotheek (aanmaken in modus `nieuw`), scannen en een audio-item statisch streamen (volledig én met Range → 206),
     byte-gelijk;
  6. sessies zichtbaar; Jelly Leon-plugin `GET /media/v1/version` geeft status `compatibel`;
  7. Hub-adapter v1 (contract 1.2 §2.3, JL4, ADR-0012; alleen met `--expect-plugin`): een eigen NIET-admin-gebruiker
     (bestaat al of wordt door de beheerder aangemaakt) kan inloggen en `GET /media/v1/version` lezen, maar ziet geen
     API-sleutels (`/Auth/Keys` → 403); een Hub-JWT wordt nergens geaccepteerd (`Bearer` en als Jellyfin-token → 401).

Alleen standaardbibliotheek. Schrijft een JSON-rapport (tokens geredigeerd; met item- en gebruikers-ID voor een
volgende `herstart`-run). Exitcode 0 = alles geslaagd.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

CLIENTS = {
    "web": {"Client": "Jellyfin Web", "Device": "Firefox", "DeviceId": "jl-smoke-web-0001", "Version": "12.4.0"},
    "android": {"Client": "Jellyfin Android", "Device": "Pixel", "DeviceId": "jl-smoke-android-0001", "Version": "2.6.3"},
    "kodi": {"Client": "Kodi", "Device": "Woonkamer", "DeviceId": "jl-smoke-kodi-0001", "Version": "1.0.0"},
}
# Zoals de Hub-adapter (in ai-server-manager) zich bij Jellyfin aanmeldt: als gewone client met een eigen gebruiker.
HUB_CLIENT = {"Client": "Hub-adapter (simulator)", "Device": "Hub", "DeviceId": "jl-smoke-hub-0001", "Version": "0.1.0"}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def fake_hub_jwt() -> str:
    """Een JWS in de vorm van een Hub-dienst-JWT (§4.3) met een nep-handtekening: Jelly Leon mag die nooit accepteren."""
    now = int(time.time())
    header = {"alg": "EdDSA", "typ": "JWT", "kid": "jl-smoke-niet-gepind"}
    claims = {
        "iss": "hub", "aud": "jelly-leon", "sub": "hub", "token_use": "hub_service", "roles": ["service"],
        "iat": now, "nbf": now, "exp": now + 60, "jti": "00000000-0000-4000-8000-000000000000",
    }
    parts = [json.dumps(part, separators=(",", ":")).encode() for part in (header, claims)]
    return ".".join([*(b64url(part) for part in parts), b64url(b"geen-echte-handtekening")])


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    item_id: str = ""
    user_id: str = ""

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

    report.secrets.append(args.password)
    completed = info.get("StartupWizardCompleted")
    if args.mode == "nieuw":
        if completed is not False:
            report.add("lege datamap", False, f"StartupWizardCompleted={completed} (verwacht False bij een lege datamap)")
            return report
        # Eerste-startwizard (zoals Jellyfin Web dat doet).
        steps = [
            ("POST", "/Startup/Configuration", {"UICulture": "nl", "MetadataCountryCode": "NL", "PreferredMetadataLanguage": "nl"}),
            ("GET", "/Startup/User", None),
            ("POST", "/Startup/User", {"Name": args.username, "Password": args.password}),
            ("POST", "/Startup/RemoteAccess", {"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False}),
            ("POST", "/Startup/Complete", None),
        ]
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
    else:
        report.add(
            "startwizard behouden na herstart",
            completed is True,
            f"StartupWizardCompleted={completed} (verwacht True: configuratie uit de bestaande datamap)",
        )
        if completed is not True:
            return report
    # Na afronding mag niemand anoniem een nieuwe beheerder aanmaken (overname na herstart/dataverlies).
    status, _, _ = client.request("GET", "/Startup/User")
    report.add("startwizard daarna niet anoniem", status in (401, 403), f"HTTP {status} (verwacht 401/403)")

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
    legacy_on = legacy_auth_expected(args)
    attempts = [("web", "Authorization"), ("android", "Authorization"), ("kodi", "X-Emby-Authorization")]
    if not legacy_on:
        attempts.append(("kodi", "Authorization"))  # een bijgewerkte derden-client met de moderne header
    for name, header_name in attempts:
        status, body = client.json(
            "POST",
            "/Users/AuthenticateByName",
            headers={header_name: auth_value(CLIENTS[name])},
            body={"Username": args.username, "Pw": args.password},
        )
        token = body.get("AccessToken") if isinstance(body, dict) else None
        if header_name == "X-Emby-Authorization" and not legacy_on:
            report.add(
                f"inloggen {CLIENTS[name]['Client']} met de oude {header_name}-header geweigerd (legacy-auth uit, BG-01)",
                status in (400, 401) and not token,
                f"HTTP {status} (verwacht 400/401)",
            )
            continue
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
    status_key, _ = client.json("GET", "/Users/Me?" + urllib.parse.urlencode({"api_key": tokens["kodi"]}))
    if legacy_on:
        report.add("oude X-Emby-Token-header en ?api_key=", status == 200 and status_key == 200,
                   f"HTTP {status} / {status_key}")
    else:
        report.add(
            "oude X-Emby-Token-header en ?api_key= geweigerd (legacy-auth uit, BG-01)",
            status == 401 and status_key == 401,
            f"HTTP {status} / {status_key} (verwacht 401/401)",
        )

    if args.mode == "nieuw":
        # Bibliotheek aanmaken en scannen.
        query = urllib.parse.urlencode(
            {"name": "Muziek", "collectionType": "music", "paths": args.library_path, "refreshLibrary": "true"}
        )
        status, _, _ = client.request(
            "POST", f"/Library/VirtualFolders?{query}", headers=web_auth, body={"LibraryOptions": {}}
        )
        report.add("bibliotheek aanmaken", status in (200, 204), f"HTTP {status}")
    else:
        status, folders = client.json("GET", "/Library/VirtualFolders", headers=web_auth)
        names = [f.get("Name") for f in folders] if isinstance(folders, list) else []
        report.add("bibliotheek behouden na herstart", status == 200 and "Muziek" in names, f"HTTP {status}; {names}")
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
    report.item_id, report.user_id = item_id, user_id
    if args.expect_item:
        report.add(
            "zelfde item-ID als vóór de herstart",
            item_id == args.expect_item,
            f"{item_id} (verwacht {args.expect_item})",
        )
    if args.expect_user:
        report.add("zelfde gebruiker als vóór de herstart", user_id == args.expect_user, f"{user_id}")

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
        hub_adapter_v1(client, report, web_auth, args)
    return report


def hub_adapter_v1(client: Client, report: Report, admin_auth: dict[str, str], args: argparse.Namespace) -> None:
    """Contract 1.2 §2.3 / JL4 (ADR-0012): de Hub-adapter v1 gebruikt alleen openbare routes en een eigen NIET-admin-
    Jellyfin-gebruiker; nooit een API-sleutel (upstream: elke sleutel is beheerder) en (nog) geen Hub-JWT."""
    report.secrets.append(args.hub_password)
    status, users = client.json("GET", "/Users", headers=admin_auth)
    user = None
    if status == 200 and isinstance(users, list):
        user = next((u for u in users if isinstance(u, dict) and u.get("Name") == args.hub_username), None)
    if user is not None:
        how = "bestond al (zelfde opslag)"
    else:
        status, created = client.json(
            "POST", "/Users/New", headers=admin_auth, body={"Name": args.hub_username, "Password": args.hub_password}
        )
        user = created if status == 200 and isinstance(created, dict) else None
        how = f"door de beheerder aangemaakt (HTTP {status})"
    policy = user.get("Policy") if isinstance(user, dict) else None
    is_admin = policy.get("IsAdministrator") if isinstance(policy, dict) else None
    report.add("Hub-adapter v1: eigen niet-admin-gebruiker", is_admin is False, f"{how}; IsAdministrator={is_admin}")
    if is_admin is not False:
        return

    status, body = client.json(
        "POST",
        "/Users/AuthenticateByName",
        headers={"Authorization": auth_value(HUB_CLIENT)},
        body={"Username": args.hub_username, "Pw": args.hub_password},
    )
    token = body.get("AccessToken") if isinstance(body, dict) else None
    report.add("Hub-adapter v1: inloggen als niet-admin", status == 200 and bool(token), f"HTTP {status}")
    if not token:
        return
    report.secrets.append(token)
    hub_auth = {"Authorization": auth_value(HUB_CLIENT, token)}

    status, body = client.json("GET", "/media/v1/version", headers=hub_auth)
    ok = status == 200 and isinstance(body, dict) and body.get("status") == "compatibel"
    detail = f"HTTP {status}" + (f"; status={body.get('status')}" if isinstance(body, dict) else "")
    report.add("Hub-adapter v1: /media/v1/version als niet-admin", ok, detail)
    status, _, _ = client.request("GET", "/Auth/Keys", headers=hub_auth)
    report.add("Hub-adapter v1: niet-admin ziet geen API-sleutels", status == 403, f"HTTP {status} (verwacht 403)")

    # Tot de B03-plugin een pinmechanisme heeft (P4), accepteert Jelly Leon geen Hub-JWT (CONTRACT_1.2 JL4).
    jwt = fake_hub_jwt()
    for label, headers in (
        ("Authorization: Bearer", {"Authorization": f"Bearer {jwt}"}),
        ("als Jellyfin-token", {"Authorization": auth_value(HUB_CLIENT, jwt)}),
    ):
        status, _, _ = client.request("GET", "/media/v1/version", headers=headers)
        report.add(f"Hub-JWT niet geaccepteerd ({label})", status == 401, f"HTTP {status} (verwacht 401)")


def legacy_auth_expected(args: argparse.Namespace) -> bool:
    """Werkt de oude aanmelding (X-Emby-*, api_key)? auto: alleen vóór 12.x (12.x zet EnableLegacyAuthorization uit)."""
    if args.legacy_auth == "aan":
        return True
    if args.legacy_auth == "uit":
        return False
    try:
        return int(args.expected_version.split(".")[0]) < 12
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stock-client-smoketest (simulator) tegen een Jelly Leon-server.")
    parser.add_argument("--url", required=True, help="bv. http://127.0.0.1:38096")
    parser.add_argument("--expected-version", required=True, help="upstream-versie die de server moet melden")
    parser.add_argument("--media-file", required=True, help="lokaal pad van het testbestand (voor bytevergelijking)")
    parser.add_argument("--library-path", required=True, help="pad van de muziekmap zoals de server hem ziet")
    parser.add_argument("--username", default="jl-smoke-admin")
    parser.add_argument("--password", default="jl-smoke-wachtwoord-niet-geheim")
    parser.add_argument("--hub-username", default="jl-smoke-hub", help="niet-admin-gebruiker van de Hub-adapter v1")
    parser.add_argument("--hub-password", default="jl-smoke-hub-wachtwoord-niet-geheim")
    parser.add_argument("--expect-plugin", action="store_true")
    parser.add_argument(
        "--modus",
        dest="mode",
        choices=("nieuw", "herstart"),
        default="nieuw",
        help="nieuw = lege datamap (wizard doorlopen); herstart = bestaande datamap (niets mag verloren zijn)",
    )
    parser.add_argument("--verwacht-item", dest="expect_item", help="item-ID uit het rapport van de vorige run")
    parser.add_argument("--verwacht-gebruiker", dest="expect_user", help="gebruikers-ID uit de vorige run")
    parser.add_argument(
        "--legacy-auth",
        choices=("auto", "aan", "uit"),
        default="auto",
        help="verwachting voor EnableLegacyAuthorization (auto: uit vanaf 12.x, BG-01)",
    )
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
        "modus": args.mode,
        "geslaagd": report.passed,
        "item_id": report.item_id,
        "gebruiker_id": report.user_id,
        "stappen": report.steps,
        "waarnemingen": report.observations,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RESULTAAT: {'GESLAAGD' if report.passed else 'MISLUKT'} ({sum(s['geslaagd'] for s in report.steps)}/{len(report.steps)})")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
