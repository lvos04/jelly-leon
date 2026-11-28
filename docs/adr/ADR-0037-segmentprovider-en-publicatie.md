# ADR-0037 — Segmentprovider en gerichte publicatie

B03-071 gebruikt de publieke plugin-ABI van Jellyfin 12.4 en de bestaande pluginassembly. De vaste providernaam is `Jelly Leon Segmenten`. Jellyfin gebruikt daarvoor de GUID-weergave van de MD5 van de naam in kleine letters en UTF-16LE.

De server geeft een segment terug zonder provider-ID. De publicatieadapter vraagt daarom aan de manager welke providers geregistreerd zijn. Hij maakt voor één leesopdracht nieuwe bibliotheekopties die alle andere providers uitsluiten. De manager selecteert de eigen rijen in de database vóór de omzetting naar DTO's. De adapter vergelijkt type en grenzen en verwijdert uitsluitend rij-ID's uit die selectie. Elke nieuwe rij krijgt een nieuwe ID en de vaste eigen provider-ID. Dit blijft werken als twee providers dezelfde tijdcodes publiceren. De analyzer staat de twee schrijvende managerleden uitsluitend toe in deze adapter.

De extractietaak leest de gewenste publicatie uit `segments.db`. De beheerlaag bewaart kandidaten, menselijke bevestigingen en gewenste publicaties in die eigen database. De module staat bij installatie uit. Een hoofdstuk met een herkenbare naam levert een kandidaat op tot het begin van het volgende hoofdstuk of het einde van het item.

De online back-up bevat ook vastgelegde WAL-pagina's. Vóór een migratie controleert de opslaglaag de bron en de kopie. Alle openstaande schemawijzigingen vormen één transactie. Bij een fout blijven de vorige schemaversie en de opgeslagen correcties beschikbaar.

## Beheer en herstel

Zet de module aan via de moduleschakelaar. Stel een bibliotheek eerst in op `shadow` met een voorbeeld en bevestig de teruggegeven `preview_hash`. Na de scan geeft de itemroute met `view=candidate` de hoofdstukkandidaten. De eigen gepubliceerde set is op de gewone stockroute `GET /MediaSegments/{itemId}` zichtbaar. Alleen beheerders en aangewezen volwassen editors mogen kandidaten bekijken. De server controleert de bibliotheekrechten van het aangemelde account. Aangewezen accounts staan in `SegmentEditors` van de pluginconfiguratie.

Een publicatie naar `published` vraagt drie verschillende bevestigde afleveringen per serie en seizoen of een beheerder die de menselijke controle met reden vastlegt. Hints en onzekere intervallen blijven in review. De publicatie schrijft eerst de gewenste set en het nog uit te voeren werk transactioneel in de eigen opslag. Na onderbreking leest de module het verschil opnieuw bij de server. Schakelen naar `shadow` of `disabled` depubliceert de gekozen scope. De moduleschakelaar trekt bij uitschakelen alle eigen publicaties in. Na verwijderen van de plugin zonder vooraf uit te schakelen, kunnen eigen rijen in de serverback-up aanwezig blijven.

De hoofdstuklezer gebruikt de bibliotheek- en hoofdstukdienst van de server. Hij controleert de mediamount bij opstart, bij bibliotheekwijzigingen en elk uur. Een schrijfbare of onbekende mount blokkeert de analyse. Na een gewijzigde mtime blijven menselijke grenzen in review. Bij gewijzigd item-ID mag één passende externe identiteit binnen de bibliotheek en hoogstens één procent duurverschil het mensenwerk terug aan het item koppelen. Bevestiging of heruitlijning is nodig voordat het weer gepubliceerd kan worden. Ambigue verwijzingen blijven wees. Meer dan vijf procent of meer dan vijftig verdwenen items binnen een scan of uur bevriest het beheer en meldt een incident aan de outbox.

Bewaar een export van de segmentroute naast de serverback-up. De gewone Jellyfin-back-up bevat alleen de publicatiekopie. Import toont eerst conflicten en bindt de bevestigingshash vijftien minuten aan de beheerder en de dataversie. Na een herstart vervalt het voorbeeld. Bestaande afwijkende items veroorzaken een conflict. Herstelde kandidaten komen in schaduw. De gemeenschappelijke grens van 1 MiB uit ADR-0030 geldt ook voor de verzoekbody van deze route. De export kan per bibliotheek worden opgevraagd.

Handmatig opruimen vraagt een export van hoogstens 24 uur oud die nog overeenkomt met de geselecteerde items. De preview vermeldt hoeveel wezen worden verwijderd. Na ontdooien of wijzigen van de data is een nieuw voorbeeld nodig. Herstel een versie van `segments.db` met de bijbehorende pluginversie terwijl de testserver stilstaat. Het analysebestand per item hoort in `/cache/jelly-leon/segments/`; alleen dit afgeleide bestand wordt bij cacheverversing verwijderd.

## Controle op een gevulde wegwerpserver

De segmentproef start met twee gebruikers, een hervatpunt, afspeelvoorkeuren, hoofdstukken en een bestaande rij van een andere provider. Twee kopieën draaien op stock en een derde met de plugin. De proef legt de serverdatabase inclusief de WAL vast en verwijdert uit de meetkopie uitsluitend rijen met de vaste provider-ID. De uitslag vermeldt de namen van afwijkende of onvergelijkbare tabellen. Een vastgestelde afwijking tegenover de stockcontroles onderbreekt de vergelijking. Onvergelijkbare stockmetingen houden de poort open terwijl onafhankelijke scenario’s doorlopen. Een aparte synthetische MediaGuard-database bevat een vooraf bekende voortgangsrij.

De film doorloopt een bestandsvervanging, een containerwissel en verwijderen en terugzetten. Afzonderlijke wegwerpkopieën testen een goede en een mislukte migratie en het terugzetten van een officiële Jellyfin-back-up. Een gewijzigde favoriet dient als bewijs dat het herstel daadwerkelijk is uitgevoerd. De tests tellen bestaande vreemde rijen, controleren de wezen bij een verdwenen bibliotheekdeel en vergelijken de bestandshashes en wijzigingstijden van het corpus. Schrijfpogingen die al bij het openen worden afgewezen zijn niet met een bestandshash te tellen.

Voer de proef onder een gedeeld testslot uit, met een eigen werkmap en de vastgezette stockimage. Gebruik bij een stockimage met een los gebouwde plugin ook `--plugin-map` met de map van de release-DLL.

```sh
python3 tools/jelly-leon/e2e/plugin_proef.py --alleen-segmenten \
  --image "$FORK_IMAGE" --stock-image "$STOCK_IMAGE" \
  --werkmap "$PROEFMAP" --rapport "$PROEFMAP/jlt-56.json"
```
