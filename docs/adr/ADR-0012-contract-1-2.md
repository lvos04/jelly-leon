# ADR-0012 — Contract 1.2 in jelly-leon: manifest §9, Custom App-instructie, Custom User en Hub-adapter v1

- **Status:** Aanvaard (Sim-getest; niets hiervan is op een echte NAS gevalideerd)
- **Datum:** 2026-11-09
- **Context:** `docs/platform-v2/PLATFORM_CONTRACTEN.md` is nu `contracts 1.2` (byte-gelijke kopie, bron-commit `8b54f39`
  van `lvos04/ai-server-manager`; `tools/jelly-leon/contract_drift.py`). `CONTRACT_1.2_CONFORMITEIT.md` §9 noemt voor
  deze repo JL1–JL6. In deze ronde horen alleen JL2 en JL3 (uitvoeren), JL4 (documenteren) en de punten voor alle
  repos (A1 kopie, A4 EVIDENCE-test, A6 rooktest op elk proces). **JL1** (12.x-upgrade, ADR-0011) is een aparte fase;
  **JL5** (`JL_SYNC_PUSH_TOKEN`) blijft ongewijzigd tot besluit 4 valt; **JL6**: ontwerptaal §13 geldt niet.

## Besluit

1. **Manifest (JL2, §9).** `custom_app.ports` en `network.joins_platform_network` zijn verwijderd; de formulierpoorten
   komen alleen uit `network.ports` (`portal.port` en `healthcheck.port` verwijzen naar de naam `web`). GPU is een
   **optionele wizardparameter** `gpu` (type `gpu`, `source: wizard`, `decision: D08`, `required: false`, géén default:
   ontbreekt de waarde dan `none`); `custom_app.gpu: {param: gpu}`; `privileges.gpu: intel_render` is het **maximum**
   met een `privilege_reason`, en D08 staat in `decisions_required`. Geen `privileged`, geen `cap_add`, geen losse
   `devices`. Veiligste lezing van het contract: de wizard biedt `intel_render` alleen aan na een D08-meting; de
   vertaling geeft dan `resources.gpus.use_all_gpus: true` (elke niet-NVIDIA-render-GPU; één specifieke render-node
   kan het formulier niet — open punt B03/P4). Gecontroleerd met de validator én vertaler van de manifesteigenaar
   (`appstore-en-fork` `bd33052`): geldig, alleen `digest_pending_release` (nog geen release); zonder D08-meting
   weigert de vertaler (`gpu_not_measured`). Bewaking: `check_fork_consistency.py` (1.2-regels) en CI-job `manifest`.
2. **Custom App-instructie (JL3, §2.1/§2.2).** `deploy/truenas/CUSTOM_APP.md`: tag als `<forkversie>@sha256:<digest>`
   (terugval als het formulier `@` weigert: alleen de exacte versie + digest-readback door de executor); publieke
   image zonder registry-login, registry-login alleen als terugvaloptie (token alleen-lezen, nooit in formulier/
   manifest/repo/log); een eventuele stock-Jellyfin (D07 meet dat) blijft ongemoeid op zijn eigen poort; terugzetten
   via de vorige tag-met-digest plus config-snapshot (`app.rollback` werkt niet voor image-tags van Custom Apps).
3. **Custom User 568 (§2.2).** Het formulier zet geen `no-new-privileges`. Bij een start als root zette de entrypoint
   dat al (`setpriv --no-new-privs`, alle capabilities weg). Bij een start als niet-root (*Custom User* aangevinkt)
   startte de server tot nu toe **zonder** `no_new_privs` (gat ten opzichte van §2.2). Nu: eerst controleren dat
   `/config` en `/cache` schrijfbaar zijn (anders een NL-melding en stoppen, nooit stil doorstarten), daarna
   `setpriv --no-new-privs --inh-caps=-all` vóór de server start. De markering van de tweede fase telt alleen als
   `NoNewPrivs` echt 1 is (een in het formulier gezette variabele kan de stap niet overslaan). Een niet-root-proces kan
   zonder `CAP_SETPCAP` de bounding-set niet legen; met `CapEff 0` en `NoNewPrivs 1` levert die geen rechten meer op.
4. **Rooktest op elk proces (A6).** `tools/jelly-leon/e2e/image_lifecycle.py` controleert nu elk proces in de container
   (Uid 568, `CapEff 0`, `NoNewPrivs 1`), niet alleen PID 1. Processen die Docker van buiten start (`docker exec`, de
   Docker-healthcheck) hebben in de PID-namespace PPid 0 en vallen met hun kinderen buiten beschouwing — zoals het
   contract de eigen `docker exec`-shell uitzondert. Plus: een run met `--user 568:568` en een weigering bij een
   `/config` die niet van 568 is.
5. **Hub-adapter v1 (JL4, alleen documentatie; §2.3).** Jelly Leon krijgt in v1 **geen enrollment**: geen `HUB_URL`/
   `HUB_ENROLLMENT_TOKEN`, geen `/appdata/secrets/hub-link.json`. De adapter leeft in de Hub en gebruikt alleen
   - openbare routes: `GET /System/Info/Public`, `GET /health`;
   - de sessie van een **eigen niet-admin-Jellyfin-gebruiker** die de beheerder in het Jellyfin-dashboard maakt en in
     de Hub-UI invoert (vault, §3.10). Volgens de upstream-code (`DefaultAuthorizationHandler`) mag elke ingeschakelde
     gebruiker routes met `[Authorize]` zonder beleid aanroepen, dus ook `GET /media/v1/version` van de Jelly Leon-
     plugin. Sinds de onafhankelijke review van deze ronde **getest** (Sim-getest, zie *Aanvulling* hieronder).
   - **Nooit** een Jellyfin-API-sleutel: upstream behandelt API-sleutels als onbeperkt ("Api keys are unrestricted"),
     dus elke sleutel is in feite beheerder. Pas als de B03-plugin (P4) scopes biedt.
   - **Geen Hub-JWT's accepteren** tot er een pinmechanisme is. Ontwerp voor P4 (nog niet gebouwd): de plugin krijgt in
     haar configuratie (Jellyfin-dashboard, alleen beheerder) een veld waarin de beheerder de publieke Hub-sleutelset
     (`jwks` + `policy_public_key`, kopieerbaar in de Hub-UI) plakt; de plugin berekent de sleutelset-vingerafdruk
     (§4.5, met de testvectoren `MEGG-8GFG-2E4Y-K2RQ` en `CYRC-JS8C-14AN-JR17` in de unit-tests) en toont die ter
     vergelijking met de Hub-UI; pas na bevestiging pint ze de sleutels. Een via HTTP opgehaalde JWKS voegt nooit
     vertrouwen toe; `jti` + replaycache tot `exp` (§4.6); fail-closed volgens §4.7. Zonder pin: `501
     capability_unavailable` op de nieuwe `/media/v1/*`-routes die een Hub-JWT zouden vragen. De bestaande
     Jellyfin-routes en hun foutformaat blijven ongewijzigd (§2.3 regel 1).

## Gevolgen

- `deploy/manifest/jelly-leon.manifest.yaml` volgt §9 van 1.2; de release-CI (P4) moet nog `image.digest` vullen en
  dan `--strict` zonder toegestane waarschuwingen halen.
- `CUSTOM_APP.md` beschrijft de echte formulierrealiteit; alles over het formulier zelf blijft NIET GEVALIDEERD (echte
  NAS) tot een installatie op de NAS van de gebruiker.
- Contract-issues (gemeld in het eindrapport): (a) de Docker-healthcheck (`HEALTHCHECK` in de Dockerfile) draait in
  elke alles-in-één image van het platform als de containergebruiker — bij een Custom App zonder *Custom User* dus als
  root met de standaard-capabilities en zonder `no_new_privs`; §2.2 zegt "alle processen" en de rooktest sluit alleen de
  eigen `docker exec`-shell uit. Kortlevend en van buiten gestart, maar niet "geen enkel proces meer als root". Veiligste
  interpretatie hier: de rooktest sluit exec-/healthcheckprocessen (PPid 0) uit en dit wordt aan de contracteigenaar
  gemeld; een oplossing (healthcheck via `setpriv` naar 568) hoort platformbreed. (b) Contract §2/§10 noemen `/appdata`
  en `/healthz`; Jelly Leon houdt `/config` + `/cache` en `/health` (ADR-0008, ongewijzigd).

## Aanvulling — onafhankelijke review van de contract 1.2-ronde (2026-11-09)

- **JL4 getest (Sim-getest):** `tools/jelly-leon/e2e/stock_client_smoke.py` (met `--expect-plugin`; CI-jobs
  *stock-client-e2e* en *image*, ook de terugzetproef) laat de beheerder een eigen **niet-admin**-gebruiker aanmaken
  (`POST /Users/New`, `IsAdministrator: false`; na een herstart bestaat die nog) en controleert als die gebruiker:
  inloggen lukt; `GET /media/v1/version` → 200 `compatibel`; `GET /Auth/Keys` → **403** (een niet-admin ziet geen
  API-sleutels). Een Hub-JWT in de vorm van een dienst-JWT (§4.3, nep-handtekening) wordt **niet** geaccepteerd:
  `Authorization: Bearer <jwt>` → 401 en als Jellyfin-token → 401. Gemeten tegen de echte server-build (geen echte
  Hub, geen echte NAS).
- **Gevolgen (a) opgelost in deze repo:** de Docker-healthcheck wisselt nu zelf naar 568 zonder capabilities vóór curl
  (ADR-0014). Het restrisico (Docker start het healthcheckproces als root; heel kort vóór de `exec`) en het
  platformbrede contract-issue blijven gemeld.
