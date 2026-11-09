"""Bron van de web-client in de image (CI-job image): vaste commit van jelly-leon-web die bij de server-basis past."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import web_bron
from conftest import commit_all, git, init_repo, write

REPO = Path(__file__).resolve().parents[3]


def package(version: str, name: str = "jellyfin-web") -> str:
    return json.dumps({"name": name, "version": version, "license": "GPL-2.0-or-later"}, indent=2) + "\n"


@pytest.fixture()
def web(tmp_path: Path) -> dict:
    """Nep-jellyfin-web: upstream-commit (tag v1.0.0) en daarop een fork-commit."""
    repo = init_repo(tmp_path / "web")
    write(repo, "package.json", package("1.0.0"))
    upstream = commit_all(repo, "upstream 1.0.0")
    git(repo, "tag", "v1.0.0", upstream)
    write(repo, "README.jelly-leon.md", "# Jelly Leon Web\n")
    fork = commit_all(repo, "fork")
    baseline = {
        "upstream_tag": "v1.0.0", "upstream_version": "1.0.0", "upstream_commit": "a" * 40, "fork_version": "1.0.0-jl.0",
        "web_repo": "https://github.com/lvos04/jelly-leon-web", "web_upstream_tag": "v1.0.0",
        "web_upstream_commit": upstream, "web_fork_commit": fork,
    }
    return {"repo": repo, "baseline": baseline, "upstream": upstream, "fork": fork}


def test_matching_checkout_passes(web):
    assert web_bron.check_checkout(web["repo"], web["baseline"]) == []


def test_real_baseline_pins_a_full_web_commit_of_the_same_release():
    baseline = json.loads((REPO / "tools/jelly-leon/baseline.json").read_text(encoding="utf-8"))
    errors, fields = web_bron.web_fields(baseline)
    assert errors == []
    assert fields["web_repo"] == "https://github.com/lvos04/jelly-leon-web"


def test_checkout_on_other_commit_fails(web):
    git(web["repo"], "checkout", "-q", web["upstream"])
    errors = web_bron.check_checkout(web["repo"], web["baseline"])
    assert any("checkout staat op" in e for e in errors)


def test_web_of_another_release_fails(web):
    """Na een upstream-sync van de server (bv. naar 12.x) moet ook de web-fork mee: anders faalt de job image."""
    baseline = {**web["baseline"], "upstream_version": "1.1.0", "upstream_tag": "v1.1"}
    errors = web_bron.check_checkout(web["repo"], baseline)
    assert any("hoort bij 1.0.0" in e for e in errors)
    # ook als iemand alleen de tag bijwerkt: de web-checkout zelf is nog 1.0.0
    errors = web_bron.check_checkout(web["repo"], {**baseline, "web_upstream_tag": "v1.1"})
    assert any("web-client is versie 1.0.0" in e for e in errors)


def test_renamed_package_breaks_technical_identity(web):
    write(web["repo"], "package.json", package("1.0.0", name="jelly-leon-web"))
    fork = commit_all(web["repo"], "naam gewijzigd")
    errors = web_bron.check_checkout(web["repo"], {**web["baseline"], "web_fork_commit": fork})
    assert any("technische identiteit" in e for e in errors)


def test_fork_not_based_on_recorded_upstream_fails(web, tmp_path):
    other = init_repo(tmp_path / "ander")
    write(other, "package.json", package("1.0.0"))
    foreign = commit_all(other, "andere basis")
    git(web["repo"], "fetch", "-q", str(other), "main")
    errors = web_bron.check_checkout(web["repo"], {**web["baseline"], "web_upstream_commit": foreign})
    assert any("geen voorouder" in e for e in errors)


def test_missing_upstream_commit_needs_full_history(web):
    errors = web_bron.check_checkout(web["repo"], {**web["baseline"], "web_upstream_commit": "b" * 40})
    assert any("volledige historie nodig" in e for e in errors)


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"web_fork_commit": "2795f3365"}, "volledige commit-SHA"),
        ({"web_fork_commit": "main"}, "volledige commit-SHA"),
        ({"web_repo": "git@github.com:lvos04/jelly-leon-web.git"}, "geen https://github.com"),
        ({"web_upstream_tag": "v1.0.1-rc1"}, "geen stabiele upstream-tag"),
    ],
)
def test_baseline_web_fields_are_strict(web, override, fragment):
    errors, _ = web_bron.web_fields({**web["baseline"], **override})
    assert any(fragment in e for e in errors), errors


def test_commit_mode_writes_github_output(web, tmp_path, monkeypatch, capsys):
    fork_repo = tmp_path / "fork"
    write(fork_repo, "tools/jelly-leon/baseline.json", json.dumps(web["baseline"]))
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert web_bron.main(["--repo", str(fork_repo), "--commit", "--github-output"]) == 0
    assert output.read_text(encoding="utf-8") == f"commit={web['fork']}\nrepo=lvos04/jelly-leon-web\n"
    assert capsys.readouterr().out.strip() == web["fork"]
    assert web_bron.main(["--repo", str(fork_repo), "--controleer", str(web["repo"])]) == 0


def test_consistency_check_includes_web_fields_but_not_in_sync_mode(repos):
    import check_fork_consistency

    fork = repos["fork"]
    path = fork / "tools/jelly-leon/baseline.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    baseline.update({"web_repo": "https://github.com/lvos04/jelly-leon-web", "web_upstream_tag": "v0.9.0",
                     "web_upstream_commit": "c" * 40, "web_fork_commit": "d" * 40})
    path.write_text(json.dumps(baseline), encoding="utf-8")
    commit_all(fork, "web-velden")
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1  # v0.9.0 ≠ basis 1.0.0
    assert check_fork_consistency.main(["--repo", str(fork), "--zonder-manifest"]) == 0
