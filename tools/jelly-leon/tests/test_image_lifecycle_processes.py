"""Rooktest op elk proces (contract 1.3 §2.2, C1.3-ALG-04/C1.3-JL-03): parser en beoordeling zonder Docker."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "e2e"))

import image_lifecycle  # noqa: E402


def status(
    name: str,
    pid: int,
    ppid: int,
    uid: int = 568,
    capeff: str = "0" * 16,
    nnp: int = 1,
    *,
    capprm: str | None = None,
    capamb: str = "0" * 16,
    capbnd: str = "0" * 16,
) -> str:
    return (
        f"Name:\t{name}\nUmask:\t0022\nState:\tS (sleeping)\nTgid:\t{pid}\nPid:\t{pid}\nPPid:\t{ppid}\n"
        f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\nGid:\t{uid}\t{uid}\t{uid}\t{uid}\nCapInh:\t{'0' * 16}\n"
        f"CapPrm:\t{capeff if capprm is None else capprm}\nCapEff:\t{capeff}\nCapBnd:\t{capbnd}\n"
        f"CapAmb:\t{capamb}\nNoNewPrivs:\t{nnp}\n"
    )


ROOT_CAPS = "00000000a80425fb"  # Docker-standaardset


def test_parser_splits_concatenated_status_files():
    text = status("jellyfin", 1, 0) + status("ffmpeg", 40, 1)
    procs = image_lifecycle.parse_proc_status(text)
    assert [p["Name"] for p in procs] == [["jellyfin"], ["ffmpeg"]]
    assert procs[1]["PPid"] == ["1"] and procs[1]["NoNewPrivs"] == ["1"]


def test_docker_exec_and_healthcheck_trees_are_excluded():
    text = (
        status("jellyfin", 1, 0)
        + status("ffmpeg", 40, 1)
        + status("find", 77, 0, uid=0, capeff=ROOT_CAPS, nnp=0)  # docker exec (van buiten)
        + status("cat", 78, 77, uid=0, capeff=ROOT_CAPS, nnp=0)  # kind daarvan
        + status("curl", 90, 0, uid=0, capeff=ROOT_CAPS, nnp=0)  # healthcheck (van buiten)
    )
    own = image_lifecycle.service_processes(image_lifecycle.parse_proc_status(text))
    assert [p["Pid"][0] for p in own] == ["1", "40"]
    assert image_lifecycle.process_problems(own) == []


def test_root_child_of_the_service_is_reported():
    """Een init die als root blijft (of een kind met rechten) voldoet niet, ook als PID 1 zelf goed is."""
    text = (
        status("jellyfin", 1, 0)
        + status("helper", 41, 1, uid=0, capeff=ROOT_CAPS, nnp=0)
    )
    problems = image_lifecycle.process_problems(image_lifecycle.service_processes(image_lifecycle.parse_proc_status(text)))
    assert problems == [
        "helper(41) Uid=0 0 0 0", f"helper(41) CapEff={ROOT_CAPS}", f"helper(41) CapPrm={ROOT_CAPS}",
        "helper(41) NoNewPrivs=0",
    ]


def test_root_init_as_pid_1_is_reported():
    text = status("dumb-init", 1, 0, uid=0, capeff=ROOT_CAPS, nnp=0) + status("jellyfin", 7, 1)
    problems = image_lifecycle.process_problems(image_lifecycle.service_processes(image_lifecycle.parse_proc_status(text)))
    assert any(p.startswith("dumb-init(1) Uid=0") for p in problems)


def test_custom_user_without_no_new_privs_is_reported():
    """Custom User 568 zonder eigen no_new_privs (het formulier zet het niet) → afwijkend."""
    text = status("jellyfin", 1, 0, nnp=0)
    assert image_lifecycle.process_problems(image_lifecycle.parse_proc_status(text)) == ["jellyfin(1) NoNewPrivs=0"]


def test_healthcheck_rights_after_root_start_must_be_fully_dropped():
    assert image_lifecycle.healthcheck_problems(status("curl", 90, 0), root_start=True) == []
    as_root = status("curl", 90, 0, uid=0, capeff=ROOT_CAPS, nnp=0)
    problems = image_lifecycle.healthcheck_problems(as_root, root_start=True)
    assert "curl(90) Uid=0 0 0 0" in problems and "curl(90) NoNewPrivs=0" in problems
    assert "healthcheck Gid=0 0 0 0" in problems


def test_healthcheck_with_groups_or_bounding_set_after_root_start_is_reported():
    with_groups = status("curl", 90, 0).replace("CapInh:", "Groups:\t0 44\nCapInh:")
    assert image_lifecycle.healthcheck_problems(with_groups, root_start=True) == ["healthcheck Groups=0 44"]
    full_bounding = status("curl", 90, 0).replace(f"CapBnd:\t{'0' * 16}", f"CapBnd:\t{ROOT_CAPS}")
    assert image_lifecycle.healthcheck_problems(full_bounding, root_start=True) == [f"healthcheck CapBnd={ROOT_CAPS}"]
    # Custom User: een niet-root-proces kan de bounding-set niet legen; CapEff 0 + NoNewPrivs 1 is de eis.
    assert image_lifecycle.healthcheck_problems(full_bounding, root_start=False) == []


def test_healthcheck_without_no_new_privs_under_custom_user_is_reported():
    assert image_lifecycle.healthcheck_problems(status("curl", 90, 0, nnp=0), root_start=False) == [
        "curl(90) NoNewPrivs=0"
    ]


def test_healthcheck_rights_need_exactly_one_status():
    assert image_lifecycle.healthcheck_problems("", root_start=True) == ["verwacht precies één status, gevonden 0"]


def test_permitted_or_ambient_capabilities_of_a_service_process_are_reported():
    """Contract 1.3 §2.2: niet alleen CapEff — ook CapPrm en CapAmb moeten 0 zijn (bv. een helper die zijn rechten
    alleen tijdelijk uit CapEff haalt, of ambient capabilities via setpriv --ambient-caps)."""
    text = (
        status("jellyfin", 1, 0)
        + status("helper", 41, 1, capprm="0000000000000400")
        + status("ambient", 42, 1, capamb="0000000000000400")
    )
    procs = image_lifecycle.service_processes(image_lifecycle.parse_proc_status(text))
    assert image_lifecycle.process_problems(procs) == [
        "helper(41) CapPrm=0000000000000400", "ambient(42) CapAmb=0000000000000400"
    ]


def test_bounding_set_of_every_service_process_must_be_empty_after_a_root_start():
    text = status("jellyfin", 1, 0) + status("ffmpeg", 40, 1, capbnd=ROOT_CAPS)
    procs = image_lifecycle.service_processes(image_lifecycle.parse_proc_status(text))
    assert image_lifecycle.process_problems(procs, root_start=True) == [f"ffmpeg(40) CapBnd={ROOT_CAPS}"]
    # Custom User: een niet-root-proces kan de bounding set niet legen; dan geen eis op CapBnd.
    assert image_lifecycle.process_problems(procs, root_start=False) == []


def test_missing_capamb_line_is_reported_not_silently_accepted():
    text = status("jellyfin", 1, 0).replace(f"CapAmb:\t{'0' * 16}\n", "")
    assert image_lifecycle.process_problems(image_lifecycle.parse_proc_status(text)) == ["jellyfin(1) CapAmb=?"]


def test_healthcheck_rights_include_permitted_and_ambient_capabilities():
    leftover = status("cat", 90, 0, capprm="0000000000000001")
    assert image_lifecycle.healthcheck_problems(leftover, root_start=True) == ["cat(90) CapPrm=0000000000000001"]


def test_custom_user_weigering_controleert_eigenaar_en_lege_map(tmp_path, monkeypatch):
    life = object.__new__(image_lifecycle.Lifecycle)
    life.work, life.cache, life.media, life.steps = tmp_path, tmp_path / "cache", tmp_path / "media", []
    oproepen = []
    monkeypatch.setattr(life, "expect_refusal", lambda *args, **kwargs: oproepen.append(kwargs))
    life.expect_custom_user_refusal()
    assert oproepen[0]["expected_text"] == f"/config is van gebruiker {image_lifecycle.os.getuid()}, niet van 568:"
    assert life.steps[-1]["geslaagd"]


def test_custom_user_weigering_merkt_nieuwe_inhoud_op(tmp_path, monkeypatch):
    life = object.__new__(image_lifecycle.Lifecycle)
    life.work, life.cache, life.media, life.steps = tmp_path, tmp_path / "cache", tmp_path / "media", []

    def onveilig(*args, **kwargs):
        (tmp_path / "config-niet-van-568" / "onverwacht").write_text("niet toegestaan")

    monkeypatch.setattr(life, "expect_refusal", onveilig)
    life.expect_custom_user_refusal()
    assert not life.steps[-1]["geslaagd"]


def test_custom_user_weigering_merkt_rechtenwijziging_op(tmp_path, monkeypatch):
    life = object.__new__(image_lifecycle.Lifecycle)
    life.work, life.cache, life.media, life.steps = tmp_path, tmp_path / "cache", tmp_path / "media", []
    monkeypatch.setattr(life, "expect_refusal", lambda *args, **kwargs: (tmp_path / "config-niet-van-568").chmod(0o777))
    life.expect_custom_user_refusal()
    assert not life.steps[-1]["geslaagd"]


def _herstel(mounts, schrijf_door=False):
    """Nabootsing van de herstelde start: vreemde ingangen weg, nieuwe DLL; met schrijf_door als de oude fout."""
    config = Path(mounts[0].split(":")[0])
    for plugin in (config / "plugins").iterdir():
        for ingang in plugin.iterdir():
            if schrijf_door:
                (config / "data" / "jellyfin.db").write_bytes(b"synthetische plugin")
            ingang.unlink()
        (plugin / "Jellyfin.Plugin.JellyLeon.dll").write_bytes(b"plugin")
    return "exited 0", "jelly-leon: eigen pluginmap hersteld zonder een koppeling te volgen\nNEPSERVER uid=568"


def _pluginlife(tmp_path, monkeypatch, refusal, repair=_herstel):
    life = object.__new__(image_lifecycle.Lifecycle)
    life.work, life.media, life.steps, life.name = tmp_path, tmp_path / "media", [], "jl"
    life.args = type("Args", (), {"image": "proef"})()
    monkeypatch.setattr(image_lifecycle, "docker", lambda *a, **k: image_lifecycle.subprocess.CompletedProcess(a, 0, "JellyLeon_0.1.0.0\n", ""))
    monkeypatch.setattr(life, "expect_refusal", refusal)
    monkeypatch.setattr(life, "run_to_exit", lambda name, **kwargs: repair(kwargs["mounts"]))
    return life


def test_pluginkoppeling_herstel_en_configweigering_root_en_custom_user(tmp_path, monkeypatch):
    oproepen = []
    life = _pluginlife(tmp_path, monkeypatch, lambda *args, **kwargs: oproepen.append(kwargs))
    assert life.expect_plugin_link_refusal(), life.steps
    custom = ["--user", f"{image_lifecycle.os.getuid()}:{image_lifecycle.os.getgid()}"]
    assert [o["extra"] for o in oproepen] == [[], custom]
    assert [o["expected_text"] for o in oproepen] == ["is geen gewoon bestand met één naam"] * 2
    xml = tmp_path / "configkoppeling-custom-user" / "config" / "plugins" / "configurations" / "Jellyfin.Plugin.JellyLeon.xml"
    assert xml.is_symlink() and str(xml.readlink()) == "/config/data/jellyfin.db"
    assert oct((xml.parent.stat().st_mode) & 0o777) == "0o755"
    assert [s["stap"] for s in life.steps if s["stap"].startswith("hersteld:")] == [
        "hersteld: plugin-DLL als koppeling en meta.json als harde koppeling (root, nep-server)",
        "hersteld: plugin-DLL als koppeling en meta.json als harde koppeling (Custom User, nep-server)",
    ]


def test_pluginkoppeling_weigering_merkt_een_overschreven_database_op(tmp_path, monkeypatch):
    def overschrijf(label, **kwargs):
        config = Path(kwargs["mounts"][0].split(":")[0])
        (config / "data" / "jellyfin.db").write_bytes(b"synthetische plugin")

    life = _pluginlife(tmp_path, monkeypatch, overschrijf)
    assert not life.expect_plugin_link_refusal()
    assert [s["geslaagd"] for s in life.steps if s["stap"].startswith("configkoppeling")] == [False, False]


@pytest.mark.parametrize("fout", ["schrijft-door", "laat-koppeling-staan", "start-niet"])
def test_pluginherstel_merkt_doorschrijven_of_uitval_op(tmp_path, monkeypatch, fout):
    def herstel(mounts):
        if fout == "laat-koppeling-staan":
            return "exited 0", "hersteld zonder een koppeling te volgen\nNEPSERVER"
        state, log = _herstel(mounts, schrijf_door=fout == "schrijft-door")
        return ("exited 1", log) if fout == "start-niet" else (state, log)

    life = _pluginlife(tmp_path, monkeypatch, lambda *a, **k: None, herstel)
    assert not life.expect_plugin_entry_repair("JellyLeon_0.1.0.0")
    assert not any(s["geslaagd"] for s in life.steps)

def _tmpfslife(tmp_path, monkeypatch, *, status=200, log="", healthy=True, cache="0:0 1777"):
    life = object.__new__(image_lifecycle.Lifecycle)
    life.work, life.config, life.media, life.steps = tmp_path, tmp_path / "config", tmp_path / "media", []
    life.name, life.port, life.args = "jl", 1, type("Args", (), {"image": "proef"})()
    starts = []

    def nep_docker(*args, **kwargs):
        starts.append(args)
        return image_lifecycle.subprocess.CompletedProcess(args, 0, cache if args[0] == "exec" else "", "")

    monkeypatch.setattr(image_lifecycle, "docker", nep_docker)
    monkeypatch.setattr(life, "wait_healthy", lambda label: healthy)
    monkeypatch.setattr(life, "smoke", lambda *a, **k: {"item_id": "i"})
    monkeypatch.setattr(life, "login", lambda *a: ("token", "id"))
    monkeypatch.setattr(life, "api", lambda *a, **k: (status, None))
    monkeypatch.setattr(life, "logs", lambda *a, **k: log)
    return life, starts


def test_tmpfs_cache_start_als_root_en_custom_user(tmp_path, monkeypatch):
    life, starts = _tmpfslife(tmp_path, monkeypatch)
    assert life.check_tmpfs_cache_starts({"item_id": "i", "gebruiker_id": "g"})
    runs = [a for a in starts if a[0] == "run"]
    assert len(runs) == 2 and all(image_lifecycle.TMPFS_CACHE in a and not any(m.endswith(":/cache") for m in a) for a in runs)
    assert image_lifecycle.TMPFS_CACHE == "/cache:size=2684354560"  # 2560 MiB (deel 1g)
    assert "--user" not in runs[0] and "568:568" in runs[1]


@pytest.mark.parametrize(
    ("status", "log", "healthy", "cache"),
    [
        (503, "", True, "0:0 1777"),
        (200, "Jelly Leon: ... alleen de plugin is uitgeschakeld", True, "0:0 1777"),
        (200, "", False, "0:0 1777"),
        (200, "", True, "568:568 1777"),  # deel 1g: de rootfase wisselde de tmpfs toch van eigenaar
    ],
)
def test_tmpfs_cache_start_merkt_terugval_of_uitval_op(tmp_path, monkeypatch, status, log, healthy, cache):
    life, _ = _tmpfslife(tmp_path, monkeypatch, status=status, log=log, healthy=healthy, cache=cache)
    assert not life.check_tmpfs_cache_starts({"item_id": "i", "gebruiker_id": "g"})


def _terugvallife(tmp_path, monkeypatch, *, schrijft=False, modules_status=503, meldingen=1):
    life = object.__new__(image_lifecycle.Lifecycle)
    life.work, life.steps, life.name, life.port = tmp_path, [], "jl", 1
    staat = {"n": 0, "veilig": False}

    def helper_sh(script):
        if "chmod 0755" in script:
            staat["veilig"] = True
        if "find config/data/jelly-leon" in script:
            staat["n"] += 1
            return "config/data/jelly-leon d 775" + (" nieuw" if schrijft and staat["n"] > 1 else "")
        return ""

    kijk = {}

    def api(method, path, token=None, body=None):
        if path == "/media/v1/modules":
            if token is None:
                return 401, None
            if token == "hub":
                return 403, None
            return (200, {}) if staat["veilig"] else (modules_status, {"code": "storage_unavailable"})
        if path == "/connector/v1/health":
            return 401, None
        if path.startswith(("/UserPlayedItems", "/UserFavoriteItems")) or (method == "POST" and "/UserData" in path):
            kijk[path.split("/")[1]] = True
            return 200, None
        if "/UserData" in path:
            return 200, {"Played": True, "IsFavorite": True, "PlaybackPositionTicks": 25000000}
        if path == "/Users/New":
            return 200, {"Id": "nieuw"}
        if method == "DELETE":
            return 204, None
        return 404, None

    monkeypatch.setattr(life, "helper_sh", helper_sh)
    monkeypatch.setattr(life, "api", api)
    monkeypatch.setattr(life, "login", lambda user, ww: ("hub", "h") if user == image_lifecycle.SMOKE_HUB[0] else ("admin", "a"))
    monkeypatch.setattr(life, "logs", lambda *a, **k: "Jelly Leon: ... alleen de plugin is uitgeschakeld\n" * meldingen)
    monkeypatch.setattr(life, "start", lambda *a, **k: None)
    monkeypatch.setattr(life, "remove", lambda *a, **k: None)
    monkeypatch.setattr(life, "wait_healthy", lambda label: True)
    monkeypatch.setattr(image_lifecycle.stock_client_smoke.Client, "request", lambda self, m, p, **k: (200, {}, b"wav"))
    return life


def test_terugvalproef_met_echte_server_slaagt_als_alles_klopt(tmp_path, monkeypatch):
    life = _terugvallife(tmp_path, monkeypatch)
    assert life.check_storage_fallback({"item_id": "i", "gebruiker_id": "g"}), life.steps
    assert [s["stap"] for s in life.steps] == [
        "teruggevallen plugin met de echte server", "na herstel en herstart: plugin aan, kijkgegevens gelijk"]


@pytest.mark.parametrize("fout", ["plugin-schrijft", "plugin-niet-teruggevallen", "geen-melding"])
def test_terugvalproef_merkt_schrijven_of_geen_terugval_op(tmp_path, monkeypatch, fout):
    life = _terugvallife(tmp_path, monkeypatch, schrijft=fout == "plugin-schrijft",
                         modules_status=200 if fout == "plugin-niet-teruggevallen" else 503, meldingen=0 if fout == "geen-melding" else 1)
    assert not life.check_storage_fallback({"item_id": "i", "gebruiker_id": "g"})
    assert not life.steps[0]["geslaagd"]
