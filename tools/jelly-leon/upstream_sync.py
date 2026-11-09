#!/usr/bin/env python3
"""Upstream-sync voor de Jelly Leon-fork (ADR-0006, B03-013, EX48).

Subcommando's:
  kies   — bepaal de nieuwste stabiele upstream-tag die nieuwer is dan de basis, per spoor:
             patch     = zelfde major.minor (beveiligings-/bugfixreleases van de huidige reeks)
             nieuwste  = hoogste stabiele tag (kan een grote sprong zijn, bv. 10.11 → 12.x)
  merge  — haal de tag op, maak branch sync/<tag> vanaf de huidige HEAD, merge de tag (--no-ff) en werk
           baseline.json + plugins/Directory.Build.props bij. Een mergeconflict = incompatibel: de merge wordt
           afgebroken, de branch verwijderd en de exitcode is 2 (de workflow faalt; EX48).

Dit script deployt NOOIT iets en pusht niets; pushen/bouwen/testen doet de workflow upstream-sync.yml.
Exitcodes: 0 = ok, 1 = algemene fout, 2 = incompatibel (mergeconflict), 4 = branch bestaat al.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jl_common import (  # noqa: E402
    BASELINE_REL,
    DEFAULT_REPO_ROOT,
    PLUGIN_PROPS_REL,
    ToolError,
    Version,
    load_baseline,
    parse_stable_tag,
    run_git,
    set_plugin_jellyfin_version,
    write_baseline,
)

TRACKS = ("patch", "nieuwste")


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

    original = current_branch(repo)
    run_git(repo, "switch", "-c", branch)
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
        run_git(repo, "merge", "--abort", check=False)
        run_git(repo, "switch", original, check=False)
        run_git(repo, "branch", "-D", branch, check=False)
        detail = ", ".join(conflicts) if conflicts else merge.stderr.strip() or merge.stdout.strip()
        raise ToolError(
            f"INCOMPATIBEL: upstream {tag} kan niet automatisch worden samengevoegd. Conflicten: {detail}. "
            "Werk de betrokken core-patches in docs/platform-v2/PATCHES.md handmatig bij op een aparte branch.",
            exit_code=2,
        )

    version_text = str(target_version)
    baseline.update(
        {
            "upstream_tag": tag,
            "upstream_version": version_text,
            "upstream_commit": upstream_commit,
            "local_upstream_tag": f"upstream-{tag}",
            "fork_version": f"{version_text}-jl.0",
        }
    )
    write_baseline(repo, baseline)
    changed = [BASELINE_REL]
    if set_plugin_jellyfin_version(repo, version_text):
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
    if args.create_local_tag:
        run_git(repo, "tag", f"upstream-{tag}", upstream_commit)

    result = {
        "branch": branch,
        "tag": tag,
        "upstream_commit": upstream_commit,
        "fork_version": f"{version_text}-jl.0",
        "gewijzigd": changed,
        "status": "samengevoegd — nog niet gebouwd/getest",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    write_github_output({"branch": branch, "upstream_commit": upstream_commit})
    return 0


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
    p_merge.set_defaults(func=cmd_merge)
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
