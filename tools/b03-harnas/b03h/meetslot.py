"""Meetprotocol (B03 2.0 §10.15, F1.1.3, F5.1.3, F6.1.3): exclusief meetslot onder stack.lock, geen docker-build of
Gradle tegelijk, loadavg en CPU per run in het bewijs, A/B afwisselend, en een run boven de lastgrens is **ongeldig**
(niet mislukt).

"Buiten de eigen processen": de last van andere processen = (CPU-gebruik van de hele machine) − (CPU van dit harnas en
al zijn nakomelingen, bv. Playwright-browsers) − (CPU van de eigen testcontainers, uit hun cgroup). Daarmee telt een
software-transcode van de eigen stock-server niet als "te hoge last".
"""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

LOCK_DIR = Path(os.environ.get("B03_LOCK_DIR", "/home/transcode/truenas-v2/.lokaal"))
STACK_LOCK = "stack.lock"
ZWARE_SLOTEN = ("gradle.lock", "docker-build.lock")
LASTGRENS = float(os.environ.get("B03_LASTGRENS", "4.0"))  # loadavg(1 min) en "andere CPU-kernen", plan: > 4 = ongeldig
_TICK = os.sysconf("SC_CLK_TCK")


def nu() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def loadavg() -> tuple[float, float, float]:
    return os.getloadavg()


def slot_bezet(pad: Path) -> bool:
    """True als een ander proces het flock-slot vasthoudt (zelfde mechanisme als `flock(1)`)."""
    try:
        fd = os.open(pad, os.O_RDONLY | os.O_CREAT, 0o664)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def actieve_zware_sloten(lock_dir: Path = LOCK_DIR) -> list[str]:
    return [naam for naam in ZWARE_SLOTEN if slot_bezet(lock_dir / naam)]


@contextmanager
def exclusief_slot(naam: str = STACK_LOCK, lock_dir: Path = LOCK_DIR, timeout: float = 7200.0,
                   bij_wachten: object = None) -> Iterator[float]:
    """Wacht netjes op het slot (zoals `flock -w`) en geeft de wachttijd terug."""
    pad = lock_dir / naam
    fd = os.open(pad, os.O_RDONLY | os.O_CREAT, 0o664)
    begin = time.monotonic()
    gemeld = False
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - begin > timeout:
                    raise TimeoutError(f"{pad} niet vrij binnen {timeout:.0f} s") from None
                if not gemeld and callable(bij_wachten):
                    bij_wachten(f"wacht op {pad} …")
                    gemeld = True
                time.sleep(2)
        yield time.monotonic() - begin
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


# --- CPU-boekhouding ----------------------------------------------------------------------------------------------

def _host_busy_seconden() -> float:
    with open("/proc/stat", encoding="ascii") as f:
        delen = f.readline().split()
    waarden = [int(x) for x in delen[1:]]
    # user nice system idle iowait irq softirq steal guest guest_nice — guest zit al in user.
    totaal = sum(waarden[:8])
    idle = waarden[3] + waarden[4]
    return (totaal - idle) / _TICK


def _proc_stat(pid: int) -> tuple[int, float] | None:
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
            ruw = f.read()
    except OSError:
        return None
    rest = ruw[ruw.rfind(")") + 2:].split()
    ppid = int(rest[1])
    utime, stime, cutime, cstime = (int(x) for x in rest[11:15])
    return ppid, (utime + stime + cutime + cstime) / _TICK


def eigen_cpu_seconden(wortel: int | None = None) -> float:
    """CPU-seconden van dit proces en al zijn levende nakomelingen (incl. hun opgeruimde kinderen)."""
    wortel = wortel or os.getpid()
    ouders: dict[int, int] = {}
    cpu: dict[int, float] = {}
    for naam in os.listdir("/proc"):
        if naam.isdigit():
            info = _proc_stat(int(naam))
            if info:
                ouders[int(naam)], cpu[int(naam)] = info
    kinderen: dict[int, list[int]] = {}
    for pid, ppid in ouders.items():
        kinderen.setdefault(ppid, []).append(pid)
    totaal, stapel = 0.0, [wortel]
    while stapel:
        pid = stapel.pop()
        totaal += cpu.get(pid, 0.0)
        stapel.extend(kinderen.get(pid, []))
    return totaal


def container_cpu_seconden(container_id: str) -> float | None:
    """CPU-seconden uit de cgroup (v2, systemd-driver) van een container; None als die niet leesbaar is."""
    for pad in (Path(f"/sys/fs/cgroup/system.slice/docker-{container_id}.scope/cpu.stat"),
                Path(f"/sys/fs/cgroup/docker/{container_id}/cpu.stat")):
        try:
            for regel in pad.read_text(encoding="ascii").splitlines():
                if regel.startswith("usage_usec "):
                    return int(regel.split()[1]) / 1e6
        except OSError:
            continue
    return None


@dataclass
class CpuMeting:
    """Meet tijdens een run: eigen CPU, CPU van de eigen containers en de rest van de machine."""

    containers: Sequence[str] = ()
    _t0: float = 0.0
    _host0: float = 0.0
    _eigen0: float = 0.0
    _cont0: dict[str, float] = field(default_factory=dict)

    def start(self) -> CpuMeting:
        self._t0 = time.monotonic()
        self._host0 = _host_busy_seconden()
        self._eigen0 = eigen_cpu_seconden()
        self._cont0 = {c: container_cpu_seconden(c) or 0.0 for c in self.containers}
        return self

    def stop(self) -> dict[str, float]:
        duur = max(time.monotonic() - self._t0, 1e-6)
        host = _host_busy_seconden() - self._host0
        eigen = eigen_cpu_seconden() - self._eigen0
        cont = sum((container_cpu_seconden(c) or 0.0) - self._cont0.get(c, 0.0) for c in self.containers)
        anders = max(0.0, host - eigen - cont)
        return {"duur_s": round(duur, 3), "machine_kernen": round(host / duur, 3), "eigen_kernen": round(eigen / duur, 3),
                "container_kernen": round(cont / duur, 3), "andere_kernen": round(anders / duur, 3)}


# --- runs ---------------------------------------------------------------------------------------------------------

@dataclass
class RunLast:
    """Lastgegevens van één run, zoals ze in het bewijs komen."""

    systeem: str
    run: int
    begin: str
    eind: str = ""
    loadavg_voor: tuple[float, float, float] = (0.0, 0.0, 0.0)
    loadavg_na: tuple[float, float, float] = (0.0, 0.0, 0.0)
    cpu: dict[str, float] = field(default_factory=dict)
    zware_sloten_voor: list[str] = field(default_factory=list)
    zware_sloten_na: list[str] = field(default_factory=list)
    geldig: bool = True
    reden: str = ""

    def als_dict(self) -> dict:
        d = asdict(self)
        d["loadavg_voor"] = [round(x, 2) for x in self.loadavg_voor]
        d["loadavg_na"] = [round(x, 2) for x in self.loadavg_na]
        return d


def beoordeel(last: RunLast, grens: float = LASTGRENS) -> RunLast:
    """Zet geldig/reden volgens het protocol. Ongeldig ≠ mislukt."""
    redenen = []
    if last.loadavg_voor[0] > grens:
        redenen.append(f"loadavg(1 min) {last.loadavg_voor[0]:.2f} > {grens} vóór de run")
    if last.cpu.get("andere_kernen", 0.0) > grens:
        redenen.append(f"andere processen gebruikten {last.cpu['andere_kernen']:.2f} kernen > {grens}")
    sloten = sorted(set(last.zware_sloten_voor) | set(last.zware_sloten_na))
    if sloten:
        redenen.append("ander zwaar slot actief: " + ", ".join(sloten))
    last.geldig = not redenen
    last.reden = "; ".join(redenen)
    return last


def wacht_op_rust(grens: float = LASTGRENS, max_wacht: float = 240.0, lock_dir: Path = LOCK_DIR) -> float:
    """Wacht (begrensd) tot de 1-min-loadavg onder de grens zakt en geen zwaar slot actief is, bv. na de eigen
    software-transcode van de vorige run. Geeft de wachttijd terug; de run zelf wordt daarna toch beoordeeld."""
    begin = time.monotonic()
    while time.monotonic() - begin < max_wacht:
        if loadavg()[0] <= grens and not actieve_zware_sloten(lock_dir):
            break
        time.sleep(5)
    return time.monotonic() - begin


@contextmanager
def run(systeem: str, nummer: int, containers: Sequence[str] = (), lock_dir: Path = LOCK_DIR,
        grens: float = LASTGRENS) -> Iterator[RunLast]:
    last = RunLast(systeem=systeem, run=nummer, begin=nu(), loadavg_voor=loadavg(),
                   zware_sloten_voor=actieve_zware_sloten(lock_dir))
    meting = CpuMeting(containers).start()
    try:
        yield last
    finally:
        last.cpu = meting.stop()
        last.eind = nu()
        last.loadavg_na = loadavg()
        last.zware_sloten_na = actieve_zware_sloten(lock_dir)
        beoordeel(last, grens)


def ab_volgorde(systemen: Sequence[str], runs: int) -> list[tuple[int, str]]:
    """Afwisselend en gebalanceerd: run 0 = a,b; run 1 = b,a; run 2 = a,b … (drift raakt beide systemen gelijk)."""
    volgorde = []
    for r in range(runs):
        reeks = list(systemen) if r % 2 == 0 else list(reversed(systemen))
        volgorde.extend((r, s) for s in reeks)
    return volgorde


def machine() -> dict[str, object]:
    """Vaste machinegegevens voor het bewijs (geen NAS-gegevens; dit is de ontwikkelmachine)."""
    info: dict[str, object] = {"cpu_s": os.cpu_count()}
    try:
        for regel in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if regel.startswith("model name"):
                info["cpu_model"] = regel.split(":", 1)[1].strip()
                break
        for regel in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if regel.startswith(("MemTotal", "SwapTotal")):
                sleutel, waarde = regel.split(":", 1)
                info[sleutel.lower() + "_gib"] = round(int(waarde.split()[0]) / 1048576, 1)
        info["kernel"] = os.uname().release
    except OSError:
        pass
    return info
