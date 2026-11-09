"""Testopzet: een nep-upstream en een fork in tijdelijke git-repositories (simulator, geen netwerk)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

GPL_HEAD = "GNU GENERAL PUBLIC LICENSE\n                       Version 2, June 1991\n"


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "commit.gpgsign", "false")
    return path


def shared_version(version: str) -> str:
    return (
        "using System.Reflection;\n\n"
        f'[assembly: AssemblyVersion("{version}")]\n[assembly: AssemblyFileVersion("{version}")]\n'
    )


PLUGIN_PROPS = """<Project>
  <PropertyGroup>
    <JellyfinVersion>{version}</JellyfinVersion>
  </PropertyGroup>
</Project>
"""

MANIFEST = """manifest_version: "1"
app_id: jelly-leon
version: "{fork}"
install:
  method: custom_app
image:
  repository: ghcr.io/lvos04/jelly-leon
  tag: "{fork}"
  digest: null
"""

DOCKERFILE = """# syntax=docker/dockerfile:1.7
ARG SDK_IMAGE=mcr.microsoft.com/dotnet/sdk:9.0@sha256:{digest}
FROM ${{SDK_IMAGE}} AS build
FROM build AS final
"""

PATCHES = """# Patchregister

## JL-0001 — Repository-guard op upstream-workflow

| Veld | Waarde |
|---|---|
| Status | actief |
| Doel | Upstream-bot-workflow niet laten falen in de fork |
| Bestanden | `.github/workflows/bot.yml` |
| Waarom geen plugin/configuratie | Workflowbestanden zijn niet via een plugin aan te passen |
| Upstream-PR-kans | laag |
| Test | tests/test_patch_register.py |
"""

FORK_PATHS = """# fork-eigen
README.jelly-leon.md
docs/platform-v2/
plugins/
deploy/
tools/jelly-leon/
"""


@pytest.fixture()
def repos(tmp_path: Path) -> dict:
    """Bouwt upstream (tags v1.0.0, v1.0.1, v1.1, v1.2-rc1) en een fork op basis van v1.0.0."""
    upstream = init_repo(tmp_path / "upstream")
    write(upstream, "LICENSE", GPL_HEAD)
    write(upstream, "CONTRIBUTORS.md", "- upstream-auteur\n")
    write(upstream, "SharedVersion.cs", shared_version("1.0.0"))
    write(upstream, ".github/workflows/bot.yml", "name: bot\njobs:\n  a:\n    runs-on: ubuntu-latest\n")
    write(upstream, "src/Server.cs", "class Server {}\n")
    base_commit = commit_all(upstream, "upstream 1.0.0")
    git(upstream, "tag", "-a", "v1.0.0", "-m", "1.0.0")

    fork = tmp_path / "fork"
    subprocess.run(["git", "clone", "-q", str(upstream), str(fork)], check=True)
    git(fork, "config", "user.name", "Test")
    git(fork, "config", "user.email", "test@example.invalid")
    git(fork, "config", "commit.gpgsign", "false")
    git(fork, "remote", "rename", "origin", "upstream")
    git(fork, "tag", "upstream-v1.0.0", base_commit)
    baseline = {
        "schema_version": "1",
        "upstream_tag": "v1.0.0",
        "upstream_version": "1.0.0",
        "upstream_commit": base_commit,
        "local_upstream_tag": "upstream-v1.0.0",
        "fork_version": "1.0.0-jl.0",
    }
    write(fork, "tools/jelly-leon/baseline.json", json.dumps(baseline, indent=2) + "\n")
    write(fork, "tools/jelly-leon/fork_paths.txt", FORK_PATHS)
    write(fork, "plugins/Directory.Build.props", PLUGIN_PROPS.format(version="1.0.0"))
    write(fork, "deploy/manifest/jelly-leon.manifest.yaml", MANIFEST.format(fork="1.0.0-jl.0"))
    write(fork, "deploy/allinone/Dockerfile", DOCKERFILE.format(digest="a" * 64))
    write(fork, "docs/platform-v2/PATCHES.md", PATCHES)
    write(fork, "README.jelly-leon.md", "# fork\n")
    # Geregistreerde core-patch JL-0001: repository-guard.
    write(
        fork,
        ".github/workflows/bot.yml",
        "name: bot\njobs:\n  a:\n    if: github.repository == 'up/stream'\n    runs-on: ubuntu-latest\n",
    )
    commit_all(fork, "fork-opzet")

    # Upstream gaat verder: 1.0.1 (compatibel), 1.1 (raakt de gepatchte workflow → conflict), 1.2-rc1 (geen release).
    write(upstream, "SharedVersion.cs", shared_version("1.0.1"))
    write(upstream, "src/Server.cs", "class Server { int Fix; }\n")
    v101 = commit_all(upstream, "upstream 1.0.1")
    git(upstream, "tag", "-a", "v1.0.1", "-m", "1.0.1")
    write(upstream, "SharedVersion.cs", shared_version("1.1.0"))
    write(
        upstream,
        ".github/workflows/bot.yml",
        "name: bot\njobs:\n  a:\n    runs-on: ubuntu-24.04\n    timeout-minutes: 5\n",
    )
    v11 = commit_all(upstream, "upstream 1.1")
    git(upstream, "tag", "-a", "v1.1", "-m", "1.1")
    write(upstream, "src/Server.cs", "class Server { int Rc; }\n")
    commit_all(upstream, "upstream 1.2-rc1")
    git(upstream, "tag", "-a", "v1.2-rc1", "-m", "rc")
    return {"upstream": upstream, "fork": fork, "base": base_commit, "v101": v101, "v11": v11}
