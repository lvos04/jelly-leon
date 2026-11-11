"""deploy/allinone/healthcheck.sh (Docker-healthcheck, contract 1.3 §2.2, C1.3-JL-03): de rechtenwissel is de eerste
handeling, daarna controleert het script zijn eigen rechten en pas dan /health; mislukt een controle of /health, dan
exitcode 1. Weigert setpriv de wissel, dan eindigt het script met de foutcode van setpriv (≠ 0; ADR-0014, aanvulling 1.3).

Zonder Docker en zonder root: `setpriv`, `curl` en programma's die het script vóór de wissel nooit mag starten (`id`,
`grep`, `awk`, `sed`, `stat`, `readlink`; zie FORBIDDEN_BEFORE_SWITCH) zijn nepprogramma's in PATH die hun aanroep
vastleggen. `cat` is bewust geen nepprogramma: de controlevlag --toon-rechten heeft na de wissel de echte cat nodig. De
nep-`setpriv` voert daarna de echte setpriv uit (of stopt met een foutcode, zie setpriv_exit), zodat no_new_privs echt
aan staat en de controle na de wissel echte rechten leest. Het pad als root (bounding set leeg, 568:568) en een proces
met capabilities kunnen hier niet zonder root; dat meten `tools/jelly-leon/e2e/healthcheck_proef.py` (script in de
runtime-image, ook met de negatieve gevallen CapPrm/CapAmb en Gid/Groups) en `tools/jelly-leon/e2e/image_lifecycle.py`
(de gebouwde image) in een echte container.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "deploy" / "allinone" / "healthcheck.sh"
REAL_SETPRIV = shutil.which("setpriv")
FORBIDDEN_BEFORE_SWITCH = ("id", "grep", "awk", "sed", "stat", "readlink")


def _status_field(name: str) -> str:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}:"):
            return line.split(":", 1)[1].strip()
    return ""


pytestmark = [
    pytest.mark.skipif(REAL_SETPRIV is None, reason="setpriv (util-linux) ontbreekt"),
    pytest.mark.skipif(os.geteuid() == 0, reason="als root zou de echte wissel naar 568 gebeuren; draai als gewone gebruiker"),
    pytest.mark.skipif(not Path("/proc/self/status").is_file(), reason="geen /proc (alleen Linux)"),
    pytest.mark.skipif(
        Path("/proc/self/status").is_file() and _status_field("NoNewPrivs") == "1",
        reason="deze testomgeving heeft al no_new_privs: de wissel van een Custom User is dan niet zichtbaar",
    ),
]


def write_tool(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_healthcheck(
    tmp_path: Path,
    *args: str,
    curl_exit: int = 0,
    setpriv_exit: int | None = None,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, list[str], str, str]:
    """Draait het script als gewone gebruiker zonder no_new_privs (zoals Custom User in het formulier).

    Met setpriv_exit weigert de nep-setpriv de wissel (zoals de echte bij een container met --cap-drop ALL)."""
    tools = tmp_path / "bin"
    tools.mkdir(exist_ok=True)
    log = tmp_path / "aanroepen.log"
    if setpriv_exit is None:
        # setpriv: argumenten vastleggen en daarna de echte setpriv met dezelfde argumenten (echte no_new_privs).
        setpriv_body = f'exec "{REAL_SETPRIV}" "$@"\n'
    else:
        setpriv_body = f'echo "setpriv: setresuid failed: Operation not permitted" >&2\nexit {setpriv_exit}\n'
    write_tool(tools, "setpriv", f'printf "setpriv %s\\n" "$*" >> "{log}"\n' + setpriv_body)
    write_tool(tools, "curl", f'printf "curl %s\\n" "$*" >> "{log}"\nexit {curl_exit}\n')
    for name in FORBIDDEN_BEFORE_SWITCH:
        write_tool(tools, name, f'printf "{name} %s\\n" "$*" >> "{log}"\nexit 0\n')
    env = {"PATH": f"{tools}{os.pathsep}/usr/bin{os.pathsep}/bin", **(env_extra or {})}
    proc = subprocess.run(["/bin/sh", str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc.returncode, calls, proc.stdout, proc.stderr


def test_switch_is_the_first_action_and_only_then_health(tmp_path):
    rc, calls, _, err = run_healthcheck(tmp_path)
    assert rc == 0, err
    assert calls[0] == f"setpriv --no-new-privs --inh-caps=-all -- /bin/sh {SCRIPT}  --na-wissel"
    assert calls[1] == "curl --noproxy localhost -fsS --max-time 8 -o /dev/null http://localhost:8096/health"
    assert len(calls) == 2, "vóór en na de wissel geen andere programma's (id, grep, …)"


def test_root_branch_drops_everything_in_one_setpriv_call():
    """Het pad als root (hier niet uit te voeren zonder root): precies deze wissel, met het script zelf daarna."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert (
        'exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups --inh-caps=-all --bounding-set=-all \\\n'
        '      --no-new-privs -- /bin/sh "$0" "$modus" --na-wissel-root'
    ) in text
    assert "APP_UID=568" in text and "APP_GID=568" in text


@pytest.mark.parametrize("curl_exit", [7, 22, 28])  # geen verbinding, HTTP-fout, time-out
def test_failed_health_request_makes_the_healthcheck_red_with_exit_1(tmp_path, curl_exit):
    rc, calls, _, err = run_healthcheck(tmp_path, curl_exit=curl_exit)
    assert rc == 1
    assert calls[-1].startswith("curl ")
    assert "/health antwoordt niet met 200" in err


def test_rights_probe_uses_the_same_switch_and_shows_the_real_rights(tmp_path):
    rc, calls, out, err = run_healthcheck(tmp_path, "--toon-rechten")
    assert rc == 0, err
    assert calls == [f"setpriv --no-new-privs --inh-caps=-all -- /bin/sh {SCRIPT} --toon-rechten --na-wissel"]
    fields = dict(line.split(":", 1) for line in out.splitlines() if ":" in line)
    assert fields["NoNewPrivs"].strip() == "1"
    assert fields["CapEff"].strip() == fields["CapPrm"].strip() == fields["CapAmb"].strip() == "0" * 16


def test_internal_phase_argument_without_a_real_switch_is_red(tmp_path):
    """Het interne fase-argument zonder echte wissel (geen no_new_privs): rood, geen tweede poging, geen /health."""
    rc, calls, _, err = run_healthcheck(tmp_path, "", "--na-wissel")
    assert rc == 1
    assert calls == [], "zonder geslaagde wissel geen setpriv-lus en geen /health-aanvraag"
    assert "NoNewPrivs 0 na de wissel" in err and "/health niet gecontroleerd" in err


def test_root_phase_after_a_switch_without_root_start_is_red(tmp_path):
    """Fase 'na een start als root', maar het proces wisselde nooit als root: Uid/Gid/CapBnd kloppen niet → rood.

    Draait onder de echte setpriv met no_new_privs, zodat alleen de root-verwachtingen falen."""
    status = subprocess.run(
        [REAL_SETPRIV, "--no-new-privs", "--", "/bin/sh", str(SCRIPT), "--toon-rechten", "--na-wissel-root"],
        capture_output=True, text=True, check=False, env={"PATH": "/usr/bin:/bin"},
    )
    assert status.returncode == 1
    assert "rechtenwissel niet in orde" in status.stderr
    # Elke root-verwachting apart: het proces erft uid, gid en groepen van deze testgebruiker (geen 568, geen wissel).
    own_uid = " ".join(_status_field("Uid").split())
    own_gid = " ".join(_status_field("Gid").split())
    own_groups = " ".join(_status_field("Groups").split())
    assert f"Uid {own_uid} (verwacht 568)" in status.stderr
    assert f"Gid {own_gid} (verwacht 568)" in status.stderr
    assert "CapBnd" in status.stderr
    if own_groups:  # zonder aanvullende groepen in deze omgeving dekt healthcheck_proef.py de Groups-controle
        assert f"Groups {own_groups}" in status.stderr
    assert "NoNewPrivs:" in status.stdout, "de controlevlag toont de rechten ook als ze niet in orde zijn"


@pytest.mark.parametrize("args", [(), ("--toon-rechten",)])
def test_refused_switch_ends_with_the_setpriv_error_and_never_checks_health(tmp_path, args):
    """setpriv weigert de wissel (bv. een container met --cap-drop ALL): het script eindigt met de foutcode van setpriv
    (≠ 0, voor Docker ongezond), zonder /health en zonder tweede poging (ADR-0014, aanvulling 1.3, punt 2)."""
    rc, calls, out, err = run_healthcheck(tmp_path, *args, setpriv_exit=127)
    assert rc == 127, err
    assert len(calls) == 1 and calls[0].startswith("setpriv --no-new-privs --inh-caps=-all -- /bin/sh ")
    assert not any(call.startswith("curl ") for call in calls)
    assert "setresuid failed" in err
    assert out == "", "zonder geslaagde wissel geen rechtenoverzicht"


def test_form_environment_cannot_skip_the_switch(tmp_path):
    """Een omgevingsvariabele uit het formulier speelt geen rol: de markering is een intern argument."""
    rc, calls, _, err = run_healthcheck(
        tmp_path, env_extra={"JELLY_LEON_HEALTHCHECK_FASE": "na-wissel-root", "JELLY_LEON_ENTRYPOINT_STAGE": "app"}
    )
    assert rc == 0, err
    assert calls[0].startswith("setpriv --no-new-privs ")


@pytest.mark.parametrize("args", [("--shell",), ("", "--overslaan"), ("--toon-rechten", "--na-wissel", "x")])
def test_unknown_option_is_refused_without_running_anything(tmp_path, args):
    rc, calls, _, err = run_healthcheck(tmp_path, *args)
    assert rc == 2 and calls == []
    assert "onbekende optie" in err or "te veel argumenten" in err


def test_healthcheck_is_exec_form_in_the_dockerfile():
    """§2.2 (1): exec-vorm, geen `sh -c` en geen shell-vorm."""
    dockerfile = (REPO / "deploy" / "allinone" / "Dockerfile").read_text(encoding="utf-8")
    assert 'CMD ["/usr/local/bin/jelly-leon-healthcheck"]' in dockerfile
    assert "HEALTHCHECK" in dockerfile and "CMD-SHELL" not in dockerfile and "sh -c" not in dockerfile.split("HEALTHCHECK", 1)[1]
