"""Tests van de stock-client-smoketest zelf, tegen een nep-Jellyfin (simulator).

Doel: de smoketest mag nooit "geslaagd" melden als de server zich anders gedraagt dan stock Jellyfin
(technische identiteit gewijzigd, anonieme toegang, wizard open na afronden, dataverlies na herstart).
"""

from __future__ import annotations

import base64
import json
import re
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "e2e"))

import stock_client_smoke  # noqa: E402

PASSWORD = "wachtwoord-voor-de-test"
HUB_USER = "jl-smoke-hub"
HUB_PASSWORD = "jl-smoke-hub-wachtwoord-niet-geheim"
MEDIA = bytes(range(256)) * 8
TOKEN_RE = re.compile(r'Token="([^"]+)"')


class FakeJellyfin:
    """Minimale nabootsing van de upstream-routes die de smoketest gebruikt. `defects` zet fouten aan."""

    def __init__(
        self,
        defects: set[str] | None = None,
        *,
        completed: bool = False,
        item_id: str = "item-1",
        hub_user: bool = False,
    ) -> None:
        self.defects = defects or set()
        self.completed = completed
        self.user_id = "gebruiker-1"
        self.item_id = item_id
        self.library = completed
        self.tokens: dict[str, str] = {}
        self.admin_tokens: set[str] = set()
        self.hub_user = hub_user  # niet-admin-gebruiker van de Hub-adapter v1 bestaat al
        self.hub_logins = 0
        self.hub_password = HUB_PASSWORD
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self) -> FakeJellyfin:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:  # stil in de testuitvoer
                return

            def _send(self, status: int, body: object = None, *, raw: bytes | None = None, headers=None) -> None:
                data = raw if raw is not None else (b"" if body is None else json.dumps(body).encode())
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _token(self) -> str | None:
                header = self.headers.get("Authorization") or self.headers.get("X-Emby-Authorization") or ""
                match = TOKEN_RE.search(header)
                token = match.group(1) if match else self.headers.get("X-Emby-Token")
                return token if token in fake.tokens else None

            def _body(self) -> dict:
                length = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(length) or b"{}") if length else {}

            def do_GET(self) -> None:  # noqa: N802 (http.server-API)
                self._route("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._route("POST")

            def _route(self, method: str) -> None:
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                authed = self._token() is not None
                if path == "/health":
                    return self._send(200, raw=b"Healthy")
                if path == "/System/Info/Public":
                    product = "Jelly Leon Server" if "renamed" in fake.defects else "Jellyfin Server"
                    return self._send(
                        200, {"ProductName": product, "Version": "10.11.11", "StartupWizardCompleted": fake.completed}
                    )
                if path.startswith("/Startup/"):
                    if fake.completed and "wizard_open" not in fake.defects and not authed:
                        return self._send(401)
                    if path == "/Startup/Complete":
                        fake.completed = True
                    return self._send(204)
                if path == "/Users/AuthenticateByName":
                    body = self._body()
                    header = self.headers.get("Authorization") or self.headers.get("X-Emby-Authorization") or ""
                    hub = body.get("Username") == HUB_USER
                    if hub:
                        valid = fake.hub_user and body.get("Pw") == fake.hub_password
                    else:
                        valid = body.get("Pw") == PASSWORD
                    if not valid or not header.startswith("MediaBrowser"):
                        return self._send(401)
                    device = re.search(r'DeviceId="([^"]+)"', header).group(1)
                    token = f"tok-{len(fake.tokens) + 1}"
                    fake.tokens[token] = device
                    if hub:
                        fake.hub_logins += 1
                    else:
                        fake.admin_tokens.add(token)
                    return self._send(200, {"AccessToken": token, "User": {"Id": "hub-1" if hub else fake.user_id}})
                if path == "/Users/Me":
                    if authed or "open_users_me" in fake.defects:
                        return self._send(200, {"Id": fake.user_id})
                    return self._send(401)
                if path == "/media/v1/version":
                    bearer = (self.headers.get("Authorization") or "").startswith("Bearer ")
                    if authed or "open_plugin" in fake.defects or (bearer and "accepts_jwt" in fake.defects):
                        return self._send(200, {"status": "compatibel", "fork_version": "10.11.11-jl.0", "reason_code": "ok"})
                    return self._send(401)
                if not authed and not path.startswith("/Audio/"):
                    return self._send(401)
                admin = self._token() in fake.admin_tokens
                hub_policy = {"IsAdministrator": "hub_admin" in fake.defects}
                if path == "/Users" and method == "GET":
                    users = [{"Name": "jl-smoke-admin", "Id": fake.user_id, "Policy": {"IsAdministrator": True}}]
                    if fake.hub_user:
                        users.append({"Name": HUB_USER, "Id": "hub-1", "Policy": hub_policy})
                    return self._send(200, users)
                if path == "/Users/New":
                    if not admin:
                        return self._send(403)
                    if "create_fails" in fake.defects:
                        return self._send(400)
                    body = self._body()
                    fake.hub_user = body.get("Name") == HUB_USER
                    fake.hub_password = body.get("Password")
                    return self._send(200, {"Name": body.get("Name"), "Id": "hub-1", "Policy": hub_policy})
                if path == "/Auth/Keys":
                    if admin or "keys_open" in fake.defects:
                        return self._send(200, {"Items": [], "TotalRecordCount": 0})
                    return self._send(403)
                if path == "/Library/VirtualFolders":
                    if method == "POST":
                        fake.library = True
                        return self._send(204)
                    return self._send(200, [{"Name": "Muziek"}] if fake.library else [])
                if path == "/Library/Refresh":
                    return self._send(204)
                if path == "/Items":
                    return self._send(200, {"Items": [{"Id": fake.item_id}] if fake.library else []})
                if path == f"/Audio/{fake.item_id}/stream":
                    match = re.match(r"bytes=(\d+)-(\d+)", self.headers.get("Range") or "")
                    if match:
                        start, end = int(match.group(1)), int(match.group(2))
                        return self._send(206, raw=MEDIA[start : end + 1])
                    return self._send(200, raw=MEDIA)
                if path == "/Sessions":
                    return self._send(200, [{"DeviceId": d} for d in sorted(set(fake.tokens.values()))])
                return self._send(404)

        return Handler


def run_smoke(tmp_path: Path, fake: FakeJellyfin, *extra: str) -> tuple[int, dict]:
    media = tmp_path / "media.wav"
    media.write_bytes(MEDIA)
    report = tmp_path / "rapport.json"
    rc = stock_client_smoke.main(
        [
            "--url", fake.url, "--expected-version", "10.11.11", "--media-file", str(media),
            "--library-path", "/media/muziek", "--expect-plugin", "--password", PASSWORD,
            "--start-timeout", "5", "--scan-timeout", "5", "--report", str(report), *extra,
        ]
    )
    return rc, json.loads(report.read_text(encoding="utf-8"))


def failed_steps(result: dict) -> list[str]:
    return [step["stap"] for step in result["stappen"] if not step["geslaagd"]]


def test_stock_behaviour_passes_and_reports_ids(tmp_path):
    with FakeJellyfin() as fake:
        rc, result = run_smoke(tmp_path, fake)
    assert rc == 0, failed_steps(result)
    assert result["geslaagd"] is True
    assert result["item_id"] == "item-1" and result["gebruiker_id"] == "gebruiker-1"
    assert PASSWORD not in json.dumps(result) and "tok-1" not in json.dumps(result)  # geredigeerd
    assert HUB_PASSWORD not in json.dumps(result)
    assert any(o["waarneming"].startswith("upstream-gedrag") for o in result["waarnemingen"])


@pytest.mark.parametrize(
    ("defect", "expected_failure"),
    [
        ("renamed", "technische identiteit"),
        ("open_users_me", "zonder token geweigerd"),
        ("open_plugin", "plugin-route zonder token geweigerd"),
        ("wizard_open", "startwizard daarna niet anoniem"),
        ("hub_admin", "Hub-adapter v1: eigen niet-admin-gebruiker"),
        ("keys_open", "Hub-adapter v1: niet-admin ziet geen API-sleutels"),
        ("accepts_jwt", "Hub-JWT niet geaccepteerd (Authorization: Bearer)"),
    ],
)
def test_deviation_from_stock_never_passes(tmp_path, defect, expected_failure):
    with FakeJellyfin({defect}) as fake:
        rc, result = run_smoke(tmp_path, fake)
    assert rc == 1
    assert result["geslaagd"] is False
    assert expected_failure in failed_steps(result)


def test_new_mode_refuses_already_configured_server(tmp_path):
    """Modus `nieuw` verwacht een lege datamap; een al ingerichte server is geen eerste start."""
    with FakeJellyfin(completed=True) as fake:
        rc, result = run_smoke(tmp_path, fake)
    assert rc == 1 and "lege datamap" in failed_steps(result)


def test_restart_mode_passes_with_same_data(tmp_path):
    with FakeJellyfin(completed=True) as fake:
        rc, result = run_smoke(
            tmp_path, fake, "--modus", "herstart", "--verwacht-item", "item-1", "--verwacht-gebruiker", "gebruiker-1"
        )
    assert rc == 0, failed_steps(result)
    assert result["modus"] == "herstart"


def test_restart_mode_detects_data_loss(tmp_path):
    """Na herstart weer een lege server (wizard open) = dataverlies → mislukt."""
    with FakeJellyfin(completed=False) as fake:
        rc, result = run_smoke(tmp_path, fake, "--modus", "herstart", "--verwacht-item", "item-1")
    assert rc == 1 and "startwizard behouden na herstart" in failed_steps(result)


def test_restart_mode_detects_new_item_id(tmp_path):
    """Andere item-ID na herstart = bibliotheek opnieuw opgebouwd (kijkgeschiedenis weg) → mislukt."""
    with FakeJellyfin(completed=True, item_id="item-2") as fake:
        rc, result = run_smoke(tmp_path, fake, "--modus", "herstart", "--verwacht-item", "item-1")
    assert rc == 1 and "zelfde item-ID als vóór de herstart" in failed_steps(result)


def test_hub_adapter_v1_uses_own_non_admin_user(tmp_path):
    """JL4: de Hub-adapter v1 leest /media/v1/version met een eigen niet-admin-gebruiker (aangemaakt door de beheerder)."""
    with FakeJellyfin() as fake:
        rc, result = run_smoke(tmp_path, fake)
        assert fake.hub_user and fake.hub_logins == 1
    assert rc == 0, failed_steps(result)
    steps = {step["stap"]: step for step in result["stappen"]}
    assert "aangemaakt" in steps["Hub-adapter v1: eigen niet-admin-gebruiker"]["detail"]
    assert steps["Hub-adapter v1: /media/v1/version als niet-admin"]["geslaagd"]
    assert steps["Hub-JWT niet geaccepteerd (als Jellyfin-token)"]["geslaagd"]


def test_hub_adapter_v1_reuses_existing_user_after_restart(tmp_path):
    with FakeJellyfin(completed=True, hub_user=True) as fake:
        rc, result = run_smoke(tmp_path, fake, "--modus", "herstart", "--verwacht-item", "item-1")
    assert rc == 0, failed_steps(result)
    step = next(s for s in result["stappen"] if s["stap"] == "Hub-adapter v1: eigen niet-admin-gebruiker")
    assert "bestond al" in step["detail"]


def test_hub_adapter_v1_stops_when_user_cannot_be_created(tmp_path):
    """Kan de niet-admin-gebruiker niet worden aangemaakt, dan nooit 'geslaagd' (en geen verdere Hub-stappen)."""
    with FakeJellyfin({"create_fails"}) as fake:
        rc, result = run_smoke(tmp_path, fake)
        assert fake.hub_logins == 0
    assert rc == 1
    assert "Hub-adapter v1: eigen niet-admin-gebruiker" in failed_steps(result)
    assert not any(step["stap"].startswith("Hub-JWT") for step in result["stappen"])


def test_hub_adapter_v1_login_failure_never_passes(tmp_path):
    """Bestaande gebruiker met een ander wachtwoord: inloggen mislukt → mislukt, geen gesimuleerd succes."""
    with FakeJellyfin(hub_user=True) as fake:
        rc, result = run_smoke(tmp_path, fake, "--hub-password", "ander-wachtwoord-niet-geheim")
    assert rc == 1
    assert failed_steps(result) == ["Hub-adapter v1: inloggen als niet-admin"]


def test_fake_hub_jwt_has_hub_service_shape():
    header, claims, _ = stock_client_smoke.fake_hub_jwt().split(".")
    decode = lambda part: json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))  # noqa: E731
    assert decode(header)["alg"] == "EdDSA"
    payload = decode(claims)
    assert payload["token_use"] == "hub_service" and payload["aud"] == "jelly-leon" and payload["jti"]
    assert payload["exp"] - payload["iat"] <= 120
