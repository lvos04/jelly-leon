"""Eén derden-client met legacy-headers (B03 2.0 §10.14; BG-01): wat doet Jellyfin 12.x met de oude auth-vormen?

Veel derden-apps (en de huidige MediaGuard-koppeling met Emby) sturen ``X-Emby-Token``, ``X-MediaBrowser-Token``,
``X-Emby-Authorization`` of ``?api_key=``. In 12.x staat ``EnableLegacyAuthorization`` standaard uit; dit meet per vorm
welke status een gewone route, de gebruikersroute en de streamroute geven. Tokens komen nooit in het rapport.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from .jfapi import Http

VORMEN = {
    "authorization_mediabrowser_token": lambda t: ({"Authorization": f'MediaBrowser Client="derde", Device="d", DeviceId="b03-derde", '
                                                                      f'Version="1", Token="{t}"'}, {}),
    "x_emby_token": lambda t: ({"X-Emby-Token": t}, {}),
    "x_mediabrowser_token": lambda t: ({"X-MediaBrowser-Token": t}, {}),
    "x_emby_authorization": lambda t: ({"X-Emby-Authorization": f'MediaBrowser Client="derde", Device="d", DeviceId="b03-derde", '
                                                                f'Version="1", Token="{t}"'}, {}),
    "query_api_key": lambda t: ({}, {"api_key": t}),
    "query_apikey_hoofdletter": lambda t: ({}, {"ApiKey": t}),
    "zonder_token": lambda t: ({}, {}),
}


def meet(url: str, token: str, user_id: str, item_id: str) -> dict[str, Any]:
    routes = {
        "system_info": "/System/Info",
        "gebruiker_items": f"/Users/{user_id}/Items?Limit=1",
        "stream_statisch": f"/Videos/{item_id}/stream?static=true",
    }
    uit: dict[str, Any] = {}
    for vorm, maak in VORMEN.items():
        headers, query = maak(token)
        rij = {}
        for naam, pad in routes.items():
            scheiding = "&" if "?" in pad else "?"
            volledig = pad + (scheiding + urllib.parse.urlencode(query) if query else "")
            http = Http(url, headers, timeout=30)
            status, ruw, kop = http.ruw("GET", volledig, headers={"Range": "bytes=0-1023"} if "stream" in naam else None)
            rij[naam] = status
        uit[vorm] = rij
    return uit


def main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415
    import json  # noqa: PLC0415

    from .stock import GEBRUIKER, WACHTWOORD, StockServer  # noqa: PLC0415

    p = argparse.ArgumentParser(prog="b03h legacy")
    p.add_argument("--uit", required=True)
    a = p.parse_args(argv)
    srv = StockServer("legacy", gpu=False, koppelingen={"/media/movies/hero": "bron/blender/hero"}).start()
    try:
        srv.inrichten([("Films", "movies", ["/media/movies"])])
        assert srv.jf
        srv.jf.login(GEBRUIKER, WACHTWOORD)
        item = srv.jf.items()[0]["Id"]
        resultaat = meet(srv.url, srv.jf.token, srv.jf.admin_id, item)
        legacy_cfg = srv.jf.a.doe("GET", "/System/Configuration").get("EnableLegacyAuthorization")
    finally:
        srv.verwijder()
    with open(a.uit, "w", encoding="utf-8") as f:
        json.dump({"EnableLegacyAuthorization": legacy_cfg, "status_per_vorm": resultaat}, f, indent=1)
    print(json.dumps(resultaat, indent=1))
    return 0
