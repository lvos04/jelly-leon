# B03-016-harnas — corpusgenerator, clientmatrix en baselines van stock Jellyfin

Gereedschap voor de **ontwikkelmachine en CI** (nooit op de NAS, nooit in de Jelly Leon-image). Besluit en motivatie:
`docs/adr/ADR-0026-b03-016-harnas-corpus-clientmatrix-baseline.md`; procedure en uitkomsten:
`docs/platform-v2/B03-016_HARNAS.md` en `docs/platform-v2/BOUWVERIFICATIE_B03-016.md`.

| Onderdeel | Ingang | Wat |
|---|---|---|
| corpusgenerator | `python -m b03h corpus …` | recepten F1–F6 + ASS + groot bestand, grondwaarheid, sha256-manifest, bevriezen, opruimen |
| CI-guard | `python -m b03h guard --git . / --bereik . A..B / --image REF / --map DIR` | weigert beperkt gelicentieerde testdata (BG-37) en media in de repo |
| baselines | `python -m b03h baseline --metingen dp,orakel,transcode,functies --runs 3` | stock-standaard en stock-best, meetprotocol, n + Wilson |
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
