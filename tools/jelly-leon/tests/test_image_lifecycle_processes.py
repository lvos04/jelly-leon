"""Rooktest op elk proces (contract 1.3 §2.2, C1.3-ALG-04/C1.3-JL-03): parser en beoordeling zonder Docker."""

from __future__ import annotations

import sys
from pathlib import Path

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
