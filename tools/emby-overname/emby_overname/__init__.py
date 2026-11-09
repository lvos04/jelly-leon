"""Overname van de kijkgeschiedenis vanuit Emby naar Jelly Leon (B03-015 deel A, bouwplan B03 §10.9.1).

Losse tool (geen module in het Jellyfin-proces), alleen Python-standaardbibliotheek:

- leest Emby **alleen** via de API met `GET` en een API-sleutel (`X-Emby-Token`); elke andere methode of een route buiten
  de witte lijst wordt vóór het netwerk geweigerd;
- koppelt items op provider-ID's (IMDb, TMDb, TVDb; afleveringen via serie + seizoen + aflevering) en daarna op pad;
- schrijft in Jelly Leon alleen via de officiële API (gebruikers-, beleids-, configuratie- en UserData-routes);
- zet niets stil weg: wat niet eenduidig over te zetten is, staat met reden op de afhandellijst;
- maakt een vóór/na-rapport per gebruiker (JSON met sha256, Markdown en eenvoudig HTML met akkoordveld) en een blijvend
  JSON-exportarchief van alle Emby-kijkgegevens (controlelijst "Emby verwijderen", §10.9.2).
"""

from __future__ import annotations

__version__ = "0.1.0"

TOOL_NAAM = "jelly-leon-emby-overname"
