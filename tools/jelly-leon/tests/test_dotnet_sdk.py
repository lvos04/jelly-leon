"""SDK-kanaal voor CI uit de upstream-global.json en de SDK-consistentiecontrole.

Aanleiding (2026-11-09): `actions/setup-dotnet` met `global-json-file` faalde op GitHub met "Could not find .NET Core
SDK with version = 9.0.0" — upstream zet 9.0.0 als ondergrens met rollForward, die versie bestaat niet als download.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import check_fork_consistency
import dotnet_sdk_kanaal
from conftest import DOCKERFILE, write
from jl_common import DEFAULT_REPO_ROOT, ToolError, read_global_json_sdk, sdk_channel, sdk_major_minor

GLOBAL_JSON = '{{\n    "sdk": {{\n        "version": "{sdk}",\n        "rollForward": "latestMinor"\n    }}\n}}\n'


@pytest.mark.parametrize(
    ("version", "channel"),
    [("9.0.0", "9.0.x"), ("9.0.320", "9.0.x"), ("10.0.0", "10.0.x"), ("10.0.100", "10.0.x"), ("12.1.5", "12.1.x")],
)
def test_sdk_channel(version, channel):
    assert sdk_channel(version) == channel
    assert sdk_major_minor(version) == channel[:-2]


@pytest.mark.parametrize("bad", ["9.0", "9", "9.0.x", "latest", "", "v9.0.0"])
def test_sdk_channel_rejects_non_versions(bad):
    with pytest.raises(ToolError):
        sdk_channel(bad)


def test_cli_prints_channel_and_writes_github_output(tmp_path, monkeypatch, capsys):
    write(tmp_path, "global.json", GLOBAL_JSON.format(sdk="9.0.0"))
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert dotnet_sdk_kanaal.main(["--repo", str(tmp_path), "--github-output"]) == 0
    out, err = capsys.readouterr()
    assert out.strip() == "9.0.x"
    assert "global.json vraagt SDK 9.0.0" in err
    assert output.read_text(encoding="utf-8") == "kanaal=9.0.x\nmajor_minor=9.0\n"


def test_cli_without_github_output_env_is_error(tmp_path, monkeypatch, capsys):
    write(tmp_path, "global.json", GLOBAL_JSON.format(sdk="9.0.0"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert dotnet_sdk_kanaal.main(["--repo", str(tmp_path), "--github-output"]) == 3
    assert "GITHUB_OUTPUT is niet gezet" in capsys.readouterr().err


def test_cli_missing_global_json(tmp_path, capsys):
    assert dotnet_sdk_kanaal.main(["--repo", str(tmp_path)]) == 3
    assert "global.json ontbreekt" in capsys.readouterr().err


@pytest.mark.parametrize(
    "content",
    ["{", '{"sdk": {}}', '{"sdk": {"version": "9.0"}}', '{"sdk": "9.0.0"}', '{"sdk": {"version": 9}}'],
)
def test_cli_invalid_global_json(tmp_path, capsys, content):
    write(tmp_path, "global.json", content)
    assert dotnet_sdk_kanaal.main(["--repo", str(tmp_path)]) == 3
    assert "FOUT: global.json" in capsys.readouterr().err


def test_global_json_with_bom_is_read(tmp_path):
    (tmp_path / "global.json").write_text(GLOBAL_JSON.format(sdk="9.0.0"), encoding="utf-8-sig")
    assert read_global_json_sdk(tmp_path) == "9.0.0"


def test_real_repo_channel_matches_baseline_and_deploy():
    """Integratie op de echte repo: global.json (upstream) → kanaal 9.0.x, baseline en Dockerfile in dezelfde reeks."""
    version = read_global_json_sdk(DEFAULT_REPO_ROOT)
    assert version is not None
    baseline = json.loads((DEFAULT_REPO_ROOT / "tools/jelly-leon/baseline.json").read_text(encoding="utf-8"))
    assert baseline["dotnet_sdk_major"] == sdk_major_minor(version)
    assert check_fork_consistency.check_sdk(DEFAULT_REPO_ROOT, baseline, include_deploy=True) == []


def _set_baseline(fork: Path, **values) -> None:
    path = fork / "tools/jelly-leon/baseline.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(values)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_consistency_without_global_json_skips_sdk_check(repos):
    assert check_fork_consistency.check_sdk(repos["fork"], {"dotnet_sdk_major": "8.0"}, include_deploy=True) == []


def test_consistency_detects_baseline_sdk_drift(repos, capsys):
    fork = repos["fork"]
    write(fork, "global.json", GLOBAL_JSON.format(sdk="9.0.0"))
    _set_baseline(fork, dotnet_sdk_major="8.0")
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    assert "baseline.dotnet_sdk_major 8.0 ≠ SDK-reeks 9.0" in capsys.readouterr().err
    _set_baseline(fork, dotnet_sdk_major="9.0")
    assert check_fork_consistency.main(["--repo", str(fork)]) == 0


def test_consistency_detects_deploy_sdk_drift_and_sync_mode_skips_it(repos, capsys):
    fork = repos["fork"]
    write(fork, "global.json", GLOBAL_JSON.format(sdk="10.0.0"))
    _set_baseline(fork, dotnet_sdk_major="10.0")
    write(fork, "deploy/allinone/Dockerfile", DOCKERFILE.format(digest="d" * 64))  # sdk:9.0
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    assert "deploy/allinone/Dockerfile:2: .NET-SDK-image 9.0 past niet bij global.json (10.0.0" in capsys.readouterr().err
    assert check_fork_consistency.main(["--repo", str(fork), "--zonder-manifest"]) == 0
    write(fork, "deploy/allinone/Dockerfile", DOCKERFILE.format(digest="d" * 64).replace("sdk:9.0@", "sdk:10.0.100@"))
    assert check_fork_consistency.main(["--repo", str(fork)]) == 0
