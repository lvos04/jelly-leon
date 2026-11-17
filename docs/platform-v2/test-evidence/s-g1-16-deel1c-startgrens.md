# S-G1-16 deel 1c — opslaggrens van de start

Status: **Bezig**. B03-017 in EVIDENCE en de lokale image blijven deel 2. Bronbasis:
`6c1deb9a79552575b9e88fb322d0a25f47b8a124`. Geen echte NAS, Emby of accounts benaderd; alleen synthetische bestanden en
wegwerpcontainers zonder netwerk. Achtergrond en redenering: ADR-0032, "Opslagdreigingen, deel 1c".

## Wat de blokkerende proef van deel 1b mat

Niet de plugin, maar `record_datamap_version` uit `deploy/allinone/entrypoint.sh`: een tijdelijk bestand
`datamap-versie.tmp.$$`, geschreven met `>`. In de container is de start PID 1, dus de naam ligt vast. Een andere
gebruiker die in een voor iedereen beschrijfbare `/config` (of `/config/jelly-leon`) een koppeling op die naam legt, laat
de start als 568 in het doel schrijven. De proef van deel 1b (functie op de host, aanvaller uid 65534 in een container)
is opnieuw gedraaid: rood, synthetische buiten-database overschreven.

Realistischer herhaald met de **echte** entrypoint als PID 1 in de gepinde runtime-basis, `/config` 0777 van een andere
gebruiker dan 568 en de koppeling naar een synthetische `/config/data/jellyfin.db` (de serverbinary vervangen door een
nepscript):

| Variant | Uitkomst |
|---|---|
| Entrypoint van 6c1deb9a7, gedeelde `/config` | Start geslaagd, `pid=1`; serverdatabase **overschreven**; `chown -R` nam eerst de bestanden van de aanvaller over |
| Nieuwe entrypoint, gedeelde `/config` | Geweigerd vóór de eigenaarswissel, NL-melding; database byte-gelijk, eigenaar en koppeling ongewijzigd |
| Nieuwe entrypoint, correcte `/config` (0755) | Start geslaagd als 568; `datamap-versie` gewoon bestand (0600) |
| Nieuwe image-modus, `/cache` als tmpfs | Start geslaagd; tmpfs-`/cache` 0755 (nam de modus van de imagemap over) |

Gemeten in de basisimage: umask 0022; `/config` en `/cache` 0777. Docker-tmpfs en een nieuw benoemd volume nemen de
modus van de imagemap over (0777; een tmpfs op een nieuw pad 1777).

## Herstel en regressietests

- Entrypoint: `assert_private_storage` vóór elke schrijfactie (als root vóór `chown -R`, als 568 vóór het vastleggen) en
  `assert_private_dir` na elke eigen `mkdir`; tijdelijk bestand via `mktemp`.
- Dockerfile: `chmod 0755 /config /cache`.
- `tools/jelly-leon/tests/test_entrypoint_opslaggrens.py` (CI-job forkregels): 13 tests; op de oude entrypoint 11 rood
  (de twee koppelingsproeven met overschreven buiten-database, zeven onveilige opzetten zonder weigering, een vreemde
  eigenaar, de volgordetest) en de twee gevallen "correcte installatie blijft starten" groen; na herstel 13 groen.
- `tools/jelly-leon/e2e/image_lifecycle.py` (CI-job image, echte image): `check_storage_modes` (lokaal rood op de
  basisimage, groen op een lichte afgeleide image met dezelfde Dockerfile-regel) en `expect_shared_config_refusal`
  (de proef van deel 1b met de echte image; de testgebruiker is de andere gebruiker; lokaal groen op die lichte image).

Het halve proefscript van deel 1b (`startopslag_grensproef.py`) is hierdoor vervangen en niet vastgelegd.

## Open, niet gevalideerd

Op de echte NAS te meten: de modusbits van de preset Apps en van het TrueNAS-opslagtype tmpfs. Geeft de preset
schrijfrecht voor de groep, dan weigeren start en plugin elke installatie volgens `deploy/truenas/CUSTOM_APP.md`.
Modusbits tonen geen NFSv4-ACL-regels voor benoemde gebruikers. De twee restgrenzen van actor (a) uit deel 1b staan
onveranderd open (ADR-0032, deel 1c, correctie op actor (a)); daarover beslist de regisseur.
