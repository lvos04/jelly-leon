# Overname kijkgeschiedenis Emby → Jelly Leon (B03-015 deel A)

Losse tool (Python 3.12, alleen de standaardbibliotheek, GPL-2.0 zoals de fork) die de kijkgeschiedenis van **alle
gebruikers** uit Emby overneemt in Jelly Leon / Jellyfin 12.x: gezien-status **met datum en aantal**, hervatpunten **op de
tick exact**, favorieten, beoordelingen (als Emby ze levert), gebruikers met rechten en ouderlijk toezicht, en taal- en
ondertitelvoorkeuren. Onthouden spoorkeuzes worden gelezen en vergeleken. Besluit en beoordeling van JellyPlex-Watched:
`docs/adr/ADR-0025-b03-015-eigen-overnametool-niet-jellyplex-watched.md`. Bouwplan: B03 §10.9.1 en §10.9.2.

> **Status (eerlijk):** golf 0 — Sim-getest tegen simulators en tegen een **echte Emby 4.10.2.0-container** met stock
> **Jellyfin 12.4** (`e2e/proefrun.py`). De echte overname op de NAS (JLT-74) is **NIET GEVALIDEERD (echte NAS)**. De
> gebruiker heeft geen terminal: op de NAS start straks de overname-assistent in het beheer van Jelly Leon deze tool
> (P4-0). Tot dan is deze opdrachtregel alleen voor de proefrun in de testomgeving en CI.

## Garanties

| Garantie | Hoe afgedwongen | Test |
|---|---|---|
| Emby wordt alleen gelezen | `EmbyLezer` staat alleen `GET` toe op een vaste witte lijst; al het andere geeft `AlleenLezenFout` vóór het netwerk; geen redirects, geen omgevingsproxy | `tests/test_eenheden.py`, `testhaak-schrijfpoging`, loggende proxy in `e2e/` (JLT-73) |
| Geen schrijfactie in Emby uitlokken | voor een bestand dat Emby nog niet heeft geanalyseerd (grootte 0) geen `PlaybackInfo` (gemeten: die laat Emby het bestand alsnog analyseren en opslaan); het item staat in de export onder `spoorkeuzes_niet_gelezen` | `test_niet_geanalyseerd_bestand_geen_playbackinfo`, e2e (exportarchief vóór/na identiek) |
| Emby-databasebestanden worden nooit geopend | de tool kent geen bestandsroute naar Emby, alleen de API | code |
| API-sleutels nergens zichtbaar | alleen in een bestand met modus 0600 (anders weigert de tool); alleen als header; spoorlog zonder headers | `test_emby_identiek_voor_en_na_en_sleutels_nergens`, e2e-zoektocht |
| Nooit per vergissing in Emby schrijven | het doel moet eerst, zonder sleutel, via `GET /System/Info/Public` `ProductName` "Jellyfin Server" melden (Emby 4.10.2.0 meldt geen ProductName maar accepteert wél de Jellyfin-aanmeldheader — gemeten); zelfde adres of zelfde server-ID als de bron → exit 9; zonder bevestigd doel weigert de client elk verzoek vóór het netwerk | `test_doel_dat_emby_is_wordt_geweigerd_voor_elke_schrijfactie`, `test_bron_en_doel_dezelfde_server_geweigerd`, e2e (JLT-73, verkeerd doel) |
| Jelly Leon alleen via de officiële API | witte lijst: `POST /Users/New`, `/Users/{id}/Policy`, `/Users/Configuration`, `/UserItems/{id}/UserData`; nooit `jellyfin.db` | `tests/test_eenheden.py` |
| Niets stil weglaten | elk Emby-item met kijkgegevens is gekoppeld of staat met reden op de afhandellijst (`verantwoord`) | JLT-72 |
| Nooit gokken | provider-ID → (bij afleveringen) serie + seizoen + aflevering → pad; meerdere kandidaten zonder eenduidig pad = `dubbel` | JLT-72 |
| Een kind ziet nooit meer dan in Emby | onvertaalbare beperkingen worden strenger ingesteld; na het schrijven wordt de zichtbaarheid per gebruiker vergeleken (`ruimer` moet 0 zijn) | JLT-70 |
| Geen schrijfactie zonder akkoord | `overzetten` vraagt een `akkoord.json` op precies het plan (sha256) van de proefrun, met akkoord op elk verschil | `test_akkoord_verplicht_en_plan_moet_gelijk_zijn` |
| Idempotent, laatste delta | samenvoegregels in `samenvoegen.py` + staat met de Emby-waarden van de vorige run | JLT-71 |
| Hervatten na een kill zonder dubbele schrijfacties | write-ahead-journaal; bij herstel per open voornemen in Jelly Leon nagaan of het al is uitgevoerd | JLT-71 |
| Wachtwoorden niet overgezet | nieuwe gebruikers krijgen een willekeurig, nergens bewaard wachtwoord; rapport vraagt om een nieuw wachtwoord of SSO | JLT-70 |

## Samenvoegregels (nooit stil overschrijven)

Eens gezien blijft gezien · aantal keren gezien: eerst `max(Emby, Jelly Leon)`, daarna alleen de nieuwe keren uit Emby erbij ·
datum: de nieuwste · hervatpunt: volgens het nieuwste moment (Jelly Leon nieuwer → blijft staan) · favoriet: toevoegen, nooit
automatisch verwijderen (een in Emby verwijderde favoriet staat ter beslissing op de afhandellijst) · beoordeling: alleen
zetten als Jelly Leon er geen heeft. Containers (serie, seizoen, collectie, persoon) krijgen alleen favoriet en beoordeling.

## Gebruik (testomgeving en CI)

```text
# 1. Inventaris (D07) en blijvend archief (controlelijst "Emby verwijderen", stap 4)
python -m emby_overname inventaris --emby-url http://emby:8096 --emby-sleutel-bestand /geheimen/emby-api-key --werkmap W
python -m emby_overname export     --emby-url http://emby:8096 --emby-sleutel-bestand /geheimen/emby-api-key --uitvoer A.json

# 2. Proefrun (droog): rapport.json/.md/.html + plan; schrijft niets
python -m emby_overname proefrun --emby-url … --emby-sleutel-bestand … --jl-url http://jelly-leon:8096 \
    --jl-sleutel-bestand /geheimen/jl-api-key --werkmap W --pad /mnt/emby/media=/data/media [--gebruiker beheerder=jlbeheer]

# 3. Akkoord op het plan (rapport.html → "Akkoord-bestand maken") en overzetten
python -m emby_overname overzetten … --akkoord akkoord.json

# 4. Laatste delta bij de overstap = opnieuw 2 en 3; daarna mag de overstap alleen met akkoord op elk verschil
python -m emby_overname akkoord-controle --rapport W/runs/…/rapport.json --akkoord akkoord-cutover.json

# Herimport uit het archief (Emby niet meer nodig): --bron-archief A.json in plaats van --emby-url/--emby-sleutel-bestand
# Emby vóór en na identiek?
python -m emby_overname vergelijk-export voor.json na.json
```

Uitvoer per run in `W/runs/<tijd>-<soort>/`: `emby-export.json` (+ `.sha256`), `rapport.json` (+ `.sha256`), `rapport.md`,
`rapport.html`, `log.jsonl` (alleen methode, pad, querysleutels, status en duur). Staat en journaal in `W/staat/`, plannen in
`W/plannen/`. Op de NAS hoort `W` onder `/config/data/jelly-leon/overname/` (eigen schrijfplek van Jelly Leon, ADR-0020) en
het archief op een dataset in de back-updekking (B12).

Exitcodes: 0 in orde · 2 gebruik · 3 akkoord ontbreekt of onvolledig · 4 plan gewijzigd sinds de proefrun · 5 verbinding ·
6 controle mislukt · 7 geheim (ontbreekt of te ruime rechten) · 8 alleen-lezen-weigering · 9 doel is geen
Jellyfin/Jelly Leon (bijv. Emby) of dezelfde server als de bron.

## Afhandellijst: redenen

| Reden | Betekenis |
|---|---|
| `geen_id` | geen provider-ID's en geen item op hetzelfde (vertaalde) pad |
| `dubbel` | meerdere Jelly Leon-items passen (bijv. twee versies met dezelfde IMDb-ID) en het pad wijst er niet één aan |
| `ontbreekt` | wel ID's, maar geen tegenhanger (ook absolute afleveringsnummering zonder seizoen valt hier, nooit aangenomen) |
| `ander_bestand` | zelfde item, ander bestand (pad of grootte): onthouden spoorkeuze niet overgenomen |
| `type_niet_ondersteund` | soort item die de tool niet koppelt (bijv. afspeellijst) |
| `niet_zichtbaar_in_jelly_leon` | gekoppeld, maar de gebruiker mag het item in Jelly Leon niet zien |
| `spoorkeuze_niet_overzetbaar` | Jellyfin 12.4 heeft geen officiële route voor spoorkeuzes (`capability_unavailable`) |
| `favoriet_verwijderd_in_emby`, `gezien_teruggezet_in_emby`, `conflict_*` | uw beslissing; de tool overschrijft niets |
| `hervatpunt_jelly_leon_nieuwer`, `*_alleen_in_jelly_leon` | verklaard verschil, ter kennisname |
| `wachtwoord_niet_overgezet`, `recht_strenger`, `recht_ruimer`, `zichtbaar_*` | gebruikers en rechten |

## Tests

```text
python -m pytest -q tools/emby-overname/tests                         # unit + simulators (geen netwerk, geen Docker)
flock /home/transcode/truenas-v2/.lokaal/stack.lock \
  python tools/emby-overname/e2e/proefrun.py --modus corpus --uitvoer <map>   # echte Emby + stock Jellyfin 12.4 (JLT-70…73)
```
