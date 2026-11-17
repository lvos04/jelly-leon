"""Opslaggrens van de start in deploy/allinone/entrypoint.sh (S-G1-16 deel 1c, ADR-0032 "Opslagdreigingen, deel 1c").

De functies en de tweede fase (als app-gebruiker, vlak vóór de server) worden letterlijk uit het entrypoint gelezen en
met `sh` (dash, net als in de image) uitgevoerd op synthetische mappen; de umask is die van de container (gemeten 0022).
Een gedeelde map moet vóór elke schrijfactie geweigerd worden; een correcte installatie moet blijven starten.
De echte image met een andere gebruiker als aanvaller: tools/jelly-leon/e2e/image_lifecycle.py (CI-job image).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "deploy" / "allinone" / "entrypoint.sh"
VERSIE = "12.4.0-jl.0"


def fase_twee(tmp: Path, data: Path, cache: Path, *, pauze: bool = False) -> str:
    tekst = SCRIPT.read_text(encoding="utf-8")
    # Alle functies van het entrypoint, eenregelig (log, fail) of meerregelig; de rest van het script draait niet.
    functies = "".join(re.findall(r"^[a-z_]+\(\) \{(?: [^\n]*\}\n|\n.*?^\}\n)", tekst, re.MULTILINE | re.DOTALL))
    begin = tekst.index("    unset JELLY_LEON_ENTRYPOINT_STAGE\n") + len("    unset JELLY_LEON_ENTRYPOINT_STAGE\n")
    body = tekst[begin : tekst.index('    exec /jellyfin/jellyfin "$@"', begin)]
    (tmp / "VERSION").write_text(VERSIE + "\n")
    bundel = tmp / "bundel" / "JellyLeon_0.1.0.0"
    bundel.mkdir(parents=True, exist_ok=True)
    (bundel / "Jellyfin.Plugin.JellyLeon.dll").write_bytes(b"synthetische plugin")
    voorwerk = (
        f"set -eu\numask 022\nDATA_DIR='{data}'\nCACHE_DIR='{cache}'\nBUNDLED_PLUGINS='{tmp / 'bundel'}'\n"
        f"IMAGE_VERSION_FILE='{tmp / 'VERSION'}'\nDATAMAP_VERSION_FILE=\"$DATA_DIR/jelly-leon/datamap-versie\"\n"
    )
    # De pauze staat buiten de productiecode: de proef leest de PID en legt dan pas de koppeling (in de container is $$ 1).
    return voorwerk + functies + ('printf "%s\\n" "$$"\nread -r _\n' if pauze else "") + body


def maak(pad: Path, modus: int = 0o755) -> Path:
    """Map met precies deze modus (de umask van de testmachine telt niet mee)."""
    pad.mkdir(parents=True, exist_ok=True)
    pad.chmod(modus)
    return pad


def opzet(tmp: Path, data_modus: int = 0o755) -> tuple[Path, Path, Path]:
    data, cache = maak(tmp / "data", data_modus), maak(tmp / "cache")
    buiten = tmp / "server.db"
    buiten.write_bytes(b"SQLite format 3\x00synthetische kijkgegevens")
    buiten.chmod(0o600)
    return data, cache, buiten


def boom(map_: Path) -> dict[str, tuple[int, str]]:
    """Elke ingang met modus en inhoud of koppelingsdoel: een weigering mag hier niets aan veranderen."""
    uit = {}
    for pad in sorted([map_, *map_.rglob("*")]):
        st = pad.lstat()
        inhoud = str(pad.readlink()) if pad.is_symlink() else pad.read_text() if pad.is_file() else ""
        uit[str(pad.relative_to(map_))] = (st.st_mode, inhoud)
    return uit


def draai(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True, timeout=30, check=False)


def draai_met_koppeling(tmp: Path, data: Path, cache: Path, doel: str) -> subprocess.CompletedProcess[str]:
    """Zoals de proef van deel 1b: de aanvaller legt de koppeling op de tijdelijke naam van de start."""
    proc = subprocess.Popen(  # noqa: S603 - vast lokaal testscript
        ["sh", "-c", fase_twee(tmp, data, cache, pauze=True)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    assert proc.stdout and proc.stdin
    pid = proc.stdout.readline().strip()
    assert pid.isdecimal()
    (data / "jelly-leon" / f"datamap-versie.tmp.{pid}").symlink_to(doel)
    uit, _ = proc.communicate("start\n", timeout=30)
    return subprocess.CompletedProcess(proc.args, proc.returncode, uit, "")


def test_gedeelde_map_met_koppeling_weigert_voor_elke_schrijfactie(tmp_path: Path) -> None:
    """De rode proef van deel 1b: map 0777, koppeling op de tijdelijke naam naar een buiten-database."""
    data, cache, buiten = opzet(tmp_path, 0o777)
    maak(data / "jelly-leon", 0o777)
    voor = buiten.read_bytes()
    proc = draai_met_koppeling(tmp_path, data, cache, "../../server.db")
    assert buiten.read_bytes() == voor, "de start schreef via de koppeling in de buiten-database"
    assert proc.returncode != 0
    assert "voor groep of anderen beschrijfbaar" in proc.stdout
    assert not (data / "jelly-leon" / "datamap-versie").exists()
    assert not (data / "plugins").exists()


def test_tijdelijke_naam_is_niet_voorspelbaar_en_volgt_geen_koppeling(tmp_path: Path) -> None:
    """Ook in een correcte map: de oude naam datamap-versie.tmp.<PID> wordt niet gebruikt (mktemp: exclusief, willekeurig)."""
    data, cache, buiten = opzet(tmp_path)
    maak(data / "jelly-leon")
    voor = buiten.read_bytes()
    proc = draai_met_koppeling(tmp_path, data, cache, "../../server.db")
    assert buiten.read_bytes() == voor
    assert proc.returncode == 0, proc.stdout
    versie = data / "jelly-leon" / "datamap-versie"
    assert not versie.is_symlink()
    assert f"fork_version={VERSIE}" in versie.read_text().splitlines()


@pytest.mark.parametrize(
    ("geval", "melding"),
    [
        ("data-groep", "voor groep of anderen beschrijfbaar (modus 775)"),
        ("eigen-map-anderen", "voor groep of anderen beschrijfbaar (modus 757)"),
        ("pluginmap-gedeeld", "voor groep of anderen beschrijfbaar (modus 777)"),
        ("oude-pluginmap-gedeeld", "voor groep of anderen beschrijfbaar (modus 777)"),
        ("cache-gedeeld", "voor groep of anderen beschrijfbaar (modus 777)"),
        ("eigen-map-koppeling", "is een symbolische koppeling"),
        ("ouder-gedeeld", "voor groep of anderen beschrijfbaar (modus 777)"),
    ],
)
def test_onveilige_opslag_weigert_zonder_iets_te_wijzigen(tmp_path: Path, geval: str, melding: str) -> None:
    ouder = maak(tmp_path / "ouder")
    data, cache, buiten = opzet(ouder)
    maak(data / "jelly-leon")
    (data / "jelly-leon" / "datamap-versie").write_text("fork_version=12.3.0-jl.0\n")
    if geval == "data-groep":
        data.chmod(0o775)
    elif geval == "eigen-map-anderen":
        (data / "jelly-leon").chmod(0o757)
    elif geval == "pluginmap-gedeeld":
        maak(data / "plugins", 0o777)
    elif geval == "oude-pluginmap-gedeeld":
        maak(data / "plugins")
        maak(data / "plugins" / "JellyLeon_0.0.9.0", 0o777)
    elif geval == "cache-gedeeld":
        cache.chmod(0o777)
    elif geval == "eigen-map-koppeling":
        elders = maak(ouder / "elders")
        (data / "jelly-leon" / "datamap-versie").rename(elders / "datamap-versie")
        (data / "jelly-leon").rmdir()
        (data / "jelly-leon").symlink_to(elders)
    elif geval == "ouder-gedeeld":
        ouder.chmod(0o777)
    voor = boom(ouder)
    proc = draai(fase_twee(tmp_path, data, cache))
    assert proc.returncode != 0
    assert melding in proc.stdout + proc.stderr
    assert "Er is niets gewijzigd" in proc.stdout + proc.stderr
    assert boom(ouder) == voor
    assert buiten.read_bytes().endswith(b"synthetische kijkgegevens")


def test_map_van_een_andere_gebruiker_weigert(tmp_path: Path) -> None:
    """/usr is van root: als app-gebruiker (geen root) is dat niet de eigen gegevensmap."""
    proc = draai(fase_twee(tmp_path, Path("/usr"), maak(tmp_path / "cache")))
    assert proc.returncode != 0
    assert "/usr is van gebruiker 0" in proc.stdout + proc.stderr


@pytest.mark.parametrize("eerste_start", [True, False])
def test_correcte_installatie_blijft_starten(tmp_path: Path, eerste_start: bool) -> None:
    """HARDE EIS: eigen mappen 0755 (eerste start of bestaande installatie met oude versie en oude plugin) starten."""
    data, cache, buiten = opzet(tmp_path)
    if not eerste_start:
        maak(data / "jelly-leon")
        (data / "jelly-leon" / "datamap-versie").write_text("fork_version=12.3.0-jl.0\n")
        maak(data / "plugins")
        maak(data / "plugins" / "JellyLeon_0.0.9.0")
        maak(data / "data")
        (data / "data" / "jellyfin.db").write_bytes(b"SQLite format 3\x00kijkgegevens")
    voor_db = (data / "data" / "jellyfin.db").read_bytes() if not eerste_start else b""
    proc = draai(fase_twee(tmp_path, data, cache))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"fork_version={VERSIE}" in (data / "jelly-leon" / "datamap-versie").read_text().splitlines()
    assert (data / "plugins" / "JellyLeon_0.1.0.0" / "Jellyfin.Plugin.JellyLeon.dll").read_bytes() == b"synthetische plugin"
    assert not (data / "plugins" / "JellyLeon_0.0.9.0").exists()
    assert not list((data / "jelly-leon").glob("datamap-versie.tmp*"))
    assert buiten.read_bytes().endswith(b"synthetische kijkgegevens")
    if not eerste_start:
        assert (data / "data" / "jellyfin.db").read_bytes() == voor_db


def test_controle_staat_als_root_voor_de_eigenaarswissel_en_als_app_voor_het_vastleggen() -> None:
    tekst = SCRIPT.read_text(encoding="utf-8")
    fase = tekst.index('if [ "${JELLY_LEON_ENTRYPOINT_STAGE:-}" = "app" ]')
    app = tekst.index('    assert_private_storage "$(id -u)"\n', fase)
    assert app < tekst.index("    record_datamap_version\n", fase)
    root = tekst.index("\nassert_private_storage\n")
    assert tekst.index("  assert_owned_mount \"$dir\"\n") < root < tekst.index('chown -R "$APP_UID:$APP_GID" "$dir"')


@pytest.mark.parametrize(
    "geval", ["map-gedeeld", "map-koppeling", "bestand-koppeling", "bestand-dode-koppeling", "bestand-fifo", "bestand-gedeeld"],
)
def test_downgradecontrole_leest_niet_voor_de_opslaggrens(tmp_path: Path, geval: str) -> None:
    """De eerste versiecontrole (ook vóór de rootfase) mag geen koppeling of FIFO volgen."""
    data, cache, _ = opzet(tmp_path)
    eigen = maak(data / "jelly-leon")
    versie = eigen / "datamap-versie"
    elders = maak(tmp_path / "elders")
    doel = elders / "datamap-versie"
    doel.write_text(f"fork_version={VERSIE}\n")
    if geval == "map-gedeeld":
        eigen.chmod(0o777)
        versie.write_text(f"fork_version={VERSIE}\n")
    elif geval == "map-koppeling":
        eigen.rmdir()
        eigen.symlink_to(elders)
    elif geval == "bestand-gedeeld":
        versie.write_text(f"fork_version={VERSIE}\n")
        versie.chmod(0o666)
    elif geval.startswith("bestand-") and geval != "bestand-fifo":
        versie.symlink_to(doel if geval == "bestand-koppeling" else elders / "ontbreekt")
    else:
        import os

        os.mkfifo(versie)
    tekst = SCRIPT.read_text(encoding="utf-8")
    functies = "".join(re.findall(r"^[a-z_]+\(\) \{(?: [^\n]*\}\n|\n.*?^\}\n)", tekst, re.MULTILINE | re.DOTALL))
    image = tmp_path / "VERSION"
    image.write_text(VERSIE + "\n")
    gelezen = tmp_path / "onveilig-gelezen"
    # Onderschep de leesaanroep: oud volgt de koppeling of zou op de FIFO wachten. Geen echt blokkerend proces.
    script = (
        f"set -eu\nDATA_DIR='{data}'\nCACHE_DIR='{cache}'\nIMAGE_VERSION_FILE='{image}'\n"
        f"DATAMAP_VERSION_FILE='{versie}'\n" + functies
        + f"sed() {{ : > '{gelezen}'; printf 'fork_version={VERSIE}\\n'; }}\n"
        + "assert_not_downgrade\n"
    )
    voor = boom(tmp_path) if geval != "bestand-fifo" else None
    proc = draai(script)
    assert not gelezen.exists(), "de versiecontrole las de onveilige datamap vóór de opslagcontrole"
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "TrueNAS" in proc.stdout + proc.stderr
    if voor is not None:
        assert boom(tmp_path) == voor
