# B03-030 · Voormeting aanbevelingen

Het commando `b03h baseline-f2` meet stock op de vastgezette 12.4-digest. De drempels voor de latere engine staan in de preregistratie. De onafhankelijke beoordeling van het D-SYN-recept hoort bij G-F2-0, vóór iemand gewichten op de validatiesplit afstelt. [Preregistratie](test-evidence/b03-030-preregistratie.json)

## Lokale uitvoering

Draai vanuit de eigen kloon met de testomgeving van de repo op het zoekpad. Kies voor `WERK` een eigen map buiten Git. `SLOT` is het pad naar de gedeelde stackslot-wrapper. `B03_LOCK_DIR` is de map met de gedeelde sloten. `BASIS` verwijst naar het definitieve meetbewijs van S-P40-50. De voorcontrole vraagt beide stockprofielen op de forkbasisdigest, elk met minimaal drie geldige runs en een interval.

```bash
export PYTHONPATH=tools/b03-harnas
export B03_CORPUS="$WERK/lege-bron" B03_UITVOER="$WERK/testsets" B03_WERK="$WERK/servers"
mkdir -p "$B03_CORPUS" "$WERK/rapporten"
"$SLOT" nice -n 10 python -m b03h corpus maak f2-dsyn --schaal vol --bevries
DSYN="$B03_UITVOER/f2-dsyn-v1-vol-s20261109"
python -m b03h corpus controleer "$DSYN"
python -m b03h baseline-f2 dml --map "$WERK/dml" --dsyn "$DSYN" --uit "$WERK/rapporten/dml.json"
python -m b03h baseline-f2 lekproef --dsyn "$DSYN" --uit "$WERK/rapporten/lek-dsyn.json"
python -m b03h baseline-f2 lekproef --dml-archief "$WERK/dml/ml-latest-small.zip" --uit "$WERK/rapporten/lek-dml.json"
STACKSLOTEN=1 "$SLOT" nice -n 10 python -m b03h baseline-f2 meet --basis "$BASIS" --dsyn "$DSYN" --uit "$WERK/rapporten/stock-dsyn.json"
STACKSLOTEN=1 "$SLOT" nice -n 10 python -m b03h baseline-f2 meet --basis "$BASIS" --dsyn "$DSYN" \
  --dml-archief "$WERK/dml/ml-latest-small.zip" --uit "$WERK/rapporten/stock-dml.json"
python -m b03h corpus opruimen "$DSYN"
```

Exitcode 3 bij `meet` betekent dat een meetvoorwaarde ontbrak. Het uitvoerbestand bevat de reden en het aantal geldige runs. De controle gebeurt vóór en na het verkrijgen van het exclusieve slot. Tijdens de scan en de twee runs gelden ook de lastcontroles van het gemeenschappelijke harnas. Het harnas verwijdert de eigen server, databases en tijdelijke D-ML-stubs bij het verlaten van de proef. Verwijder na gebruik ook het gedownloade archief uit de eigen werkmap. Alleen geaggregeerde cijfers en controlesommen horen in het bewijs.

## Datasets

**D-SYN** gebruikt het bevroren recept met 240 films, 20 series met elk drie afleveringen en zes gebruikers uit drie huishoudens. Dit levert 300 mediastubs van één seconde en 260 kandidaten. De SHA-256 omvat ook de NFO's, grondwaarheid en huishoudens. De klok T is de al vastgelegde eerste achtergehouden interactie per profiel. De voorkeuren komen uit genres en tags die ook in de NFO's staan. Voor het kind geldt de leeftijdsgrens uit het recept. De technische beoordeling van dit recept staat open. [Bevroren manifest](test-evidence/b03-016-corpus/f2-dsyn.v1.vol.manifest.json)

**D-ML** gebruikt de onderzoeksversie van `ml-latest-small` uit de officiële GroupLens-distributie. De downloader controleert de vaste SHA-256 vóór de atomaire hernoeming. Alleen films met een beoordeling vóór T krijgen een stub. De NFO bevat de vaste genres, tags van vóór T, de eerste beoordeling als toevoegdatum en het gemiddelde van uitsluitend eerdere beoordelingen op de tienpuntsschaal. Alle gebruikers tellen mee voor populariteit. De evaluatie gebruikt de profielen met minstens vijf eerdere positieven en twee verschillende, ongeziene positieve films daarna binnen de catalogus. De grens voor een positieve beoordeling is 4,0. Interacties exact op T tellen aan geen van beide kanten mee. Beperkte NFO's dragen de licentiemarkering. De guard kent de hashes van het archief en de vier CSV-tabellen.

Het splitmoment is de eerste hele seconde waarop het grootste aantal gebruikers aan de tijdseisen voldoet. Elke gebruiker telt mee vanaf één seconde na de vijfde positieve beoordeling tot exclusief de voorlaatste positieve beoordeling. De overlap van deze intervallen levert een bovengrens op, onafhankelijk van de metadatakwaliteit of het aanbevelingssysteem. Voor de vastgelegde archiefversie is deze bovengrens 30. Na de cataloguscontrole blijven er 29 over. De eis voor M1 blijft 100. De offline lekproef mag ook bij een kleinere groep de werking van de meetlat toetsen.

## Stockroutes en kandidaten

De scan moet elk verwacht corpus-ID precies één keer vinden, met dezelfde genres en hetzelfde type. Bij D-ML vergelijkt de proef ook de toevoegdatum, tags en waardering. Elke synthetische gebruiker krijgt een eigen lokale sessie. Na het zaaien en na de twee runs leest het harnas alle zichtbare films en series, Played-vlaggen, favorieten en speeldatums van films terug. Afwijkingen breken de proef af. De MediaGuard-koppeling en Emby hebben geen rol in deze opstelling.

| Systeem | Ranglijst vóór het gemeenschappelijke filter |
|---|---|
| S-REC | Categorieën uit `/Movies/Recommendations`, om beurten één item uit elke lijst |
| S-REC-best | Beste afzonderlijke RecommendationType over het hele cohort, voor elke kwaliteitsmetriek afzonderlijk |
| S-SIM | Lokale `/Items/{id}/Similar` voor de drie laatst bekeken titels, om beurten samengevoegd |
| S-LAT | `/Items/Latest` voor films en series |
| S-RND | `/Items/Suggestions` voor hetzelfde profiel |
| POP | Aantal kijkinteracties vóór T, daarna corpus-ID bij gelijke aantallen |
| S-TMDB | Niet gemeten. De remote provider vraagt netwerkverkeer naar TMDb |
| S-BEST | Maximum per kwaliteitsmetriek over S-REC, S-REC-best, S-SIM, S-LAT en, indien gemeten voor alle gebruikers, S-TMDB |

Elk systeem krijgt hetzelfde filter op film of serie, toegang, bekeken items en herhaling van een ID. Pas daarna kapt het harnas af op tien. Selectie van de beste categorie en S-BEST vindt plaats op de hele testgroep. ILD en coverage voor deze twee samengestelde rijen volgen de winnaar voor NDCG. Zonder S-TMDB geeft het rapport `volledig: false` bij S-BEST. Een winstclaim tegen de volledige stockconfiguratie vraagt ook die meting.

## Meetlat en lekbewaking

NDCG@10 deelt de som van de gedisconteerde treffers door de ideale score voor dezelfde binaire holdout. Recall@10 deelt het aantal treffers door de omvang van die holdout. Coverage deelt het aantal verschillende aanbevolen items over alle gebruikers door de catalogusgrootte. ILD is de gemiddelde paarsgewijze afstand `1 − Jaccard(genres)` binnen de lijst. Twee lege genresets hebben afstand nul. Bij minder dan twee items is de afgesproken ILD nul.

In het handvoorbeeld staan treffers op plaats 1 en 3, met drie relevante items. De DCG is 1,5 en de ideale DCG is circa 2,13093. Dit geeft NDCG 0,703918 en recall 2/3. De genreafstanden 1/2, 1 en 1/2 geven ILD 2/3. Drie unieke aanbevelingen uit vijf films geven coverage 3/5. De toekomstige .NET-CLI van S-G2-22 moet dezelfde JSON-voorbeelden lezen. [Gedeelde handvoorbeelden](../../tools/b03-harnas/tests/voorbeelden/f2-metrieken.json)

Elke stockrun rapporteert n, NDCG, recall, coverage en ILD. Het rapport bevat per metriek het absolute verschil tussen de twee runs. De intervallen voor NDCG, recall en ILD gebruiken 1000 bootstrapsteekproeven over gebruikers met seed 20261109. Verschillen met POP gebruiken één gepaard verschil per gebruiker. De lektest geeft elke gebruiker de holdout van een andere gebruiker. Een onafhankelijke loting en een bewust van de omgewisselde antwoorden voorziene ranglijst controleren beide kanten van de toets. Voor F2 geldt later dat de 95%-ondergrens van de geschudde NDCG van F2 min POP hooguit nul mag zijn.

De functieproef herhaalt B1–B8 en B10 met aparte synthetische profielen op D-SYN, inclusief de 404 voor een verborgen titel en vijftien latentiemetingen per route. B9 en B11 zijn broncontroles. De eerdere functionele cijfers op een andere bibliotheek blijven een afzonderlijke voormeting. G-F2-2 herhaalt stock op de exacte forkbasisdigest.
