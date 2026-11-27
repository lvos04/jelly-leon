"""Afzonderlijke testclients voor Watch Together. Alleen de eigen container-ID's worden opgeruimd."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import struct
import subprocess
import tarfile
import tempfile
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from . import android, meetslot, web
from .clientmatrix import _inloggen_telefoon
from .corpus.manifest import sha256_bestand
from .desktop import BINARY, NODE_IMAGE
from .stock import WERK, StockServer, docker
from .watchmeting import nulproef

ANDROID_KLOK = web.WEB.parent / "android-klok"
# Vaste TCP-doorvoer naar de testserver of naar de debugpoort van de eigen desktop.
DOORVOER = """
const net = require('node:net');
const [luister, doel, poort] = process.argv.slice(1);
net.createServer(client => {
    const server = net.connect(Number(poort), doel);
    client.on('error', () => server.destroy());
    server.on('error', () => client.destroy());
    client.on('close', () => server.destroy());
    server.on('close', () => client.destroy());
    client.pipe(server).pipe(client);
}).listen(Number(luister));
"""
BEPERKT = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]


def tijdelijk(stapel: ExitStack, *args: str) -> str:
    cid = docker("run", "-d", *args).stdout.strip()
    stapel.callback(docker, "rm", "-f", "-v", cid)
    return cid


def lokaal_adres(cid: str, poort: int) -> str:
    binding = docker("port", cid, f"{poort}/tcp").stdout.strip()
    return "http://" + binding


@contextmanager
def netwerk(server: StockServer):
    naam = "b03020-" + uuid.uuid4().hex
    net = docker("network", "create", naam).stdout.strip()
    try:
        docker("network", "connect", "--alias", "testserver", net, server.container_id)
        try:
            yield naam
        finally:
            docker("network", "disconnect", net, server.container_id)
    finally:
        docker("network", "rm", net)


def lokaal_netembeeld(stapel: ExitStack) -> tuple[str, str] | None:
    """Verpak de lokale tc, sleep en hun ELF-bibliotheken voor uitvoering in een eigen container."""
    ldd_pad = shutil.which("ldd")
    if not ldd_pad:
        return None
    bestanden = {}
    for naam in ("tc", "sleep"):
        binair = shutil.which(naam)
        if not binair:
            return None
        bestanden["usr/bin/" + naam] = Path(binair)
        ldd = subprocess.run([ldd_pad, binair], text=True, capture_output=True, timeout=10, check=False)
        if ldd.returncode or "not found" in ldd.stdout:
            return None
        for lib in re.findall(r"(/[^\s()]+)", ldd.stdout):
            bestanden[lib.lstrip("/")] = Path(lib)
    with tempfile.TemporaryDirectory(dir=WERK) as bouw:
        pakket = Path(bouw) / "gereedschap.tar"
        with tarfile.open(pakket, "w", format=tarfile.USTAR_FORMAT) as tar:
            for naam, bron in sorted(bestanden.items()):
                info = tarfile.TarInfo(naam)
                info.size, info.mode = bron.stat().st_size, 0o755
                with bron.open("rb") as f:
                    tar.addfile(info, f)
        som = sha256_bestand(pakket)
        # Het unieke label identificeert uitsluitend de image van deze meetpoging voor het opruimen.
        beeld = docker("image", "import", "--change", "LABEL b03020-proef=" + uuid.uuid4().hex,
                       "--change", "ENV PATH=/usr/bin:/usr/sbin", str(pakket)).stdout.strip()
        stapel.callback(docker, "image", "rm", beeld)
    return beeld, som


@contextmanager
def netem(server: StockServer, net: str, image: str | None = None):
    """De proef en B's doorvoer delen één nieuw netwerknamespace. Alleen daarin is NET_ADMIN beschikbaar."""
    with ExitStack() as stapel:
        poort = 8097
        # tc uit de stockimage. Een ontbrekend programma, kernelmodule of recht wordt als S3-blokkade geboekt.
        try:
            cid = tijdelijk(stapel, "--network", net, "--cap-drop", "ALL", "--cap-add", "NET_ADMIN", "--security-opt",
                            "no-new-privileges", "-p", f"{urlsplit(server.url).hostname}::{poort}",
                            "--entrypoint", "sleep", image or server.image, "infinity")
        except subprocess.CalledProcessError as fout:
            yield None, {"status": "niet gemeten", "reden": "eigen proefcontainer met NET_ADMIN kon niet starten",
                         "exitcode_docker": fout.returncode}
            return
        proef = docker("exec", cid, "tc", "qdisc", "add", "dev", "eth0", "root", "netem", "delay", "80ms", "20ms",
                       "loss", "1%", check=False)
        if proef.returncode == 127 and image is None:
            stapel.close()
            try:
                hulpmiddel = lokaal_netembeeld(stapel)
            except (OSError, subprocess.SubprocessError) as fout:
                yield None, {"status": "niet gemeten", "stock_tc_exit": 127,
                             "reden": "eigen tc-image kon niet worden gemaakt", "foutsoort": type(fout).__name__}
                return
            if hulpmiddel:
                beeld, som = hulpmiddel
                with netem(server, net, beeld) as (url, waarneming):
                    yield url, {**waarneming, "stock_tc_exit": 127, "gereedschap_sha256": som}
                return
        if proef.returncode:
            yield None, {"status": "niet gemeten", "reden": "tc netem niet beschikbaar in de proefcontainer",
                         "exitcode_tc": proef.returncode, "image": image or server.image}
            return
        qdisc = docker("exec", cid, "tc", "qdisc", "show", "dev", "eth0").stdout
        if not all(x in qdisc for x in ("netem", "80ms", "20ms", "1%")):
            raise ValueError("S3: netwerkcondities niet bevestigd in de proefcontainer")
        tijdelijk(stapel, "--network", f"container:{cid}", *BEPERKT, NODE_IMAGE, "node", "-e", DOORVOER,
                  str(poort), "testserver", "8096")
        yield lokaal_adres(cid, poort), {"status": "tc gecontroleerd", "vertraging_ms": 80, "spreiding_ms": 20,
                                          "verlies_pct": 1, "image": image or server.image}


@contextmanager
def desktop(server: StockServer, net: str, build: Path, image: str, werk: Path):
    if not (build / BINARY).is_file():
        raise ValueError("desktopbuild ontbreekt")
    scherm = werk / "xvfb"
    scherm.mkdir(exist_ok=True)
    with ExitStack() as stapel:
        cid = tijdelijk(stapel, "--network", net, *BEPERKT, "--shm-size", "1g", "--memory", "2g", "--cpus", "2",
                        "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", "-e", "DISPLAY=:99",
                        "-e", "QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox", "-v", f"{build.resolve()}:/out:ro",
                        "-v", f"{scherm}:/scherm", "-p", f"{urlsplit(server.url).hostname}::9223", image,
                        "sh", "-c", "Xvfb :99 -screen 0 1280x720x24 -fbdir /scherm >/dev/null 2>&1 & sleep 2; "
                        "exec /out/build/src/jellyfin-desktop --fullscreen --remote-debugging-port 9222")
        tijdelijk(stapel, "--network", f"container:{cid}", *BEPERKT, NODE_IMAGE, "node", "-e", DOORVOER,
                  "9223", urlsplit(server.url).hostname, "9222")
        yield {"cdp": lokaal_adres(cid, 9223), "xwd": str(scherm / "Xvfb_screen0"), "desktopUrl": "http://testserver:8096",
               "desktop_image_id": docker("inspect", "--format", "{{.Image}}", cid).stdout.strip(), "cid": cid}


def adb_klok(ruw: bytes, voor: float, na: float) -> dict:
    breedte, hoogte, formaat = struct.unpack_from("<III", ruw)
    kop = len(ruw) - breedte * hoogte * 4
    if formaat not in (1, 2) or kop not in (12, 16) or breedte < 160 or hoogte < 100:
        raise ValueError("onbekend adb-screencapformaat")
    rij = kop + hoogte // 2 * breedte * 4
    frame = sum(int(ruw[rij + int((i + .45) * breedte / 16) * 4] >= 128) << i for i in range(16))
    periode = 1001 / 24
    cycli = round(((voor + na) / (2 * periode) - frame) / 65536)
    return {"voor_ms": voor, "na_ms": na, "klok_ms": (frame + 65536 * cycli) * periode}


def bouw_klok(werk: Path) -> Path:
    """Kleine offline test-app zonder permissies. De eenmalige ondertekening verdwijnt met de werkmap."""
    bouw = werk / "android-klok"
    bouw.mkdir()
    sdk = android.SDK / "build-tools/35.0.0"
    bibliotheek = str(android.SDK / "platforms/android-35/android.jar")
    apk = bouw / "klok.apk"
    getekend = bouw / "getekend" / apk.name
    getekend.parent.mkdir()

    def voer(*args, env=None):
        subprocess.run(args, cwd=bouw, capture_output=True, check=True, timeout=120, env=env)

    voer("javac", "--release", "8", "-classpath", bibliotheek, "-d", str(bouw), str(ANDROID_KLOK / "Meetklok.java"))
    voer(sdk / "d8", "--min-api", "26", "--lib", bibliotheek, "--output", bouw, *sorted(bouw.rglob("*.class")))
    voer(sdk / "aapt2", "link", "-o", apk, "-I", bibliotheek, "--manifest", ANDROID_KLOK / "AndroidManifest.xml")
    with zipfile.ZipFile(apk, "a") as archief:
        archief.write(bouw / "classes.dex", "classes.dex")
    voer(sdk / "zipalign", "-f", "4", apk, "uitgelijnd.apk")
    env = {**os.environ, "B03_EENMALIG": secrets.token_urlsafe(24)}
    voer("keytool", "-genkeypair", "-alias", "meetklok", "-dname", "CN=Test", "-keyalg", "RSA", "-validity", "1",
         "-keystore", "meting.p12", "-storepass:env", "B03_EENMALIG", env=env)
    voer(sdk / "apksigner", "sign", "--ks", "meting.p12", "--ks-pass", "env:B03_EENMALIG",
         "--out", getekend, "uitgelijnd.apk", env=env)
    return getekend


def adb_nulproef(werk: Path) -> dict:
    """Eigen telefoonemulator met eigen ADB-server in een Docker-bridge. Er is geen host-ADB-verbinding."""
    if not Path("/dev/kvm").exists() or not (android.SDK / "emulator/emulator").is_file():
        return {"status": "niet gemeten", "reden": "KVM of lokaal emulator-SDK ontbreekt"}
    # Deze kalibratie is klaar en opgeruimd voordat de tijdgevoelige groepsruns beginnen.
    with meetslot.exclusief_slot("gradle.lock"), ExitStack() as stapel:
        android.maak_avd("telefoon", werk / "avd")
        emu = android.Emulator("telefoon", netwerk="bridge", avd_map=werk / "avd")
        stapel.callback(emu.stop)
        apk = bouw_klok(werk)
        emu.start(apk.parent)
        emu.adb("install", "/apk/klok.apk", check=True)
        emu.adb("shell", "am", "start", "-W", "-n", "test.b03.klok/.Meetklok", check=True)
        time.sleep(3)
        opnamen = []
        for _ in range(15):
            voor = time.time_ns() / 1e6
            p = subprocess.run(["docker", "exec", "-u", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", emu.cid,
                                str(android.SDK / "platform-tools/adb"), "exec-out", "screencap"],
                               timeout=15, capture_output=True, check=True)
            na = time.time_ns() / 1e6
            opnamen.append(adb_klok(p.stdout, voor, na))
        return nulproef(opnamen)


def android_ready_uitkomst(groep: str, sessie: str, serverlog: str, spoor: dict) -> dict:
    """Koppel uitsluitend de Ready-timeout van deze groep aan de geauthenticeerde Android-sessie."""
    vertragingen = []
    patroon = r'Group "?([\da-f-]+)"? waited (\d+) ms for session\(s\) (.*?) to report ready, giving up'
    for gid, duur, sessies in re.findall(patroon, serverlog, flags=re.I):
        verwachte_sessie = sessie.replace("-", "").lower()
        gemeld = [s.replace("-", "").lower() for s in re.findall(r"[\da-f-]{32,36}", sessies, flags=re.I)]
        if gid.replace("-", "").lower() == groep.replace("-", "").lower() and verwachte_sessie in gemeld:
            vertragingen.append(int(duur))
    uit = {**spoor, "ready_timeouts_android_ms": vertragingen}
    if vertragingen:
        return {**uit, "ok": False}
    if spoor["observatie_ms"] >= 40000 and len(spoor["voortgang_ms"]) == 2 and min(spoor["voortgang_ms"]) >= 2000:
        return {**uit, "ok": True}
    return {**uit, "status": "niet reproduceerbaar in de simulatie",
            "reden": "geen Android-timeout en geen bevestigde afspeelvoortgang van beide clients"}


def android_ready(server: StockServer, werk: Path, cfg: dict, apk: Path) -> dict:
    """Server #18121: een officiële Android-app voegt zich bij een al spelende webgroep."""
    if not Path("/dev/kvm").exists() or not (android.SDK / "emulator/emulator").is_file():
        return {"status": "niet reproduceerbaar in de simulatie",
                "reden": "KVM of het lokale emulator-SDK ontbreekt voor de Android-groepsproef"}
    if not apk.is_file():
        return {"status": "niet reproduceerbaar in de simulatie", "reden": "de vastgezette stock-APK ontbreekt lokaal"}
    assert server.jf
    jf = server.jf
    kopie = werk / "groepsapk" / android.APKS["android"]["naam"]
    kopie.parent.mkdir()
    shutil.copyfile(apk, kopie)
    digest = sha256_bestand(kopie)
    if digest != android.APKS["android"]["sha256"]:
        raise ValueError("de Android-groepsproef weigert de APK met afwijkende SHA-256")
    with meetslot.exclusief_slot("gradle.lock"), netwerk(server) as net, ExitStack() as eigen:
        avd = werk / "groepsavd"
        android.maak_avd("telefoon", avd)
        emu = android.Emulator("telefoon", netwerk=net, avd_map=avd)
        eigen.callback(emu.stop)
        emu.start(kopie.parent)
        emu.adb("install", "/apk/" + kopie.name, check=True)
        tijdelijk(eigen, "--network", "container:" + emu.cid, *BEPERKT, NODE_IMAGE, "node", "-e", DOORVOER, "8098", "testserver", "8096")
        emu.adb("reverse", "tcp:8098", "tcp:8098", check=True)
        browsernaam, telefoonnaam = cfg["namen"]
        _inloggen_telefoon(emu, "http://localhost:8098", telefoonnaam, cfg["wachtwoord"])
        with ThreadPoolExecutor(max_workers=1) as pool:
            browser = pool.submit(web.harnas, "watchandroid", cfg, timeout=300, pogingen=1)
            einde = time.monotonic() + 90
            while True:
                if browser.done():
                    browser.result()
                    raise ValueError("webclient beëindigde de Android-groepsproef vóór deelname")
                groepen = jf.a.doe("GET", "/SyncPlay/List")
                groep = next((g for g in groepen if g["Participants"] == [browsernaam] and g["State"] == "Playing"), None)
                if groep:
                    break
                if time.monotonic() >= einde:
                    raise ValueError("de spelende webgroep voor de Android-proef ontbreekt")
                time.sleep(1)
            menu = emu.wacht_op(r"^SyncPlay$", timeout=30)
            if not menu:
                raise ValueError("de Android-app toont geen SyncPlay-knop")
            emu.tik(menu)
            einde = time.monotonic() + 70
            while True:
                knopen = emu.dump()
                doel = emu.zoek(re.escape(groep["GroupName"]), knopen)
                knoppen = [k for k in knopen if emu.zoek(r"Join group|Deelnemen aan groep", [k])]
                if doel and knoppen:
                    emu.tik(min(knoppen, key=lambda k: abs(k.midden[1] - doel.midden[1])))
                    break
                if time.monotonic() >= einde:
                    raise ValueError("de Android-app toont de aangemaakte webgroep niet")
                time.sleep(1)
            spoor = browser.result()
        sessies = [s for s in jf.a.doe("GET", "/Sessions") if s.get("UserName") == telefoonnaam and "android" in s.get("Client", "").lower()]
        if len(sessies) != 1:
            raise ValueError("de ingelogde Android-sessie voor de logcontrole ontbreekt")
        return {**android_ready_uitkomst(groep["GroupId"], sessies[0]["Id"], server.logs(6000), spoor), "apk_sha256": digest}
