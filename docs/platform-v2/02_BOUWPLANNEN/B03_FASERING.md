# B03 2.0 — Fasering, volgorde, afhankelijkheden en gates

Versie: synthese 2026-11-09 (voorstel), aangevuld op 2026-11-09 met de genomen besluiten, de HARDE EIS van de gebruiker en
de overname vanuit Emby (`BESLUITEN_GENOMEN.md`). Hoort bij `B03_UNIVERSELE_MEDIASERVER.md` (versie 2.0). Dit is een plan; er is
niets gebouwd. De tekstvoorstellen in §8 zijn op 2026-11-09 door de eigenaar (`ai-server-manager`) overgenomen in
`OVERDRACHT/OVERDRACHT_PROMPT.md` §4, `01_ARCHITECTUUR/06_FASERING_EN_GATES.md` en de Excel (rij P4-0 op het blad Fasen,
de B03-rijen en de testrijen JLT-01…74).

## 1. Uitgangspunten

1. **Programmafasen blijven P0–P6** (`01_ARCHITECTUUR/06_FASERING_EN_GATES.md`). Nieuw is **P4-0**: de upgrade van server en
   web naar de nieuwste stabiele Jellyfin 12.x, als aparte fase vóór P4 (besluit van de gebruiker, ADR-0011 in jelly-leon).
2. **P4 = plugins vóór patches.** Alle zes functies zijn modules in één plugin; core-, web- en clientpatches komen pas als
   de ladder faalt, klein en geregistreerd, en meestal in de laatste golf.
3. **P5 = lokale AI.** Alles wat een model nodig heeft (vertaling, embeddings, spraakherkenning, lokale AI voor segmenten)
   valt in P5, is optioneel en staat standaard uit; de klassieke route is in P4 al af en werkt altijd.
4. **Golven binnen P4** (jury haalbaarheid A-8): de ontwikkelmachine kan maar één zware stap tegelijk aan (emulator
   3,3–3,9 GB, 14,5 GiB RAM), dus wordt P4 in golven opgedeeld. Golf 0 kan nu al, parallel aan P0–P3, tegen stock 12.4.
5. **NAS is de laatste gate.** Alles wat de A310, de UHD 770, de echte bibliotheek of echte apparaten nodig heeft, staat
   op *Geblokkeerd* in de NAS-testrijen tot een echte run (cutover-gate "Jellyfin client/GPU testmatrix geslaagd").
6. Elke subfase houdt de bestaande B03-fase-entry en -exit: code review, back-up-/rollbackgate, een gebruikersreis op
   mobiel, een negatieve permissietest; bij een blokkade niets forceren: *Geblokkeerd* + reden + eigenaar. Na elke
   bouwstap een onafhankelijke review-agent (OVERDRACHT §3); na elke UI-stap een ontwerpreview (alleen Hub-UI, §13).
7. **Kijkgeschiedenis eerst (gebruiker, 2026-11-09).** HARDE EIS: alle kijkgeschiedenis (gezien-status, hervatpunten,
   favorieten, beoordelingen, onthouden spoorkeuzes, gebruikers, rechten) en de MediaGuard-voortgang blijven altijd
   beschikbaar; geen cutover zonder vóór/na-rapport per gebruiker en uitdrukkelijk akkoord op elk verschil; de bestaande
   installatie blijft ongewijzigd als terugval. De huidige server is **Emby**: B03-015 (overname vanuit Emby) en
   JLT-70…74 hebben prioriteit P0 en starten al in golf 0 tegen stock 12.4 met een echte Emby-container. "Het belangrijkste
   is mijn kijkgeschiedenis; als alles werkt verwijder ik Emby." Emby verwijderen doet de gebruiker zelf, na de
   controlelijst van bouwplan §10.9.2.

## 2. Overzicht

```
P0–P3 (lopend, andere repos) ─────────────────────────────────────────────────────────────────────────────▶
   └─ golf 0 (nu, tegen stock 12.4): corpus, harnas, voormetingen, spikes zonder 12.x;
      Emby-overname-proefrun met een echte Emby-container (B03-015, JLT-70…73; P0 van de gebruiker)
P4-0  upgrade 12.x + overname-procedure + definitieve baselines  ── gate P4-0 (incl. Δ-MG-AUTH per server + Δ-MG-DUAL)
P4    golf 1  gemeenschappelijke basis (pluginlaag, werker, planner, MG-client)   ── gate golf 1
      golf 2  eerste functiekernen (F1-decorator, F2-engine, F5-waarneming + HW-assistent, F6-engine)
      golf 3  functies af (F1, F3 klassiek, F4 niveaus, F6 cues, streamroute-spike)
      golf 4  web/clients/Hub en patches (F5 lanes/leren, F6 knoppen/correctie, F2 webrij, Hub-kaarten)
P5    lokale AI (F3 vertaling, F2 embeddings, F4 STT-taal, F6 lokale AI) — optioneel, standaard uit
P6 / cutover  NAS-acceptatie: JLT-06, -15, -26, -39, -49, -59, -69, -74; B03-015 echt (vanuit Emby, laatste delta,
              akkoord); B03-013 eindproef; daarna de controlelijst "Emby verwijderen" (de gebruiker voert uit)
```

## 3. Golven en werkpakketten

| Golf / fase | Wanneer | Werkpakketten | Opleverbaar | Gate (alles aantoonbaar) |
|---|---|---|---|---|
| **Golf 0** | nu, parallel aan P0–P3; tegen stock `jellyfin/jellyfin:12.4@sha256:fea863d0…1771` | **B03-015 deel A (P0, gebruiker): overname vanuit Emby** — eerst JellyPlex-Watched beoordelen, dan de overnametool en een herhaalbare proefrun met een echte Emby-container (`emby/embyserver:4.10.2.0@sha256:7082c63b…65cc1`, of de NAS-versie zodra D07 die meet); B03-016 (corpusgenerator, clientmatrix, harnasraamwerk, desktop-spike), B03-020, B03-030, B03-060, B03-070, F3-nulmeting (golf 0 van F3), F4-QC-G0 (testset T-QC, N-QC-rommelig; voorbereiding B03-052/054) | overnametool (alleen-lezen tegen Emby) met droog rapport, afhandellijst en vóór/na-rapport per gebruiker; één harnasraamwerk met meetprotocol; bevroren testsets met sha256-manifest; voormetingen (a) en (b) per functie; spikes S-IS (Intro Skipper op 12.x), desktop onder Xvfb, tablet-AVD | **JLT-70…73 Sim-geslaagd** (100 % gezien-status en hervatpunten van de gekoppelde items, rest op de afhandellijst; tweede run 0 schrijfacties; 0 schrijfacties naar Emby); voormetingen reproduceerbaar (≥ 3 runs, loadavg); testsets bevroren vóór het afstemmen; CI-guard testdatalicenties werkt |
| **P4-0** | na de P0-afronding (contract 1.2, rode CI's), vóór elk B03-modulewerk | B03-014, B03-015 (Emby-overname herhaald tegen jelly-leon:12.x; Jellyfin-procedure + proef op een kopie als D07 die meet), B03-016 (definitieve baselines), B03-019 (register `UPSTREAM_GEDRAG.md` + compat-rooktest) | jelly-leon en jelly-leon-web op 12.x; plugin op `net10.0`; `JL_RUNTIME_IMAGE` 12.x; overnameprocedure; Δ-MG-AUTH per server en Δ-MG-DUAL bij MediaGuard | §4 "Gate P4-0" |
| **Golf 1** | begin P4 | B03-017 (pluginlaag + ADR + prototype), B03-018 (werker, bestandspas, planner, budgetbeslisser, belastingtest), B03-009 (viewerclient), B03-010 (deel IsKid), IStartupFilter-spike | één plugin met modules; connector, outbox, foutcatalogus, Hub-pin (JL4), geheimenmap, UserDeleted, analyzer, haakmodule, config.json-generator; werker met SBOM; planner; gecombineerde belastingtest | §4 "Gate golf 1" |
| **Golf 2** | P4 | F1 B03-021 (decorator-spike); F2 B03-031…035; F5 B03-061, B03-062, spikes F5-S2; F6 B03-071, B03-072, B03-073 (de aanvulling op B03-007 begint hier en loopt tot golf 4) | eerste werkende modules met eigen opslag en API; HW-assistent; segmentengine met post-credit-bescherming | WT-1-gate (decorator of core-patch), G-F2-1…5, F5-S1/F5-S3, F6-S1–F6-S3 (o.a. JLT-51 nultolerantie) |
| **Golf 3** | P4 | F1 B03-022…027; F3 B03-040, 041, 042, 043, 047 (3A/3B, klassiek: inventaris, toolkit, sync, publicatie zonder vertaling); F4 B03-050…057 (QC-0…QC-5); F6 B03-074; B03-010 (spike streamroutes) | Watch Together compleet (behalve chat/Hub); ondertitelsync en publicatie zonder model; kwaliteitscontrole niveau 0/1/1,5/2/3; families/cues | JLT-03/05/07/08, JLT-20/22/23/24, JLT-30…37, JLT-53/57 |
| **Golf 4** | P4 | F1 B03-028 (na BG-12), B03-029; F2 B03-036, 037, 039; F3 B03-049 (P4-deel); F4 B03-058; F5 B03-004/005 (aanvullingen), B03-063…069; F6 B03-075…078 en de afronding van B03-007 (aanvulling) | webhaken, clientpatches, lanewrapper, leren met bevestiging, correctie-editor, skipknoppen, Hub-kaarten (na JL4 en Hub P2/P3) | JLT-09/14/38/41…48/54…56/58, compat JLT-63/64 per oplevering |
| **P5** | na P4; samen met de P5-modelapps uit contract §1/§2 | F2 B03-038; F3 B03-044, 045, 046, 048, 049 (rest); F4 B03-059; F6 B03-079 | optionele modelapps (mt, stt, embeddings) met één producent per soort; vertaalpijplijn met gekalibreerde score | JLT-18, JLT-21, JLT-27, JLT-28, JLT-29, JLT-32 (STT-deel); modellen standaard uit en terugval aangetoond |
| **P6 / cutover** | na P4 (en P5 voor de modeldelen) | NAS-testrijen JLT-06, -15, -26, -39, -49, -59, -69, -74; B03-015 echt (vanuit Emby: laatste delta, eindrapport, akkoord); B03-013 eindproef; B03-019 releasegate | echte overname met per-gebruikerrapport en akkoord; controlelijst "Emby verwijderen" klaar voor de gebruiker; metingen per render-node (D08); echte apparaten (D15) | alleen echte uitvoering; tot dan *Geblokkeerd* met NIET GEVALIDEERD |

**Doorlopend vanaf P4-0:** B03-019 (compat-regressie bij elke module-oplevering en elke upstream-sync), de upstream-sync-proef
naar elke nieuwe 12.y (JLT-67) en de B03-013-bijdragen per module.

## 4. Gates

### Gate P4-0 (vóór elk B03-modulewerk)
- B03-014 en B03-015 Sim-getest; JLT-70…73 Sim-geslaagd (Emby-overname, ook tegen jelly-leon:12.x); JLT-60, JLT-61
  (onderdelen a en b), JLT-62 en JLT-64 (met de bestaande plugin) Sim-geslaagd; JLT-63 rooktestdeel en JLT-67 Sim-geslaagd. De moduledelen van JLT-61 (c), JLT-64 en JLT-65 draaien
  pas als er modules zijn: per module-oplevering (B03-019) en als eindproef in P6 (bouwplan Bijlage B35).
- `JL_RUNTIME_IMAGE` op de 12.x-digest; `UPSTREAM_GEDRAG.md` bestaat met een werkende CI-runner.
- **Δ-MG-AUTH** (per server: Emby `X-Emby-Token`, Jelly Leon 12.x `Authorization: MediaBrowser Token=…`) en **Δ-MG-DUAL**
  (MediaGuard volgt Emby én Jelly Leon) opgeleverd met contracttest; de Emby-koppeling onderbreekt nooit. Zonder Δ-MG-AUTH mag P4 op de ontwikkelmachine verder (met een
  MediaGuard-simulator), maar draait er **geen B03-batch op de NAS** en toont Jelly Leon `mediaguard: onbekend`.
- Besluit legacy-auth (BG-01) vastgelegd; voorlopige manifestresources (4 CPU's, 4096 MiB, batchmodules standaard uit).
- Baselines (B03-016) opnieuw gemeten op exact de 12.x-tag en -digest van de forkbasis.
- **No-go:** een verschil in het per-gebruikerrapport zonder uitdrukkelijk akkoord van de gebruiker (HARDE EIS); terugzetten niet bewezen; stock-clients breken;
  `EnableLegacyAuthorization` weer aan zonder besluit.

### Gate golf 1 (vóór elk functiewerk in P4)
- ADR-B03-02 aanvaard en het prototype met twee modules bewezen (laadt op fork en stock; elke `/connector/v1`-route
  één keer); JLT-68 Sim-geslaagd; JLT-64 en JLT-65 Sim-geslaagd met de modules die dan bestaan (Core + prototype).
- Foutcatalogus-contracttest, analyzer en UserDeleted-test groen; geheimen niet in XML/export/log.
- Werker: smoketest, SBOM, geen auditok/torch/ctranslate2; groei van de image binnen de ADR-grens.
- Planner: pauze ≤ 5 s bij elke sessie; ≤ 2 threads en ≤ 1 GiB batch; JLT-66 Sim-geslaagd of de batchmodules blijven op
  de NAS uit tot het besluit over de resources (BG-07).
- **No-go:** dubbele routes, een gedeelde singleton die per module verschilt, OOM in de belastingtest.

### Gates per functie
De subfase-gates staan per functie in Fx.8 van het bouwplan (WT-0…WT-9, F2-0…F2-9, 3A…3E, QC-G0…QC-8, F5-S0…F5-S9,
F6-S0…F6-S9). Een functie mag "aantoonbaar beter" pas claimen als haar Fx.1-drempels tegen **stock-best** gehaald zijn op
dezelfde 12.x-digest, met n en Wilson-interval (anders *smoke-gate*), terwijl JLT-63/64/65 geen regressie tonen.

### Cutover-gate (P6) — "Jellyfin client/GPU testmatrix geslaagd"
- Echte overname vanuit Emby (B03-015, JLT-74) met vóór/na-rapport per gebruiker en uitdrukkelijk akkoord van de gebruiker
  op elk verschil; laatste delta bij de overstap; Emby blijft ongewijzigd draaien als terugval; ZFS-snapshot en
  terugzetproef op de NAS (HARDE EIS).
- Emby uit pas na de controlelijst "Emby verwijderen" (bouwplan §10.9.2: laatste delta, eindrapport + akkoord,
  ZFS-snapshot, blijvend JSON-exportarchief met sha256 in de back-updekking, MediaGuard laat Emby los) en een besluit van
  de gebruiker (APP-02, I26-26-02); de gebruiker verwijdert Emby zelf.
- D07, D08, D15 ingevuld; topologie A310/UHD 770 vastgesteld; meting per werkklasse per node (MediaGuard gepauzeerd en met
  last).
- NAS-testrijen uitgevoerd; Swiftfin/Safari blijven NIET GEVALIDEERD (Mac/Xcode) tot een echt apparaat.
- **No-go (uit 06_FASERING P4, ongewijzigd):** upstream clients breken, HDR/DV-verlies, media mutatie buiten MediaGuard,
  Jellyfin direct verwijderen.

## 5. Afhankelijkheden

| Van | Naar | Waarom |
|---|---|---|
| P0-afronding (contract 1.2, groene CI) | P4-0 | de upgrade bouwt op groene CI en contract 1.2 |
| B03-014 (12.x) | alles in P4 | plugin-ABI 12.x, .NET 10, webpaden legacy/modern |
| Δ-MG-AUTH per server + Δ-MG-DUAL (media-guard-ultimate) | B03-batch op de NAS; F1/F5 kijkpauze en G8; cutover | 12.x zet legacy-auth uit; MediaGuard moet Emby én Jelly Leon volgen |
| B03-016 (corpus) + echte Emby-container | B03-015 golf 0 (JLT-70…73) | proefrun met echte media en synthetische gebruikers |
| D07 (Emby gemeten op de NAS) | B03-015 echt (JLT-74) | versie, gebruikers, bibliotheken, mountpaden |
| B12 + Δ-HUB-3 | controlelijst "Emby verwijderen" | blijvend exportarchief in de back-updekking |
| B03-016 (corpus, harnas) | alle baselinerijen (020/030/060/070) en alle gates | eerlijke vergelijking, bevroren testsets |
| B03-017 (pluginlaag) | alle modules | één connector, foutcatalogus, gegevensbescherming |
| B03-018 (werker, planner) | F3, F4, F6 (batch); F5 (budget); F1 (lane vasthouden) | één budget, één bestandspas |
| B03-009 (viewerclient) | F3, F4, F5, F6 MediaGuard-delen | één client, witte lijsten |
| B03-010 (IsKid; streamroutes) | F1–F6 kinderregels; F1 VPN-gasten (B03-027) | één definitie; ADR-0009 |
| F3 B03-042 (syncmeter) | F4 B03-054; B03-008 | één meter |
| F5 B03-062 (HW-assistent) → B03-063/064 (lanes, budget) | F1 B03-025 (capaciteitsadvies) | headroom per werkklasse |
| F6 B03-071 (provider) | F1 groepsskip (H3) | skip onder SyncPlay |
| JL4-pin + Hub-adapter (Δ-HUB-JL, P3) | alle Hub-kaarten (029, 039, 049, 058, 069, 078) | zonder pin 401 `not_linked` |
| Δ-CONTRACT-MG | F3 "eerst menselijk zoeken", F4 herstel via de Hub | contract §2.3; tot dan deeplink |
| Δ-CONTRACT-MT / -MODEL | P5-delen F2, F3, F4, F6 | welke optionele app, één producent |
| B10-005 / I21 (Tailscale) + BG-09 | F1 B03-027 | geen open poorten zonder besluit |

**Voorrang (gebruiker):** B03-015 deel A (overname vanuit Emby) loopt vanaf golf 0 parallel en heeft voorrang bij een
conflict om de ontwikkelmachine; JLT-70…73 worden in P4-0 herhaald tegen jelly-leon:12.x en JLT-74 op de NAS.

**Kritiek pad:** P0-afronding → B03-014 (+ Δ-MG-AUTH) → B03-016 definitief → B03-017 + B03-018 (prototype en
belastingtest) → per functie golf 2 → golf 3 → golf 4 → NAS-gate. F5 B03-062 (HW-assistent, gemeten ≈ 25× minder CPU per
HDR-transcode op de ontwikkelmachine) en F6 B03-071…073 hebben de hoogste gebruikerswaarde per inspanning en staan daarom
in golf 2.

## 6. Middelen op de ontwikkelmachine

- Hooguit **één zware stap tegelijk**: emulator, Gradle, docker-build of een stack met vaste poorten, onder respectievelijk
  `gradle.lock`, `docker-build.lock` en `stack.lock`. Metingen alleen in een exclusief meetslot.
- Emulators alleen in een container met `--device /dev/kvm` en 4 GiB (de gebruiker `transcode` zit niet in de groep kvm;
  zie BG-38).
- Testsets on demand genereren en daarna opruimen; alleen het sha256-manifest blijft (schijf 89 % vol).
- De Meteor Lake-iGPU telt als functioneel bewijs en bovengrens, nooit als capaciteit van de A310 of UHD 770.

## 7. Prioriteiten

- **P0 (17):** de basis en de bescherming — B03-004, -005, -009, -010 (bestaand), B03-014…019 (gemeenschappelijk),
  B03-034 (kinderprofiel aanbevelingen), B03-043 (MediaGuard-voorrang ondertitels), B03-047 (opslag en spoorkeuzes),
  B03-050 (alleen-lezen-fundament kwaliteit), B03-053 (planner-jobtypes kwaliteit), B03-060 (baseline apparaten),
  B03-068 (bescherming stock-clients).
- **P2 (7):** B03-028 (chat), B03-038 (embeddings), B03-039 (Hub-kaart/release F2), B03-059 (STT-taal), B03-069 (native
  clients + Hub F5), B03-077 (clientpatches skipknoppen), B03-079 (lokale AI segmenten).
- **P1:** al het overige (48 rijen).
- **Testrijen P0 van de gebruiker:** JLT-70…74 (overname vanuit Emby: kijkgeschiedenis). De prioriteit per testrij staat
  in `EXCEL_TAKEN_PER_REPO.json` (`per_test.<ID>.prioriteit`).

## 8. Voorgestelde tekstwijzigingen (voor de eigenaar ai-server-manager)

### 8.1 `OVERDRACHT/OVERDRACHT_PROMPT.md` §4 — de regels P4 en P5

**Nu:**
> - **P4:** B03 in jelly-leon, jelly-leon-web, jelly-leon-clients (plugins vóór core-patches), manifests I06/I22/I24.
> - **P5:** B10, B07, B15, B08-005/006, B01-010/012, B02-009, manifests I11/I12/I14/I21/I25/I26 + lokale modellen.

**Voorstel:**
> - **P4-0 (nieuw, vóór P4):** upgrade jelly-leon + jelly-leon-web naar de nieuwste stabiele Jellyfin 12.x (ADR-0011; B03-014),
>   overname vanuit de bestaande mediaserver — **Emby**, en Jellyfin als D07 dat meet — met een vóór/na-rapport per
>   gebruiker en akkoord van de gebruiker op elk verschil (B03-015; HARDE EIS), definitieve stock-baselines op dezelfde
>   12.x-digest (B03-016), register `UPSTREAM_GEDRAG.md` (B03-019). Exitcriterium: Δ-MG-AUTH per server en Δ-MG-DUAL in
>   media-guard-ultimate; zonder Δ-MG-AUTH geen B03-batch op de NAS. Golf 0 (corpus, harnas, voormetingen tegen stock 12.4
>   en — met voorrang, P0 van de gebruiker — de Emby-overname-proefrun JLT-70…73 met een echte Emby-container) mag al
>   parallel aan P0–P3.
> - **P4:** B03 in jelly-leon, jelly-leon-web, jelly-leon-clients (plugins vóór core-patches), in golven: golf 1
>   gemeenschappelijke basis (één plugin met modules, connector/Hub-pin JL4, foutcatalogus, MediaGuard-viewerclient,
>   analysewerker, globale planner, belastingtest; B03-009/010/017/018); golf 2–4 de zes functies F1–F6 (Watch Together,
>   aanbevelingen, ondertitels klassiek, kwaliteitscontrole, apparaatprofielen, intro/outro/recap; B03-004/005/007 en
>   B03-020…079 zonder de P5-rijen); patches en Hub-kaarten in golf 4; manifests I06/I22/I24. Ontwerpstap en -review
>   alleen voor de Hub-kaarten (Jelly Leon zelf valt buiten de ontwerptaal).
> - **P5:** B10, B07, B15, B08-005/006, B01-010/012, B02-009, manifests I11/I12/I14/I21/I25/I26 + lokale modellen, **plus de
>   P5-delen van B03** (B03-038, B03-044…046, B03-048, B03-049-rest, B03-059, B03-079) met één producent per modelsoort
>   (Δ-CONTRACT-MODEL, Δ-CONTRACT-MT); alles optioneel en standaard uit.
> - **P6:** ongewijzigd, plus de NAS-testrijen van B03 (JLT-06/15/26/39/49/59/69/74), de echte overname vanuit Emby met
>   laatste delta en akkoord (B03-015), de terugzetproef B03-013 en de controlelijst "Emby verwijderen" (de gebruiker
>   verwijdert Emby zelf, APP-02/I26-26-02).

### 8.2 `01_ARCHITECTUUR/06_FASERING_EN_GATES.md`

**Nieuwe sectie tussen P3 en P4:**
> ## Fase P4-0 — Jellyfin 12.x als basis
> **Doel:** server en web van de fork naar de nieuwste stabiele Jellyfin 12.x (.NET 10) vóór er B03-functies gebouwd
> worden; de kijkgeschiedenis uit de bestaande mediaserver (Emby; ook Jellyfin als D07 dat meet) veilig overnemen;
> eerlijke baselines van standaard Jellyfin op dezelfde versie.
> **Opgeleverd:** jelly-leon en jelly-leon-web op 12.x met groene CI, plugin op 12.x, terugzetproef (vorige image +
> DB-snapshot), Emby-overname (alleen-lezen) en proefmigratie op een kopie met een per-gebruikerrapport en akkoord,
> baselines (stock-standaard en stock-best), register van upstream-gedrag, MediaGuard volgt Emby én Jelly Leon zonder
> legacy-auth (Δ-MG-AUTH per server, Δ-MG-DUAL).
> **No-go:** een verschil in kijkgeschiedenis of rechten zonder uitdrukkelijk akkoord van de gebruiker (HARDE EIS),
> terugzetten niet bewezen, een schrijfactie naar Emby, stock-clients breken, legacy-auth weer aan zonder besluit,
> B03-batch op de NAS zonder Δ-MG-AUTH.

**Fase P4 — aangepast (toegevoegde zinnen vet):**
> **Doel:** Jellyfin plugin/adapter eerst, daarna minimaal onderhouden fork, streaming matrix, A310 scheduling, scene search,
> live-tv/DVR, offline apps waar haalbaar. **Daarbij de zes uitbreidingen Watch Together, aanbevelingen, ondertitels
> (klassiek), kwaliteitscontrole, apparaatprofielen en intro/outro/recap als modules van één plugin, in golven
> (gemeenschappelijke basis eerst).**
> **Opgeleverd:** echte playbacktests, TV/client compat, intacte watch history, MediaGuard request links. **Per functie een
> meetbare winst tegen stock-standaard én stock-best op dezelfde 12.x-digest; compat-regressie per clientrol; differentiële
> gegevensbeschermingsrun.**
> **No-go:** upstream clients breken, HDR/DV verlies, media mutatie buiten MediaGuard, Jellyfin direct verwijderen. **Ook:
> een afspeelstart van een stock-client weigeren of verlagen; schrijven in kijkgeschiedenis buiten het besluit BG-21 en de
> eenmalige overname van B03-015; Emby uitzetten of verwijderen vóór de controlelijst "Emby verwijderen";
> B03-batch op de A310 terwijl MediaGuard daar encodeert; een winstclaim zonder baseline of op een niet-bevroren testset.**

**Fase P5 — aangepast (toegevoegd):**
> **Doel:** … **plus de optionele lokale AI van B03 (vertaling, embeddings, spraakherkenning voor taal en segmenten).**
> **Opgeleverd:** … **met één producent per modelsoort en een aangetoonde klassieke terugval.**
> **No-go:** … **een model in de jelly-leon-image; een model-app op de A310; een NC-gelicentieerd model.**

**Gate matrix — nieuwe regels:**
> | Δ-MG-AUTH per server + Δ-MG-DUAL + proefmigratie 10.11 → 12.x op een kopie geslaagd | Voor P4 (B03-functies) |
> | Emby-overname JLT-70…73 Sim-geslaagd (golf 0, herhaald in P4-0) | Voor P4 (B03-functies) |
> | Vóór/na-rapport per gebruiker + uitdrukkelijk akkoord op elk verschil (HARDE EIS) | Voor elke cutover |
> | Controlelijst "Emby verwijderen" (laatste delta, eindrapport + akkoord, ZFS-snapshot, exportarchief, MediaGuard los) | Voor Emby uit (de gebruiker beslist en voert uit) |
> | Eén plugin met modules + belastingtest binnen de manifestresources | Voor B03-batch op de NAS |
> | Hub-sleutelpin in Jelly Leon (JL4) | Voor Hub-kaarten van B03 |
> | Δ-CONTRACT-MG | Voor herstel/zoeken in MediaGuard via de Hub |

### 8.3 Excel — blad Fasen (via Δ-ASM-EXCEL)

Nieuwe rij tussen P3 en P4:

| Fase | Beschrijving | Go / No-go voor volgende fase | Status | Validatie |
|---|---|---|---|---|
| P4-0 | Upgrade Jelly Leon server + web naar Jellyfin 12.x; overname vanuit de bestaande mediaserver (Emby; ook Jellyfin als D07 dat meet) met vóór/na-rapport per gebruiker; terugzetten (snapshot + vorige image); baselines standaard Jellyfin | Geen verschil in kijkgeschiedenis of rechten zonder uitdrukkelijk akkoord van de gebruiker (HARDE EIS); Emby blijft ongewijzigd als terugval; terugzetten bewezen; Δ-MG-AUTH per server + Δ-MG-DUAL; stock-clients werken | Niet gestart | — |

En op de bladen Werkpakketten en Testmatrix de rijen uit `excel_taken_nieuw.json` en `testmatrix_nieuw.json` (bestaande
B03-004/005/007/009/010/013 vervangen door de uitgebreide versie; de rijen hebben exact de velden van `tasks.json` en de
wijzigingsnotitie staat in `EXCEL_TAKEN_PER_REPO.json`, veld `per_rij.<ID>.wijziging`), met de Prioriteit per
JLT-rij uit `EXCEL_TAKEN_PER_REPO.json`.

**Uitgevoerd op 2026-11-09** met `tools/excel/update_excel.py` (Δ-ASM-EXCEL) en de invoer in
`ai-server-manager/docs/platform-v2/08_EXCEL/b03/` (`werkpakketten.json`, `testen.json`, `EXCEL_TAKEN_PER_REPO.json`,
`fasen.json`): 66 nieuwe en 6 vervangen werkpakketten, 74 testrijen (JLT-01…74; de 8 NAS-rijen JLT-06/15/26/39/49/59/69/74
op *Geblokkeerd*) en de rij P4-0.
