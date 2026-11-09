"""deploy/allinone/healthcheck.sh (Docker-healthcheck, contract 1.2 §2.2): curl draait nooit als root.

Zonder Docker: `id`, `setpriv` en `curl` zijn nepprogramma's in PATH die hun argumenten vastleggen. Zo is te zien welke
rechtenwissel het script vraagt (als root en als Custom User) en dat een mislukte /health-aanvraag de healthcheck rood
maakt (exitcode ≠ 0). De echte wissel meet tools/jelly-leon/e2e/image_lifecycle.py in de container (`--toon-rechten`).
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "deploy" / "allinone" / "healthcheck.sh"


def write_tool(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_healthcheck(tmp_path: Path, *args: str, uid: str, curl_exit: int = 0) -> tuple[int, list[str], str]:
    tools = tmp_path / "bin"
    tools.mkdir(exist_ok=True)
    log = tmp_path / "aanroepen.log"
    write_tool(tools, "id", f'[ "$1" = "-u" ] && echo {uid}\n')
    # setpriv: argumenten vastleggen en daarna (zoals echt) het programma na `--` uitvoeren.
    write_tool(
        tools,
        "setpriv",
        f'printf "setpriv %s\\n" "$*" >> "{log}"\n'
        'while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do shift; done\nshift\nexec "$@"\n',
    )
    write_tool(tools, "curl", f'printf "curl %s\\n" "$*" >> "{log}"\nexit {curl_exit}\n')
    write_tool(tools, "cat", f'printf "cat %s\\n" "$*" >> "{log}"\n')
    env = {"PATH": f"{tools}{os.pathsep}/usr/bin{os.pathsep}/bin"}
    proc = subprocess.run(["/bin/sh", str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc.returncode, calls, proc.stderr


def test_as_root_drops_to_568_without_capabilities_before_curl(tmp_path):
    rc, calls, _ = run_healthcheck(tmp_path, uid="0")
    assert rc == 0
    assert calls[0] == (
        "setpriv --reuid=568 --regid=568 --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs -- "
        "curl --noproxy localhost -fsS --max-time 8 -o /dev/null http://localhost:8096/health"
    )
    assert calls[1].startswith("curl ") and len(calls) == 2


def test_as_custom_user_sets_no_new_privs_before_curl(tmp_path):
    rc, calls, _ = run_healthcheck(tmp_path, uid="568")
    assert rc == 0
    assert calls[0].startswith("setpriv --no-new-privs --inh-caps=-all -- curl ")
    assert "--reuid" not in calls[0]


@pytest.mark.parametrize("uid", ["0", "568"])
def test_failed_health_request_makes_the_healthcheck_red(tmp_path, uid):
    rc, calls, _ = run_healthcheck(tmp_path, uid=uid, curl_exit=7)  # 7 = geen verbinding
    assert rc == 7
    assert calls[-1].startswith("curl ")


def test_rights_probe_uses_the_same_drop(tmp_path):
    rc, calls, _ = run_healthcheck(tmp_path, "--toon-rechten", uid="0")
    assert rc == 0
    assert calls[0].startswith("setpriv --reuid=568 --regid=568 --clear-groups --inh-caps=-all --bounding-set=-all")
    assert calls[0].endswith("-- cat /proc/self/status")


def test_unknown_option_is_refused_without_running_anything(tmp_path):
    rc, calls, err = run_healthcheck(tmp_path, "--shell", uid="0")
    assert rc == 2 and calls == []
    assert "onbekende optie" in err


def test_dockerfile_uses_the_wrapper_as_healthcheck():
    dockerfile = (REPO / "deploy" / "allinone" / "Dockerfile").read_text(encoding="utf-8")
    assert 'CMD ["/usr/local/bin/jelly-leon-healthcheck"]' in dockerfile
    assert "COPY deploy/allinone/healthcheck.sh /usr/local/bin/jelly-leon-healthcheck" in dockerfile
    assert '"curl"' not in dockerfile  # nooit meer curl rechtstreeks als containergebruiker
