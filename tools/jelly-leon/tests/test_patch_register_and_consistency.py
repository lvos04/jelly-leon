"""Tests voor patch_register_check.py en check_fork_consistency.py (ADR-0001/0002/0004/0005)."""

from __future__ import annotations

import json
from pathlib import Path

import check_fork_consistency
import patch_register_check
from conftest import DOCKERFILE, MANIFEST, commit_all, write


def test_register_ok_for_fork_paths_and_registered_patch(repos, capsys):
    assert patch_register_check.main(["--repo", str(repos["fork"])]) == 0
    out = capsys.readouterr().out
    assert "core-patch JL-0001: M .github/workflows/bot.yml" in out
    assert "Patchregister in orde." in out


def test_unregistered_core_patch_fails(repos, capsys):
    fork: Path = repos["fork"]
    write(fork, "src/Server.cs", "class Server { int Stiekem; }\n")
    write(fork, "src/Nieuw.cs", "class Nieuw {}\n")
    commit_all(fork, "stiekeme core-patch")
    assert patch_register_check.main(["--repo", str(fork)]) == 1
    err = capsys.readouterr().err
    assert "src/Server.cs: niet-geregistreerde core-patch (status M)" in err
    assert "src/Nieuw.cs: niet-geregistreerde core-patch (status A)" in err


def test_deleting_or_renaming_upstream_file_counts_as_patch(repos, capsys):
    fork: Path = repos["fork"]
    (fork / "src/Server.cs").rename(fork / "src/Hernoemd.cs")
    commit_all(fork, "hernoemen")
    assert patch_register_check.main(["--repo", str(fork)]) == 1
    err = capsys.readouterr().err
    assert "src/Server.cs" in err and "src/Hernoemd.cs" in err


def test_license_credits_and_identity_never_patchable(repos, capsys):
    fork: Path = repos["fork"]
    write(fork, "LICENSE", "MIT\n")
    write(fork, "CONTRIBUTORS.md", "")
    write(fork, "SharedVersion.cs", '[assembly: AssemblyVersion("9.9.9")]\n')
    commit_all(fork, "verboden")
    assert patch_register_check.main(["--repo", str(fork)]) == 1
    err = capsys.readouterr().err
    for name in ("LICENSE", "CONTRIBUTORS.md", "SharedVersion.cs"):
        assert f"{name}: mag nooit afwijken" in err


def test_stale_register_entry_fails(repos, capsys):
    fork: Path = repos["fork"]
    text = (fork / "docs/platform-v2/PATCHES.md").read_text(encoding="utf-8")
    write(fork, "docs/platform-v2/PATCHES.md", text.replace("`.github/workflows/bot.yml`", "`.github/workflows/bot.yml`, `src/Server.cs`"))
    commit_all(fork, "register met niet-bestaande patch")
    assert patch_register_check.main(["--repo", str(fork)]) == 1
    assert "src/Server.cs wijkt niet (meer) af" in capsys.readouterr().err


def test_register_requires_all_fields(repos, capsys):
    fork: Path = repos["fork"]
    text = (fork / "docs/platform-v2/PATCHES.md").read_text(encoding="utf-8")
    write(fork, "docs/platform-v2/PATCHES.md", text.replace("| Upstream-PR-kans | laag |\n", ""))
    commit_all(fork, "onvolledig register")
    assert patch_register_check.main(["--repo", str(fork)]) == 1
    assert "verplicht veld 'Upstream-PR-kans'" in capsys.readouterr().err


def test_vervallen_patch_is_not_counted(repos, capsys):
    fork: Path = repos["fork"]
    text = (fork / "docs/platform-v2/PATCHES.md").read_text(encoding="utf-8")
    write(fork, "docs/platform-v2/PATCHES.md", text.replace("| Status | actief |", "| Status | vervallen |"))
    commit_all(fork, "patch vervallen maar bestand nog gewijzigd")
    assert patch_register_check.main(["--repo", str(fork)]) == 1
    assert ".github/workflows/bot.yml: niet-geregistreerde core-patch" in capsys.readouterr().err


def test_missing_base_commit_is_usage_error(repos, capsys):
    assert patch_register_check.main(["--repo", str(repos["fork"]), "--base", "0" * 40]) == 3
    assert "volledige historie" in capsys.readouterr().err


def test_consistency_ok(repos, capsys):
    assert check_fork_consistency.main(["--repo", str(repos["fork"])]) == 0
    assert "Forkconsistentie in orde" in capsys.readouterr().out


def test_consistency_detects_plugin_version_drift(repos, capsys):
    fork: Path = repos["fork"]
    write(fork, "plugins/Directory.Build.props", "<Project><PropertyGroup><JellyfinVersion>1.1.0</JellyfinVersion></PropertyGroup></Project>")
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    assert "JellyfinVersion 1.1.0" in capsys.readouterr().err


def test_consistency_detects_bad_fork_version_and_identity_change(repos, capsys):
    fork: Path = repos["fork"]
    baseline_path = fork / "tools/jelly-leon/baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["fork_version"] = "1.0.0+jl1"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    write(fork, "SharedVersion.cs", '[assembly: AssemblyVersion("1.0.0-jelly")]\n')
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    err = capsys.readouterr().err
    assert "fork_version '1.0.0+jl1' volgt niet het schema" in err
    assert "SharedVersion.cs: ongeldige versie: '1.0.0-jelly'" in err


def test_consistency_detects_identity_version_change(repos, capsys):
    fork: Path = repos["fork"]
    write(fork, "SharedVersion.cs", '[assembly: AssemblyVersion("1.0.0.1")]\n')
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    assert "vierde versiedeel" in capsys.readouterr().err
    write(fork, "SharedVersion.cs", '[assembly: AssemblyVersion("1.0.1")]\n')
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    assert "SharedVersion.cs meldt 1.0.1 maar de basis is 1.0.0" in capsys.readouterr().err


def test_consistency_rejects_latest_compose_and_unpinned_images(repos, capsys):
    fork: Path = repos["fork"]
    write(
        fork,
        "deploy/manifest/jelly-leon.manifest.yaml",
        MANIFEST.format(fork="1.0.0-jl.0").replace('tag: "1.0.0-jl.0"', "tag: latest") + "compose: |\n  services: {}\n",
    )
    write(fork, "deploy/allinone/Dockerfile", "FROM debian:bookworm\nFROM node:latest AS web\n")
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    err = capsys.readouterr().err
    assert "image.tag" in err and "latest" in err and "compose" in err
    assert "FROM debian:bookworm zonder @sha256-digest" in err
    assert "node:latest" in err


def test_consistency_accepts_stage_reference_and_arg_digest(repos):
    fork: Path = repos["fork"]
    write(fork, "deploy/allinone/Dockerfile", DOCKERFILE.format(digest="b" * 64))
    assert check_fork_consistency.check_dockerfiles(fork) == []


def test_consistency_detects_unmerged_baseline(repos, capsys):
    fork: Path = repos["fork"]
    baseline_path = fork / "tools/jelly-leon/baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["upstream_commit"] = repos["v11"]  # bestaat niet in de fork-historie
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    assert "bestaat niet in deze repository" in capsys.readouterr().err
