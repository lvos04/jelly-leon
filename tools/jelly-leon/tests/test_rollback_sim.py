"""Tests van de terugzetproef (B03-013) met een nep-Docker (simulator; de echte proef draait in de CI-job image).

Doel: de proef mag alleen slagen als de volgorde klopt (back-up vóór de migratie, terugzetten vóór de herstart van de
oude binary) én de teruggezette /config echt de toestand van vóór de migratie is. Een terugzetstap die stilletjes niets
doet of een falende smoketest na het terugzetten geeft MISLUKT — nooit gesimuleerd succes.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "e2e"))

import rollback_sim  # noqa: E402

UPSTREAM = "docker.io/jellyfin/jellyfin:10.11.11@sha256:" + "a" * 64
FORK = "jelly-leon:test"


class FakeDocker:
    """Bootst alleen de bestandseffecten na die de proef controleert (database, pluginmap van de entrypoint)."""

    def __init__(self, sim: rollback_sim.RollbackSim, *, restore_does_nothing: bool = False) -> None:
        self.sim = sim
        self.events: list[str] = []
        self.restore_does_nothing = restore_does_nothing

    def start(self, image: str | None = None) -> None:
        image = image or FORK
        self.events.append(f"start {image}")
        (self.sim.config / "data").mkdir(parents=True, exist_ok=True)
        (self.sim.config / "data" / "jellyfin.db").write_bytes(b"sqlite")
        if image == FORK:  # de Jelly Leon-entrypoint installeert de plugin in de datamap
            (self.sim.config / "plugins" / "JellyLeon_0.1.0.0").mkdir(parents=True, exist_ok=True)

    def helper(self, *args: str) -> None:
        self.events.append("helper " + " ".join(args))
        if self.restore_does_nothing and args[-1] == "/werk/config":  # alleen de terugzetstap faalt stil
            return
        paths = [self.sim.work / a.removeprefix("/werk/") for a in args[1:] if a.startswith("/werk/")]
        if args[0] == "/bin/cp":
            shutil.copytree(paths[0], paths[1], symlinks=True)
        elif args[0] == "/bin/rm":
            for path in paths:
                shutil.rmtree(path, ignore_errors=True)


def make_sim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, fail_smoke: str = "", **fake_kwargs):
    args = argparse.Namespace(
        image=FORK, upstream_image=UPSTREAM, expected_version="12.4.0", upstream_version="10.11.11",
        werkmap=str(tmp_path), health_timeout=1, report=None, opmerking="", verwacht_web_ref="", keep_workdir=False,
    )
    sim = rollback_sim.RollbackSim(args)
    fake = FakeDocker(sim, **fake_kwargs)
    monkeypatch.setattr(sim, "start", fake.start)
    monkeypatch.setattr(sim, "helper", fake.helper)
    monkeypatch.setattr(sim, "remove", lambda name: fake.events.append("remove"))

    def wait_healthy(label: str) -> bool:
        return sim.add(f"healthy ({label})", True, "nep")

    def smoke(label: str, mode: str, previous=None, *, expect_plugin: bool = True, version=None):
        fake.events.append(f"smoke {label} {mode} plugin={expect_plugin} versie={version or args.expected_version}")
        ok = label != fail_smoke
        sim.add(f"stock-client-smoketest ({label}, modus {mode})", ok, "nep")
        return {"item_id": "item-1", "gebruiker_id": "user-1"} if ok else None

    monkeypatch.setattr(sim, "wait_healthy", wait_healthy)
    monkeypatch.setattr(sim, "smoke", smoke)
    return sim, fake


def test_rollback_order_and_restore_marker(tmp_path, monkeypatch):
    sim, fake = make_sim(tmp_path, monkeypatch)
    assert sim.run() is True
    starts = [e for e in fake.events if e.startswith(("start", "helper", "smoke"))]
    assert starts == [
        f"start {UPSTREAM}",
        "smoke upstream-eerste-start nieuw plugin=False versie=10.11.11",
        "helper /bin/cp -a /werk/config /werk/backup-config",
        f"start {FORK}",
        "smoke jelly-leon-na-migratie herstart plugin=True versie=12.4.0",
        "helper /bin/rm -rf /werk/config",
        "helper /bin/cp -a /werk/backup-config /werk/config",
        f"start {UPSTREAM}",
        "smoke upstream-na-terugzetten herstart plugin=False versie=10.11.11",
    ]
    steps = {s["stap"]: s["geslaagd"] for s in sim.steps}
    assert steps["migratie zichtbaar in /config"] is True
    assert steps["back-up teruggezet in /config"] is True
    assert not (sim.config / "plugins" / "JellyLeon_0.1.0.0").exists()


def test_restore_that_does_nothing_fails(tmp_path, monkeypatch):
    sim, fake = make_sim(tmp_path, monkeypatch, restore_does_nothing=True)
    assert sim.run() is False
    steps = {s["stap"]: s["geslaagd"] for s in sim.steps}
    assert steps["koude back-up van /config (model voor de ZFS-snapshot)"] is True
    assert steps["migratie zichtbaar in /config"] is True
    assert steps["back-up teruggezet in /config"] is False
    assert not any(e.startswith("smoke upstream-na-terugzetten") for e in fake.events)


def test_failing_smoke_after_restore_fails(tmp_path, monkeypatch):
    sim, _fake = make_sim(tmp_path, monkeypatch, fail_smoke="upstream-na-terugzetten")
    assert sim.run() is False
    assert not all(s["geslaagd"] for s in sim.steps)


def test_failing_smoke_on_fork_stops_before_restore(tmp_path, monkeypatch):
    sim, fake = make_sim(tmp_path, monkeypatch, fail_smoke="jelly-leon-na-migratie")
    assert sim.run() is False
    assert "helper /bin/rm -rf /werk/config" not in fake.events


def test_upstream_image_without_digest_is_refused(tmp_path, capsys):
    code = rollback_sim.main(
        ["--image", FORK, "--upstream-image", "docker.io/jellyfin/jellyfin:10.11.11", "--expected-version", "10.11.11",
         "--werkmap", str(tmp_path)]
    )
    assert code == 3
    assert "@sha256" in capsys.readouterr().err
