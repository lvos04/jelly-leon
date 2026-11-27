# B03-016-harnas — corpusgenerator, clientmatrix en baselines van stock Jellyfin

Gereedschap voor de **ontwikkelmachine en CI** (nooit op de NAS, nooit in de Jelly Leon-image). Besluit en motivatie:
`docs/adr/ADR-0026-b03-016-harnas-corpus-clientmatrix-baseline.md`; procedure en uitkomsten:
`docs/platform-v2/B03-016_HARNAS.md` en `docs/platform-v2/BOUWVERIFICATIE_B03-016.md`.

| Onderdeel | Ingang | Wat |
|---|---|---|
| corpusgenerator | `python -m b03h corpus …` | recepten F1–F6 + ASS + groot bestand, grondwaarheid, sha256-manifest, bevriezen, opruimen |
| CI-guard | `python -m b03h guard --git . / --bereik . A..B / --image REF / --map DIR` | weigert beperkt gelicentieerde testdata (BG-37) en media in de repo |
| baselines | `python -m b03h baseline --metingen dp,orakel,transcode,functies --runs 3` | stock-standaard en stock-best, meetprotocol, n + Wilson |
| aanbevelingen | `python -m b03h baseline-f2 dml/lekproef/meet …` | Bevroren catalogus, gepaarde evaluatie en twee stockruns. [Meetprocedure B03-030](../../docs/platform-v2/B03-030_AANBEVELINGEN.md) |
| clientmatrix | `python -m b03h clientmatrix --onderdelen web,ua,webdir,legacy,telefoon,tablet,tv,tv36` | rooktest hero.mp4 per client |
| controle-run | `python -m b03h diffrun [--negatieve-proef] [--toegestaan module.json]` | stock tegen stock (of Jelly Leon) op kopieën van één datamap |
| legacy-client | `python -m b03h legacy --uit …` | wat 12.x doet met X-Emby-Token, api_key, … |
| desktop-spike | `python -m b03h desktop [--stap bouw\|draai\|alles]` | jellyfin-desktop 2.0.0 (bron uit jelly-leon-clients, alleen-lezen) onder Xvfb, ruwe CDP (`desktop/cdp.mjs`); Geblokkeerd zonder geslaagde spike |
| rapport | `python -m b03h rapport <baseline.json>` | baselinebewijs als Markdown-tabel |

Voorbereiden (eenmalig, niets committen):

```bash
cd tools/b03-harnas/playwright && npm ci     # Playwright 1.63.0 (browsers: npx playwright install chromium firefox webkit)
python3 -m venv ../jelly-leon/.venv          # of de bestaande venv van tools/jelly-leon (pytest, ruff)
```

Regels (bouwplan §10.13–§10.15, analyse 5 §7):

- Het corpus (`<WERKMAP>/.lokaal/media-corpus`) wordt **alleen-lezen** gekoppeld; afgeleide sets komen in
  `.lokaal/jelly-leon-b03-016/testsets/` en worden na gebruik opgeruimd (`corpus opruimen`); alleen recept en bevroren
  manifest blijven (BG-38).
- Metingen alleen in het **exclusieve meetslot** (`stack.lock`); een run met loadavg(1 min) > 4, met andere processen > 4
  kernen of met een actieve docker-build/Gradle is **ongeldig** (niet mislukt). Emulators onder `gradle.lock`, binnen
  `stack.lock`, één tegelijk, 4 GiB.
- GPU alleen via `--device /dev/dri/renderD128 --group-add <render-gid>`, KVM via `--device /dev/kvm`; nooit
  `--privileged`, nooit de Docker-socket in een testcontainer; alles op 127.0.0.1.
- Tests: `python -m pytest -q tools/b03-harnas/tests` (synthetisch mini-corpus met de host-ffmpeg; geen netwerk);
  lint: `ruff check --config tools/b03-harnas/ruff.toml tools/b03-harnas`.

## JLT-40 — meetcommando winstmeting apparaatprofielen

Voer de opdrachten uit vanuit de repo. Zet `B03_CORPUS` op het lokale testcorpus, `B03_WERK`, `TMPDIR` en
`B03_UITVOER` op eigen mappen in de ketenmap en `B03_LOCK_DIR` op de gedeelde map met `stack.lock`.
Gebruik de Python 3.12-omgeving van de forktools. Maak de sets met de vastgezette ffmpeg uit het corpusrecept.

```bash
export PYTHONPATH=tools/b03-harnas
"$B03_LOCK_DIR/stackslot" nice -n 10 python3.12 -m b03h corpus maak f5-fouten --schaal vol --bevries
"$B03_LOCK_DIR/stackslot" nice -n 10 python3.12 -m b03h corpus maak ass --schaal vol --bevries
```

`B03_BASIS` wijst naar het JSON-rapport van de definitieve S-P40-50-sessie. Zet `B03_FORK_IMAGE` op het lokale
image-ID van de te vergelijken golf-4-bouw. Het harnas zet Devices aan op een eigen wegwerpserver en leest de
schakelaar terug. De drie systemen wisselen elkaar af. Per geval start de webclient tweemaal met dezelfde
apparaatidentiteit. De A5-matrix, ToS/BBB, elf formaatgevallen, ASS, tekst-SRT en de bevroren testset krijgen eigen
noemers. De twee recepten en alle gebruikte mediabestanden worden vóór de sessie op SHA-256 gecontroleerd.

```bash
STACKSLOTEN=1 "$B03_LOCK_DIR/stackslot" nice -n 10 python3.12 -m b03h apparaten \
  --basis "${B03_BASIS:?definitieve S-P40-50-baseline vereist}" --sets "$B03_UITVOER" --split testset \
  --fork-image "${B03_FORK_IMAGE:?lokaal image-ID van de fork vereist}" --runs 3 \
  --uit docs/platform-v2/test-evidence/jlt-40-apparaatprofielen.json
```

Dit schrijft ook `jlt-40-apparaatprofielen.md`. In S-P40-64 draait dezelfde ingang met `--split beide`, de twee
stockprofielen en als uitvoer `b03-060-voormeting.json`. Laat daarvoor `--fork-image` weg. Een ontbrekende
definitieve baseline of te hoge startlast geeft exitcode 1 en een rapport met de reden. De devset blijft apart van
de testset bij het berekenen van de tellers. De emulator- en desktopresultaten voor JLT-40 komen uit S-G4-30.

De voormeting voor Watch Together draait met twee afzonderlijke SyncPlay-clients. [S1–S5, kalibratie en rollenproef](../../docs/platform-v2/B03-020_WATCH_TOGETHER.md)

## JLT-50 — winstmeting segmenten op de bevroren testset

B03-070 gebruikt de ingang `python -m b03h segmenten`. De meetlat staat bij de bestaande corpusgenerator, stockserver en statistiek in `tools/b03-harnas/b03h/`. Het bouwplan noemde hiervoor `tools/jelly-leon/segments-eval`. S-G2-42, S-G2-44 en S-G4-48 gebruiken hetzelfde manifest en dezelfde telregels.

### Testset en meetcommando

Voer de opdrachten uit vanaf de repo-root. `WERKMAP` wijst naar de lokale platformwerkmap en `KETEN` naar de eigen ketenmap. `BASIS` is het definitieve JSON-bewijs van S-P40-50 op de forkbasis. `JL_PROEF` is de naam van een eigen lokale wegwerpcontainer met F6. De testbibliotheken hebben uitsluitend de twee alleen-lezen-mediamounts `$SET/series:/media/f6/series:ro` en `$SET/films:/media/f6/films:ro`. Gebruik het containerlabel `org.jelly-leon.proef=jlt50`, een dynamische lokale poort en de synthetische beheerfixture van `b03h.stock`. De F6-analyse en publicatie van de testset moeten voltooid zijn. De lezer controleert de onderliggende stock-imagelagen, de mediamounts en elk bibliotheekitem.

```bash
export PYTHONPATH=tools/b03-harnas
PY=tools/jelly-leon/.venv/bin/python
export B03_CORPUS="$WERKMAP/.lokaal/media-corpus"
export B03_LOCK_DIR="$WERKMAP/.lokaal" B03_WERK="$KETEN/jlt50" B03_UITVOER="$KETEN/testsets"
SLOT="$WERKMAP/.lokaal/stackslot"
SET="$B03_UITVOER/f6-segmenten-v2-vol-s20261127"
BEWIJS=docs/platform-v2/test-evidence/b03-070.json
VAST=$(jq -er '.manifest_sha256' "$BEWIJS")
IS_PAKKET="$KETEN/intro-skipper-v12.0.8.0.zip"

df -h "$KETEN"
"$PY" -m b03h segmenten bronscheiding
"$SLOT" nice -n 10 "$PY" -m b03h corpus maak f6-segmenten --versie 2 --schaal vol --seed 20261127 --bevries
"$PY" -m b03h corpus controleer "$SET"
"$PY" tools/b03-harnas/tests/herhaal_segmenten.py "$SET" "$VAST"

"$SLOT" nice -n 10 "$PY" -m b03h segmenten spike --intro-pakket "$IS_PAKKET" --uit "$KETEN/s-is.json"
STACKSLOTEN=1 "$SLOT" nice -n 10 "$PY" -m b03h segmenten meet \
  --set "$SET" --manifest-sha256 "$VAST" --baseline "$BASIS" --runs 3 \
  --profielen stock-standaard,is-standaard,is-ruim,jelly-leon \
  --intro-pakket "$IS_PAKKET" --spike-bewijs "$KETEN/s-is.json" --jelly-container "$JL_PROEF" \
  --poort --uit "$KETEN/jlt50.json"

"$PY" -m b03h corpus opruimen "$SET"
```

Het pakket voor S-IS is het ongewijzigde release-zipbestand. Het harnas controleert de pakket-SHA256, de actieve pluginversie en de zichtbaarheid van segmenten op acht synthetische ontwikkelitems. Alleen de laadproef gebruikt deze items. De twee IS-profielen gebruiken de standaardinstellingen (25%, maximaal 10 minuten) en het ruimere venster (50%, maximaal 20 minuten). Elk profiel krijgt een eigen tijdelijke stockserver op de vastgezette 12.x-digest. Er wordt geen externe segmentdatabase gekoppeld. [Intro Skipper-release 12.0.8.0](https://github.com/intro-skipper/intro-skipper/releases/tag/12.0%2Fv12.0.8.0)

Voor alleen baseline (a) gebruikt dezelfde opdracht `--profielen stock-standaard` zonder de opties voor IS, Jelly Leon of de eindpoort. Voor S-G2-42 en S-G2-44 geeft `--profielen jelly-leon --schaduw --jelly-container "$JL_PROEF"` de kandidaten in schaduwmodus. Laat daarbij `--poort` weg. In publicatiemodus vergelijkt het harnas de multiverzamelingen van type, begin- en eindtick uit `GET /media/v1/segments/{itemId}?view=candidate` en `GET /MediaSegments/{itemId}`. Een onvolledige analyse, een ontbrekend item of een afwijkende tick breekt de meting af.

### Vooraf vastgelegde drempels

Per aflevering en type telt een label hoogstens één keer en een voorspelling hoogstens één keer. Een match vereist IoU ≥ 0,5. Precisie en recall krijgen een tweezijdig Wilson-95%-interval. F1 is het harmonisch gemiddelde, berekend uit de gezamenlijke tellingen. Bij nul voorspellingen blijft precisie onbepaald. Een lege bibliotheek levert geen meting op.

| Type | Streef-n | Ondergrens precisie | Ondergrens recall | Grensfout p95 |
| --- | ---: | ---: | ---: | --- |
| Intro | 60 | 0,90 | 0,80 | ≤ 1,5 s voor begin- en eindfouten samen |
| Outro | 60 | 0,90 | 0,75 | ≤ 2,0 s voor de eindfout |
| Recap | 40 | 0,85 | 0,65 | — |
| Preview | 30 | 0,80 | 0,50 | — |
| Intro na het zoekvenster en seizoensvariant, elk afzonderlijk | 20 | — | 0,65 | — |

Het rapport geeft per type de mediaan en p95 van de absolute grensfout, het aandeel binnen één seconde en scores per augmentatie. Onder de streef-n luidt het resultaat `smoke-gate (n = …)`. Drie afwisselende runs lezen dezelfde afleveringen. Het rapport vermeldt de belasting rond iedere uitleesrun en telt elke aflevering één keer voor n. De vergelijking met elk IS-profiel gebruikt 10.000 gepaarde bootstrapsteekproeven per aflevering met seed 20261127. Voor het F1-verschil Jelly Leon min IS geldt een 95%-ondergrens van ten minste −0,05 per type en strikt groter dan nul voor late intro, seizoensvariant en recap.

De publicatie mag maximaal twee seconden inhoud per uur onterecht overslaan. De unie van overlappende voorspellingen telt één keer. Voor mid-credit, post-credit en previews geldt nultolerantie bij minstens 30 beschermde scènes. De uitvoer bevat de overlaptijd, het aantal scènes met ten minste 0,1 s overlap en de Wilson-bovengrens. Een correct als Preview getypeerde preview geldt als beschermd bij een overslaand Intro, Outro, Recap of Commercial. De eindpoort vereist nul beschermde overlaptijd.

De verwachte stockuitkomst is nul segmenten. Alleen een geldige meting levert een stockcijfer. Bij een ontbrekende definitieve baseline of te hoge éénminuutbelasting (grens 4,0) eindigt het commando met exitcode 3 en `NIET GEMETEN (machinelast)`. Bij een ontbrekende of onbruikbare IS-laadproef blijft baseline (b) Geblokkeerd. Echte series vragen twee onafhankelijk gelabelde rondes, menselijke bevestiging voor Pioneer One en een eigen bibliotheeksteekproef.
