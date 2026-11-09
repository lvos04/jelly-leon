#!/usr/bin/env python3
"""Controleert dat elke afwijking van upstream (core-patch) in het patchregister staat (ADR-0001).

Werking:
  * basis = upstream-commit uit tools/jelly-leon/baseline.json (of --base);
  * `git diff --name-status basis HEAD` geeft alle gewijzigde, toegevoegde, verwijderde en hernoemde bestanden;
  * fork-eigen paden (tools/jelly-leon/fork_paths.txt) zijn geen core-patch;
  * LICENSE, CONTRIBUTORS.md en SharedVersion.cs mogen nooit afwijken (GPL-credits, technische identiteit);
  * elk ander bestand moet bij een actieve patch in docs/platform-v2/PATCHES.md staan;
  * elk bestand in een actieve patch moet ook echt afwijken (anders is het register verouderd).

Exitcodes: 0 = in orde, 1 = overtreding, 3 = gebruiks-/omgevingsfout.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jl_common import (  # noqa: E402
    DEFAULT_REPO_ROOT,
    PATCHES_REL,
    ToolError,
    is_fork_path,
    load_baseline,
    load_fork_paths,
    run_git,
)

FORBIDDEN_FILES = ("LICENSE", "CONTRIBUTORS.md", "SharedVersion.cs")
ACTIVE_STATUSES = {"actief", "upstream-aangeboden"}
KNOWN_STATUSES = ACTIVE_STATUSES | {"vervallen"}
PATCH_HEADING_RE = re.compile(r"^##\s+(JL-\d{4})\b(.*)$")
ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$")
BACKTICK_RE = re.compile(r"`([^`]+)`")


@dataclass
class Patch:
    patch_id: str
    title: str
    status: str = ""
    files: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)


REQUIRED_FIELDS = ("Status", "Doel", "Bestanden", "Waarom geen plugin/configuratie", "Upstream-PR-kans", "Test")


def parse_register(text: str) -> list[Patch]:
    patches: list[Patch] = []
    current: Patch | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        heading = PATCH_HEADING_RE.match(line)
        if heading:
            current = Patch(patch_id=heading.group(1), title=heading.group(2).strip(" —-"))
            patches.append(current)
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is None:
            continue
        row = ROW_RE.match(line)
        if not row:
            continue
        key, value = row.group(1).strip(), row.group(2).strip()
        if key in ("Veld", "---") or set(key) <= {"-", ":"}:
            continue
        current.fields[key] = value
        if key == "Status":
            current.status = value.strip("`* ").lower()
        elif key == "Bestanden":
            current.files = BACKTICK_RE.findall(value)
    return patches


def validate_register(patches: list[Patch]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for patch in patches:
        if patch.patch_id in seen:
            problems.append(f"{patch.patch_id}: dubbel patch-ID in {PATCHES_REL}")
        seen.add(patch.patch_id)
        for name in REQUIRED_FIELDS:
            if not patch.fields.get(name):
                problems.append(f"{patch.patch_id}: verplicht veld '{name}' ontbreekt of is leeg")
        if patch.status not in KNOWN_STATUSES:
            problems.append(
                f"{patch.patch_id}: onbekende status '{patch.status}' (toegestaan: {', '.join(sorted(KNOWN_STATUSES))})"
            )
        if patch.status in ACTIVE_STATUSES and not patch.files:
            problems.append(f"{patch.patch_id}: actieve patch zonder bestanden")
    return problems


def changed_files(repo: Path, base: str, head: str) -> list[tuple[str, str]]:
    """Lijst (status, pad) van alle afwijkingen; bij hernoemen tellen oud én nieuw pad."""
    proc = run_git(repo, "diff", "--name-status", "-M", base, head)
    result: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            result.append((status[0], parts[1]))
            result.append((status[0], parts[2]))
        else:
            result.append((status, parts[1]))
    return result


def check(repo: Path, base: str | None, head: str) -> tuple[list[str], list[str]]:
    """Geeft (fouten, info-regels)."""
    baseline = load_baseline(repo)
    base_ref = base or baseline["upstream_commit"]
    if run_git(repo, "cat-file", "-e", f"{base_ref}^{{commit}}", check=False).returncode != 0:
        raise ToolError(
            f"basiscommit {base_ref} niet gevonden; haal de volledige historie op (actions/checkout fetch-depth: 0)",
            exit_code=3,
        )
    fork_paths = load_fork_paths(repo)
    register_path = repo / PATCHES_REL
    if not register_path.is_file():
        raise ToolError(f"{PATCHES_REL} ontbreekt", exit_code=3)
    patches = parse_register(register_path.read_text(encoding="utf-8"))
    errors = validate_register(patches)

    registered: dict[str, str] = {}
    for patch in patches:
        if patch.status in ACTIVE_STATUSES:
            for file_path in patch.files:
                if file_path in registered:
                    errors.append(f"{file_path}: staat in twee patches ({registered[file_path]}, {patch.patch_id})")
                registered[file_path] = patch.patch_id

    diffs = changed_files(repo, base_ref, head)
    diff_paths = {path for _, path in diffs}
    info: list[str] = []
    core_patch_files = 0
    for status, path in sorted(set(diffs), key=lambda item: item[1]):
        if path in FORBIDDEN_FILES:
            errors.append(f"{path}: mag nooit afwijken van upstream (status {status}; GPL-credits/technische identiteit)")
            continue
        if is_fork_path(path, fork_paths):
            continue
        if path in registered:
            core_patch_files += 1
            info.append(f"core-patch {registered[path]}: {status} {path}")
            continue
        errors.append(
            f"{path}: niet-geregistreerde core-patch (status {status}); voeg hem toe aan {PATCHES_REL} "
            "of verplaats de wijziging naar een plugin/fork-eigen pad"
        )

    for path, patch_id in sorted(registered.items()):
        if path in FORBIDDEN_FILES:
            errors.append(f"{patch_id}: {path} staat in het register maar mag nooit gepatcht worden")
        elif path not in diff_paths:
            errors.append(f"{patch_id}: {path} wijkt niet (meer) af van upstream; register is verouderd")

    info.append(
        f"basis {base_ref[:12]} → {head}: {len(diff_paths)} afwijkende paden, "
        f"{core_patch_files} in geregistreerde core-patches, {len(patches)} patches in register"
    )
    return errors, info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controleer het patchregister tegen de upstream-basis.")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--base", help="basiscommit (standaard: upstream_commit uit baseline.json)")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)
    try:
        errors, info = check(args.repo.resolve(), args.base, args.head)
    except ToolError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return exc.exit_code
    for line in info:
        print(line)
    if errors:
        print(f"PATCHREGISTER NIET IN ORDE ({len(errors)} problemen):", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print("Patchregister in orde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
