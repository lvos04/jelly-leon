# ADR-0008 — Alles-in-één image `ghcr.io/lvos04/jelly-leon` als standaard Custom App (schets P0)

- **Status:** Voorgesteld (schets P0; definitief in P4)
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
   bovenste map nog niet van 568 is), eigen pluginmap bijwerken, groepen van aanwezige `/dev/dri/*` toevoegen
   (groep 0 nooit), daarna `setpriv` naar 568:568 zonder capabilities en met `no_new_privs`. Als niet-root: niets
   aanpassen. Geen geheimen, geen netwerk, geen andere shellfuncties.
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

## Gevolgen

- De image is de enige installatievorm (standaard Custom App); compose alleen voor ontwikkeling/CI (hier niet nodig).
- Contractafwijkingen (`/config`+`/cache`, geen PostgreSQL, `/health`) staan in het eindrapport onder contract_issues.
