# ADR-0011 — Server naar de nieuwste stabiele Jellyfin 12.x (.NET 10) vóór P4, als aparte fase

- **Status:** Aanvaard — besluit van de gebruiker (2026-11-09, besluit 2 in
  `ai-server-manager/docs/platform-v2/OVERDRACHT/STATUS.md`). **Uitgevoerd in P4-0 op 2026-11-10** (B03-014): basis
  `v12.4` (`83d0d0e7f76e`), forkversie `12.4.0-jl.0`, .NET 10; keuzes bij de uitvoering in ADR-0027, bewijs in
  `docs/platform-v2/BOUWVERIFICATIE_P4-0.md` (Sim-getest; echte NAS NIET GEVALIDEERD). In de P0-afronding was de
  upgrade nog niet uitgevoerd (basis toen `v10.11.11`).
- **Context:** De fork staat op upstream `v10.11.11` (.NET 9). Upstream heeft al een nieuwe releasereeks: gemeten op
  2026-11-09 (`git ls-remote --tags`, alleen lezen) zijn `v12.0`…`v12.4` de stabiele tags na `v10.11.11`
  (`v12.4` = commit `83d0d0e7f76e`), en `jellyfin-web` heeft dezelfde tags. B03 (P4) zou anders eerst op 10.11 gebouwd
  en daarna nog eens gemigreerd moeten worden. De gebruiker besliste: **Swiftfin 1.6.1 blijft**, en de **server gaat
  vóór P4 naar de nieuwste stabiele 12.x**, zodat B03 direct op 12.x gebouwd wordt (jelly-leon + jelly-leon-web;
  Android-clients op 12.x-compatibiliteit controleren).

## Besluit

1. **Doelversie = de nieuwste stabiele 12.x-tag op het moment van uitvoeren**, bepaald met
   `tools/jelly-leon/upstream_sync.py kies --spoor nieuwste` (nooit rc/beta; numerieke volgorde, `v12.10` > `v12.4`).
   Niet vooraf vastgezet: gemeten op 2026-11-09 is dat `v12.4`. Server en web-client gaan naar **dezelfde** tag.
2. **Aparte fase "upgrade 12.x"** na de P0-afronding en vóór de eerste B03-bouwstap van P4. P1–P3-werk in andere repos
   wacht er niet op; nieuw B03-werk in deze repo (plugins, patches) begint pas op de 12.x-basis.
3. **Werkwijze (ADR-0006, geen nieuwe weg):**
   - `upstream_sync.py merge --tag <v12.x>` → methode *herbasis* (andere reeks): upstream-tag + fork-eigen paden +
     geregistreerde core-patches op branch `sync/<tag>`. Gemeten proef naar v12.4: 1 conflict in
     `.github/workflows/commands.yml` (JL-0001) — de guard opnieuw op de nieuwe `if:`-regel zetten en het register
     bijwerken.
   - Wat de sync automatisch meeneemt: `baseline.json` (incl. `dotnet_sdk_major` → `10.0`), plugin-`JellyfinVersion` en
     `TargetFramework` (`net10.0`); CI kiest via `dotnet_sdk_kanaal.py` vanzelf het SDK-kanaal `10.0.x` (ADR-0010).
   - Wat handwerk is (release-artefacten, door `check_fork_consistency.py` afgedwongen buiten de sync-modus):
     `deploy/allinone/Dockerfile` → `SDK_IMAGE` op `mcr.microsoft.com/dotnet/sdk:10.0.<patch>@sha256:…`,
     `RUNTIME_IMAGE` op `docker.io/jellyfin/jellyfin:<12.x>@sha256:…`, `NODE_IMAGE` op een Node **24**-image
     (`jellyfin-web` v12.4 vraagt `node >=24`, `npm >=11`; de huidige `node:22` voldoet dan niet), manifest en
     `CUSTOM_APP.md`. Alle digests opnieuw meten (`docker buildx imagetools inspect`), nooit `latest`.
   - `jelly-leon-web` volgt met zijn eigen upstream-sync naar dezelfde tag (eigen repo, eigen bouwer).
   - `docs/openapi/jelly-leon.openapi.json` wordt **bewust** vervangen door de 12.x-export (API-wijzigingen van
     upstream beoordelen op clientimpact); de plugin-OpenAPI blijft gelijk tenzij de plugin verandert.
4. **Gegevens en terugzetten (B03-013):** de databasemigratie 10.11 → 12.x is eenrichtingsverkeer. Eerst migreren op een
   **kopie** van een 10.11.11-`/config` (Sim: levenscyclustest met een vooraf gevulde 10.11.11-datamap; echt: kopie
   van de NAS-dataset), vóór de echte update een back-up via de upstream-Backup-API + ZFS-snapshot. Terugzetten =
   vorige image-tag **én** de database-back-up/snapshot samen; nooit alleen de image terugzetten.
   De terugzetproef `tools/jelly-leon/e2e/rollback_sim.py` (CI-job *image*) doorloopt dit pad al met de huidige
   versie; bij de upgrade krijgt hij `--upstream-image` = de oude 10.11-runtime en `--image` = de 12.x-build, en
   hoort een extra negatieve stap (alleen de oude binary zonder back-up op de gemigreerde database) te falen.
5. **Acceptatie van de fase (gate vóór P4):** build 0 fouten; volledige upstream-testsuite; plugins tegen de 12.x-ABI;
   OpenAPI-wijzigingen beoordeeld; stock-client-smoketest; image-levenscyclus inclusief migratie van een
   10.11.11-datamap; web-smoketest met Chromium; clientmatrix opnieuw: Jellyfin Android en Android TV (12.x-
   compatibiliteit, in `jelly-leon-clients`), Swiftfin **1.6.1** tegen de 12.x-server (NIET GEVALIDEERD (Mac/Xcode)
   tot een echt apparaat), overige clients NIET GEVALIDEERD (hardware) tot een echte sessie. GitHub-CI groen.
   Overnemen in de standaardbranch en een release blijven handmatige R2-stappen (ADR-0006).

## Gevolgen

- Versies volgen ADR-0005: nieuwe basis begint op `<12.x>-jl.0` (bv. `12.4.0-jl.0`; `v12.4` wordt intern 12.4.0), de
  server meldt dan zelf de upstream-versie 12.x. Of er vóór de upgrade nog een release op 10.11.11 komt, is een apart
  R2-besluit; voor P4 is die niet nodig.
- Zolang de fase niet is uitgevoerd, blijft alles in deze repo op 10.11.11 / .NET 9 (CI, image, manifest, evidence).
- Upstream-security van 10.11.x blijft tot de upgrade gevolgd via het spoor `patch` van de wekelijkse upstream-sync.

## Risico's

- Plugin-ABI-breuk (`Jellyfin.Controller` 12.x): plugin opnieuw bouwen en testen; de OpenAPI-contracttest van de
  plugin bewaakt `/media/v1/version`.
- Clients: Android-apps en Swiftfin 1.6.1 tegen een 12.x-server zijn nog niet gemeten — tot een echte test `unknown`.
- Grote sprong: een gewone merge gaf 79 conflicten (upstream-backports); daarom uitsluitend herbasis.
