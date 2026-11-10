#!/usr/bin/env python3
"""Healthcheck-proef in een echte container (contract 1.3 §2.2, C1.3-ALG-04/C1.3-JL-03; Sim-getest, geen echte NAS).

Draait `deploy/allinone/healthcheck.sh` uit deze checkout (alleen-lezen gemount op het pad in de image) in de vastgezette
upstream-runtime (`JL_RUNTIME_IMAGE`, dezelfde basis als de image) — zonder de hele image te bouwen. De containers
starten zoals het formulier: zonder `--security-opt no-new-privileges`, zonder `--cap-drop`, en zonder netwerk naar
buiten (`--network none`, alleen de eigen loopback).

  1. start als root (geen Custom User): `--toon-rechten` meldt na de wissel Uid/Gid 568, geen groepen, CapEff, CapPrm,
     CapAmb en CapBnd 0 en NoNewPrivs 1 (exitcode 0); zonder server op 8096 is de healthcheck rood (exitcode 1);
  2. als root met het interne fase-argument `--na-wissel`: er wordt toch gewisseld (rechten in orde, exitcode 0);
  3. `docker exec --user 568:568` met `--na-wissel-root` (geen echte wissel, geen no_new_privs): rood (exitcode 1);
  4. "Custom User 568" (`--user 568:568`): `--toon-rechten` meldt Uid 568, CapEff/CapPrm/CapAmb 0, NoNewPrivs 1
     (CapBnd mag de Docker-standaardset zijn); met `--na-wissel` zonder echte wissel rood;
  5. met de stock-server als dienst (die zelf als root draait; alleen om /health te hebben): de healthcheck wordt
     groen (exitcode 0) zodra /health 200 geeft — curl draait daarbij als 568 met no_new_privs.

De gebouwde image zelf (HEALTHCHECK in exec-vorm, elk proces in de boom van PID 1) controleert image_lifecycle.py.
Alleen standaardbibliotheek; Docker via subprocess zonder shell. Exitcode 0 = alles geslaagd.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from image_lifecycle import (  # noqa: E402
    APP_UID,
    HEALTHCHECK,
    docker,
    healthcheck_problems,
    parse_proc_status,
    utc_now,
)

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "deploy" / "allinone" / "healthcheck.sh"


def fields(status_text: str) -> str:
    procs = parse_proc_status(status_text)
    if len(procs) != 1:
        return f"{len(procs)} statussen"
    proc = procs[0]
    return ", ".join(
        f"{key}={' '.join(proc.get(key, [])) or '-'}"
        for key in ("Uid", "Gid", "Groups", "CapPrm", "CapEff", "CapAmb", "CapBnd", "NoNewPrivs")
    )


class Proef:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.steps: list[dict] = []
        self.prefix = f"jl-hc-proef-{os.getpid()}"
        self.containers: list[str] = []

    def add(self, name: str, ok: bool, detail: str) -> bool:
        self.steps.append({"stap": name, "geslaagd": ok, "detail": detail, "tijd": utc_now()})
        print(f"[{'OK  ' if ok else 'FOUT'}] {name}: {detail}", flush=True)
        return ok

    def start(self, suffix: str, *, user: str | None = None, server: bool = False) -> str:
        name = f"{self.prefix}-{suffix}"
        args = ["run", "-d", "--name", name, "--network", "none", "-v", f"{SCRIPT}:{HEALTHCHECK}:ro"]
        if user:
            args += ["--user", user]
        if server:
            args += [self.args.image]  # standaard-entrypoint van de runtime: de stock-server (alleen voor /health)
        else:
            args += ["--entrypoint", "/bin/sleep", self.args.image, "infinity"]
        docker(*args)
        self.containers.append(name)
        return name

    def rights(self, label: str, name: str, *, root_start: bool, extra: tuple[str, ...] = (), user: str | None = None) -> bool:
        cmd = ["exec", *(["--user", user] if user else []), name, HEALTHCHECK, "--toon-rechten", *extra]
        proc = docker(*cmd, check=False)
        problems = healthcheck_problems(proc.stdout, root_start=root_start)
        if proc.returncode != 0:
            problems.append(f"exitcode {proc.returncode}: {proc.stderr.strip()[:200]}")
        detail = fields(proc.stdout) + ("; AFWIJKEND: " + "; ".join(problems[:6]) if problems else "")
        return self.add(label, not problems, detail)

    def red(self, label: str, name: str, *args: str, user: str | None = None, expect: str) -> bool:
        cmd = ["exec", *(["--user", user] if user else []), name, HEALTHCHECK, *args]
        proc = docker(*cmd, check=False)
        ok = proc.returncode == 1 and expect in proc.stderr
        return self.add(label, ok, f"exitcode {proc.returncode}; {proc.stderr.strip()[:200]}")

    def run(self) -> bool:
        uid = f"{APP_UID}:{APP_UID}"
        root = self.start("root")
        self.rights("als root gestart: rechten na de wissel (controlevlag)", root, root_start=True)
        self.red("als root gestart, geen server: healthcheck rood", root, expect="/health antwoordt niet met 200")
        self.rights("als root met fase-argument --na-wissel: toch gewisseld", root, root_start=True,
                    extra=("--na-wissel",))
        self.red("exec als 568 met --na-wissel-root zonder echte wissel: rood", root, "", "--na-wissel-root",
                 user=uid, expect="rechtenwissel niet in orde")

        custom = self.start("custom-user", user=uid)
        self.rights("Custom User 568: rechten na de wissel (controlevlag)", custom, root_start=False)
        self.red("Custom User 568 met --na-wissel zonder echte wissel: rood", custom, "", "--na-wissel",
                 expect="rechtenwissel niet in orde")

        server = self.start("server", server=True)
        deadline = time.monotonic() + self.args.health_timeout
        last = None
        while time.monotonic() < deadline:
            last = docker("exec", server, HEALTHCHECK, check=False)
            if last.returncode == 0:
                break
            time.sleep(3)
        ok = last is not None and last.returncode == 0
        detail = "exitcode 0 (GET /health = 200, curl als 568 met no_new_privs)" if ok else (
            f"na {self.args.health_timeout:.0f}s: exitcode {last.returncode if last else '?'}; "
            f"{(last.stderr if last else '').strip()[:200]}"
        )
        self.add("stock-server draait: healthcheck groen", ok, detail)
        return all(step["geslaagd"] for step in self.steps)

    def cleanup(self) -> None:
        for name in self.containers:
            docker("rm", "-f", "-v", name, check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Healthcheck-proef in de runtime-image (Docker, Sim-getest).")
    parser.add_argument("--image", required=True, help="runtime-image op digest (JL_RUNTIME_IMAGE)")
    parser.add_argument("--health-timeout", type=float, default=180)
    parser.add_argument("--rapport", help="pad voor het JSON-rapport")
    args = parser.parse_args(argv)
    if not SCRIPT.is_file():
        print(f"FOUT: {SCRIPT} ontbreekt", file=sys.stderr)
        return 3
    proef = Proef(args)
    started = utc_now()
    try:
        passed = proef.run()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        proef.add("uitvoering", False, str(exc)[:500])
        passed = False
    finally:
        proef.cleanup()
    result = {
        "soort": "Sim-getest (Docker op de bouwmachine; geen echte NAS, geen TrueNAS-formulier)",
        "image": args.image,
        "script": str(SCRIPT.relative_to(REPO)),
        "script_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
        "gestart": started,
        "klaar": utc_now(),
        "geslaagd": passed,
        "stappen": proef.steps,
    }
    if args.rapport:
        Path(args.rapport).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ok = sum(step["geslaagd"] for step in proef.steps)
    print(f"RESULTAAT: {'GESLAAGD' if passed else 'MISLUKT'} ({ok}/{len(proef.steps)})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
