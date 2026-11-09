"""Testopzet: pakket importeerbaar maken, nep-servers en sleutelbestanden (0600) per test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nep_servers import NepEmby, NepJellyfin  # noqa: E402


@pytest.fixture
def emby():
    server = NepEmby()
    yield server
    server.stop()


@pytest.fixture
def jl():
    server = NepJellyfin()
    yield server
    server.stop()


@pytest.fixture
def sleutels(tmp_path: Path) -> dict[str, Path]:
    geheimen = tmp_path / "secrets"
    geheimen.mkdir(mode=0o700)
    uit = {}
    for naam, waarde in (("emby", NepEmby.SLEUTEL), ("jl", NepJellyfin.SLEUTEL)):
        pad = geheimen / f"{naam}-api-key"
        pad.write_text(waarde + "\n", encoding="utf-8")
        os.chmod(pad, 0o600)
        uit[naam] = pad
    return uit
