# ADR-0025 — B03-015: eigen overnametool (alleen-lezen uit Emby) in plaats van JellyPlex-Watched

- **Status:** Aanvaard (2026-11-09) — besluit van de bouwer (`docs/platform-v2/02_BOUWPLANNEN/B03_BESLUITEN.md` §2.1:
  "Hergebruik van JellyPlex-Watched of een eigen overnametool — de bouwer (ADR in jelly-leon), geen gebruikersbesluit").
  Uitvoering: `tools/emby-overname/` (golf 0, tegen stock `jellyfin/jellyfin:12.4` met een echte Emby-container).
- **Herkomst:** B03-015 stap A2 (bouwplan §10.9.1 stap 2); vervolg op de slotregel van ADR-0015.
- **Werkpakketten / testen:** B03-015; JLT-70, JLT-71, JLT-72, JLT-73 (golf 0, Sim), JLT-74 (echte NAS, Geblokkeerd).

## Context

De gebruiker gebruikt nu Emby; "het belangrijkste is mijn kijkgeschiedenis". Het plan eist (B03-015 A3–A10): Emby alleen
lezen met een API-sleutel, waarbij de client elke andere methode **vóór het netwerk** weigert; koppelen op provider-ID's en
daarna pad, bij twijfel nooit gokken; per gebruiker gezien-status **met datum en aantal**, hervatpunten **op de tick exact**,
favorieten en (waar Emby ze levert) beoordelingen en spoorkeuzes; gebruikers met rechten en ouderlijk toezicht (een kind ziet
nooit meer dan in Emby); een afhandellijst (nooit stil weglaten); herhaalbare proefrun, idempotent, laatste delta, hervatten
na een afbreking zonder dubbele schrijfacties; een vóór/na-rapport per gebruiker met akkoord; een blijvend JSON-archief.

Beoordeeld: **luigi311/JellyPlex-Watched v9.0.0** (tag-commit `3137cdd1efdd3ed9fe3136572fb655cdfb9f3f67`, 2026-11-04;
`git ls-remote --tags` op 2026-11-09), licentie **GPL-3.0** (`LICENSE`), Python ≥ 3.12 met loguru, plexapi, pydantic,
requests. De broncode is gelezen in een losse map (`src/jellyfin_emby.py`, `src/emby.py`, `README.md`); er is niets van
uitgevoerd en niets overgenomen. Daarnaast is het gedrag van Emby 4.10.2.0 en Jellyfin 12.4 in echte containers gemeten.

| Eis | JellyPlex-Watched v9.0.0 | Gevolg |
|---|---|---|
| Licentie naast de GPL-2.0-only fork (ADR-0023) | GPL-3.0 | alleen als apart proces; geen code in de fork |
| Alleen-lezen richting Emby, afgedwongen vóór het netwerk | één `query()` voor GET én POST naar elke server; alleen-lezen hangt af van de configuratie (`sync_to`, `dryrun`) | **voldoet niet** aan A3 |
| Gezien met **aantal** | vraagt `UserDataLastPlayedDate` maar niet `UserDataPlayCount`; schrijft altijd `PlayCount: 1`. Gemeten: Emby 4.10.2.0 geeft zonder dat veld `PlayCount: 0` in lijsten | aantal keren gezien gaat verloren |
| Gezien met **datum** | ontbrekende datum wordt `now()` | onjuiste datum zonder melding |
| Hervatpunt **ticks exact** | rekent om naar milliseconden (`floor(ticks / 10000)`); films die niet gezien zijn en < 60 s (600 000 000 ticks) gevorderd worden overgeslagen | niet exact; stil weggelaten |
| Favorieten, beoordelingen, spoorkeuzes | niet ondersteund | ontbreekt |
| Gebruikers, rechten, ouderlijk toezicht | alleen naamkoppeling; maakt geen gebruikers en vertaalt geen beleid | ontbreekt |
| Koppelen zonder gok | bestandsnaam (basename) óf een provider-ID volstaat; geen detectie van dubbele ID's | risico op een verkeerde koppeling |
| Afhandellijst, vóór/na-rapport per gebruiker, akkoord | niet aanwezig (droge run = logregels) | ontbreekt |
| Herhaalbaar, delta, hervatten na kill | vergelijkt telkens de actuele toestanden; geen journaal; aantal niet additief | niet aantoonbaar |
| Onderhoud | actief (meerdere releases in 2026) | positief, maar de ontbrekende delen zitten in de kern (datamodel in ms, koppelen op bestandsnaam) |

## Besluit

1. **Geen hergebruik van JellyPlex-Watched** voor de overname; ook geen fork ervan. Een eigen, kleine tool
   `tools/emby-overname` (Python 3.12, **alleen de standaardbibliotheek**, GPL-2.0 zoals de fork) draait als **los proces**
   (geen module in het Jellyfin-proces), zodat hij al in golf 0 tegen stock 12.4 werkt (§10.9.1).
2. **Alleen-lezen in code:** `EmbyLezer` laat alleen `GET` toe op een vaste witte lijst; elke andere methode of route geeft
   `AlleenLezenFout` vóór het netwerk. De sleutel gaat alleen als header `X-Emby-Token` mee (nooit in een URL), staat alleen in
   een bestand met modus 0600 in de geheimenmap en komt in geen log, rapport of export. Redirects worden nooit gevolgd en
   omgevingsproxy's genegeerd.
3. **Schrijven in Jelly Leon** uitsluitend via de officiële routes `POST /Users/New`, `/Users/{id}/Policy`,
   `/Users/Configuration` en `/UserItems/{id}/UserData` (witte lijst in `JellyfinClient`); nooit in `jellyfin.db`.
   Nieuwe gebruikers krijgen een willekeurig wachtwoord dat nergens wordt bewaard: inloggen kan pas na een nieuw wachtwoord
   (of SSO, B13).
4. **Kennis, geen code:** van JellyPlex-Watched is alleen de bevestiging overgenomen dat `UserDataLastPlayedDate` expliciet
   gevraagd moet worden; de tool vraagt daarnaast `UserDataPlayCount` (zelf gemeten).
5. Onthouden **spoorkeuzes** leest de tool uit Emby's `PlaybackInfo` (GET) en vergelijkt ze met wat Jelly Leon kiest. Jellyfin
   12.4 heeft geen officiële route om een spoorkeuze te zetten (alleen via afspeelrapportage, die ook kijkgegevens wijzigt):
   een afwijkende keuze komt daarom op de afhandellijst (`spoorkeuze_niet_overzetbaar`, of `ander_bestand` als pad of
   grootte verschilt) — `capability_unavailable`, nooit een gesimuleerd succes.
6. JellyPlex-Watched wordt voor deze overname niet op de NAS geïnstalleerd. Of een bestaande installatie van
   JellyPlex-Watched (I26, APP-03) nog nodig is, blijft een aparte vraag voor de gebruiker (A03: "kandidaat uitschakelen").

## Alternatieven

- **JellyPlex-Watched ongewijzigd gebruiken:** snel, maar faalt op ticks, aantal, datum, favorieten, rechten, afhandellijst
  en de alleen-lezen-garantie. Verworpen.
- **JellyPlex-Watched forken en aanvullen (GPL-3.0, apart proces):** licentietechnisch mogelijk, maar het datamodel
  (milliseconden, `PlayCount` 1) en het koppelen op bestandsnaam zitten in de kern; dat is in feite herschrijven plus het
  bijhouden van een fork met Plex-code die we niet nodig hebben. Verworpen.
- **Rechtstreeks de Emby-database lezen:** sneller en vollediger, maar het plan verbiedt het openen van de
  Emby-databasebestanden. Verworpen.

## Gevolgen

- Eigen onderhoud (± 2 000 regels Python) met unit-, integratie- (simulators) en E2E-tests tegen een echte Emby-container en
  stock Jellyfin 12.4, ook in CI (`.github/workflows/jelly-leon-ci.yml`, job *emby-overname*).
- Een nieuwe Emby-versie (D07 meet de NAS-versie) vraagt eerst een proefrun met die versie op vaste digest.
- De gebruiker heeft geen terminal: op de NAS start later de overname-assistent in het beheer van Jelly Leon (B03 §1, P4-0)
  deze tool; tot die er is, blijft de echte overname (JLT-74) **Geblokkeerd — NIET GEVALIDEERD (echte NAS)**.

## Verificatie

`tools/emby-overname/tests` (unit en simulators) en `tools/emby-overname/e2e/proefrun.py` (echte Emby 4.10.2.0 + stock
Jellyfin 12.4; JLT-70…73): 100 % van gezien-status en hervatpunten van de gekoppelde items, afhandellijst voor de rest,
tweede run 0 schrijfacties met een inhoudelijk identiek rapport, delta en hervatten na kill, en een loggende proxy die
bewijst dat er alleen GET-verzoeken naar Emby gaan. Bewijs in `docs/platform-v2/test-evidence/b03-015-*`.
