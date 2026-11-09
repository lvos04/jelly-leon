"""OpenAPI-driftcontrole: structurele API-wijzigingen falen, alleen afwijkende beschrijvingen niet.

Aanleiding (gemeten 2026-11-09): upstream laadt XML-docbestanden in bestandssysteemvolgorde; dezelfde build gaf in twee
omgevingen 22 andere `description`-teksten (verder identiek). Op tmpfs met omgekeerde aanmaakvolgorde: weer anders.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import openapi_drift
from jl_common import DEFAULT_REPO_ROOT

BASE = {
    "openapi": "3.0.4",
    "info": {"title": "Jellyfin API", "version": "10.11.11"},
    "paths": {
        "/Users/AuthenticateByName": {
            "post": {
                "operationId": "AuthenticateUserByName",
                "summary": "Authenticates a user by name.",
                "parameters": [{"name": "X-Emby-Authorization", "in": "header", "description": "Header.", "schema": {"type": "string"}}],
                "responses": {"200": {"description": "User authenticated."}},
            }
        }
    },
    "components": {
        "schemas": {
            "AuthenticationResult": {
                "type": "object",
                "description": "Class AuthenticationResult.",
                "properties": {
                    "User": {"allOf": [{"$ref": "#/components/schemas/UserDto"}], "description": "Gets or sets the user.", "nullable": True},
                    "description": {"type": "string", "description": "Eigenschap die zelf zo heet."},
                },
                "required": ["User"],
            },
            "MediaType": {"enum": ["Unknown", "Video", "Audio"], "type": "string", "description": "Media types."},
            "Voorbeeld": {"type": "object", "example": {"description": "voorbeeldwaarde"}},
        }
    },
}


def dump(tmp_path: Path, name: str, doc: dict, indent: int | None = 2) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(doc, indent=indent), encoding="utf-8")
    return path


def run(tmp_path: Path, generated: dict, **kwargs) -> tuple[int, list[str]]:
    return openapi_drift.compare(dump(tmp_path, "verwacht.json", BASE), dump(tmp_path, "gegenereerd.json", generated, **kwargs))


def test_byte_equal_is_ok(tmp_path):
    code, lines = run(tmp_path, BASE)
    assert code == 0 and lines[0].startswith("OK: OpenAPI byte-gelijk")


def test_only_descriptions_differ_is_warning_not_failure(tmp_path):
    doc = copy.deepcopy(BASE)
    doc["components"]["schemas"]["AuthenticationResult"]["properties"]["User"]["description"] = "Class UserDto."
    doc["components"]["schemas"]["MediaType"]["description"] = "Gets or sets the type of the media."
    doc["paths"]["/Users/AuthenticateByName"]["post"]["parameters"][0]["description"] = "Anders."
    code, lines = run(tmp_path, doc)
    assert code == 0
    assert lines[0].startswith("WAARSCHUWING") and "3 description-teksten" in lines[0]
    assert '["User"]["description"]' in "\n".join(lines)


def test_formatting_only_is_warning(tmp_path):
    code, lines = run(tmp_path, BASE, indent=None)
    assert code == 0 and "alleen opmaak of sleutelvolgorde" in lines[0]


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    [
        (lambda d: d["paths"].pop("/Users/AuthenticateByName"), '$["paths"]["/Users/AuthenticateByName"]'),
        (lambda d: d["paths"]["/Users/AuthenticateByName"]["post"].update(operationId="Ander"), '["operationId"]'),
        (lambda d: d["paths"]["/Users/AuthenticateByName"]["post"].update(summary="Nieuw."), '["summary"]'),
        (lambda d: d["components"]["schemas"]["MediaType"]["enum"].remove("Audio"), '["MediaType"]["enum"]'),
        (lambda d: d["components"]["schemas"]["AuthenticationResult"].update(required=[]), '["required"]'),
        (lambda d: d["components"]["schemas"]["AuthenticationResult"]["properties"]["User"].update(nullable=False), '["nullable"]'),
        (lambda d: d["components"]["schemas"]["AuthenticationResult"]["properties"].pop("description"), '["properties"]["description"]'),
        (lambda d: d["components"]["schemas"]["Voorbeeld"]["example"].update(description="ander voorbeeld"), '["example"]["description"]'),
        (lambda d: d["paths"]["/Users/AuthenticateByName"]["post"]["parameters"][0].update(name="X-Ander"), '["parameters"][0]["name"]'),
    ],
)
def test_structural_changes_fail(tmp_path, mutation, expected_path):
    doc = copy.deepcopy(BASE)
    mutation(doc)
    code, lines = run(tmp_path, doc)
    assert code == 1, lines
    assert lines[0].startswith("FOUT: OpenAPI wijkt structureel af")
    assert expected_path in "\n".join(lines)


def test_missing_empty_and_invalid_files(tmp_path):
    expected = dump(tmp_path, "verwacht.json", BASE)
    assert openapi_drift.compare(expected, tmp_path / "bestaat-niet.json")[0] == 3
    (tmp_path / "leeg.json").write_text("", encoding="utf-8")
    assert openapi_drift.compare(expected, tmp_path / "leeg.json")[0] == 3
    (tmp_path / "kapot.json").write_text("{", encoding="utf-8")
    assert openapi_drift.compare(expected, tmp_path / "kapot.json")[0] == 3


def test_cli_github_annotations(tmp_path, capsys):
    expected = dump(tmp_path, "verwacht.json", BASE)
    doc = copy.deepcopy(BASE)
    doc["components"]["schemas"]["MediaType"]["description"] = "Anders."
    generated = dump(tmp_path, "gegenereerd.json", doc)
    assert openapi_drift.main(["--verwacht", str(expected), "--gegenereerd", str(generated), "--github"]) == 0
    assert "::warning::WAARSCHUWING" in capsys.readouterr().out
    doc["components"]["schemas"]["MediaType"]["type"] = "integer"
    generated = dump(tmp_path, "gegenereerd.json", doc)
    assert openapi_drift.main(["--verwacht", str(expected), "--gegenereerd", str(generated), "--github"]) == 1
    out, err = capsys.readouterr()
    assert "::error::FOUT" in out and '["MediaType"]["type"]' in err


def test_real_spec_against_itself_and_description_variant():
    """Integratie met de echte vastgelegde upstream-spec (315 paden): gelijk aan zichzelf; beschrijvingsvariant = waarschuwing."""
    spec = DEFAULT_REPO_ROOT / "docs/openapi/jelly-leon.openapi.json"
    assert openapi_drift.compare(spec, spec)[0] == 0
    doc = json.loads(spec.read_text(encoding="utf-8"))
    assert len(doc["paths"]) == 315
    stripped = openapi_drift.strip_descriptions(doc)
    assert "description" not in json.dumps(stripped["components"]["schemas"]["AuthenticationResult"]["properties"]["User"])
    assert stripped["paths"].keys() == doc["paths"].keys()
