# Universele mediaserver — volledige bouwspecificatie

**Type/eigenaar:** Jellyfin-fork met losse uitbreidingen  
**Doel:** Eigen speler voor film/series/anime/muziek/live-tv op alle apparaten; gelijkwaardige basisfunctionaliteit behouden en uitbreiden zonder Jellyfin 1:1 herschrijven.

**Afhankelijkheden:** Back-up basis; MediaGuard API; Jellyfin upstream; GPU capability tests.

**Bron:** https://github.com/jellyfin/jellyfin

## 1. Concrete schermen en gebruikersreizen
Discover; Bibliotheek; Film; Serie; Anime; Muziek; Live TV; DVR; Zoek en scène; Downloads; Speler; Profielen; Apparaten; Onderhoud; Kwaliteitsweergave

**Per scherm minimaal:** responsief (360/390/768/1440 px), status leeg/laden/storing/offline, gedocumenteerde navigatie, zoek/filter/paginering, rolcontrole, datum van laatste update, bronherkomst, fout in het Nederlands, toegankelijk toetsenbordgebruik en zichtbaar auditspoor voor wijzigingen.

## 2. Datamodel en levensduur
media_item, external_id, episode_map, subtitle_track, audio_track, segment, scene_embedding, playback_capability, transcode_job, device_profile, playback_session, watch_progress, download_job, channel, epg_event, dvr_rule, client_version

Dwing database-migraties met forward-schema-tests af; time-series met retentie/aggregatie; primaire gegevens alleen bij bron. Entiteiten krijgen stable ID, versie, eigenaar, timestamps en provenance waar toepasselijk. Secrets alleen als vault-reference.

## 3. API en integratie-contracten
Jellyfin upstream API hergebruiken waar mogelijk; adapter GET /media/v1/search; GET /media/v1/scenes; POST /media/v1/mediaguard/request; GET /media/v1/transcode/capabilities; /media/v1/events/playback

Bij alle endpoints: authenticatie, rol, inputvalidatie, idempotency voor mutaties, paginering of cursors voor lijsten, rate limits, time-outs, versie/capability-detectie en machineleesbare foutcodes. De genoemde uitbreidingsroutes zijn ontwerpeisen, niet automatisch bestaande endpoints. API-contracten moet de bouwer in OpenAPI vastleggen en e2e verifiëren.

## 4. Bouwfasen (verplichte volgorde)

### F0 - Inventaris & onderzoek
**Fase-entry:** voorafgaande kritieke gates geslaagd; bestaande gegevens en huidige release vastgelegd; rollback plan bekend.

#### B03-001 — Forkstrategie en licentie
**Status bij start:** Bouwen; **impact:** Hoog.
**Gewenst gedrag en grenzen:** Baseline Jellyfin versie pinnen, forklicentie en upstream sync, scheid patches van plugins, upgradepad bewaken.
**Implementatie in code/diensten:** Import fork, CI, GPL-2.0 compliance, upstream change review; compat matrix server↔clients.
**Schermen/bediening:** Versie- en clientcompatibiliteitspagina.
**Acceptatie / concrete toets:** Stock Jellyfin clients kunnen inloggen/streamen na eerste fork zonder regressie.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

**Fase-exit:** alle in deze fase genoemde checks aantoonbaar geslaagd, code review, back-up-/rollback-gate, een gebruikersreis op mobiel en een negatieve test voor permissions. Bij een blocker niets forceren: status `Geblokkeerd` + reden + eigenaar.

### F1 - Kern en contracten
**Fase-entry:** voorafgaande kritieke gates geslaagd; bestaande gegevens en huidige release vastgelegd; rollback plan bekend.

#### B03-002 — Universele bibliotheek
**Status bij start:** Bouwen; **impact:** Middel.
**Gewenst gedrag en grenzen:** Film, series, anime, muziek in één ervaring met filters, collecties, tags, genres, persoon en talen.
**Implementatie in code/diensten:** Jellyfin backend metadata APIs; add overlay for anime metadata + external IDs; no DB direct edits.
**Schermen/bediening:** Unified homepage, watchlist, anime-splits, details en muziek.
**Acceptatie / concrete toets:** Anime met absolute episodes en film met zelfde titel blijven aparte items.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

#### B03-003 — Beschikbaarheid van clients
**Status bij start:** Bouwen; **impact:** Middel.
**Gewenst gedrag en grenzen:** Web, Android, iOS, Android TV, tv-browser, Chromecast/airplay waar clients dit ondersteunen; toegankelijkheid.
**Implementatie in code/diensten:** Keep upstream protocol, develop PWA shell and prioritized native client after compat tests; tested matrix.
**Schermen/bediening:** Responsive player, remote controls, subtitle/audio selector.
**Acceptatie / concrete toets:** Ondertitels, resume en afspelen geverifieerd op echte gebruikte tv/apparaten.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

**Fase-exit:** alle in deze fase genoemde checks aantoonbaar geslaagd, code review, back-up-/rollback-gate, een gebruikersreis op mobiel en een negatieve test voor permissions. Bij een blocker niets forceren: status `Geblokkeerd` + reden + eigenaar.

### F2 - Functionaliteit
**Fase-entry:** voorafgaande kritieke gates geslaagd; bestaande gegevens en huidige release vastgelegd; rollback plan bekend.

#### B03-004 — Intel transcoding planner
**Status bij start:** Bouwen; **impact:** Hoog.
**Gewenst gedrag en grenzen:** Arc A310 eerst voor AV1 encodes waar geschikt; UHD770 voor andere QSV lanes; fallback CPU zonder kwaliteit beschadigen.
**Implementatie in code/diensten:** Probe /dev/dri render node mapping and FFmpeg codec capabilities; per-session benchmark, GPU workload budget shared with MediaGuard.
**Schermen/bediening:** Streamkwaliteit Auto/Direct/Transcode met reden en hardware lane.
**Acceptatie / concrete toets:** A310 AV1 job belast verkeerde node niet; A310 offline → afspelen via fallback.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

#### B03-005 — Beste kwaliteit per apparaat
**Status bij start:** Bouwen; **impact:** Hoog.
**Gewenst gedrag en grenzen:** Direct play bij compatibele codecs/HDR/DV/audio; transcode uitsluitend wanneer nodig en legbaar.
**Implementatie in code/diensten:** Capability profile by codec/level/container/audio/DV/HDR/bitrate and bandwidth, feedback from playback failures.
**Schermen/bediening:** Per-client debug scherm met geschatte bandbreedte en why-transcode.
**Acceptatie / concrete toets:** Ondersteund DV-device krijgt originele DV, ongeschikt apparaat fallback met duidelijk kwaliteitslabel.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

**Fase-exit:** alle in deze fase genoemde checks aantoonbaar geslaagd, code review, back-up-/rollback-gate, een gebruikersreis op mobiel en een negatieve test voor permissions. Bij een blocker niets forceren: status `Geblokkeerd` + reden + eigenaar.

### F3 - Integraties en veiligheid
**Fase-entry:** voorafgaande kritieke gates geslaagd; bestaande gegevens en huidige release vastgelegd; rollback plan bekend.

#### B03-006 — Metadata en anime mapping
**Status bij start:** Bouwen; **impact:** Middel.
**Gewenst gedrag en grenzen:** Multi-source metadata quality, titels/talen, anime seizoen/absolute/TVDB mapping; conflict review.
**Implementatie in code/diensten:** Versioned external IDs, confidence + user overrides; delayed background scans; never modify MediaGuard wanted state.
**Schermen/bediening:** Metadata-suggesties met bron en behoud eigen wijzigingen.
**Acceptatie / concrete toets:** S01E01 versus absolute E13 blijft correct gelinkt na metadata refresh.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

#### B03-007 — Intro/recap/credits detectie
**Status bij start:** Bouwen; **impact:** Middel.
**Gewenst gedrag en grenzen:** Playback segmenten herkennen of crowdsourced metadata vergelijken, handmatig corrigeren; geen ongetest automatisch overslaan.
**Implementatie in code/diensten:** Segment provider with timestamps, source, confidence, QC sample, plugin upstream compatible.
**Schermen/bediening:** Skip intro/recap/credits knop per episode en profielswitch.
**Acceptatie / concrete toets:** Geen segmenten > mediaduur, overlap; skip werkt op mobiel en web.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

**Fase-exit:** alle in deze fase genoemde checks aantoonbaar geslaagd, code review, back-up-/rollback-gate, een gebruikersreis op mobiel en een negatieve test voor permissions. Bij een blocker niets forceren: status `Geblokkeerd` + reden + eigenaar.

### F4 - Automatisering
**Fase-entry:** voorafgaande kritieke gates geslaagd; bestaande gegevens en huidige release vastgelegd; rollback plan bekend.

#### B03-008 — Semantische scènezoeker
**Status bij start:** Bouwen; **impact:** Hoog.
**Gewenst gedrag en grenzen:** Zoeken op omschrijving of uitgesproken dialoog; auteursrechten/privacy en resource constraints respecteren.
**Implementatie in code/diensten:** Local ASR optional per opted-in media, scene detection, subtitles sync, vector index with per-user ACL; batching only idle.
**Schermen/bediening:** Zoekresultaat met tijdcode, titel, reden, open stream at timestamp.
**Acceptatie / concrete toets:** Zonder transcript of permissie geen hallucinaties of lek van verborgen media.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

#### B03-009 — MediaGuard-integratie
**Status bij start:** Bouwen; **impact:** Hoog.
**Gewenst gedrag en grenzen:** Missing/upgrades/subtitles via officiële MediaGuard actie; behoud van releasedecision, owner boundaries.
**Implementatie in code/diensten:** Read-only wanted/status connector, trigger allowed request with approval, idempotency; app context deep link.
**Schermen/bediening:** Bij titel knop ‘Vraag aan/zoek betere versie’ en leverstatus, geen tweede downloader.
**Acceptatie / concrete toets:** Noodstop en kwaliteitsregels MediaGuard blijven leidend.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

**Fase-exit:** alle in deze fase genoemde checks aantoonbaar geslaagd, code review, back-up-/rollback-gate, een gebruikersreis op mobiel en een negatieve test voor permissions. Bij een blocker niets forceren: status `Geblokkeerd` + reden + eigenaar.

### F5 - Hardening & UX
**Fase-entry:** voorafgaande kritieke gates geslaagd; bestaande gegevens en huidige release vastgelegd; rollback plan bekend.

#### B03-010 — Accounts en parental control
**Status bij start:** Bouwen; **impact:** Hoog.
**Gewenst gedrag en grenzen:** Gezinsprofielen, kijkstatus, kijkbeperkingen op leeftijd, pincodes, apparaten en offline status.
**Implementatie in code/diensten:** Integrate upstream permissions, per-profile visibility for metadata/scenes/downloads, lock token expiry.
**Schermen/bediening:** Kinderprofiel met contentfilters, user picker, geschiedenis.
**Acceptatie / concrete toets:** Kinderaccount krijgt geen adult media via zoeken, thumbnail cache of download API.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

#### B03-011 — Offline downloaden
**Status bij start:** Bouwen; **impact:** Middel.
**Gewenst gedrag en grenzen:** Geautoriseerde media encrypted lokaal opslaan in cliënt waar mogelijk, verlopen rechten en opslagquota.
**Implementatie in code/diensten:** Mobile download manager with profile auth, expiring tokens, resume/retry, download codec profiles.
**Schermen/bediening:** Download overzicht met voortgang, opslag, kwaliteit, opruimen.
**Acceptatie / concrete toets:** App kan na tijdelijk netwerkverlies offline kijken; uitgezet account kan niet nieuwe downloads starten.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

#### B03-012 — Live-tv en DVR
**Status bij start:** Bouwen; **impact:** Middel.
**Gewenst gedrag en grenzen:** EPG, tuner, opnameplanner, overlapdetectie en opslagquota met behoud van Jellyfin compatibiliteit.
**Implementatie in code/diensten:** Use Jellyfin tuner and DVR baseline; add conflicts UI, recording job status, retention and guide sync.
**Schermen/bediening:** Gids, live player, geplande opnames, overlapwaarschuwing.
**Acceptatie / concrete toets:** Overlappende opname meldt beperkingen; na herstart planner herneemt veilig.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

**Fase-exit:** alle in deze fase genoemde checks aantoonbaar geslaagd, code review, back-up-/rollback-gate, een gebruikersreis op mobiel en een negatieve test voor permissions. Bij een blocker niets forceren: status `Geblokkeerd` + reden + eigenaar.

### F6 - Release en nazorg
**Fase-entry:** voorafgaande kritieke gates geslaagd; bestaande gegevens en huidige release vastgelegd; rollback plan bekend.

#### B03-013 — Beheer en terugkeer upstream
**Status bij start:** Bouwen; **impact:** Middel.
**Gewenst gedrag en grenzen:** Automatische upstream security/advisories, canary tests, apart client compatibility en schema-migraties.
**Implementatie in code/diensten:** Patch stack minimal; protected CI, canary DB copy, version compatibility documented.
**Schermen/bediening:** Updatecentrum inclusief client matrix.
**Acceptatie / concrete toets:** Fork migratie is terug te zetten met DB backup + binary en streaming blijft werken.
**Foutafhandeling en bewijs:** een externe storing mag niet als succes worden gelogd; leg testscenario, gebruikte app/image-versie, screenshots, redacted request/response, timestamps, audit/rollback en incidentlink vast.

**Fase-exit:** alle in deze fase genoemde checks aantoonbaar geslaagd, code review, back-up-/rollback-gate, een gebruikersreis op mobiel en een negatieve test voor permissions. Bij een blocker niets forceren: status `Geblokkeerd` + reden + eigenaar.

## 5. Niet-regressie, randgevallen en verbodsbepalingen
Begin met een Jellyfin plugin/adapter in plaats van direct eigen protocol. Maak fork pas wanneer onderbouwd nodig. Transcoding wordt nooit gelijktijdig onbeperkt met MediaGuard AV1 uitgevoerd. Geen aanname dat alle smart-tv platforms automatisch native apps ondersteunen; per platform testen.

## 6. Oplevering door bouwer
Opleveren: (1) broncode en tests, (2) migration scripts en versiecompatibiliteit, (3) Compose/TrueNAS app manifest met gepinde images, (4) .env.example zonder geheimen, (5) OpenAPI/connector schemas, (6) test- en auditrapport, (7) restore bewijs, (8) release notes, (9) gebruikershandleiding, (10) screenshots web/mobiel. Markeer niet-geteste hardware/echte accounts als `NIET GEVALIDEERD`.

## 7. Proof of Done
Alle acceptatiecriteria in Excel zijn gekoppeld aan testbewijs en codecommit; bij stroomonderbreking, uitval van afhankelijke app, NAS-herstart, gewijzigde credentials en incompatibele versie degradeert de service aantoonbaar veilig. Geen directe writes aan de database van een andere app.
