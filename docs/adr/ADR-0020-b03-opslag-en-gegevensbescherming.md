# ADR-0020 — B03: Eigen opslag en gegevensbescherming; kijkgeschiedenis blijft altijd beschikbaar (HARDE EIS)

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011).
- **Herkomst:** voorstel ADR-B03-08 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §10.9). Jurypunten J-BESCH A5–A8, A15, F3-B1, F4-B2, F2-I3, F6-I1.
- **Werkpakketten:** B03-017, B03-015, B03-013; testen JLT-65, JLT-61, JLT-62; HARDE EIS ook JLT-60 en
  JLT-70…74 (aanvulling hieronder).

## Context

- De gebruiker eist dat bibliotheken, metadata, kijkgeschiedenis en gebruikersgegevens beschermd blijven; het risicobeleid
  verbiedt het wijzigen van bestanden zonder verificatie en massale operaties bij een mogelijke storing.
- Upstream schrijft standaard ondertitels naast de media (`SaveSubtitlesWithMedia` = true); de upstream-back-up neemt
  plugin-data niet mee; `GET /Plugins/{id}/Configuration` geeft de plugin-XML aan elke beheerder; `CleanupUserDataTask`
  heeft geen standaardtrigger.
- `SaveUserData` schrijft het hele UserData-record (`UserDataManager.cs:50-77`); een herstel uit een momentopname kan
  gelijktijdige kijkvoortgang overschrijven (F3-B1).

## Besluit

1. **Schrijfplekken:** alleen `/config/data/jelly-leon/**`, `/cache/jelly-leon/**`, de interne metadatamap (alleen F3), de
   bevestigde `encoding.xml` (F5, met back-up) en de eigen MediaSegments-rijen (F6, gericht). Nooit mediamappen,
   `jellyfin.db` direct, `UserData`/`Users`/rechten/voorkeuren (enige bewaakte uitzondering: F3-spoorindexen bij `reset`/
   `remap` na BG-21), `UpdateItemAsync`, `IItemRepository.Save*`, `forceOverwrite`.
2. **Afdwingen** met een analyzer per namespace, `InternalWriteScope` en een opdrachtbouwer die bibliotheekpaden als
   uitvoer weigert; **mountcontrole** zonder proefschrijven.
3. **Geheimen** in `/config/data/jelly-leon/secrets` (0700/0600, eigenaar 568); nooit in de XML, een export of een log.
4. **Register van persoonsgegevens** met bewaartermijnen en **één `UserDeleted`-afhandeling** (wissen of pseudonimiseren);
   exports standaard zonder interactielog; kopieën van vóór een migratie hooguit 30 dagen (max. 3).
5. **Menselijk werk nooit automatisch wissen.** Stroomonderbreker: > 5 % of > 50 items wees in één scan → opruimen bevriest,
   status degraded, incident.
6. **Migraties:** per module een kopie met `integrity_check` vóór de migratie; forward-schematests.
7. **Back-up:** export per module met `preview_hash`, ZFS-snapshot van `/config`, B12-dekkingsitem (Δ-HUB-3).
8. **Terug naar stock:** per module gedocumenteerd gedrag en restanten (B03-013 uitgebreid).
9. **Bewijs:** een differentiële controle-run (stock tegen Jelly Leon, echte 12.x-tabellen, toegestane wijzigingslijst per
   module) in plaats van checksums over Jellyfin-tabellen (die veranderen altijd, bijv. `Users.LastActivityDate`).

## Gevolgen

- Machinevertalingen staan niet naast de media (MediaGuard blijft naar een menselijke vertaling zoeken).
- Na het verwijderen van de plugin blijven gedocumenteerde restanten (bijv. eigen MediaSegments-rijen, gepubliceerde
  vertalingen tot "alles depubliceren"); die zijn zichtbaar en per module op te ruimen.

## Verificatie

JLT-65 (integrale differentiële run, 0 bytes gewijzigd in het corpus, 0 GUID's na UserDeleted, geen geheimen in XML/export/
log), JLT-61 (terug naar stock), JLT-62 (mount en schrijfopties), per functie de gegevensbeschermingstest.

## Aanvulling 2026-11-09 — HARDE EIS van de gebruiker

Letterlijk: alle kijkgeschiedenis (gezien-status, hervatpunten, favorieten, beoordelingen, onthouden spoorkeuzes,
gebruikers, rechten) en de MediaGuard-voortgang blijven altijd beschikbaar. Gevolgen voor dit besluit: (1) de enige
schrijfactie in `UserData`/`Users` buiten F3 (BG-21) is de eenmalige overname van B03-015 vóór de cutover, via de
officiële API, na akkoord op het droge rapport en met een vóór/na-rapport per gebruiker; (2) geen cutover zonder akkoord
van de gebruiker op elk verschil, ook door upstream-migraties; (3) de bestaande installatie (Emby, of Jellyfin als D07 die
meet) blijft ongewijzigd als terugval; (4) vóór Emby verwijderd wordt, staat een blijvend JSON-exportarchief van alle
Emby-kijkgegevens met sha256 in de back-updekking (bouwplan §10.9.2); (5) MediaGuard-releases bewijzen een upgrade op een
gevulde database van de vorige versie zonder gegevensverlies (eis aan media-guard-ultimate).
