# TrueNAS Home Platform V2 — documentatie voor `jelly-leon`

Bron: uitvoeringspakket `TrueNAS_Home_Platform_V2_VOLLEDIG_2026-11-09.zip` (peildatum 9 november 2026).

**Rol van deze repo (vast besluit):** B03 mediaserver: fork van jellyfin/jellyfin v10.11.11 (GPL-2.0), patches gescheiden van plugins, upstream-sync.

Hier staan alleen de eigen B-, I-, A- en promptdocumenten plus de gedeelde architectuur (`00_START`, `01_ARCHITECTUUR`, `05_TESTS`). Het volledige pakket en de Excel staan in `lvos04/ai-server-manager` onder `docs/platform-v2/`.

**Platformcontract:** `PLATFORM_CONTRACTEN.md` (`contracts 1.2`) en `CONTRACT_1.2_CONFORMITEIT.md` zijn byte-gelijke
kopieën uit `lvos04/ai-server-manager` (bron van waarheid, bron-commit `8b54f39`). Ze worden hier nooit aangepast;
`tools/jelly-leon/contract_drift.py` (CI-job *forkregels*) bewaakt de sha256 en vergelijkt online met de bron.

Onbekende NAS-gegevens (D01–D18) worden nooit met voorbeeldwaarden ingevuld; ze worden via de onboarding-wizard in de web-UI vastgelegd.

## B03 2.0 — universele mediaserver (goedgekeurd door de gebruiker op 2026-11-09)

- `02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` (versie 2.0), `02_BOUWPLANNEN/B03_FASERING.md` en
  `02_BOUWPLANNEN/B03_BESLUITEN.md` zijn byte-gelijke kopieën uit `lvos04/ai-server-manager` (bron-commit `0f390bf`),
  net als `00_START/INHOUDSOPGAVE.md`, `04_BESTAANDE_APPS/A02_EMBY.md` en `04_BESTAANDE_APPS/A03_JELLYPLEX_WATCHED.md`.
  Nooit hier bewerken: een nieuwe stand overnemen = opnieuw byte-gelijk kopiëren uit de bron.
- **HARDE EIS van de gebruiker:** alle kijkgeschiedenis (gezien-status, hervatpunten, favorieten, beoordelingen, onthouden
  spoorkeuzes, gebruikers, rechten) en de MediaGuard-voortgang blijven altijd beschikbaar (bouwplan §10.9 en B03-015). Geen
  cutover zonder vóór/na-rapport per gebruiker en uitdrukkelijk akkoord van de gebruiker op elk verschil (ook door
  upstream-migraties); de bestaande installatie blijft ongewijzigd als terugval.
- **Huidige mediaserver: Emby.** De gebruiker: "Het belangrijkste is mijn kijkgeschiedenis; als alles werkt verwijder ik
  Emby." De overname vanuit Emby (B03-015, testen JLT-70…74) heeft prioriteit P0 en begint al in golf 0, tegen stock 12.4
  met een echte Emby-container. Emby wordt alleen gelezen (API-sleutel, alleen GET) en blijft ongewijzigd draaien tot de
  gebruiker na de controlelijst "Emby verwijderen" (bouwplan §10.9.2) zelf besluit; de gebruiker verwijdert Emby zelf.
  Deze repo levert de overnametool en het vóór/na-rapport (eerst JellyPlex-Watched beoordelen op licentie en hergebruik).
- ADR-nummers in die kopieën: een kaal ADR-0001…0011 is een ADR van deze repo, behalve waar "web" of "jelly-leon-web"
  erbij staat (bv. "web ADR-0001"); "ADR-0016…0020 in `docs/adr/`" (bouwplan) en "ADR-0020" (`A02_EMBY.md`) zijn ADR's
  van ai-server-manager. De ADR-voorstellen ADR-B03-01…13 uit het bouwplan staan,
  voor zover ze deze fork raken, hier als ADR-0015…0024 (overzicht en herkomst in [`../adr/README.md`](../adr/README.md)).
- `EXCEL_TAKEN.json` bevat de volledige B03-set: B03-001…079 (de uitgebreide rijen B03-004/005/007/009/010/013 vervangen
  de oude rijen; de oude tekst staat er letterlijk vooraan in) en de testrijen JLT-01…74 (conventie van ai-server-manager:
  Fase `P6 - E2E`, Soort `Testen`, startstatus en bewijsrijen in `Afhankelijkheid`). Nooit `Gereed` of `Geslaagd`.

- **B03-016 (golf 0):** corpusgenerator met grondwaarheid en bevroren sha256-manifesten, CI-guard testdatalicenties,
  clientmatrix-rooktest en baselinemetingen van stock 12.4 (stock-standaard en stock-best) in één harnasraamwerk:
  `B03-016_HARNAS.md` (procedure), `BOUWVERIFICATIE_B03-016.md` (gemeten uitkomsten), `test-evidence/b03-016-*`,
  code in `tools/b03-harnas/`, besluit ADR-0026.

## Bestanden

- `PLATFORM_CONTRACTEN.md` (kopie, contract 1.2)
- `CONTRACT_1.2_CONFORMITEIT.md` (kopie; voor deze repo §9, JL1–JL6)
- `00_START/BESLUITEN_EN_ONBEKENDEN.md`
- `00_START/INHOUDSOPGAVE.md`
- `00_START/INHOUD_CONTROLE.json`
- `00_START/LEES_MIJ_EERST.md`
- `00_START/SHA256SUMS.txt`
- `01_ARCHITECTUUR/01_PROJECTCHARTER.md`
- `01_ARCHITECTUUR/02_DATA_EIGENAARSCHAP.md`
- `01_ARCHITECTUUR/03_RISICO_AUTONOMIE.md`
- `01_ARCHITECTUUR/04_GEGEVENS_EN_STORAGE.md`
- `01_ARCHITECTUUR/05_OPERATIES_EN_UPDATES.md`
- `01_ARCHITECTUUR/06_FASERING_EN_GATES.md`
- `01_ARCHITECTUUR/07_API_EN_EVENTSCHEMA.md`
- `01_ARCHITECTUUR/08_UI_EN_INTERACTIES.md`
- `02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` (versie 2.0, kopie)
- `02_BOUWPLANNEN/B03_FASERING.md` (kopie)
- `02_BOUWPLANNEN/B03_BESLUITEN.md` (kopie)
- `03_INSTALLATIE/I06_JELLYFIN.md`
- `03_INSTALLATIE/I22_NAVIDROME_OPT.md`
- `03_INSTALLATIE/I24_UNIVERSELE_MEDIASERVER.md`
- `04_BESTAANDE_APPS/A01_PLEX.md`
- `04_BESTAANDE_APPS/A02_EMBY.md`
- `04_BESTAANDE_APPS/A03_JELLYPLEX_WATCHED.md`
- `04_BESTAANDE_APPS/A17_JELLYFIN.md`
- `05_TESTS/GEBRUIKERSWENSEN_TRACEERBAARHEID.md`
- `05_TESTS/INTEGRALE_E2E_TESTMATRIX.md`
- `06_TEMPLATES/PROMPTS_PER_APP/PROMPT_B03_UNIVERSELE_MEDIASERVER.md`
