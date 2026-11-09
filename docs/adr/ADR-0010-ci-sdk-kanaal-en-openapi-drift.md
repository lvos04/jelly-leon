# ADR-0010 — CI: .NET-SDK-kanaal uit global.json en structurele OpenAPI-driftcontrole

- **Status:** Aanvaard (P0-afronding, 2026-11-09)
- **Context:** De eerste runs van *Jelly Leon CI* op GitHub (42595226924, 42595990869, 42605533435) faalden in de jobs
  *server* en *plugins*: `actions/setup-dotnet` met `global-json-file: global.json` gaf "Could not find .NET Core SDK
  with version = 9.0.0". Bij het lokaal herhalen van build en tests op de Ubuntu-machine (2026-11-09) bleek bovendien
  dat de gegenereerde `openapi.json` níet byte-gelijk was aan `docs/openapi/jelly-leon.openapi.json`, terwijl broncode,
  SDK-image (digest) en NuGet-pakketten gelijk waren aan de sandboxmeting waarin hij wel byte-gelijk was.

## Besluit 1 — SDK-kanaal afleiden, global.json niet patchen

- `global.json` is een upstream-bestand (`"version": "9.0.0", "rollForward": "latestMinor"`). 9.0.0 is een ondergrens,
  geen downloadbare SDK. Upstream zelf installeert in zijn workflows `9.0.x`.
- `tools/jelly-leon/dotnet_sdk_kanaal.py` leidt het kanaal `<major>.<minor>.x` af uit global.json; de workflows
  installeren dat kanaal en `dotnet` kiest daarna zelf via global.json/rollForward (`dotnet --version` staat als stap in
  de log). Zo blijft global.json de enige bron van waarheid en volgt een upstream-sync naar 12.x (global.json 10.0.0)
  vanzelf het kanaal `10.0.x`.
- **Geen core-patch:** global.json blijft byte-gelijk aan upstream (minder conflicten bij elke sync, PATCHES.md
  ongewijzigd).
- `check_fork_consistency.py` bewaakt dat `baseline.json` → `dotnet_sdk_major` en de SDK-image in
  `deploy/allinone/Dockerfile` bij dezelfde reeks horen als global.json (het deploy-deel niet in sync-modus: de
  Dockerfile volgt pas bij een release). `upstream_sync.py` werkt `dotnet_sdk_major` mee bij.

Overwogen: `dotnet-version: '9.0.x'` hard in de workflow (zoals upstream) — werkt nu, maar breekt stil bij de sprong
naar 12.x/.NET 10; global.json aanpassen naar een bestaande versie — onnodige core-patch.

## Besluit 2 — OpenAPI-drift structureel vergelijken

**Gemeten oorzaak (upstream, niet door de fork):** `Jellyfin.Server/Extensions/ApiServiceCollectionExtensions.cs`
laadt de XML-docbestanden met `Directory.EnumerateFiles(AppContext.BaseDirectory, "*.xml")` — zonder sortering, dus in
de volgorde van het bestandssysteem. Voor eigenschappen die naar een ander schema verwijzen (`allOf`/`$ref`) bepaalt die
volgorde welke XML-tekst als `description` wint (bv. "Gets or sets the user." of "Class UserDto.").

| Proef (zelfde build, `OpenApiSpecTests`) | sha256 `openapi.json` | Verschil met `docs/openapi` |
|---|---|---|
| oude sandbox (2×, P0) | `f0580e74a4e4…` | byte-gelijk |
| Ubuntu-machine, ext4, volledige testrun en 2× alleen `OpenApiSpecTests` | `4bd2d710549c…` | 22 `description`-teksten, verder identiek |
| tmpfs, XML-bestanden in oplopende aanmaakvolgorde | `94be85990695…` | 9 `description`-teksten |
| tmpfs, XML-bestanden in aflopende aanmaakvolgorde | `4bd2d710549c…` | 22 `description`-teksten |

Een byte-vergelijking is dus omgevingsafhankelijk en zou op GitHub-runners willekeurig rood of groen zijn.

- `tools/jelly-leon/openapi_drift.py` vergelijkt in lagen: byte-gelijk → in orde; structureel gelijk (paden, operaties,
  `operationId`, `summary`, parameters, schema's, typen, enums, `required`, `nullable`, voorbeeldwaarden …) met alleen
  andere `description`-teksten → in orde met een waarschuwing; elke andere afwijking → falen (API-wijziging = core-patch).
  `description` binnen voorbeeld- of standaardwaarden en een schema-eigenschap die zelf `description` heet tellen wél mee.
- Het vastgelegde bestand `docs/openapi/jelly-leon.openapi.json` blijft ongewijzigd (één van de geldige varianten).
- **Geen core-patch** om de XML-volgorde te sorteren: het raakt alleen documentatieteksten, niet de API. Wel een
  upstream-PR-kans (sorteren van `xmlFiles`) — followup, niet in deze fork.

## Gevolgen

- CI-jobs *server*, *plugins* en *stock-client-e2e* installeren de actuele 9.0.x-SDK; upstream-sync gebruikt het kanaal
  van de nieuwe basis.
- Een wijziging in alleen beschrijvingen geeft een `::warning::` in de job, geen rode CI. Een echte API-wijziging blijft
  CI laten falen.
- Tests: `tools/jelly-leon/tests/test_dotnet_sdk.py`, `tests/test_openapi_drift.py`,
  `tests/test_upstream_sync_herbasis.py::test_herbasis_follows_sdk_line_of_new_base`.
