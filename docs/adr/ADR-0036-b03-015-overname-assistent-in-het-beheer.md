# ADR-0036 — Overname uit Emby via het beheer van Jelly Leon

**Aanvaard.** De gebruiker koos op 2026-11-27 de interpreter van de analysewerker (optie a). Dit is het ontwerp voor B03-015 en C1.3-JL-05. S-P40-82 bouwt het scherm en wacht op de levering van de interpreter in S-G1-30.

## Runtime

De beheerpagina start de bestaande overnametool als apart proces. Zo gebruiken de assistent en de proefomgeving dezelfde doelcontrole, samenvoegregels, rapporten en herstelprocedure. De tool gebruikt alleen de standaardbibliotheek van Python. [Besluit over de tool](ADR-0025-b03-015-eigen-overnametool-niet-jellyplex-watched.md) · [Gereedschap en uitvoer per run](../../tools/emby-overname/README.md)

| Mogelijkheid | Gevolg voor bouw en onderhoud |
|---|---|
| **a. Interpreter van de analysewerker (gekozen)** | S-G1-30 levert de vastgezette Python-omgeving onder `/opt/jelly-leon/python`. S-P40-82 verpakt de bestaande tool bij die omgeving. Er is één interpreter om te testen, bij te werken en in de software-inventaris te volgen. |
| b. Kleine interpreter voor de overnametool | De assistent zou eerder kunnen worden ingebouwd. Een tweede runtime vergroot de image en vraagt eigen versiebeheer, inventarisatie en beveiligingsupdates. |
| c. Herschrijven in de plugin | De assistent zou zonder Python kunnen draaien. Koppeling, akkoord, journaal en rapportage zouden een tweede implementatie krijgen. Gelijk gedrag zou voor alle overnameproeven opnieuw aangetoond moeten worden. |

Bij dit besluit bevat de basisimage nog geen Python. Tot de omgeving uit S-G1-30 beschikbaar is, draait de tool alleen in de testomgeving en CI. S-P40-82 gebruikt ook de beheerpijplijn uit S-G1-14 en de geheimenmap uit S-G1-20. [Analysewerker en runtime](ADR-0017-b03-analysewerker-en-bestandspas.md)

## Verloop voor de beheerder

De pagina **Overname uit Emby** volgt de vormgeving van het Jellyfin-beheer. Ze toont de huidige stap, het resultaat van de laatste run en welke beslissing nog nodig is. De beheerder kan de pagina sluiten en later hetzelfde rapport openen.

| Stap | Wat de beheerder ziet en doet |
|---|---|
| 1. Inventaris | **Inventaris lezen** toont de Emby-versie, gebruikers, bibliotheken, paden en plugins (D07). Na de inventaris maakt de assistent met de exportfunctie van de tool een blijvend archief van de bron. De tool leest het terug en controleert de SHA-256. |
| 2. Droge proefrun | De beheerder opent de assistent eerst op de Jelly Leon-installatie die met de kopie van de datamap draait. **Proefrun starten** vergelijkt Emby met die installatie en maakt een plan met de verwachte doelwaarden. Beide mediaservers worden alleen gelezen. |
| 3. Rapport per gebruiker | Het scherm toont bronwaarde, verwachte doelwaarde en afhandellijst. Het vergelijkt gezien-status met datum en aantal, hervatpunten in ticks, favorieten, beoordelingen, spoorkeuzes, gebruikers, rechten en voorkeuren. Elk ongekoppeld item of verschil heeft een reden. Zo blijft ook een spoorkeuze zichtbaar die de officiële API niet kan overzetten. Een kind mag op het doel nooit meer zien dan in Emby. |
| 4. Akkoord op het plan | De beheerder beoordeelt elk verschil afzonderlijk en bevestigt het plan, ook bij nul verschillen. De vakjes beginnen leeg. De server koppelt het akkoord aan de inhoud van dit rapport én dit plan. **Overzetten** wordt pas beschikbaar nadat de server het volledige akkoord heeft gecontroleerd. |
| 5. Overzetten | Na de klik controleert de tool het doel, het actuele plan en het akkoord opnieuw. Hij schrijft uitsluitend via de officiële Jelly Leon-API, eerst op de kopie. Hij leest het resultaat terug en toont per gebruiker de werkelijke waarden vóór en na. |
| 6. Laatste delta | **Laatste delta voorbereiden** start een nieuwe droge proefrun voor de wijzigingen sinds de vorige overzetting. De beheerder doorloopt opnieuw de afhandellijst, geeft akkoord op dit plan en kiest **Overzetten**. Een nieuwere doelwaarde wordt volgens de samenvoegregels behouden of als verschil voorgelegd. |
| 7. Eindrapport | Het scherm toont het vóór/na-rapport van de laatste overzetting en vraagt opnieuw akkoord per verschil. Pas wanneer ieder bronitem verantwoord is en de tool dit eindakkoord met `akkoord-controle` heeft bevestigd, verschijnt **Overstap toegestaan**. Het rapport (JSON met SHA-256) en het bijbehorende akkoord blijven terug te lezen. |

De server bewaart het akkoord bij de run als `jelly-leon/emby-overname-akkoord/1`. Hij vult `akkoord_door` vanuit de beheerderssessie en `datum` vanuit de serverklok. `verschillen` bevat de individueel bevestigde verschil-ID's. Een akkoord van soort `plan` bevat `rapport_inhoud_sha256` en `plan_sha256`. Een akkoord van soort `cutover` hoort bij de inhoudshash van het eindrapport. Een ander rapport of een gewijzigd plan vraagt nieuw akkoord. De eigen installatie doorloopt dezelfde stappen bij de uiteindelijke overstap. Een akkoord uit de proef op de kopie wordt daarvoor niet hergebruikt. [Schema van het akkoord](../../tools/emby-overname/schemas/emby-overname-akkoord.schema.json)

## Toegang, proces en opslag

- Alleen een persoonlijke beheerderssessie van Jelly Leon krijgt toegang, ook voor het lezen van rapporten en afhandellijsten. De beheerpijplijn controleert dit op **elke** route. Een gewone gebruiker krijgt 403. De Hub en de AI hebben geen start-, lees- of akkoordroute. Een losse API-sleutel geldt niet als persoonlijke sessie.
- Onder `/media/v1/overname` lezen GET-routes de stand en het rapport met afhandellijst van een run. Muterende beheerroutes starten de inventaris, proefrun, overzetting of deltavoorbereiding en slaan een akkoord op. De server bepaalt welke overgang is toegestaan. Een herhaald verzoek met dezelfde idempotentiesleutel levert hetzelfde resultaat op. [Beheerpijplijn](ADR-0030-b03-017-foutcatalogus-pipeline-en-1-mib-per-route.md)
- De processtarter in `Core.Werker` gebruikt de gewone appgebruiker, een vast interpreterpad, het toolpakket uit de alleen-lezen image en een lijst van argumenten. Er is geen shell. Een exclusief slot laat één run tegelijk toe. Een tweede start toont de lopende run. Bij een tijdslimiet stopt de starter het eigen proces en geeft het slot pas vrij zodra dat is geëindigd. Na een onderbreking controleert de tool met zijn journaal welke goedgekeurde schrijfacties nog openstaan.
- De vaste werkmap is `/config/data/jelly-leon/overname/`. Onder `runs/` staan de rapporten en bronexports per run, onder `plannen/` de plannen en onder `staat/` de voortgang en het journaal. De server kiest de bestanden die bij de geselecteerde run horen. Het blijvende exportarchief valt onder de back-updekking van B12. [Opslag en gegevensbescherming](ADR-0020-b03-opslag-en-gegevensbescherming.md)
- De beheerder voert de Emby-sleutel en de Jelly Leon-sleutel in via afgeschermde invoervelden. Alleen de geheimenmap (0700) bewaart de waarden, elk in een bestand met modus 0600. De tool krijgt uitsluitend de vaste bestandspaden via `--emby-sleutel-bestand` en `--jl-sleutel-bestand`. De waarden komen nooit in XML, procesargumenten, antwoorden, rapporten, exports of logs. Het scherm toont bij teruglezen alleen of iedere sleutel is ingesteld.

## Doelcontrole en meldingen

Het doeladres komt uitsluitend uit de eigen Jelly Leon-installatie. Emby-instellingen en schermverzoeken kunnen het doeladres niet leveren of wijzigen. Vóór iedere overzetting controleert de tool het adres en leest hij zonder sleutel `GET /System/Info/Public`. Hij eist `ProductName` gelijk aan `Jellyfin Server`, een server-ID en een ander adres én een andere server-ID dan de bron. Bij exitcode 9 breekt de assistent de reeks af vóór enige schrijfactie op bron of doel. Er volgt geen delta of automatische herhaling.

Het scherm gebruikt vaste Nederlandse meldingen. Het geeft geen ruwe procesuitvoer terug. Alleen code 0 opent de volgende toegestane stap.

| Exitcode | Melding en vervolg op het scherm |
|---|---|
| 0 | Stap voltooid. Bekijk de uitkomst. |
| 1 of onbekend | De tool stopte onverwacht. Controleer de stand van de run. |
| 2 | De invoer is ongeldig. Controleer de ingevulde velden. |
| 3 | Het akkoord ontbreekt, is onvolledig of hoort bij een ander rapport. Open het juiste rapport en bevestig elk verschil. |
| 4 | Het plan is gewijzigd. Start een nieuwe proefrun en beoordeel het nieuwe plan. |
| 5 | De verbinding met een mediaserver is mislukt. Controleer de verbinding en de stand van de run voordat u hervat. |
| 6 | De controle is mislukt. Bekijk de open punten in het rapport. De overstap is geblokkeerd. |
| 7 | Een sleutel ontbreekt of het sleutelbestand is onvoldoende afgeschermd. Controleer de sleutelinstellingen. |
| 8 | De tool heeft een verzoek buiten de toegestane routes geweigerd. De run is gestopt. |
| 9 | Overname gestopt. Het doel is niet bevestigd als Jellyfin of is gelijk aan de bron. Er is niets in de mediaservers geschreven. Controleer de doelinstelling. |

Bij een onderbreking of tijdslimiet toont het scherm **Run onderbroken**. Na een begonnen overzetting kunnen al doelwaarden zijn bijgewerkt. De beheerder kan de stand en het journaal laten controleren en het goedgekeurde restant hervatten. Nieuwe acties vragen een nieuwe proefrun.

## Emby als terugval

Emby blijft beschikbaar met de oorspronkelijke kijkgeschiedenis. De tool doet alleen toegestane GET-verzoeken en slaat afspeelinformatie over bij een nog niet geanalyseerd bestand, om ook indirect schrijven te voorkomen. De bestaande Emby-koppeling van MediaGuard blijft werken. De voortgang blijft beschikbaar in de eigen database van MediaGuard. De assistent wijzigt geen media of databasebestanden.

De pagina toont **Emby verwijderen** als leeslijst. Alleen de gebruiker beslist later zelf over een proefstop en afzonderlijke verwijdering. De assistent kan Emby niet wijzigen, stoppen of verwijderen. Conform BG-22 gebruikt hij de Bazarr-vertaler niet en installeert hij geen Jellyfin-ondertiteldownloaders. [Procedure en controlelijst](../platform-v2/OVERNAME_EMBY.md)

S-P40-82 moet met testgegevens onder meer de 403 op elke route, het ontbrekende akkoord, de stop bij een verkeerd doel, uitsluitend GET naar Emby en de afwezigheid van sleutelwaarden aantonen. De vóór/na-rapporten via de beheerpagina moeten overeenkomen met die van de bestaande tool. De echte overname en de controlelijst horen bij JLT-74.
