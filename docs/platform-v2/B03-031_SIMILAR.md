# Meer zoals dit voor films en series

De module **Aanbevelingen** voegt de lokale provider **Jelly Leon** toe aan de bestaande Jellyfin-route
`/Items/{itemId}/Similar`. Zet de module aan op de Jelly Leon-beheerpagina. Zet daarna per bibliotheek en
mediatype Jelly Leon bovenaan in de volgorde van Similar-providers om de selectie te gebruiken.
`Recommendations.Enabled` staat standaard uit. Binnen een actieve module kan `Recommendations.Similar.Enabled`
de provider afzonderlijk uitschakelen. De plugin wijzigt zelf geen bibliotheekopties.

Sinds B03-032 rangschikt de klassieke engine de films of series uit de toegankelijke bibliotheken van de vrager.
De metadata van het bronitem bepalen de overeenkomst. De eigen kijkgeschiedenis personaliseert de volgorde.
Al bekeken vergelijkbare titels krijgen een lagere score. De bron en eerder gekozen item-ID's vallen buiten
de selectie. Een ontbrekende gebruiker, afgeschermde bron of limiet van nul geeft een lege lijst.

De tijdslimiet is 300 ms. Bij een leesfout of een verstreken termijn krijgt de server een lege lijst en kan hij
de volgende provider proberen. De synchrone bibliotheeklezing van 12.4 kan nog uitlopen. Per providerinstantie
blijven hooguit twee lezingen tegelijk actief. Een derde verzoek valt meteen door naar de volgende provider.

De provider implementeert de twee lokale interfaces voor Movie en Series. De kernprovider blijft verantwoordelijk
voor `/Movies/Recommendations`. De klassieke engine staat volgens ADR-0029 in dezelfde plugin-DLL. [Werking en evaluatie](B03-032_AANBEVELINGEN.md)

## Proef op een wegwerpserver

`tools/jelly-leon/e2e/similar_proef.py` maakt acht films en twee series en vult twee testprofielen op stock 12.x.
De gewone plugin en de waarnemer starten na elkaar op kopieën van diezelfde configuratie. De proef vergelijkt het
Similar-responsschema inclusief verwijzingen en de aanbevelingsverzameling. Voor vier films per profiel vergelijkt
hij de kijkgegevens op stock, bij de pluginstart en na de leesproeven. Beide profielen hebben een ander hervatpunt
op dezelfde film. De acht afhankelijkheden
van upstream staan in `UPSTREAM_GEDRAG.md`, onder UG-F2-1 tot en met UG-F2-8.

Onderstaande commando’s gaan uit van de gepinde stock-image, een eigen proefmap, de vastgezette Playwright-installatie
onder `tools/b03-harnas/playwright` en Chromium. Voer containerproeven lokaal onder het gedeelde testslot uit.

```sh
dotnet build plugins/JellyLeon/src/Jellyfin.Plugin.JellyLeon/Jellyfin.Plugin.JellyLeon.csproj -c Release -o "$PROEF/plugin"
bash tools/jelly-leon/bouw_similar_proef.sh "$PROEF/waarnemer"
python3 tools/jelly-leon/e2e/similar_proef.py --image "$STOCK" --stock-image "$STOCK" \
  --plugin-map "$PROEF/plugin" --proef-plugin-map "$PROEF/waarnemer" --werkmap "$PROEF" --rapport "$PROEF/stock.json"
python3 tools/jelly-leon/e2e/similar_proef.py --image "$FORK" --stock-image "$STOCK" \
  --werkmap "$PROEF" --rapport "$PROEF/image.json"
```

De proefbouw bevat een teller bij de metadatalezing, een lezer die kan falen of twee seconden kan blokkeren, en een
waarnemer voor de reden van een bewaargebeurtenis. Alleen de expliciete bouwconfiguratie `SimilarProef` neemt deze
bron op. De analyzer van de proefbouw staat drie serverleden toe in de waarnemer. De Release-analyzertest
controleert dat de gewone bouw elk van deze toegangen weigert. De productie-image installeert de gewone
Release-DLL. Bij upstream-sync herhaalt de CI de volledige
voorraadvergelijking met de nieuwe runtime-digest.

Voor de eerdere prestatiebaseline gelden de beperkingen bij B03-030. NIET GEVALIDEERD (echte NAS): echte bibliotheek (JLT-15).
