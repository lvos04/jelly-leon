"""Contract van de WT-1-proef en de twee toegestane normalisaties."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "jelly-leon" / "e2e"))
import watch_contract as watch  # noqa: E402


class ProefHttp:
    def __init__(self, naam="Lid", compact=True):
        self.groep = {"GroupId": str(uuid.uuid4()), "GroupName": "WT-contract", "Participants": [naam], "LastUpdatedAt": "2026-01-01T00:00:00Z"}
        self.compact = compact
        self.verlaten = False

    def doe(self, methode, pad, **kwargs):
        assert methode == "POST"
        if pad == "/SyncPlay/New":
            assert kwargs["body"]["GroupName"] == self.groep["GroupName"]
            return self.groep
        assert pad == "/SyncPlay/Leave"
        self.verlaten = True

    def ruw(self, methode, pad):
        assert methode == "GET"
        assert pad in ("/SyncPlay/List", "/SyncPlay/" + self.groep["GroupId"])
        data = [self.groep] if pad == "/SyncPlay/List" else self.groep
        return 200, json.dumps(data, separators=(",", ":") if self.compact else None).encode(), {}


def test_alleen_groepsid_en_tijd_worden_genormaliseerd():
    basis = ProefHttp()
    tweede = ProefHttp()
    tweede.groep["LastUpdatedAt"] = "2026-02-02T00:00:04.1234567Z"
    verwacht = watch.groepsopname(basis)
    assert watch.groepsopname(tweede) == verwacht and basis.verlaten and tweede.verlaten
    assert watch.groepsopname(ProefHttp("Ander")) != verwacht
    assert watch.groepsopname(ProefHttp(compact=False)) != verwacht
    tweede.groep["Participants"] = []
    with pytest.raises(RuntimeError, match="deelnemer"):
        watch.groepsopname(tweede)


def test_alle_operaties_en_hun_schemas_wegen_mee():
    doc = json.loads((REPO / "docs/openapi/jelly-leon.openapi.json").read_bytes())
    opname = watch.contract(doc)
    assert "GroupInfoDto" in opname["schemas"] and len(opname["paths"]) == 23
    origineel = json.dumps(opname, sort_keys=True)
    doc["components"]["schemas"]["GroupInfoDto"]["properties"].pop("Participants")
    assert json.dumps(watch.contract(doc), sort_keys=True) != origineel
    del doc["paths"]["/GetUtcTime"]
    with pytest.raises(ValueError, match="22 SyncPlay"):
        watch.contract(doc)
