"""Tests van de stock-client-smoketest zelf, tegen een nep-Jellyfin (simulator).

Doel: de smoketest mag nooit "geslaagd" melden als de server zich anders gedraagt dan stock Jellyfin
(technische identiteit gewijzigd, anonieme toegang, wizard open na afronden, dataverlies na herstart).
"""

from __future__ import annotations

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
MEDIA = bytes(range(256)) * 8
TOKEN_RE = re.compile(r'Token="([^"]+)"')


class FakeJellyfin:
    """Minimale nabootsing van de upstream-routes die de smoketest gebruikt. `defects` zet fouten aan."""

    def __init__(self, defects: set[str] | None = None, *, completed: bool = False, item_id: str = "item-1") -> None:
        self.defects = defects or set()
        self.completed = completed
        self.user_id = "gebruiker-1"
        self.item_id = item_id
        self.library = completed
        self.tokens: dict[str, str] = {}
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
                    if body.get("Pw") != PASSWORD or not header.startswith("MediaBrowser"):
                        return self._send(401)
                    device = re.search(r'DeviceId="([^"]+)"', header).group(1)
                    token = f"tok-{len(fake.tokens) + 1}"
                    fake.tokens[token] = device
                    return self._send(200, {"AccessToken": token, "User": {"Id": fake.user_id}})
                if path == "/Users/Me":
                    if authed or "open_users_me" in fake.defects:
                        return self._send(200, {"Id": fake.user_id})
                    return self._send(401)
                if path == "/media/v1/version":
                    if authed or "open_plugin" in fake.defects:
                        return self._send(200, {"status": "compatibel", "fork_version": "10.11.11-jl.0", "reason_code": "ok"})
                    return self._send(401)
                if not authed and not path.startswith("/Audio/"):
                    return self._send(401)
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
    assert any(o["waarneming"].startswith("upstream-gedrag") for o in result["waarnemingen"])


@pytest.mark.parametrize(
    ("defect", "expected_failure"),
    [
        ("renamed", "technische identiteit"),
        ("open_users_me", "zonder token geweigerd"),
        ("open_plugin", "plugin-route zonder token geweigerd"),
        ("wizard_open", "startwizard daarna niet anoniem"),
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
