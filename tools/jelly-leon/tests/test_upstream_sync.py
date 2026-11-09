"""Tests voor upstream_sync.py — simulatie van EX48 (incompatibele upstream-update faalt, geen deploy)."""

from __future__ import annotations

import json
from pathlib import Path

import check_fork_consistency
import patch_register_check
import upstream_sync
from conftest import git
from jl_common import Version, parse_stable_tag

LS_REMOTE = """\
aaaa000000000000000000000000000000000001\trefs/tags/v10.11.10
aaaa000000000000000000000000000000000002\trefs/tags/v10.11.11
bbbb000000000000000000000000000000000002\trefs/tags/v10.11.11^{}
aaaa000000000000000000000000000000000003\trefs/tags/v12.0-rc7
aaaa000000000000000000000000000000000004\trefs/tags/v12.0
aaaa000000000000000000000000000000000005\trefs/tags/v12.4
aaaa000000000000000000000000000000000006\trefs/tags/v12.10
aaaa000000000000000000000000000000000007\trefs/tags/v12.11-rc1
aaaa000000000000000000000000000000000008\trefs/tags/10.11.12
"""


def test_parse_stable_tag_accepts_two_and_three_part_versions():
    assert parse_stable_tag("v10.11.11") == Version(10, 11, 11)
    assert parse_stable_tag("v12.4") == Version(12, 4, 0)
    assert parse_stable_tag("v12.0-rc7") is None
    assert parse_stable_tag("10.11.12") is None  # zonder v is geen upstream-releasetag


def test_ls_remote_prefers_peeled_commit():
    tags = upstream_sync.parse_ls_remote(LS_REMOTE)
    assert tags["v10.11.11"] == "bbbb000000000000000000000000000000000002"


def test_choose_tracks_numeric_order_and_skips_rc():
    tags = upstream_sync.parse_ls_remote(LS_REMOTE)
    current = Version(10, 11, 11)
    assert upstream_sync.choose(tags, current, "patch") == (None, [])
    candidate, newer = upstream_sync.choose(tags, current, "nieuwste")
    assert candidate == "v12.10"  # numeriek, niet alfabetisch (12.10 > 12.4)
    assert newer == ["v12.0", "v12.4", "v12.10"]
    candidate, _ = upstream_sync.choose(tags, Version(10, 11, 10), "patch")
    assert candidate == "v10.11.11"


def test_choose_cli_writes_github_output(repos, tmp_path, monkeypatch, capsys):
    fork: Path = repos["fork"]
    tags_file = tmp_path / "tags.txt"
    tags_file.write_text(git(fork, "ls-remote", "--tags", str(repos["upstream"])), encoding="utf-8")
    out_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    rc = upstream_sync.main(["--repo", str(fork), "kies", "--tags-bestand", str(tags_file)])
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["patch"]["kandidaat"] == "v1.0.1"
    assert result["nieuwste"]["kandidaat"] == "v1.1"  # v1.2-rc1 telt niet
    assert 'kandidaten=["v1.0.1", "v1.1"]' in out_file.read_text(encoding="utf-8")


def test_merge_compatible_tag_updates_baseline_and_stays_consistent(repos, capsys):
    fork: Path = repos["fork"]
    rc = upstream_sync.main(
        ["--repo", str(fork), "merge", "--tag", "v1.0.1", "--bron", str(repos["upstream"]), "--maak-lokale-tag"]
    )
    assert rc == 0, capsys.readouterr().err
    assert git(fork, "rev-parse", "--abbrev-ref", "HEAD") == "sync/v1.0.1"
    baseline = json.loads((fork / "tools/jelly-leon/baseline.json").read_text(encoding="utf-8"))
    assert baseline["upstream_commit"] == repos["v101"]
    assert baseline["fork_version"] == "1.0.1-jl.0"
    assert "<JellyfinVersion>1.0.1</JellyfinVersion>" in (fork / "plugins/Directory.Build.props").read_text()
    # Manifest volgt de forkversie pas bij een release; de consistentiecheck moet dit dus melden.
    errors = check_fork_consistency.check_baseline(fork, baseline)
    assert errors == []
    manifest_errors = check_fork_consistency.check_manifest(fork, baseline)
    assert any("manifest" in e for e in manifest_errors)
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    assert check_fork_consistency.main(["--repo", str(fork), "--zonder-manifest"]) == 0
    # De geregistreerde core-patch blijft geldig tegen de nieuwe basis.
    errors, _ = patch_register_check.check(fork, None, "HEAD")
    assert errors == []
    assert git(fork, "rev-parse", "upstream-v1.0.1^{commit}") == repos["v101"]


def test_merge_incompatible_tag_fails_cleanly_ex48(repos, capsys):
    fork: Path = repos["fork"]
    head_before = git(fork, "rev-parse", "HEAD")
    rc = upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v1.1", "--bron", str(repos["upstream"])])
    err = capsys.readouterr().err
    assert rc == 2
    assert "INCOMPATIBEL" in err and ".github/workflows/bot.yml" in err
    # Niets half achtergelaten: terug op main, zelfde commit, geen sync-branch, schone boom.
    assert git(fork, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(fork, "rev-parse", "HEAD") == head_before
    assert git(fork, "branch", "--list", "sync/v1.1") == ""
    assert git(fork, "status", "--porcelain") == ""


def test_merge_refuses_rc_and_downgrade(repos, capsys):
    fork: Path = repos["fork"]
    assert upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v1.2-rc1", "--geen-fetch"]) == 1
    assert "geen stabiele" in capsys.readouterr().err
    assert upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v1.0.0", "--geen-fetch"]) == 1
    assert "geen downgrade" in capsys.readouterr().err


def test_merge_refuses_dirty_tree_and_existing_branch(repos, capsys):
    fork: Path = repos["fork"]
    (fork / "src/Server.cs").write_text("vies\n", encoding="utf-8")
    assert upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v1.0.1", "--bron", str(repos["upstream"])]) == 1
    assert "niet schoon" in capsys.readouterr().err
    git(fork, "checkout", "--", "src/Server.cs")
    git(fork, "branch", "sync/v1.0.1")
    assert upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v1.0.1", "--bron", str(repos["upstream"])]) == 4
