#!/usr/bin/env python3
"""Levenscyclustest van de alles-in-één image (Sim-getest met Docker; GEEN echte NAS, geen TrueNAS-formulier).

Bootst na wat een standaard TrueNAS Custom App met de waarden uit deploy/truenas/CUSTOM_APP.md doet:
  1. lege host-mappen voor /config en /cache (eigenaar = aanroeper, niet 568) en media alleen-lezen;
  2. container starten zoals het formulier: als root (geen Custom User), niet privileged, geen extra capabilities,
     geen host-netwerk, alleen poort 8096 gepubliceerd;
  3. wachten tot de Docker-healthcheck van de image `healthy` meldt;
  4. stock-client-smoketest modus `nieuw` (wizard, inloggen, bibliotheek, streamen, plugin) en web-client op /web/:
     index.html én elk daarin genoemd script/stylesheet laadt (HTTP 200, niet leeg) — een half gelukte web-build valt
     zo op; optioneel (--verwacht-web-ref) de herkomst van de web-client (label + SOURCE_REVISIONS in de image);
  5. proces 1 draait als 568:568, zonder capabilities, met NoNewPrivs; alles in /config en /cache is van 568;
     de mediamap is niet gewijzigd;
  6. `docker restart` → healthy → smoketest modus `herstart` (zelfde gebruiker en item-ID, wizard blijft dicht);
  7. container verwijderen en opnieuw aanmaken met dezelfde opslag (zoals een app-update/herinstallatie)
     → healthy → smoketest modus `herstart`;
  8. negatieve tests (fail-closed): de container weigert te starten en de mediamap blijft onaangeroerd bij
     - geen opslagregel voor /cache (anoniem Docker-volume);
     - JELLYFIN_CACHE_DIR naar de mediamap (root zou anders `chown -R` op de media doen);
     - /config als tmpfs (opslagtype tmpfs in het formulier: database weg na elke herstart, startwizard weer open);
     - JELLYFIN_CONFIG_DIR in de container zelf (instellingen weg bij elke update);
     - een padoptie (`--datadir`) in het veld Command.
  9. bij succes wordt de werkmap opgeruimd (bestanden van 568 via een wegwerpcontainer; --behoud-werkmap houdt hem).

Alleen standaardbibliotheek; Docker via subprocess zonder shell. Schrijft een JSON-rapport. Exitcode 0 = alles geslaagd.
"""

from __future__ import annotations

import argparse
import html.parser
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
SMOKE = E2E_DIR / "stock_client_smoke.py"
MAKE_MEDIA = E2E_DIR / "make_test_media.py"
MEDIA_REL = Path("Jelly Leon Test") / "Smoketest" / "01 - Sinus 440 Hz.wav"
APP_UID = "568"


class AssetParser(html.parser.HTMLParser):
    """Verzamelt de scripts en stylesheets die index.html van de web-client laadt."""

    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.assets.append(str(values["src"]))
        elif tag == "link" and (values.get("rel") or "").lower() == "stylesheet" and values.get("href"):
            self.assets.append(str(values["href"]))


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def docker(*args: str, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, check=False, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:2])} mislukte (exit {proc.returncode}): {proc.stderr.strip()[:500]}")
    return proc


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Lifecycle:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.steps: list[dict] = []
        self.name = f"jl-lifecycle-{os.getpid()}"
        self.port = free_port()
        self.work = Path(tempfile.mkdtemp(prefix="jl-lifecycle-", dir=args.werkmap))
        self.config = self.work / "config"
        self.cache = self.work / "cache"
        self.media = self.work / "media"

    # ------------------------------------------------------------------ hulpfuncties
    def add(self, name: str, ok: bool, detail: str) -> bool:
        self.steps.append({"stap": name, "geslaagd": ok, "detail": detail, "tijd": utc_now()})
        print(f"[{'OK  ' if ok else 'FOUT'}] {name}: {detail}", flush=True)
        return ok

    def run_args(
        self,
        name: str,
        *,
        mounts: list[str],
        env: list[str] | None = None,
        extra: list[str] | None = None,
        command: list[str] | None = None,
        image: str | None = None,
    ) -> list[str]:
        args = ["run", "-d", "--name", name, "-p", f"127.0.0.1:{self.port}:8096"]
        for item in env or []:
            args += ["-e", item]
        for mount in mounts:
            args += ["-v", mount]
        return [*args, *(extra or []), image or self.args.image, *(command or [])]

    def standard_mounts(self) -> list[str]:
        return [f"{self.config}:/config", f"{self.cache}:/cache", f"{self.media}:/media/muziek:ro"]

    def start(self, image: str | None = None) -> None:
        docker(*self.run_args(self.name, mounts=self.standard_mounts(), image=image))

    def remove(self, name: str) -> None:
        docker("rm", "-f", "-v", name, check=False)

    def logs(self, name: str, lines: int = 60) -> str:
        proc = docker("logs", "--tail", str(lines), name, check=False)
        return (proc.stdout + proc.stderr)[-6000:]

    def wait_healthy(self, label: str) -> bool:
        deadline = time.monotonic() + self.args.health_timeout
        status = "?"
        while time.monotonic() < deadline:
            proc = docker("inspect", "-f", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
                          self.name, check=False)
            parts = proc.stdout.split()
            status = " ".join(parts) or proc.stderr.strip()
            if parts[:1] == ["exited"] or (len(parts) > 1 and parts[1] == "unhealthy"):
                break
            if len(parts) > 1 and parts[1] == "healthy":
                return self.add(f"healthy ({label})", True, f"Docker-healthcheck van de image: {status}")
            time.sleep(3)
        self.add(f"healthy ({label})", False, f"status '{status}' na {self.args.health_timeout}s")
        print(self.logs(self.name), file=sys.stderr)
        return False

    def smoke(
        self,
        label: str,
        mode: str,
        previous: dict | None = None,
        *,
        expect_plugin: bool = True,
        version: str | None = None,
    ) -> dict | None:
        report_path = self.work / f"smoke-{label}.json"
        cmd = [
            sys.executable, str(SMOKE), "--url", f"http://127.0.0.1:{self.port}",
            "--expected-version", version or self.args.expected_version, "--library-path", "/media/muziek",
            "--media-file", str(self.media / MEDIA_REL), "--modus", mode,
            "--report", str(report_path), "--start-timeout", "60",
        ]
        if expect_plugin:
            cmd.append("--expect-plugin")
        if previous:
            cmd += ["--verwacht-item", previous["item_id"], "--verwacht-gebruiker", previous["gebruiker_id"]]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
        result = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
        passed = proc.returncode == 0 and bool(result and result.get("geslaagd"))
        total = len(result["stappen"]) if result else 0
        ok_steps = sum(s["geslaagd"] for s in result["stappen"]) if result else 0
        self.add(f"stock-client-smoketest ({label}, modus {mode})", passed, f"{ok_steps}/{total} stappen")
        if not passed:
            print(proc.stdout[-4000:], proc.stderr[-2000:], file=sys.stderr)
        return result if passed else None

    def check_process_and_ownership(self) -> bool:
        status = docker("exec", self.name, "cat", "/proc/1/status").stdout
        fields = {}
        for line in status.splitlines():
            key, _, value = line.partition(":")
            fields[key] = value.split()
        ok = (
            fields.get("Uid", [])[:4] == [APP_UID] * 4
            and fields.get("Gid", [])[:4] == [APP_UID] * 4
            and fields.get("CapEff") == ["0000000000000000"]
            and fields.get("CapPrm") == ["0000000000000000"]
            and fields.get("CapBnd") == ["0000000000000000"]
            and fields.get("NoNewPrivs") == ["1"]
        )
        detail = (
            f"Uid={' '.join(fields.get('Uid', []))}; Gid={' '.join(fields.get('Gid', []))}; "
            f"Groups={' '.join(fields.get('Groups', []))}; CapEff={''.join(fields.get('CapEff', []))}; "
            f"CapBnd={''.join(fields.get('CapBnd', []))}; NoNewPrivs={''.join(fields.get('NoNewPrivs', []))}"
        )
        self.add("proces 1 als 568:568 zonder capabilities", ok, detail)
        foreign = docker("exec", self.name, "find", "/config", "/cache", "!", "-user", APP_UID, "-print").stdout.split()
        self.add("/config en /cache volledig van 568", not foreign, f"{len(foreign)} bestanden van een andere eigenaar")
        plugin = docker("exec", self.name, "find", "/config/plugins", "-name", "Jellyfin.Plugin.JellyLeon.dll").stdout
        self.add("Jelly Leon-plugin in de datamap", bool(plugin.strip()), plugin.strip() or "niet gevonden")
        return ok and not foreign

    def fetch(self, path: str, limit: int = 20_000_000) -> tuple[int, bytes]:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=15) as resp:  # noqa: S310
            return resp.status, resp.read(limit)

    def check_web_client(self) -> bool:
        """De meegeleverde web-client wordt door de server zelf geserveerd (één poort, geen aparte web-app)."""
        try:
            status, body = self.fetch("/web/index.html", 200_000)
        except OSError as exc:
            return self.add("web-client bereikbaar", False, str(exc)[:200])
        ok = status == 200 and b"<title>" in body
        self.add("web-client bereikbaar", ok, f"HTTP {status}; {len(body)} bytes; <title> aanwezig={b'<title>' in body}")
        parser = AssetParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        assets = [a for a in parser.assets if not urllib.parse.urlsplit(a).netloc]  # alleen eigen bestanden
        failed: list[str] = []
        total_bytes = 0
        for asset in assets:
            path = "/web/" + urllib.parse.urlsplit(asset).path.lstrip("/")
            try:
                asset_status, asset_body = self.fetch(path)
            except OSError as exc:
                failed.append(f"{asset}: {str(exc)[:80]}")
                continue
            total_bytes += len(asset_body)
            if asset_status != 200 or not asset_body:
                failed.append(f"{asset}: HTTP {asset_status}, {len(asset_body)} bytes")
        assets_ok = bool(assets) and not failed
        detail = f"{len(assets) - len(failed)}/{len(assets)} scripts/stylesheets uit index.html geladen ({total_bytes} bytes)"
        if failed:
            detail += "; mislukt: " + "; ".join(failed[:3])
        self.add("web-client: alle bundels uit index.html laden", assets_ok, detail)
        return ok and assets_ok

    def check_source_revisions(self) -> bool:
        """Herkomst (GPL 'bron beschikbaar'): label én bestand in de image noemen de verwachte web-commit."""
        expected = self.args.verwacht_web_ref
        label = docker(
            "image", "inspect", "-f", '{{index .Config.Labels "io.github.lvos04.jelly-leon.web.revision"}}', self.args.image
        ).stdout.strip()
        revisions = docker("exec", self.name, "cat", "/usr/share/doc/jelly-leon/SOURCE_REVISIONS", check=False).stdout
        ok = label == expected and f"web {expected}" in revisions.splitlines()
        return self.add(
            "herkomst web-client (label + SOURCE_REVISIONS)",
            ok,
            f"verwacht {expected}; label {label or '-'}; bestand: {' | '.join(revisions.split(chr(10))[:2]) or '-'}",
        )

    def media_fingerprint(self) -> list[tuple[str, int, int, int]]:
        result = []
        for path in sorted(self.media.rglob("*")):
            st = path.stat()
            result.append((str(path.relative_to(self.media)), st.st_uid, st.st_gid, st.st_mode))
        return result

    def expect_refusal(
        self,
        label: str,
        *,
        mounts: list[str],
        env: list[str],
        expected_text: str,
        extra: list[str] | None = None,
        command: list[str] | None = None,
    ) -> None:
        name = f"{self.name}-neg"
        self.remove(name)
        before = self.media_fingerprint()
        docker(*self.run_args(name, mounts=mounts, env=env, extra=extra, command=command))
        deadline = time.monotonic() + 60
        state = ""
        while time.monotonic() < deadline:
            state = docker("inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}", name, check=False).stdout.strip()
            if state.startswith("exited"):
                break
            time.sleep(1)
        log = self.logs(name, 20)
        refused = state.startswith("exited") and not state.endswith(" 0") and expected_text in log
        untouched = self.media_fingerprint() == before
        last_line = log.strip().splitlines()[-1] if log.strip() else ""
        self.add(f"geweigerd: {label}", refused and untouched, f"{state}; media ongewijzigd={untouched}; {last_line[:200]}")
        self.remove(name)

    # ------------------------------------------------------------------ verloop
    def run(self) -> bool:
        for directory in (self.config, self.cache, self.media):
            directory.mkdir(parents=True)
        subprocess.run([sys.executable, str(MAKE_MEDIA), str(self.media)], check=True, capture_output=True)
        media_before = self.media_fingerprint()
        try:
            self.start()
            if not self.wait_healthy("eerste start, lege opslag"):
                return False
            first = self.smoke("eerste start", "nieuw")
            if not first:
                return False
            self.check_process_and_ownership()
            self.check_web_client()
            if self.args.verwacht_web_ref:
                self.check_source_revisions()

            docker("restart", self.name, timeout=180)
            if not self.wait_healthy("na docker restart") or not self.smoke("na herstart", "herstart", first):
                return False

            self.remove(self.name)
            self.start()
            if not self.wait_healthy("nieuwe container, zelfde opslag"):
                return False
            if not self.smoke("nieuwe container", "herstart", first):
                return False
            self.check_process_and_ownership()
            self.add("mediamap onaangeroerd", self.media_fingerprint() == media_before, "eigenaar/rechten ongewijzigd")
        finally:
            self.remove(self.name)

        self.expect_refusal(
            "geen opslagregel voor /cache (anoniem Docker-volume)",
            mounts=[f"{self.config}:/config", f"{self.media}:/media/muziek:ro"],
            env=[],
            expected_text="anoniem Docker-volume",
        )
        self.expect_refusal(
            "JELLYFIN_CACHE_DIR wijst naar de mediamap",
            mounts=self.standard_mounts(),
            env=["JELLYFIN_CACHE_DIR=/media/muziek"],
            expected_text="buiten /config of /cache",
        )
        # Opslagtype tmpfs in het formulier: zonder weigering zou de server 'healthy' worden, na elke herstart een lege
        # database hebben en de startwizard weer anoniem aanbieden (gemeten in de review P0-afronding).
        self.expect_refusal(
            "/config als tmpfs (werkgeheugen)",
            mounts=[f"{self.cache}:/cache", f"{self.media}:/media/muziek:ro"],
            env=[],
            extra=["--tmpfs", "/config"],
            expected_text="staat in het werkgeheugen (tmpfs)",
        )
        self.expect_refusal(
            "JELLYFIN_CONFIG_DIR in de container zelf",
            mounts=self.standard_mounts(),
            env=["JELLYFIN_CONFIG_DIR=/jl-config"],
            expected_text="in de container zelf",
        )
        self.expect_refusal(
            "padoptie --datadir in het veld Command",
            mounts=self.standard_mounts(),
            env=[],
            command=["--datadir", "/jl-data"],
            expected_text="opdrachtregeloptie '--datadir'",
        )
        return bool(self.steps) and all(step["geslaagd"] for step in self.steps)

    def cleanup(self) -> bool:
        """Werkmap opruimen; /config en /cache zijn van 568, dus via een wegwerpcontainer (geen sudo)."""
        docker(
            "run", "--rm", "--network", "none", "--entrypoint", "/bin/rm", "-v", f"{self.work}:/werk", self.args.image,
            "-rf", "/werk/config", "/werk/cache", "/werk/media", check=False, timeout=120,
        )
        shutil.rmtree(self.work, ignore_errors=True)
        return not self.work.exists()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Levenscyclustest van de Jelly Leon-image (Docker, Sim-getest).")
    parser.add_argument("--image", required=True, help="te testen image (lokaal gebouwd, bv. jelly-leon:test)")
    parser.add_argument("--expected-version", required=True, help="upstream-versie die de server moet melden")
    parser.add_argument("--werkmap", default=None, help="map voor tijdelijke opslag (standaard: systeem-tmp)")
    parser.add_argument(
        "--behoud-werkmap", dest="keep_workdir", action="store_true",
        help="werkmap ook bij succes laten staan (bij falen blijft hij altijd staan, ter diagnose)",
    )
    parser.add_argument("--health-timeout", type=float, default=240)
    parser.add_argument("--report", help="pad voor het JSON-rapport")
    parser.add_argument("--opmerking", default="", help="vrije toelichting in het rapport (bv. herkomst web-client)")
    parser.add_argument(
        "--verwacht-web-ref", dest="verwacht_web_ref", default="",
        help="commit van jelly-leon-web die in label en /usr/share/doc/jelly-leon/SOURCE_REVISIONS moet staan",
    )
    args = parser.parse_args(argv)
    lifecycle = Lifecycle(args)
    started = utc_now()
    try:
        passed = lifecycle.run()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        lifecycle.add("uitvoering", False, str(exc)[:500])
        passed = False
    result = {
        "soort": "Sim-getest (Docker op de bouwmachine; geen echte NAS, geen TrueNAS-formulier)",
        "image": args.image,
        "opmerking": args.opmerking,
        "gestart": started,
        "klaar": utc_now(),
        "geslaagd": passed,
        "stappen": lifecycle.steps,
        "werkmap": str(lifecycle.work),
    }
    if passed and not args.keep_workdir:
        result["werkmap"] += " (opgeruimd)" if lifecycle.cleanup() else " (opruimen mislukt)"
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ok = sum(step["geslaagd"] for step in lifecycle.steps)
    print(f"RESULTAAT: {'GESLAAGD' if passed else 'MISLUKT'} ({ok}/{len(lifecycle.steps)})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
