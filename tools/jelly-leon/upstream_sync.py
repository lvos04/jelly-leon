#!/usr/bin/env python3
"""Upstream-sync voor de Jelly Leon-fork (ADR-0006, B03-013, EX48).

Subcommando's:
  kies   — bepaal de nieuwste stabiele upstream-tag die nieuwer is dan de basis, per spoor:
             patch     = zelfde major.minor (beveiligings-/bugfixreleases van de huidige reeks)
             nieuwste  = hoogste stabiele tag (kan een grote sprong zijn, bv. 10.11 → 12.x)
  merge  — haal de tag op en maak branch sync/<tag>, dan per methode:
             merge     = `git merge --no-ff` van de tag in de huidige HEAD (standaard binnen dezelfde reeks);
             herbasis  = de fork opnieuw verankeren op de tag: boom = upstream-tag + fork-eigen paden + de
                         geregistreerde core-patches (3-way), vastgelegd als merge-commit met beide ouders
                         (standaard bij een andere major.minor: upstream-releasereeksen lopen uiteen, zodat een
                         gewone merge conflicten geeft in bestanden die de fork nooit wijzigde);
             auto      = merge bij dezelfde major.minor, anders herbasis.
           Daarna baseline.json (incl. dotnet_sdk_major uit de global.json van de nieuwe basis) +
           plugins/Directory.Build.props (JellyfinVersion en TargetFramework van de nieuwe upstream-ABI) bijwerken.
           Een conflict = incompatibel: alles wordt teruggedraaid, de branch verwijderd en de exitcode is 2
           (de workflow faalt; EX48). Bij herbasis wordt elke geregistreerde core-patch LOS toegepast en per patch
           gerapporteerd (schoon/conflict + bestanden; B03-019 (d), JLT-67).
           Met --handmatig-oplossen blijft bij een patchconflict de branch sync/<tag> staan met conflictmarkeringen
           (exitcode 2 blijft); de bouwer lost de conflicten op, registreert dat in PATCHES.md en rondt af met
  voltooi — herbasis afronden na handmatig oplossen: geen onopgeloste bestanden of conflictmarkeringen meer, dan de
           herbasis-commit (2 ouders) + baseline/plugin-props zoals bij een schone merge.

Dit script deployt NOOIT iets en pusht niets; pushen/bouwen/testen doet de workflow upstream-sync.yml.
Exitcodes: 0 = ok, 1 = algemene fout, 2 = incompatibel (mergeconflict), 4 = branch bestaat al.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jl_common import (  # noqa: E402
    BASELINE_REL,
    DEFAULT_REPO_ROOT,
    PATCHES_REL,
    PLUGIN_PROPS_REL,
    ToolError,
    Version,
    load_baseline,
    load_fork_paths,
    parse_stable_tag,
    read_global_json_sdk,
    read_upstream_target_framework,
    run_git,
    sdk_major_minor,
    set_plugin_jellyfin_version,
    set_plugin_target_framework,
    write_baseline,
)
from patch_register_check import ACTIVE_STATUSES, parse_register  # noqa: E402

TRACKS = ("patch", "nieuwste")
METHODS = ("auto", "merge", "herbasis")
# Toestand van een herbasis die wacht op handmatig oplossen (in .git, nooit gecommit).
STATE_REL = "jelly-leon-sync.json"
CONFLICT_MARKER_RE = re.compile(r"^(<{7}|>{7})( |$)", re.MULTILINE)


def parse_ls_remote(output: str) -> dict[str, str]:
    """Zet `git ls-remote --tags`-uitvoer om naar {tag: commit}; geannoteerde tags via ^{}."""
    direct: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 2 or not parts[1].startswith("refs/tags/"):
            continue
        sha, ref = parts
        name = ref[len("refs/tags/"):]
        if name.endswith("^{}"):
            peeled[name[:-3]] = sha
        else:
            direct[name] = sha
    direct.update(peeled)
    return direct


def stable_tags(tags: dict[str, str]) -> list[tuple[Version, str]]:
    result = []
    for name in tags:
        version = parse_stable_tag(name)
        if version is not None:
            result.append((version, name))
    result.sort()
    return result


def choose(tags: dict[str, str], current: Version, track: str) -> tuple[str | None, list[str]]:
    """Geeft (kandidaat-tag of None, alle nieuwere stabiele tags in dit spoor)."""
    if track not in TRACKS:
        raise ToolError(f"onbekend spoor '{track}' (kies uit: {', '.join(TRACKS)})")
    newer = []
    for version, name in stable_tags(tags):
        if version <= current:
            continue
        if track == "patch" and (version.major, version.minor) != (current.major, current.minor):
            continue
        newer.append(name)
    return (newer[-1] if newer else None), newer


def remote_tags(repo: Path, source: str) -> dict[str, str]:
    proc = run_git(repo, "ls-remote", "--tags", source)
    return parse_ls_remote(proc.stdout)


def write_github_output(values: dict[str, str]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def cmd_choose(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    baseline = load_baseline(repo)
    current = Version.parse(baseline["upstream_version"])
    if args.tags_file:
        tags = parse_ls_remote(Path(args.tags_file).read_text(encoding="utf-8"))
    else:
        tags = remote_tags(repo, args.source)
    result: dict[str, object] = {"huidige_basis": baseline["upstream_tag"]}
    for track in args.track:
        candidate, newer = choose(tags, current, track)
        result[track] = {"kandidaat": candidate, "nieuwere_stabiele_tags": newer}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    outputs = {}
    candidates = sorted({r["kandidaat"] for k, r in result.items() if k in TRACKS and r["kandidaat"]})
    outputs["kandidaten"] = json.dumps(candidates)
    outputs["heeft_kandidaat"] = "true" if candidates else "false"
    write_github_output(outputs)
    return 0


def ensure_clean(repo: Path) -> None:
    status = run_git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if status:
        raise ToolError("werkboom is niet schoon; commit of stash eerst je wijzigingen")


def current_branch(repo: Path) -> str:
    return run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def abort_sync(repo: Path, branch: str, original: str) -> None:
    """Zet alles terug: geen half samengevoegde boom, geen achtergebleven sync-branch."""
    run_git(repo, "merge", "--abort", check=False)
    run_git(repo, "reset", "-q", "--hard", check=False)
    run_git(repo, "switch", "-q", original, check=False)
    run_git(repo, "branch", "-D", branch, check=False)


def incompatible(tag: str, method: str, conflicts: list[str], fallback: str) -> ToolError:
    detail = ", ".join(conflicts) if conflicts else fallback
    return ToolError(
        f"INCOMPATIBEL ({method}): upstream {tag} kan niet automatisch worden overgenomen. "
        f"Conflicten ({len(conflicts)}): {detail}. Werk de betrokken core-patches in {PATCHES_REL} "
        "handmatig bij op een aparte branch.",
        exit_code=2,
    )


def do_merge(repo: Path, branch: str, tag: str, upstream_commit: str, original: str) -> None:
    run_git(repo, "switch", "-q", "-c", branch)
    merge = run_git(
        repo,
        "merge",
        "--no-ff",
        "--no-edit",
        "-m",
        f"Sync: upstream {tag} samengevoegd in {branch}",
        upstream_commit,
        check=False,
    )
    if merge.returncode != 0:
        conflicts = run_git(repo, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
        abort_sync(repo, branch, original)
        raise incompatible(tag, "merge", conflicts, merge.stderr.strip() or merge.stdout.strip())


def state_path(repo: Path) -> Path:
    git_dir = Path(run_git(repo, "rev-parse", "--git-dir").stdout.strip())
    return (git_dir if git_dir.is_absolute() else repo / git_dir) / STATE_REL


def apply_patches_separately(
    repo: Path, old_base: str, fork_head: str, patches: list
) -> list[dict[str, object]]:
    """Past elke geregistreerde core-patch los toe (3-way) en geeft per patch het resultaat (B03-019 (d))."""
    results: list[dict[str, object]] = []
    for patch in patches:
        diff = run_git(repo, "diff", "--binary", old_base, fork_head, "--", *patch.files).stdout
        if not diff.strip():
            results.append({"patch": patch.patch_id, "resultaat": "geen_wijziging", "bestanden": patch.files})
            continue
        applied = run_git(repo, "apply", "--3way", "--whitespace=nowarn", "-", check=False, input_text=diff)
        unmerged = set(run_git(repo, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split())
        conflicts = sorted(f for f in patch.files if f in unmerged)
        if applied.returncode == 0 and not conflicts:
            results.append({"patch": patch.patch_id, "resultaat": "schoon", "bestanden": patch.files})
        else:
            results.append(
                {
                    "patch": patch.patch_id,
                    "resultaat": "conflict",
                    "bestanden": patch.files,
                    "conflicten": conflicts or patch.files,
                    "melding": applied.stderr.strip()[-2000:],
                }
            )
    return results


def do_rebase_anchor(
    repo: Path,
    branch: str,
    tag: str,
    old_base: str,
    fork_head: str,
    upstream_commit: str,
    original: str,
    *,
    manual: bool = False,
    state: dict | None = None,
) -> list[dict[str, object]]:
    """Herbasis: upstream-tag + fork-eigen paden + geregistreerde core-patches, als merge-commit (2 ouders)."""
    fork_paths = load_fork_paths(repo)
    register = (repo / PATCHES_REL).read_text(encoding="utf-8") if (repo / PATCHES_REL).is_file() else ""
    active = [p for p in parse_register(register) if p.status in ACTIVE_STATUSES and p.files]
    run_git(repo, "switch", "-q", "-c", branch, upstream_commit)
    try:
        for entry in fork_paths:
            path = entry.rstrip("/")
            if run_git(repo, "cat-file", "-e", f"{fork_head}:{path}", check=False).returncode == 0:
                run_git(repo, "checkout", fork_head, "--", path)
        results = apply_patches_separately(repo, old_base, fork_head, active)
        conflicted = [r for r in results if r["resultaat"] == "conflict"]
        if conflicted:
            files = sorted({f for r in conflicted for f in r["conflicten"]})  # type: ignore[union-attr]
            status = "wacht_op_handmatig_oplossen" if manual else "incompatibel_teruggedraaid"
            print(json.dumps({"status": status, "tag": tag, "patches": results}, indent=2, ensure_ascii=False))
            if manual and state is not None:
                state.update({"branch": branch, "patches": results})
                state_path(repo).write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                raise ToolError(
                    f"INCOMPATIBEL (herbasis): {len(conflicted)} core-patch(es) met conflict in {', '.join(files)}. "
                    f"Branch {branch} blijft staan met conflictmarkeringen: los ze op, werk {PATCHES_REL} bij, "
                    "'git add' de bestanden en rond af met: upstream_sync.py voltooi",
                    exit_code=2,
                )
            raise incompatible(tag, "herbasis", files, "; ".join(str(r.get("melding", "")) for r in conflicted))
        commit_anchor(repo, tag, fork_head, upstream_commit)
        return results
    except ToolError as exc:
        if not (manual and exc.exit_code == 2 and state_path(repo).is_file()):
            abort_sync(repo, branch, original)
        raise


def commit_anchor(repo: Path, tag: str, fork_head: str, upstream_commit: str) -> None:
    run_git(repo, "add", "-A")
    tree = run_git(repo, "write-tree").stdout.strip()
    message = (
        f"Sync: fork opnieuw verankerd op upstream {tag} (herbasis)\n\n"
        "Boom = upstream-tag + fork-eigen paden (tools/jelly-leon/fork_paths.txt) + geregistreerde core-patches\n"
        f"({PATCHES_REL}). Ouders: vorige forkstand en de upstream-tag. Nooit automatisch naar productie."
    )
    commit = run_git(repo, "commit-tree", tree, "-p", fork_head, "-p", upstream_commit, "-m", message).stdout.strip()
    run_git(repo, "reset", "-q", "--hard", commit)


def finish_baseline(
    repo: Path, baseline: dict, tag: str, upstream_commit: str, *, create_local_tag: bool, tag_exists: bool
) -> list[str]:
    target_version = parse_stable_tag(tag)
    assert target_version is not None
    local_tag = f"upstream-{tag}"
    version_text = str(target_version)
    baseline.update(
        {
            "upstream_tag": tag,
            "upstream_version": version_text,
            "upstream_commit": upstream_commit,
            "local_upstream_tag": local_tag,
            "fork_version": f"{version_text}-jl.0",
        }
    )
    # SDK-reeks van de nieuwe basis (global.json is upstream-eigendom; CI leidt er het kanaal x.y.x uit af).
    new_sdk = read_global_json_sdk(repo)
    if new_sdk is not None:
        baseline["dotnet_sdk_major"] = sdk_major_minor(new_sdk)
    write_baseline(repo, baseline)
    changed = [BASELINE_REL]
    plugin_changed = set_plugin_jellyfin_version(repo, version_text)
    upstream_tf = read_upstream_target_framework(repo)
    if upstream_tf:
        plugin_changed = set_plugin_target_framework(repo, upstream_tf) or plugin_changed
    if plugin_changed:
        changed.append(PLUGIN_PROPS_REL)
    run_git(repo, "add", *changed)
    run_git(
        repo,
        "commit",
        "-m",
        f"Sync: basis bijgewerkt naar upstream {tag} (forkversie {version_text}-jl.0)\n\n"
        "Automatisch door tools/jelly-leon/upstream_sync.py. Nooit automatisch naar productie;\n"
        "eerst bouwen, testen en handmatig beoordelen (ADR-0006).",
    )
    if create_local_tag and not tag_exists:
        run_git(repo, "tag", local_tag, upstream_commit)
    return changed


def cmd_merge(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    tag = args.tag
    target_version = parse_stable_tag(tag)
    if target_version is None:
        raise ToolError(f"'{tag}' is geen stabiele upstream-tag (rc/beta worden nooit gesynchroniseerd)")
    baseline = load_baseline(repo)
    current_version = Version.parse(baseline["upstream_version"])
    if target_version <= current_version:
        raise ToolError(f"{tag} ({target_version}) is niet nieuwer dan de basis {current_version}; geen downgrade")
    ensure_clean(repo)

    branch = args.branch or f"sync/{tag}"
    if run_git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0:
        raise ToolError(f"branch {branch} bestaat al; verwijder of hergebruik hem bewust", exit_code=4)

    sync_ref = f"refs/upstream-sync/{tag}"
    if not args.no_fetch:
        run_git(repo, "fetch", "--no-tags", args.source, f"+refs/tags/{tag}:{sync_ref}")
    commit_proc = run_git(repo, "rev-parse", "--verify", f"{sync_ref}^{{commit}}", check=False)
    if commit_proc.returncode != 0:
        raise ToolError(f"tag {tag} niet gevonden (ref {sync_ref}); fetch mislukt of tag bestaat niet")
    upstream_commit = commit_proc.stdout.strip()

    # Lokale upstream-tag mag al bestaan (bv. eerder gepusht door de sync-workflow), maar alleen op dezelfde commit.
    local_tag = f"upstream-{tag}"
    existing_tag = run_git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{local_tag}^{{commit}}", check=False)
    tag_exists = existing_tag.returncode == 0
    if args.create_local_tag and tag_exists and existing_tag.stdout.strip() != upstream_commit:
        raise ToolError(
            f"lokale tag {local_tag} wijst naar {existing_tag.stdout.strip()[:12]}, maar upstream {tag} is "
            f"{upstream_commit[:12]}; upstream-tag verplaatst? Eerst handmatig onderzoeken (niets gewijzigd)."
        )

    method = args.method
    if method == "auto":
        same_line = (target_version.major, target_version.minor) == (current_version.major, current_version.minor)
        method = "merge" if same_line else "herbasis"

    original = current_branch(repo)
    fork_head = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    patch_results: list[dict[str, object]] = []
    if method == "merge":
        do_merge(repo, branch, tag, upstream_commit, original)
    else:
        if state_path(repo).is_file():
            raise ToolError(f"er wacht al een herbasis op handmatig oplossen ({state_path(repo)}); eerst 'voltooi'")
        state = {
            "tag": tag,
            "upstream_commit": upstream_commit,
            "fork_head": fork_head,
            "old_base": baseline["upstream_commit"],
            "original": original,
            "create_local_tag": bool(args.create_local_tag),
            "tag_exists": tag_exists,
        }
        patch_results = do_rebase_anchor(
            repo, branch, tag, baseline["upstream_commit"], fork_head, upstream_commit, original,
            manual=bool(getattr(args, "manual", False)), state=state,
        )

    changed = finish_baseline(
        repo, baseline, tag, upstream_commit, create_local_tag=args.create_local_tag, tag_exists=tag_exists
    )
    return report(branch, tag, method, upstream_commit, changed, patch_results)


def report(
    branch: str, tag: str, method: str, upstream_commit: str, changed: list[str], patches: list[dict[str, object]]
) -> int:
    version = parse_stable_tag(tag)
    result = {
        "branch": branch,
        "tag": tag,
        "methode": method,
        "upstream_commit": upstream_commit,
        "fork_version": f"{version}-jl.0",
        "gewijzigd": changed,
        "patches": patches,
        "status": "samengevoegd — nog niet gebouwd/getest",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    write_github_output({"branch": branch, "upstream_commit": upstream_commit})
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    """Rondt een herbasis af na handmatig oplossen van patchconflicten (zelfde eindstand als een schone herbasis)."""
    repo = args.repo.resolve()
    path = state_path(repo)
    if not path.is_file():
        raise ToolError("geen herbasis die wacht op handmatig oplossen (start met merge --handmatig-oplossen)")
    state = json.loads(path.read_text(encoding="utf-8"))
    if current_branch(repo) != state["branch"]:
        raise ToolError(f"verwacht branch {state['branch']}, maar HEAD staat op {current_branch(repo)}")
    unmerged = run_git(repo, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
    if unmerged:
        raise ToolError(f"nog onopgeloste bestanden (git add na oplossen): {', '.join(unmerged)}")
    files = sorted({f for r in state.get("patches", []) for f in r.get("bestanden", [])})
    with_markers = [
        f for f in files if (repo / f).is_file() and CONFLICT_MARKER_RE.search((repo / f).read_text(errors="replace"))
    ]
    if with_markers:
        raise ToolError(f"conflictmarkeringen staan nog in: {', '.join(with_markers)}")
    commit_anchor(repo, state["tag"], state["fork_head"], state["upstream_commit"])
    baseline = load_baseline(repo)
    # De baseline in de boom is die van de vorige forkstand (fork-eigen pad); de oude basis moet kloppen.
    if baseline["upstream_commit"] != state["old_base"]:
        raise ToolError("baseline.json is tijdens het oplossen gewijzigd; laat die aan de tool over")
    changed = finish_baseline(
        repo, baseline, state["tag"], state["upstream_commit"],
        create_local_tag=state["create_local_tag"], tag_exists=state["tag_exists"],
    )
    for r in state.get("patches", []):
        if r.get("resultaat") == "conflict":
            r["resultaat"] = "conflict_handmatig_opgelost"
    path.unlink()
    return report(state["branch"], state["tag"], "herbasis", state["upstream_commit"], changed, state.get("patches", []))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upstream-sync voor Jelly Leon (nooit automatisch naar productie).")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    p_choose = sub.add_parser("kies", help="bepaal kandidaat-tags per spoor")
    p_choose.add_argument("--spoor", dest="track", action="append", choices=TRACKS)
    p_choose.add_argument("--bron", dest="source", default="https://github.com/jellyfin/jellyfin.git")
    p_choose.add_argument("--tags-bestand", dest="tags_file", help="uitvoer van git ls-remote --tags (tests/offline)")
    p_choose.set_defaults(func=cmd_choose)

    p_merge = sub.add_parser("merge", help="merge een upstream-tag in branch sync/<tag>")
    p_merge.add_argument("--tag", required=True)
    p_merge.add_argument("--bron", dest="source", default="https://github.com/jellyfin/jellyfin.git")
    p_merge.add_argument("--branch")
    p_merge.add_argument("--geen-fetch", dest="no_fetch", action="store_true", help="ref al aanwezig (tests)")
    p_merge.add_argument("--maak-lokale-tag", dest="create_local_tag", action="store_true")
    p_merge.add_argument("--methode", dest="method", choices=METHODS, default="auto")
    p_merge.add_argument(
        "--handmatig-oplossen",
        dest="manual",
        action="store_true",
        help="herbasis: bij een patchconflict de branch met conflictmarkeringen laten staan (exitcode blijft 2)",
    )
    p_merge.set_defaults(func=cmd_merge)

    p_finish = sub.add_parser("voltooi", help="herbasis afronden na handmatig oplossen van patchconflicten")
    p_finish.set_defaults(func=cmd_finish)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "track", None) is None and args.command == "kies":
        args.track = list(TRACKS)
    try:
        return args.func(args)
    except ToolError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
