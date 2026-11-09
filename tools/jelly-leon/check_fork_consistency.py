#!/usr/bin/env python3
"""Controleert dat alle versie- en forkgegevens met elkaar kloppen (ADR-0002, ADR-0004, ADR-0005, ADR-0008).

Controles:
  1. baseline.json: upstream_tag ↔ upstream_version ↔ fork_version (`<upstream>-jl.<N>`).
  2. SharedVersion.cs (wat de server aan clients meldt) == upstream_version (technische identiteit blijft upstream).
  3. plugins/Directory.Build.props JellyfinVersion == upstream_version en TargetFramework == dat van
     MediaBrowser.Controller (plugins bouwen tegen dezelfde ABI).
  4. upstream_commit zit in de historie van HEAD (de basis is echt samengevoegd); lokale tag wijst naar dezelfde commit.
  5. LICENSE is nog de GPL-2.0-tekst.
  6. Manifest: versie/tag == fork_version, geen `latest`, geen compose, install.method custom_app; contract 1.2 §9:
     geen joins_platform_network en geen custom_app.ports, network.ports aanwezig, GPU als {param} van type gpu
     (wizard, D08, niet verplicht) binnen privileges.gpu (intel_render vereist D08 en privilege_reason).
  7. Dockerfiles onder deploy/: elke base-image op @sha256-digest, nergens `latest`.
  8. .NET-SDK: baseline.dotnet_sdk_major == major.minor uit de upstream-global.json; de SDK-image in de deploy-
     Dockerfiles hoort bij dezelfde major.minor (deploy-deel overgeslagen met --zonder-manifest, zoals het manifest).
  9. Web-client van de image (baseline.web_*): volledige SHA's, web_upstream_tag hoort bij dezelfde release als de
     server (overgeslagen met --zonder-manifest; de checkout zelf controleert web_bron.py in de CI-job image).

Exitcodes: 0 = in orde, 1 = inconsistent, 3 = gebruiks-/omgevingsfout.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jl_common import (  # noqa: E402
    DEFAULT_REPO_ROOT,
    FORK_VERSION_RE,
    MANIFEST_REL,
    ToolError,
    Version,
    load_baseline,
    parse_stable_tag,
    read_global_json_sdk,
    read_plugin_jellyfin_version,
    read_plugin_target_framework,
    read_shared_version,
    read_upstream_target_framework,
    run_git,
    sdk_major_minor,
)
from web_bron import web_fields  # noqa: E402

FROM_RE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.IGNORECASE)
ARG_IMAGE_RE = re.compile(r"^\s*ARG\s+([A-Z0-9_]*IMAGE[A-Z0-9_]*)=(\S+)", re.IGNORECASE)
SDK_IMAGE_RE = re.compile(r"mcr\.microsoft\.com/dotnet/sdk:(\d+)\.(\d+)(?:\.\d+)?(?=[@\s]|$)")


def check_baseline(repo: Path, baseline: dict) -> list[str]:
    errors: list[str] = []
    tag_version = parse_stable_tag(baseline["upstream_tag"])
    if tag_version is None:
        errors.append(f"baseline.upstream_tag '{baseline['upstream_tag']}' is geen stabiele upstream-tag")
    upstream_version = Version.parse(baseline["upstream_version"])
    if tag_version is not None and tag_version != upstream_version:
        errors.append(f"upstream_tag {baseline['upstream_tag']} hoort bij {tag_version}, niet bij {upstream_version}")
    match = FORK_VERSION_RE.match(baseline["fork_version"])
    if not match:
        errors.append(f"fork_version '{baseline['fork_version']}' volgt niet het schema <upstream>-jl.<N>")
    elif Version.parse(match.group(1)) != upstream_version:
        errors.append(f"fork_version {baseline['fork_version']} past niet bij upstream_version {upstream_version}")

    try:
        shared = Version.parse(read_shared_version(repo))
    except ToolError as exc:
        errors.append(f"SharedVersion.cs: {exc} (technische identiteit moet de upstream-versie blijven)")
    else:
        if shared != upstream_version:
            errors.append(
                f"SharedVersion.cs meldt {shared} maar de basis is {upstream_version}; "
                "de server moet de upstream-versie blijven melden (ADR-0003/ADR-0005)"
            )

    plugin_version = read_plugin_jellyfin_version(repo)
    if plugin_version is not None and Version.parse(plugin_version) != upstream_version:
        errors.append(f"plugins/Directory.Build.props JellyfinVersion {plugin_version} ≠ basis {upstream_version}")
    plugin_tf, upstream_tf = read_plugin_target_framework(repo), read_upstream_target_framework(repo)
    if plugin_tf and upstream_tf and plugin_tf != upstream_tf:
        errors.append(
            f"plugins/Directory.Build.props TargetFramework {plugin_tf} ≠ upstream-ABI {upstream_tf} "
            "(MediaBrowser.Controller.csproj)"
        )

    commit = baseline["upstream_commit"]
    if run_git(repo, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode != 0:
        errors.append(f"upstream_commit {commit} bestaat niet in deze repository (volledige historie nodig)")
    elif run_git(repo, "merge-base", "--is-ancestor", commit, "HEAD", check=False).returncode != 0:
        errors.append(f"upstream_commit {commit} is geen voorouder van HEAD: de basis is niet samengevoegd")

    local_tag = baseline.get("local_upstream_tag")
    if local_tag:
        proc = run_git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{local_tag}^{{commit}}", check=False)
        if proc.returncode == 0 and proc.stdout.strip() != commit:
            errors.append(f"lokale tag {local_tag} wijst naar {proc.stdout.strip()[:12]}, baseline zegt {commit[:12]}")
    return errors


def check_license(repo: Path) -> list[str]:
    path = repo / "LICENSE"
    if not path.is_file():
        return ["LICENSE ontbreekt (GPL-2.0 verplicht, ADR-0004)"]
    head = path.read_text(encoding="utf-8", errors="replace")[:400]
    if "GNU GENERAL PUBLIC LICENSE" not in head or "Version 2" not in head:
        return ["LICENSE is niet (meer) de GPL-2.0-tekst"]
    return []


def check_manifest(repo: Path, baseline: dict) -> list[str]:
    path = repo / MANIFEST_REL
    if not path.is_file():
        return [f"{MANIFEST_REL} ontbreekt"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    fork_version = baseline["fork_version"]
    version = re.search(r"^version:\s*\"?([^\"\s]+)\"?\s*$", text, re.MULTILINE)
    if not version or version.group(1) != fork_version:
        errors.append(f"manifest 'version' moet {fork_version} zijn")
    tag = re.search(r"^\s+tag:\s*\"?([^\"\s]+)\"?\s*$", text, re.MULTILINE)
    if not tag or tag.group(1) != fork_version:
        errors.append(f"manifest image.tag moet {fork_version} zijn")
    if re.search(r"(:|tag:\s*\"?)latest\b", text):
        errors.append("manifest bevat 'latest' (verboden)")
    if re.search(r"^\s*compose\s*:", text, re.MULTILINE):
        errors.append("manifest bevat een compose-veld (verboden, contract §9)")
    if not re.search(r"^\s+method:\s*custom_app\s*$", text, re.MULTILINE):
        errors.append("manifest install.method moet custom_app zijn")
    return errors + check_manifest_1_2(text)


def top_level_block(text: str, key: str) -> str | None:
    """Tekst van een blok op het hoogste niveau (`key:` tot de volgende sleutel zonder inspringing)."""
    match = re.search(rf"^{re.escape(key)}:(.*)$", text, re.MULTILINE)
    if not match:
        return None
    rest = text[match.end() :]
    end = re.search(r"^\S", rest, re.MULTILINE)
    return match.group(1) + rest[: end.start() if end else len(rest)]


def parameter_block(text: str, name: str) -> str | None:
    """Tekst van één parameter (`- name: <naam>` tot de volgende parameter) binnen `parameters:`."""
    block = top_level_block(text, "parameters")
    if block is None:
        return None
    for item in re.split(r"^\s*-\s+(?=name:)", block, flags=re.MULTILINE)[1:]:
        if re.match(rf"name:\s*\"?{re.escape(name)}\"?\s*$", item.splitlines()[0]):
            return item
    return None


def _scalar(block: str | None, key: str, indent: int = 2) -> str | None:
    if block is None:
        return None
    match = re.search(rf"^ {{{indent}}}{re.escape(key)}:\s*(.*?)\s*(?:#.*)?$", block, re.MULTILINE)
    return match.group(1).strip("\"'") if match else None


def check_manifest_1_2(text: str) -> list[str]:
    """Wijzigingen van contract 1.2 §9 (poorten alleen in network.ports, GPU als optionele parameter met D08).

    Bewust eenvoudig (standaardbibliotheek, vaste opmaak van ons eigen manifest); de volledige validatie doet de
    validator van de manifesteigenaar (appstore-en-fork) in de CI-job `manifest`.
    """
    errors: list[str] = []
    if re.search(r"^\s*joins_platform_network\s*:", text, re.MULTILINE):
        errors.append("manifest: network.joins_platform_network is vervallen (contract 1.2 §9) — verwijderen")
    custom_app = top_level_block(text, "custom_app")
    if custom_app is not None and re.search(r"^  ports\s*:", custom_app, re.MULTILINE):
        errors.append("manifest: custom_app.ports is vervallen (contract 1.2 §9) — poorten alleen in network.ports")
    network = top_level_block(text, "network")
    if network is None or not re.search(r"^  ports\s*:", network, re.MULTILINE):
        errors.append("manifest: network.ports ontbreekt (enige bron voor de formulierpoorten, contract 1.2 §9)")

    max_gpu = _scalar(top_level_block(text, "privileges"), "gpu")
    if max_gpu not in ("none", "intel_render"):
        errors.append(f"manifest: privileges.gpu moet none of intel_render zijn, niet {max_gpu!r}")
    app_gpu = _scalar(custom_app, "gpu")
    param = re.fullmatch(r"\{\s*param:\s*([a-z][a-z0-9_]*)\s*\}", app_gpu or "")
    if app_gpu is None:
        errors.append("manifest: custom_app.gpu ontbreekt")
    elif param:
        block = parameter_block(text, param.group(1))
        wanted = {"type": "gpu", "source": "wizard", "decision": "D08", "required": "false"}
        found = {key: _scalar(block, key, indent=4) for key in wanted}
        if block is None or found != wanted:
            errors.append(
                f"manifest: GPU-parameter {param.group(1)!r} moet type gpu, source wizard, decision D08 en required "
                f"false hebben (contract 1.2 §9), gevonden {found if block is not None else 'geen parameter'}"
            )
    elif app_gpu not in ("none", "intel_render"):
        errors.append(f"manifest: custom_app.gpu {app_gpu!r} moet none, intel_render of {{param: <naam>}} zijn")
    if app_gpu not in (None, "none") and max_gpu != "intel_render":
        errors.append("manifest: custom_app.gpu vraagt (mogelijk) een GPU maar privileges.gpu (het maximum) is niet intel_render")
    if max_gpu == "intel_render":
        decisions = re.search(r"^decisions_required:\s*\[([^\]]*)\]", text, re.MULTILINE)
        if not decisions or "D08" not in [d.strip() for d in decisions.group(1).split(",")]:
            errors.append("manifest: privileges.gpu intel_render vereist D08 in decisions_required")
        reason = top_level_block(text, "privilege_reason")
        if not reason or reason.strip() in ("", "null", ">-", "|"):
            errors.append("manifest: privileges.gpu intel_render vereist een privilege_reason")
    return errors


def check_dockerfiles(repo: Path) -> list[str]:
    errors: list[str] = []
    deploy = repo / "deploy"
    if not deploy.is_dir():
        return errors
    for dockerfile in sorted(deploy.rglob("Dockerfile*")):
        if dockerfile.suffix == ".dockerignore":
            continue
        rel = dockerfile.relative_to(repo)
        stage_names: set[str] = set()
        arg_images: dict[str, str] = {}
        for number, line in enumerate(dockerfile.read_text(encoding="utf-8").splitlines(), start=1):
            arg = ARG_IMAGE_RE.match(line)
            if arg:
                arg_images[arg.group(1)] = arg.group(2)
                if "@sha256:" not in arg.group(2):
                    errors.append(f"{rel}:{number}: {arg.group(1)} zonder @sha256-digest")
                if re.search(r":latest(@|$)", arg.group(2)):
                    errors.append(f"{rel}:{number}: {arg.group(1)} gebruikt 'latest'")
            frm = FROM_RE.match(line)
            if frm:
                image = frm.group(1)
                alias = re.search(r"\bAS\s+(\S+)", line, re.IGNORECASE)
                if image.startswith("${") or image.startswith("$"):
                    name = image.strip("${}")
                    if name not in arg_images:
                        errors.append(f"{rel}:{number}: FROM {image} zonder ARG-standaardwaarde met digest")
                elif image not in stage_names and image != "scratch":
                    if "@sha256:" not in image:
                        errors.append(f"{rel}:{number}: FROM {image} zonder @sha256-digest")
                    if re.search(r":latest(@|$)", image):
                        errors.append(f"{rel}:{number}: FROM {image} gebruikt 'latest'")
                if alias:
                    stage_names.add(alias.group(1))
    return errors


def check_sdk(repo: Path, baseline: dict, *, include_deploy: bool) -> list[str]:
    """global.json is een upstream-bestand: baseline en deploy-Dockerfiles moeten dezelfde SDK-reeks volgen."""
    version = read_global_json_sdk(repo)
    if version is None:
        return []
    errors: list[str] = []
    major_minor = sdk_major_minor(version)
    recorded = baseline.get("dotnet_sdk_major")
    if recorded is not None and str(recorded) != major_minor:
        errors.append(
            f"baseline.dotnet_sdk_major {recorded} ≠ SDK-reeks {major_minor} uit global.json ({version}); "
            "werk baseline.json bij (upstream_sync.py doet dat bij een sync)"
        )
    deploy = repo / "deploy"
    if include_deploy and deploy.is_dir():
        for dockerfile in sorted(deploy.rglob("Dockerfile*")):
            if dockerfile.suffix == ".dockerignore":
                continue
            rel = dockerfile.relative_to(repo)
            for number, line in enumerate(dockerfile.read_text(encoding="utf-8").splitlines(), start=1):
                for match in SDK_IMAGE_RE.finditer(line):
                    found = f"{match.group(1)}.{match.group(2)}"
                    if found != major_minor:
                        errors.append(
                            f"{rel}:{number}: .NET-SDK-image {found} past niet bij global.json ({version}, reeks "
                            f"{major_minor}); de image moet met dezelfde SDK-reeks bouwen als CI"
                        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controleer versie- en forkconsistentie.")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument(
        "--zonder-manifest",
        dest="skip_manifest",
        action="store_true",
        help="manifest- en deploy-SDK-controle overslaan (alleen in upstream-sync: deploy volgt pas bij een release)",
    )
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    try:
        baseline = load_baseline(repo)
        errors = check_baseline(repo, baseline) + check_license(repo) + check_dockerfiles(repo)
        errors += check_sdk(repo, baseline, include_deploy=not args.skip_manifest)
        if not args.skip_manifest:
            errors += check_manifest(repo, baseline)
            if "web_repo" in baseline:
                errors += web_fields(baseline)[0]
    except ToolError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return exc.exit_code if exc.exit_code != 1 else 3
    if errors:
        print(f"FORKCONSISTENTIE NIET IN ORDE ({len(errors)} problemen):", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(
        f"Forkconsistentie in orde: basis {baseline['upstream_tag']} ({baseline['upstream_commit'][:12]}), "
        f"forkversie {baseline['fork_version']}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
