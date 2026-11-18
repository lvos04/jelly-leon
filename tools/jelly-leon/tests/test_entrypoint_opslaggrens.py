"""Opslaggrens van de start in deploy/allinone/entrypoint.sh (S-G1-16 deel 1c, ADR-0032 "Opslagdreigingen, deel 1c").

De functies en de tweede fase (als app-gebruiker, vlak vóór de server) worden letterlijk uit het entrypoint gelezen en
met `sh` (dash, net als in de image) uitgevoerd op synthetische mappen; de umask is die van de container (gemeten 0022).
Een gedeelde map moet vóór elke schrijfactie geweigerd worden; een correcte installatie moet blijven starten.
De echte image met een andere gebruiker als aanvaller: tools/jelly-leon/e2e/image_lifecycle.py (CI-job image).
"""

from __future__ import annotations

import os
import re
import struct
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "deploy" / "allinone" / "entrypoint.sh"
VERSIE = "12.4.0-jl.0"


def fase_twee(
    tmp: Path, data: Path, cache: Path, *, pauze: bool = False, body: str | None = None, mountinfo: str | None = None
) -> str:
    tekst = SCRIPT.read_text(encoding="utf-8")
    # Alle functies van het entrypoint, eenregelig (log, fail) of meerregelig; de rest van het script draait niet.
    functies = "".join(re.findall(r"^[a-z_]+\(\) \{(?: [^\n]*\}\n|\n.*?^\}\n)", tekst, re.MULTILINE | re.DOTALL))
    begin = tekst.index("    unset JELLY_LEON_ENTRYPOINT_STAGE\n") + len("    unset JELLY_LEON_ENTRYPOINT_STAGE\n")
    if body is None:
        body = tekst[begin : tekst.index('    exec /jellyfin/jellyfin "$@"', begin)]
    (tmp / "VERSION").write_text(VERSIE + "\n")
    bundel = tmp / "bundel" / "JellyLeon_0.1.0.0"
    bundel.mkdir(parents=True, exist_ok=True)
    (bundel / "Jellyfin.Plugin.JellyLeon.dll").write_bytes(b"synthetische plugin")
    voorwerk = (
        f"set -eu\numask 022\nDATA_DIR='{data}'\nCACHE_DIR='{cache}'\nBUNDLED_PLUGINS='{tmp / 'bundel'}'\n"
        f"IMAGE_VERSION_FILE='{tmp / 'VERSION'}'\nDATAMAP_VERSION_FILE=\"$DATA_DIR/jelly-leon/datamap-versie\"\n"
        f"MOUNTINFO='{mountinfo or standaard_mountinfo(tmp)}'\n"
    )
    # De pauze staat buiten de productiecode: de proef leest de PID en legt dan pas de koppeling (in de container is $$ 1).
    return voorwerk + functies + ('printf "%s\\n" "$$"\nread -r _\n' if pauze else "") + body


def standaard_mountinfo(tmp: Path) -> Path:
    """Alleen een overlay-wortel, zoals in de container zonder tmpfs: de uitkomst hangt niet af van de testmachine."""
    pad = tmp / "mountinfo-standaard"
    pad.write_text("21 1 0:20 / / rw,relatime - overlay overlay rw\n")
    return pad


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
    assert app < tekst.index("    repair_plugin_dirs\n", fase) < tekst.index("    record_datamap_version\n", fase)
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
        os.mkfifo(versie)
    tekst = SCRIPT.read_text(encoding="utf-8")
    functies = "".join(re.findall(r"^[a-z_]+\(\) \{(?: [^\n]*\}\n|\n.*?^\}\n)", tekst, re.MULTILINE | re.DOTALL))
    image = tmp_path / "VERSION"
    image.write_text(VERSIE + "\n")
    gelezen = tmp_path / "onveilig-gelezen"
    # Onderschep de leesaanroep: oud volgt de koppeling of zou op de FIFO wachten. Geen echt blokkerend proces.
    script = (
        f"set -eu\nDATA_DIR='{data}'\nCACHE_DIR='{cache}'\nIMAGE_VERSION_FILE='{image}'\nBUNDLED_PLUGINS='{tmp_path}/geen'\n"
        f"MOUNTINFO='{standaard_mountinfo(tmp_path)}'\nDATAMAP_VERSION_FILE='{versie}'\n" + functies
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


KIJKGEGEVENS = b"SQLite format 3\x00synthetische kijkgegevens"


@pytest.mark.parametrize(
    "geval",
    [
        "dll-koppeling",  # de proef van R-TECH-1
        "dll-dode-koppeling",
        "dll-harde-koppeling",
        "dll-map",
        "dll-fifo",  # oud (1d): cmp wachtte hierop
        "manifest-koppeling",  # meta.json schrijft de server zelf bij de start
        "manifest-harde-koppeling",  # ontdubbelen of terugzetten met behoud van koppelingen (R-HARDE-EIS-2)
        "tweede-naam",  # ontdubbelen binnen de map (R-VEILIG-4)
        "oude-versie-koppeling",
    ],
)
def test_vreemde_ingang_in_de_eigen_pluginmap_wordt_hersteld_zonder_te_volgen(tmp_path: Path, geval: str) -> None:
    """BN-2 (deel 1f; R-HARDE-EIS-2, R-VEILIG-4): een ingang in een eigen pluginmap die geen gewoon bestand met één naam
    is, legt de mediaserver niet meer stil. De app-fase verwijdert de ingang zelf (unlink volgt niets; vóór cmp, het
    vastleggen van de versie of een schrijfactie) en plaatst de DLL als nieuw bestand. Het doel van een koppeling en de
    andere naam van een harde koppeling blijven byte-gelijk; daarbuiten verandert niets."""
    ouder = maak(tmp_path / "ouder")
    data, cache, buiten = opzet(ouder)
    plug = maak(maak(data / "plugins") / ("JellyLeon_0.0.9.0" if geval.startswith("oude-") else "JellyLeon_0.1.0.0"))
    dll, manifest = plug / "Jellyfin.Plugin.JellyLeon.dll", plug / "meta.json"
    if geval in ("dll-koppeling", "oude-versie-koppeling"):
        dll.symlink_to(buiten)
    elif geval == "dll-dode-koppeling":
        dll.symlink_to(ouder / "ontbreekt.db")
    elif geval == "dll-harde-koppeling":
        os.link(buiten, dll)
    elif geval == "dll-map":
        maak(dll)
    elif geval == "dll-fifo":
        os.mkfifo(dll)
    else:
        dll.write_bytes(b"oude plugin")
        if geval == "manifest-koppeling":
            manifest.symlink_to(buiten)
        elif geval == "manifest-harde-koppeling":
            os.link(buiten, manifest)
        else:
            os.link(dll, plug / "kopie.dll.bak")
    buiten_voor = {p: p.lstat() for p in ouder.iterdir()}
    proc = draai(fase_twee(tmp_path, data, cache))
    uit = proc.stdout + proc.stderr
    assert buiten.read_bytes() == KIJKGEGEVENS, "de start schreef via het pluginbestand in de serverdatabase"
    assert proc.returncode == 0, uit
    nieuw = data / "plugins" / "JellyLeon_0.1.0.0"
    assert sorted(p.name for p in nieuw.iterdir()) == ["Jellyfin.Plugin.JellyLeon.dll"]
    dll_nu = nieuw / "Jellyfin.Plugin.JellyLeon.dll"
    assert not dll_nu.is_symlink() and dll_nu.read_bytes() == b"synthetische plugin" and dll_nu.stat().st_nlink == 1
    assert not (data / "plugins" / "JellyLeon_0.0.9.0").exists()
    assert buiten.stat().st_nlink == 1 and sorted(ouder.iterdir()) == sorted(buiten_voor)
    assert all(p.lstat().st_mode == s.st_mode for p, s in buiten_voor.items())
    assert uit.count("hersteld zonder een koppeling te volgen") == 1, uit


def test_map_met_inhoud_in_de_eigen_pluginmap_weigert_zonder_wijziging(tmp_path: Path) -> None:
    """Wat de start niet veilig kan opruimen (een map met inhoud), blijft een weigering vóór elke wijziging, als root vóór
    de eigenaarswissel; de melding noemt de veilige weg en waarschuwt bij een snapshot (R-HARDE-EIS-2)."""
    ouder = maak(tmp_path / "ouder")
    data, cache, buiten = opzet(ouder)
    plug = maak(maak(data / "plugins") / "JellyLeon_0.1.0.0")
    (plug / "meta.json").symlink_to(buiten)
    (maak(plug / "sub") / "x.dll").write_bytes(b"x")
    voor = boom(ouder)
    for body in (None, "assert_private_storage\nprintf 'EIGENAARSWISSEL\\n'\n"):
        proc = draai(fase_twee(tmp_path, data, cache, body=body))
        uit = proc.stdout + proc.stderr
        assert proc.returncode != 0 and "EIGENAARSWISSEL" not in uit, uit
        assert "is een map met inhoud in de eigen pluginmap" in uit and "Er is niets gewijzigd" in uit
        assert "Veilige weg" in uit and "kijkgegevens van na die snapshot verloren gaan" in uit
        assert boom(ouder) == voor
    assert buiten.read_bytes() == KIJKGEGEVENS


def test_rootfase_laat_herstel_aan_de_app_fase_en_volgt_geen_koppeling(tmp_path: Path) -> None:
    """Als root (vóór `chown -R`, zie de volgordetest) blijft een gekoppeld pluginbestand staan; het herstel doet de
    app-fase. Root leest of schrijft er niets doorheen."""
    data, cache, buiten = opzet(tmp_path)
    dll = maak(maak(data / "plugins") / "JellyLeon_0.1.0.0") / "Jellyfin.Plugin.JellyLeon.dll"
    dll.symlink_to(buiten)
    proc = draai(fase_twee(tmp_path, data, cache, body="assert_private_storage\nprintf 'EIGENAARSWISSEL\\n'\n"))
    assert proc.returncode == 0 and "EIGENAARSWISSEL" in proc.stdout, proc.stdout + proc.stderr
    assert dll.is_symlink() and buiten.read_bytes() == KIJKGEGEVENS


def test_elke_snapshotraad_waarschuwt_voor_verlies_van_kijkgegevens() -> None:
    """R-HARDE-EIS-2: geen melding raadt het terugzetten van een snapshot aan zonder de waarschuwing dat kijkgegevens van
    na die snapshot verloren gaan, en elke zo'n melding noemt eerst een veilige weg."""
    meldingen = [r for r in SCRIPT.read_text(encoding="utf-8").splitlines() if 'fail "' in r and "snapshot" in r]
    assert len(meldingen) >= 5
    for melding in meldingen:
        assert "kijkgegevens van na die snapshot" in melding and "Veilige weg" in melding, melding


@pytest.mark.parametrize("soort", ["koppeling", "harde-koppeling"])
def test_plaatsen_volgt_nooit_een_bestaande_ingang(tmp_path: Path, soort: str) -> None:
    """Ook los van de weigering: de nieuwe DLL ontstaat als nieuw bestand naast het doel en vervangt de ingang zelf."""
    data, cache, buiten = opzet(tmp_path)
    doel = maak(maak(data / "plugins") / "JellyLeon_0.1.0.0") / "Jellyfin.Plugin.JellyLeon.dll"
    if soort == "koppeling":
        doel.symlink_to(buiten)
    else:
        os.link(buiten, doel)
    bron = tmp_path / "nieuw.dll"
    bron.write_bytes(b"nieuwe plugin")
    proc = draai(fase_twee(tmp_path, data, cache, body=f"place_file '{bron}' '{doel}'\n"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert buiten.read_bytes() == KIJKGEGEVENS
    assert not doel.is_symlink() and doel.read_bytes() == b"nieuwe plugin" and doel.stat().st_nlink == 1
    assert sorted(p.name for p in doel.parent.iterdir()) == [doel.name]


@pytest.mark.parametrize("dll", [b"oude plugin", b"synthetische plugin"])
def test_bestaande_pluginmap_van_deze_versie_blijft_starten(tmp_path: Path, dll: bytes) -> None:
    """HARDE EIS: een correcte bestaande installatie (gewone DLL en meta.json van de server, de eigen pluginconfiguratie
    als gewoon bestand) start ongewijzigd door; bestanden van andere plugins in plugins/configurations, ook een
    koppeling, zijn geen reden om te weigeren (deel 1f)."""
    data, cache, buiten = opzet(tmp_path)
    plug = maak(maak(data / "plugins") / "JellyLeon_0.1.0.0")
    (plug / "Jellyfin.Plugin.JellyLeon.dll").write_bytes(dll)
    (plug / "meta.json").write_text('{"status": "Active"}')
    conf = maak(data / "plugins" / "configurations")
    (conf / XML).write_text("<PluginConfiguration />")
    (conf / "Andere.Plugin.xml").symlink_to(XML)
    proc = draai(fase_twee(tmp_path, data, cache))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    nieuw = plug / "Jellyfin.Plugin.JellyLeon.dll"
    assert nieuw.read_bytes() == b"synthetische plugin" and nieuw.stat().st_nlink == 1
    assert (plug / "meta.json").read_text() == '{"status": "Active"}'
    assert sorted(p.name for p in plug.iterdir()) == ["Jellyfin.Plugin.JellyLeon.dll", "meta.json"]
    assert ("geïnstalleerd" in proc.stdout) == (dll != b"synthetische plugin")
    assert (conf / XML).read_text() == "<PluginConfiguration />" and (conf / "Andere.Plugin.xml").is_symlink()
    assert buiten.read_bytes() == KIJKGEGEVENS


XML = "Jellyfin.Plugin.JellyLeon.xml"


@pytest.mark.parametrize(
    ("geval", "melding"),
    [
        ("xml-koppeling", "is geen gewoon bestand met één naam"),  # de proef van R-VEILIG-1
        ("xml-dode-koppeling", "is geen gewoon bestand met één naam"),
        ("xml-harde-koppeling", "is geen gewoon bestand met één naam"),
        ("xml-fifo", "is geen gewoon bestand met één naam"),
        ("xml-map", "is geen gewoon bestand met één naam"),
        ("configmap-gedeeld", "voor groep of anderen beschrijfbaar (modus 777)"),
        ("configmap-koppeling", "is een symbolische koppeling"),
    ],
)
def test_pluginconfiguratie_die_de_server_schrijft_weigert_zonder_wijziging(tmp_path: Path, geval: str, melding: str) -> None:
    """R-VEILIG-1 (deel 1f): de server leest plugins/configurations/Jellyfin.Plugin.JellyLeon.xml en schrijft er bij een
    mislukte lezing met FileMode.Create een nieuwe in (volgt een koppeling). Die map en dat bestand vallen nu onder de
    startgrens; de serverdatabase en elke ingang blijven gelijk."""
    ouder = maak(tmp_path / "ouder")
    data, cache, buiten = opzet(ouder)
    plugins = maak(data / "plugins")
    if geval == "configmap-koppeling":
        elders = maak(ouder / "elders")
        (plugins / "configurations").symlink_to(elders)
        conf = elders
    else:
        conf = maak(plugins / "configurations", 0o777 if geval == "configmap-gedeeld" else 0o755)
    xml = conf / XML
    if geval in ("xml-koppeling", "configmap-koppeling"):
        xml.symlink_to(buiten)
    elif geval == "xml-dode-koppeling":
        xml.symlink_to(ouder / "ontbreekt.db")
    elif geval == "xml-harde-koppeling":
        os.link(buiten, xml)
    elif geval == "xml-fifo":
        os.mkfifo(xml)
    elif geval == "xml-map":
        maak(xml)
    else:
        xml.write_text("<PluginConfiguration />")
    voor = boom(ouder)
    proc = draai(fase_twee(tmp_path, data, cache))
    uit = proc.stdout + proc.stderr
    assert buiten.read_bytes() == KIJKGEGEVENS, "de start of de server zou via de pluginconfiguratie schrijven"
    assert proc.returncode != 0, uit
    assert melding in uit
    assert "Er is niets gewijzigd" in uit
    assert boom(ouder) == voor


def test_rootfase_weigert_een_gekoppelde_pluginconfiguratie_voor_de_eigenaarswissel(tmp_path: Path) -> None:
    data, cache, buiten = opzet(tmp_path)
    (maak(maak(data / "plugins") / "configurations") / XML).symlink_to(buiten)
    proc = draai(fase_twee(tmp_path, data, cache, body="assert_private_storage\nprintf 'EIGENAARSWISSEL\\n'\n"))
    assert proc.returncode != 0
    assert "EIGENAARSWISSEL" not in proc.stdout
    assert "is geen gewoon bestand met één naam" in proc.stdout + proc.stderr


def mountinfo(tmp: Path, *regels: str) -> str:
    """Een synthetische /proc/self/mountinfo (in de container leest de start de echte)."""
    pad = tmp / "mountinfo"
    pad.write_text("21 1 0:20 / / rw,relatime - overlay overlay rw\n" + "".join(regels))
    return str(pad)


def tmpfs_regel(punt: Path, wortel: str = "/") -> str:
    """Zoals Docker een tmpfs uit het formulier (alleen size) in mountinfo zet."""
    return f"900 21 0:99 {wortel} {punt} rw,nosuid,nodev,noexec,relatime - tmpfs tmpfs rw,size=512000k,inode64\n"


@pytest.mark.parametrize("modus", [0o1777, 0o777, 0o755])
def test_eigen_tmpfs_als_cache_start_met_de_modus_van_docker_of_truenas(tmp_path: Path, modus: int) -> None:
    """BN-1 optie B (R-HARDE-EIS-1, deel 1f): /cache als tmpfs bestaat alleen in deze container. Een eigen, bij de start lege
    tmpfs op het koppelpunt /cache start, ook met de modus die Docker of TrueNAS meegeeft (de image: 1777)."""
    data, cache, buiten = opzet(tmp_path)
    cache.chmod(modus)
    proc = draai(fase_twee(tmp_path, data, cache, mountinfo=mountinfo(tmp_path, tmpfs_regel(cache))))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"fork_version={VERSIE}" in (data / "jelly-leon" / "datamap-versie").read_text().splitlines()
    assert not any(cache.iterdir()), "de start schrijft niets in /cache"
    assert buiten.read_bytes() == KIJKGEGEVENS


@pytest.mark.parametrize("geval", ["hostmap", "submap", "gevuld", "geen-tmpfs", "data-als-tmpfs"])
def test_tmpfs_die_niet_alleen_van_de_container_is_blijft_streng(tmp_path: Path, geval: str) -> None:
    """Niet op naam: een gekoppelde map van een host-tmpfs (wortel niet "/"), een map ín een tmpfs, een al gevulde tmpfs of
    een gewone map met 1777 wordt geweigerd; /config blijft even streng, ook als tmpfs. Bij een tmpfs wijst de melding
    niet naar een dataset (R-HARDE-EIS-1)."""
    data, cache, buiten = opzet(tmp_path)
    regels = {
        "hostmap": tmpfs_regel(cache, "/gedeeld"),
        "submap": tmpfs_regel(tmp_path),
        "gevuld": tmpfs_regel(cache),
        "geen-tmpfs": "",
        "data-als-tmpfs": tmpfs_regel(data),
    }
    (data if geval == "data-als-tmpfs" else cache).chmod(0o1777)
    if geval == "gevuld":
        (cache / "van-een-ander").write_text("x")
    script = fase_twee(tmp_path, data, cache, mountinfo=mountinfo(tmp_path, regels[geval]))
    voor = boom(tmp_path)
    proc = draai(script)
    uit = proc.stdout + proc.stderr
    assert proc.returncode != 0, uit
    assert "voor groep of anderen beschrijfbaar (modus 1777)" in uit and "Er is niets gewijzigd" in uit
    assert ("werkgeheugen (tmpfs)" in uit) == (geval != "geen-tmpfs")
    assert ("Datasets → de dataset van deze map" in uit) == (geval == "geen-tmpfs")
    assert boom(tmp_path) == voor


def overerfbare_acl(map_: Path, groep: int) -> None:
    """Zet een POSIX default-ACL (u::rwx, g::<groep>, m::<groep>, o::r-x) zonder setfacl: het xattr-formaat van de kernel,
    versie 2, daarna per regel tag, rechten en id (-1 voor de eigenaar-, groeps-, masker- en anderenregel)."""
    regels = [(0x01, 7), (0x04, groep), (0x10, groep), (0x20, 5)]
    waarde = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", tag, recht, 0xFFFFFFFF) for tag, recht in regels)
    os.setxattr(map_, "system.posix_acl_default", waarde)


def staat(map_: Path) -> dict[str, tuple[int, int, int, str, bytes]]:
    """Modus, eigenaar, groep, inhoud of koppelingsdoel en overerfbare ACL van elke ingang (bytevergelijking)."""
    uit = {}
    for pad in sorted([map_, *map_.rglob("*")]):
        st = pad.lstat()
        inhoud = str(pad.readlink()) if pad.is_symlink() else pad.read_text() if pad.is_file() else ""
        acl = os.getxattr(pad, "system.posix_acl_default") if pad.is_dir() and "system.posix_acl_default" in os.listxattr(pad) else b""
        uit[str(pad.relative_to(map_))] = (st.st_mode, st.st_uid, st.st_gid, inhoud, acl)
    return uit


@pytest.mark.parametrize("fase", ["app", "root"])
def test_overerfbare_acl_weigert_voor_elke_wijziging(tmp_path: Path, fase: str) -> None:
    """R-VEILIG-3 (deel 1f): /config 0755 met alleen een overerfbare ACL-regel die nieuwe mappen schrijfrecht voor de groep
    geeft. De start weigert vóór elke wijziging (als root vóór de eigenaarswissel, als app-gebruiker vóór herstel en
    vastleggen): eigenaar, rechten, ACL en inhoud byte-gelijk, geen proefmap achter."""
    ouder = maak(tmp_path / "ouder")
    data, cache, buiten = opzet(ouder)
    (maak(data / "data") / "jellyfin.db").write_bytes(KIJKGEGEVENS)
    overerfbare_acl(data, 7)
    assert oct(data.stat().st_mode & 0o777) == "0o755"
    body = None if fase == "app" else "assert_private_storage\nassert_new_dirs_private\nprintf 'EIGENAARSWISSEL\\n'\n"
    script = fase_twee(tmp_path, data, cache, body=body)
    voor = staat(ouder)
    proc = draai(script)
    uit = proc.stdout + proc.stderr
    assert proc.returncode != 0 and "EIGENAARSWISSEL" not in uit, uit
    assert "door een overerfbare ACL-regel van die map" in uit and "Er is niets gewijzigd" in uit
    assert staat(ouder) == voor
    assert buiten.read_bytes() == KIJKGEGEVENS


@pytest.mark.parametrize("geval", ["acl-zonder-schrijfrecht", "bestaande-installatie"])
def test_overerfbare_acl_die_niets_opent_blijft_starten(tmp_path: Path, geval: str) -> None:
    """Geen nieuwe strengheid: een overerfbare ACL zonder schrijfrecht voor groep of anderen, of een bestaande installatie
    waarin de start geen map meer aanmaakt, start door."""
    data, cache, buiten = opzet(tmp_path)
    if geval == "bestaande-installatie":
        maak(data / "jelly-leon")
        maak(maak(data / "plugins") / "JellyLeon_0.1.0.0")
    overerfbare_acl(data, 7 if geval == "bestaande-installatie" else 5)
    proc = draai(fase_twee(tmp_path, data, cache))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not list(data.glob(".jelly-leon-proef.*"))
    assert all(oct(m.stat().st_mode & 0o777) == "0o755" for m in (data / "jelly-leon", data / "plugins"))


def test_proef_op_overerving_staat_voor_elke_wijziging() -> None:
    tekst = SCRIPT.read_text(encoding="utf-8")
    root = tekst.index("\nassert_private_storage\nassert_new_dirs_private\n")
    assert root < tekst.index('chown -R "$APP_UID:$APP_GID" "$dir"')
    fase = tekst.index('if [ "${JELLY_LEON_ENTRYPOINT_STAGE:-}" = "app" ]')
    app = tekst.index('    assert_private_storage "$(id -u)"\n    assert_new_dirs_private\n', fase)
    assert app < tekst.index("    repair_plugin_dirs\n", fase)
