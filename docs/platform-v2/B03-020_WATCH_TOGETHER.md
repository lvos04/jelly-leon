# B03-020 · Voormeting Watch Together

Het harnas vergelijkt twee stockprofielen op de vastgezette Jellyfin 12.4-image van B03-016. De meetpoging van 27 november 2026 heeft de status **NIET GEMETEN (machinelast)**. De definitieve S-P40-50-baseline ontbrak en de éénminuutslast was 12,13 bij een grens van 4,00. Het bestand bevat nul prestatiemetingen. [Meetpoging](test-evidence/b03-020-meetpoging.json)

## Meten op de ontwikkelmachine

Gebruik de Python-omgeving, de Playwright-versie van het harnas en het lokale testcorpus uit B03-016. Zet `B03_WERK`, `B03_UITVOER` en `TMPDIR` op absolute paden in de eigen ketenmap. `B03_CORPUS` wijst naar het alleen-lezen mediacorpus en `B03_LOCK_DIR` naar de gedeelde testsloten. De shellvariabele `SLOT` verwijst naar de gedeelde `stackslot`-wrapper. [Installatie van het harnas](B03-016_HARNAS.md)

```sh
export PYTHONPATH=tools/b03-harnas
"$SLOT" nice -n 10 "$PY" -m b03h corpus maak f1-framecode --schaal vol --bevries
STACKSLOTEN=1 "$SLOT" nice -n 10 "$PY" -m b03h watchtogether \
  --baseline "$BASIS" --desktopbouw "$DESKTOPBOUW" --desktop-image "$DESKTOPIMAGE" \
  --label definitief-forkbasis --runs 5 --uit "$BEWIJS/b03-020.json"
```

`BASIS` is het definitieve S-P40-50-meetbestand voor beide stockprofielen. `DESKTOPBOUW` bevat de uitvoerbare `build/src/jellyfin-desktop` van S-P40-90. Gebruik de bijbehorende Xvfb-runtime als `DESKTOPIMAGE`. Het harnas maakt zijn eigen stockserver, testgebruikers en netwerk. Het koppelt de vier afspeelbestanden alleen-lezen. Voor bronnen korter dan 370 seconden herhaalt het de oorspronkelijke pakketten met stream-copy, zodat het vijfminutenvenster past. Het legt de bronhash en de hash van ieder afspeelbestand vast. Voor de framecode controleert het ook de grondwaarheid en de video tegen het bevroren SHA-256-manifest. [Framecodemanifest](test-evidence/b03-016-corpus/f1-framecode.v1.vol.manifest.json)

De volledige framecode is voor deze stap opnieuw gegenereerd. De twee bestanden (55.801.725 bytes samen) gaven bij de bevriezingscontrole exact dezelfde sethash als het bestaande manifest. Ook de afzonderlijke SHA-256-controle van beide bestanden gaf nul fouten.

Het meetvenster sluit de overige stacksloten uit. De startcontrole en elke run gebruiken een lastgrens van maximaal vier. Een afgewezen poging schrijft een apart bestand met het achtervoegsel `-meetpoging.json`. De opdracht geeft exitcode 3 bij uitstel en 1 bij een meetfout. Een fout in de client of in de kalibratie blijft als fout zichtbaar. Voltooit de matrix, dan schrijft het harnas een baselinebestand en de ruwe sporen in een bijbehorende map.

## Scenario’s

| Scenario | Deelnemers en proef | Controle in het harnas |
|---|---|---|
| S1 | Twee verschillende kijkers, Chromium en Firefox, met Hero via loopback | Beide actieve sessies melden Direct Play |
| S2 | Firefox en Chromium met de 1080p HEVC 10-bit-testclip | Precies één videotranscode bij Chromium en een nieuwe QSV-encoderlog. De eerste 30 s vallen buiten de driftstatistiek |
| S3 | Hero met alleen de tweede client achter een afzonderlijke TCP-doorvoer | `tc netem` in de eigen containernetwerkruimte, 80 ± 20 ms en 1% verlies. De qdisc wordt teruggelezen. Bij ontbrekende ondersteuning krijgt S3 een reden |
| S4 | Chromium en de echte desktop onder Xvfb met de bevroren framecode | Framenummer uit het Xvfb-scherm en gelijktijdige browserpositie. De desktoprooktest van S-P40-90 bepaalt of deze combinatie beschikbaar is |
| S5 | Firefox en een Chromium-deelnemer met Sintel 1080p | Alleen de download van Chromium wordt begrensd tot 1,5 Mbit/s. De referentieclient meet de groepsstilstand |

Voor S3 probeert het harnas eerst de netwerkruimte van een aparte proefcontainer. Ontbreekt `tc` in de stockimage, dan kan het harnas de lokale Linux-programma’s `tc` en `sleep` met hun bibliotheken in een tijdelijke image verpakken. De tarhash en het image-ID staan bij de waarneming. Met `--netem-image` kan ook een eigen testimage op digest worden meegegeven. De netwerkproef verandert uitsluitend de eigen containerinterface. In een afzonderlijke proef zijn de ingestelde 80 ± 20 ms en 1% verlies teruggelezen en gaf een HTTP-aanvraag door de vertraagde verbinding 200. [Netem-proefcontainer](test-evidence/b03-020-netemproef.json)

Elk scenario gebruikt minstens vijf onafhankelijke runs per stockprofiel van vijf minuten. De volgorde wisselt per ronde. Beide profielen krijgen dezelfde handmatige QSV-serverinstellingen. Stock-best krijgt per apparaat de vijf SyncPlay-waarden uit het profiel. Iedere run krijgt nieuwe gebruikers en aparte clients. [Stock-bestprofiel](../../tools/b03-harnas/profielen/stock-best.json)

## Kalibratie en interpretatie

- Twee lezers bemonsteren dezelfde lopende sessie in Chromium en Firefox. Het harnas vergelijkt hun mediaklok na correctie voor het leestijdstip. Een maximale fout boven 20 ms onderbreekt de vergelijking voor S1.
- Een bekende klok tekent zestien binaire blokken bij 24000/1001 beelden per seconde. Het harnas leest de framecode uit een Playwright-screenshot, het echte Xvfb-framebuffer en de uitvoer van `adb exec-out screencap` in een eigen telefoonemulator. De Android-meetklok is een lokale test-app zonder permissies. Iedere opname heeft een tijdstempel vóór en na de opname. Een fout boven 100 ms sluit die opnamemethode uit voor de driftbeoordeling.
- Iedere ruwe run bevat gekoppelde posities en tijden, belasting, CPU, datum en de afspeelpaden. Minder dan 10 Hz, een lang gat, een teruggedateerd start-event of een ontbrekende deelnemer maakt het spoor onbruikbaar. De hervatduur loopt van de groepsopdracht tot het laatste `playing`-event. Bij de native desktop geldt het eerste voortschrijdende rasterbeeld na hervatten, bemonsterd op 20 Hz.
- Het harnas berekent per run de absolute drift op een gemeenschappelijk tijdstip. Over de runs rapporteert het de gemiddelde p50 en p95, het waargenomen maximum, de p95-hervatduur en de groepsstilstand in milliseconden. De 95%-bootstrap trekt hele runs met vaste seed. De stockvoormeting bevat geen winstclaim voor Jelly Leon.

## Rollen en upstream-regressies

De functionele proef kan los van de prestatiebaseline draaien en herkent het geërfde gedeelde stackslot. De opdracht geeft exitcode 1 bij een stockafwijking of een onderbroken proef. De waarnemingen staan in het rapport.

```sh
"$SLOT" nice -n 10 "$PY" -m b03h watchtogether \
  --functieproef --uit "$BEWIJS/b03-020-functieproef.json"
```

Voor een bekende testgroep vraagt elke rol de lijst en het groepsdetail op. Het bewijs telt groepen en unieke deelnemersnamen. De eigenaar en het lid vormen de positieve controle. De testrol zonder SyncPlay-recht moet een weigering krijgen. In dezelfde groep meet het harnas met een tijdelijk toegangsschema of een actief lid binnen 90 s verdwijnt.

Op de lokale stockserver zagen gast en kind op beide routes elk één groep met twee deelnemersnamen. De rol zonder SyncPlay-recht kreeg tweemaal HTTP 403. Buiten het toegangsschema kreeg het actieve lid ook HTTP 403 voor de groepslijst terwijl de eigenaar dit lid na 91,51 s nog in de groep zag. De stockimage bevatte geen uitvoerbare `tc` (exit 127). De eerste browserproef brak af voordat de browserresultaten werden weggeschreven. [Functionele meetpoging](test-evidence/b03-020-functieproef.json)

In de tweede proef met Firefox en Chromium startte de tweede deelnemer niet (#17351). Acht afspeelproeven die twee spelende deelnemers vereisen, hebben daardoor geen uitkomst. Toen beide vensters sloten, zag de onafhankelijke waarnemer bij de eerste controle na 53,24 ms geen deelnemers meer (#17352). Het actieve lid bleef bij de afzonderlijke schemaproef na 91,41 s zichtbaar. Het harnas heeft de netem-instellingen in zijn eigen tijdelijke proefimage toegepast en teruggelezen. [Tweede stockproef](test-evidence/b03-020-browserproef.json)

De browsertests controleren starten en synchronisatie (#17351, #16241), versie- en spoorkeuze (#18422, #16964), HLS-segmenten na een seek (#17654), groepsopruiming (#17352), updates na verlaten (#8727), het volgende wachtrij-item (#8690) en aantal en positie van Ready-meldingen (#8408, #8396). Een ontbrekende tweede versie of ontbrekende HLS-waarneming krijgt een eigen reden. S4 registreert de Ready-positie van de desktop na een groepsseek voor #1290.

De versieproef gebruikt twee versies van dezelfde serieaflevering met meerdere audio- en ondertitelsporen. De test kiest de andere versie en vergelijkt de bron- en spoorselectie met de actieve serversessie. De HLS-proef volgt de segmentantwoorden van Chromium bij twee groepsseeks in de HEVC-testclip. Voor de opruimproef sluiten beide ingelogde browsers hun venster terwijl ze nog in de groep zitten. Een afzonderlijke waarnemer controleert tot 30 s of de groep verdwijnt. [Alternatieve aflevering](https://github.com/jellyfin/jellyfin/issues/18422) · [Groep na sluiten van vensters](https://github.com/jellyfin/jellyfin/issues/17352)

De Android-proef opent de officiële telefoonapp in een eigen emulator onder het Gradle-slot. Met `--android-apk` kan de vastgezette APK van B03-016 worden meegegeven. De app voegt zich bij een al spelende Chromium-groep. Het harnas volgt beide afspeelposities gedurende 45 s en controleert of de server een Ready-timeout aan deze specifieke Android-sessie toeschrijft. Bij ontbrekende emulator of APK vermeldt het bewijs de reden. [Upstreammelding over Android Ready](https://github.com/jellyfin/jellyfin/issues/18121)

NIET GEVALIDEERD (hardware): A310, UHD 770 en echte tv's; NIET GEVALIDEERD (Mac/Xcode): Swiftfin; NIET GEVALIDEERD (echte NAS).
