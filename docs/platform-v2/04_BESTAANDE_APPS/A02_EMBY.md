# Emby — behoud, migratie en acceptatie

## Besluit
Kandidaat uitschakelen na Jellyfin/MediaGuard audit.

## Waarom
MediaGuard stond eerder gekoppeld met Emby; controleer of die hook nog actief is.

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
**Acceptatie:** Onderzoek refresh/playback/bibliotheek; switch alleen na zelfde resultaat in Jellyfin.

**Gereed wanneer:** installatiestatus en functionele proef op echte TrueNAS gelogd zijn; bij stoppen kunnen gebruikers in één handeling naar de oude app terug.

## Aanvulling 2026-11-09 — kijkgeschiedenis en Emby verwijderen (ADR-0020)
De gebruiker gebruikt nu Emby; de kijkgeschiedenis staat daar. "Het belangrijkste is mijn kijkgeschiedenis; als alles werkt
verwijder ik Emby." De overname naar Jelly Leon is B03-015 deel A (prioriteit P0, al in golf 0; testen JLT-70…74): alleen
lezen uit Emby, vóór/na-rapport per gebruiker met akkoord, laatste delta bij de overstap. MediaGuard volgt tot dan Emby én
Jelly Leon (Δ-MG-DUAL); de Emby-koppeling onderbreekt nooit. Deze rij (APP-02) en I26-26-02 blijven gelden: Emby gaat pas
uit na aantoonbaar gelijk resultaat, een besluit van de gebruiker en de controlelijst "Emby verwijderen" (bouwplan B03
§10.9.2: laatste delta, eindrapport + akkoord, ZFS-snapshot, blijvend JSON-exportarchief met sha256 in de back-updekking,
MediaGuard laat Emby los). De gebruiker verwijdert Emby zelf; app stoppen en data verwijderen blijven aparte stappen (A4).
