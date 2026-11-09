"""Client voor Jelly Leon / Jellyfin 12.x via de officiële API (B03-015 A6).

Schrijven alleen via de routes die het bouwplan toestaat (§10.9 "Nooit", uitzondering B03-015): gebruiker aanmaken,
beleid, configuratie en UserData. Elke andere schrijfroute wordt vóór het netwerk geweigerd; `jellyfin.db` wordt nooit
geopend. Authenticatie met `Authorization: MediaBrowser … Token="…"` (12.x zet legacy-auth uit; geen token in URL's).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any

from . import __version__
from .fouten import NietToegestaneRoute
from .http import HttpClient

_GUID = r"[0-9a-fA-F-]{32,36}"
WITTE_LIJST: dict[str, tuple[re.Pattern[str], ...]] = {
    "GET": tuple(
        re.compile(p)
        for p in (
            r"^/System/Info$",
            r"^/System/Info/Public$",
            r"^/Users$",
            rf"^/Users/{_GUID}$",
            r"^/Items$",
            rf"^/Items/{_GUID}/PlaybackInfo$",
            r"^/Library/VirtualFolders$",
            r"^/Localization/ParentalRatings$",
            r"^/Persons$",
            r"^/Artists$",
            r"^/Genres$",
            r"^/Studios$",
        )
    ),
    "POST": tuple(
        re.compile(p)
        for p in (
            r"^/Users/New$",
            rf"^/Users/{_GUID}/Policy$",
            r"^/Users/Configuration$",
            rf"^/UserItems/{_GUID}/UserData$",
        )
    ),
}
VELDEN_ITEMS = "ProviderIds,Path,MediaSources,ParentId,OfficialRating"
BLADGROOTTE = 500


def controleer_route(methode: str, pad: str) -> None:
    patronen = WITTE_LIJST.get(methode, ())
    if "?" in pad or not any(p.match(pad) for p in patronen):
        raise NietToegestaneRoute(f"Jelly Leon-route {methode} {pad!r} is niet toegestaan voor de overname; geweigerd vóór het netwerk")


class JellyfinClient:
    def __init__(self, basis_url: str, sleutel: str, spoor: Callable[[dict[str, Any]], None] | None = None,
                 timeout: float = 60.0) -> None:
        autorisatie = (
            f'MediaBrowser Client="Jelly Leon overname", Device="overnametool", DeviceId="jelly-leon-emby-overname", '
            f'Version="{__version__}", Token="{sleutel}"'
        )
        self._http = HttpClient(basis_url, {"Authorization": autorisatie}, "Jelly Leon", timeout=timeout, spoor=spoor)

    def _verzoek(self, methode: str, pad: str, query: dict[str, Any] | None = None, body: Any = None) -> Any:
        controleer_route(methode, pad)
        return self._http.verzoek(methode, pad, query, body).data

    # -- lezen -------------------------------------------------------------------------------------------------
    def systeeminfo(self) -> dict[str, Any]:
        return self._verzoek("GET", "/System/Info")

    def gebruikers(self) -> list[dict[str, Any]]:
        return list(self._verzoek("GET", "/Users") or [])

    def gebruiker(self, gebruiker_id: str) -> dict[str, Any]:
        return self._verzoek("GET", f"/Users/{gebruiker_id}")

    def bibliotheken(self) -> list[dict[str, Any]]:
        return list(self._verzoek("GET", "/Library/VirtualFolders") or [])

    def leeftijdsclassificaties(self) -> list[dict[str, Any]]:
        return list(self._verzoek("GET", "/Localization/ParentalRatings") or [])

    def alle_items(self, gebruiker_id: str | None = None, extra: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Alle items (als beheerder), of de items die één gebruiker ziet mét diens UserData."""
        start = 0
        while True:
            query: dict[str, Any] = {
                "recursive": True, "fields": VELDEN_ITEMS, "enableImages": False, "sortBy": "SortName",
                "sortOrder": "Ascending", "startIndex": start, "limit": BLADGROOTTE,
            }
            if gebruiker_id:
                query.update({"userId": gebruiker_id, "enableUserData": True})
            if extra:
                query.update(extra)
            data = self._verzoek("GET", "/Items", query)
            items = data.get("Items", []) if isinstance(data, dict) else []
            yield from items
            start += len(items)
            if not items or start >= (data.get("TotalRecordCount", 0) if isinstance(data, dict) else 0):
                return

    def benoemde_items(self, route: str, naam: str, gebruiker_id: str | None = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"searchTerm": naam, "limit": 50, "fields": "ProviderIds", "enableImages": False}
        if gebruiker_id:
            query.update({"userId": gebruiker_id, "enableUserData": True})
        data = self._verzoek("GET", route, query)
        return data.get("Items", []) if isinstance(data, dict) else []

    def afspeelinfo(self, item_id: str, gebruiker_id: str) -> dict[str, Any]:
        return self._verzoek("GET", f"/Items/{item_id}/PlaybackInfo", {"userId": gebruiker_id}) or {}

    # -- schrijven (alleen officiële routes) -------------------------------------------------------------------
    def maak_gebruiker(self, naam: str, wachtwoord: str) -> dict[str, Any]:
        return self._verzoek("POST", "/Users/New", body={"Name": naam, "Password": wachtwoord})

    def zet_beleid(self, gebruiker_id: str, beleid: dict[str, Any]) -> None:
        self._verzoek("POST", f"/Users/{gebruiker_id}/Policy", body=beleid)

    def zet_configuratie(self, gebruiker_id: str, configuratie: dict[str, Any]) -> None:
        self._verzoek("POST", "/Users/Configuration", {"userId": gebruiker_id}, body=configuratie)

    def zet_userdata(self, gebruiker_id: str, item_id: str, velden: dict[str, Any]) -> dict[str, Any]:
        return self._verzoek("POST", f"/UserItems/{item_id}/UserData", {"userId": gebruiker_id}, body=velden) or {}
