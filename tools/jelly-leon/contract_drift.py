#!/usr/bin/env python3
"""Drifttest van de gekopieerde platformcontracten (contract 1.3 kop en §10, C1.3-ALG-01 / C1.3-JL-01).

`docs/platform-v2/PLATFORM_CONTRACTEN.md` en `docs/platform-v2/CONTRACT_1.3_CONFORMITEIT.md` zijn byte-gelijke kopieën
uit `lvos04/ai-server-manager` (bron van waarheid) op een vastgezette bron-commit. Deze repo wijzigt ze nooit zelf; een
nieuwe contractversie overnemen is een stap van de orkestratie (nieuwe bron-commit + sha256 hieronder).

`docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md` blijft als historie staan (contract 1.3 C1.3-ALG-01 staat dat toe). Hij
is byte-gelijk aan de bron op de bron-commit van de 1.2-ronde en wordt nooit bijgewerkt; ook die kopie heeft een pin,
zodat niemand hem hier stil aanpast (`HISTORIE`).

Controles:
  1. altijd (offline): sha256 van elke kopie == de vastgezette sha256 (niemand heeft de kopie hier aangepast), ook
     voor de historiekopie;
  2. `--bron-map <checkout van ai-server-manager>`: de kopie is byte-gelijk aan `git show <bron-commit>:<pad>`
     (historie: op zijn eigen bron-commit); wijkt de werkboom van die checkout af, dan alleen een waarschuwing
     "bron gewijzigd" (kopie bijwerken; niet voor de historie);
  3. `--online`: idem via raw.githubusercontent.com op de volledige bron-commit (publieke repo, geen token) en —
     alleen als waarschuwing — op de bronbranch (`--bronbranch`).

Alleen standaardbibliotheek. Exitcodes: 0 = gelijk (eventueel met waarschuwing), 1 = drift/afwijking,
3 = gebruiks- of omgevingsfout (bv. bron niet bereikbaar).
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jl_common import DEFAULT_REPO_ROOT  # noqa: E402

BRON_REPO = "lvos04/ai-server-manager"
#: Commit van ai-server-manager waaruit de kopieën komen (contracts 1.3 incl. de review-correcties RV1–RV13,
#: ADR-0027/ADR-0028 daar; dezelfde bron-commit als in de andere repos).
BRON_COMMIT = "02b119cb84be9a307a88532f6692ea8a4bcb12f1"
BRON_BRANCH = "ccr-c133d7a0-kuz1cv"
#: Pad (gelijk in bron en kopie) → sha256 van de bron op BRON_COMMIT.
KOPIEEN: dict[str, str] = {
    "docs/platform-v2/PLATFORM_CONTRACTEN.md": "15b30cf17f91b606451ef9c41f02327076ef76ce655ee94e40e3538106962310",
    "docs/platform-v2/CONTRACT_1.3_CONFORMITEIT.md": "f0a2352ddb27088ae668013501c62a1eaaf879efe742a2d4422ffe8d33b43466",
}
#: Historiekopieën: pad → (eigen bron-commit, sha256). Nooit bijwerken; alleen bewaken dat ze niet lokaal wijzigen.
HISTORIE: dict[str, tuple[str, str]] = {
    "docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md": (
        "8b54f39408e25fd5c9b9e390d1bbacba52f0e584",
        "6daedffb44a9506f97c7b9135f65393191a4b6247e96661a64c7a6fed5297f59",
    ),
}
#: Kop die in de contractkopie moet staan (de versie die deze repo volgt).
VERSIEKOP = b"Versie: `contracts 1.3`"
RAW_URL = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"

Reader = Callable[[str], bytes | None]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_pins(
    repo: Path, pins: dict[str, str] | None = None, historie: dict[str, tuple[str, str]] | None = None
) -> list[str]:
    """Offline: elke kopie (en elke historiekopie) bestaat en heeft precies de vastgezette sha256."""
    errors: list[str] = []
    for rel, expected in (KOPIEEN if pins is None else pins).items():
        path = repo / rel
        if not path.is_file():
            errors.append(f"{rel} ontbreekt (kopie uit {BRON_REPO} verplicht, contract 1.3 C1.3-ALG-01)")
            continue
        data = path.read_bytes()
        found = sha256(data)
        if found != expected:
            errors.append(
                f"{rel}: sha256 {found[:16]}… ≠ vastgezet {expected[:16]}… — de kopie is gewijzigd; niet hier "
                f"aanpassen maar byte-gelijk opnieuw kopiëren uit {BRON_REPO}@{BRON_COMMIT[:9]} (of de pin bijwerken "
                "bij een nieuwe contractversie)"
            )
        if rel.endswith("PLATFORM_CONTRACTEN.md") and VERSIEKOP not in data:
            errors.append(f"{rel}: versiekop {VERSIEKOP.decode()} ontbreekt")
    for rel, (commit, expected) in (HISTORIE if historie is None else historie).items():
        path = repo / rel
        if not path.is_file():
            # Historie mag weg (git bewaart hem); alleen een lokaal aangepaste historiekopie is drift.
            continue
        found = sha256(path.read_bytes())
        if found != expected:
            errors.append(
                f"{rel} (historie): sha256 {found[:16]}… ≠ vastgezet {expected[:16]}… — een historiekopie wordt "
                f"nooit aangepast; zet hem terug op {BRON_REPO}@{commit[:9]} of verwijder hem"
            )
    return errors


def compare_with_source(
    repo: Path,
    at_commit: Reader,
    current: Reader | None,
    pins: dict[str, str] | None = None,
    historie: dict[str, Reader] | None = None,
) -> tuple[list[str], list[str]]:
    """Kopie ↔ bron op de bron-commit (fout bij verschil) en ↔ huidige bron (alleen waarschuwing).

    `historie`: pad → lezer op de eigen bron-commit van die historiekopie (alleen byte-gelijkheid, geen waarschuwing
    als de bron daarna veranderde: een historiekopie volgt de bron bewust niet)."""
    errors: list[str] = []
    warnings: list[str] = []
    for rel in KOPIEEN if pins is None else pins:
        path = repo / rel
        copy = path.read_bytes() if path.is_file() else None
        source = at_commit(rel)
        if source is None:
            errors.append(f"{rel}: niet gevonden in {BRON_REPO} op {BRON_COMMIT[:9]}")
        elif copy != source:
            errors.append(f"{rel}: kopie is niet byte-gelijk aan {BRON_REPO}@{BRON_COMMIT[:9]}")
        if current is not None:
            latest = current(rel)
            if latest is not None and source is not None and latest != source:
                warnings.append(
                    f"{rel}: de bron is na {BRON_COMMIT[:9]} gewijzigd — nieuwe contractstand overnemen "
                    "(orkestratie: byte-gelijk kopiëren, bron-commit en sha256 in contract_drift.py bijwerken)"
                )
    for rel, read in (historie or {}).items():
        path = repo / rel
        if not path.is_file():
            continue
        source = read(rel)
        commit = HISTORIE.get(rel, ("?", ""))[0]
        if source is None:
            errors.append(f"{rel} (historie): niet gevonden in {BRON_REPO} op {commit[:9]}")
        elif path.read_bytes() != source:
            errors.append(f"{rel} (historie): kopie is niet byte-gelijk aan {BRON_REPO}@{commit[:9]}")
    return errors, warnings


def git_reader(source_repo: Path, ref: str) -> Reader:
    def read(rel: str) -> bytes | None:
        proc = subprocess.run(["git", "-C", str(source_repo), "show", f"{ref}:{rel}"], capture_output=True, check=False)
        return proc.stdout if proc.returncode == 0 else None

    return read


def worktree_reader(source_repo: Path) -> Reader:
    def read(rel: str) -> bytes | None:
        path = source_repo / rel
        return path.read_bytes() if path.is_file() else None

    return read


def http_reader(ref: str, attempts: int = 4) -> Reader:
    def read(rel: str) -> bytes | None:
        url = RAW_URL.format(repo=BRON_REPO, ref=ref, path=rel)
        delay = 2.0
        last = ""
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (vaste https-URL)
                    return resp.read()
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return None
                last = f"HTTP {exc.code}"
            except (urllib.error.URLError, TimeoutError) as exc:
                last = str(exc)
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
        raise OSError(f"{url} niet bereikbaar na {attempts} pogingen ({last})")

    return read


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drifttest van de platformcontract-kopieën (contract 1.3).")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO_ROOT)
    bron = parser.add_mutually_exclusive_group()
    bron.add_argument("--bron-map", type=Path, help="lokale checkout van ai-server-manager (vergelijk met git show)")
    bron.add_argument("--online", action="store_true", help="vergelijk met de publieke bron op GitHub")
    parser.add_argument("--bronbranch", default=BRON_BRANCH, help="branch van de bron voor de driftwaarschuwing")
    parser.add_argument("--github", action="store_true", help="waarschuwingen als ::warning:: voor GitHub Actions")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()

    errors = check_pins(repo)
    warnings: list[str] = []
    try:
        if args.bron_map:
            if not (args.bron_map / ".git").exists():
                print(f"FOUT: {args.bron_map} is geen git-checkout van {BRON_REPO}", file=sys.stderr)
                return 3
            historie = {rel: git_reader(args.bron_map, commit) for rel, (commit, _) in HISTORIE.items()}
            more, warnings = compare_with_source(
                repo, git_reader(args.bron_map, BRON_COMMIT), worktree_reader(args.bron_map), historie=historie
            )
            errors += more
        elif args.online:
            historie = {rel: http_reader(commit) for rel, (commit, _) in HISTORIE.items()}
            more, warnings = compare_with_source(
                repo, http_reader(BRON_COMMIT), http_reader(args.bronbranch), historie=historie
            )
            errors += more
    except OSError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return 3

    for line in warnings:
        print(f"::warning::{line}" if args.github else f"WAARSCHUWING: {line}", file=sys.stderr)
    if errors:
        print(f"CONTRACTKOPIE NIET IN ORDE ({len(errors)} problemen):", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1
    mode = "online tegen GitHub" if args.online else ("tegen de lokale bron" if args.bron_map else "offline, sha256-pin")
    present = [rel for rel in HISTORIE if (repo / rel).is_file()]
    print(
        f"Contractkopieën in orde ({mode}): {len(KOPIEEN)} bestanden byte-gelijk aan {BRON_REPO}@{BRON_COMMIT[:9]}"
        + (f"; historie ongewijzigd: {', '.join(Path(rel).name for rel in present)}" if present else "")
        + "."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
