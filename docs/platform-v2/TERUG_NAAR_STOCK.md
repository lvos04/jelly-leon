# Terug naar stock met Devices en Quality

Een beheerder leest de schakelstanden met `GET /media/v1/modules` en zet een
module uit via `PUT /media/v1/modules/{slug}`. Uitzetten stopt het verzamelen.
De beheerexport en de wisactie blijven bereikbaar voor een persoonlijke
beheerderssessie, ook nadat de module is uitgezet.

| Module | Eigen tabellen die na uitzetten bewaard blijven | Na de wisactie |
| --- | --- | --- |
| Devices | `instellingen`, `playback_sessions` in `data/jelly-leon/devices/devices.db` | Beide tabellen zijn leeg. De bewaartermijn valt terug op 30 dagen. |
| Quality | `instellingen`, `findings`, `suppressions`, `scans` in `data/jelly-leon/quality/quality.db` | Alle vier tabellen zijn leeg. De bewaartermijn valt terug op 90 dagen. |

## Exporteren, controleren en wissen

1. Zet de module uit als het verzamelen moet stoppen. Gebruik voor `{slug}`
   de waarde `devices` of `quality`.
2. Download `GET /media/v1/{slug}/export` en bewaar de originele JSON-bytes.
   De export bevat tijdstip, modulenaam, schemaversie, rijen en aantallen per
   tabel. Accountverwijzingen zijn per module gepseudonimiseerd. Vergelijk de
   SHA-256 van het gedownloade bestand met de ETag, zonder de aanhalingstekens.
3. Stuur `POST /media/v1/{slug}/data/purge?dry_run=true` met een
   `Idempotency-Key` (UUID) en de JSON-body
   `{"export_sha256":"<sha256-van-het-bestand>"}`. Controleer de aantallen en
   `applied: false`. Zonder queryparameter geeft de route ook dit voorbeeld.
4. Bevestig met dezelfde body, `dry_run=false` en een nieuwe
   `Idempotency-Key`. Een antwoord met `applied: true` geeft de aantallen
   gewiste rijen. Herhaal bij een onderbroken verbinding hetzelfde verzoek
   met dezelfde sleutel om het bewaarde antwoord op te vragen.

De server bewaart per module de laatste export als `beheerexport.json` naast
de moduledatabase en leest het bestand na het schrijven terug. Een volgende
export vervangt dat bestand. Bij het wissen vergelijkt de server zowel het
opgeslagen bestand als de actuele rijen met de opgegeven hash. Het UTC-tijdstip
in de export mag hoogstens 24 uur oud zijn. Verificatie en verwijdering delen
één SQLite-schrijftransactie. Een gewijzigde rij vraagt ook bij gelijke
aantallen een nieuwe export. Een fout in een van de tabellen draait de
hele verwijdering terug.

Een aangemelde gebruiker zonder beheerrecht krijgt HTTP 403. Een ontbrekend,
verlopen of beschadigd archief geeft HTTP 409 met `details.reason`
`export_required`. Bij gewijzigde gegevens geeft HTTP 409 de reden
`export_changed`. Een schemawijziging of een onverwachte nevenwijziging
tijdens het wissen leidt eveneens tot weigering.

## Restanten op de testkopie

Na het wissen blijven het lege moduleschema, de beheerexport en eventuele
bestaande migratiekopieën aanwezig. SQLite beheert zelf zijn volgnummer in
`sqlite_sequence` en de bestanden `-wal` en `-shm`. De module bewaart
herhaalantwoorden per verzoek in `jelly-leon/{slug}/beheerherhaling.db`
onder de cachemap. De idempotentielaag herkent verzoeken gedurende 24 uur
en ruimt verlopen antwoorden op bij het volgende wis- of voorbeeldverzoek.
De gedeelde kerndatabase, de andere module, de bibliotheek, de kijkgegevens
en de MediaGuard-voortgang vallen buiten de wisactie.

De paden onder `data/` zijn relatief aan de configuratiemap. De pluginbundel
staat onder `plugins/JellyLeon_<versie>/`. De schakelstanden staan in
`plugins/configurations/Jellyfin.Plugin.JellyLeon.xml`. Ook de kernopslag,
de geheimenmap en de versieaanduiding `jelly-leon/datamap-versie` blijven
aanwezig. De afzonderlijke `UserDeleted`-afhandeling beheert de
persoonsgegevens van één verwijderd account.

Bewaar de koude kopie en de gedownloade exports. Op een afzonderlijke,
gestopte testkopie kan de beheerder daarna de pluginbundel en de eigen
data- en cachemap van de gekozen module weghalen. De integrale
JLT-61(c)-proef vergelijkt vervolgens de kijkgegevens per gebruiker, de
mediamap en de restanten, en controleert het afspelen met stock.

## Toegestane wijzigingen in de Jellyfin-database

`tools/b03-harnas/toegestaan-modules.json` bevat een leeg object. Devices
schrijft zijn afspeelsessies in de eigen opslag. Quality schrijft daar zijn
bevindingen, onderdrukkingen en scangegevens. Voor beide modules zijn dus nul
extra kolomuitzonderingen op de stockdatabase verantwoord. De standaarduitzonderingen
van het vergelijkingsharnas blijven zichtbaar in het meetrapport.

Bij `b03h diffrun --alle-modules` leest het harnas de modulelijst van systeem B,
zet iedere uitgeschakelde module aan en leest de standen terug. Het rapport
noemt de actieve modules en de aantallen gemeten gebruikers en items. Een lege
bibliotheek, een ontbrekende proefgebruiker of een lege modulelijst breekt deze
meting af.
