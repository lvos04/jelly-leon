# ADR-0014 — Docker-healthcheck zonder root-rechten (contract 1.2 §2.2)

- **Status:** Aanvaard (Sim-getest met Docker; niet op een echte NAS)
- **Datum:** 2026-11-09
- **Context:** Contract 1.2 §2.2 en §10: na de eigenaarschapsstap draait geen enkel proces meer als root; het
  TrueNAS-formulier zet geen `no-new-privileges` en laat de standaard-capabilities van Docker staan. Docker start de
  `HEALTHCHECK` als de **containergebruiker**: bij een Custom App zonder *Custom User* is dat root, met de
  standaard-capabilities (`CapEff 00000000a80425fb`) en zonder `no_new_privs`. Tot nu toe was de healthcheck
  `curl … http://localhost:8096/health`: curl las dus **als root** het HTTP-antwoord van de server (die als 568 draait).
  Een gecompromitteerde server zou via een fout in curl root-rechten in de container kunnen krijgen. ADR-0012
  (Gevolgen (a)) meldde dit als contract-issue en sloot healthcheckprocessen in de rooktest uit. Bij de onafhankelijke
  review van de contract 1.2-ronde is gekozen dit in deze repo zelf zo veel mogelijk op te lossen (veiligste lezing van
  §2.2), zonder op een platformbreed besluit te wachten.

## Besluit

1. `HEALTHCHECK` roept `/usr/local/bin/jelly-leon-healthcheck` aan (`deploy/allinone/healthcheck.sh`, interval, timeout
   en retries ongewijzigd). Het script wisselt vóór de HTTP-aanvraag van rechten:
   - als root: `setpriv --reuid=568 --regid=568 --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs --
     curl …` (zelfde wissel als de entrypoint, zonder GPU-groepen: die heeft de healthcheck niet nodig);
   - als niet-root (*Custom User* 568): `setpriv --no-new-privs --inh-caps=-all -- curl …` (een niet-root-proces kan de
     bounding-set zonder `CAP_SETPCAP` niet legen; met `CapEff 0` en `NoNewPrivs 1` levert die niets op, ADR-0012).
   De aanvraag zelf is ongewijzigd (`/health`, alleen `localhost`, geen proxy) met `--max-time 8` binnen de
   Docker-timeout van 10 s. Een mislukte aanvraag geeft een exitcode ≠ 0 (healthcheck rood). Een onbekende optie
   → exitcode 2 zonder iets uit te voeren.
2. `jelly-leon-healthcheck --toon-rechten` voert met **precies dezelfde wissel** `cat /proc/self/status` uit in plaats
   van curl. Alleen bedoeld voor de rooktest; toont niets geheims.
3. Bewaking:
   - `tools/jelly-leon/e2e/image_lifecycle.py` (ook CI-job *image*), bij een start als root én met *Custom User*
     568:568: de `HEALTHCHECK` van de image is het script; de rechten waarmee curl start zijn `Uid 568` (alle vier),
     `CapEff 0` en `NoNewPrivs 1`, bij een root-start bovendien `Gid 568`, geen aanvullende groepen en `CapBnd 0`; en de
     healthcheck zelf slaagt.
   - `tools/jelly-leon/tests/test_healthcheck_script.py`: het script met nep-`id`/`setpriv`/`curl` (welke wissel als
     root en als *Custom User*, rood bij een mislukte aanvraag, weigering van onbekende opties, Dockerfile gebruikt
     het script en nergens meer rechtstreeks curl).

## Gevolgen en restrisico

- curl verwerkt het antwoord van de server nooit meer met root-rechten, ook niet zonder *Custom User*.
- **Restrisico (niet op te lossen in de image):** Docker start het healthcheckproces zelf als de containergebruiker;
  de `sh` van het script en `setpriv` draaien dus heel kort als root vóór de `exec`. In dat venster wordt geen invoer
  verwerkt. Hetzelfde geldt voor elke `docker exec`. De rooktest sluit processen die Docker van buiten start (PPid 0)
  daarom nog steeds uit; het contract-issue voor de contracteigenaar blijft staan (platformbreed besluit; andere repos
  worden hier niet gewijzigd). Dit script kan als voorbeeld dienen.
- Geen core-patch (`deploy/` is een fork-eigen pad); upstream-code ongewijzigd.

## Aanvulling contract 1.3 (2026-11-10, C1.3-JL-03; motivering in ADR-0028)

Contract 1.3 §2.2 maakt dit besluit platformbreed (de contracteigenaar mat het script als conform) en scherpt drie
dingen aan; bij het nalopen zijn die hier doorgevoerd:

1. **Eerste handeling = de wissel, daarna pas controleren.** Het script leest zijn eigen rechten vóór de wissel alleen
   met ingebouwde shellopdrachten (`read`, `case`): er start geen ander programma (`id`) meer als root. Na de wissel
   start `setpriv` het script opnieuw (`/bin/sh <script> <modus> --na-wissel[-root]`), dat dan eerst zijn eigen
   `/proc/self/status` controleert — Uid 568 (bij *Custom User* de eigen uid, nooit 0), `CapPrm`, `CapEff` en `CapAmb`
   0, `NoNewPrivs 1`, na een start als root ook `Gid 568`, geen groepen en `CapBnd 0` — en pas dan `/health` opvraagt.
2. **Exitcode 1 bij elke mislukking** (controle na de wissel, `/health`), in plaats van de foutcode van curl. Weigert
   `setpriv` zelf de wissel, dan eindigt het met de foutcode van setpriv: Docker telt elke exitcode behalve 0 als
   ongezond, en er blijft geen root-proces wachten (bewust `exec`, geen ouderproces als root dat de code omzet).
3. **Het fase-argument is intern en geen omweg:** als root wordt altijd gewisseld; staat `no_new_privs` na de wissel
   nog uit, dan rood zonder tweede poging (geen lus). Het is een argument, geen omgevingsvariabele: het formulier kan
   het niet zetten (Docker start de healthcheck zonder argumenten).

Bewaking erbij: `tools/jelly-leon/e2e/healthcheck_proef.py` (script uit de checkout in de runtime-image, als root en als
568, met de negatieve gevallen; CI-job *stock-client-e2e*), `image_lifecycle.py` controleert de controlevlag ook op
`CapPrm`/`CapAmb` en het fase-argument zonder echte wissel (rood), en elk proces in de boom van PID 1 op
`CapPrm`/`CapAmb` 0 en — na een start als root — `CapBnd` 0. Het restrisico hierboven (het korte venster waarin de
shell zelf als root draait) blijft het gemelde restrisico van §2.2.
