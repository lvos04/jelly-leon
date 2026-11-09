"""Tests van de web-clientcontrole in de levenscyclustest, tegen een lokale nep-webserver (simulator).

Doel: een half gelukte web-build (index.html aanwezig, maar een bundel ontbreekt of is leeg) mag nooit als
"web-client bereikbaar en volledig" door de levenscyclustest komen.
"""

from __future__ import annotations

import argparse
import functools
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "e2e"))

import image_lifecycle  # noqa: E402

INDEX = """<!doctype html><html><head><title>Jellyfin</title>
<link rel="manifest" href="manifest.json">
<link rel="stylesheet" href="main.jellyfin.css?abc">
<script defer="defer" src="runtime.bundle.js?3cf5"></script>
<script defer="defer" src="node_modules.%40jellyfin.sdk.bundle.js?3cf5"></script>
<script src="https://cdn.example.invalid/extern.js"></script>
</head><body></body></html>
"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:  # geen ruis in de testuitvoer
        pass


@pytest.fixture()
def webserver(tmp_path: Path):
    root = tmp_path / "root"
    web = root / "web"
    web.mkdir(parents=True)
    (web / "index.html").write_text(INDEX, encoding="utf-8")
    (web / "main.jellyfin.css").write_text("body{}", encoding="utf-8")
    (web / "runtime.bundle.js").write_text("console.log(1)", encoding="utf-8")
    (web / "node_modules.@jellyfin.sdk.bundle.js").write_text("export{}", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield web, server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def lifecycle_for(port: int, tmp_path: Path) -> image_lifecycle.Lifecycle:
    args = argparse.Namespace(
        image="jelly-leon:test", expected_version="10.11.11", werkmap=str(tmp_path), health_timeout=1,
        report=None, opmerking="", verwacht_web_ref="",
    )
    lifecycle = image_lifecycle.Lifecycle(args)
    lifecycle.port = port
    return lifecycle


def test_asset_parser_collects_scripts_and_stylesheets_only():
    parser = image_lifecycle.AssetParser()
    parser.feed(INDEX)
    assert parser.assets == [
        "main.jellyfin.css?abc",
        "runtime.bundle.js?3cf5",
        "node_modules.%40jellyfin.sdk.bundle.js?3cf5",
        "https://cdn.example.invalid/extern.js",
    ]


def test_complete_web_client_passes(webserver, tmp_path):
    _web, port = webserver
    lifecycle = lifecycle_for(port, tmp_path)
    assert lifecycle.check_web_client() is True
    steps = {s["stap"]: s for s in lifecycle.steps}
    assert steps["web-client bereikbaar"]["geslaagd"]
    assert steps["web-client: alle bundels uit index.html laden"]["detail"].startswith("3/3 scripts/stylesheets")


@pytest.mark.parametrize("defect", ["ontbreekt", "leeg"])
def test_missing_or_empty_bundle_fails(webserver, tmp_path, defect):
    web, port = webserver
    bundle = web / "node_modules.@jellyfin.sdk.bundle.js"
    if defect == "ontbreekt":
        bundle.unlink()
    else:
        bundle.write_bytes(b"")
    lifecycle = lifecycle_for(port, tmp_path)
    assert lifecycle.check_web_client() is False
    step = next(s for s in lifecycle.steps if s["stap"] == "web-client: alle bundels uit index.html laden")
    assert not step["geslaagd"] and "node_modules.%40jellyfin.sdk.bundle.js" in step["detail"]


def test_index_without_bundles_fails(webserver, tmp_path):
    web, port = webserver
    (web / "index.html").write_text("<html><head><title>Jellyfin</title></head></html>", encoding="utf-8")
    lifecycle = lifecycle_for(port, tmp_path)
    assert lifecycle.check_web_client() is False
