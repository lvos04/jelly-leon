# B03 — Besluiten van de gebruiker: genomen en nog open

Samengevoegd op 2026-11-09 bij het verwerken van het goedgekeurde B03 2.0-plan, uit `BESLUITEN_GENOMEN.md` en
`BESLUITEN_VOOR_GEBRUIKER.md` van de synthese. Hoort bij `B03_UNIVERSELE_MEDIASERVER.md` (bouwplan) en `B03_FASERING.md`.
**Een genomen besluit gaat voor het advies.** Een open besluit wordt pas gevraagd als de fase of golf begint; tot dan geldt de
veiligste stand ("Zonder besluit" in §3), nooit automatisch het advies.

## 1. Genomen besluiten (2026-11-09, via keuzemenu)

- **HARDE EIS van de gebruiker:** alle kijkgeschiedenis (gezien-status, hervatpunten, favorieten, beoordelingen, onthouden
  spoorkeuzes, gebruikers, rechten) en de MediaGuard-voortgang blijven altijd beschikbaar. Gevolg: B03-015 — geen cutover
  zonder vóór/na-rapport per gebruiker én uitdrukkelijk akkoord van de gebruiker op elk verschil (ook verschillen door
  upstream-migraties zoals HarmonizeConflictingUserData/MergeDuplicatePeople); de bestaande installatie blijft ongewijzigd als
  terugval. MediaGuard: nieuwe releases (ook de eerste uit de nieuwe publieke repo) bewijzen een upgrade op een gevulde database
  van de vorige versie zonder gegevensverlies; UI-rondes wijzigen geen datamodel.
- **BG-01:** MediaGuard omzetten naar `Authorization: MediaBrowser Token=…` (Δ-MG-AUTH); EnableLegacyAuthorization blijft uit;
  derden-apps eerst testen.
- **BG-02:** geen release meer op 10.11.11; eerste Jelly Leon-release op 12.x; P4-0 als eigen fase (eigen rij op blad Fasen).
- **BG-32:** Intro Skipper alleen als ongewijzigde vergelijkingsbasis in een testcontainer; externe segmentdatabases uit;
  bestaande segmenten uit de huidige installatie eenmalig als hint (met voorbeeld vooraf).
- **BG-34:** de gebruiker (of een aangewezen persoon) labelt de echte afleveringen; de bouwer levert een eenvoudig labelscherm.
- **BG-37:** MovieLens (alleen lokaal) ja; Pioneer One (alleen lokaal) ja; eenmalige evaluatie op de echte kijkhistorie (na
  B03-039; samengevat rapport, afmelden kan, kinderen nooit) ja; TMDb in een wegwerpcontainer met alleen publieke MovieLens-ID's
  ja; Netflix-4K/DV-masters niet zolang de schijf vol is.
- **BG-38:** tijdelijke meetdata opgeruimd; testsets on demand maken en daarna weggooien (alleen recept/manifest blijft);
  Android-systeemimages blijven; gebruiker `transcode` toegevoegd aan de groepen render en kvm (actief na opnieuw inloggen).
- Overige BG-03…BG-31, BG-33, BG-35, BG-36: worden gevraagd als hun fase/golf begint (zie BESLUITEN_VOOR_GEBRUIKER.md).

### Emby (gebruiker, 2026-11-09)

- **Feit (gebruiker):** de gebruiker gebruikt nu **Emby** als mediaserver; de kijkgeschiedenis staat in Emby. Versie, plugins,
  gebruikers en bibliotheken zijn nog niet gemeten (D07 blijft Open tot de wizard/TrueNAS-API het meet).
- **Besluit Emby:** Emby blijft ongewijzigd draaien (ook als terugval). Gezien-status, hervatpunten, favorieten (en waar
  mogelijk beoordelingen en onthouden spoorkeuzes) worden per gebruiker van Emby naar Jelly Leon overgezet — alleen-lezen
  uit Emby (API-sleutel), herhaalbare proefrun, vóór/na-rapport per gebruiker, akkoord van de gebruiker op elk verschil, en
  een laatste delta-overzetting bij de overstap. Wachtwoorden zijn niet over te zetten (nieuw wachtwoord of SSO). Pas als
  Jelly Leon aantoonbaar hetzelfde doet (APP-02, I26-26-02) besluit de gebruiker of Emby uit mag; data verwijderen staat los
  van stoppen.
- **Besluit MediaGuard:** MediaGuard volgt **Emby én Jelly Leon tegelijk** (kijkpauze als iemand op één van beide kijkt,
  afspeeltest en NL-ondertitels per server). Gevolg: Δ-MG-AUTH wordt per server (Emby blijft `X-Emby-Token`, Jelly Leon 12.x
  `Authorization: MediaBrowser Token=…`) en er komt Δ-MG-DUAL (meerdere mediaservers tegelijk). De bestaande Emby-koppeling
  mag op geen enkel moment onderbreken.
- **Prioriteit (gebruiker):** "Het belangrijkste is mijn kijkgeschiedenis; als alles werkt verwijder ik Emby." Gevolg:
  B03-015 (Emby-overname) en JLT-70…74 krijgen prioriteit P0 en worden al in golf 0 tegen stock 12.4 met een echte
  Emby-container beproefd. Doel: 100 % van gezien-status en hervatpunten overgezet; wat niet automatisch te koppelen is
  staat op een afhandellijst voor de gebruiker (nooit stil weggelaten).
- **Emby verwijderen doet de gebruiker zelf**, pas na een vaste controlelijst: (1) laatste delta-overzetting, (2) eindrapport
  per gebruiker met akkoord, (3) ZFS-snapshot van de Emby-configuratie/-dataset, (4) blijvend exportbestand (JSON) van alle
  kijkgegevens per gebruiker uit Emby, met sha256, als archief op de NAS (en in de back-updekking), zodat de geschiedenis ook
  na het verwijderen opnieuw te importeren is, (5) MediaGuard laat Emby netjes los en volgt alleen Jelly Leon. App stoppen en
  data verwijderen blijven aparte stappen (APP-02/A4).

## 2. Open besluiten — wanneer ze gevraagd worden

| Wanneer (fase of golf, zie `B03_FASERING.md`) | Besluit | Advies in één regel |
|---|---|---|
| P4-0 (overname) | **BG-22** — Bazarr-vertaler en Jellyfin-ondertiteldownloaders | Bazarr-vertaler niet voor NL; Jellyfin-downloaders niet installeren |
| vóór golf 1 | **BG-03** — Wat is een kinderprofiel? | automatisch voorstellen, beheerder bevestigt |
| vóór golf 1 | **BG-04** — Waar voer je de MediaGuard-sleutel in? | in Jelly Leon zelf, alleen leesrechten |
| na golf 1 | **BG-07** — Resources van de jelly-leon-app | eerst meten; batch alleen binnen het gemeten budget |
| golf 2 | **BG-16** — Kijkgedrag van gezinsleden en een fijnere kijklog | opt-in, standaard uit; fijnere log uit |
| golf 2 | **BG-27** — A310 voor live kijken terwijl MediaGuard encodeert; meten | ja, binnen een grens; jij pauzeert MediaGuard zelf voor de meting |
| golf 2 | **BG-33** — Wie mag tijdcodes corrigeren; schaduwmodus | beheerders + aangewezen volwassenen; eerst schaduwmodus |
| golf 2 | **BG-35** — Hardware-decode voor de beeldanalyse | alleen de UHD 770, en pas na D08 |
| golf 2 | **BG-36** — Module uit: eigen segmenten wissen of verbergen | wissen (herstelbaar uit de eigen database) |
| vóór golf 3 (anders deeplinks) | **BG-05** — Mag de Hub MediaGuard laten herstellen of zoeken? | ja, via een contractwijziging en goedkeuring per actie |
| golf 3 | **BG-10** — Watch Together op Android TV en Swiftfin | volgmodus (± 2 s), geen grote clientpatch |
| golf 3 | **BG-11** — Wie ziet een nieuwe kijkgroep? | huishouden |
| golf 3 | **BG-13** — Haperende deelnemer en volle GPU's bij een groepstart | na 10 s doorgaan; bij een groepstart alleen waarschuwen |
| golf 3 | **BG-14** — Watch Together-knoppen ook in de oude weergave | alleen in Modern |
| golf 3 | **BG-19** — Opslag, naam en levensduur van machinevertalingen | in Jelly Leon zelf, label "Machinevertaling", verbergen als er een menselijke komt |
| golf 3 | **BG-21** — Onthouden audio-/ondertitelkeuzes bij een nieuw spoor | eerst `hold` (niets schrijven), later `reset` |
| golf 3 | **BG-23** — Volledige decodecontrole voor de hele bibliotheek | nee: steekproef voor alles, volledig voor nieuw/vervangen |
| golf 3 | **BG-24** — Bewijs-miniaturen, label, "Meld een probleem", home video's | miniaturen op verzoek; label uit; melden later aan; home video's uit |
| golf 3 | **BG-25** — Gecorrigeerde ondertitelkopie bij slechte sync | alleen op verzoek, nooit automatisch |
| vóór B03-027 (golf 3) | **BG-09** — Watch Together met mensen buiten huis | nu alleen thuis; later VPN voor eigen apparaten |
| vóór golf 4 | **BG-08** — Swiftfin (iPhone/iPad/Apple TV) | geen eigen patches in v1 |
| golf 4 | **BG-12** — Chat en reacties tijdens samen kijken | uit |
| golf 4 | **BG-15** — Rij "Aanbevolen voor jou" op het startscherm | ja, via één kleine webhaak; Android TV later |
| golf 4 | **BG-26** — Afspeelprofiel aanpassen voor officiële apps en stock-tv-apps | alleen met opt-in per apparaat, alleen beperkend |
| golf 4 | **BG-28** — Volle of uitgevallen GPU's | standaardgedrag; lagere kwaliteit alleen opt-in; software-voorstel met één klik |
| golf 4 | **BG-29** — Kwaliteitslabel en wanneer de speler om feedback vraagt | label alleen bij afwijking; feedback alleen bij falen |
| golf 4 | **BG-30** — Android TV-patch voor het automatische capabilityrapport | ja, na de eigen app-ID, prioriteit P2 |
| golf 4 | **BG-31** — Skipknoppen: tekst en standaardgedrag | exact "Sla intro over / samenvatting / aftiteling over"; overal vragen, nooit automatisch |
| bij B03-006 | **BG-17** — Online metadata (TMDb/OMDb) | aan laten, met de bekende privacykosten; keuze in B03-006 |
| vóór P5 | **BG-06** — Optionele lokale modellen: welke apps, wie maakt wat | één producent per soort; voorlopig geen embeddings |
| vóór P5 | **BG-18** — Vertaalmotor en licentie van het vertaalmodel | OPUS-MT in een aparte app `mt`, standaard uit; LLM alleen Apache-2.0/MIT |
| P5 | **BG-20** — Automatisch vertalen en publiceren | beide uit; 72 uur wachten op MediaGuard/Bazarr |

Genomen: BG-01, BG-02, BG-32, BG-34, BG-37, BG-38. Open: 32 besluiten.

### 2.1 Open punten over Emby (geen BG-ID; bestaande Excel-rijen en B03-015)

| Punt | Wie | Wanneer | Waar |
|---|---|---|---|
| Akkoord op elk verschil in het vóór/na-rapport per gebruiker (HARDE EIS) | de gebruiker | bij elke proefrun en bij de echte overname | B03-015 (A8), JLT-70, JLT-74 |
| Per gebruiker een nieuw wachtwoord of SSO (Authentik, B13); wachtwoorden zijn niet over te zetten | de gebruiker | vóór de echte overname (P6/cutover) | B03-015 (A4) |
| Emby stoppen (proefstop) en later, apart, Emby-data verwijderen | de gebruiker, zelf | pas na JLT-74 en de controlelijst "Emby verwijderen" (bouwplan §10.9.2) | APP-02, I26-26-02 |
| Hergebruik van JellyPlex-Watched of een eigen overnametool | de bouwer (ADR in jelly-leon), geen gebruikersbesluit | golf 0 | B03-015 (A2) |

## 3. Alle besluiten in detail (opties, advies, zonder besluit, raakt)

### Overzicht

| ID | Besluit | Advies in één regel | Wanneer nodig | Status |
|---|---|---|---|---|
| BG-01 | MediaGuard-koppeling na de upgrade naar 12.x | MediaGuard omzetten (Δ-MG-AUTH); legacy-auth blijft uit | vóór P4-0 | genomen |
| BG-02 | Release vóór de upgrade en P4-0 in de Excel | geen release meer op 10.11.11; P4-0 als eigen fase | vóór P4-0 | genomen |
| BG-03 | Wat is een kinderprofiel? | automatisch voorstellen, beheerder bevestigt | vóór golf 1 | open |
| BG-04 | Waar voer je de MediaGuard-sleutel in? | in Jelly Leon zelf, alleen leesrechten | vóór golf 1 | open |
| BG-05 | Mag de Hub MediaGuard laten herstellen of zoeken? | ja, via een contractwijziging en goedkeuring per actie | vóór golf 3 (anders deeplinks) | open |
| BG-06 | Optionele lokale modellen: welke apps, wie maakt wat | één producent per soort; voorlopig geen embeddings | vóór P5 | open |
| BG-07 | Resources van de jelly-leon-app | eerst meten; batch alleen binnen het gemeten budget | na golf 1 | open |
| BG-08 | Swiftfin (iPhone/iPad/Apple TV) | geen eigen patches in v1 | vóór golf 4 | open |
| BG-09 | Watch Together met mensen buiten huis | nu alleen thuis; later VPN voor eigen apparaten | vóór B03-027 (golf 3) | open |
| BG-10 | Watch Together op Android TV en Swiftfin | volgmodus (± 2 s), geen grote clientpatch | golf 3 | open |
| BG-11 | Wie ziet een nieuwe kijkgroep? | huishouden | golf 3 | open |
| BG-12 | Chat en reacties tijdens samen kijken | uit | golf 4 | open |
| BG-13 | Haperende deelnemer en volle GPU's bij een groepstart | na 10 s doorgaan; bij een groepstart alleen waarschuwen | golf 3 | open |
| BG-14 | Watch Together-knoppen ook in de oude weergave | alleen in Modern | golf 3 | open |
| BG-15 | Rij "Aanbevolen voor jou" op het startscherm | ja, via één kleine webhaak; Android TV later | golf 4 | open |
| BG-16 | Kijkgedrag van gezinsleden en een fijnere kijklog | opt-in, standaard uit; fijnere log uit | golf 2 | open |
| BG-17 | Online metadata (TMDb/OMDb) | aan laten, met de bekende privacykosten; keuze in B03-006 | bij B03-006 | open |
| BG-18 | Vertaalmotor en licentie van het vertaalmodel | OPUS-MT in een aparte app `mt`, standaard uit; LLM alleen Apache-2.0/MIT | vóór P5 | open |
| BG-19 | Opslag, naam en levensduur van machinevertalingen | in Jelly Leon zelf, label "Machinevertaling", verbergen als er een menselijke komt | golf 3 | open |
| BG-20 | Automatisch vertalen en publiceren | beide uit; 72 uur wachten op MediaGuard/Bazarr | P5 | open |
| BG-21 | Onthouden audio-/ondertitelkeuzes bij een nieuw spoor | eerst `hold` (niets schrijven), later `reset` | golf 3 | open |
| BG-22 | Bazarr-vertaler en Jellyfin-ondertiteldownloaders | Bazarr-vertaler niet voor NL; Jellyfin-downloaders niet installeren | P4-0 (overname) | open |
| BG-23 | Volledige decodecontrole voor de hele bibliotheek | nee: steekproef voor alles, volledig voor nieuw/vervangen | golf 3 | open |
| BG-24 | Bewijs-miniaturen, label, "Meld een probleem", home video's | miniaturen op verzoek; label uit; melden later aan; home video's uit | golf 3 | open |
| BG-25 | Gecorrigeerde ondertitelkopie bij slechte sync | alleen op verzoek, nooit automatisch | golf 3 | open |
| BG-26 | Afspeelprofiel aanpassen voor officiële apps en stock-tv-apps | alleen met opt-in per apparaat, alleen beperkend | golf 4 | open |
| BG-27 | A310 voor live kijken terwijl MediaGuard encodeert; meten | ja, binnen een grens; jij pauzeert MediaGuard zelf voor de meting | golf 2 | open |
| BG-28 | Volle of uitgevallen GPU's | standaardgedrag; lagere kwaliteit alleen opt-in; software-voorstel met één klik | golf 4 | open |
| BG-29 | Kwaliteitslabel en wanneer de speler om feedback vraagt | label alleen bij afwijking; feedback alleen bij falen | golf 4 | open |
| BG-30 | Android TV-patch voor het automatische capabilityrapport | ja, na de eigen app-ID, prioriteit P2 | golf 4 | open |
| BG-31 | Skipknoppen: tekst en standaardgedrag | exact "Sla intro over / samenvatting / aftiteling over"; overal vragen, nooit automatisch | golf 4 | open |
| BG-32 | Intro Skipper, externe segmentdatabases en bestaande segmenten | Intro Skipper alleen als testbaseline; databases uit; bestaande segmenten eenmalig als hint | golf 0 | genomen |
| BG-33 | Wie mag tijdcodes corrigeren; schaduwmodus | beheerders + aangewezen volwassenen; eerst schaduwmodus | golf 2 | open |
| BG-34 | Wie labelt de echte afleveringen? | jij of een aangewezen persoon; reken op meer dan 1–2 uur | golf 0 | genomen |
| BG-35 | Hardware-decode voor de beeldanalyse | alleen de UHD 770, en pas na D08 | golf 2 | open |
| BG-36 | Module uit: eigen segmenten wissen of verbergen | wissen (herstelbaar uit de eigen database) | golf 2 | open |
| BG-37 | Testdata met een beperkende licentie | MovieLens en Pioneer One alleen lokaal; geen Netflix-masters; eenmalige evaluatie op echte historie | golf 0 | genomen |
| BG-38 | Ontwikkelmachine: opruimen en rechten | tijdelijke meetdata weg; Android-images houden; geen groepsrechten | nu | genomen |

---

### 1. Basis en platform

#### BG-01 — MediaGuard-koppeling na de upgrade naar Jellyfin 12.x
**Genomen (2026-11-09):** MediaGuard omzetten naar `Authorization: MediaBrowser Token=…` (Δ-MG-AUTH); EnableLegacyAuthorization blijft uit; derden-apps eerst testen.
**Vraag.** Jellyfin 12.x zet de oude aanmeldmethode uit (`EnableLegacyAuthorization` = false). MediaGuard gebruikt die nog
(`X-Emby-Token`), dus de koppeling breekt; daarmee vallen de kijkpauze van MediaGuard en de controle "hangt MediaGuard aan
deze Jelly Leon?" weg. Derden-apps (bijv. Kodi-add-ons, Infuse, Findroid) gebruiken mogelijk ook de oude methode — dat is
niet gemeten.
**Opties.** (a) MediaGuard omzetten naar `Authorization: MediaBrowser Token=…` (Δ-MG-AUTH) en legacy-auth uit laten;
(b) legacy-auth tijdelijk weer aanzetten. Gevolg (b): tokens kunnen weer als `api_key=` in URL's en logs staan; minder
veilig; voor derden-apps werkt het wel.
**Advies.** (a). Voor derden-apps eerst meten (één app in de testmatrix); pas als een app die je echt gebruikt (D15) faalt,
dit besluit opnieuw bekijken.
**Zonder besluit.** (a) wordt gevraagd aan MediaGuard; tot het er is: geen B03-batch op de NAS, status `mediaguard: onbekend`.
**Raakt.** B03-014, B03-019; JLT-60, JLT-63, JLT-67.

#### BG-02 — Release vóór de upgrade en P4-0 in de Excel
**Genomen (2026-11-09):** geen release meer op 10.11.11; eerste Jelly Leon-release op 12.x; P4-0 als eigen fase (eigen rij op blad Fasen).
**Vraag.** Komt er nog een release van Jelly Leon op 10.11.11, of gaat de eerste release direct op 12.x? En krijgt de
upgrade een eigen fase (P4-0) met eigen afvinkregels?
**Opties.** (a) geen release meer op 10.11.11; eerste release op 12.x; P4-0 als eigen rij op het blad Fasen; (b) eerst een
release op 10.11.11 (extra release- en testwerk, daarna toch migreren).
**Advies.** (a): B03 wordt toch op 12.x gebouwd (ADR-0011), een 10.11-release levert alleen extra migratiewerk op.
**Zonder besluit.** Geen release; de upgrade staat als P4-0 in het plan, maar nog niet in de Excel.
**Raakt.** B03-014; `FASERING.md` §8.3.

#### BG-03 — Wat is een kinderprofiel?
**Vraag.** Alle zes functies hebben kinderregels (geen gemengde groepen met externen, geen verborgen titels in uitleg,
geen correcties door kinderen). Wanneer is een gebruiker een kind?
**Opties.** (a) iedere gebruiker met een leeftijdsgrens (`MaxParentalRating`), geblokkeerde tags of een toegangsschema;
(b) alleen wie de beheerder als "kind" markeert; (c) beide: Jelly Leon stelt automatisch voor, de beheerder bevestigt.
**Advies.** (c). (a) kan volwassenen met een filter onterecht als kind behandelen; (b) vergeet makkelijk iemand.
**Zonder besluit.** de ruimste regel (a) geldt als veilige stand.
**Raakt.** B03-010 (uitgebreid), B03-017; F1 B03-023, F2 B03-034, F6 B03-075.

#### BG-04 — Waar voer je de MediaGuard-sleutel van Jelly Leon in?
**Opties.** (a) in Jelly Leon zelf (beheerpagina; de sleutel staat dan alleen in een afgeschermd bestand, nooit in de
plugin-instellingen); (b) via de Hub. Gevolg (b): kan pas als Jelly Leon aan de Hub gekoppeld is met geheimen-uitwisseling,
en dat bestaat in v1 niet (contract §2.3).
**Advies.** (a), met een sleutel met **alleen leesrechten** (viewer). Een sleutel met meer rechten weigert Jelly Leon.
**Raakt.** B03-009; F3–F6 MediaGuard-delen; JLT-37, JLT-45.

#### BG-05 — Mag de Hub MediaGuard laten herstellen of zoeken (na jouw goedkeuring)?
**Vraag.** Jelly Leon mag nooit zelf bestanden wijzigen. Herstel (opnieuw zoeken, vrijgavecontrole, een beschadigd bestand
opnieuw binnenhalen) en "eerst menselijke ondertitels zoeken" zijn van MediaGuard. Het contract staat de Hub bij MediaGuard
nu alleen "noodstop aan" toe.
**Opties.** (a) contractwijziging Δ-CONTRACT-MG: de Hub mag deze acties met jouw goedkeuring per actie laten uitvoeren
(terugzetten uit quarantaine blijft altijd handmatig in MediaGuard), plus MediaGuard-uitbreidingen Δ-MG-1 (bevindingen
innemen) en Δ-MG-2 (aanwezig bestand opnieuw binnenhalen); (b) niet: Jelly Leon toont alleen het probleem met bewijs en
een link naar MediaGuard.
**Advies.** (a), maar pas na P2/P3 (Hub-policy en MediaGuard-adapter). Tot dan geldt (b).
**Raakt.** B03-009, F3 B03-043, F4 B03-056/058; hoofdstuk 18.

#### BG-06 — Optionele lokale modellen: welke apps, en wie maakt wat?
**Vraag.** Het contract noemt een lokaal embeddingmodel en spraakherkenning als optionele apps, maar legt niet vast welke
app wat levert. Spraakherkenning is dubbel gepland (B03-008 en B07-004), embeddings ook (zoeken maakt ze al van de bron
"jellyfin").
**Opties.** Vertaling: (a) aparte optionele app `mt` (eventueel samen met het embeddingmodel). Embeddings: (a) Jelly Leon
maakt ze en zoeken leest; (b) zoeken maakt ze en Jelly Leon leest; (c) voorlopig geen. Spraak: één producent (Jelly Leon
of zoeken) voor B03-008, B07, de taalcontrole (F4) en de segmentdetectie (F6).
**Advies.** Embeddings voorlopig (c); komen ze er, dan (a) met hetzelfde model in beide apps. Eén spraakproducent: Jelly
Leon (eigenaar van de media-metadata). Alle model-apps standaard uit, zonder GPU of alleen op de UHD 770, nooit op de A310.
**Raakt.** Δ-CONTRACT-MODEL, Δ-CONTRACT-MT, Δ-ZK-2; B03-038, B03-044, B03-059, B03-079.

#### BG-07 — Resources van de jelly-leon-app
**Vraag.** Jelly Leon draait nu met 4 CPU's en 4 GiB. Opgeteld vragen de batchmodules (ondertitels, kwaliteit, segmenten)
plus live-transcodes mogelijk meer (geschat 4,4–5,5 GB; niet gemeten). Hoeveel RAM heeft de NAS?
**Opties.** (a) resources ophogen als de batchmodules aan staan; (b) strikt na elkaar binnen 4 CPU's / 4 GiB; (c) batch
alleen 's nachts.
**Advies.** Eerst de gecombineerde belastingtest (B03-018, JLT-66); tot dan (b), met de batchmodules op de NAS standaard
uit. Daarna een onderbouwd voorstel op basis van de NAS-RAM.
**Raakt.** B03-014, B03-018; JLT-66.

#### BG-08 — Swiftfin (iPhone, iPad, Apple TV)
**Vraag.** Swiftfin 1.6.1 heeft geen SyncPlay en geen skipknoppen. Eigen patches (MPL-2.0) zijn groot en hier niet te
testen (geen Mac/Xcode).
**Opties.** (a) in v1 accepteren: Watch Together via de volgmodus, geen skipknoppen; (b) later eigen Swiftfin-patches.
**Advies.** (a). Swiftfin blijft NIET GEVALIDEERD (Mac/Xcode).
**Raakt.** F1 B03-026, F6 B03-077; JLT-06, JLT-59.

### 2. Watch Together (F1)

#### BG-09 — Mogen mensen van buiten jullie huis meekijken?
**Opties.** (a) **nee**, alleen thuis (standaard); (b1) **VPN, alleen eigen apparaten** (eigen tailnet, zonder Tailscale-delen
met anderen); (b2) **VPN met gasten** via Tailscale-apparaatdeling: **restrisico** — zolang Jellyfin video zonder inlog levert
(ADR-0009), kan een gast elke titel afspelen waarvan hij het ID kent, en zonder ACL bereikt hij ook de TrueNAS-UI,
MediaGuard en de Hub; daarom pas na de inlogcontrole op de streamroutes (B03-010) én een ACL die alleen Jelly Leon
openzet; (c) via internet: vraagt eerst die inlogcontrole, HTTPS, een ADR en een besluit over poorten. Cloudflare valt af
voor video (voorwaarden 2026-09-28).
**Advies.** (a) nu; (b1) zodra Tailscale in het platform klaar is (B10/I21); (b2) pas na B03-010.
**Zonder besluit.** (a); B03-027 staat op *Geblokkeerd*.
**Raakt.** B03-027, B03-010; JLT-08, JLT-06.

#### BG-10 — Watch Together op Android TV en Swiftfin
**Opties.** (a) **volgmodus**: de server stuurt de tv met de bestaande afstandsbediening (± 2 s marge, geen clientpatch);
(b) echte SyncPlay voor Android TV via een grote clientpatch op basis van een niet-gemergde community-PR (lastig bij
upstream-updates). Swiftfin krijgt sowieso geen echte SyncPlay (BG-08).
**Advies.** (a).
**Raakt.** B03-026; JLT-07.

#### BG-11 — Wie ziet een nieuwe kijkgroep standaard?
**Opties.** (a) **huishouden**: gasten en kinderen van wie de maker geen verzorger is zien niets; (b) **open**: zoals standaard
Jellyfin (iedereen met SyncPlay-recht ziet de groep en de namen); (c) **privé**: alleen wie is uitgenodigd. Let op: bij (a)
en (c) doen Android TV, Swiftfin en derden-apps alleen via "tv laten volgen" mee.
**Advies.** (a). Vul daarvoor ook de lijst gasten/verzorgers in (§9).
**Raakt.** B03-022, B03-023; JLT-05.

#### BG-12 — Chat en reacties tijdens samen kijken
**Opties.** uit / alleen vaste reacties / reacties en korte tekst. Voor kinderen altijd uit.
**Advies.** uit (B03-028 is P2).
**Raakt.** B03-028; JLT-05 (voorwaardelijk deel).

#### BG-13 — Haperende deelnemer en volle GPU's bij een groepstart
**Opties haperen.** (a) na 10 s doorgaan zonder de haperende deelnemer (alleen als de racetest slaagt); (b) wachten zoals
standaard Jellyfin (tot 30 s). **Opties capaciteit.** (a) alleen waarschuwen ("2 van 3 moeten omzetten; ruimte voor 1");
(b) Jelly Leon-web mag een groepstart blokkeren als de GPU's vol zitten (officiële apps nooit).
**Advies.** Haperen: (a). Capaciteit: (a), waarschuwen.
**Raakt.** B03-025; JLT-03, JLT-04.

#### BG-14 — Watch Together-knoppen ook in de oude weergave (Legacy)?
**Opties.** (a) alleen in Modern (standaard in 12.x; één kleine haak); (b) ook in Legacy (een tweede haak die bij elke
upstream-update mee moet).
**Advies.** (a). De andere functies werken al in beide weergaven zonder extra haak.
**Raakt.** B03-024.

### 3. Aanbevelingen (F2)

#### BG-15 — Rij "Aanbevolen voor jou" op het startscherm
**Opties.** (a) via één kleine, geregistreerde webhaak (werkt in Modern en Legacy); (b) geen eigen rij: dan verbetert alleen
"Meer zoals dit". Een afspeellijst per gebruiker of een nieuw starttype in de server vallen af (schrijven in je
gebruikersgegevens of vragen een serverpatch). Android TV: een eigen rij vraagt een patch in de tv-app.
**Advies.** (a); Android TV niet in de eerste levering (wel "Meer zoals dit").
**Raakt.** B03-036, B03-037; JLT-14.

#### BG-16 — Kijkgedrag van gezinsleden en een fijnere kijklog
**Opties.** Gezinsleden: (a) nooit; (b) opt-in per profiel in beide richtingen, standaard uit, telt pas mee als minstens 3
**andere** volwassenen een titel keken (in een klein huishouden werkt het dan waarschijnlijk nooit); kinderen nooit.
Fijnere log: uit / aan (365 dagen, lokaal).
**Advies.** (b), en de fijnere log uit tot gemeten is dat hij helpt.
**Raakt.** B03-034, B03-032; JLT-13.

#### BG-17 — Online metadata (TMDb/OMDb)
**Vraag.** Standaard Jellyfin stuurt titels naar TMDb/OMDb om metadata te halen. Aanbevelingen leunen op die metadata; bij
de meting waren meerdere titels verkeerd gekoppeld.
**Opties.** (a) aan laten (beste metadata, titels gaan naar buiten); (b) uit en handmatig/lokaal verzorgen (privacy, meer werk).
**Advies.** (a) is het standaardgedrag en verandert B03 niet; de keuze hoort bij B03-006 (metadata).
**Raakt.** B03-006, B03-032.

### 4. Ondertitelvertaling (F3)

#### BG-18 — Vertaalmotor en licentie van het vertaalmodel
**Opties motor.** (a) een **aparte optionele app `mt`**, standaard uit, met OPUS-MT en→nl via CTranslate2 (model eenmalig
buiten de NAS omgezet, met herkomst en sha256; meegeleverd in de mt-image of door jou geüpload); (b) in de jelly-leon-image
(vervallen: dat vraagt torch of een onbewezen stap). **Opties licentie.** OPUS-MT-modellen CC-BY 4.0 (naamsvermelding);
een LLM-route via Ollama (experimenteel): (a) alleen Apache-2.0/MIT-modellen (Qwen3, EuroLLM, Mistral Small); (b) ook gated
modellen met eigen voorwaarden (Gemma, Llama). NC-modellen (o.a. NLLB) nooit.
**Advies.** App `mt`, model meegeleverd; LLM alleen (a) en alleen na een gemeten budget op de NAS, anders vervalt die route.
**Raakt.** B03-044, B03-045; Δ-CONTRACT-MT; JLT-21, JLT-27.

#### BG-19 — Opslag, naam en levensduur van machinevertalingen
**Opties opslag.** (a) in Jelly Leon zelf (`/config`: interne metadatamap + eigen database); (b) naast de media. Gevolg (b):
een bestandswijziging buiten MediaGuard (P4-no-go), en MediaGuard/Bazarr stoppen met zoeken naar een menselijke vertaling.
**Naam in het ondertitelmenu.** "Machinevertaling" of het upstream-woord "Automatisch vertaald". **Als later een menselijke
NL verschijnt:** verbergen (bewaard, herstelbaar) of laten staan. **Als je de module uitzet:** depubliceren of laten staan.
**Advies.** (a); "Machinevertaling"; verbergen; depubliceren bij uitzetten (hoofdkopieën blijven, opnieuw publiceren kan).
**Raakt.** B03-047, B03-049; JLT-23, JLT-24, JLT-25.

#### BG-20 — Automatisch vertalen en automatisch publiceren
**Opties.** Na installatie (a) beide uit; per bibliotheek aanzetten; publiceren pas automatisch na een geslaagde kalibratie;
(b) direct aan. Wachttijd voor MediaGuard/Bazarr om eerst een menselijke ondertitel te vinden: 72 uur of anders.
**Advies.** (a), 72 uur.
**Raakt.** B03-043, B03-046.

#### BG-21 — Onthouden audio- en ondertitelkeuzes als er een nieuw spoor bijkomt
**Vraag.** Jellyfin nummert de sporen opnieuw zodra er een extern ondertitelspoor bijkomt; een onthouden keuze kan dan naar
een ander spoor wijzen.
**Opties.** (a) **hold**: niets schrijven; een publicatie die een keuze zou laten verspringen wacht op de beheerder;
(b) **reset**: alleen die twee keuzes wissen (de speler kiest weer op taalvoorkeur; gezien en positie blijven onaangeroerd);
(c) **remap**: de keuze naar hetzelfde spoor omzetten, met waarborgen (de Jellyfin-API schrijft daarbij het hele record).
**Advies.** (a) bij de start; (b) na een groene JLT-24; (c) alleen als behoud van de gekozen taal zwaarder weegt.
**Zonder besluit.** (a) — dit is de enige plek waar een module in kijkgegevens zou schrijven.
**Raakt.** B03-047; JLT-24, JLT-65.

#### BG-22 — Bazarr-vertaler en de ondertiteldownloaders van Jellyfin
**Opties.** Bazarr-vertaler voor NL: (a) niet gebruiken (die gebruikt standaard Google Translate in de cloud en schrijft een
gewone `.nl.srt` in de bibliotheek); (b) wel. Jellyfin-ondertiteldownloaders in Jelly Leon: (a) niet installeren, zodat
MediaGuard en Bazarr de enige downloaders blijven; (b) wel. Bazarr-synchronisatie blijft je eigen keuze.
**Advies.** Beide (a).
**Raakt.** B03-015, B03-043.

### 5. Kwaliteitscontrole (F4)

#### BG-23 — Volledige decodecontrole voor de hele bibliotheek?
**Vraag.** Hardware-decode verbergt beschadigingen, dus de volledige controle draait op de CPU. Voor 1000 4K-films kost dat
naar schatting 1500–2200 uur (rekensom, niet gemeten op de NAS).
**Opties.** (a) steekproef (niveau 1,5) voor alles, volledige controle alleen voor nieuwe of door MediaGuard vervangen
bestanden en op verzoek; (b) volledige controle voor alles binnen het dagbudget.
**Advies.** (a), met een achterstandsschatting in de beheerpagina om later (b) te kunnen kiezen.
**Raakt.** B03-051, B03-052, B03-053.

#### BG-24 — Bewijs-miniaturen, label, melden en home video's
**Opties.** Miniaturen als bewijs: uit / op verzoek / automatisch. Neutraal label "bekend probleem met dit bestand" voor
gewone gebruikers: uit / aan. Knop "Meld een probleem": uit / aan. "Home video's en foto's" en "gemengde inhoud" scannen:
standaard nee / ja.
**Advies.** Miniaturen op verzoek, alleen voor beheerders, nooit naar de Hub; label uit; melden aan na een eerste test;
home video's en gemengd standaard niet (per bibliotheek opt-in, dan nooit miniaturen of spraakherkenning).
**Raakt.** B03-055, B03-057; JLT-34, JLT-38.

#### BG-25 — Gecorrigeerde ondertitelkopie bij slechte synchronisatie
**Opties.** (a) alleen melden met een hint voor de tijdverschuiving; (b) op verzoek een gecorrigeerde kopie in de eigen
opslag (via F3), nooit over het origineel en nooit als standaardspoor.
**Advies.** (b), op verzoek.
**Raakt.** B03-054, B03-042.

### 6. Apparaatprofielen en GPU (F5)

#### BG-26 — Afspeelprofiel aanpassen voor officiële apps en stock-tv-apps?
**Vraag.** De officiële Android- en desktopapp laden de webclient van Jelly Leon; stock-tv-apps (Android TV, Kodi, Swiftfin)
niet. Jelly Leon kan bij falen leren en bijsturen.
**Opties.** (a) nooit; (b) alleen als jij of de beheerder het **per apparaat** aanzet (standaard uit), en bij stock-tv-apps
alleen **beperkend**; (c) altijd.
**Advies.** (b). Zonder keuze speelt een officiële app precies zoals standaard Jellyfin.
**Raakt.** B03-066, B03-068; JLT-46.

#### BG-27 — De A310 voor live kijken terwijl MediaGuard AV1 encodeert; meten
**Opties gebruik.** (a) ja, binnen een deel van de capaciteit (voorlopig de helft, niet gemeten); (b) alleen als overloop
wanneer de UHD 770 vol is; (c) nooit. **Opties meten.** (a) de assistent vraagt je MediaGuard even **zelf** te pauzeren (via
een link; Jelly Leon bedient MediaGuard nooit); (b) meten tijdens MediaGuard-werk met het label "met MediaGuard-last".
**Advies.** Gebruik (a) met hooguit 1 Jelly Leon-stream op de A310 tot de NAS-meting; meten (a).
**Raakt.** B03-062, B03-064; JLT-43, JLT-45.

#### BG-28 — Volle of uitgevallen GPU's
**Opties bij vol.** (a) altijd het gedrag van standaard Jellyfin; (b) Jelly Leon-web mag bij de **volgende** start zelf een
lagere kwaliteit kiezen (met label en knop "Toch origineel"). **Opties bij uitval van alle GPU's.** (a) alleen melden;
(b) een voorstel "tijdelijk software-transcoding" dat een beheerder met één klik toepast en terugzet. Automatisch omschakelen
gebeurt nooit.
**Advies.** Vol: (a) als start. Uitval: (b).
**Raakt.** B03-004, B03-063; JLT-44.

#### BG-29 — Kwaliteitslabel en feedback in de speler
**Opties label.** altijd / alleen als beeld of geluid afwijkt van het origineel / nooit. **Opties feedback.** nooit / alleen als
afspelen mislukt / ook bij elke nieuwe combinatie van apparaat en formaat.
**Advies.** Label alleen bij een afwijking; feedback alleen bij falen.
**Raakt.** B03-067, B03-065.

#### BG-30 — Android TV-patch voor het automatische capabilityrapport
**Opties.** (a) ja: de Jelly Leon-tv-app (eigen app-ID) stuurt het bestaande rapport automatisch en past geleerde
beperkende regels toe; (b) nee: alleen via de bestaande knop.
**Advies.** (a), na de patches voor de eigen app-ID, prioriteit P2.
**Raakt.** B03-069; JLT-42.

### 7. Intro, aftiteling en samenvatting (F6)

#### BG-31 — Skipknoppen: tekst en standaardgedrag
**Opties tekst.** (a) exact "Sla intro over", "Sla samenvatting over", "Sla aftiteling over" in Jelly Leon-web en de eigen apps
(één webhaak en twee clientpatches; officiële apps houden "Skip"/"Overslaan", andere talen de upstream-tekst); (b) de
upstream-teksten "Intro overslaan / Terugblik overslaan / Aftiteling overslaan" volstaan. **Opties gedrag.** (a) overal
"vragen" (knop tonen, ook bij samenvattingen), nooit automatisch; (b) intro's automatisch overslaan als standaard.
**In een Watch Together-groep:** (a) altijd vragen; (b) automatisch overslaan toestaan (slaat dan voor iedereen over, ook
voor kinderen).
**Advies.** Tekst (a), gedrag (a), groep (a). Post-credit-scènes vallen nooit binnen een overslaanbaar segment.
**Raakt.** B03-007, B03-076, B03-077; JLT-55, JLT-51.

#### BG-32 — Intro Skipper, externe segmentdatabases en bestaande segmenten
**Genomen (2026-11-09):** Intro Skipper alleen als ongewijzigde vergelijkingsbasis in een testcontainer; externe segmentdatabases uit; bestaande segmenten uit de huidige installatie eenmalig als hint (met voorbeeld vooraf).
**Opties Intro Skipper (GPL-3.0).** (a) alleen als ongewijzigde vergelijkingsbasis in een aparte testcontainer; (b) ook op de
NAS naast Jelly Leon (dan maar één segmentprovider per bibliotheek); (c) helemaal niet (dan geen vergelijking). **Externe
databases** (AniSkip, TheIntroDB, SkipMe.db): (a) uit in v1; (b) opt-in als hint — die sturen ID's naar derden.
**Bestaande segmenten** uit je huidige installatie (D07): (a) eenmalig als hint overnemen, met voorbeeld vooraf; (b) niet.
**Advies.** Intro Skipper (a); databases (a); bestaande segmenten (a) als die installatie bestaat.
**Raakt.** B03-070, B03-015; JLT-50.

#### BG-33 — Wie mag tijdcodes corrigeren, en eerst schaduwmodus?
**Opties correctie.** (a) beheerders en door jou aangewezen volwassen editors; iedere volwassene mag "klopt niet" melden;
(b) elke volwassen gebruiker. Kinderen nooit. **Opties publicatie.** (a) nieuwe segmenten eerst onzichtbaar (schaduwmodus)
tot jij per serie 3 afleveringen hebt bevestigd; (b) direct publiceren.
**Advies.** (a) en (a).
**Raakt.** B03-071, B03-075; JLT-54.

#### BG-34 — Wie labelt de echte afleveringen?
**Genomen (2026-11-09):** de gebruiker (of een aangewezen persoon) labelt de echte afleveringen; de bouwer levert een eenvoudig labelscherm.
**Vraag.** Zonder bevestigde labels (Pioneer One en een steekproef uit je eigen bibliotheek: series, anime, films met
post-credits) is er geen bewijs op echte content; alleen de synthetische testset telt dan.
**Opties.** (a) jij of een aangewezen persoon labelt (reken op meer dan 1–2 uur); (b) niet: dat deel blijft *Geblokkeerd*.
**Advies.** (a).
**Raakt.** B03-070; JLT-50, JLT-53, JLT-59.

#### BG-35 — Hardware-decode voor de beeldanalyse
**Opties.** (a) alleen de UHD 770, en pas nadat D08 bevestigd is; (b) alleen de CPU. De A310 blijft voor MediaGuard en live.
**Advies.** (a) (op de ontwikkelmachine: 7,0 s CPU met VA-API tegen 132 s zonder voor Sintel 1080p).
**Raakt.** B03-073, B03-018.

#### BG-36 — Module uit of "schaduw": eigen segmenten wissen of verbergen?
**Opties.** (a) de eigen gepubliceerde segmenten uit Jellyfin wissen (altijd herstelbaar uit de eigen database); (b) alleen
verbergen via de bibliotheekinstelling (schrijft in de bibliotheekinstellingen van Jellyfin).
**Advies.** (a).
**Raakt.** B03-071, B03-013; JLT-56.

### 8. Testdata en ontwikkelmachine

#### BG-37 — Testdata met een beperkende licentie
**Genomen (2026-11-09):** MovieLens (alleen lokaal) ja; Pioneer One (alleen lokaal) ja; eenmalige evaluatie op de echte kijkhistorie (na B03-039; samengevat rapport, afmelden kan, kinderen nooit) ja; TMDb in een wegwerpcontainer met alleen publieke MovieLens-ID's ja; Netflix-4K/DV-masters niet zolang de schijf vol is.
**Opties.** MovieLens `ml-latest-small` (onderzoekslicentie; alleen lokaal): ja / nee — zonder MovieLens of een evaluatie op
echte kijkhistorie kan niet worden aangetoond dat de aanbevelingen beter rangschikken. Pioneer One (CC BY-NC-SA) en de
fanondertitels (licentie onduidelijk): alleen lokaal / niet. Netflix Open Content-masters (CC BY 4.0, tientallen GB) voor
echte DV/4K-HDR: ja / nee. Eenmalige offline-evaluatie op jullie echte kijkhistorie op de NAS (alleen een samengevat
rapport, ieder kan zich afmelden, kinderen nooit): ja / nee. TMDb aanroepen in een wegwerpcontainer met alleen de publieke
MovieLens-ID's (voor de best ingestelde stock-baseline): ja / nee.
**Advies.** MovieLens ja; Pioneer One alleen lokaal; Netflix-masters nee (schijf 89 % vol) tot er ruimte is; eenmalige
evaluatie ja (na B03-039); TMDb in de wegwerpcontainer ja.
**Raakt.** B03-016, B03-030, B03-032; JLT-10, JLT-11, JLT-15.

#### BG-38 — Ontwikkelmachine: opruimen en rechten
**Genomen (2026-11-09):** tijdelijke meetdata opgeruimd; testsets on demand maken en daarna weggooien (alleen recept/manifest blijft); Android-systeemimages blijven; gebruiker `transcode` toegevoegd aan de groepen render en kvm (actief na opnieuw inloggen).
**Opties.** Opruimen mag (de veiligheidscontrole weigerde dat in eerdere stappen): `analyse/jf-baseline/cache/` (2,2 GB
HLS-segmenten), `features/f3-meting/venv/` (1,4 GB) en `modellen/` (383 MB) na de bouwfase, `features/meting-f6/out/fp/`
(onvolledige eerste run). Houden: de Android-systeemimages (12 GB) voor de emulatortests. Rechten: de gebruiker `transcode`
in de groepen render (gid 990) en kvm (gid 991), of blijven werken via containers met `--device`. Testsets: on demand maken
en daarna weggooien (alleen het manifest blijft) of permanent bewaren.
**Advies.** Tijdelijke meetdata weg; Android-images houden; geen extra groepsrechten (containers werken); testsets on demand.

---

### 9. Gegevens die nodig zijn (geen keuze)

Deze vragen zijn feiten over jullie situatie. Vul ze in via de onboarding-wizard (D-gegevens) of laat ze meten; nooit
worden voorbeeldwaarden als echte waarden gebruikt.

| Gegeven | Waarvoor | Waar |
|---|---|---|
| **D07** — de bestaande mediaserver: volgens de gebruiker **Emby** (2026-11-09); versie, plugins, gebruikers, bibliotheken en mountpaden nog niet gemeten; draait er daarnaast een (stock-)Jellyfin, welke versie en plugins (o.a. Intro Skipper)? | overname B03-015 (Emby: §10.9.1; Jellyfin: deel B), BG-32 | wizard D07 / TrueNAS-API |
| **D08** — welke `/dev/dri/renderD12x` is de A310 en welke de UHD 770; render-gid op TrueNAS | GPU-rollen, lanes, F6-beelddecode | wizard D08 |
| Ziet Jelly Leon straks **beide** GPU's? (de iGPU staat naast een losse kaart vaak uit in het BIOS — algemene waarneming, niet op jullie NAS gecontroleerd) | topologie `two_gpu` of `a310_only` | BIOS / wizard |
| **D15** — welke tv's, telefoons, tablets, boxen, browsers en derden-apps (Kodi, Infuse, Findroid, Chromecast) jullie echt gebruiken; HDR/DV-schermen; receiver voor passthrough | apparaattests, legacy-auth (BG-01) | wizard D15 |
| NAS-RAM, TrueNAS-versie en kernel | resources (BG-07), modelkeuze | wizard / TrueNAS-API |
| Gebruikt MediaGuard het nachtvenster 23:00–07:00 met de CPU-baan? Is MediaGuard nu aan Emby of aan Jellyfin gekoppeld? Transcoderen Plex/Emby nog op de A310 of UHD 770? | planner-vensters, kijkpauze (G8) | MediaGuard-instellingen |
| Welke Jellyfin-gebruikers zijn gasten en wie verzorgt welk kind? | Watch Together (BG-11) | Jelly Leon-beheer |

### 10. Herkomst van de vragen (plandeel-ID → BG)

| Bron | Vraag-ID's → besluit |
|---|---|
| F1 Watch Together | WT-B1 → BG-09 · WT-B2 → BG-10 · WT-B3 → BG-11 · WT-B4 → BG-12 · WT-B5 → BG-14 · WT-B6 → §9 · WT-B7, WT-B8 → BG-13 |
| F2 Aanbevelingen | O-1, O-7 → BG-37 · O-2, O-5 → BG-15 · O-3, O-6 → BG-16 · O-4 → BG-06 · O-8 → BG-03 · O-9 → BG-17 |
| F3 Ondertitels | B-F3-1, B-F3-5, B-F3-10 → BG-18 (en BG-06) · B-F3-2, B-F3-8, B-F3-9, B-F3-12 → BG-19 · B-F3-3 → BG-20 · B-F3-4 → BG-21 · B-F3-6, B-F3-13 → BG-22 · B-F3-7 → BG-37 · B-F3-11 (beeldondertitels met OCR) → buiten v1, geen besluit nu · Δ-CONTRACT-MG (deel subtitles.search; in F3 eerder "MG-SUB") → BG-05 |
| F4 Kwaliteit | B1 → BG-23 · B2 → BG-05 · B3 → BG-04 · B4, B5, B10 → BG-24 · B6 → BG-25 · B8 → BG-06 · B11 → §9 · B12 → BG-07 (B7, B9 vervallen) |
| F5 Apparaten | O1, O9 → BG-26 · O2, O6 → BG-29 · O3, O11 → BG-27 · O4, O13 → BG-28 · O5, O10 → §9 · O8 → BG-30 · O12 → BG-07 (O7 vervallen) |
| F6 Intro/outro | B1, B2, B9 → BG-32 · B3, B4, B11 → BG-31 · B5, B6 → BG-33 · B7 → BG-08 · B8 → BG-34 · B10 → BG-35 · B12 → BG-36 · B13 → BG-38 |
| Analyses A1–A5 | opslag NL-ondertitels → BG-19 · extern Watch Together → BG-09 · Modern/Legacy → BG-14 · release/P4-0 → BG-02 · legacy-auth MediaGuard → BG-01 · knopteksten → BG-31 · Android TV/Swiftfin → BG-10, BG-08 · startschermrij → BG-15 · Intro Skipper/databases → BG-32 · LLM-licenties → BG-18 · Δ-MG-1/2 → BG-05 · MediaGuard-sleutel → BG-04 · embeddings/ASR → BG-06 · ondertiteldownloaders → BG-22 · groepsrechten, cache, Android-images → BG-38 · Netflix, Pioneer One → BG-37 · D07/D08/D15 → §9 |
