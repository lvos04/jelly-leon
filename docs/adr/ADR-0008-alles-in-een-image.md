# ADR-0008 — Alles-in-één image `ghcr.io/lvos04/jelly-leon` als standaard Custom App

- **Status:** Voorgesteld (P0: volledige image lokaal gebouwd en Sim-getest; definitief bij de eerste release in P4,
  na de upgrade naar 12.x — ADR-0011)
- **Context:** Contract 1.1 §1/§2/§10: één alles-in-één image per repo, standaard TrueNAS Custom App (geen YAML/compose),
  één datamap `/appdata` met ingebouwde PostgreSQL, start als root alleen voor eigenaarschap en daarna 568:568,
  `/healthz` + `/readyz`. Jellyfin is echter een bestaande server met eigen conventies: SQLite, `/config` + `/cache`,
  `/health`, en een officiële runtime met jellyfin-ffmpeg en de Intel-mediastack.

## Besluit

1. **Runtime-basis = officiële upstream-image** `docker.io/jellyfin/jellyfin:10.11.11@sha256:aefb67e6…` (Debian 13,
   jellyfin-ffmpeg 7.1.4, Intel OpenCL/VA). Wij vervangen alleen `/jellyfin` (server uit deze fork, self-contained),
   `/jellyfin/jellyfin-web` (uit `lvos04/jelly-leon-web`, aparte build-context) en voegen de Jelly Leon-plugin toe.
   Geen eigen ffmpeg- of driverbouw (geen dubbel werk; INVENTARIS §5/§6). Build-images op exacte versie + digest
   (`dotnet/sdk:9.0.320`, `node:22.23.4-bookworm-slim`).
2. **Opslag `/config` + `/cache` (+ media alleen-lezen) in plaats van één `/appdata`** — veiligste interpretatie: dit zijn
   de upstream-paden (`JELLYFIN_*` in de runtime-image), migratie vanaf de bestaande Jellyfin en upstream-documentatie
   blijven kloppen, en cache (transcodes) kan op een aparte dataset zonder back-up. Afwijking gemeld als contract-issue.
3. **Geen PostgreSQL**: Jellyfin gebruikt SQLite (EF Core); een PostgreSQL-provider bestaat upstream niet. De
   database-back-up loopt via de upstream-Backup-API + ZFS-snapshot van `/config`.
4. **Start:** `deploy/allinone/entrypoint.sh` — als root alleen `/config` en `/cache` aan 568:568 (recursief alleen als de
   bovenste map nog niet van 568 is), groepen van aanwezige `/dev/dri/*` toevoegen (groep 0 nooit), daarna `setpriv`
   naar 568:568 zonder capabilities en met `no_new_privs`; pas in die tweede fase (als 568) wordt de eigen pluginmap
   bijgewerkt. Als niet-root: niets aanpassen behalve de pluginmap. Geen geheimen, geen netwerk, geen andere
   shellfuncties. **Fail-closed (review P0):**
   - de upstream-basisimage declareert `VOLUME /config /cache`; zonder opslagregel in het formulier maakt Docker
     stilletjes een anoniem volume en staat de database níet op de gekozen dataset (weg bij verwijderen). De
     entrypoint herkent een anoniem volume (`…/volumes/<64 hex>/_data` in `/proc/self/mountinfo`) en weigert te
     starten met een NL-melding ("onduidelijke datamap" is een P0-no-go). ixVolumes en hostpaden zijn geen anonieme
     volumes;
   - `JELLYFIN_DATA_DIR`/`JELLYFIN_CACHE_DIR` (na het oplossen van symlinks) buiten `/config` of `/cache` → weigeren:
     als root nooit `chown -R` op systeem- of mediamappen.
   - **(QA-review P0-afronding)** datamap én instellingenmap (`JELLYFIN_CONFIG_DIR`, standaard `<datamap>/config`)
     moeten op blijvende, lokale opslag staan, ook als de container als niet-root start. De entrypoint zoekt de mount
     waarop het pad ligt (langste mountpoint in `/proc/self/mountinfo`) en weigert: een anoniem Docker-volume, `tmpfs`/
     `ramfs` (het formulier biedt opslagtype *tmpfs*), de container zelf (geen eigen mount) en NFS/SMB (`nfs`, `nfs4`,
     `cifs`, `smb3`, `smbfs`: SQLite-vergrendeling niet betrouwbaar). Gemeten vóór de reparatie: met `/config` als
     tmpfs werd de container *healthy* met een lege database en stond de startwizard anoniem open (HTTP 200 op
     `/Startup/Configuration`, `StartupWizardCompleted=false`) — na elke herstart opnieuw, zodat de eerste bezoeker
     beheerder wordt. `/cache` mag tmpfs zijn (opnieuw op te bouwen); daar geldt alleen de controle op een anoniem volume;
   - padopties in het veld *Command* (`-d/--datadir`, `-c/--configdir`, `-C/--cachedir`, `-l/--logdir`, `-w/--webdir`)
     omzeilen deze controles → weigeren.
5. **Gezondheid:** upstream `/health` (HEALTHCHECK). Contract-`/healthz` en `/readyz` volgen in P1 via de plugin
   (anoniem, zonder geheimen) — geen core-patch.
6. **GPU** standaard uit (`gpu: none` in het manifest) tot de wizard de rendernodes meet (D08); de manifeststandaard kent
   nog geen optionele GPU-parameter (followup appstore-en-fork).
7. **Licentie/bron:** labels `org.opencontainers.image.{source,revision,version,licenses}`, `LICENSE`, `CONTRIBUTORS.md`,
   `NOTICE.jelly-leon` en `VERSION` in `/usr/share/doc/jelly-leon/` (ADR-0004).

## Gemeten in P0 (Sim-getest, geen echte NAS)

- Server-stage van de Dockerfile gebouwd (BuildKit, optioneel CA-geheim). Volledige image **niet** gebouwd: `npm ci` van
  de web-client haalt een afhankelijkheid als GitHub-archief op en die host is in deze bouwomgeving geblokkeerd (HTTP 403).
- `entrypoint.sh` op de officiële runtime met de server-stage-uitvoer: root → chown → 568:568, `CapEff=0`, `CapBnd=0`,
  `NoNewPrivs=1`; herstart zonder chown; gesimuleerde rendernode (gid 107 → toegevoegd, gid 0 → geweigerd);
  start als 568; ontbrekende mount → duidelijke NL-fout; stock-client-smoketest 17/17.

## Gemeten in de review P0 (Sim-getest, geen echte NAS)

- **Volledige image** gebouwd met de ongewijzigde productie-Dockerfile; alleen de stage `web` is via een BuildKit-
  named-context vervangen door de web-dist uit de vastgezette upstream-runtime (de broncode van `jelly-leon-web` is in
  P0 gelijk aan upstream 10.11.11; de npm-build is hier door de proxy geblokkeerd). De proxy-CA zit niet in de image.
- `tools/jelly-leon/e2e/image_lifecycle.py` (ook CI-job `image`): lege hostmappen → *healthy* (Docker-healthcheck van
  de image) → stock-client-smoketest → proces 1 = 568:568, `CapEff=0`, `CapBnd=0`, `NoNewPrivs=1`, alles in
  `/config`/`/cache` van 568, web-client op `/web/` → `docker restart` en een **nieuwe container met dezelfde opslag**:
  wizard blijft afgerond, zelfde gebruiker en item-ID, streamen byte-gelijk (geen dataverlies) → negatieve tests
  (anoniem volume, cachemap naar de media) weigeren te starten en laten de media ongemoeid: **16/16**
  (`docs/platform-v2/test-evidence/p0-image-lifecycle.json`). Echte NAS/TrueNAS-formulier: NIET GEVALIDEERD.

## Gemeten in de P0-afronding (Ubuntu-machine, 2026-11-09; Sim-getest, geen echte NAS)

- **Volledige image mét de echte web-build** gebouwd met de productie-Dockerfile: `npm ci` (ook het
  `classList.js`-archief van GitHub, dat in de sandbox geblokkeerd was) en `npm run build:production` uit een
  `git archive` van `lvos04/jelly-leon-web` (commit `2795f3365`), server en plugin uit een `git archive` van deze repo.
  De web-client in de image verschilt in precies 4 bestanden van de upstream-web-dist (webpack-hash/commit-info): het
  is de eigen build.
- Herkomst in de image: label `io.github.lvos04.jelly-leon.web.revision` + `/usr/share/doc/jelly-leon/SOURCE_REVISIONS`
  (server- en web-commit); `org.opencontainers.image.url`/`documentation` wijzen naar de fork, niet naar jellyfin.org.
- `image_lifecycle.py` **18/18** (nu ook: elke bundel uit `index.html` laadt, herkomst klopt) en de web-smoketest van
  `jelly-leon-web` in headless Chromium **21/21** tegen dezelfde image (`docs/platform-v2/test-evidence/
  p0-afronding-*.json`). In GitHub-CI blijft de stage `web` vervangen door de upstream-web-dist zolang `jelly-leon-web`
  privé is (geen leestoken; gebruikersbesluit 3: repos worden publiek na een scan).

## Gemeten in de QA-review van de P0-afronding (2026-11-09; Sim-getest, geen echte NAS)

- Volledige image opnieuw gebouwd (server en plugin uit de werkboom op `d4bc20d6a`, echte web-build van
  `jelly-leon-web` `2795f3365`; de web-stage kwam uit de BuildKit-cache met identieke invoer). Levenscyclus **21/21**
  (`docs/platform-v2/test-evidence/p0-qa-image-lifecycle.json`): alle eerdere 18 stappen plus drie nieuwe weigeringen
  (`/config` als tmpfs, `JELLYFIN_CONFIG_DIR` in de container, `--datadir` in *Command*). Los nagemeten: start als
  niet-root (`--user 568:568`) blijft *healthy*; `/cache` als tmpfs blijft toegestaan; `/config` als tmpfs wordt ook
  als niet-root geweigerd. De weigering van NFS/SMB is **niet** getest (geen NFS/SMB-server in de testomgeving).

## Gevolgen

- De image is de enige installatievorm (standaard Custom App); compose alleen voor ontwikkeling/CI (hier niet nodig).
- Contractafwijkingen (`/config`+`/cache`, geen PostgreSQL, `/health`) staan in het eindrapport onder contract_issues.
