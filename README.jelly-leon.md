# Jelly Leon

Jelly Leon is de mediaserver van het TrueNAS Home Platform V2 (bouwplan **B03**): een fork van
[Jellyfin](https://github.com/jellyfin/jellyfin) **v10.11.11**, gelicenseerd onder **GPL-2.0** (zie `LICENSE`;
upstream-credits in `CONTRIBUTORS.md`). De technische identiteit blijft *Jellyfin* zodat alle bestaande Jellyfin-apps
blijven werken; alleen de zichtbare naam is *Jelly Leon*. Jelly Leon is geen officiële Jellyfin-release.

De upstream-README staat ongewijzigd in `README.md`.

## Waar staat wat

| Pad | Inhoud |
|---|---|
| `docs/platform-v2/FORK_STRATEGIE.md` | forkstrategie (plugin vóór patch, branding, GPL, versies, sync) |
| `docs/platform-v2/PATCHES.md` | patchregister: elke afwijking van upstream (CI dwingt dit af) |
| `docs/platform-v2/INVENTARIS.md` | wat upstream al kan + delta-matrix B03 |
| `docs/platform-v2/CLIENT_COMPAT_MATRIX.md` | compatibiliteit server ↔ clients |
| `docs/platform-v2/BOUWVERIFICATIE_P0.md`, `test-evidence/` | gemeten bouw- en testresultaten |
| `docs/platform-v2/EVIDENCE.json` | status per Excel-taak (nooit "Gereed" zonder echte acceptatie) |
| `docs/adr/` | architectuurbesluiten ADR-0001…0011 (ADR-0011: vóór P4 naar Jellyfin 12.x, besluit gebruiker) |
| `docs/openapi/` | upstream-API (gegenereerd) en de fork-eigen pluginroutes |
| `plugins/` | eigen Jellyfin-plugins (eigen solution, tegen dezelfde Jellyfin-versie) |
| `tools/jelly-leon/` | `baseline.json` (bron van waarheid), patchregister-/consistentiecontrole, upstream-sync, smoketest, levenscyclus- en terugzetproef van de image (`e2e/`) |
| `deploy/` | alles-in-één image (lokaal volledig gebouwd en getest; publicatie in P4), TrueNAS Custom App-formulier, manifest |
| `.github/workflows/jelly-leon-ci.yml`, `upstream-sync.yml` | eigen CI en upstream-sync (nooit automatisch naar productie) |

## Ontwikkelen

- Server: `dotnet build Jellyfin.sln -c Release` en `dotnet test Jellyfin.sln -c Release` (.NET 9 SDK).
- Plugins: `dotnet build plugins/JellyLeon.Plugins.sln -c Release` en `dotnet test …`.
- Forkregels: `python3 tools/jelly-leon/check_fork_consistency.py`, `python3 tools/jelly-leon/patch_register_check.py`,
  `python3 -m pytest tools/jelly-leon/tests` (venv in `tools/jelly-leon/.venv`, niet committen).

## Installeren

Alleen als **standaard TrueNAS Custom App** (geen YAML, geen compose, geen terminal): zie
`deploy/truenas/CUSTOM_APP.md`. Er is nog geen gepubliceerde image: de eerste release (`<upstream>-jl.1`) volgt
pas na de upgrade naar de nieuwste stabiele Jellyfin 12.x (ADR-0011, besluit van de gebruiker).
