# JellyPlex-Watched — behoud, migratie en acceptatie

## Besluit
Kandidaat uitschakelen als synchronisatie overbodig.

## Waarom
Onderzoek of cross-server seen status nog nodig is.

## Verplichte inventaris voor bouwer
1. Draaiende TrueNAS image-tag/digest, container ID, owner en status (niet alleen repositoryversie).
2. Netwerkpoorten, domein, eventuele VPN/tunnel en gekoppelde app credentials (geschoond).
3. Datasets, database en restoretype; controleer OneDrive-dekking en snapshot.
4. API dependencies: welke apps praten ermee en welke acties mogen zij uitvoeren?
5. Laatste echte gebruiksdatum, hulpcode, logs en performance.

## Gefaseerde aanpak
- **A0: Meten:** documenteer bovenstaande, inclusief screenshot van huidige UI en configuratie-export.
- **A1: Niet-mutatief integreren:** koppel in Hub als catalogusitem, toon status en diep-link.
- **A2: Verbeteren of vervangen:** voer alleen functies die aantoonbaar ontbreken uit via de in B-plannen vastgelegde data-eigenaar.
- **A3: Proefstop (alleen indien kandidaat):** schakel tijdelijk uit met eigen data intact en verifieer gebruikersreizen.
- **A4: Behoud/decommission:** beslissing schriftelijk, backup restore test, veilige rollback; data verwijderen staat los van app-stop.

## Testcase en beslissing
**Acceptatie:** Test watch/resume state van minstens 3 gebruikers voor/na stop.

**Gereed wanneer:** installatiestatus en functionele proef op echte TrueNAS gelogd zijn; bij stoppen kunnen gebruikers in één handeling naar de oude app terug.

## Aanvulling 2026-11-09 — hergebruik bij de Emby-overname
Vóór er een eigen overnametool komt, beoordeelt B03-015 (stap A2) JellyPlex-Watched op licentie (GPL-3.0 volgens GitHub op
2026-11-09, release v9.0.0; als los proces naast de GPL-2.0-only fork) en hergebruik (alleen-lezen tegen Emby, per gebruiker,
hervatpunten, droog rapport). Het besluit komt in een ADR in jelly-leon. De beslissing over de app zelf (APP-03) blijft los
daarvan staan.
