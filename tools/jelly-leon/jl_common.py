"""Gedeelde hulpfuncties voor de Jelly Leon-forktools (alleen Python-standaardbibliotheek).

Deze module wordt gebruikt door check_fork_consistency.py, patch_register_check.py en upstream_sync.py.
Alle meldingen voor mensen zijn Nederlands; identifiers zijn Engels.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = TOOLS_DIR.parent.parent

BASELINE_REL = "tools/jelly-leon/baseline.json"
FORK_PATHS_REL = "tools/jelly-leon/fork_paths.txt"
PATCHES_REL = "docs/platform-v2/PATCHES.md"
PLUGIN_PROPS_REL = "plugins/Directory.Build.props"
SHARED_VERSION_REL = "SharedVersion.cs"
MANIFEST_REL = "deploy/manifest/jelly-leon.manifest.yaml"
UPSTREAM_ABI_PROJECT_REL = "MediaBrowser.Controller/MediaBrowser.Controller.csproj"

# Stabiele upstream-tags: v10.11.11 (oude reeks) én v12.4 (nieuwe reeks zonder patchnummer).
# Alles met een achtervoegsel (-rc1, -beta, ...) is géén stabiele release.
STABLE_TAG_RE = re.compile(r"^v(\d+)\.(\d+)(?:\.(\d+))?$")
FORK_VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)-jl\.(\d+)$")


class ToolError(Exception):
    """Fout die als nette Nederlandse melding met exitcode wordt getoond."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True, order=True)
class Version:
    """Upstream-versie als (major, minor, patch); v12.4 wordt 12.4.0."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> Version:
        cleaned = text.strip()
        if cleaned.startswith("v"):
            cleaned = cleaned[1:]
        parts = cleaned.split(".")
        if not 2 <= len(parts) <= 4 or not all(p.isdigit() for p in parts):
            raise ToolError(f"ongeldige versie: {text!r}")
        nums = [int(p) for p in parts]
        if len(nums) == 4:
            if nums[3] != 0:
                raise ToolError(f"vierde versiedeel moet 0 zijn: {text!r}")
            nums = nums[:3]
        while len(nums) < 3:
            nums.append(0)
        return cls(nums[0], nums[1], nums[2])

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def parse_stable_tag(tag: str) -> Version | None:
    """Geeft de versie van een stabiele upstream-tag, of None voor rc/beta/onbekend."""
    match = STABLE_TAG_RE.match(tag.strip())
    if not match:
        return None
    major, minor, patch = match.group(1), match.group(2), match.group(3) or "0"
    return Version(int(major), int(minor), int(patch))


def run_git(
    repo: Path, *args: str, check: bool = True, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Voert git uit zonder shell; geeft stdout/stderr als tekst terug."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        input=input_text,
    )
    if check and proc.returncode != 0:
        raise ToolError(f"git {' '.join(args)} mislukte (exit {proc.returncode}): {proc.stderr.strip()}")
    return proc


def load_baseline(repo: Path) -> dict:
    path = repo / BASELINE_REL
    if not path.is_file():
        raise ToolError(f"{BASELINE_REL} ontbreekt")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolError(f"{BASELINE_REL} is geen geldige JSON: {exc}") from exc
    for key in ("upstream_tag", "upstream_version", "upstream_commit", "fork_version"):
        if not data.get(key):
            raise ToolError(f"{BASELINE_REL}: veld '{key}' ontbreekt of is leeg")
    return data


def write_baseline(repo: Path, data: dict) -> None:
    path = repo / BASELINE_REL
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_shared_version(repo: Path) -> str:
    text = (repo / SHARED_VERSION_REL).read_text(encoding="utf-8-sig")
    match = re.search(r'AssemblyVersion\("([^"]+)"\)', text)
    if not match:
        raise ToolError(f"{SHARED_VERSION_REL}: AssemblyVersion niet gevonden")
    return match.group(1)


def read_plugin_jellyfin_version(repo: Path) -> str | None:
    path = repo / PLUGIN_PROPS_REL
    if not path.is_file():
        return None
    match = re.search(r"<JellyfinVersion>([^<]+)</JellyfinVersion>", path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else None


def set_plugin_jellyfin_version(repo: Path, version: str) -> bool:
    """Zet JellyfinVersion in plugins/Directory.Build.props; True als er iets veranderde."""
    path = repo / PLUGIN_PROPS_REL
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r"<JellyfinVersion>[^<]+</JellyfinVersion>",
        f"<JellyfinVersion>{version}</JellyfinVersion>",
        text,
    )
    if count != 1:
        raise ToolError(f"{PLUGIN_PROPS_REL}: verwacht precies één <JellyfinVersion>, gevonden {count}")
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def load_fork_paths(repo: Path) -> list[str]:
    path = repo / FORK_PATHS_REL
    if not path.is_file():
        raise ToolError(f"{FORK_PATHS_REL} ontbreekt")
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


def is_fork_path(file_path: str, fork_paths: list[str]) -> bool:
    for entry in fork_paths:
        if entry.endswith("/"):
            if file_path.startswith(entry):
                return True
        elif file_path == entry:
            return True
    return False


TF_RE = re.compile(r"<TargetFramework>([^<]+)</TargetFramework>")


def read_upstream_target_framework(repo: Path) -> str | None:
    """TargetFramework van de upstream-plugin-ABI (MediaBrowser.Controller → NuGet Jellyfin.Controller)."""
    path = repo / UPSTREAM_ABI_PROJECT_REL
    if not path.is_file():
        return None
    match = TF_RE.search(path.read_text(encoding="utf-8-sig"))
    return match.group(1).strip() if match else None


def read_plugin_target_framework(repo: Path) -> str | None:
    path = repo / PLUGIN_PROPS_REL
    if not path.is_file():
        return None
    match = TF_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else None


def set_plugin_target_framework(repo: Path, target_framework: str) -> bool:
    """Zet TargetFramework in plugins/Directory.Build.props (als die er staat); True als er iets veranderde."""
    path = repo / PLUGIN_PROPS_REL
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if not TF_RE.search(text):
        return False
    new_text = TF_RE.sub(f"<TargetFramework>{target_framework}</TargetFramework>", text, count=1)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False
