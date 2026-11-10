"""upstream_gedrag_check.py (B03-019 a): register van upstream-gedrag met sync-blokkerende ankers en runtime-tests."""

from __future__ import annotations

from pathlib import Path

import upstream_gedrag_check as ug

HEAD = "| ID | Gedrag | Bestand | Anker | Gebruikt door | Test |\n|---|---|---|---|---|---|\n"
ROW1 = "| UG-GEM-1 | legacy uit | `src/Auth.cs` | `EnableLegacy = false;` | BG-01 | anker + runtime:legacy_auth_uit |\n"
ROW2 = "| UG-GEM-2 | plugins apart | `src/Plugins.cs` | `new PluginLoadContext\\(` | B03-017 | anker |\n"


def make_repo(tmp_path: Path, rows: str = ROW1 + ROW2) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs/platform-v2").mkdir(parents=True)
    (repo / "tools/jelly-leon").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "tools/jelly-leon/fork_paths.txt").write_text("docs/platform-v2/\ntools/jelly-leon/\n", encoding="utf-8")
    (repo / "src/Auth.cs").write_text("class A { void M() { EnableLegacy = false; } }\n", encoding="utf-8")
    (repo / "src/Plugins.cs").write_text("var c = new PluginLoadContext(path);\n", encoding="utf-8")
    (repo / ug.REGISTER_REL).write_text("# Register\n\n" + HEAD + rows, encoding="utf-8")
    return repo


KNOWN = {"legacy_auth_uit"}


def test_register_ok(tmp_path: Path) -> None:
    entries, errors = ug.check(make_repo(tmp_path), KNOWN)
    assert errors == [] and [e.entry_id for e in entries] == ["UG-GEM-1", "UG-GEM-2"]
    assert entries[0].tests == ("anker", "runtime:legacy_auth_uit")


def test_changed_upstream_behaviour_blocks(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src/Auth.cs").write_text("class A { void M() { EnableLegacy = true; } }\n", encoding="utf-8")
    (repo / "src/Plugins.cs").unlink()
    _, errors = ug.check(repo, KNOWN)
    assert any("UG-GEM-1: anker niet gevonden" in e for e in errors)
    assert any("UG-GEM-2: src/Plugins.cs bestaat niet" in e for e in errors)


def test_unknown_runtime_test_and_missing_test_fail(tmp_path: Path) -> None:
    rows = ROW1.replace("runtime:legacy_auth_uit", "runtime:bestaat_niet") + ROW2.replace("| anker |", "| — |")
    _, errors = ug.check(make_repo(tmp_path, rows), KNOWN)
    assert any("onbekende runtime-test runtime:bestaat_niet" in e for e in errors)
    assert any("UG-GEM-2: gedrag, 'gebruikt door' en een test" in e for e in errors)


def test_numbering_duplicates_and_fork_paths(tmp_path: Path) -> None:
    rows = ROW1 + ROW1 + ROW2.replace("UG-GEM-2", "UG-GEM-4").replace("`src/Plugins.cs`", "`tools/jelly-leon/x.py`")
    _, errors = ug.check(make_repo(tmp_path, rows), KNOWN)
    assert any("dubbele ID's: UG-GEM-1" in e for e in errors)
    assert any("niet doorlopend" in e for e in errors)
    assert any("fork-eigen pad" in e for e in errors)


def test_reference_without_register_entry_fails_but_plan_copies_do_not(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "docs/platform-v2/02_BOUWPLANNEN").mkdir()
    (repo / "docs/platform-v2/02_BOUWPLANNEN/B03.md").write_text("gepland: UG-F2-1 en UG-F5-13\n", encoding="utf-8")
    (repo / "docs/platform-v2/UPSTREAM_GEDRAG_WEB.md").write_text("zie UG-WEB-3 (webregister)\n", encoding="utf-8")
    assert ug.check(repo, KNOWN)[1] == []
    (repo / "tools/jelly-leon/module.py").write_text("# steunt op UG-GEM-7\n", encoding="utf-8")
    _, errors = ug.check(repo, KNOWN)
    assert errors == ["tools/jelly-leon/module.py:1: verwijst naar UG-GEM-7, dat niet in docs/platform-v2/UPSTREAM_GEDRAG.md staat"]


def test_real_register_is_consistent_with_runtime_runner() -> None:
    entries, errors = ug.check(ug.DEFAULT_REPO_ROOT)
    assert errors == []
    runtime = {t.removeprefix("runtime:") for e in entries for t in e.tests if t.startswith("runtime:")}
    assert runtime == ug.runtime_checks()  # elke runtime-test hoort bij een regel en omgekeerd
