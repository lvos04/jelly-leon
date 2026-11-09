"""Eenheden: statistiek, meetprotocol en het baselinebewijs (geen netwerk, geen Docker)."""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
from pathlib import Path

import pytest

from b03h import bewijs, meetslot, statistiek


def test_wilson_bekende_waarden():
    # Plan F6.1.3: 0 fouten op n = 60 → ondergrens ≈ 60/63,84 ≈ 0,94; 0 schendingen op n = 30 → bovengrens ≈ 11 %.
    iv = statistiek.wilson(60, 60)
    assert iv.punt == 1.0 and iv.boven == 1.0
    assert iv.onder == pytest.approx(60 / 63.84, abs=0.002)
    assert statistiek.wilson(0, 30).boven == pytest.approx(0.1135, abs=0.002)
    assert statistiek.wilson(0, 30).onder == 0.0
    # Plan F4.1.5: 29/30 → 0,83 voldoet (≥ 0,80); 28/30 → 0,79 niet.
    assert statistiek.wilson(29, 30).onder == pytest.approx(0.833, abs=0.005)
    assert statistiek.wilson(28, 30).onder < 0.80
    # F3: 0 slechte varianten bij n ≥ 120 → bovengrens ≈ 3,1 %.
    assert statistiek.wilson(0, 120).boven == pytest.approx(0.031, abs=0.001)


def test_wilson_ongeldig():
    with pytest.raises(ValueError):
        statistiek.wilson(1, 0)
    with pytest.raises(ValueError):
        statistiek.wilson(5, 4)


def test_gate_label_smoke():
    assert statistiek.gate_label(30, 30) == "gate"
    assert statistiek.gate_label(25, 30) == "smoke-gate (n = 25)"


def test_kwantiel_en_t_interval():
    assert statistiek.kwantiel([1, 2, 3, 4], 0.5) == 2.5
    assert statistiek.kwantiel([10], 0.95) == 10
    iv = statistiek.t_interval([6.0, 6.2, 6.1])
    assert iv.onder < 6.1 < iv.boven
    assert iv.boven - iv.onder == pytest.approx(2 * 4.302652730 * 0.1 / 3 ** 0.5, rel=1e-6)
    assert statistiek.t_interval([5.0]).onder == 5.0


def test_bootstrap_herhaalbaar_en_verschil():
    a = [40.0, 42.0, 44.0, 41.0, 43.0]
    b = [30.0, 31.0, 33.0, 29.0, 32.0]
    i1 = statistiek.bootstrap(a, seed=7)
    i2 = statistiek.bootstrap(a, seed=7)
    assert i1 == i2
    d = statistiek.bootstrap_verschil(a, b, seed=7, trekkingen=2000)
    assert d.boven < 0  # b duidelijk lager
    assert statistiek.herhaling_binnen(i1, 42.0)


def test_ab_volgorde_gebalanceerd():
    v = meetslot.ab_volgorde(["a", "b"], 3)
    assert v == [(0, "a"), (0, "b"), (1, "b"), (1, "a"), (2, "a"), (2, "b")]


def test_beoordeel_run_ongeldig_niet_mislukt():
    last = meetslot.RunLast("stock-standaard", 0, "t", loadavg_voor=(5.2, 3.0, 2.0), cpu={"andere_kernen": 1.0})
    meetslot.beoordeel(last, 4.0)
    assert not last.geldig and "loadavg" in last.reden
    last = meetslot.RunLast("stock-best", 1, "t", loadavg_voor=(1.0, 1.0, 1.0), cpu={"andere_kernen": 6.7})
    meetslot.beoordeel(last, 4.0)
    assert not last.geldig and "andere processen" in last.reden
    last = meetslot.RunLast("stock-best", 1, "t", loadavg_voor=(1.0, 1.0, 1.0), cpu={"andere_kernen": 0.2},
                            zware_sloten_na=["docker-build.lock"])
    meetslot.beoordeel(last, 4.0)
    assert not last.geldig and "docker-build.lock" in last.reden
    last = meetslot.RunLast("stock-best", 2, "t", loadavg_voor=(1.0, 1.0, 1.0), cpu={"andere_kernen": 0.2})
    assert meetslot.beoordeel(last, 4.0).geldig


def test_slot_bezet_met_flock(tmp_path: Path):
    pad = tmp_path / "gradle.lock"
    assert not meetslot.slot_bezet(pad)
    houder = subprocess.Popen(["flock", str(pad), "sleep", "5"], start_new_session=True)
    try:
        for _ in range(50):
            if meetslot.slot_bezet(pad):
                break
            subprocess.run(["sleep", "0.1"], check=True)
        assert meetslot.slot_bezet(pad)
        assert meetslot.actieve_zware_sloten(tmp_path) == ["gradle.lock"]
    finally:
        os.killpg(houder.pid, signal.SIGKILL)  # flock geeft het slot door aan zijn kind (sleep): hele groep stoppen
        houder.wait()
    for _ in range(50):
        if not meetslot.slot_bezet(pad):
            break
        subprocess.run(["sleep", "0.1"], check=True)
    assert not meetslot.slot_bezet(pad)


def test_exclusief_slot_wacht_en_timeout(tmp_path: Path):
    pad = tmp_path / "stack.lock"
    fd = os.open(pad, os.O_RDONLY | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(TimeoutError), meetslot.exclusief_slot("stack.lock", tmp_path, timeout=0.5):
            pass
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    with meetslot.exclusief_slot("stack.lock", tmp_path, timeout=1) as wacht:
        assert wacht < 1


def test_cpu_meting_eigen_processen():
    m = meetslot.CpuMeting().start()
    subprocess.run(["python3", "-c", "s=0\nfor i in range(3_000_000): s+=i"], check=True)
    uit = m.stop()
    assert uit["eigen_kernen"] > 0.2
    assert set(uit) == {"duur_s", "machine_kernen", "eigen_kernen", "container_kernen", "andere_kernen"}


def _document(**extra):
    run = {"last": meetslot.RunLast("stock-standaard", 0, "t").als_dict(), "k": 16, "n": 25}
    m = bewijs.metriek(id="F5-B1-x", functie="F5", omschrijving="o", methode="m", systeem="stock-standaard", soort="proportie",
                       image="docker.io/jellyfin/jellyfin:12.4@sha256:" + "f" * 64, seed=None, runs=[run], waarde={"k": 16},
                       interval=statistiek.wilson(16, 25), n=25)
    return {"schema": bewijs.SCHEMA, "label": "voormeting-12.4", "images": {"stock": m["image"]}, "metingen": [m], **extra}


def test_bewijs_volledig_en_fouten():
    assert bewijs.controleer(_document()) == []
    d = _document(label="definitief")
    assert any("label" in f for f in bewijs.controleer(d))
    d = _document()
    d["images"]["stock"] = "jellyfin/jellyfin:12.4"
    assert any("digest" in f for f in bewijs.controleer(d))
    d = _document()
    d["metingen"][0]["validatie"] = "Intel-iGPU-getest (ontwikkelmachine)"
    assert any("contract §11" in f for f in bewijs.controleer(d))
    d = _document()
    del d["metingen"][0]["runs"][0]["last"]["loadavg_voor"]
    assert any("loadavg" in f for f in bewijs.controleer(d))
    d = _document()
    d["metingen"][0]["interval"] = None
    assert any("interval" in f for f in bewijs.controleer(d))


def test_bewijs_schrijf_weigert_onvolledig(tmp_path: Path):
    d = _document()
    d["metingen"][0]["methode"] = ""
    with pytest.raises(ValueError):
        bewijs.schrijf(tmp_path / "x.json", d)
    bewijs.schrijf(tmp_path / "y.json", _document())
    assert (tmp_path / "y.json").exists()
