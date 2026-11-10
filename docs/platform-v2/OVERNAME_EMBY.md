# Overname van de kijkgeschiedenis uit Emby (B03-015 deel A) — procedure, rapport en controlelijst

Voor wie: de gebruiker (en de bouwer die de overname-assistent later in het beheer van Jelly Leon zet). Bouwplan: B03 2.0
§10.9.1 en §10.9.2; besluit over hergebruik: `docs/adr/ADR-0025-b03-015-eigen-overnametool-niet-jellyplex-watched.md`;
tool: `tools/emby-overname/` (README daar).

> **Stand (2026-11-09, eerlijk):** de tool en de proefrun werken tegen een **echte Emby 4.10.2.0-container** en stock
> **Jellyfin 12.4** op de ontwikkelmachine en in CI (Sim; bewijs in `test-evidence/b03-015-*`). Op de echte NAS is nog
> niets gedaan: JLT-74 staat op **Geblokkeerd — NIET GEVALIDEERD (echte NAS)**. D07 (versie, gebruikers, bibliotheken en
> mountpaden van uw Emby) is nog niet gemeten; nergens zijn voorbeeldwaarden als echte waarden gebruikt.

## Wat er overgaat — en wat niet

| Gegeven | Overgezet | Hoe |
|---|---|---|
| Gezien (met datum en aantal keren) | ja, exact | `Played`, `PlayCount`, `LastPlayedDate` via de officiële UserData-route |
| Hervatpunten | ja, op de tick exact | `PlaybackPositionTicks` |
| Favorieten (films, afleveringen, series, personen, …) | ja | `IsFavorite`; in Emby verwijderde favorieten nooit automatisch verwijderd |
| Beoordelingen | als Emby ze levert | `Rating`/`Likes`; gemeten met Emby 4.10.2.0: ook na `POST /Users/{id}/Items/{id}/Rating?Likes=true` (HTTP 200) gaf Emby in de UserData geen `Rating` of `Likes` terug — dan staat in het rapport "0 beoordelingen in Emby" (capability_unavailable aan de bron) |
| Gebruikers, rechten, ouderlijk toezicht | ja | zelfde naam; beheerder, bibliotheken, leeftijdsgrens, geblokkeerde tags, downloaden, toegang buitenshuis, tijdschema's; wat niet exact kan, wordt **strenger** en komt op de afhandellijst |
| Taal- en ondertitelvoorkeuren | ja | gebruikersconfiguratie |
| Onthouden spoorkeuzes (audio/ondertitel per item) | **nee, wel gemeld** | Jellyfin 12.4 heeft geen officiële route om ze te zetten; elk verschil staat op de afhandellijst (bij een ander bestand: `ander_bestand`) |
| Wachtwoorden | **nee** | Emby geeft ze niet vrij; stel per gebruiker een nieuw wachtwoord in (of SSO, B13) |
| MediaGuard-voortgang | niet nodig | blijft in de eigen database van MediaGuard; de overname raakt die niet |

Emby wordt **alleen gelezen** (alleen GET, met een API-sleutel die u in Emby aanmaakt); de Emby-databasebestanden worden
nooit geopend. Emby blijft ongewijzigd draaien als terugval.

**Doelcontrole (sinds de QA-review van golf 0 + P4-0):** Emby accepteert ook de aanmeldheader van Jellyfin (gemeten met
Emby 4.10.2.0). Wijst het adres van Jelly Leon per vergissing naar Emby, dan zou een overname zonder controle in Emby
schrijven. Daarom leest de tool eerst, zónder sleutel, `GET /System/Info/Public` van het doel en gaat alleen verder als
dat `ProductName` "Jellyfin Server" meldt (Jellyfin en Jelly Leon doen dat; Emby niet). Zijn de adressen gelijk, of
hebben bron en doel dezelfde server-ID, dan stopt de tool ook (exitcode 9). Er wordt dan niets geschreven en de
Jelly Leon-sleutel wordt niet verstuurd.

**Geen analyse uitlokken:** gemeten met Emby 4.10.2.0 laat een `GET /Items/{id}/PlaybackInfo` op een bestand dat Emby nog
niet heeft geanalyseerd (grootte 0, geen streams) Emby dat bestand alsnog analyseren en opslaan. Voor zo'n bestand vraagt
de tool daarom geen afspeelinformatie; het staat in de export onder `spoorkeuzes_niet_gelezen`. Een nooit afgespeeld
bestand heeft geen onthouden spoorkeuze, dus er gaat niets verloren.

## Stappen

1. **Inventaris (D07)** — versie, gebruikers, bibliotheken en plugins van Emby, alleen lezen.
2. **Exportarchief** — een blijvend JSON-bestand met alle kijkgegevens per gebruiker, met sha256.
3. **Proefrun (droog)** — er wordt niets geschreven. U krijgt per gebruiker een rapport (`rapport.html`, ook als Markdown en
   als JSON met sha256) met: wat er in Emby staat, wat er in Jelly Leon komt, en de **afhandellijst** (alles wat niet
   automatisch kan, met reden).
4. **Akkoord op het plan** — in `rapport.html` vinkt u elk verschil aan en maakt u het akkoord-bestand. Zonder akkoord op
   elk verschil schrijft de tool niets. Is er sinds de proefrun iets veranderd, dan weigert de tool en maakt u een nieuwe
   proefrun.
5. **Overzetten** — via de officiële Jelly Leon-API, eerst op een kopie van de Jelly Leon-datamap. Een afgebroken run
   hervat zonder iets dubbel te schrijven.
6. **Vóór/na-rapport en akkoord** — per gebruiker per soort vóór en na; elk verschil vraagt uw akkoord.
7. **Laatste delta bij de overstap** — stap 3–6 opnieuw: alleen wat sinds de vorige run in Emby veranderde, gaat mee.
   Een nieuwere waarde in Jelly Leon wordt nooit stil overschreven (eens gezien blijft gezien; hervatpunt volgens het
   nieuwste moment).

## Controlelijst "Emby verwijderen" (u voert dit zelf uit — geen enkele agent verwijdert Emby)

| # | Stap | Bewijs | Stand |
|---|---|---|---|
| 1 | Laatste delta overgezet; niemand kijkt nog op Emby (0 Emby-sessies, zichtbaar via MediaGuard) | vóór/na-rapport van de delta-run; MediaGuard | nog niet (NAS) |
| 2 | Eindrapport per gebruiker met uw akkoord op elk verschil; rapport (JSON + sha256) bewaard | `akkoord-controle` geeft "overstap toegestaan" | nog niet (NAS) |
| 3 | ZFS-snapshot van de Emby-configuratie/-dataset; naam en tijdstip in het eindrapport | TrueNAS | nog niet (NAS) |
| 4 | Blijvend JSON-exportarchief van alle Emby-kijkgegevens met sha256, op de NAS en in de back-updekking (B12); herimportproef uit het archief op een lege kopie geslaagd | `export`, `--bron-archief` (in de proef: Sim-geslaagd) | NAS-deel nog niet |
| 5 | MediaGuard laat Emby netjes los en volgt alleen Jelly Leon (Δ-MG-DUAL); kijkpauze bij een Jelly Leon-sessie aangetoond | media-guard-ultimate | nog niet |
| 6 | Eerst een proefstop (terug naar Emby in één handeling); data verwijderen pas later en apart; snapshot en archief blijven bewaard | APP-02/A4 | nog niet |

## Wat nog moet gebeuren vóór de echte overname

- D07 meten (wizard of TrueNAS-API): Emby-versie en -digest, gebruikers, bibliotheken, mountpaden; daarna de proefrun
  herhalen met precies die Emby-versie op vaste digest.
- De overname-assistent in het beheer van Jelly Leon (P4-0), zodat u geen terminal nodig hebt; tot die er is, voert de
  tool alleen de proefrun in de testomgeving uit.
- De proefrun herhalen tegen `jelly-leon:12.x` (gate P4-0) en de echte overname op de NAS (JLT-74).
