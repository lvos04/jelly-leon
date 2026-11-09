# ADR-0009 — Bekende upstream-risico's worden in P0 vastgelegd, niet gepatcht

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** De stock-client-smoketest toonde dat `GET /Audio/{id}/stream` (en de vergelijkbare video-route) in
  upstream 10.11.11 **zonder token** media levert (`AudioController`/`VideosController` hebben op die routes geen
  `[Authorize]`); item-ID's zijn niet geheim. Daarnaast kent upstream maar één GPU-apparaat (INVENTARIS §5).
  Opdracht P0: in de servercode nog niets wijzigen; B03-001-acceptatie: stock clients zonder regressie.

## Besluit

- Geen core-patch in P0. Een `[Authorize]` op de streamroutes kan externe spelers, cast-ontvangers en DLNA-achtige
  clients breken die URL's zonder header gebruiken; dat moet eerst op echte apparaten (D15) worden gemeten.
- Mitigatie tot dan: Jelly Leon alleen op LAN/VPN (I24 §1), geen WAN-poort; de smoketest legt het gedrag vast als
  *waarneming* zodat een upstream-wijziging zichtbaar wordt.
- Vervolg in B03-010 (kinderprofielen, download-API) als eerste kandidaat voor een geregistreerde core-patch met
  upstream-PR-kans, plus clienttest.

## Gevolgen

- Risico staat in INVENTARIS §7 en in de followups; EVIDENCE B03-010 blijft `Niet gestart`.
