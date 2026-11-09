# ADR-0013 — CI bouwt de image met de echte jelly-leon-web-build op een vaste commit

- **Status:** Aanvaard
- **Datum:** 2026-11-09
- **Context:** Tot nu toe verving de CI-job `image` de stage `web` van de productie-Dockerfile door de web-dist uit de
  vastgezette upstream-runtime (`jellyfin/jellyfin:10.11.11`), omdat `lvos04/jelly-leon-web` privé was en
  `GITHUB_TOKEN` alleen deze repo mag lezen (ADR-0008). De echte web-build was alleen lokaal gebouwd en getest. Sinds
  2026-11-09 zijn de repos publiek (gebruikersbesluit 3); een anonieme `git ls-remote` en de GitHub-API (HTTP 200
  zonder token) bevestigen dat voor `jelly-leon-web`.

## Besluit

1. `tools/jelly-leon/baseline.json` krijgt **`web_fork_commit`**: de volledige SHA van de `jelly-leon-web`-commit waaruit
   de image de web-client bouwt — nu `2795f3365ffe21d16bf5b76a0da8d556f29ad38d`, dezelfde commit die in de P0-afronding
   en QA-review lokaal is gebouwd en met de web-smoketest (Chromium 21/21) getest. Geen branchnaam: een branch schuift
   mee met werk in de andere repo en maakt builds niet reproduceerbaar. Bijwerken = bewuste commit hier (bv. bij de
   12.x-upgrade, ADR-0011, samen met de serverbasis).
2. De CI-job `image` haalt `jelly-leon-web` op die commit op (publiek, `persist-credentials: false`, volledige historie
   zonder blobs), controleert met **`tools/jelly-leon/web_bron.py --controleer`** dat HEAD = `web_fork_commit`,
   `package.json` heet `jellyfin-web` (technische identiteit) met versie = `upstream_version` van de server, en dat
   `web_upstream_commit` (tag `web_upstream_tag`) een voorouder is — server en web-client komen altijd uit dezelfde
   release. Daarna een schone `git archive`-export als build-context `jelly-leon-web` en de **ongewijzigde
   productie-Dockerfile** (`npm ci` + `npm run build:production`); `--build-arg WEB_REF` = die commit. De
   levenscyclustest controleert met `--verwacht-web-ref` het label `io.github.lvos04.jelly-leon.web.revision` en
   `/usr/share/doc/jelly-leon/SOURCE_REVISIONS` (GPL "bron beschikbaar", ADR-0004).
3. `check_fork_consistency.py` bewaakt de web-velden van `baseline.json` (volledige SHA's, `web_upstream_tag` hoort bij
   de serverbasis), behalve in de sync-modus (`--zonder-manifest`), zodat een upstream-sync niet op de web-velden
   strandt; de job `image` op een sync-branch faalt dan wél met een duidelijke melding tot de web-fork mee is — bewust
   (nooit een server van release X met een web-client van release Y in één image).
4. `_extern/` staat in `deploy/allinone/Dockerfile.dockerignore` en wordt na de export verwijderd: bronnen van andere
   repos komen nooit in de server-stage.

## Gevolgen

- De CI-image is nu dezelfde als de lokaal geteste image (zelfde Dockerfile, zelfde web-commit); alleen de omgeving
  verschilt. Duur: `npm ci` + webpack-productiebuild komen erbij (lokaal 17 s + 75 s op 22 CPU's).
- De CI is afhankelijk van de publieke zichtbaarheid van `jelly-leon-web` en van npm/GitHub-archieven tijdens `npm ci`.
  Wordt de repo weer privé, dan faalt de job `image` (geen stille terugval op de upstream-web-dist).
- ADR-0008 (CI-web-stage = upstream-web-dist) is op dit punt vervangen.
