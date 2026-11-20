#!/usr/bin/env python3
"""De Docker-proeven gebruiken alleen hun eigen, aan beide kanten gecontroleerde jobmap."""
from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


def mountoptie(koppeling: dict[str, str], relatief: Path, doel: str, alleen_lezen: bool) -> str:
    bron = Path(koppeling["pad"]) / relatief
    if koppeling["soort"] == "volume":
        optie = f"type=volume,source={koppeling['naam']},volume-subpath={bron},target={doel},volume-nocopy"
    else:
        optie = f"type=bind,source={bron},target={doel}"
    return optie + (",readonly" if alleen_lezen else "")


def eigen_koppelingen(docker: str, werk: Path):
    yield {"soort": "bind", "pad": str(werk)}
    # Inspecteer uitsluitend de eigen jobcontainer. Alleen de mount waaronder de proefmap ligt is relevant.
    inspectie = subprocess.run(
        [docker, "container", "inspect", "--format", "{{json .Mounts}}", socket.gethostname()],
        capture_output=True, text=True, check=False,
    )
    if inspectie.returncode:
        return
    mounts = sorted(json.loads(inspectie.stdout), key=lambda m: len(m["Destination"]), reverse=True)
    for m in mounts:
        bestemming = Path(m["Destination"])
        if not werk.is_relative_to(bestemming):
            continue
        suffix = werk.relative_to(bestemming)
        if m["Type"] == "volume":
            yield {"soort": "volume", "naam": m["Name"], "pad": str(Path(m.get("Subpath") or ".") / suffix)}
        elif m["Type"] == "bind":
            yield {"soort": "bind", "pad": str(Path(m["Source"]) / suffix)}
        break


def gedeelde_map(docker: str, image: str, bases: list[Path]) -> tuple[Path, dict[str, str]]:
    for basis in bases:
        werk = Path(tempfile.mkdtemp(prefix="jl-proeven-", dir=basis))
        marker = werk / "jobmarker"
        try:
            # Een willekeurige marker sluit een lege of oude gelijknamige daemonmap uit.
            waarde = secrets.token_hex(16)
            marker.write_text(waarde, encoding="ascii")
            for koppeling in eigen_koppelingen(docker, werk):
                optie = mountoptie(koppeling, Path("."), "/proef", True)
                proef = subprocess.run(
                    [docker, "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL", "--user", f"{os.getuid()}:{os.getgid()}",
                     "--security-opt", "no-new-privileges", "--mount", optie, "--entrypoint", "/bin/cat", image, "/proef/jobmarker"],
                    capture_output=True, text=True, check=False,
                )
                if proef.returncode == 0 and proef.stdout == waarde:
                    marker.unlink()
                    return werk, koppeling
        finally:
            if marker.exists():
                shutil.rmtree(werk)
    raise RuntimeError("De buildengine ziet het proefbestand niet. Koppel een jobvolume of deel CI_DOCKER_WERKMAP met de engine.")


def bereid() -> int:
    omgeving = os.environ
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker-CLI ontbreekt")
    repo = Path(__file__).resolve().parents[2]
    bases = [omgeving.get("CI_DOCKER_WERKMAP"), omgeving["GITHUB_WORKSPACE"], omgeving["RUNNER_TEMP"]]
    locaties = list(dict.fromkeys(Path(b).resolve(strict=True) for b in bases if b))
    image = omgeving["JL_RUNTIME_IMAGE"]
    if subprocess.run([docker, "image", "inspect", "--format", "{{.Id}}", image], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, check=False).returncode:
        subprocess.run([docker, "pull", image], check=True)
    werk, koppeling = gedeelde_map(docker, image, locaties)
    # De healthcheck is de enige losse bronfile die de Docker-proeven vanuit de checkout koppelen.
    shutil.copy2(repo / "deploy/allinone/healthcheck.sh", werk / "healthcheck.sh")
    hulp = Path(tempfile.mkdtemp(prefix="jl-docker-", dir=omgeving["RUNNER_TEMP"]))
    (hulp / "koppeling.json").write_text(json.dumps({"docker": docker, "werk": str(werk), "repo": str(repo), **koppeling}), encoding="utf-8")
    start = hulp / "docker"
    start.write_text(f'#!/bin/sh\nexec python3 {shlex.quote(str(Path(__file__).resolve()))} docker "$@"\n', encoding="utf-8")
    start.chmod(0o700)
    with Path(omgeving["GITHUB_PATH"]).open("a", encoding="utf-8") as out:
        print(hulp, file=out)
    with Path(omgeving["GITHUB_ENV"]).open("a", encoding="utf-8") as out:
        print(f"JL_PROEFMAP={werk}\nJL_DOCKER_KOPPELING={hulp / 'koppeling.json'}", file=out)
    print(f"Proefmap in de geïsoleerde buildengine gecontroleerd ({koppeling['soort']}).")
    return 0


def docker_opdracht(args: list[str]) -> None:
    koppeling = json.loads(Path(os.environ["JL_DOCKER_KOPPELING"]).read_text(encoding="utf-8"))
    werk = Path(koppeling["werk"])
    if args and args[0] in {"run", "create"}:
        for i in range(1, len(args) - 1):
            if args[i] not in {"-v", "--volume"} or not args[i + 1].startswith("/"):
                continue
            bron, doel, *modus = args[i + 1].split(":")
            bronpad = Path(bron).resolve()
            alleen_lezen = modus == ["ro"]
            if alleen_lezen and bronpad == Path(koppeling["repo"]) / "deploy/allinone/healthcheck.sh":
                bronpad = werk / "healthcheck.sh"
            if not bronpad.is_relative_to(werk) or modus not in ([], ["rw"], ["ro"]):
                raise RuntimeError("Docker-bind valt buiten de eigen proefmap of heeft een onbekende modus")
            args[i] = "--mount"
            args[i + 1] = mountoptie(koppeling, bronpad.relative_to(werk), doel, alleen_lezen)
    os.execv(koppeling["docker"], [koppeling["docker"], *args])  # noqa: S606 - vaste CLI met losse argumenten


def ruim() -> None:
    bestand = Path(os.environ["JL_DOCKER_KOPPELING"])
    koppeling = json.loads(bestand.read_text(encoding="utf-8"))
    werk = Path(koppeling["werk"])
    if werk != Path(os.environ["JL_PROEFMAP"]) or not werk.name.startswith("jl-proeven-") or werk.is_symlink():
        raise RuntimeError("Onbekende proefmap bij het opruimen")
    try:
        shutil.rmtree(werk)
    except PermissionError:
        subprocess.run([koppeling["docker"], "run", "--rm", "--network", "none", "--user", "0:0", "--mount",
                        mountoptie(koppeling, Path("."), "/proef", False), "--entrypoint", "/bin/chown", os.environ["JL_RUNTIME_IMAGE"],
                        "-R", f"{os.getuid()}:{os.getgid()}", "/proef"], check=True)
        shutil.rmtree(werk)
    shutil.rmtree(bestand.parent)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["bereid"]:
            sys.exit(bereid())
        if sys.argv[1:] == ["ruim"]:
            ruim()
            sys.exit(0)
        if sys.argv[1:2] != ["docker"]:
            raise RuntimeError("Verwacht bereid, docker of ruim")
        docker_opdracht(sys.argv[2:])
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as fout:
        sys.exit(f"Docker-proefmap: {fout}")
