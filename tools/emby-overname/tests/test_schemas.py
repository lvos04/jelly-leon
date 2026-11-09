"""De bestandsformaten van de tool (export, plan, rapport, akkoord) volgen de JSON Schemas in `schemas/`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from test_integratie import akkoord_voor, basis_args, draai, vul  # noqa: E402

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def valideer(naam: str, data: dict) -> None:
    schema = json.loads((SCHEMAS / naam).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(data)


def test_uitvoer_volgt_de_schemas(emby, jl, sleutels, tmp_path, capsys):
    vul(emby, jl)
    werkmap = tmp_path / "werk"
    _, proef = draai(["proefrun", *basis_args(emby, jl, sleutels, werkmap)], capsys)
    akkoord = akkoord_voor(proef, "plan", tmp_path / "akkoord.json")
    _, over = draai(["overzetten", *basis_args(emby, jl, sleutels, werkmap), "--akkoord", str(akkoord)], capsys)
    for samenvatting in (proef, over):
        valideer("emby-overname-rapport.schema.json", json.loads(Path(samenvatting["rapport"]).read_text(encoding="utf-8")))
        valideer("emby-kijkgegevens-export.schema.json",
                 json.loads((Path(samenvatting["map"]) / "emby-export.json").read_text(encoding="utf-8")))
    valideer("emby-overname-akkoord.schema.json", json.loads(akkoord.read_text(encoding="utf-8")))
    plannen = list((werkmap / "plannen").glob("*.json"))
    assert plannen
    for pad in plannen:
        valideer("emby-overname-plan.schema.json", json.loads(pad.read_text(encoding="utf-8")))


def test_schema_weigert_eindstatus_en_vreemde_velden():
    with pytest.raises(jsonschema.ValidationError):
        valideer("emby-overname-akkoord.schema.json", {"schema": "jelly-leon/emby-overname-akkoord/1", "soort": "ja",
                                                       "rapport_inhoud_sha256": "0" * 64, "akkoord_door": "x", "datum": "",
                                                       "verschillen": []})
