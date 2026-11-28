# B03-021 · Watch Together op Jellyfin 12.x

WT-1 voegt groepsmetadata en diagnose toe aan de bestaande SyncPlay-server. De schakelaar `watch` staat standaard uit. In het Jellyfin-dashboard toont de pluginpagina de stand van de decorator. Bij een inactieve decorator en ingestelde gasten of een kinderprofiel wordt de melding rood, geeft `/connector/v1/health` de status `down` en verschijnt `media.watchgroup.degraded` in de outbox. Zet in dat geval in het Jellyfin-dashboard het SyncPlay-recht van gasten en kinderen op **Geen**. Zonder zulke accounts is de status bij dezelfde storing `degraded`.

## Groepen en persoonsgegevens

De plugin vervangt uitsluitend de bekende singletonregistratie uit `ApplicationHost` en geeft alle zeven leden van `ISyncPlayManager` door aan dezelfde upstream-instantie. Groep aanmaken, toetreden en verlaten leiden daarna tot een controle bij SyncPlay. Ook bij `SessionEnded` en elke 30 seconden controleert de module de groepen. Bij een serverstart sluit hij openstaande rijen uit de vorige serverinstantie. Het veld `detected_by` vermeldt welke controle het einde als eerste vaststelde. De waarden zijn `reconcile`, `session_ended` en `startup`. Een latere sessiemelding voor dezelfde groep levert geen tweede event op. De vastgelegde event-ID maakt het doorgeven van `media.watchgroup.ended` herhaalbaar na een onderbreking.

`/config/data/jelly-leon/watch/watch.db` bewaart het groeps-ID, het eigenaarspseudoniem, de begin- en eindtijd, de zichtbaarheid, het wachtbeleid en de stand van de eventmelding. De groepsnaam en de deelnemersnamen komen bij een verzoek uit de draaiende server. `UserDeleted` ontkoppelt de eigenaar in de actuele tabel, verwijdert de gastinstelling en laat Core de schrijflog inkorten. De sleutel voor het eigenaarspseudoniem staat in de geheimenmap. Beëindigde groepen worden standaard na zes uur opgeruimd, zodra het event is vastgelegd. De instelling heet `GroupRetentionHours`. Bewaarde migratiekopieën vallen onder het back-upbeleid van Core.

## API voor de aangemelde gebruiker

| Route onder `/media/v1/watch` | Gedrag |
| --- | --- |
| `GET /capabilities` | Rapporteert `decorator_active`, health en de beschikbare functies. In WT-1 staat privézichtbaarheid uit. |
| `GET /groups` | Pagineert de zichtbare groepen met de ETag van hun metadata. `limit` is standaard 50 en maximaal 200. |
| `GET /groups/{id}/diagnostics` | Toegang voor een aangetoond lid of een volwassen beheerder met zicht op de groep. Voor een niet-lid geven een bestaand en een onbekend groeps-ID dezelfde 404-fout. |
| `POST /admin/purge` | Een persoonlijke beheersessie, `Idempotency-Key` en `{"confirm":"WISSEN"}` zijn vereist. HTTP 202 bevestigt het wissen van groepsrijen, module-events en de modulesleutel. |

Op alle routes geldt de gemeenschappelijke grens van 1 MiB. De contracten en de geregistreerde afhankelijkheid van upstream staan in [OpenAPI](../openapi/jelly-leon-plugin.openapi.json) en [UG-F1-1](UPSTREAM_GEDRAG.md).

## Uitzetten, verwijderen en terug naar stock

- **Module uit.** De vier moduleroutes geven een aangemelde gebruiker 404. De oorspronkelijke dienst verzorgt `/SyncPlay/*` en `/GetUtcTime`. Bestaande moduledata volgt de bewaartermijn. Voor onmiddellijk wissen gebruikt een beheerder de purge terwijl de module nog aanstaat.
- **Plugin verwijderd.** Stop de eigen testserver, verwijder op een kopie de plugin-DLL en start zonder de plugin. SyncPlay wordt door Jellyfin geregistreerd. Het modulebestand, de pluginconfiguratie en de geheimenmap kunnen als restanten blijven staan.
- **Terug naar stock.** Gebruik een compatibele stockversie op een kopie van de configuratie zonder de DLL. De fork-image kan de meegeleverde DLL bij het starten opnieuw plaatsen. De pluginproef vergelijkt vóór en na de overgang ook favoriet, gezienstatus, beoordeling en hervatpunt van een synthetische gebruiker. Maak vóór de eerste inschakeling op de NAS een snapshot en de reguliere Jellyfin-back-up, volgens het herstelplan.

## Verificatie van WT-1

| Onderdeel | Proef |
| --- | --- |
| a | `plugin_proef.py` vergelijkt de 22 SyncPlay-operaties, `GET /GetUtcTime` en alle gerefereerde schema’s op stock, met de module aan en uit, en na verwijdering. |
| b | De upstream-implementatietest construeert zelf `SyncPlayManager`. De controllertest start via `JellyfinApplicationFactory` een eigen server. De server- en pluginjobs bouwen afzonderlijk. In deze opzet is de suite met een geladen en ingeschakelde plugin niet uitgevoerd. |
| c | Twee stockcontroles, de plugin en de terugkeer naar stock leveren een lijst en detailantwoord voor een niet-lege groep. Alleen het groeps-ID en `LastUpdatedAt` worden vervangen voordat de proef de antwoordbytes vergelijkt. |
| d | `watch_herhaal.py` doorloopt minimaal 50 keer een tweede `NewGroup`, uitloggen en herstarten van het serverproces. Per gebeurtenis controleert het script de actieve rijen, de eindreden en de overeenkomstige outboxmelding. De afzonderlijke plugintest simuleert dezelfde drie overgangen en laat de 30-secondencontrole een gemiste sessiemelding herstellen. |
| e | `WatchTogetherTests` forceert een inactieve manager en controleert health, capabilities en de outbox. `test_config_pagina.py` controleert de rode waarschuwing en het SyncPlay-advies op de dashboardpagina. |

De afzonderlijke DI-proef gebruikt de gebouwde upstream-assembly met een gesimuleerd sessie-, gebruikers- en bibliotheekbeheer. De normale registratie moet één oorspronkelijke singleton opleveren. De proef maakt daarmee twee groepen en controleert de actieve rij na de wissel en na vertrek. Met een reeds gebouwde upstream-revisie is deze proef als volgt te herhalen.

```sh
dotnet test plugins/JellyLeon.Plugins.sln -c Release \
  -p:JellyLeonSyncPlayAssembly="$PWD/Emby.Server.Implementations/bin/Release/net10.0/Emby.Server.Implementations.dll" \
  --filter 'FullyQualifiedName~WatchSamenstellingProef'
```

Het meetbewijs per onderdeel staat in [EVIDENCE](EVIDENCE.json). De baseline uit [B03-020](B03-020_WATCH_TOGETHER.md) en JLT-06 met echte apparaten hebben hun eigen meetstatus.
