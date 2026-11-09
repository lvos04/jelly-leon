# Forkstrategie Jelly Leon (B03-001)

Versie P0 (afronding) · 2026-11-09 · repo `lvos04/jelly-leon` · basis `jellyfin/jellyfin` **v10.11.11** · licentie
**GPL-2.0** · **besluit gebruiker: vóór P4 naar de nieuwste stabiele 12.x (.NET 10), zie §6a en ADR-0011.**

Jelly Leon is een fork van Jellyfin met één doel: de universele mediaserver uit B03 bouwen **zonder Jellyfin 1:1 te
herschrijven** en zonder stock Jellyfin-clients te breken. Dit document is de samenvatting; de besluiten staan in
`docs/adr/` (ADR-0001…0011), de bewaking in `tools/jelly-leon/` en CI.

## 1. Pakketregel: plugin/extensie vóór core-patch (ADR-0001)

Elke nieuwe functie volgt deze volgorde; een stap verder mag pas als de vorige aantoonbaar niet volstaat:

1. **Configuratie** van upstream (QSV/VAAPI, ouderlijk toezicht, DVR, back-up-API, …).
2. **Bestaande upstream-plugin** (bv. de officiële Webhook-plugin) — niet zelf herbouwen.
3. **Eigen plugin** in `plugins/<Naam>/` tegen de publieke plugin-ABI (ADR-0002).
4. **Externe dienst/adapter** via de Jellyfin-API (Hub, `jelly-leon-platform`, `zoeken-en-persoonlijke-ai`).
5. **Core-patch** — uitsluitend via het patchregister [`PATCHES.md`](PATCHES.md) (doel, bestanden, waarom geen
   plugin, upstream-PR-kans, test). CI (`patch_register_check.py`) faalt op elke niet-geregistreerde afwijking.

Stand P0: **geen** core-patch in servercode; één CI-patch (JL-0001, repository-guards op upstream-bot-workflows).

## 2. Scheiding patches ↔ plugins (ADR-0002)

| | Core-patch | Plugin |
|---|---|---|
| Waar | upstream-bestanden (buiten `fork_paths.txt`) | `plugins/<Naam>/src/Jellyfin.Plugin.<Naam>/` + `tests/` |
| Solution | `Jellyfin.sln` (upstream, ongewijzigd) | `plugins/JellyLeon.Plugins.sln` (eigen; niets in `Jellyfin.sln`) |
| Build-instellingen | upstream `Directory.*.props` | eigen `plugins/Directory.Build.props`/`.targets`/`Directory.Packages.props` (geen overerving van de root) |
| Bouwt tegen | broncode | NuGet `Jellyfin.Controller`/`Jellyfin.Model` **exact** de basisversie (`ExcludeAssets=runtime`) |
| Registratie | `PATCHES.md` (verplicht) | geen; wel tests + OpenAPI (`docs/openapi/jelly-leon-plugin.openapi.json`) |
| Werkt op stock Jellyfin | nee | ja (gemeten: de plugin draait in de officiële image 10.11.11) |

Eerste plugin: `Jellyfin.Plugin.JellyLeon` (zichtbare naam "Jelly Leon") met `GET /media/v1/version` — forkversie,
upstream-basis en of plugin en server bij elkaar passen (`compatibel` / `afwijkend` / `unknown`, nooit gesimuleerd groen).
Dit is de databron voor de Hub-pagina *Versie en clientcompatibiliteit* (B03-001-scherm, in `ai-server-manager`).

## 3. Branding (ADR-0003)

- **Technische identiteit blijft "Jellyfin"**: `ProductName` "Jellyfin Server", serverversie = upstream-versie, routes,
  `MediaBrowser`/`X-Emby-*`-headers, discovery, `targetAbi`, assembly-/pakketnamen, `jellyfin.db`, `JELLYFIN_*`.
- **Alleen de zichtbare naam wordt "Jelly Leon"** (web-client-titel, Custom App-naam, image, pluginnaam, Hub-teksten),
  eerst via configuratie (`BrandingOptions`), later via geregistreerde patches in `jelly-leon-web`.
- **In P0 is niets aan branding gewijzigd.** De smoketest en de plugin bewaken dat de identiteit intact blijft.

## 4. GPL-2.0-verplichtingen (ADR-0004)

- `LICENSE` (GPL-2.0) en `CONTRIBUTORS.md` blijven byte-gelijk aan upstream (CI-controle); geen extra licentiebestand
  zonder vraag aan de gebruiker.
- **Bron beschikbaar** voor elke verspreide image: git-tag `v<forkversie>` in `lvos04/jelly-leon` + web-ref in
  `lvos04/jelly-leon-web`; OCI-labels `source`/`revision`/`version`/`licenses`; in de image `LICENSE`,
  `CONTRIBUTORS.md`, `NOTICE.jelly-leon` en `VERSION` onder `/usr/share/doc/jelly-leon/`.
- **Wijzigingen herkenbaar** (GPL-2.0 §2a): elke core-patch met datum en doel in `PATCHES.md`.
- Credits: "gebaseerd op Jellyfin" blijft zichtbaar; geen upstream-logo als eigen merk; geen schijn van een officiële
  Jellyfin-release.
- **Open gebruikersbesluit:** zichtbaarheid (publiek/privé) van `jelly-leon`, `jelly-leon-web` en het GHCR-pakket vóór
  de eerste image-release (een privé-repo met een publieke image voldoet niet aan "bron beschikbaar").

## 5. Versieschema (ADR-0005)

- Forkversie `<upstream>-jl.<N>`: nu `10.11.11-jl.0` (ontwikkelstand, **nooit** gepubliceerd); eerste release `-jl.1`.
- Git-tags: eigen `v10.11.11-jl.1`; upstream lokaal als `upstream-v10.11.11`. Image-tag = forkversie, nooit `latest`.
- De server blijft de upstream-versie melden (`/System/Info` → `10.11.11`); de forkversie staat in het OCI-label,
  `/usr/share/doc/jelly-leon/VERSION` en `GET /media/v1/version`.
- Bron van waarheid: `tools/jelly-leon/baseline.json`; `check_fork_consistency.py` bewaakt baseline ↔ `SharedVersion.cs`
  ↔ plugins ↔ manifest ↔ gepinde base-images.

## 6. Upstream-sync en upgradepad (ADR-0006, B03-013)

- `upstream-sync.yml` (wekelijks + handmatig): nieuwste stabiele tag per spoor (`patch` = 10.11.x, `nieuwste` = nu
  **v12.4**) → branch `sync/<tag>` (merge binnen dezelfde reeks; bij een reekssprong **herbasis**: upstream-tag +
  fork-eigen paden + geregistreerde patches) → volledige build/test, plugins tegen de nieuwe ABI, stock-client-smoketest.
  **Incompatibel (conflict/build/test) = workflow faalt (EX48); nooit automatisch naar productie.**
- Gemeten syncproef naar v12.4: gewone merge 79 conflicten (door upstream-backports), herbasis 1 conflict
  (`commands.yml`, patch JL-0001) → workflow zou terecht falen; zie ADR-0006.
- Overnemen + release zijn handmatige R2-stappen; terugzetten = oude image-tag **én** database-back-up/snapshot samen.
- Upstream-security: nieuwe patchreleases verschijnen in de wekelijkse samenvatting; advisories volgen is een followup.

## 6a. Besluit: naar Jellyfin 12.x vóór P4 (ADR-0011)

**Besluit van de gebruiker (2026-11-09):** Swiftfin 1.6.1 blijft; de **server gaat vóór P4 naar de nieuwste stabiele
Jellyfin 12.x (.NET 10)**, zodat B03 direct op 12.x gebouwd wordt (jelly-leon + jelly-leon-web; Android-clients op
12.x-compatibiliteit controleren).

- **Aparte fase, niet in de P0-afronding uitgevoerd.** Tot die fase blijft alles op `v10.11.11` / .NET 9.
- Doel = nieuwste stabiele 12.x op het moment van uitvoeren (`upstream_sync.py kies --spoor nieuwste`; gemeten
  2026-11-09: `v12.4`), via **herbasis** op `sync/<tag>` (ADR-0006); conflict in JL-0001 handmatig oplossen.
- Automatisch mee: baseline (`dotnet_sdk_major` 10.0), plugin-`JellyfinVersion`/`TargetFramework` (`net10.0`), het
  CI-SDK-kanaal (`10.0.x`, ADR-0010). Handwerk: Dockerfile (`dotnet/sdk:10.0.x`, `jellyfin/jellyfin:<12.x>`, Node 24
  voor `jellyfin-web` 12.x), manifest, `CUSTOM_APP.md`, nieuwe `docs/openapi`-export — alles op gemeten digests.
- DB-migratie 10.11 → 12.x eerst op een kopie; terugzetten = oude image-tag + database-back-up/snapshot samen.
- Gate vóór P4: build/tests/plugins/OpenAPI-beoordeling/smoketest/levenscyclus met migratie, clientmatrix opnieuw
  (Android/Android TV 12.x; Swiftfin 1.6.1 NIET GEVALIDEERD (Mac/Xcode)), CI groen.

## 7. Compatibiliteitsmatrix server ↔ clients

Zie [`CLIENT_COMPAT_MATRIX.md`](CLIENT_COMPAT_MATRIX.md). In P0 is alleen het **protocol** in simulatie getest
(stock-client-smoketest 17/17, zowel fork-build als stock image). Elke echte client/tv staat op **NIET GEVALIDEERD**
tot hij op een echt apparaat is getest (D15).

## 8. Bouwen, testen en CI

| Wat | Waar | Stand P0 |
|---|---|---|
| Upstream-solution bouwen + volledige tests | `jelly-leon-ci.yml` job *server* | Ubuntu-machine (SDK 9.0.320): build 0 fouten/0 waarschuwingen; van 2 555 tests **2 548 geslaagd**, 7 overgeslagen (upstream), **0 mislukt** (de 4 omgevingsfouten uit de sandbox slagen hier; zie `BOUWVERIFICATIE_P0.md` §11). CI installeert het SDK-kanaal uit global.json (ADR-0010) |
| OpenAPI-drift | idem | structureel gelijk; alleen `description`-teksten hangen af van de bestandssysteemvolgorde van upstream (ADR-0010) |
| Plugins | job *plugins* | 16/16 tests |
| Forkregels | job *forkregels* | patchregister, consistentie (incl. SDK-reeks), tool-tests (incl. EX48-simulatie), ruff, shellcheck, actionlint |
| Stock-client-E2E | job *stock-client-e2e* | lokaal 17/17 (Sim-getest) |
| Image | `deploy/allinone/Dockerfile`, job *image* | volledige image mét echte web-build van `jelly-leon-web` lokaal gebouwd en levenscyclus getest (Sim-getest; na de QA-review 21/21 incl. weigering van `/config` op tmpfs); CI bouwt hem met de upstream-web-dist (jelly-leon-web is privé); publicatie in P4 |
| Terugzetproef (B03-013) | `tools/jelly-leon/e2e/rollback_sim.py`, job *image* | upstream-Jellyfin → Jelly Leon → terug met DB-back-up (koude kopie als model voor de ZFS-snapshot) + oude binary: lokaal 10/10 (Sim-getest). In P0 zonder databasemigratie (zelfde versie); onderscheidend pas bij 12.x (ADR-0011). Echte NAS: NIET GEVALIDEERD |

Upstream-workflows blijven bestaan; wat in de fork draait staat in ADR-0007.

## 9. Installatie

Uitsluitend als **standaard TrueNAS Custom App** (`deploy/truenas/CUSTOM_APP.md`, manifest
`deploy/manifest/jelly-leon.manifest.yaml`), normaal door het platform via de TrueNAS-API. De bestaande Jellyfin blijft
draaien tot de pilot (I24 stap 6) slaagt; Jelly Leon krijgt eigen poort en datasets en leest media alleen-lezen.
