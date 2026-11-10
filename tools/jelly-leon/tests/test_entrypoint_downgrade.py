"""Downgradeweigering in deploy/allinone/entrypoint.sh (B03-014, JLT-61 b): versievergelijking in POSIX-sh.

De functies `version_fields` en `version_newer` worden letterlijk uit het entrypoint gelezen en met `sh` (dash, net als
in de image) uitgevoerd. De weigering zelf (container stopt, /config byte-gelijk) meet
tools/jelly-leon/e2e/image_lifecycle.py met de echte image.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "deploy" / "allinone" / "entrypoint.sh"


def functions() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    parts = []
    for name in ("version_fields", "version_newer"):
        match = re.search(rf"^{name}\(\) {{\n.*?^}}\n", text, re.MULTILINE | re.DOTALL)
        assert match, f"functie {name} niet gevonden in het entrypoint"
        parts.append(match.group(0))
    return "".join(parts)


def newer(a: str, b: str) -> bool:
    script = functions() + 'if version_newer "$(version_fields "$1")" "$(version_fields "$2")"; then exit 0; else exit 1; fi\n'
    return subprocess.run(["sh", "-c", script, "sh", a, b], check=False).returncode == 0


def fields(value: str) -> str:
    script = functions() + 'version_fields "$1"\n'
    return subprocess.run(["sh", "-c", script, "sh", value], capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("12.5.0-jl.0", "12.4.0-jl.0", True),
        ("12.4.0-jl.1", "12.4.0-jl.0", True),
        ("12.10.0-jl.0", "12.9.3-jl.4", True),  # numeriek, niet alfabetisch
        ("13.0.0-jl.0", "12.99.99-jl.99", True),
        ("12.4.0-jl.0", "12.4.0-jl.0", False),  # zelfde versie: gewoon starten
        ("10.11.11-jl.0", "12.4.0-jl.0", False),  # upgrade: datamap ouder dan de image
        ("12.4.0-jl.0", "12.4.0-jl.1", False),
    ],
)
def test_version_newer(a: str, b: str, expected: bool) -> None:
    assert newer(a, b) is expected


@pytest.mark.parametrize("value", ["12.4-jl.0", "12.4.0", "12.4.0-jl.0x", "v12.4.0-jl.0", "", "12.4.0-jl."])
def test_unknown_form_gives_no_fields(value: str) -> None:
    assert fields(value) == ""


def test_known_form() -> None:
    assert fields("12.4.0-jl.3") == "12 4 0 3"


def test_guard_runs_before_any_write_and_version_is_recorded_only_as_app_user() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    guard = text.index("\nassert_not_downgrade\n")
    # vóór elke eigenaarswissel en vóór de pluginmap; vastleggen pas in de tweede fase (als 568, vlak vóór de start)
    assert guard < text.index('chown -R "$APP_UID:$APP_GID" "$dir"')
    stage_two = text.index('if [ "${JELLY_LEON_ENTRYPOINT_STAGE:-}" = "app" ]')
    record = text.index("    record_datamap_version\n")
    assert stage_two < record < text.index("    install_plugins\n    exec /jellyfin/jellyfin")
