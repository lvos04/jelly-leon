# ADR-0028 — Contract 1.3 in jelly-leon: kopie en drifttest, EVIDENCE §11, healthcheck §2.2 en manifest §9

- **Status:** Aanvaard (Unit-getest en Sim-getest; niets hiervan is op een echte NAS gevalideerd)
- **Datum:** 2026-11-11
- **Context:** `docs/platform-v2/PLATFORM_CONTRACTEN.md` is nu `contracts 1.3` (byte-gelijke kopie, bron-commit `02b119c`
  van `lvos04/ai-server-manager`). `CONTRACT_1.3_CONFORMITEIT.md` §9 noemt voor deze repo C1.3-JL-01…09 en voor alle
  repos C1.3-ALG-01…05. In deze ronde horen alleen de punten met moment **NU**: C1.3-JL-01 (kopie en pin), C1.3-JL-02
  (EVIDENCE), C1.3-JL-03 (healthcheck en rooktest nalopen), C1.3-JL-04 (manifest) en C1.3-ALG-01…04. De rest staat
  onderaan bij *Later*. ADR-0012 (contract 1.2) blijft gelden waar 1.3 niets wijzigt.

  Let op de nummering: "ADR-0028" in de gekopieerde contractbestanden verwijst naar
  `ai-server-manager:docs/adr/ADR-0028-review-contract-1-3.md`; dit is de ADR van deze repo met toevallig hetzelfde
  nummer.

## Besluit

1. **Kopie en drifttest (C1.3-JL-01, C1.3-ALG-01).** `PLATFORM_CONTRACTEN.md` en `CONTRACT_1.3_CONFORMITEIT.md` zijn
   byte-gelijk overgenomen en worden hier nooit bewerkt. `tools/jelly-leon/contract_drift.py` zet beide vast op hun
   sha256 en op de bron-commit en vergelijkt in de CI-job *forkregels* online met de bron.
   `CONTRACT_1.2_CONFORMITEIT.md` blijft als historie staan, vastgezet op zijn eigen bron-commit (`8b54f39`); dat mag
   volgens C1.3-ALG-01.
2. **EVIDENCE §11 (C1.3-JL-02, C1.3-ALG-02).** `tools/jelly-leon/tests/test_evidence_contract.py` bewaakt de regels
   van 1.3: de nieuwe waarden `Intel-iGPU-getest (ontwikkelmachine)` en `Niet getest` (die laatste alleen bij
   `Niet gestart`), nooit een lege `validatie`, elke `NIET GEVALIDEERD (…)` uit `blokkade` ook in `validatie`, en eigen
   regels voor contractpunten (`C1.3-…`) en reviews (`REVIEW-…`), waarbij een `C1.3-JL-nn` in de gekopieerde
   conformiteitslijst moet bestaan. `Gereed` en `Geslaagd` blijven verboden.
   *Gekozen interpretatie:* §11 kent voor een testrij alleen `Sim-geslaagd` of `Sim-mislukt`, als resultaat van de
   hele rij. Is maar een deel van een rij uitgevoerd (JLT-60, JLT-63, JLT-70, JLT-73), dan houdt deze repo
   `Sim-getest` aan, alleen bij status `Bezig` en met een `opmerking` die zegt wat niet is gedraaid. Dat is de veiligste
   lezing: nooit een geslaagd voor iets wat niet gedraaid heeft. Gemeld als contractpunt.
3. **Healthcheck en rooktest (C1.3-JL-03, C1.3-ALG-04).** De details staan in de aanvulling van ADR-0014; het besluit
   in het kort:
   - De `HEALTHCHECK` staat in **exec-vorm** (`CMD ["/usr/local/bin/jelly-leon-healthcheck"]`, geen `sh -c`). Als
     eerste handeling wisselt het naar 568:568 zonder groepen, met een lege bounding set (bij een start als root),
     zonder inheritable of ambient capabilities en met `no_new_privs`; pas daarna controleert het zijn eigen rechten en
     dan `/health`. Elke mislukking geeft exitcode 1.
   - *Gekozen interpretatie:* §2.2 spreekt van "een klein programma" dat `setgroups`, `setgid`, `setuid` en
     `prctl(PR_SET_NO_NEW_PRIVS)` uitvoert. Hier is dat een shellscript dat vóór de wissel alleen ingebouwde
     shellopdrachten gebruikt en de wissel in één `setpriv`-aanroep doet (hetzelfde hulpmiddel als het entrypoint),
     geen apart gecompileerd programma. De contracteigenaar mat dit script in 1.3 als conform. Een gecompileerd
     hulpprogramma zou een extra bouwstap en een extra binair bestand in de image vragen zonder dat het restrisico
     (het korte venster waarin Docker het proces als root start) kleiner wordt. Gemeld als contractpunt.
   - **Controlevlag `--toon-rechten`:** dezelfde wissel en controle, daarna `/proc/self/status` van een proces met
     precies die rechten. De rooktest (`tools/jelly-leon/e2e/image_lifecycle.py`) gebruikt de vlag voor de aparte
     controle van de healthcheck (`Uid 568`, `CapEff`, `CapPrm` en `CapAmb` 0, `NoNewPrivs 1`) en controleert elk
     proces in de boom van PID 1, na een start als root ook op `CapBnd` 0. `healthcheck_proef.py` draait het script
     uit de checkout in de runtime-image, als root en als 568, met de negatieve gevallen.
   - Het fase-argument van het script is intern en slaat niets over: als root wordt altijd gewisseld. Het is een
     argument en geen omgevingsvariabele, zodat het formulier het niet kan zetten.
4. **Manifest §9 (C1.3-JL-04).** `deploy/manifest/jelly-leon.manifest.yaml`:
   - **Geen `HUB_*`-namen** in `parameters` of `custom_app.env` (`env: []`). De Hub-koppeling van de plugin loopt via
     het dashboard (C1.3-JL-06), niet via formulierwaarden.
   - **Monitorplan** `healthcheck.monitor: {pad: /health, verwachte_status: 200, timeout_s: 10, interval_s: 60}`.
     `/health` is de upstream-route (§2.3 regel 9) en dezelfde als `healthcheck.path`. De Hub maakt hier alleen een
     plan van; de beheerder neemt het over in Uptime Kuma en bevestigt het daar. Tot dan is het niet bevestigd.
   - **`post_install_checks`: `startwizard_afronden`, soort `handmatig`.** Zolang de startwizard van Jellyfin
     openstaat, kan iedereen op het netwerk die de pagina opent beheerder worden: precies het open
     eerste-gebruik-venster waar §9 dit veld voor noemt.
     *Gekozen interpretatie:* `soort: http` zou dit automatisch kunnen meten (`GET /System/Info/Public` geeft
     `StartupWizardCompleted`), maar §9 geeft een `http`-controle alleen `id`, `soort` en `beschrijving_nl`: geen
     velden voor het pad of de verwachte inhoud. Zonder die velden zou een `http`-controle iets beloven wat het
     manifest niet vastlegt, dus `handmatig`. Gemeld als contractpunt.
   - **`accepted_findings`:** alleen `digest_pending_release`, met reden (eigen image vóór de eerste release). De
     vertaling weigert een image zonder digest (`digest_not_pinned`), dus installeren via het platform kan pas na de
     eerste release.
   - **CI valideert strikt, zonder eigen uitzonderingenlijst.** De job *manifest* haalt de validator van de
     manifesteigenaar (`appstore-en-fork`) op een vastgezette commit die 1.3 kent (`7b3159d`) en draait
     `validate --strict`. `tools/jelly-leon/manifest_rapport.py` beoordeelt het rapport en kent de vlag `--toegestaan`
     niet meer: een waarschuwing telt alleen als geaccepteerd wanneer de validator haar zo markeert, met de reden uit
     het manifest en een code uit de vaste lijst van §9. Ook de exitcode van de validator telt.
   - `check_fork_consistency.py` bewaakt dezelfde regels zonder netwerk (job *forkregels*), inclusief de koppeling
     "`digest_pending_release` precies dan geaccepteerd als `image.digest` leeg is".

## Gemeten

- Validator `appstore-en-fork@7b3159d`, `validate --strict`: manifest geldig en strikt geldig, één waarschuwing
  (`digest_pending_release`), geaccepteerd met reden. Vijf negatieve proeven falen zoals bedoeld (zie
  `docs/platform-v2/test-evidence/c13-manifest-validator.json`).
- Eén afwijking van de contracttekst, gemeld als contractpunt: een **parameter** met de naam `HUB_URL` weigert de
  validator met `invalid_format` (parameternamen zijn kleine letters), niet met `reserved_env`; als
  `custom_app.env`-naam geeft hij wel `reserved_env`. De uitkomst is in beide gevallen een fout, dus veilig.
- Lokaal gebouwde alles-in-één image: rooktest en healthcheckproef, zie de regels C1.3-JL-03 en C1.3-ALG-04 in
  `EVIDENCE.json`. Alles is simulatorbewijs op de ontwikkelmachine.

## Gevolgen

- De release-CI (P4) vult `image.digest` en haalt in dezelfde wijziging `digest_pending_release` uit
  `accepted_findings`; laat ze dat na, dan faalt `--strict` op `accepted_finding_unused` en faalt
  `check_fork_consistency.py`.
- Een nieuwe waarschuwing van de validator laat de CI falen tot ze is opgelost of, als ze in de vaste lijst van §9
  staat, met reden in het manifest is geaccepteerd. Een nieuwere validator overnemen = `APPSTORE_COMMIT` in de
  workflow verzetten.
- Geen core-patch: alle wijzigingen staan in fork-eigen paden (`deploy/`, `tools/jelly-leon/`, `docs/`, de eigen
  workflow). Upstream-code en de technische identiteit "Jellyfin" zijn ongewijzigd.

## Later (niet in deze ronde)

| Punt | Wat | Moment |
|---|---|---|
| C1.3-JL-05 | Overname uit Emby en vóór/na-rapport bij elke upgrade die `jellyfin.db` migreert | P4-0 (golf 0 gedaan, Sim-getest; echte NAS open) |
| C1.3-JL-06 | Plugin: Hub-koppeling met pin via het dashboard en `service_id` | P4 |
| C1.3-JL-07 | 1 MiB per route, foutcatalogus, health-regels en eventnamen nalopen | P4 |
| C1.3-JL-08 | MediaGuard-viewerclient; acties alleen als deeplink | P4 (na BG-04; acties na BG-05) |
| C1.3-JL-09 | Geen torch, transformers of ctranslate2 in de image; vertaling via de app `mt` | P5 (na BG-06/BG-18) |
| C1.3-ALG-05 | Peil-verbeterpunten alleen via Peil 1.1.1 | na Peil 1.1.1 (deze repo heeft geen statuspagina) |

C1.3-ALG-03 (licentie) is conform zonder wijziging: de fork houdt de upstream-licentie GPL-2.0 (ADR-0004).
