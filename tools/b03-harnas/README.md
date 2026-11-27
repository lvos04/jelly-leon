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
