#!/usr/bin/env python3
"""Terugzetproef voor B03-013 (Sim-getest met Docker; GEEN echte NAS, geen ZFS-snapshot, geen TrueNAS-formulier).

Acceptatie B03-013: "Fork-migratie is terug te zetten met DB-back-up + binary en streaming blijft werken". Deze proef
doorloopt dat pad met echte images op de bouwmachine:
  1. de upstream-image (de 'bestaande Jellyfin', zonder --user zoals een gewone `docker run`, dus als root) op lege
     opslag → healthy → stock-client-smoketest modus `nieuw` (zonder plugin);
  2. container verwijderen en een koude kopie van /config maken als back-up (`cp -a` in een wegwerpcontainer; staat
     model voor de ZFS-snapshot van de config-dataset, CUSTOM_APP.md "Updaten en terugdraaien");
  3. migratie: de Jelly Leon-image op dezelfde opslag → healthy → smoketest modus `herstart` (zelfde gebruiker en
     item-ID, plugin `compatibel`; de entrypoint maakt 568 eigenaar van /config en /cache);
  4. terugzetten: container verwijderen, /config vervangen door de back-up (merkteken: de pluginmap die alleen de
     Jelly Leon-entrypoint aanmaakt is daarna weg), de upstream-image opnieuw starten → healthy → smoketest modus
     `herstart` (zelfde gebruiker en item-ID, wizard blijft dicht, streamen byte-gelijk);
  5. de mediamap is in alle stappen onaangeroerd.

Beperking (eerlijk): in P0 zijn fork en upstream dezelfde versie (10.11.11), dus er is geen databasemigratie en
"alleen de binary terugzetten" zou hier ook werken. De proef bewijst het terugzetpad zelf en wordt pas onderscheidend
bij de upgrade naar 12.x (ADR-0011), waar de nieuwe versie de database migreert en alleen database + binary samen
terug veilig is. Echte NAS (ZFS-snapshot, TrueNAS `app.update`/terugzetten): NIET GEVALIDEERD.

Alleen standaardbibliotheek; Docker via subprocess zonder shell. Exitcode 0 = alles geslaagd.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from image_lifecycle import Lifecycle, docker, utc_now  # noqa: E402


class RollbackSim(Lifecycle):
    """Hergebruikt de hulpfuncties van de levenscyclustest; alleen het verloop is anders."""

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__(args)
        self.name = self.name.replace("jl-lifecycle-", "jl-rollback-")
        self.backup = self.work / "backup-config"

    def helper(self, *args: str) -> None:
        """Bestandsbewerking als root in een wegwerpcontainer zonder netwerk (bestanden zijn van root of 568)."""
        entrypoint, *rest = args
        docker(
            "run", "--rm", "--network", "none", "--entrypoint", entrypoint, "-v", f"{self.work}:/werk",
            self.args.image, *rest, timeout=300,
        )

    def take_backup(self) -> bool:
        self.helper("/bin/cp", "-a", "/werk/config", "/werk/backup-config")
        ok = (self.backup / "data" / "jellyfin.db").is_file()
        return self.add("koude back-up van /config (model voor de ZFS-snapshot)", ok, f"{self.backup.name}/data/jellyfin.db aanwezig={ok}")

    def fork_plugin_present(self) -> bool:
        """Merkteken van de migratie: alleen de Jelly Leon-entrypoint zet JellyLeon_* in /config/plugins."""
        plugins = self.config / "plugins"
        return plugins.is_dir() and any(plugins.glob("JellyLeon_*"))

    def restore_backup(self) -> bool:
        migrated = self.fork_plugin_present()
        self.add("migratie zichtbaar in /config", migrated, f"Jelly Leon-plugin door de entrypoint geïnstalleerd={migrated}")
        self.helper("/bin/rm", "-rf", "/werk/config")
        self.helper("/bin/cp", "-a", "/werk/backup-config", "/werk/config")
        # Zonder dit merkteken zou een terugzetstap die stilletjes niets doet niet opvallen (de smoketest slaagt dan ook).
        restored = self.config.is_dir() and not self.fork_plugin_present()
        return self.add(
            "back-up teruggezet in /config",
            migrated and restored,
            f"toestand van vóór de migratie (geen Jelly Leon-plugin meer)={restored}",
        )

    def run(self) -> bool:
        for directory in (self.config, self.cache, self.media):
            directory.mkdir(parents=True)
        subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "make_test_media.py"), str(self.media)],
                       check=True, capture_output=True)
        media_before = self.media_fingerprint()
        upstream = self.args.upstream_image
        upstream_version = self.args.upstream_version or self.args.expected_version
        try:
            # 1. bestaande upstream-Jellyfin
            self.start(image=upstream)
            if not self.wait_healthy("upstream, lege opslag"):
                return False
            first = self.smoke("upstream-eerste-start", "nieuw", expect_plugin=False, version=upstream_version)
            if not first:
                return False
            self.remove(self.name)

            # 2. back-up vóór de migratie
            if not self.take_backup():
                return False

            # 3. migratie naar de Jelly Leon-image
            self.start()
            if not self.wait_healthy("Jelly Leon na migratie"):
                return False
            if not self.smoke("jelly-leon-na-migratie", "herstart", first):
                return False
            self.remove(self.name)

            # 4. terugzetten: back-up + oude binary
            if not self.restore_backup():
                return False
            self.start(image=upstream)
            if not self.wait_healthy("upstream na terugzetten"):
                return False
            if not self.smoke(
                "upstream-na-terugzetten", "herstart", first, expect_plugin=False, version=upstream_version
            ):
                return False
            self.add("mediamap onaangeroerd", self.media_fingerprint() == media_before, "eigenaar/rechten ongewijzigd")
        finally:
            self.remove(self.name)
        return bool(self.steps) and all(step["geslaagd"] for step in self.steps)

    def cleanup(self) -> bool:
        self.helper("/bin/rm", "-rf", "/werk/config", "/werk/cache", "/werk/media", "/werk/backup-config")
        return super().cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Terugzetproef B03-013 (Docker, Sim-getest).")
    parser.add_argument("--image", required=True, help="Jelly Leon-image (lokaal gebouwd, bv. jelly-leon:test)")
    parser.add_argument(
        "--upstream-image", required=True,
        help="upstream-image met de basisversie, op digest (bv. de JL_RUNTIME_IMAGE uit de CI)",
    )
    parser.add_argument("--expected-version", required=True, help="versie die de Jelly Leon-server moet melden")
    parser.add_argument(
        "--upstream-version", default="",
        help="versie van de upstream-image (standaard gelijk aan --expected-version; anders bij de 12.x-upgrade)",
    )
    parser.add_argument("--werkmap", default=None, help="map voor tijdelijke opslag (standaard: systeem-tmp)")
    parser.add_argument("--health-timeout", type=float, default=240)
    parser.add_argument("--report", help="pad voor het JSON-rapport")
    parser.add_argument("--opmerking", default="", help="vrije toelichting in het rapport")
    parser.add_argument(
        "--behoud-werkmap", dest="keep_workdir", action="store_true",
        help="werkmap ook bij succes laten staan (bij falen blijft hij altijd staan, ter diagnose)",
    )
    args = parser.parse_args(argv)
    if "@sha256:" not in args.upstream_image:
        print("FOUT: --upstream-image moet op @sha256-digest staan (geen zwevende tag)", file=sys.stderr)
        return 3
    args.verwacht_web_ref = ""
    sim = RollbackSim(args)
    started = utc_now()
    try:
        passed = sim.run()
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        sim.add("uitvoering", False, str(exc)[:500])
        passed = False
    result = {
        "soort": "Sim-getest (Docker op de bouwmachine; geen echte NAS, koude kopie i.p.v. ZFS-snapshot)",
        "image": args.image,
        "upstream_image": args.upstream_image,
        "opmerking": args.opmerking,
        "gestart": started,
        "klaar": utc_now(),
        "geslaagd": passed,
        "stappen": sim.steps,
        "werkmap": str(sim.work),
    }
    if passed and not args.keep_workdir:
        result["werkmap"] += " (opgeruimd)" if sim.cleanup() else " (opruimen mislukt)"
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ok = sum(step["geslaagd"] for step in sim.steps)
    print(f"RESULTAAT: {'GESLAAGD' if passed else 'MISLUKT'} ({ok}/{len(sim.steps)})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
