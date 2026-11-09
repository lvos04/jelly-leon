"""Rooktest op elk proces (contract 1.2 §2.2, conformiteitspunt A6): parser en beoordeling zonder Docker."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "e2e"))

import image_lifecycle  # noqa: E402


def status(name: str, pid: int, ppid: int, uid: int = 568, capeff: str = "0" * 16, nnp: int = 1) -> str:
    return (
        f"Name:\t{name}\nUmask:\t0022\nState:\tS (sleeping)\nTgid:\t{pid}\nPid:\t{pid}\nPPid:\t{ppid}\n"
        f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\nGid:\t{uid}\t{uid}\t{uid}\t{uid}\nCapInh:\t{'0' * 16}\n"
        f"CapPrm:\t{capeff}\nCapEff:\t{capeff}\nCapBnd:\t{'0' * 16}\nNoNewPrivs:\t{nnp}\n"
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
    assert problems == ["helper(41) Uid=0 0 0 0", f"helper(41) CapEff={ROOT_CAPS}", "helper(41) NoNewPrivs=0"]


def test_root_init_as_pid_1_is_reported():
    text = status("dumb-init", 1, 0, uid=0, capeff=ROOT_CAPS, nnp=0) + status("jellyfin", 7, 1)
    problems = image_lifecycle.process_problems(image_lifecycle.service_processes(image_lifecycle.parse_proc_status(text)))
    assert any(p.startswith("dumb-init(1) Uid=0") for p in problems)


def test_custom_user_without_no_new_privs_is_reported():
    """Custom User 568 zonder eigen no_new_privs (het formulier zet het niet) → afwijkend."""
    text = status("jellyfin", 1, 0, nnp=0)
    assert image_lifecycle.process_problems(image_lifecycle.parse_proc_status(text)) == ["jellyfin(1) NoNewPrivs=0"]
