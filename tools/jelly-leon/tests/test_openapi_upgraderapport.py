"""openapi_upgraderapport.py: breekbare en additieve wijzigingen tussen twee OpenAPI-exports (B03-014)."""

from __future__ import annotations

import json
from pathlib import Path

import openapi_upgraderapport as rap

OLD = {
    "openapi": "3.0.4",
    "info": {"version": "1.0.0"},
    "paths": {
        "/Items": {"get": {"parameters": [{"name": "userId", "in": "query", "schema": {"type": "string"}},
                                          {"name": "oud", "in": "query", "schema": {"type": "boolean"}}],
                           "responses": {"200": {}}}},
        "/Weg": {"get": {"responses": {"200": {}}}},
        "/Verborgen/{id}/master.m3u8": {"get": {"responses": {"200": {}}}},
        "/Devices": {"delete": {"parameters": [{"name": "id", "in": "query", "schema": {"type": "string"}}],
                                "responses": {"204": {}}}},
    },
    "components": {"schemas": {
        "Dto": {"properties": {"A": {"type": "string"}, "B": {"type": "integer", "format": "int32"}}},
        "Soort": {"enum": ["Een", "Twee"]},
        "Oud": {"properties": {}},
    }},
}
NEW = {
    "openapi": "3.0.4",
    "info": {"version": "2.0.0"},
    "paths": {
        "/Items": {"get": {"parameters": [{"name": "userId", "in": "query", "required": True, "schema": {"type": "string"}},
                                          {"name": "nieuw", "in": "query", "schema": {"type": "string"}}],
                           "responses": {"200": {}}}},
        "/Devices": {"delete": {"parameters": [{"name": "id", "in": "query",
                                                "schema": {"type": "array", "items": {"type": "string"}}}],
                                "responses": {"204": {}}}},
        "/Nieuw": {"post": {"responses": {"204": {}}}},
    },
    "components": {"schemas": {
        "Dto": {"properties": {"A": {"type": "string"}, "C": {"type": "boolean"}}, "required": ["A"]},
        "Soort": {"enum": ["Een", "Drie"]},
    }},
}

CONTROLLER = '''namespace X;

[Route("")]
[Authorize]
[ApiExplorerSettings(IgnoreApi = true)]
public class HlsController : BaseJellyfinApiController
{
    [HttpGet("Verborgen/{id}/master.m3u8")]
    public void Master() { }
}
'''


def test_report_classifies_changes(tmp_path: Path) -> None:
    (tmp_path / "HlsController.cs").write_text(CONTROLLER, encoding="utf-8")
    result = rap.report(OLD, NEW, [tmp_path])
    breaking = result["breekbaar"]
    assert breaking["operaties_verwijderd"] == ["GET /Weg"]
    assert breaking["operaties_alleen_uit_documentatie"] == {"GET /Verborgen/{id}/master.m3u8": ["HlsController.cs"]}
    items = breaking["operaties_gewijzigd"]["GET /Items"]
    assert "parameter verwijderd: query:oud" in items and "parameter verplicht geworden: query:userId" in items
    assert breaking["operaties_gewijzigd"]["DELETE /Devices"] == ["parametertype query:id: string → array<string>"]
    assert breaking["schemas"]["Oud"] == ["schema verwijderd"]
    assert "eigenschap verwijderd: B" in breaking["schemas"]["Dto"]
    assert "eigenschap verplicht geworden: A" in breaking["schemas"]["Dto"]
    assert breaking["schemas"]["Soort"] == ["enumwaarden verwijderd: ['Twee']"]
    additive = result["additief"]
    assert additive["operaties_nieuw"] == ["POST /Nieuw"]
    assert additive["operaties_gewijzigd"]["GET /Items"] == ["parameter nieuw: query:nieuw"]
    assert "eigenschap nieuw: C" in additive["schemas"]["Dto"]
    assert result["telling"]["waarvan_nog_in_broncode"] == 1


def test_inherited_controller_route(tmp_path: Path) -> None:
    (tmp_path / "MusicGenresController.cs").write_text(
        "public class MusicGenresController : BaseJellyfinApiController\n{\n    [HttpGet]\n    public void A() { }\n}\n",
        encoding="utf-8",
    )
    routes = rap.source_routes(tmp_path)
    assert routes == {"get /musicgenres": ["MusicGenresController.cs"]}


def test_cli_writes_report(tmp_path: Path, capsys) -> None:
    old, new, out = tmp_path / "oud.json", tmp_path / "nieuw.json", tmp_path / "r.json"
    old.write_text(json.dumps(OLD), encoding="utf-8")
    new.write_text(json.dumps(NEW), encoding="utf-8")
    assert rap.main(["--oud", str(old), "--nieuw", str(new), "--uit", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["telling"]["operaties_verwijderd"] == 2
    assert "1.0.0 → 2.0.0" in capsys.readouterr().err
    (tmp_path / "kapot.json").write_text("{", encoding="utf-8")
    assert rap.main(["--oud", str(tmp_path / "kapot.json"), "--nieuw", str(new)]) == 3
