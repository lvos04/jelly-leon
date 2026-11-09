# ADR-0015 — B03: Jellyfin 12.x als basis en overname van de bestaande mediaserver (Emby; ook Jellyfin als D07 dat meet)

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011). Deel A (overname vanuit Emby) heeft prioriteit P0 van de gebruiker en begint al in golf 0.
- **Herkomst:** voorstel ADR-B03-01 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §8, §10.9.1 en B03-014/B03-015). Vult ADR-0011 aan; vervangt het niet.
- **Werkpakketten:** B03-014, B03-015; testen JLT-60, JLT-61, JLT-62, JLT-67; overname vanuit Emby
  JLT-70…74 (aanvulling hieronder).

## Context

- De gebruiker besliste dat server en web vóór P4 naar de nieuwste stabiele 12.x gaan (besluit 2 in `ai-server-manager/docs/platform-v2/OVERDRACHT/STATUS.md`). ADR-0011
  legt de werkwijze vast (herbasis via `upstream_sync.py`, Node 24, digests, terugzetten = image + DB samen).
- 12.x verandert data: 18 nieuwe EF-migraties en migratieroutines, waaronder `HarmonizeConflictingUserData`,
  `MergeDuplicatePeople` en `RemoveOrphanedUserPermissionsAndPreferences`; `MigrateRatingLevels` draait opnieuw.
- Een 10.11-back-up kan in 12.x niet worden teruggezet (modelpariteit, `JellyfinMigrationService.cs:491`); de pluginmap zit
  niet in de upstream-back-up.
- 12.x zet legacy-authenticatie uit; MediaGuard gebruikt `X-Emby-Token` en breekt (Δ-MG-AUTH).
- Er kan al een stock-Jellyfin draaien (D07, onbekend), met een eigen bibliotheek, kijkgeschiedenis en plugins, en met
  upstream-opties die in mediamappen schrijven (`SaveSubtitlesWithMedia` standaard true).
- `JL_RUNTIME_IMAGE` staat in CI nog op 10.11.11; gedragstests zouden dan op de oude runtime draaien.

## Besluit

1. P4-0 is een **eigen programmafase** met een gate (`docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md` §4); geen B03-modulewerk vóór die gate.
2. **Overname = procedure met een proef op een kopie:** snapshot + upstream-back-up + export van plugin-data; proefmigratie
   op een kopie; **vóór/na-rapport per gebruiker** (gezien, hervatpunten, favorieten, beoordelingen, onthouden spoorkeuzes,
   rechten, ouderlijk toezicht, apparaten, kunnen inloggen); elk verschil vraagt goedkeuring. Pas daarna de echte update.
3. **Terugzetten** = vorige image én DB-snapshot samen; een negatieve test bewijst dat alleen de image niet volstaat.
4. Bij de overname worden upstream-opties die in mediamappen schrijven geïnventariseerd en, na bevestiging, met back-up en
   readback uitgezet; de ondertitel-downloaders van Jellyfin worden niet geïnstalleerd (BG-22). Media blijven alleen-lezen
   gekoppeld; de mountcontrole leest de vlag zonder proefschrijven.
5. **Legacy-auth blijft uit**; Δ-MG-AUTH is exitcriterium. Zonder Δ-MG-AUTH geen B03-batch op de NAS (status `onbekend`).
   Eén derden-client met legacy-headers komt in de matrix (BG-01).
6. `JL_RUNTIME_IMAGE` gaat in P4-0 mee naar de 12.x-digest; baselines worden op exact die digest opnieuw gemeten.

## Alternatieven

- *Direct in-place upgraden zonder proef:* sneller, maar een verandering in kijkgeschiedenis wordt pas achteraf ontdekt en
  is niet meer terug te zetten met een 10.11-back-up. Verworpen.
- *Legacy-auth weer aanzetten:* lost MediaGuard op zonder MediaGuard-werk, maar zet tokens weer in URL's en logs. Alleen
  als bewuste keuze van de gebruiker (BG-01).
- *Eerst B03 op 10.11 bouwen en later migreren:* dubbel werk (ABI-breuk `CleanupExtractedData`, .NET 10). Verworpen door de
  gebruiker.

## Gevolgen

- P4 start later, maar op een vaste basis; elke latere 12.y-sync gebruikt dezelfde procedure (B03-019, JLT-67).
- De gebruiker ziet vóór de echte overname per gebruiker wat er verandert.
- MediaGuard moet in de eigen repo een kleine wijziging leveren vóór de NAS-batch kan draaien.

## Verificatie

JLT-60 (proefmigratie, 0 onverklaarde verschillen), JLT-61 (terugzetten + negatieve proef + terug naar stock), JLT-62
(schrijfopties, mountcontrole, bestaande plugins), JLT-67 (sync-proef op de 12.x-runtime). Echte overname: JLT-69
(*Geblokkeerd* tot de NAS).

## Aanvulling 2026-11-09 — de bestaande mediaserver is Emby (besluit van de gebruiker)

- **Feit:** de gebruiker gebruikt nu **Emby**; de kijkgeschiedenis staat in Emby (D07 meet versie, gebruikers en
  bibliotheken). "Het belangrijkste is mijn kijkgeschiedenis; als alles werkt verwijder ik Emby."
- **HARDE EIS:** alle kijkgeschiedenis (gezien-status, hervatpunten, favorieten, beoordelingen, onthouden spoorkeuzes,
  gebruikers, rechten) en de MediaGuard-voortgang blijven altijd beschikbaar; geen cutover zonder vóór/na-rapport per
  gebruiker en uitdrukkelijk akkoord op elk verschil; de bestaande installatie blijft ongewijzigd als terugval.
- **Aanvullend besluit:** B03-015 wordt "Overname vanuit de bestaande mediaserver (Emby; ook Jellyfin als D07 dat meet)".
  Deel A (Emby, P0, al in golf 0): eerst JellyPlex-Watched beoordelen (GPL-3.0, los proces); alleen-lezen via de Emby-API
  (alleen GET, API-sleutel in de geheimenmap); koppelen op provider-ID's en daarna pad; afhandellijst voor de rest; per
  gebruiker gezien-status, hervatpunten, favorieten (en waar mogelijk beoordelingen en spoorkeuzes); schrijven in Jelly Leon
  alleen via de officiële API na akkoord; herhaalbare proefrun; laatste delta bij de overstap; wachtwoorden niet (nieuw of
  SSO). Deel B (Jellyfin) is de procedure hierboven. Emby blijft draaien tot de controlelijst "Emby verwijderen"
  (bouwplan §10.9.2) is afgewerkt; de gebruiker verwijdert Emby zelf (APP-02, I26-26-02).
- **MediaGuard:** Δ-MG-AUTH geldt per server (Emby `X-Emby-Token`, Jelly Leon 12.x `Authorization: MediaBrowser Token=…`);
  Δ-MG-DUAL laat MediaGuard Emby én Jelly Leon tegelijk volgen; de Emby-koppeling onderbreekt nooit.
- **Verificatie:** JLT-70 (proefrun met een echte Emby-container), JLT-71 (idempotent, delta), JLT-72 (afhandellijst), JLT-73
  (0 schrijfacties naar Emby, MediaGuard volgt beide), JLT-74 (echte NAS; *Geblokkeerd*).

- **Volgend besluit in deze repo:** na de beoordeling van JellyPlex-Watched (B03-015 stap A2; GPL-3.0 volgens
  GitHub op 2026-11-09) komt de keuze hergebruiken, aanvullen of een eigen overnametool als eigen ADR in deze
  repo (`docs/platform-v2/04_BESTAANDE_APPS/A03_JELLYPLEX_WATCHED.md`). Emby blijft tot de controlelijst
  "Emby verwijderen" (bouwplan §10.9.2) ongewijzigd draaien; de gebruiker verwijdert Emby zelf.
