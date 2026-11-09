#!/usr/bin/env python3
"""Bron van de web-client in de image: welke commit van `lvos04/jelly-leon-web` en klopt die bij de server-basis.

`tools/jelly-leon/baseline.json` legt naast de serverbasis vast:
  - `web_repo`, `web_upstream_tag`, `web_upstream_commit`: de upstream-basis van de web-fork;
  - `web_fork_commit`: de commit van `jelly-leon-web` waaruit de image de web-client bouwt (CI-job `image`, en
    lokaal via `git archive`). Vast op een volledige SHA: reproduceerbaar en herkomst (GPL "bron beschikbaar").

Gebruik:
  web_bron.py --commit [--github-output]   geeft `web_fork_commit` (en `commit=`/`repo=` in $GITHUB_OUTPUT)
  web_bron.py --controleer <checkout>      controleert een checkout van jelly-leon-web (volledige historie nodig;
                                           blob:none volstaat): HEAD == web_fork_commit, package.json heet
                                           `jellyfin-web` (technische identiteit) met versie == upstream_version van
                                           de server, web_upstream_tag hoort bij die versie en web_upstream_commit is
                                           een voorouder van HEAD (de fork staat echt op die basis).

Na een upstream-sync of de 12.x-upgrade (ADR-0011) faalt `--controleer` tot `web_fork_commit` naar een web-commit
op dezelfde versie wijst — bewust: server en web-client komen altijd uit dezelfde release.
Alleen standaardbibliotheek. Exitcodes: 0 = in orde, 1 = afwijking, 3 = gebruiks-/omgevingsfout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jl_common import DEFAULT_REPO_ROOT, ToolError, Version, load_baseline, parse_stable_tag, run_git  # noqa: E402

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
WEB_REPO_RE = re.compile(r"^https://github\.com/([A-Za-z0-9-]+/[A-Za-z0-9._-]+?)(?:\.git)?$")


def web_fields(baseline: dict) -> tuple[list[str], dict[str, str]]:
    errors: list[str] = []
    fields = {key: str(baseline.get(key) or "") for key in ("web_repo", "web_upstream_tag", "web_upstream_commit", "web_fork_commit")}
    for key in ("web_upstream_commit", "web_fork_commit"):
        if not SHA_RE.match(fields[key]):
            errors.append(f"baseline.{key} moet een volledige commit-SHA zijn (40 hex), niet {fields[key]!r}")
    if not WEB_REPO_RE.match(fields["web_repo"]):
        errors.append(f"baseline.web_repo {fields['web_repo']!r} is geen https://github.com/<eigenaar>/<repo>")
    tag_version = parse_stable_tag(fields["web_upstream_tag"])
    if tag_version is None:
        errors.append(f"baseline.web_upstream_tag {fields['web_upstream_tag']!r} is geen stabiele upstream-tag")
    elif tag_version != Version.parse(baseline["upstream_version"]):
        errors.append(
            f"baseline.web_upstream_tag {fields['web_upstream_tag']} hoort bij {tag_version}, de server-basis is "
            f"{baseline['upstream_version']}: server en web-client komen uit dezelfde release"
        )
    return errors, fields


def check_checkout(checkout: Path, baseline: dict) -> list[str]:
    errors, fields = web_fields(baseline)
    if errors:
        return errors
    head = run_git(checkout, "rev-parse", "HEAD", check=False)
    if head.returncode != 0:
        return [f"{checkout} is geen git-checkout van {fields['web_repo']}"]
    if head.stdout.strip() != fields["web_fork_commit"]:
        errors.append(f"checkout staat op {head.stdout.strip()[:12]}, baseline.web_fork_commit is {fields['web_fork_commit'][:12]}")
    try:
        package = json.loads((checkout / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [*errors, f"package.json van de web-client onleesbaar: {exc}"]
    if package.get("name") != "jellyfin-web":
        errors.append(f"package.json name {package.get('name')!r}: technische identiteit moet 'jellyfin-web' blijven (ADR-0003)")
    try:
        web_version = Version.parse(str(package.get("version", "")))
    except ToolError:
        errors.append(f"package.json version {package.get('version')!r} is geen versie")
    else:
        if web_version != Version.parse(baseline["upstream_version"]):
            errors.append(
                f"web-client is versie {web_version}, de server-basis {baseline['upstream_version']}: zet "
                "baseline.web_fork_commit op een jelly-leon-web-commit van dezelfde release"
            )
    base = fields["web_upstream_commit"]
    if run_git(checkout, "cat-file", "-e", f"{base}^{{commit}}", check=False).returncode != 0:
        errors.append(f"web_upstream_commit {base[:12]} niet in de checkout (volledige historie nodig, blob:none volstaat)")
    elif run_git(checkout, "merge-base", "--is-ancestor", base, "HEAD", check=False).returncode != 0:
        errors.append(f"web_upstream_commit {base[:12]} ({fields['web_upstream_tag']}) is geen voorouder van de web-fork-commit")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bron van de web-client in de Jelly Leon-image.")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO_ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--commit", action="store_true", help="geef web_fork_commit uit baseline.json")
    mode.add_argument("--controleer", type=Path, metavar="CHECKOUT", help="controleer een checkout van jelly-leon-web")
    parser.add_argument("--github-output", action="store_true", help="schrijf commit= en repo= naar $GITHUB_OUTPUT")
    args = parser.parse_args(argv)
    try:
        baseline = load_baseline(args.repo.resolve())
    except ToolError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return 3
    if args.commit:
        errors, fields = web_fields(baseline)
        if errors:
            print("WEB-BRON NIET IN ORDE:\n  - " + "\n  - ".join(errors), file=sys.stderr)
            return 1
        if args.github_output:
            output = os.environ.get("GITHUB_OUTPUT")
            if not output:
                print("FOUT: --github-output gevraagd maar GITHUB_OUTPUT is niet gezet", file=sys.stderr)
                return 3
            repo = WEB_REPO_RE.match(fields["web_repo"])
            assert repo is not None  # door web_fields gecontroleerd
            with open(output, "a", encoding="utf-8") as handle:
                handle.write(f"commit={fields['web_fork_commit']}\nrepo={repo.group(1)}\n")
        print(fields["web_fork_commit"])
        return 0
    errors = check_checkout(args.controleer.resolve(), baseline)
    if errors:
        print(f"WEB-BRON NIET IN ORDE ({len(errors)} problemen):", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(
        f"Web-bron in orde: {baseline['web_repo']}@{baseline['web_fork_commit'][:12]} = jellyfin-web "
        f"{baseline['upstream_version']} op upstream {baseline['web_upstream_tag']} ({baseline['web_upstream_commit'][:12]})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
