"""Android-telefoon-, tablet- en Android TV-emulator in een container (B03 2.0 §10.14; analyse 5 §2).

Regels: alleen in een container met ``--device /dev/kvm`` (geen groepsrechten op de host nodig), één emulator tegelijk,
4 GiB (geheugenlimiet = swaplimiet), onder ``gradle.lock`` (en ``stack.lock`` voor de server en de vaste adb-poorten),
geen ``--privileged`` en geen Docker-socket. De officiële APK's worden via download.py opgehaald (tijdelijk bestand +
sha256 van de GitHub-release + atomaire hernoeming). De rooktest: app start, verbindt met de stock-server, logt in en
speelt hero.mp4 af (gestart via de officiële afstandsbedieningsroute ``POST /Sessions/{id}/Playing``); bewijs = de
serverkant ziet PositionTicks ≥ 2 s oplopen, plus een schermafdruk.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET  # noqa: S405 - eigen uiautomator-dump uit de eigen emulator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .corpus.download import download
from .stock import WERK, docker

SDK = Path(os.environ.get("ANDROID_HOME", str(Path.home() / "android-sdk")))
DEBIAN = "docker.io/library/debian:trixie-20261104-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2"
APK_MAP = WERK / "apk"
AVD_MAP = WERK / "avd"
EMU = "b03016-emu"
APKS = {
    "android": {"naam": "jellyfin-android-v2.7.3-libre-release.apk", "pakket": "org.jellyfin.mobile",
                "url": "https://github.com/jellyfin/jellyfin-android/releases/download/v2.7.3/jellyfin-android-v2.7.3-libre-release.apk",
                "sha256": "f9f4b3ab46cc9434df811194c2d4351417f4db83a4c1a0facd0a662d69533f7f"},
    "androidtv": {"naam": "jellyfin-androidtv-v0.19.10-release.apk", "pakket": "org.jellyfin.androidtv",
                  "url": "https://github.com/jellyfin/jellyfin-androidtv/releases/download/v0.19.10/jellyfin-androidtv-v0.19.10-release.apk",
                  "sha256": "8510a517c99927076082917f41bf306dd7a2546c59d492dd11bde18d6e2e4628"},
}
AVDS = {
    "telefoon": {"avd": "b03016-telefoon", "image": "system-images;android-35;google_apis;x86_64", "apparaat": "pixel_6", "app": "android"},
    "tablet": {"avd": "b03016-tablet", "image": "system-images;android-35;google_apis;x86_64", "apparaat": "pixel_tablet", "app": "android"},
    "tv": {"avd": "b03016-tv", "image": "system-images;android-34;android-tv;x86", "apparaat": "tv_1080p", "app": "androidtv"},
    "tv36": {"avd": "b03016-tv36", "image": "system-images;android-36;android-tv;x86_64", "apparaat": "tv_1080p", "app": "androidtv"},
}
LIBS = ("libx11-6 libpulse0 libnss3 libpng16-16t64 libexpat1 libdrm2 libxcb1 libxi6 libxext6 libdbus-1-3 libxkbfile1 libgl1 "
        "libegl1 libxcomposite1 libxcursor1 libxdamage1 libxtst6 libxrender1 libxrandr2 libfontconfig1 libfreetype6 "
        "libxkbcommon0 libasound2t64 procps")


def log(tekst: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {tekst}", flush=True)


def haal_apks() -> dict[str, Path]:
    uit = {}
    for sleutel, a in APKS.items():
        doel = APK_MAP / a["naam"]
        download(a["url"], doel, a["sha256"])
        uit[sleutel] = doel
    return uit


def maak_avd(soort: str) -> str:
    """Maakt het AVD op de host (avdmanager heeft Java nodig, de container niet) in een eigen map buiten de repo."""
    a = AVDS[soort]
    AVD_MAP.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "ANDROID_HOME": str(SDK), "ANDROID_SDK_ROOT": str(SDK), "ANDROID_AVD_HOME": str(AVD_MAP)}
    subprocess.run([str(SDK / "cmdline-tools/latest/bin/avdmanager"), "create", "avd", "-n", a["avd"], "-k", a["image"],
                    "-d", a["apparaat"], "--force"], input="no\n", text=True, capture_output=True, env=env, check=True)
    for slot in AVD_MAP.rglob("*.lock"):
        slot.unlink(missing_ok=True) if slot.is_file() else None
    return a["avd"]


@dataclass
class Knoop:
    tekst: str
    id: str
    klasse: str
    omschrijving: str
    bounds: tuple[int, int, int, int]
    focus: bool

    @property
    def midden(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2


class Emulator:
    def __init__(self, soort: str) -> None:
        self.soort = soort
        self.avd = AVDS[soort]["avd"]
        self.cid = ""

    def adb(self, *args: str, timeout: float = 120, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["docker", "exec", "-u", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", EMU,
                               str(SDK / "platform-tools/adb"), *args], capture_output=True, text=True, timeout=timeout,
                              check=check)

    def sh(self, opdracht: str, timeout: float = 120) -> str:
        return self.adb("shell", opdracht, timeout=timeout).stdout

    def start(self, apk_map: Path) -> float:
        docker("rm", "-f", EMU, check=False)
        kvm_gid = os.stat("/dev/kvm").st_gid
        self.cid = docker("run", "-d", "--name", EMU, "--device", "/dev/kvm", "--group-add", str(kvm_gid),
                          "--memory", "4g", "--memory-swap", "4g", "--network", "host", "--security-opt", "no-new-privileges",
                          "-e", f"ANDROID_AVD_HOME={AVD_MAP}", "-e", f"ANDROID_SDK_ROOT={SDK}", "-e", "HOME=/tmp",
                          "-v", f"{SDK}:{SDK}:ro", "-v", f"{AVD_MAP}:{AVD_MAP}", "-v", f"{apk_map}:/apk:ro",
                          DEBIAN, "sleep", "infinity").stdout.strip()
        uit = docker("exec", EMU, "sh", "-c", f"apt-get update -qq >/dev/null && apt-get install -y -qq --no-install-recommends {LIBS} "
                     ">/dev/null", check=False, timeout=900)
        if uit.returncode != 0:
            raise RuntimeError(f"apt in de emulatorcontainer faalde: {uit.stderr[-400:]}")
        t0 = time.monotonic()
        subprocess.run(["docker", "exec", "-d", "-u", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", EMU, "sh", "-c",
                        f"{SDK}/emulator/emulator -avd {self.avd} -no-window -no-audio -no-boot-anim -no-snapshot -wipe-data "
                        f"-gpu swiftshader_indirect -memory 2048 -cores 4 -accel on -no-metrics > /tmp/emu.log 2>&1"],  # noqa: S108
                       check=True)
        self.adb("start-server")
        for _ in range(600):
            if self.sh("getprop sys.boot_completed").strip() == "1":
                return time.monotonic() - t0
            time.sleep(1)
        log_in_container = "/tmp/emu.log"  # noqa: S108 - pad binnen de wegwerpcontainer
        raise RuntimeError("emulator niet opgestart binnen 600 s: " + docker("exec", EMU, "tail", "-20", log_in_container,
                                                                             check=False).stdout)

    def geheugen(self) -> dict[str, Any]:
        basis = Path(f"/sys/fs/cgroup/system.slice/docker-{self.cid}.scope")
        uit: dict[str, Any] = {"limiet_bytes": 4 * 1024**3}
        try:
            uit["piek_bytes"] = int((basis / "memory.peak").read_text().strip())
            events = dict(r.split() for r in (basis / "memory.events").read_text().splitlines())
            uit["oom"] = int(events.get("oom", 0))
            uit["oom_kill"] = int(events.get("oom_kill", 0))
        except OSError as fout:
            uit["fout"] = str(fout)
        return uit

    def stop(self) -> None:
        docker("rm", "-f", EMU, check=False)

    # --- UI ---------------------------------------------------------------------------------------------------

    def dump(self) -> list[Knoop]:
        self.sh("uiautomator dump /sdcard/ui.xml >/dev/null 2>&1")
        xml = self.adb("exec-out", "cat", "/sdcard/ui.xml").stdout
        if "<hierarchy" not in xml:
            return []
        knopen = []
        for n in ET.fromstring(xml[xml.index("<hierarchy"):]).iter("node"):  # noqa: S314
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds", ""))
            if m:
                knopen.append(Knoop(n.get("text", ""), n.get("resource-id", ""), n.get("class", ""), n.get("content-desc", ""),
                                    tuple(int(x) for x in m.groups()), n.get("focused") == "true"))  # type: ignore[arg-type]
        return knopen

    def zoek(self, patroon: str, knopen: list[Knoop] | None = None, klasse: str | None = None) -> Knoop | None:
        rx = re.compile(patroon, re.I)
        for k in knopen if knopen is not None else self.dump():
            if (rx.search(k.tekst) or rx.search(k.omschrijving) or rx.search(k.id)) and (klasse is None or klasse in k.klasse):
                return k
        return None

    def wacht_op(self, patroon: str, timeout: float = 60, klasse: str | None = None) -> Knoop | None:
        einde = time.monotonic() + timeout
        while time.monotonic() < einde:
            k = self.zoek(patroon, klasse=klasse)
            if k:
                return k
            time.sleep(2)
        return None

    def tik(self, k: Knoop) -> None:
        x, y = k.midden
        self.sh(f"input tap {x} {y}")

    def typ(self, tekst: str) -> None:
        self.sh("input text " + shlex.quote(tekst.replace(" ", "%s")))

    def toets(self, *codes: str) -> None:
        for c in codes:
            self.sh(f"input keyevent {c}")

    def schermafdruk(self, pad: Path) -> None:
        pad.parent.mkdir(parents=True, exist_ok=True)
        uit = subprocess.run(["docker", "exec", "-u", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", EMU,
                              str(SDK / "platform-tools/adb"), "exec-out", "screencap", "-p"], capture_output=True, timeout=60,
                             check=False)
        pad.write_bytes(uit.stdout)

    def teksten(self) -> list[str]:
        return [k.tekst or k.omschrijving for k in self.dump() if k.tekst or k.omschrijving][:40]
