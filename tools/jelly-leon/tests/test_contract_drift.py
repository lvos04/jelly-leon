"""Drifttest van de platformcontract-kopieën (contract 1.3, C1.3-ALG-01/C1.3-JL-01): byte-gelijk aan ai-server-manager op
de bron-commit; de 1.2-conformiteitslijst blijft als ongewijzigde historie staan."""

from __future__ import annotations

import shutil
from pathlib import Path

import contract_drift
from conftest import commit_all, init_repo, write

REPO = Path(__file__).resolve().parents[3]


def test_copies_in_this_repo_match_the_pinned_source_hashes():
    assert contract_drift.check_pins(REPO) == []
    assert contract_drift.main(["--repo", str(REPO)]) == 0


def test_contract_copy_is_version_1_3_on_the_shared_source_commit():
    text = (REPO / "docs/platform-v2/PLATFORM_CONTRACTEN.md").read_text(encoding="utf-8")
    assert text.splitlines()[2].startswith("Versie: `contracts 1.3`")
    conformity = (REPO / "docs/platform-v2/CONTRACT_1.3_CONFORMITEIT.md").read_text(encoding="utf-8")
    assert "## 9. jelly-leon (server-fork)" in conformity
    assert "C1.3-JL-01" in conformity and "C1.3-JL-09" in conformity
    # Zelfde bron-commit als de andere repos (orkestratie C1.3-ALG-01), volledige SHA.
    assert contract_drift.BRON_COMMIT == "02b119cb84be9a307a88532f6692ea8a4bcb12f1"
    assert set(contract_drift.KOPIEEN) == {
        "docs/platform-v2/PLATFORM_CONTRACTEN.md",
        "docs/platform-v2/CONTRACT_1.3_CONFORMITEIT.md",
    }


def test_conformity_1_2_is_pinned_history_only():
    assert set(contract_drift.HISTORIE) == {"docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md"}
    commit, _ = contract_drift.HISTORIE["docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md"]
    assert commit != contract_drift.BRON_COMMIT and len(commit) == 40


def _copy_repo(tmp_path: Path) -> Path:
    target = tmp_path / "kopie"
    for rel in [*contract_drift.KOPIEEN, *contract_drift.HISTORIE]:
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
    (repo / "docs/platform-v2/CONTRACT_1.3_CONFORMITEIT.md").unlink()
    assert any("ontbreekt" in e for e in contract_drift.check_pins(repo))


def test_whitespace_only_change_is_still_drift(tmp_path):
    """Byte-gelijk betekent ook regeleinden en witruimte (geen 'inhoudelijk gelijk')."""
    repo = _copy_repo(tmp_path)
    path = repo / "docs/platform-v2/CONTRACT_1.3_CONFORMITEIT.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n", 1))
    assert contract_drift.check_pins(repo)


def test_old_version_header_is_reported(tmp_path):
    """Een kopie die (byte-gelijk) een andere versie is, valt op de versiekop: deze repo volgt 1.3."""
    repo = _copy_repo(tmp_path)
    path = repo / "docs/platform-v2/PLATFORM_CONTRACTEN.md"
    data = path.read_bytes().replace(b"Versie: `contracts 1.3`", b"Versie: `contracts 1.2`", 1)
    path.write_bytes(data)
    pins = {**contract_drift.KOPIEEN, "docs/platform-v2/PLATFORM_CONTRACTEN.md": contract_drift.sha256(data)}
    errors = contract_drift.check_pins(repo, pins)
    assert errors == ["docs/platform-v2/PLATFORM_CONTRACTEN.md: versiekop Versie: `contracts 1.3` ontbreekt"]


def test_local_edit_of_the_history_copy_is_drift(tmp_path):
    repo = _copy_repo(tmp_path)
    path = repo / "docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md"
    path.write_bytes(path.read_bytes() + b"\nlokale aantekening\n")
    errors = contract_drift.check_pins(repo)
    assert len(errors) == 1 and "(historie)" in errors[0] and "nooit aangepast" in errors[0]
    assert contract_drift.main(["--repo", str(repo)]) == 1


def test_removed_history_copy_is_allowed(tmp_path):
    repo = _copy_repo(tmp_path)
    (repo / "docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md").unlink()
    assert contract_drift.check_pins(repo) == []


def test_history_is_compared_with_its_own_source_commit(tmp_path):
    repo = _copy_repo(tmp_path)
    rel = "docs/platform-v2/CONTRACT_1.2_CONFORMITEIT.md"
    originals = {r: (REPO / r).read_bytes() for r in contract_drift.KOPIEEN}
    same = {rel: (REPO / rel).read_bytes()}
    errors, warnings = contract_drift.compare_with_source(repo, originals.get, None, historie={rel: same.get})
    assert errors == [] and warnings == []
    other = {rel: b"andere stand"}
    errors, _ = contract_drift.compare_with_source(repo, originals.get, None, historie={rel: other.get})
    assert errors == [f"{rel} (historie): kopie is niet byte-gelijk aan lvos04/ai-server-manager@8b54f3940"]


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
