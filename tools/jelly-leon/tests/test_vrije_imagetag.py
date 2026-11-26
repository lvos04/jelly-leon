"""Alleen een bevestigde ontbrekende GHCR-tag geeft de releasestap vrij."""

import json
import os
import subprocess
from pathlib import Path

import pytest

CONTROLE = Path(__file__).resolve().parents[1] / "controleer_vrije_imagetag.sh"


@pytest.mark.parametrize(
    ("status", "antwoord", "verwacht"),
    [
        ("404", {"errors": [{"code": "MANIFEST_UNKNOWN"}]}, 0),
        ("404", {"errors": [{"code": "NAME_UNKNOWN"}]}, 0),
        ("200", {"schemaVersion": 2}, 1),
        ("403", {"errors": [{"code": "DENIED"}]}, 1),
        ("404", {"errors": []}, 1),
        ("404", {"errors": [{"code": "DENIED"}]}, 1),
        ("503", {"errors": [{"code": "MANIFEST_UNKNOWN"}]}, 1),
    ],
)
def test_alleen_ontbrekende_tag_is_vrij(tmp_path, status, antwoord, verwacht):
    curl = tmp_path / "curl"
    curl.write_text(
        """#!/usr/bin/env bash
set -eu
case "${!#}" in
    https://ghcr.io/token) echo '{"token":"proef"}' ;;
    https://ghcr.io/v2/lvos04/jelly-leon/manifests/1.0.0-jl.1)
        while [[ $1 != -o ]]; do shift; done
        echo "$ANTWOORD" > "$2"
        echo "$STATUS" ;;
    *) exit 2 ;;
esac
""",
        encoding="utf-8",
    )
    curl.chmod(0o700)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_ACTOR": "proef",
        "GH_TOKEN": "",
        "STATUS": status,
        "ANTWOORD": json.dumps(antwoord),
    }
    controle = subprocess.run(["bash", str(CONTROLE), "1.0.0-jl.1"], env=env, capture_output=True, text=True)
    assert controle.returncode == verwacht, controle.stderr
