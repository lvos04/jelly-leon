# Inventaris jelly-leon (P0, B03-001) — wat upstream al kan

> **Bijgewerkt 2026-11-10 (P4-0, B03-014):** de forkbasis is nu **v12.4** (`83d0d0e7f76e`, forkversie 12.4.0-jl.0, .NET 10). Dit inventaris is de P0-peiling op 10.11.11; wat 12.x verandert staat in bouwplan §8.1, de API-wijzigingen in `test-evidence/p40/openapi-10.11.11-naar-12.4.json` en het upstream-gedrag waarop we steunen in `UPSTREAM_GEDRAG.md`.

Peildatum 2026-11-09 · basis `jellyfin/jellyfin` **v10.11.11** (commit `1fbd8739292c`, lokale tag `upstream-v10.11.11`) ·
bron van waarheid `tools/jelly-leon/baseline.json`.

Doel: vastleggen wat Jellyfin upstream al levert, zodat Jelly Leon **niets dubbel bouwt** (pakketregel ADR-0001) en
alleen echte hiaten (delta-matrix §9) oppakt. Alles hieronder is gemeten in deze repository of in de officiële
runtime-image; niets is op de echte NAS gecontroleerd (D01–D18 onbekend).

## 1. Stand van de fork

| Onderwerp | Gemeten waarde |
|---|---|
| Servercode t.o.v. upstream | **identiek** aan `v10.11.11`: `git diff upstream-v10.11.11 HEAD` raakt alleen fork-eigen paden en de geregistreerde CI-patch JL-0001 (zie `PATCHES.md`; `tools/jelly-leon/patch_register_check.py` bewaakt dit). |
| Branding | ongewijzigd (`ProductName` = "Jellyfin Server", versie 10.11.11) — ADR-0003. |
| Nieuwste stabiele upstream | **v12.4** (tags `v12.0`…`v12.4`, vanaf 12.0 zonder patchnummer; NuGet `Jellyfin.Controller` 12.4.0). `v10.11.11` is de nieuwste in de 10.11-reeks. Een sync naar 12.x is een grote sprong (eigen sync-branch, ADR-0006). |
| Licentie | GPL-2.0 (`LICENSE` ongewijzigd), credits in `CONTRIBUTORS.md` (ongewijzigd). |

## 2. Projectstructuur en bouwbasis

| Onderdeel | Inhoud |
|---|---|
| Solution | `Jellyfin.sln`: 24 productprojecten + 16 testprojecten (plus 2 fuzz-projecten buiten de solution), ± 1 785 C#-bestanden + 175 testbestanden. |
| .NET | `net9.0`; `global.json` SDK `9.0.0` met `rollForward: latestMinor` (gebouwd met SDK **9.0.320**). |
| Centrale build | `Directory.Build.props` (Nullable, TreatWarningsAsErrors, analyzers in Debug), `Directory.Packages.props` (centrale pakketversies), `nuget.config` (alleen nuget.org). |
| Kernassemblies (plugin-ABI, op NuGet) | `MediaBrowser.Controller` → **Jellyfin.Controller**, `MediaBrowser.Model` → **Jellyfin.Model**, `MediaBrowser.Common` → **Jellyfin.Common**, `Jellyfin.Data`, `Jellyfin.Extensions`, `Emby.Naming`, … (versie = serverversie). |
| Server | `Jellyfin.Server` (host, Kestrel, startup), `Emby.Server.Implementations`, `Jellyfin.Server.Implementations`, `Jellyfin.Api` (60 controllers). |
| Database | EF Core + **SQLite** (`src/Jellyfin.Database/*`, 78 migratiebestanden); provider-abstractie aanwezig. Geen PostgreSQL. |
| Media | `MediaBrowser.MediaEncoding` (ffmpeg/ffprobe), `Jellyfin.MediaEncoding.Hls`, `…Keyframes`, `MediaBrowser.Controller/MediaEncoding/EncodingHelper.cs`. |
| Live-tv | `src/Jellyfin.LiveTv` (tuners, gids, opnames). |
| Upstream-packaging | Niet in deze repo: `jellyfin/jellyfin-packaging` (officiële image `jellyfin/jellyfin`), `jellyfin/jellyfin-ffmpeg`. |

### Testprojecten (gemeten run, zie `BOUWVERIFICATIE_P0.md`)

`Jellyfin.Api.Tests` (79), `Common` (30), `Controller` (28), `Extensions` (141), `LiveTv` (48), `MediaEncoding` (47),
`MediaEncoding.Hls` (17), `MediaEncoding.Keyframes` (2), `Model` (627), `Naming` (614), `Networking` (119),
`Providers` (235), `Server` (7), `Server.Implementations` (424, 4 overgeslagen), `Server.Integration` (103, 3 overgeslagen;
start een echte testserver, o.a. opstartwizard, gebruikers, auth, OpenAPI-export), `XbmcMetadata` (34).
Totaal **2 555** tests.

## 3. API-oppervlak relevant voor B03

De volledige upstream-API (315 paden) staat in `docs/openapi/jelly-leon.openapi.json` (gegenereerd door
`OpenApiSpecTests`, byte-gelijk reproduceerbaar; CI faalt bij drift). Relevante groepen:

| Gebied | Upstream-routes (selectie) | Opmerking voor B03 |
|---|---|---|
| Authenticatie | `POST /Users/AuthenticateByName`, `/QuickConnect/*`, `/Auth/Keys` (API-sleutels), header `Authorization: MediaBrowser …` en oud `X-Emby-Authorization`/`X-Emby-Token` | Stock-client-protocol; ongewijzigd laten (ADR-0003). |
| Gebruikers en ouderlijk toezicht | `/Users/*`, `UserPolicy`: `MaxParentalRating`, `MaxParentalSubRating`, `BlockUnratedItems`, `BlockedTags`/`AllowedTags`, `AccessSchedules`, `EnabledFolders`, `EnableContentDownloading`, `EnableLiveTvAccess`, `MaxActiveSessions`, `RemoteClientBitrateLimit` | Basis voor B03-010; zie risico §7. |
| Afspelen en sessies | `POST /Items/{id}/PlaybackInfo` (DeviceProfile-onderhandeling, `StreamBuilder`), `/Videos/{id}/stream`, `/Audio/{id}/stream`, `/Audio/{id}/universal`, HLS (`/Videos/{id}/master.m3u8`, `DynamicHls`), `/Sessions/*`, `/Sessions/Playing{,/Progress,/Stopped}`, `/SyncPlay/*`, WebSocket `/socket` | `TranscodeReason`-vlaggen bestaan al (basis "why-transcode" B03-005). |
| Segmenten, trickplay, songteksten | `/MediaSegments/{itemId}` + `IMediaSegmentProvider`, `/Videos/{id}/Trickplay/*`, `/Audio/{id}/Lyrics` | Intro/recap/credits (B03-007) als **segmentprovider-plugin**, niet zelf afspelen-logica bouwen. |
| Live-tv/DVR | 31 `/LiveTv/*`-routes: tuners (HDHomeRun, M3U), gidsen (XMLTV, Schedules Direct), timers/serietimers, opnames | Basis voor B03-012; tunerconflict alleen als fout bij afspelen/opnemen (`LiveTvConflictException`), geen overlap-planner. |
| Plugins | `/Plugins/*`, `/Packages/*`, `/Repositories`; `IPluginServiceRegistrator`, `BasePlugin<T>`, `IScheduledTask`, `IEventConsumer<T>`, eigen ASP.NET-controllers in plugins | Uitbreidingspunt nr. 1 (ADR-0001/0002). |
| Gebeurtenissen | In-process `IEventManager` + `IEventConsumer<T>` (sessie, authenticatie, plugins, gebruikers, taken), activiteitenlog `/System/ActivityLog/Entries`, WebSocket-berichten | **Geen** uitgaande webhooks in core; officiële plugin *Webhook* bestaat in de upstream-pluginrepository (niet zelf herbouwen). |
| Back-up | `POST /Backup/Create`, `POST /Backup/Restore`, `GET /Backup`, `GET /Backup/Manifest` (alleen beheerder, nieuw in 10.11) | Gebruiken voor B03-013 (DB-back-up vóór update), geen eigen DB-back-up bouwen. |
| Systeem | `/System/Info/Public` (ProductName, Version, Id), `/System/Ping`, `/health` (ASP.NET health check, buiten OpenAPI) | `/health` is de healthcheck van de image; contract-`/healthz`/`/readyz` volgen later via de plugin (ADR-0008). |

Fork-eigen routes staan apart in `docs/openapi/jelly-leon-plugin.openapi.json` (nu alleen `GET /media/v1/version`).
De overige B03-routes (`/media/v1/search`, `/media/v1/scenes`, `/media/v1/mediaguard/request`,
`/media/v1/transcode/capabilities`, `/media/v1/events/playback`) bestaan **nog niet** — ontwerpeisen voor latere fasen.

## 4. Datamodel (upstream) versus B03-entiteiten

| B03-entiteit | Upstream | Status |
|---|---|---|
| media_item, external_id, subtitle_track, audio_track | `BaseItem` + `ProviderIds`, `MediaStream` | bestaand |
| episode_map (absolute nummering) | `IndexNumber`/`ParentIndexNumber`, `AbsoluteEpisodeNumber` in metadata-providers; geen versiebeheer van mappings | onvolledig (B03-002/006) |
| segment | `MediaSegment` (intro/outro/recap/preview/commercial) | bestaand (provider-API) |
| playback_session, watch_progress, device_profile, client_version | `SessionInfo`, `UserData`, `DeviceProfile`, `Devices` | bestaand |
| transcode_job, playback_capability | `TranscodingJob` (in-memory), ffmpeg-capabilities via `EncoderValidator` | onvolledig (geen per-GPU-lane, geen budget) |
| channel, epg_event, dvr_rule | LiveTv-entiteiten, timers/serietimers | bestaand; conflicten/retentie onvolledig |
| download_job | alleen `EnableContentDownloading` + `/Items/{id}/Download` | ontbrekend (offline-manager zit in clients) |
| scene_embedding | — | ontbrekend (B03-008; bij voorkeur in `zoeken-en-persoonlijke-ai`) |

## 5. Hardwareversnelling (Intel Arc A310 / UHD 770) — wat upstream al kan

| Functie | Upstream 10.11.11 |
|---|---|
| Methoden | `HardwareAccelerationType`: none, amf, **qsv**, nvenc, v4l2m2m, **vaapi**, videotoolbox, rkmpp. |
| Apparaatkeuze | **Eén** apparaat per server: `EncodingOptions.VaapiDevice` (standaard `/dev/dri/renderD128`) of `QsvDevice`. |
| Encoders | `h264_qsv`, `hevc_qsv`, **`av1_qsv`**, `h264_vaapi`, `hevc_vaapi`, **`av1_vaapi`**; opties `AllowHevcEncoding`, `AllowAv1Encoding`, low-power-encoders (`EnableIntelLowPower*`). |
| Decoders | per codec instelbaar (`HardwareDecodingCodecs`), 10-bit HEVC/VP9, HEVC RExt. |
| Tonemapping | VPP (`EnableVppTonemapping`) en OpenCL/Vulkan (`EnableTonemapping`), HDR10/HLG; DV-profielen afhankelijk van ffmpeg. |
| Detectie | `EncoderValidator`: versiecheck, `CheckVaapiDeviceByDriverName` (iHD/i965), Vulkan-DRM-interop, filter- en hwaccel-vlaggen. |
| Runtime (officiële image `jellyfin/jellyfin:10.11.11`) | Debian 13, **jellyfin-ffmpeg 7.1.4** met eigen VA-drivers, `intel-opencl-icd` 26.18, IGC 2.x, `vainfo` aanwezig — gemeten in de image, **niet** op de A310/UHD 770. |

**Dus niet zelf bouwen:** ffmpeg, Intel-drivers, QSV/VAAPI-pijplijnen, tonemapping, encoder-detectie.
**Echte hiaten (B03-004):** kiezen van rendernode **per sessie/codec** (A310 voor AV1-encodes, UHD 770 voor overige
QSV-lanes), fallback als één GPU wegvalt, en een gedeeld GPU-budget met MediaGuard. Upstream kent alleen één globaal
apparaat → dit vraagt later een geregistreerde core-patch of een externe planner; eerst meten (D08, I24 stap 2).

## 6. Distributie en runtime

De officiële image (`jellyfin/jellyfin`, bron `jellyfin-packaging`) levert: self-contained server in `/jellyfin`,
web-client in `/jellyfin/jellyfin-web`, `JELLYFIN_*`-omgevingsvariabelen (`/config`, `/cache`), healthcheck op `/health`,
`setpriv` aanwezig. Jelly Leon hergebruikt die runtime en vervangt alleen server + web + plugin (ADR-0008).

## 7. Gevonden risico's (upstream-gedrag, niet gepatcht in P0)

1. **Anoniem streamen.** `AudioController` en `VideosController` hebben op `…/{itemId}/stream` geen `[Authorize]`:
   wie een item-ID kent, kan zonder token streamen. Gemeten voor audio in de stock-client-smoketest (stock 10.11.11 én
   fork: HTTP 200 zonder token); voor video volgt het uit code-inspectie (`VideosController`, route `{itemId}/stream`). Relevant voor B03-010 (kinderprofielen, download-API) en voor blootstelling buiten het
   LAN. Geen patch in P0 (zou stock-clients/DLNA kunnen raken); als hiaat opgenomen voor B03-010 en de netwerkopzet
   (alleen LAN/VPN, I24 §1).
2. **Eén GPU-apparaat** (zie §5): A310/UHD 770-lanes zijn niet upstream te kiezen.
3. **Grote upstream-sprong**: 10.11 → 12.x; .NET 10 (`global.json` 10.0.0, `net10.0`), database-migraties en
   plugin-ABI wijzigen (NuGet 12.x). Gewone merge geeft 79 conflicten (upstream-backports); sync daarom via herbasis op
   `sync/<tag>` + volledige test (ADR-0006).

## 8. Upstream-GitHub-workflows in de fork

Zie ADR-0007. Kort: `ci-tests.yml`, `ci-openapi.yml`, `ci-compat.yml` en `ci-codeql-analysis.yml` blijven en draaien
waar hun triggers passen; bot-workflows die `secrets.JF_BOT_TOKEN` nodig hebben zijn met een repository-guard
beperkt tot `jellyfin/jellyfin` (patch JL-0001). Onze eigen CI: `jelly-leon-ci.yml`, `upstream-sync.yml`.

## 9. Delta-matrix B03 (bestaand / onvolledig / ontbrekend)

| ID | Onderwerp | Upstream 10.11.11 | Delta | Aanpak (ADR-0001-volgorde) |
|---|---|---|---|---|
| B03-001 | Forkstrategie, licentie, CI, compat-matrix | upstream-CI aanwezig | **onvolledig** → in P0 opgezet | fork-eigen docs, tools, CI (deze fase) |
| B03-002 | Universele bibliotheek, anime-overlay | films/series/muziek/collecties/tags | onvolledig (anime absolute ↔ seizoen) | metadata-plugin/overlay, geen DB-edits |
| B03-003 | Clients (PWA/native) | Web + officiële apps (andere repos) | onvolledig (matrix op echte apparaten) | `jelly-leon-web`, `jelly-leon-clients`; protocol ongewijzigd |
| B03-004 | Intel-transcodeplanner | QSV/VAAPI, één apparaat | **ontbrekend**: per-lane-keuze, fallback, GPU-budget | eerst meten (D08); dan core-patch of externe planner |
| B03-005 | Beste kwaliteit per apparaat | DeviceProfile, StreamBuilder, TranscodeReason | onvolledig (UI/feedbacklus) | plugin + Hub-UI |
| B03-006 | Metadata en anime-mapping | providers (TMDb, …), ProviderIds | onvolledig (versies, confidence, overrides) | plugin |
| B03-007 | Intro/recap/credits | MediaSegments-API + providers | onvolledig (detectie zelf) | `IMediaSegmentProvider`-plugin (eventueel bestaande community-plugin eerst beoordelen) |
| B03-008 | Semantische scènezoeker | — | ontbrekend | externe dienst (`zoeken-en-persoonlijke-ai`) + plugin-ACL |
| B03-009 | MediaGuard-integratie | — | ontbrekend | plugin/adapter, read-only + goedgekeurde verzoeken |
| B03-010 | Accounts en ouderlijk toezicht | UserPolicy, ratings, tags, schema's | onvolledig + risico §7.1 | eerst configuratie; daarna gerichte patch/plugin |
| B03-011 | Offline downloaden | download-route, policy-vlag | ontbrekend (clientkant) | clients + verlopende tokens |
| B03-012 | Live-tv en DVR | tuners, gids, timers, opnames | onvolledig (overlap-UI, retentie) | plugin + Hub-UI |
| B03-013 | Beheer en terugkeer upstream | — | **onvolledig** → sync-basis in P0 | `upstream-sync.yml`, patchregister, Backup-API |
