# Terug naar stock met Devices en Quality

De beheerder ziet de geregistreerde modules via `GET /media/v1/modules`. De
schakelaar `PUT /media/v1/modules/{slug}` bewaart de stand in de
pluginconfiguratie. Uitzetten beëindigt het gebruik van de module. De volgende
opslag hoort volgens de bron bij de huidige implementatie.

| Module | Na uitzetten | Na de beheeractie ‘gegevens verwijderen’ |
| --- | --- | --- |
| Devices | `data/jelly-leon/devices/devices.db` met de tabellen `instellingen` en `playback_sessions` | De geregistreerde beheerroutes bieden deze actie nog niet aan. |
| Quality | `data/jelly-leon/quality/quality.db` met de tabellen `instellingen`, `findings`, `suppressions` en `scans` | De geregistreerde beheerroutes bieden deze actie nog niet aan. |

De paden zijn relatief aan de configuratiemap. In de gebouwde revisie
`5d8784c635ea` bevat `data/jelly-leon/core/core.db` de gedeelde tabellen
`hub_jti`, `idempotentie`, `outbox` en `jobs`. Core beheert ook de map
`data/jelly-leon/secrets/`. SQLite kan zelf `sqlite_sequence` aanmaken voor
een tabel met een automatisch oplopende sleutel en naast een database de
bestanden `-wal` en `-shm` bijhouden.

De bundel staat onder `plugins/JellyLeon_<versie>/`. De schakelstanden staan
in `plugins/configurations/Jellyfin.Plugin.JellyLeon.xml`. De versieaanduiding
`jelly-leon/datamap-versie` beschermt de terugval. De beheercode voor de
schakelaars en de registratie van de routes staan in `PluginModuleSwitches`
en `RouteTable`. De aparte afhandeling van `UserDeleted` verwijdert de
persoonsgegevens van één verwijderd proefaccount.

Voor de handmatige controle in de simulator blijft de oorspronkelijke koude
kopie bewaard. Op een afzonderlijke, gestopte testkopie kan de beheerder de
pluginbundel en, na veiligstelling, de eigen opslagmap van de betreffende module
weghalen. Handmatig opruimen levert geen bewijs voor de ontbrekende beheeractie.
JLT-61(c) vraagt ook een verse export, een vergelijking van kijkgegevens per
gebruiker en afspelen met de stock-image.

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
