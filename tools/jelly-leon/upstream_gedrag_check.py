#!/usr/bin/env python3
"""Controleert het register van upstream-gedrag, serverdeel (docs/platform-v2/UPSTREAM_GEDRAG.md; B03-019 a, §10.11).

Per regel `UG-<functie>-<n>` (functie: GEM of F1…F6):
  * alle velden gevuld; bestand en anker tussen backticks; ID's uniek en per reeks doorlopend vanaf 1;
  * het bestand ligt buiten de fork-eigen paden (het gaat om upstream-gedrag) en bestaat;
  * het anker (Python-regex, `re.MULTILINE`) staat in dat bestand van de huidige boom — anders is het gedrag bij een
    upstream-sync verhuisd of verdwenen en blokkeert de sync (EX48, JLT-67);
  * de kolom Test noemt `anker` en/of `runtime:<naam>`; elke runtime-naam bestaat in
    tools/jelly-leon/e2e/upstream_gedrag_runtime.py (CHECKS);
  * elke verwijzing `UG-…` in eigen documentatie, code en workflows staat in het register ("een verwijzing UG-…
    zonder test laat de build falen", B03-019). Plankopieën uit ai-server-manager (02_BOUWPLANNEN/, EXCEL_TAKEN.json en
    de andere genummerde mappen) en het webregister (`UG-WEB-…`) tellen niet mee.

Exitcodes: 0 = in orde, 1 = overtreding, 3 = gebruiks-/omgevingsfout.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "e2e"))

from jl_common import DEFAULT_REPO_ROOT, ToolError, is_fork_path, load_fork_paths  # noqa: E402

REGISTER_REL = "docs/platform-v2/UPSTREAM_GEDRAG.md"
ID_RE = re.compile(r"^UG-(GEM|F[1-6])-(\d+)$")
REF_RE = re.compile(r"\bUG-(GEM|F[1-6])-(\d+)\b")
CELL_CODE_RE = re.compile(r"^`([^`]+)`$")
TEST_RE = re.compile(r"\b(anker|runtime:[a-z0-9_]+)\b")
SCAN_ROOTS = ("docs/adr", "docs/platform-v2", "README.jelly-leon.md", "tools/jelly-leon", "tools/emby-overname",
              "tools/b03-harnas", ".github/workflows/jelly-leon-ci.yml", ".github/workflows/upstream-sync.yml")
SCAN_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".txt"}
# Kopieën uit ai-server-manager: plantekst met geplande reeksen, geen claims van deze repo.
SKIP_PREFIXES = ("docs/platform-v2/0", "docs/platform-v2/PLATFORM_CONTRACTEN.md", "docs/platform-v2/CONTRACT_1.2_",
                 "tools/jelly-leon/tests/", "tools/jelly-leon/.venv/")


@dataclass(frozen=True)
class Entry:
    entry_id: str
    series: str
    number: int
    behaviour: str
    path: str
    anchor: str
    used_by: str
    tests: tuple[str, ...]


def _split_row(line: str) -> list[str]:
    cells = line.strip()
    if not (cells.startswith("|") and cells.endswith("|")):
        return []
    return [cell.strip() for cell in cells[1:-1].split("|")]


def parse_register(text: str) -> tuple[list[Entry], list[str]]:
    entries: list[Entry] = []
    errors: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        cells = _split_row(line)
        if not cells or not ID_RE.match(cells[0]):
            continue
        where = f"{REGISTER_REL}:{number}"
        if len(cells) != 6:
            errors.append(f"{where}: {cells[0]} heeft {len(cells)} kolommen, verwacht 6 (een '|' in de regex? gebruik \\x7c)")
            continue
        entry_id, behaviour, path_cell, anchor_cell, used_by, test = cells
        path_match, anchor_match = CELL_CODE_RE.match(path_cell), CELL_CODE_RE.match(anchor_cell)
        if not path_match or not anchor_match:
            errors.append(f"{where}: {entry_id}: bestand en anker staan elk tussen backticks")
            continue
        tests = tuple(TEST_RE.findall(test))
        if not all((behaviour, used_by)) or not tests:
            errors.append(f"{where}: {entry_id}: gedrag, 'gebruikt door' en een test (anker/runtime:<naam>) zijn verplicht")
            continue
        match = ID_RE.match(entry_id)
        assert match
        entries.append(Entry(entry_id, match.group(1), int(match.group(2)), behaviour, path_match.group(1),
                             anchor_match.group(1), used_by, tests))
    return entries, errors


def runtime_checks() -> set[str]:
    import upstream_gedrag_runtime  # noqa: PLC0415 - alleen nodig voor de namen

    return set(upstream_gedrag_runtime.CHECKS)


def check_entries(repo: Path, entries: list[Entry], fork_paths: list[str], known_runtime: set[str]) -> list[str]:
    errors: list[str] = []
    if not entries:
        errors.append(f"{REGISTER_REL}: geen enkele UG-regel (register leeg of onleesbaar)")
    for series in sorted({e.series for e in entries}):
        numbers = [e.number for e in entries if e.series == series]
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        if duplicates:
            errors.append(f"{REGISTER_REL}: dubbele ID's: {', '.join(f'UG-{series}-{n}' for n in duplicates)}")
        if sorted(set(numbers)) != list(range(1, len(set(numbers)) + 1)):
            errors.append(f"{REGISTER_REL}: nummering UG-{series} niet doorlopend vanaf 1 ({sorted(set(numbers))})")
    for entry in entries:
        for test in entry.tests:
            if test.startswith("runtime:") and test.removeprefix("runtime:") not in known_runtime:
                errors.append(f"{entry.entry_id}: onbekende runtime-test {test} (niet in upstream_gedrag_runtime.CHECKS)")
        if is_fork_path(entry.path, fork_paths):
            errors.append(f"{entry.entry_id}: {entry.path} is een fork-eigen pad; het register gaat over upstream-gedrag")
            continue
        try:
            pattern = re.compile(entry.anchor, re.MULTILINE)
        except re.error as exc:
            errors.append(f"{entry.entry_id}: anker is geen geldige regex: {exc}")
            continue
        target = repo / entry.path
        if not target.is_file():
            errors.append(f"{entry.entry_id}: {entry.path} bestaat niet (meer) — gedrag verhuisd? Eerst opnieuw beoordelen")
            continue
        if not pattern.search(target.read_text(encoding="utf-8", errors="replace")):
            errors.append(
                f"{entry.entry_id}: anker niet gevonden in {entry.path} ({entry.behaviour}) — upstream-gedrag gewijzigd; "
                "eerst opnieuw beoordelen, dan pas module/anker aanpassen"
            )
    return errors


def iter_scan_files(repo: Path):
    for root in SCAN_ROOTS:
        path = repo / root
        if path.is_file():
            yield path
        elif path.is_dir():
            for item in sorted(path.rglob("*")):
                rel = item.relative_to(repo).as_posix()
                if (item.is_file() and item.suffix in SCAN_SUFFIXES and "__pycache__" not in item.parts
                        and not rel.startswith(SKIP_PREFIXES) and "node_modules" not in item.parts):
                    yield item


def check_references(repo: Path, entries: list[Entry]) -> list[str]:
    known = {(e.series, e.number) for e in entries}
    errors: list[str] = []
    for path in iter_scan_files(repo):
        rel = path.relative_to(repo).as_posix()
        if rel == REGISTER_REL:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            for match in REF_RE.finditer(line):
                if (match.group(1), int(match.group(2))) not in known:
                    errors.append(f"{rel}:{number}: verwijst naar {match.group(0)}, dat niet in {REGISTER_REL} staat")
    return errors


def check(repo: Path, known_runtime: set[str] | None = None) -> tuple[list[Entry], list[str]]:
    register = repo / REGISTER_REL
    if not register.is_file():
        raise ToolError(f"{REGISTER_REL} ontbreekt (B03-019: het register bestaat)", exit_code=1)
    entries, errors = parse_register(register.read_text(encoding="utf-8"))
    errors += check_entries(repo, entries, load_fork_paths(repo), runtime_checks() if known_runtime is None else known_runtime)
    errors += check_references(repo, entries)
    return entries, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controleer het register van upstream-gedrag (serverdeel).")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--overzicht", action="store_true", help="druk per regel ID, bestand, tests en uitkomst af")
    args = parser.parse_args(argv)
    try:
        entries, errors = check(args.repo.resolve())
    except ToolError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return exc.exit_code
    if args.overzicht:
        failed = {line.split(":", 1)[0] for line in errors}
        for entry in entries:
            print(f"{'FOUT' if entry.entry_id in failed else 'OK  '} {entry.entry_id:<10} {', '.join(entry.tests):<45} {entry.path}")
    if errors:
        print(f"UPSTREAM-GEDRAG NIET IN ORDE ({len(errors)} problemen):", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1
    runtime = sorted({t for e in entries for t in e.tests if t.startswith("runtime:")})
    print(f"Upstream-gedrag (serverdeel) in orde: {len(entries)} ankers gevonden, {len(runtime)} runtime-tests gekoppeld, "
          "alle UG-verwijzingen bekend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
