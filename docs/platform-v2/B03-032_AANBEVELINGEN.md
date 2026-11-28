# Klassieke aanbevelingen en offline-evaluatie

De bestaande Similar-provider gebruikt dezelfde C#-engine als `jl-rec-eval`. De module staat standaard uit. De beheerder kan haar per bibliotheek en mediatype vooraan zetten in de volgorde voor *Meer zoals dit*. [Instellingen en terugval](B03-031_SIMILAR.md)

## Selectie en uitleg

De adapter controleert de bibliotheekmap met de vrager en gebruikt dat profiel ook voor de itemselectie. Hij leest films en series, de voor de vrager zichtbare collecties, de actuele kijkgegevens en de volgende aflevering. Kijkgeschiedenis, hervatposities, favorieten en spoorvoorkeuren blijven bij Jellyfin. De engine heeft geen eigen database.

De engine maakt TF-IDF-vectoren uit onder meer genres, tags, studio’s, personen, collecties, type en leeftijdsklasse. Het smaakprofiel weegt de huidige kijktoestand met een halfwaardetijd van 365 dagen. De vijf recentste positieve titels leveren een tweede inhoudsscore. Een persoonlijke rij sluit bekeken titels, series met een volgende aflevering, afgeschermde items en uitgesloten items of collecties uit. Bij *Meer zoals dit* telt vooral de overeenkomst met de bron. Een eerder bekeken vergelijkbare titel krijgt een lagere score.

MMR gebruikt λ = 0,7 en kiest hooguit twee items uit dezelfde serie of collectie. Het kijkverleden bepaalt de verdeling over film, serie en anime. Per tien persoonlijke resultaten is één plek bestemd voor exploratie. Bij een gelijkspel beslist de item-ID. De klok en het profiel bepalen de exploratiekeuze. Elke aanbeveling bevat uitleg uit eigen kijkgedrag of zichtbare metadata.

Bij minder dan drie positieve titels gaan gekozen onboardinggenres en de kenmerken van zichtbare onboardingtitels voor. Het huishoudsignaal vereist opt-in van de volwassen ontvanger én voldoende andere volwassen delers in hetzelfde huishouden. Standaard is het minimum drie. De engine heeft hiervoor invoerpunten. De huidige Similar-adapter leest de eigen Jellyfin-toestand. Opslag van persoonlijke feedback, het regelen van opt-ins en de publieke thuisrij volgen in latere stappen.

## Validatie en meetlat

Commit `16a1d0e94d` legde het rooster van gewichten en de keuzeregel vooraf vast. De laatste tien procent van de beoordelingen vóór T vormde de validatieperiode. De training, itemmetadata en populariteit kwamen uitsluitend uit de periode vóór V. Twaalf validatieprofielen en 7.667 films bepaalden de keuze. De winnende gewichten voor inhoud, overeenkomst met de vijf titels, kwaliteit en versheid zijn respectievelijk 0,60, 0,20, 0,10 en 0,05. [Protocol](test-evidence/b03-032-meetprotocol.json) · [Validatiecijfers](test-evidence/b03-032-gewichten.json)

Het harnas stuurt zichtbare rechten, metadata en trainingsgegevens naar de CLI. Het houdt de testantwoorden en de verborgen voorkeur zelf. JLT-10 gebruikt de volledige training, JLT-11 de laatste nul, één of twee interacties met huishoud-opt-in uit en aan. In de D-ML-simulatie zijn alle andere gebruikers mogelijke delers. De vergelijkingen gebruiken dezelfde gebruikers, kandidaatfilters, vaste klok en bootstrapseed. Het interval van het verschil met POP op de geschudde holdout controleert op lekkage. Series en anime worden uitsluitend synthetisch onderzocht.

Onderstaande opdrachten lopen vanaf de repowortel. `LOKAAL` is de eigen ketenmap voor testuitvoer buiten Git. `DSYN` wijst naar de opnieuw geverifieerde volledige synthetische set en `DML` naar het lokaal toegestane archief. `B03_LOCK_DIR` wijst naar de gedeelde map met het echte meetslot en `B03_WERK` naar de eigen werkmap voor tijdelijke testservers.

```sh
export PYTHONPATH=tools/b03-harnas
dotnet build tools/jl-rec-eval -c Release -o "$LOKAAL/cli"
CLI="$LOKAAL/cli/jl-rec-eval"
"$CLI" handvoorbeelden < tools/b03-harnas/tests/voorbeelden/f2-metrieken.json
python3 tools/b03-harnas/tests/cli_rookproef.py "$CLI"
python3 -m b03h eval-f2 valideer --dml-archief "$DML" --cli "$CLI" --uit "$LOKAAL/validatie.json"
python3 -m b03h eval-f2 functie --dsyn "$DSYN" --cli "$CLI" --uit "$LOKAAL/dsyn.json"
python3 -m b03h eval-f2 functie --dml-archief "$DML" --cli "$CLI" --uit "$LOKAAL/dml.json"
python3 -m b03h eval-f2 meet --dsyn "$DSYN" --dml-archief "$DML" --basis "$BASIS" \
  --voormeting "$VOORMETING" --cli "$CLI" --uit "$LOKAAL/stock-dml.json"
```

Voor D-SYN vervalt `--dml-archief` bij `meet`. `BASIS` is het definitieve S-P40-50-bewijs op de forkbasisdigest. `VOORMETING` bevat de eerdere stockruns van B03-030. De gate controleert beide vóór de vergelijking. Een stockherhaling buiten het interval van de eerste geldige voormeting stopt de meting vóór de engine aan de beurt komt. Ontbrekende invoer of overbelasting levert exitcode 3 op. De licentieguard controleert de checkout, het Git-bereik en de productie-image. [Meetuitkomst](test-evidence/b03-032-proeven.json)
