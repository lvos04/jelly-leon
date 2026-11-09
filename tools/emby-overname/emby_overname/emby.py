"""Alleen-lezen-client voor Emby (bouwplan §10.9 regel "Bestaande mediaserver", B03-015 A3).

Garantie in code, vóór het netwerk:
- alleen de methode GET; elke andere methode (POST, PUT, PATCH, DELETE, HEAD, OPTIONS, ...) → `AlleenLezenFout`;
- alleen paden uit een vaste witte lijst (lezen van systeeminfo, gebruikers, bibliotheken, items met kijkgegevens,
  afspeelinformatie voor spoorkeuzes, classificaties, plugins en benoemde favorieten);
- de API-sleutel gaat uitsluitend als header `X-Emby-Token` mee (nooit in de URL, dus nooit in een Emby-log van URL's);
- de Emby-databasebestanden worden nooit geopend: de tool kent geen bestandsroute naar Emby.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any

from . import __version__
from .fouten import AlleenLezenFout
from .http import Antwoord, HttpClient

_ID = r"[0-9A-Za-z-]{1,64}"
WITTE_LIJST_GET: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"^/System/Info$",
        r"^/System/Info/Public$",
        r"^/Users$",
        rf"^/Users/{_ID}$",
        rf"^/Users/{_ID}/Items$",
        rf"^/Items/{_ID}/PlaybackInfo$",
        r"^/Library/VirtualFolders$",
        r"^/Library/VirtualFolders/Query$",
        r"^/Localization/ParentalRatings$",
        r"^/Plugins$",
        r"^/Persons$",
        r"^/Artists$",
        r"^/Genres$",
        r"^/Studios$",
    )
)

# Velden die Emby in lijsten alleen met een expliciete vraag teruggeeft (zonder deze velden toont Emby PlayCount 0 en
# geen LastPlayedDate — een valkuil die tot stil verlies van "aantal keren gezien" en "datum" zou leiden).
VELDEN_ITEMS = (
    "ProviderIds,Path,ParentIndexNumber,IndexNumber,SeriesId,SeriesName,OfficialRating,ProductionYear,"
    "UserDataPlayCount,UserDataLastPlayedDate"
)
VELDEN_DETAIL = "ProviderIds,Path,MediaSources,UserDataPlayCount,UserDataLastPlayedDate"
BLADGROOTTE = 500


def controleer_alleen_lezen(methode: str, pad: str) -> None:
    """De weigering vóór het netwerk; publiek zodat tests en de testhaak precies deze controle gebruiken."""
    if methode != "GET":
        raise AlleenLezenFout(f"Emby wordt alleen gelezen: methode {methode} naar {pad} geweigerd vóór het netwerk")
    if "?" in pad or not any(p.match(pad) for p in WITTE_LIJST_GET):
        raise AlleenLezenFout(f"Emby-route {pad!r} staat niet op de witte lijst; geweigerd vóór het netwerk")


class EmbyLezer:
    def __init__(self, basis_url: str, sleutel: str, spoor: Callable[[dict[str, Any]], None] | None = None,
                 timeout: float = 60.0) -> None:
        headers = {
            "X-Emby-Token": sleutel,
            "X-Emby-Authorization": (
                f'Emby Client="Jelly Leon overname", Device="overnametool", DeviceId="jelly-leon-emby-overname", '
                f'Version="{__version__}"'
            ),
        }
        self._http = HttpClient(basis_url, headers, "Emby", timeout=timeout, spoor=spoor)

    # -- de enige toegang tot het netwerk ------------------------------------------------------------------------
    def _get(self, pad: str, query: dict[str, Any] | None = None) -> Any:
        controleer_alleen_lezen("GET", pad)
        return self._http.verzoek("GET", pad, query).data

    def testhaak_schrijfpoging(self, methode: str, pad: str) -> Antwoord:
        """Alleen voor JLT-73: probeert een niet-GET-verzoek via dezelfde controle; moet altijd vóór het netwerk falen."""
        controleer_alleen_lezen(methode, pad)
        return self._http.verzoek(methode, pad)  # pragma: no cover - onbereikbaar zolang de controle werkt

    # -- lezen -------------------------------------------------------------------------------------------------
    def systeeminfo(self) -> dict[str, Any]:
        return self._get("/System/Info")

    def gebruikers(self) -> list[dict[str, Any]]:
        lijst = self._get("/Users")
        if isinstance(lijst, dict):  # sommige versies geven {Items: [...]} terug
            lijst = lijst.get("Items", [])
        return [self._get(f"/Users/{g['Id']}") for g in lijst]

    def bibliotheken(self) -> list[dict[str, Any]]:
        data = self._get("/Library/VirtualFolders/Query")
        return data.get("Items", []) if isinstance(data, dict) else list(data or [])

    def plugins(self) -> list[dict[str, Any]]:
        return list(self._get("/Plugins") or [])

    def leeftijdsclassificaties(self) -> list[dict[str, Any]]:
        return list(self._get("/Localization/ParentalRatings") or [])

    def items_van_gebruiker(self, gebruiker_id: str) -> Iterator[dict[str, Any]]:
        """Alle items die de gebruiker in Emby ziet, met kijkgegevens, in pagina's (stabiel gesorteerd)."""
        start = 0
        while True:
            data = self._get(
                f"/Users/{gebruiker_id}/Items",
                {
                    "Recursive": True, "Fields": VELDEN_ITEMS, "EnableUserData": True, "EnableImages": False,
                    "SortBy": "SortName", "SortOrder": "Ascending", "StartIndex": start, "Limit": BLADGROOTTE,
                },
            )
            items = data.get("Items", []) if isinstance(data, dict) else []
            yield from items
            start += len(items)
            totaal = data.get("TotalRecordCount", 0) if isinstance(data, dict) else 0
            if not items or start >= totaal:
                return

    def details(self, gebruiker_id: str, item_ids: list[str]) -> list[dict[str, Any]]:
        """Mediabronnen (pad en grootte) voor een reeks items, in porties van 100."""
        resultaat: list[dict[str, Any]] = []
        for i in range(0, len(item_ids), 100):
            deel = item_ids[i : i + 100]
            data = self._get(
                f"/Users/{gebruiker_id}/Items",
                {"Ids": ",".join(deel), "Fields": VELDEN_DETAIL, "EnableUserData": True, "EnableImages": False},
            )
            resultaat.extend(data.get("Items", []) if isinstance(data, dict) else [])
        return resultaat

    def benoemde_favorieten(self, gebruiker_id: str) -> list[dict[str, Any]]:
        """Favoriete personen, artiesten, genres en studio's (staan niet in de recursieve itemlijst)."""
        resultaat: list[dict[str, Any]] = []
        for route in ("/Persons", "/Artists", "/Genres", "/Studios"):
            data = self._get(route, {"UserId": gebruiker_id, "Filters": "IsFavorite", "Fields": "ProviderIds",
                                     "EnableUserData": True, "Recursive": True})
            for item in (data.get("Items", []) if isinstance(data, dict) else []):
                resultaat.append(item)
        return resultaat

    def afspeelinfo(self, item_id: str, gebruiker_id: str) -> dict[str, Any]:
        """Effectieve (onthouden) spoorkeuze per gebruiker: Emby toont die alleen in PlaybackInfo (GET, zonder bijwerking)."""
        return self._get(f"/Items/{item_id}/PlaybackInfo", {"UserId": gebruiker_id}) or {}
