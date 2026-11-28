# S-G1-14 · C1.3-JL-07

**Bezig · 28 november 2026.** De routetests gebruiken tijdelijke plugindatabases, een Hub-simulator en synthetische sessies. Een tweede proef start Kestrel op een tijdelijk lokaal luisteradres. De client leest het volledige HTTP/1.1-antwoord.

| Aanmelding en instelling | Te groot met Content-Length | Te groot met chunked |
|---|---|---|
| Geldige sessie, standaardinstelling | 413 | 413 |
| Zonder sessie, standaardinstelling | 401 | 401 |
| Zonder sessie, spike aan op het rootpad | 413 | 401 |
| Zonder sessie, spike aan onder de basis-URL | 401 | 401 |
| Geldige sessie, spike aan onder de basis-URL | 413 | 413 |

Elke cel omvat GET, POST en PUT. PUT gebruikte formulierinhoud op een route met een padparameter. De client controleerde de status, de contractvelden, trace-ID, cache-instructie en voor 413 ook `details.max_bytes`. De test controleerde tevens de limiet die Kestrel na routering op het verzoek toepast. In het routeharnas kreeg elk van 41 routes de vier combinaties van wel of geen aanmelding en bekende of onbekende lengte. De grens was 1.048.576 bytes. Ook precies de grens is beproefd.

De routeproef en de HTTP-proef draaiden na integratie van de aanbevelingsmodule en de segmentroutes op bronstand `72fdc65ad5` met de dubbele controllerattributen verwijderd. Het verplichte routeattribuut draagt de transportlimiet. Op deze stand liepen alle 17 catalogustests en alle 471 tests van de pluginsuite door. De eerdere meetstand met 32 routes doorliep eveneens de volledige pluginsuite (453 tests). De generator leverde byte voor byte het gepubliceerde OpenAPI-bestand op. De gedeelde Python-client uit `plugin_proef.py` stuurde hetzelfde lichaam tweemaal naar een lokale HTTP-ontvanger. Die stelde op de draad één bekende lengte en één chunked-overdracht zonder lengtekop vast. In beide gevallen las de client de volledige testrespons. De JSON-driftcontrole omvat alle pluginroutes. De afzonderlijke serverroute `/media/v1/version` valt buiten de plugin.

De catalogustest toetst onder meer 423 bij afspelen, 429 met wachttijd en de 503-codes per afhankelijkheid. De healthproef zet een bron op 900 en 901 seconden en controleert de rangorde van de vier statussen, de reden van veroudering en het oudste tijdstip in het totaal. Zonder workercontrole meldt de connector `unknown`. De startproef weigert gedeclareerde eventnamen met twee of vier segmenten. De outbox controleert `ernst` en behoudt de opgegeven ernst bij inkorten van een grote payload.

De versie van ADR-0033 uit de oorspronkelijke stockproef blijft het uitgangspunt voor de herhaling. Het uitgebreide harnas meet ook chunked en de ingestelde basis-URL. De herhalingen op stock en de lokale fork en de volledige pluginproef op de fork hebben de uitkomst **NIET GEDRAAID (geen testslot)**. Tijdens de eigen wachtpogingen tussen 01.21 en 01.56 uur (CET) bleven de drie stacksloten bezet. Er is geen servercontainer voor deze herhalingen gestart.

De regisseur draagt de voorrang van 401 of 413 in contract §2.3 regel 9 en de centrale conformiteitsrij over aan ai-server-manager. Voor Δ-HUB-2 beschrijft ADR-0031 de indeling van onder meer `media.subtitle.rejected` en `media.quality_finding.detected`. NIET GEVALIDEERD (echte Hub): de Hub-inbox heeft deze events nog niet ontvangen; NIET GEVALIDEERD (echte NAS).
