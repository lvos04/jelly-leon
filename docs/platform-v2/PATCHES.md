# Patchregister Jelly Leon (core-patches op upstream-bestanden)

Elke wijziging aan een bestand **buiten** de fork-eigen paden (`tools/jelly-leon/fork_paths.txt`) ten opzichte van de
upstream-basis (`tools/jelly-leon/baseline.json` → `upstream_commit`) is een **core-patch** en moet hier staan
(ADR-0001). `tools/jelly-leon/patch_register_check.py` controleert dat in CI:

- een niet-geregistreerd gewijzigd, toegevoegd, verwijderd of hernoemd upstream-bestand → CI faalt;
- een geregistreerd bestand dat niet (meer) afwijkt → CI faalt (register verouderd, bv. na upstream-acceptatie);
- `LICENSE`, `CONTRIBUTORS.md` en `SharedVersion.cs` mogen **nooit** afwijken (GPL-credits, technische identiteit).

Volgorde vóór een core-patch: configuratie → bestaande upstream-plugin → eigen plugin → externe dienst → pas dan patch.

**Vorm per patch** (de checker leest deze tabelvelden): `Status` ∈ `actief` | `upstream-aangeboden` | `vervallen`;
`Bestanden` met elk pad tussen backticks; verplicht ook `Doel`, `Waarom geen plugin/configuratie`, `Upstream-PR-kans`, `Test`.

| ID | Titel | Soort | Status |
|---|---|---|---|
| JL-0001 | Repository-guards op upstream-bot-workflows | CI (geen servercode) | actief |

Servercode (C#): **geen** core-patches in P0.

## JL-0001 — Repository-guards op upstream-bot-workflows

| Veld | Waarde |
|---|---|
| Status | actief |
| Soort | CI-configuratie; raakt geen servercode, API of clientgedrag |
| Sinds | 2026-11-09 (forkversie 10.11.11-jl.0) |
| Doel | Upstream-workflows die `secrets.JF_BOT_TOKEN` of upstream-infrastructuur nodig hebben, niet laten falen of onbedoeld laten handelen in de fork; workflows zelf niet stilletjes uitzetten (ADR-0007). |
| Bestanden | `.github/workflows/commands.yml`, `.github/workflows/issue-template-check.yml`, `.github/workflows/release-bump-version.yaml`, `.github/workflows/ci-compat.yml` |
| Wijziging | `commands.yml` (rebase/rename-bot) en `issue-template-check.yml`: job-`if` uitgebreid met `github.repository == 'jellyfin/jellyfin'`. `release-bump-version.yaml`: beide jobs alleen in upstream — anders zou een GitHub-release in de fork de serverversie ophogen en pushen (in strijd met ADR-0005). `ci-compat.yml`: de twee commentaarstappen met `JF_BOT_TOKEN` alleen in upstream; in de fork komt het ApiCompat-resultaat in de job-samenvatting. |
| Waarom geen plugin/configuratie | Workflowbestanden zijn niet via een plugin of instelling aan te passen; uitschakelen via de GitHub-UI is onzichtbaar in de repo ("stilletjes"). |
| Upstream-PR-kans | laag — upstream heeft deze guards niet nodig; mogelijk wel als "fork-vriendelijke workflows"-voorstel. Bij elke sync kan een conflict in deze bestanden ontstaan; dan de guard opnieuw toepassen. |
| Test | `tools/jelly-leon/patch_register_check.py` (CI-job *Forkregels*); `actionlint` op de gewijzigde workflows lokaal geslaagd (zie `BOUWVERIFICATIE_P0.md`). Echte GitHub-run: NIET GEVALIDEERD. |
| Bekend bij volgende sync | Syncproef naar v12.4 (herbasis, 2026-11-09): conflict in `.github/workflows/commands.yml` — upstream wijzigde de `if:`-regel van de rename-job (MEMBER-check verwijderd) en actie-versies. Guard dan opnieuw op de nieuwe regel zetten. |
