"""Herbasis-sync bij uiteenlopende upstream-releasereeksen (zoals 10.11.x-backports versus 12.x).

Gemeten op 2026-11-09: een gewone merge van upstream v12.4 in de fork (basis v10.11.11) gaf 79 conflicten, waarvan maar
4 in bestanden die de fork zelf wijzigt — de rest komt uit upstream zelf (backports op de releasebranch). Deze test
bootst dat na met een nep-upstream.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import check_fork_consistency
import dotnet_sdk_kanaal
import patch_register_check
import upstream_sync
from conftest import (
    DOCKERFILE,
    FORK_PATHS,
    GPL_HEAD,
    MANIFEST,
    PATCHES,
    commit_all,
    git,
    init_repo,
    shared_version,
    write,
)

CSPROJ = "<Project>\n  <PropertyGroup>\n    <TargetFramework>{tf}</TargetFramework>\n  </PropertyGroup>\n</Project>\n"
PROPS_WITH_TF = (
    "<Project>\n  <PropertyGroup>\n    <JellyfinVersion>1.0.0</JellyfinVersion>\n"
    "    <TargetFramework>net9.0</TargetFramework>\n  </PropertyGroup>\n</Project>\n"
)
BOT_BASE = "name: bot\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
GLOBAL_JSON = '{{\n    "sdk": {{\n        "version": "{sdk}",\n        "rollForward": "latestMinor"\n    }}\n}}\n'
BOT_GUARDED = "name: bot\njobs:\n  a:\n    if: github.repository == 'up/stream'\n    runs-on: ubuntu-latest\n"


@pytest.fixture()
def diverged(tmp_path: Path) -> dict:
    upstream = init_repo(tmp_path / "upstream")
    write(upstream, "LICENSE", GPL_HEAD)
    write(upstream, "CONTRIBUTORS.md", "- upstream-auteur\n")
    write(upstream, "SharedVersion.cs", shared_version("1.0.0"))
    write(upstream, ".github/workflows/bot.yml", BOT_BASE)
    write(upstream, "src/Server.cs", "class Server {}\n")
    write(upstream, "MediaBrowser.Controller/MediaBrowser.Controller.csproj", CSPROJ.format(tf="net9.0"))
    write(upstream, "global.json", GLOBAL_JSON.format(sdk="9.0.0"))
    base = commit_all(upstream, "upstream 1.0.0")
    git(upstream, "tag", "-a", "v1.0.0", "-m", "1.0.0")

    # Releasereeks 1.0: backport (andere tekst dan op main).
    git(upstream, "switch", "-q", "-c", "release-1.0")
    write(upstream, "SharedVersion.cs", shared_version("1.0.1"))
    write(upstream, "src/Server.cs", "class Server { int Fix; } // backport\n")
    v101 = commit_all(upstream, "backport fix 1.0.1")
    git(upstream, "tag", "-a", "v1.0.1", "-m", "1.0.1")

    # Hoofdlijn naar 2.0: dezelfde fix anders, nieuwe functie, extra job onderaan de gepatchte workflow.
    git(upstream, "switch", "-q", "main")
    write(upstream, "SharedVersion.cs", shared_version("2.0.0"))
    write(upstream, "src/Server.cs", "class Server { int Fix; int Feature; }\n")
    write(upstream, "src/New.cs", "class New {}\n")
    write(upstream, "MediaBrowser.Controller/MediaBrowser.Controller.csproj", CSPROJ.format(tf="net10.0"))
    write(upstream, "global.json", GLOBAL_JSON.format(sdk="10.0.0"))
    write(upstream, ".github/workflows/bot.yml", BOT_BASE + "  b:\n    runs-on: ubuntu-latest\n")
    v20 = commit_all(upstream, "upstream 2.0")
    git(upstream, "tag", "-a", "v2.0", "-m", "2.0")

    fork = tmp_path / "fork"
    subprocess.run(["git", "clone", "-q", "--branch", "v1.0.0", str(upstream), str(fork)], check=True)
    git(fork, "switch", "-q", "-c", "main")
    for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"), ("commit.gpgsign", "false")):
        git(fork, "config", key, value)
    baseline = {
        "schema_version": "1",
        "upstream_tag": "v1.0.0",
        "upstream_version": "1.0.0",
        "upstream_commit": base,
        "local_upstream_tag": "upstream-v1.0.0",
        "fork_version": "1.0.0-jl.0",
        "dotnet_sdk_major": "9.0",
    }
    write(fork, "tools/jelly-leon/baseline.json", json.dumps(baseline, indent=2) + "\n")
    write(fork, "tools/jelly-leon/fork_paths.txt", FORK_PATHS)
    write(fork, "plugins/Directory.Build.props", PROPS_WITH_TF)
    write(fork, "deploy/manifest/jelly-leon.manifest.yaml", MANIFEST.format(fork="1.0.0-jl.0"))
    write(fork, "deploy/allinone/Dockerfile", DOCKERFILE.format(digest="c" * 64))
    write(fork, "docs/platform-v2/PATCHES.md", PATCHES)
    write(fork, "README.jelly-leon.md", "# fork\n")
    write(fork, ".github/workflows/bot.yml", BOT_GUARDED)
    commit_all(fork, "fork-opzet")
    return {"upstream": upstream, "fork": fork, "v101": v101, "v20": v20}


def test_patch_release_on_same_line_uses_merge(diverged, capsys):
    fork = diverged["fork"]
    rc = upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v1.0.1", "--bron", str(diverged["upstream"])])
    assert rc == 0, capsys.readouterr().err
    assert json.loads(capsys.readouterr().out)["methode"] == "merge"
    assert "backport" in (fork / "src/Server.cs").read_text()


def _fork_on_release_line(diverged) -> Path:
    fork = diverged["fork"]
    assert upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v1.0.1", "--bron", str(diverged["upstream"])]) == 0
    git(fork, "switch", "-q", "main")
    git(fork, "merge", "-q", "--ff-only", "sync/v1.0.1")
    return fork


def test_plain_merge_across_lines_conflicts_in_unpatched_files(diverged, capsys):
    fork = _fork_on_release_line(diverged)
    capsys.readouterr()
    head = git(fork, "rev-parse", "HEAD")
    rc = upstream_sync.main(
        ["--repo", str(fork), "merge", "--tag", "v2.0", "--bron", str(diverged["upstream"]), "--methode", "merge"]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "INCOMPATIBEL (merge)" in err and "src/Server.cs" in err  # bestand dat de fork nooit wijzigde
    assert git(fork, "rev-parse", "HEAD") == head and git(fork, "status", "--porcelain") == ""


def test_herbasis_across_lines_keeps_fork_and_patches_upstream_wins_elsewhere(diverged, capsys):
    fork = _fork_on_release_line(diverged)
    fork_head = git(fork, "rev-parse", "HEAD")
    capsys.readouterr()
    rc = upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v2.0", "--bron", str(diverged["upstream"])])
    out, err = capsys.readouterr()
    assert rc == 0, err
    assert json.loads(out)["methode"] == "herbasis"
    # Upstream wint voor alles buiten fork-paden en patches.
    assert (fork / "src/Server.cs").read_text() == "class Server { int Fix; int Feature; }\n"
    assert (fork / "src/New.cs").is_file()
    # Geregistreerde core-patch opnieuw toegepast (3-way), nieuwe upstream-job behouden.
    bot = (fork / ".github/workflows/bot.yml").read_text()
    assert "if: github.repository == 'up/stream'" in bot and "  b:\n" in bot
    # Fork-eigen bestanden aanwezig en basis bijgewerkt.
    baseline = json.loads((fork / "tools/jelly-leon/baseline.json").read_text())
    assert baseline["upstream_commit"] == diverged["v20"] and baseline["fork_version"] == "2.0.0-jl.0"
    assert (fork / "README.jelly-leon.md").is_file()
    # Historie behouden: herbasis-commit heeft de vorige forkstand én de upstream-tag als ouders.
    anchor = git(fork, "rev-parse", "HEAD~1")
    assert git(fork, "rev-list", "--parents", "-n", "1", anchor).split()[1:] == [fork_head, diverged["v20"]]
    assert git(fork, "merge-base", "--is-ancestor", fork_head, "HEAD") == ""
    # Forkregels kloppen tegen de nieuwe basis.
    errors, _ = patch_register_check.check(fork, None, "HEAD")
    assert errors == []
    props = (fork / "plugins/Directory.Build.props").read_text()
    assert "<JellyfinVersion>2.0.0</JellyfinVersion>" in props and "<TargetFramework>net10.0</TargetFramework>" in props
    assert check_fork_consistency.main(["--repo", str(fork), "--zonder-manifest"]) == 0


def test_herbasis_follows_sdk_line_of_new_base(diverged, capsys):
    """Reekssprong met nieuwe SDK (zoals 10.11 → 12.x met .NET 10): baseline volgt global.json, deploy niet vanzelf."""
    fork = _fork_on_release_line(diverged)
    capsys.readouterr()
    assert upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v2.0", "--bron", str(diverged["upstream"])]) == 0
    capsys.readouterr()
    baseline = json.loads((fork / "tools/jelly-leon/baseline.json").read_text())
    assert baseline["dotnet_sdk_major"] == "10.0"
    assert '"version": "10.0.0"' in (fork / "global.json").read_text()  # upstream-bestand ongewijzigd overgenomen
    assert dotnet_sdk_kanaal.main(["--repo", str(fork)]) == 0
    assert capsys.readouterr().out.strip() == "10.0.x"
    # Sync-modus (zonder deploy-controle) slaagt; de deploy-Dockerfile (SDK 9.0) moet bij de release handmatig mee.
    assert check_fork_consistency.main(["--repo", str(fork), "--zonder-manifest"]) == 0
    capsys.readouterr()
    assert check_fork_consistency.main(["--repo", str(fork)]) == 1
    assert ".NET-SDK-image 9.0 past niet bij global.json (10.0.0" in capsys.readouterr().err


def test_consistency_detects_plugin_target_framework_drift(diverged, capsys):
    fork = diverged["fork"]
    write(fork, "MediaBrowser.Controller/MediaBrowser.Controller.csproj", CSPROJ.format(tf="net10.0"))
    assert check_fork_consistency.main(["--repo", str(fork), "--zonder-manifest"]) == 1
    assert "TargetFramework net9.0 ≠ upstream-ABI net10.0" in capsys.readouterr().err


def test_herbasis_fails_cleanly_when_patch_no_longer_applies(diverged, capsys):
    fork = _fork_on_release_line(diverged)
    upstream = diverged["upstream"]
    write(upstream, ".github/workflows/bot.yml", "name: bot\njobs:\n  a:\n    runs-on: ubuntu-24.04\n")
    commit_all(upstream, "upstream 2.1 wijzigt de gepatchte regels")
    git(upstream, "tag", "-a", "v2.1", "-m", "2.1")
    head = git(fork, "rev-parse", "HEAD")
    capsys.readouterr()
    rc = upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v2.1", "--bron", str(upstream)])
    err = capsys.readouterr().err
    assert rc == 2 and "INCOMPATIBEL (herbasis)" in err and ".github/workflows/bot.yml" in err
    assert git(fork, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(fork, "rev-parse", "HEAD") == head
    assert git(fork, "status", "--porcelain") == ""
    assert git(fork, "branch", "--list", "sync/v2.1") == ""




def _two_patch_fork(diverged) -> Path:
    """Fork met twee geregistreerde core-patches: bot.yml (botst in 2.1) en src/Server.cs (blijft schoon)."""
    fork = _fork_on_release_line(diverged)
    register = (fork / "docs/platform-v2/PATCHES.md").read_text()
    extra = (
        "\n## JL-9002 — Serverkleinigheid\n\n| Veld | Waarde |\n|---|---|\n| Status | actief |\n"
        "| Doel | test |\n| Bestanden | `src/Extra.cs` |\n| Waarom geen plugin/configuratie | test |\n"
        "| Upstream-PR-kans | laag |\n| Test | test |\n"
    )
    write(fork, "docs/platform-v2/PATCHES.md", register + extra)
    write(fork, "src/Extra.cs", "class Extra {}\n")
    commit_all(fork, "tweede core-patch")
    upstream = diverged["upstream"]
    write(upstream, ".github/workflows/bot.yml", "name: bot\njobs:\n  a:\n    runs-on: ubuntu-24.04\n")
    commit_all(upstream, "upstream 2.1 wijzigt de gepatchte regels")
    git(upstream, "tag", "-a", "v2.1", "-m", "2.1")
    return fork


def test_herbasis_reports_result_per_patch_and_aborts_without_manual(diverged, capsys):
    fork = _two_patch_fork(diverged)
    head = git(fork, "rev-parse", "HEAD")
    capsys.readouterr()
    rc = upstream_sync.main(["--repo", str(fork), "merge", "--tag", "v2.1", "--bron", str(diverged["upstream"])])
    out, err = capsys.readouterr()
    assert rc == 2 and "INCOMPATIBEL (herbasis)" in err
    per_patch = {r["patch"]: r for r in json.loads(out)["patches"]}
    assert per_patch["JL-9002"]["resultaat"] == "schoon"
    assert per_patch[next(p for p in per_patch if p != "JL-9002")]["resultaat"] == "conflict"
    assert git(fork, "rev-parse", "HEAD") == head and git(fork, "status", "--porcelain") == ""
    assert git(fork, "branch", "--list", "sync/v2.1") == ""


def test_herbasis_manual_resolution_then_voltooi(diverged, capsys):
    fork = _two_patch_fork(diverged)
    fork_head = git(fork, "rev-parse", "HEAD")
    capsys.readouterr()
    rc = upstream_sync.main(
        ["--repo", str(fork), "merge", "--tag", "v2.1", "--bron", str(diverged["upstream"]), "--handmatig-oplossen"]
    )
    out, err = capsys.readouterr()
    assert rc == 2 and "voltooi" in err
    assert json.loads(out)["status"] == "wacht_op_handmatig_oplossen"
    assert git(fork, "rev-parse", "--abbrev-ref", "HEAD") == "sync/v2.1"
    bot = fork / ".github/workflows/bot.yml"
    assert "<<<<<<<" in bot.read_text()

    # Nog niet opgelost: voltooi weigert (onopgelost bestand of markeringen).
    assert upstream_sync.main(["--repo", str(fork), "voltooi"]) == 1
    assert "onopgelost" in capsys.readouterr().err
    git(fork, "add", ".github/workflows/bot.yml")
    assert upstream_sync.main(["--repo", str(fork), "voltooi"]) == 1
    assert "conflictmarkeringen" in capsys.readouterr().err

    # Guard opnieuw op de nieuwe upstream-regel zetten (zoals JL-0001 bij v12.4).
    write(fork, ".github/workflows/bot.yml",
          "name: bot\njobs:\n  a:\n    if: github.repository == 'up/stream'\n    runs-on: ubuntu-24.04\n")
    git(fork, "add", ".github/workflows/bot.yml")
    assert upstream_sync.main(["--repo", str(fork), "voltooi"]) == 0, capsys.readouterr().err
    result = json.loads(capsys.readouterr().out)
    states = {r["patch"]: r["resultaat"] for r in result["patches"]}
    assert states["JL-9002"] == "schoon" and "conflict_handmatig_opgelost" in states.values()
    baseline = json.loads((fork / "tools/jelly-leon/baseline.json").read_text())
    assert baseline["upstream_tag"] == "v2.1" and baseline["fork_version"] == "2.1.0-jl.0"
    anchor = git(fork, "rev-parse", "HEAD~1")
    upstream_v21 = git(diverged["upstream"], "rev-parse", "v2.1^{commit}")
    assert git(fork, "rev-list", "--parents", "-n", "1", anchor).split()[1:] == [fork_head, upstream_v21]
    assert (fork / "src/Extra.cs").read_text() == "class Extra {}\n"
    errors, _ = patch_register_check.check(fork, None, "HEAD")
    assert errors == []
    assert upstream_sync.main(["--repo", str(fork), "voltooi"]) == 1  # toestand opgeruimd
