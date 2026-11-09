# TrueNAS Home Platform V2 — documentatie voor `jelly-leon`

Bron: uitvoeringspakket `TrueNAS_Home_Platform_V2_VOLLEDIG_2026-11-09.zip` (peildatum 9 november 2026).

**Rol van deze repo (vast besluit):** B03 mediaserver: fork van jellyfin/jellyfin v10.11.11 (GPL-2.0), patches gescheiden van plugins, upstream-sync.

Hier staan alleen de eigen B-, I-, A- en promptdocumenten plus de gedeelde architectuur (`00_START`, `01_ARCHITECTUUR`, `05_TESTS`). Het volledige pakket en de Excel staan in `lvos04/ai-server-manager` onder `docs/platform-v2/`.

**Platformcontract:** `PLATFORM_CONTRACTEN.md` (`contracts 1.2`) en `CONTRACT_1.2_CONFORMITEIT.md` zijn byte-gelijke
kopieën uit `lvos04/ai-server-manager` (bron van waarheid, bron-commit `8b54f39`). Ze worden hier nooit aangepast;
`tools/jelly-leon/contract_drift.py` (CI-job *forkregels*) bewaakt de sha256 en vergelijkt online met de bron.

Onbekende NAS-gegevens (D01–D18) worden nooit met voorbeeldwaarden ingevuld; ze worden via de onboarding-wizard in de web-UI vastgelegd.

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
- `02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md`
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
