# ADR-0006 — Upstream-sync via `sync/<tag>`, nooit automatisch naar productie (EX48)

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** B03-013 ("patch stack minimal; protected CI; version compatibility documented"), I06 stap 7
  ("upstream tracking branch en CI compat smoke"), I24 stap 1, testmatrix **EX48** ("nieuwe Jellyfin-upstreamcode met
  incompatibiliteit → PR-test faalt, geen productiedeploy"). Gemeten op 2026-11-09: upstream heeft naast `v10.11.11`
  al `v12.0`…`v12.4` (nieuw tagformaat zonder patchnummer, NuGet 12.x) — een sync is dus niet altijd klein.

## Besluit

1. **Werktuig:** `tools/jelly-leon/upstream_sync.py` (alleen standaardbibliotheek, unit-getest met een nep-upstream).
   - `kies` bepaalt per spoor de nieuwste **stabiele** tag die nieuwer is dan de basis: `patch` (zelfde major.minor,
     bv. 10.11.x) en `nieuwste` (hoogste stabiele tag, bv. 12.4). rc/beta/tags zonder `v` tellen nooit; volgorde is
     numeriek (`v12.10` > `v12.4`).
   - `merge` haalt de tag op in `refs/upstream-sync/<tag>` en maakt branch `sync/<tag>` met één van twee methoden
     (`--methode auto` kiest):
     - **merge** (zelfde major.minor, bv. 10.11.11 → 10.11.12): `git merge --no-ff` van de tag;
     - **herbasis** (andere reeks, bv. 10.11 → 12.x): boom = upstream-tag + fork-eigen paden (`fork_paths.txt`) +
       de geregistreerde core-patches uit `PATCHES.md` (3-way toegepast), vastgelegd als merge-commit met de vorige
       forkstand én de upstream-tag als ouders (historie blijft, geen force-push nodig). Dit is precies de regel
       "het patchregister is de volledige delta".
     Daarna `baseline.json` (`upstream_*`, `fork_version = <versie>-jl.0`) en de plugin-`JellyfinVersion` +
     `TargetFramework` (uit `MediaBrowser.Controller.csproj` van de nieuwe basis) bijwerken.
     **Conflict = incompatibel:** alles terugdraaien, branch weg, werkboom schoon, exitcode 2.
   - Weigert: rc-tags, downgrades/zelfde versie, vuile werkboom, bestaande sync-branch (exit 4).
2. **Workflow `upstream-sync.yml`:** wekelijks (maandag 04:17 UTC) en handmatig (expliciete tag of spoor). Per kandidaat:
   merge → forkregels (consistentie zonder manifest, patchregister, tool-tests) → volledige upstream-build en -tests →
   plugins bouwen/testen tegen de **nieuwe** `Jellyfin.Controller` (ABI-breuk = falen) → OpenAPI-wijziging melden →
   stock-client-smoketest. Elke fout laat de job falen (EX48).
3. **Nooit naar productie:** de workflow maakt geen release-tag, publiceert geen image en wijzigt de standaardbranch niet.
   Resultaat: git-bundle als artefact; alleen met geheim `JL_SYNC_PUSH_TOKEN` (contents + workflows-recht, omdat
   upstream-merges `.github/workflows` raken en `GITHUB_TOKEN` dat niet mag pushen) wordt `sync/<tag>` gepusht ter
   beoordeling. Overnemen in de standaardbranch en een release (`-jl.1`) zijn handmatige, goed te keuren stappen (R2).
   **Scheiding (review P0):** het push-token staat alleen in een aparte job `push` die zelf geen upstream-code bouwt,
   test of uitvoert. De sync-job (waarin upstream-MSBuild-targets en -tests draaien) heeft geen toegang tot het token;
   anders zou upstream-code via git-hooks, `PATH` of `GITHUB_ENV` het token kunnen onderscheppen. De push-job neemt
   alleen bundles over van legs waarin **alle** stappen slaagden (artefact `upstream-sync-geslaagd-<tag>`), valideert
   de tagnaam, schakelt git-hooks uit (`core.hooksPath=/dev/null`) en overschrijft een bestaande `sync/<tag>` nooit
   (geen force-push; eerst beoordelen of verwijderen). Een al bestaande lokale `upstream-<tag>` wordt alleen
   geaccepteerd als die naar dezelfde commit wijst; een verplaatste upstream-tag stopt de sync zonder wijzigingen.
4. **Grote sprongen** (andere major, bv. 10.11 → 12.x) worden net zo behandeld, maar vragen bovendien: DB-migratie op een
   kopie (canary DB copy, B03-013), clientmatrix opnieuw, terugzetpad (database + binary samen).

## Echte meting (2026-11-09, tijdelijke lokale kloon, niets gepusht)

- `kies` tegen `github.com/jellyfin/jellyfin`: spoor `patch` → geen nieuwere 10.11.x; spoor `nieuwste` → **v12.4**
  (v12.0…v12.4). v12.4 vraagt .NET SDK 10 (`global.json` 10.0.0), `TargetFramework` net10.0, `AssemblyVersion` 12.4.0.
- **merge** van v12.4: **79 conflicten**, waarvan maar 4 in door de fork gewijzigde bestanden — de rest komt doordat
  upstream 10.11.x-fixes als backports op een releasebranch zette (gemeenschappelijke voorouder 2025-10-19, 2 443
  upstream-commits). Een gewone merge is voor een reekssprong dus onbruikbaar.
- **herbasis** van v12.4: **1 conflict** — `.github/workflows/commands.yml` (JL-0001): upstream wijzigde precies de
  bewaakte `if:`-regel. De sync faalt dus terecht (EX48) en wijst exact aan welke patch handwerk vraagt.
- Bouwen/testen van 12.4 is hier niet uitgevoerd (andere SDK, conflict eerst oplossen) — NIET GEVALIDEERD.

## Gevolgen

- EX48 is in simulatie aangetoond (`tools/jelly-leon/tests/test_upstream_sync.py::test_merge_incompatible_tag_fails_cleanly_ex48`).
  Een echte GitHub-run is nog **NIET GEVALIDEERD** (workflow nog niet op de standaardbranch; scheduled workflows draaien
  alleen daar).
- Zonder `JL_SYNC_PUSH_TOKEN` blijft alles werken, maar moet een mens de bundle ophalen. Geheimen nooit in de repo.
- Upstream-security: GitHub-advisories van `jellyfin/jellyfin` volgen (followup); de wekelijkse run toont nieuwe
  patchreleases in de samenvatting.

## Overwogen alternatieven

- *Rebasen van de fork op upstream* — verworpen: herschrijft gedeelde historie (geen force-push toegestaan).
- *Automatisch mergen naar de standaardbranch bij groene tests* — verworpen: B03-013/EX48 eisen menselijke beoordeling.
- *Dependabot/Renovate voor upstream* — werkt niet voor een volledige bron-fork.
