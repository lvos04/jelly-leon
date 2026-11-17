"""Een onvolledige of rode opslagproef mag niet als dicht worden beoordeeld."""
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("opslag_grensproef", Path(__file__).parents[1] / "opslag_grensproef.py")
assert SPEC and SPEC.loader
proef = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proef)


def test_onvolledig_is_geen_bewijs(tmp_path):
    log = tmp_path / "proef.log"
    log.write_text("OPSLAGPROEVEN=[]\n")
    assert proef.beoordeel(log) == 2


def test_een_buitenwijziging_blijft_rood(tmp_path):
    log = tmp_path / "proef.log"
    rijen = [{"proef": p, "bytegelijk": True, "mapgelijk": True, "weigering": None} for p in proef.PROEVEN]
    rijen[0]["bytegelijk"] = False
    log.write_text("OPSLAGPROEVEN=" + json.dumps(rijen) + "\n")
    assert proef.beoordeel(log) == 1
    rijen[0]["bytegelijk"] = True
    rijen[0]["mapgelijk"] = False
    log.write_text("OPSLAGPROEVEN=" + json.dumps(rijen) + "\n")
    assert proef.beoordeel(log) == 1


def test_alleen_volledig_ongewijzigd_is_groen(tmp_path):
    log = tmp_path / "proef.log"
    rijen = [{"proef": p, "bytegelijk": True, "mapgelijk": True, "weigering": None} for p in proef.PROEVEN]
    log.write_text("OPSLAGPROEVEN=" + json.dumps(rijen) + "\n")
    assert proef.beoordeel(log) == 0
