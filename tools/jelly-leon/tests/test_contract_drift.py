"""Drifttest van de platformcontract-kopieën (contract 1.2, A1): byte-gelijk aan ai-server-manager op de bron-commit."""

from __future__ import annotations

import shutil
from pathlib import Path

import contract_drift
from conftest import commit_all, init_repo, write

REPO = Path(__file__).resolve().parents[3]


def test_copies_in_this_repo_match_the_pinned_source_hashes():
    assert contract_drift.check_pins(REPO) == []
    assert contract_drift.main(["--repo", str(REPO)]) == 0


def test_contract_copy_is_version_1_2():
    text = (REPO / "docs/platform-v2/PLATFORM_CONTRACTEN.md").read_text(encoding="utf-8")
    assert text.splitlines()[2].startswith("Versie: `contracts 1.2`")
    conformity = (REPO / "docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md").read_text(encoding="utf-8")
    assert "## 9. jelly-leon (server-fork)" in conformity


def _copy_repo(tmp_path: Path) -> Path:
    target = tmp_path / "kopie"
    for rel in contract_drift.KOPIEEN:
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target / rel)
    return target


def test_local_edit_of_a_copy_is_drift(tmp_path):
    repo = _copy_repo(tmp_path)
    path = repo / "docs/platform-v2/PLATFORM_CONTRACTEN.md"
    path.write_bytes(path.read_bytes().replace(b"Custom App", b"Custom app", 1))
    errors = contract_drift.check_pins(repo)
    assert len(errors) == 1 and "is gewijzigd" in errors[0]
    assert contract_drift.main(["--repo", str(repo)]) == 1


def test_missing_copy_is_an_error(tmp_path):
    repo = _copy_repo(tmp_path)
    (repo / "docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md").unlink()
    assert any("ontbreekt" in e for e in contract_drift.check_pins(repo))


def test_whitespace_only_change_is_still_drift(tmp_path):
    """Byte-gelijk betekent ook regeleinden en witruimte (geen 'inhoudelijk gelijk')."""
    repo = _copy_repo(tmp_path)
    path = repo / "docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n", 1))
    assert contract_drift.check_pins(repo)


def test_compare_with_source_reports_moved_source_as_warning_only(tmp_path):
    repo = _copy_repo(tmp_path)
    originals = {rel: (REPO / rel).read_bytes() for rel in contract_drift.KOPIEEN}
    moved = dict(originals)
    moved["docs/platform-v2/PLATFORM_CONTRACTEN.md"] += b"\n## 14. Nieuw\n"
    errors, warnings = contract_drift.compare_with_source(repo, originals.get, moved.get)
    assert errors == []
    assert len(warnings) == 1 and "gewijzigd" in warnings[0]


def test_compare_with_source_fails_when_copy_differs_from_pinned_commit(tmp_path):
    repo = _copy_repo(tmp_path)
    source = {rel: (REPO / rel).read_bytes() + b"x" for rel in contract_drift.KOPIEEN}
    errors, _ = contract_drift.compare_with_source(repo, source.get, None)
    assert len(errors) == 2 and all("niet byte-gelijk" in e for e in errors)


def test_git_reader_reads_the_file_at_a_commit(tmp_path):
    source = init_repo(tmp_path / "bron")
    write(source, "docs/platform-v2/PLATFORM_CONTRACTEN.md", "versie A\n")
    commit = commit_all(source, "A")
    write(source, "docs/platform-v2/PLATFORM_CONTRACTEN.md", "versie B\n")
    commit_all(source, "B")
    read = contract_drift.git_reader(source, commit)
    assert read("docs/platform-v2/PLATFORM_CONTRACTEN.md") == b"versie A\n"
    assert read("docs/platform-v2/BESTAAT_NIET.md") is None
    assert contract_drift.worktree_reader(source)("docs/platform-v2/PLATFORM_CONTRACTEN.md") == b"versie B\n"


def test_bron_map_must_be_a_git_checkout(tmp_path):
    assert contract_drift.main(["--repo", str(REPO), "--bron-map", str(tmp_path)]) == 3
