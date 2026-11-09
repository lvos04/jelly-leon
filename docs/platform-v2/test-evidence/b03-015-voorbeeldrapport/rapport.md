# Overname kijkgeschiedenis Emby → Jelly Leon — Vóór/na-rapport na de overzetting

- Gemaakt: 2026-11-09T21:04:21Z · tool jelly-leon-emby-overname 0.1.0
- Bron: Emby 4.10.2.0 (server f1762f44b308); exportinhoud sha256 `28fbeb1723f50aca17356ec89398063df1e21807c366ebc24c50df64c54a062a`
- Doel: Jellyfin Server 12.4.0 (server bc475772fa0e)
- Rapport (JSON) sha256: `1677d3d47e944ddf8cff7a0df3ecedb2b1341898ec6c6a0f1c296351787d0d7b` · inhoud sha256: `71569c075089d3ff35d71be33e79b52d781cef296f08a5bf8757ed3fc16cd721` · plan sha256: `134d360e560a8f12459731b93d4e82555162eb3b3acb77233180f23c27ae7ba0`

Emby is alleen gelezen (alleen GET). Wachtwoorden zijn niet overgezet. Niets is stil weggelaten: wat niet automatisch over te zetten is, staat hieronder op de afhandellijst.

## Samenvatting (alle gebruikers)

| Soort | In Emby | Gekoppeld | Gelijk in Jelly Leon | Jelly Leon nieuwer | Afhandellijst | Gelijk of verklaard (van gekoppeld) |
|---|---|---|---|---|---|---|
| Gezien (met datum en aantal) | 25 | 21 | 21 | 0 | 4 | 100,0 % |
| Hervatpunten (ticks exact) | 7 | 7 | 7 | 0 | 0 | 100,0 % |
| Favorieten | 6 | 5 | 5 | 0 | 1 | 100,0 % |
| Beoordelingen | 0 | 0 | 0 | 0 | 0 | — |
| Onthouden spoorkeuzes | 33 | 28 | 26 | 0 | 7 | 92,9 % |

- Alles verantwoord (overgezet of op de afhandellijst): **ja**
- Schrijfacties in deze run: 43 ({"gebruiker": 4, "beleid": 4, "configuratie": 4, "userdata": 31})
- Bibliotheken: Series → Series; Films → Films

Te beoordelen verschillen: **20** (elk verschil vraagt uw akkoord).

## Gebruiker: Anna

- In Jelly Leon: **Anna** — door de overname aangemaakt
- Wachtwoord: niet overgezet
- Kijkgegevens verantwoord: 6 van 6 items (klopt)
- Zichtbaar: Emby 42 items, Jelly Leon 34; ruimer dan Emby: **0**, smaller: 0, alleen in Jelly Leon: 8

| Soort | In Emby | Gekoppeld | Gelijk in Jelly Leon | Jelly Leon nieuwer | Afhandellijst | Gelijk of verklaard (van gekoppeld) |
|---|---|---|---|---|---|---|
| Gezien (met datum en aantal) | 4 | 4 | 4 | 0 | 0 | 100,0 % |
| Hervatpunten (ticks exact) | 2 | 2 | 2 | 0 | 0 | 100,0 % |
| Favorieten | 1 | 1 | 1 | 0 | 0 | 100,0 % |
| Beoordelingen | 0 | 0 | 0 | 0 | 0 | — |
| Onthouden spoorkeuzes | 6 | 6 | 5 | 0 | 1 | 83,3 % |

**Rechten, ouderlijk toezicht en voorkeuren**

| Instelling | Emby | Jelly Leon | Status | Toelichting |
|---|---|---|---|---|
| IsAdministrator | nee | nee | gelijk |  |
| EnableRemoteAccess | ja | ja | gelijk |  |
| EnableContentDownloading | ja | ja | gelijk |  |
| Bibliotheektoegang | alle bibliotheken | alle bibliotheken | gelijk |  |
| MaxParentalRating | — | — | gelijk | geen leeftijdsgrens |
| Geblokkeerde tags | — | — | gelijk |  |
| IsHiddenRemotely | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableTranscodingQuality | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableSubtitleDownloading | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| AllowCameraUpload | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| AudioLanguagePreference | eng | eng | gelijk |  |
| SubtitleLanguagePreference | dut | dut | gelijk |  |
| SubtitleMode | Always | Always | gelijk |  |

**Afhandellijst en verschillen**

| ID | Soort | Wat | Item | Kijkgegevens in Emby | Toelichting |
|---|---|---|---|---|---|
| V-961a7a569153 | gebruiker | Actie nodig | — | — | wachtwoord_niet_overgezet: Wachtwoorden zijn niet over te zetten (Emby geeft ze niet vrij). Stel in Jelly Leon een nieuw wachtwoord in (Dashboard → Gebruikers → deze gebruiker → Wachtwoord) of gebruik SSO; tot dan kan niemand als deze gebruiker inloggen. |
| V-4cdc4ff2c7e9 | rechten | Ter kennisname | — | — | recht_zonder_tegenhanger: Emby-instellingen zonder tegenhanger in Jelly Leon (raken geen toegang tot media): AllowCameraUpload, EnableSubtitleDownloading, EnableTranscodingQuality, IsHiddenRemotely. |
| V-a81eeeadd415 | spoorkeuze | Uw beslissing | Sintel Kort (2010) | — | ander_bestand: Het bestand verschilt (Emby 1172428172 bytes, Jelly Leon 48725294 bytes); de spoorkeuze (audio: eng · ac3 · “AC3 5.1 @ 640 Kbps”; ondertitel: eng · subrip) wordt daarom niet overgenomen. |

## Gebruiker: Bram

- In Jelly Leon: **Bram** — door de overname aangemaakt
- Wachtwoord: niet overgezet
- Kijkgegevens verantwoord: 10 van 10 items (klopt)
- Zichtbaar: Emby 42 items, Jelly Leon 34; ruimer dan Emby: **0**, smaller: 0, alleen in Jelly Leon: 8

| Soort | In Emby | Gekoppeld | Gelijk in Jelly Leon | Jelly Leon nieuwer | Afhandellijst | Gelijk of verklaard (van gekoppeld) |
|---|---|---|---|---|---|---|
| Gezien (met datum en aantal) | 7 | 7 | 7 | 0 | 0 | 100,0 % |
| Hervatpunten (ticks exact) | 1 | 1 | 1 | 0 | 0 | 100,0 % |
| Favorieten | 2 | 2 | 2 | 0 | 0 | 100,0 % |
| Beoordelingen | 0 | 0 | 0 | 0 | 0 | — |
| Onthouden spoorkeuzes | 9 | 9 | 9 | 0 | 0 | 100,0 % |

**Rechten, ouderlijk toezicht en voorkeuren**

| Instelling | Emby | Jelly Leon | Status | Toelichting |
|---|---|---|---|---|
| IsAdministrator | nee | nee | gelijk |  |
| EnableRemoteAccess | ja | ja | gelijk |  |
| EnableContentDownloading | nee | nee | gelijk |  |
| Bibliotheektoegang | alle bibliotheken | alle bibliotheken | gelijk |  |
| MaxParentalRating | — | — | gelijk | geen leeftijdsgrens |
| Geblokkeerde tags | — | — | gelijk |  |
| IsHiddenRemotely | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableTranscodingQuality | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableSubtitleDownloading | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| AllowCameraUpload | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| SubtitleMode | OnlyForced | OnlyForced | gelijk |  |

**Afhandellijst en verschillen**

| ID | Soort | Wat | Item | Kijkgegevens in Emby | Toelichting |
|---|---|---|---|---|---|
| V-c29de6c68cd0 | gebruiker | Actie nodig | — | — | wachtwoord_niet_overgezet: Wachtwoorden zijn niet over te zetten (Emby geeft ze niet vrij). Stel in Jelly Leon een nieuw wachtwoord in (Dashboard → Gebruikers → deze gebruiker → Wachtwoord) of gebruik SSO; tot dan kan niemand als deze gebruiker inloggen. |
| V-42020ffc5d64 | rechten | Ter kennisname | — | — | recht_zonder_tegenhanger: Emby-instellingen zonder tegenhanger in Jelly Leon (raken geen toegang tot media): AllowCameraUpload, EnableSubtitleDownloading, EnableTranscodingQuality, IsHiddenRemotely. |

## Gebruiker: Gast

- In Jelly Leon: **Gast** — door de overname aangemaakt
- Wachtwoord: niet overgezet
- Kijkgegevens verantwoord: 2 van 2 items (klopt)
- Zichtbaar: Emby 20 items, Jelly Leon 11; ruimer dan Emby: **0**, smaller: 0, alleen in Jelly Leon: 5

| Soort | In Emby | Gekoppeld | Gelijk in Jelly Leon | Jelly Leon nieuwer | Afhandellijst | Gelijk of verklaard (van gekoppeld) |
|---|---|---|---|---|---|---|
| Gezien (met datum en aantal) | 1 | 0 | 0 | 0 | 1 | — |
| Hervatpunten (ticks exact) | 1 | 1 | 1 | 0 | 0 | 100,0 % |
| Favorieten | 0 | 0 | 0 | 0 | 0 | — |
| Beoordelingen | 0 | 0 | 0 | 0 | 0 | — |
| Onthouden spoorkeuzes | 2 | 1 | 0 | 0 | 2 | 0,0 % |

**Rechten, ouderlijk toezicht en voorkeuren**

| Instelling | Emby | Jelly Leon | Status | Toelichting |
|---|---|---|---|---|
| IsAdministrator | nee | nee | gelijk |  |
| EnableRemoteAccess | nee | nee | gelijk |  |
| EnableContentDownloading | ja | ja | gelijk |  |
| Bibliotheektoegang | Films | Films | gelijk |  |
| MaxParentalRating | — | — | gelijk | geen leeftijdsgrens |
| Geblokkeerde tags | — | — | gelijk |  |
| IsHiddenRemotely | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableTranscodingQuality | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableSubtitleDownloading | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| AllowCameraUpload | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| SubtitleMode | Smart | Smart | gelijk |  |

**Afhandellijst en verschillen**

| ID | Soort | Wat | Item | Kijkgegevens in Emby | Toelichting |
|---|---|---|---|---|---|
| V-be03623a4c23 | gebruiker | Actie nodig | — | — | wachtwoord_niet_overgezet: Wachtwoorden zijn niet over te zetten (Emby geeft ze niet vrij). Stel in Jelly Leon een nieuw wachtwoord in (Dashboard → Gebruikers → deze gebruiker → Wachtwoord) of gebruik SSO; tot dan kan niemand als deze gebruiker inloggen. |
| V-4fef5bd2376b | item | Uw beslissing | Hero (2018) | gezien (1×, laatst 24-10-2026 20:00:00 UTC) | geen_id: geen provider-ID's en geen item op hetzelfde pad in Jelly Leon. pad /data/media/Films/Hero (2018)/Hero (2018).mp4 niet gevonden |
| V-ea35d9113c31 | rechten | Ter kennisname | — | — | recht_zonder_tegenhanger: Emby-instellingen zonder tegenhanger in Jelly Leon (raken geen toegang tot media): AllowCameraUpload, EnableSubtitleDownloading, EnableTranscodingQuality, IsHiddenRemotely. |
| V-735dff98b365 | spoorkeuze | Actie nodig | Sintel (2010) | — | spoorkeuze_niet_overzetbaar: Emby kiest voor deze gebruiker audio: eng · ac3 · “AC3 5.1 @ 640 Kbps”; ondertitel: uit/standaard; Jelly Leon kiest nu audio: eng · ac3 · “AC3 5.1 @ 640 Kbps”; ondertitel: deu · subrip. Jellyfin 12.4 heeft geen officiële route om een onthouden spoorkeuze te zetten (capability_unavailable): kies het spoor één keer zelf in Jelly Leon, dan onthoudt Jelly Leon het. |

## Gebruiker: Kim

- In Jelly Leon: **Kim** — door de overname aangemaakt
- Wachtwoord: niet overgezet
- Kijkgegevens verantwoord: 5 van 5 items (klopt)
- Zichtbaar: Emby 30 items, Jelly Leon 22; ruimer dan Emby: **0**, smaller: 0, alleen in Jelly Leon: 7

| Soort | In Emby | Gekoppeld | Gelijk in Jelly Leon | Jelly Leon nieuwer | Afhandellijst | Gelijk of verklaard (van gekoppeld) |
|---|---|---|---|---|---|---|
| Gezien (met datum en aantal) | 3 | 3 | 3 | 0 | 0 | 100,0 % |
| Hervatpunten (ticks exact) | 1 | 1 | 1 | 0 | 0 | 100,0 % |
| Favorieten | 1 | 1 | 1 | 0 | 0 | 100,0 % |
| Beoordelingen | 0 | 0 | 0 | 0 | 0 | — |
| Onthouden spoorkeuzes | 4 | 4 | 4 | 0 | 0 | 100,0 % |

**Rechten, ouderlijk toezicht en voorkeuren**

| Instelling | Emby | Jelly Leon | Status | Toelichting |
|---|---|---|---|---|
| IsAdministrator | nee | nee | gelijk |  |
| EnableRemoteAccess | nee | nee | gelijk |  |
| EnableContentDownloading | nee | nee | gelijk |  |
| Bibliotheektoegang | Films, Series | Films, Series | gelijk |  |
| MaxParentalRating | 5 (PG, TV-PG) | 10 | gelijk | via de classificatienaam (PG, TV-PG); Jelly Leon-score 10 |
| Geblokkeerde tags | Horror | Horror | gelijk |  |
| IsHiddenRemotely | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableTranscodingQuality | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableSubtitleDownloading | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| AllowCameraUpload | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| SubtitleMode | None | None | gelijk |  |

**Afhandellijst en verschillen**

| ID | Soort | Wat | Item | Kijkgegevens in Emby | Toelichting |
|---|---|---|---|---|---|
| V-8ee191a31120 | gebruiker | Actie nodig | — | — | wachtwoord_niet_overgezet: Wachtwoorden zijn niet over te zetten (Emby geeft ze niet vrij). Stel in Jelly Leon een nieuw wachtwoord in (Dashboard → Gebruikers → deze gebruiker → Wachtwoord) of gebruik SSO; tot dan kan niemand als deze gebruiker inloggen. |
| V-f72fc53b6174 | rechten | Ter kennisname | — | — | recht_zonder_tegenhanger: Emby-instellingen zonder tegenhanger in Jelly Leon (raken geen toegang tot media): AllowCameraUpload, EnableSubtitleDownloading, EnableTranscodingQuality, IsHiddenRemotely. |

## Gebruiker: beheerder

- In Jelly Leon: **jlbeheer** — bestond al in Jelly Leon (rechten niet aangepast) · beheerder
- Wachtwoord: eigen Jelly Leon-wachtwoord
- Kijkgegevens verantwoord: 13 van 13 items (klopt)
- Zichtbaar: Emby 42 items, Jelly Leon 34; ruimer dan Emby: **0**, smaller: 0, alleen in Jelly Leon: 8

| Soort | In Emby | Gekoppeld | Gelijk in Jelly Leon | Jelly Leon nieuwer | Afhandellijst | Gelijk of verklaard (van gekoppeld) |
|---|---|---|---|---|---|---|
| Gezien (met datum en aantal) | 10 | 7 | 7 | 0 | 3 | 100,0 % |
| Hervatpunten (ticks exact) | 2 | 2 | 2 | 0 | 0 | 100,0 % |
| Favorieten | 2 | 1 | 1 | 0 | 1 | 100,0 % |
| Beoordelingen | 0 | 0 | 0 | 0 | 0 | — |
| Onthouden spoorkeuzes | 12 | 8 | 8 | 0 | 4 | 100,0 % |

**Rechten, ouderlijk toezicht en voorkeuren**

| Instelling | Emby | Jelly Leon | Status | Toelichting |
|---|---|---|---|---|
| IsAdministrator | ja | ja | gelijk |  |
| EnableRemoteAccess | ja | ja | gelijk |  |
| EnableLiveTvManagement | ja | nee | strenger |  |
| EnableContentDownloading | ja | ja | gelijk |  |
| EnableSubtitleManagement | ja | nee | strenger |  |
| IsHidden | nee | ja | handmatig |  |
| Bibliotheektoegang | alle | alle | gelijk |  |
| MaxParentalRating | — | — | gelijk |  |
| Geblokkeerde tags | — | — | gelijk |  |
| SubtitleMode | Smart | Default | handmatig |  |
| IsHiddenRemotely | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableTranscodingQuality | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| EnableSubtitleDownloading | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| AllowCameraUpload | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |
| AllowSharingPersonalItems | ja | — | niet_van_toepassing | Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media |

**Afhandellijst en verschillen**

| ID | Soort | Wat | Item | Kijkgegevens in Emby | Toelichting |
|---|---|---|---|---|---|
| V-aec6ae9eeb6f | item | Uw beslissing | Spring (2019) | favoriet | dubbel: niet eenduidig: meerdere Jelly Leon-items passen. 2 Jelly Leon-items met imdb=tt10200208 en geen eenduidig pad |
| V-dfb77f6479ef | item | Uw beslissing | Hero (2018) | gezien (1×, laatst 01-09-2026 19:00:00 UTC) | geen_id: geen provider-ID's en geen item op hetzelfde pad in Jelly Leon. pad /data/media/Films/Hero (2018)/Hero (2018).mp4 niet gevonden |
| V-094f9aa8d082 | item | Uw beslissing | B03 Anime S01E03 — B03 Anime - 03 | gezien (1×, laatst 05-10-2026 18:00:00 UTC) | ontbreekt: geen tegenhanger in Jelly Leon (ID's en pad gezocht). serie-ID en pad /data/media/Series/B03 Anime/B03 Anime - 03.mkv niet gevonden |
| V-92e6970f8f0b | item | Uw beslissing | Cosmos Laundromat (2015) | gezien (1×, laatst 02-09-2026 19:00:00 UTC) | ontbreekt: geen tegenhanger in Jelly Leon (ID's en pad gezocht). imdb=tt4957236, tmdb=358332 en pad /data/media/Films/Cosmos Laundromat (2015)/Cosmos Laundromat (2015).mp4 niet gevonden |
| V-40b0a56e3b97 | rechten | Actie nodig | — | — | recht_handmatig: SubtitleMode: Emby 'Smart' → Jelly Leon 'Default'. |
| V-f4c4d1f84f90 | rechten | Actie nodig | — | — | recht_handmatig: IsHidden: Emby False → Jelly Leon True. |
| V-010159e30e28 | rechten | Ter kennisname | — | — | recht_strenger: EnableLiveTvManagement: Emby True → Jelly Leon False. |
| V-b38540e9057a | rechten | Ter kennisname | — | — | recht_strenger: EnableSubtitleManagement: Emby True → Jelly Leon False. |
| V-3fd1d19565bb | rechten | Ter kennisname | — | — | recht_zonder_tegenhanger: Emby-instellingen zonder tegenhanger in Jelly Leon (raken geen toegang tot media): AllowCameraUpload, AllowSharingPersonalItems, EnableSubtitleDownloading, EnableTranscodingQuality, IsHiddenRemotely. |

## Akkoord

Ik heb dit rapport (inhoud sha256 `71569c075089d3ff35d71be33e79b52d781cef296f08a5bf8757ed3fc16cd721`) gelezen en ga akkoord met elk hierboven genoemd verschil (20 stuks).

Naam: ______________________   Datum: ____________   Handtekening: ______________________

Digitaal: open `rapport.html`, vink elk verschil aan en kies *Akkoord-bestand maken*; of maak zelf een `akkoord.json` met `schema`, `soort` (`plan` of `cutover`), `rapport_inhoud_sha256`, `plan_sha256` (bij `plan`), `akkoord_door`, `datum` en de lijst `verschillen`. Zonder volledig akkoord geen overzetting en geen overstap.
