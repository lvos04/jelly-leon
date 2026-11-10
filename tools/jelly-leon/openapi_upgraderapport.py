#!/usr/bin/env python3
"""Upgraderapport van de upstream-API: wat verandert er tussen twee OpenAPI-exports (bv. 10.11.11 → 12.4)?

Doel (B03-014, ADR-0011 §3): de OpenAPI van de server wordt bij een reekssprong BEWUST vervangen door de nieuwe
export; dit rapport maakt de wijzigingen zichtbaar voor de beoordeling van de clientimpact (stock-apps, MediaGuard,
de Hub-adapter, de overnametool). Het oordeelt niet zelf: het somt op wat clients kan breken.

Breekbaar voor bestaande clients (`breekbaar`):
  - verwijderde paden of operaties;
  - per operatie: verwijderde parameters, parameters die verplicht werden, nieuwe verplichte parameters,
    een verplicht geworden requestBody, verwijderde succes-statuscodes;
  - verwijderde schema's, verwijderde eigenschappen, eigenschappen met een ander type, verwijderde enumwaarden.
Uitbreidingen (`additief`): nieuwe paden/operaties/schema's/eigenschappen/enumwaarden.

Met `--bron <map>` (één of meer keren) wordt per verdwenen operatie gezocht of de route nog in de broncode staat
(klasse-`[Route("…")]` + methode-`[HttpGet("…")]` e.d.): dan is hij alleen uit de documentatie gehaald (bv.
`[ApiExplorerSettings(IgnoreApi = true)]`) en wordt hij nog geserveerd; anders is hij echt verwijderd. Of een verborgen
route echt antwoordt, meet de compat-rooktest tegen de draaiende server (geen 404).

Alleen standaardbibliotheek. Exitcode 0 = rapport gemaakt (ook als er breekbare wijzigingen zijn), 3 = invoerfout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

METHODS = ("get", "put", "post", "delete", "patch", "head", "options")


def load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FOUT: {path} niet leesbaar als JSON: {exc}") from exc
    if not isinstance(data, dict) or "paths" not in data:
        raise SystemExit(f"FOUT: {path} is geen OpenAPI-document (paths ontbreekt)")
    return data


def operations(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for path, item in doc.get("paths", {}).items():
        for method in METHODS:
            if method in item:
                result[f"{method.upper()} {path}"] = item[method]
    return result


def params(op: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f"{p.get('in')}:{p.get('name')}": p for p in op.get("parameters", []) if isinstance(p, dict)}


def type_of(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return type_of(schema["allOf"][0])
    kind = schema.get("type", "?")
    if kind == "array":
        return f"array<{type_of(schema.get('items', {}))}>"
    fmt = schema.get("format")
    return f"{kind}({fmt})" if fmt else str(kind)


def compare_operation(old: dict[str, Any], new: dict[str, Any]) -> tuple[list[str], list[str]]:
    breaking: list[str] = []
    additive: list[str] = []
    po, pn = params(old), params(new)
    for key in sorted(set(po) - set(pn)):
        breaking.append(f"parameter verwijderd: {key}")
    for key in sorted(set(pn) - set(po)):
        (breaking if pn[key].get("required") else additive).append(
            f"parameter nieuw{' (verplicht)' if pn[key].get('required') else ''}: {key}"
        )
    for key in sorted(set(po) & set(pn)):
        if pn[key].get("required") and not po[key].get("required"):
            breaking.append(f"parameter verplicht geworden: {key}")
        to, tn = type_of(po[key].get("schema", {})), type_of(pn[key].get("schema", {}))
        if to != tn:
            breaking.append(f"parametertype {key}: {to} → {tn}")
    if (new.get("requestBody") or {}).get("required") and not (old.get("requestBody") or {}).get("required"):
        breaking.append("requestBody verplicht geworden")
    ro = {c for c in old.get("responses", {}) if str(c).startswith("2")}
    rn = {c for c in new.get("responses", {}) if str(c).startswith("2")}
    for code in sorted(ro - rn):
        breaking.append(f"succescode verdwenen: {code}")
    if old.get("deprecated") is not True and new.get("deprecated") is True:
        additive.append("nu als deprecated gemarkeerd")
    return breaking, additive


def compare_schemas(old: dict[str, Any], new: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    breaking: dict[str, list[str]] = {}
    additive: dict[str, list[str]] = {}
    for name in sorted(set(old) | set(new)):
        if name not in new:
            breaking.setdefault(name, []).append("schema verwijderd")
            continue
        if name not in old:
            additive.setdefault(name, []).append("schema nieuw")
            continue
        so, sn = old[name], new[name]
        eo, en = so.get("enum"), sn.get("enum")
        if isinstance(eo, list) and isinstance(en, list):
            gone = [v for v in eo if v not in en]
            added = [v for v in en if v not in eo]
            if gone:
                breaking.setdefault(name, []).append(f"enumwaarden verwijderd: {gone}")
            if added:
                additive.setdefault(name, []).append(f"enumwaarden nieuw: {added}")
        po, pn = so.get("properties", {}) or {}, sn.get("properties", {}) or {}
        for prop in sorted(set(po) - set(pn)):
            breaking.setdefault(name, []).append(f"eigenschap verwijderd: {prop}")
        for prop in sorted(set(pn) - set(po)):
            additive.setdefault(name, []).append(f"eigenschap nieuw: {prop}")
        for prop in sorted(set(po) & set(pn)):
            to, tn = type_of(po[prop]), type_of(pn[prop])
            if to != tn:
                breaking.setdefault(name, []).append(f"type {prop}: {to} → {tn}")
        ro, rn = set(so.get("required", []) or []), set(sn.get("required", []) or [])
        for prop in sorted(rn - ro):
            breaking.setdefault(name, []).append(f"eigenschap verplicht geworden: {prop}")
    return breaking, additive


CLASS_ROUTE_RE = re.compile(r'^\s*\[Route\("([^"]*)"\)\]\s*\n(?:\s*\[[^\n]*\]\s*\n)*\s*public (?:sealed |abstract )?class', re.MULTILINE)
CLASS_NAME_RE = re.compile(r"^\s*public (?:sealed |abstract )?class (\w+)(?:\s*:\s*(\w+))?", re.MULTILINE)
# Upstream: BaseJellyfinApiController draagt [Route("[controller]")]; afgeleide controllers erven die.
INHERITED_ROUTE = {"BaseJellyfinApiController": "[controller]"}
HTTP_ATTR_RE = re.compile(r'\[Http(Get|Post|Put|Delete|Patch|Head|Options)(?:\("([^"]*)"[^)]*\))?')


def source_routes(source: Path) -> dict[str, list[str]]:
    """Alle routes uit de broncode als "METHODE pad" (klasse-`[Route]` + methode-`[Http…]`) → bestanden."""
    routes: dict[str, list[str]] = {}
    for file in sorted(source.rglob("*.cs")):
        text = file.read_text(encoding="utf-8", errors="replace")
        if "[Http" not in text:
            continue
        prefix_match = CLASS_ROUTE_RE.search(text)
        class_match = CLASS_NAME_RE.search(text)
        prefix = prefix_match.group(1) if prefix_match else ""
        if prefix_match is None and class_match and class_match.group(2):
            prefix = INHERITED_ROUTE.get(class_match.group(2), "")
        if class_match:
            prefix = prefix.replace("[controller]", class_match.group(1).removesuffix("Controller"))
        for method, template in HTTP_ATTR_RE.findall(text):
            if template.startswith(("/", "~/")):
                full = template.lstrip("~/")
            elif template:
                full = f"{prefix.strip('/')}/{template}" if prefix else template
            else:
                full = prefix
            key = f"{method.upper()} /{full.strip('/')}".lower()
            routes.setdefault(key, []).append(file.name)
    return routes


def report(old: dict[str, Any], new: dict[str, Any], source: list[Path] | None = None) -> dict[str, Any]:
    oo, on = operations(old), operations(new)
    ops_breaking: dict[str, list[str]] = {}
    ops_additive: dict[str, list[str]] = {}
    for key in sorted(set(oo) & set(on)):
        b, a = compare_operation(oo[key], on[key])
        if b:
            ops_breaking[key] = b
        if a:
            ops_additive[key] = a
    sb, sa = compare_schemas(
        old.get("components", {}).get("schemas", {}), new.get("components", {}).get("schemas", {})
    )
    removed_ops = sorted(set(oo) - set(on))
    added_ops = sorted(set(on) - set(oo))
    served: dict[str, list[str]] = {}
    if source is not None:
        known: dict[str, list[str]] = {}
        for directory in source:
            for key, files in source_routes(directory).items():
                known.setdefault(key, []).extend(files)
        for op in removed_ops:
            hits = known.get(op.lower())
            if hits:
                served[op] = sorted(set(hits))
    return {
        "schema": "jelly-leon/openapi-upgraderapport/1",
        "oud": old.get("info", {}).get("version"),
        "nieuw": new.get("info", {}).get("version"),
        "telling": {
            "operaties_oud": len(oo),
            "operaties_nieuw": len(on),
            "operaties_verwijderd": len(removed_ops),
            "waarvan_nog_in_broncode": len(served),
            "operaties_nieuw_toegevoegd": len(added_ops),
            "operaties_breekbaar_gewijzigd": len(ops_breaking),
            "schemas_breekbaar_gewijzigd": len(sb),
        },
        "breekbaar": {
            "operaties_verwijderd": [op for op in removed_ops if op not in served],
            "operaties_alleen_uit_documentatie": served if source is not None else "niet onderzocht (geen --bron)",
            "operaties_gewijzigd": ops_breaking,
            "schemas": sb,
        },
        "additief": {
            "operaties_nieuw": added_ops,
            "operaties_gewijzigd": ops_additive,
            "schemas": sa,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upgraderapport tussen twee OpenAPI-exports (clientimpact).")
    parser.add_argument("--oud", type=Path, required=True)
    parser.add_argument("--nieuw", type=Path, required=True)
    parser.add_argument("--uit", type=Path, help="pad voor het JSON-rapport (anders stdout)")
    parser.add_argument("--bron", type=Path, action="append",
                        help="map met controllers van de nieuwe versie (bv. Jellyfin.Api); mag vaker")
    args = parser.parse_args(argv)
    try:
        result = report(load(args.oud), load(args.nieuw), args.bron)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 3
    text = json.dumps(result, indent=1, ensure_ascii=False) + "\n"
    if args.uit:
        args.uit.parent.mkdir(parents=True, exist_ok=True)
        args.uit.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    t = result["telling"]
    print(
        f"{result['oud']} → {result['nieuw']}: operaties {t['operaties_oud']} → {t['operaties_nieuw']}; "
        f"verwijderd {t['operaties_verwijderd']} (waarvan nog in de broncode {t['waarvan_nog_in_broncode']}), "
        f"nieuw {t['operaties_nieuw_toegevoegd']}, breekbaar gewijzigd {t['operaties_breekbaar_gewijzigd']}; "
        f"schema's breekbaar gewijzigd {t['schemas_breekbaar_gewijzigd']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
