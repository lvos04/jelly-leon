"""Simulators van Emby en Jellyfin 12.x (alleen de routes die de overnametool gebruikt), voor integratietests zonder Docker.

Beide registreren elk verzoek (methode, pad) zodat tests kunnen bewijzen dat er naar Emby alleen GET gaat en dat een
tweede run 0 schrijfacties doet. Gedrag dat de echte servers ook hebben en dat ertoe doet, is nagebootst: Emby geeft
PlayCount/LastPlayedDate in lijsten alleen met de juiste Fields; Jellyfin filtert items op het beleid van de gebruiker.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from emby_overname.model import Kijkgegevens


class _Server:
    def __init__(self) -> None:
        self.verzoeken: list[tuple[str, str]] = []
        self.lock = threading.Lock()
        eigenaar = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # stil
                pass

            def _doe(self, methode: str) -> None:
                deel = urlsplit(self.path)
                query = {k: v[-1] for k, v in parse_qs(deel.query).items()}
                lengte = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(lengte)) if lengte else None
                with eigenaar.lock:
                    eigenaar.verzoeken.append((methode, deel.path))
                    status, data = eigenaar.behandel(methode, deel.path, query, body, dict(self.headers))
                inhoud = b"" if data is None else json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(inhoud)))
                self.end_headers()
                self.wfile.write(inhoud)

            def do_GET(self) -> None:  # noqa: N802
                self._doe("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._doe("POST")

            def do_DELETE(self) -> None:  # noqa: N802
                self._doe("DELETE")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def behandel(self, methode: str, pad: str, query: dict[str, str], body: Any, headers: dict[str, str]) -> tuple[int, Any]:
        raise NotImplementedError


def _pagina(items: list[dict[str, Any]], query: dict[str, str], start_sleutel: str, limiet_sleutel: str) -> dict[str, Any]:
    start = int(query.get(start_sleutel, 0))
    limiet = int(query.get(limiet_sleutel, 10_000))
    return {"Items": items[start : start + limiet], "TotalRecordCount": len(items)}


class NepEmby(_Server):
    SLEUTEL = "emby-geheime-sleutel-0123456789"

    def __init__(self) -> None:
        self.gebruikers: dict[str, dict[str, Any]] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self.userdata: dict[tuple[str, str], dict[str, Any]] = {}
        self.spoorkeuzes: dict[tuple[str, str], tuple[int | None, int | None]] = {}
        self.bibliotheken = [
            {"Name": "Films", "Guid": "aaaa0000aaaa0000aaaa0000aaaa0001", "ItemId": "3", "CollectionType": "movies",
             "Locations": ["/mnt/emby/media/Films"]},
            {"Name": "Series", "Guid": "aaaa0000aaaa0000aaaa0000aaaa0002", "ItemId": "5", "CollectionType": "tvshows",
             "Locations": ["/mnt/emby/media/Series"]},
        ]
        # Elk verzoek waarin de Jelly Leon-sleutel meekwam (mag nooit: een verkeerd doel krijgt die sleutel niet).
        self.vreemde_sleutels: list[str] = []
        super().__init__()

    def voeg_gebruiker(self, naam: str, beleid: dict[str, Any] | None = None, config: dict[str, Any] | None = None) -> str:
        uid = uuid.uuid4().hex
        standaard = {"IsAdministrator": False, "IsHidden": False, "IsDisabled": False, "EnableAllFolders": True,
                     "EnabledFolders": [], "BlockedTags": [], "EnableRemoteAccess": True, "EnableContentDownloading": True,
                     "EnableAllDevices": True, "EnableAllChannels": True, "InvalidLoginAttemptCount": 0}
        self.gebruikers[uid] = {
            "Id": uid, "Name": naam, "HasConfiguredPassword": True,
            "Policy": {**standaard, **(beleid or {})},
            "Configuration": {"SubtitleMode": "Smart", "RememberAudioSelections": True, "RememberSubtitleSelections": True,
                              "PlayDefaultAudioTrack": True, **(config or {})},
        }
        return uid

    def voeg_item(self, item_id: str, type_: str, naam: str, pad: str, bib: str, provider: dict[str, str] | None = None,
                  grootte: int = 1000, **extra: Any) -> None:
        self.items[item_id] = {"Id": item_id, "Type": type_, "Name": naam, "Path": pad, "ProviderIds": provider or {},
                               "_bib": bib, "_grootte": grootte, **extra}

    def zet(self, uid: str, item_id: str, **velden: Any) -> None:
        self.userdata.setdefault((uid, item_id), {}).update(velden)

    def zichtbaar(self, uid: str) -> list[dict[str, Any]]:
        beleid = self.gebruikers[uid]["Policy"]
        uit = []
        for item in self.items.values():
            if not beleid.get("EnableAllFolders") and item["_bib"] not in beleid.get("EnabledFolders", []):
                continue
            if beleid.get("MaxParentalRating") is not None and item.get("_waarde", 0) > beleid["MaxParentalRating"]:
                continue
            uit.append(item)
        return sorted(uit, key=lambda i: (i["Name"], i["Id"]))

    def _dto(self, item: dict[str, Any], uid: str, velden: str) -> dict[str, Any]:
        ud = dict(self.userdata.get((uid, item["Id"]), {}))
        ud.setdefault("Played", False)
        ud.setdefault("IsFavorite", False)
        ud.setdefault("PlaybackPositionTicks", 0)
        if "UserDataPlayCount" not in velden:
            ud["PlayCount"] = 0  # zoals echte Emby: zonder Fields toont de lijst 0
        else:
            ud.setdefault("PlayCount", 0)
        if "UserDataLastPlayedDate" not in velden:
            ud.pop("LastPlayedDate", None)
        dto = {k: v for k, v in item.items() if not k.startswith("_")}
        dto["UserData"] = ud
        if "MediaSources" in velden:
            dto["MediaSources"] = [{"Path": item["Path"], "Size": item["_grootte"]}]
        return dto

    def behandel(self, methode: str, pad: str, query: dict[str, str], body: Any, headers: dict[str, str]) -> tuple[int, Any]:
        if any(NepJellyfin.SLEUTEL in v for v in headers.values()):
            self.vreemde_sleutels.append(f"{methode} {pad}")
        if methode == "GET" and pad == "/System/Info/Public":
            # Gemeten bij emby/embyserver:4.10.2.0: anoniem, zonder ProductName.
            return 200, {"LocalAddresses": [], "RemoteAddresses": [], "ServerName": "nep-emby", "Version": "4.10.2.0",
                         "Id": "emby-server-1"}
        # Gemeten bij 4.10.2.0: Emby accepteert de sleutel als X-Emby-Token én als `Authorization: MediaBrowser … Token="…"`.
        if headers.get("X-Emby-Token") != self.SLEUTEL and f'Token="{self.SLEUTEL}"' not in headers.get("Authorization", ""):
            return 401, None
        if methode != "GET":
            return 405, None
        delen = pad.strip("/").split("/")
        if pad == "/System/Info":
            return 200, {"Id": "emby-server-1", "ServerName": "nep-emby", "Version": "4.10.2.0"}
        if pad == "/Users":
            return 200, [{"Id": g["Id"], "Name": g["Name"]} for g in self.gebruikers.values()]
        if len(delen) == 2 and delen[0] == "Users":
            return 200, copy.deepcopy(self.gebruikers[delen[1]])
        if len(delen) == 3 and delen[0] == "Users" and delen[2] == "Items":
            uid = delen[1]
            velden = query.get("Fields", "")
            items = self.zichtbaar(uid)
            if "Ids" in query:
                ids = set(query["Ids"].split(","))
                items = [i for i in items if i["Id"] in ids]
            return 200, _pagina([self._dto(i, uid, velden) for i in items], query, "StartIndex", "Limit")
        if pad == "/Library/VirtualFolders/Query":
            return 200, {"Items": self.bibliotheken}
        if pad == "/Localization/ParentalRatings":
            return 200, [{"Name": "G", "Value": 1}, {"Name": "PG", "Value": 5}, {"Name": "PG-13", "Value": 7}, {"Name": "R", "Value": 9}]
        if pad == "/Plugins":
            return 200, [{"Name": "Nep", "Version": "1.0"}]
        if pad in ("/Persons", "/Artists", "/Genres", "/Studios"):
            return 200, {"Items": [], "TotalRecordCount": 0}
        if len(delen) == 3 and delen[0] == "Items" and delen[2] == "PlaybackInfo":
            item = self.items[delen[1]]
            audio, ondertitel = self.spoorkeuzes.get((query.get("UserId", ""), item["Id"]), (1, None))
            return 200, {"MediaSources": [{
                "Path": item["Path"], "Size": item["_grootte"], "DefaultAudioStreamIndex": audio,
                "DefaultSubtitleStreamIndex": ondertitel,
                "MediaStreams": [{"Index": 0, "Type": "Video", "Codec": "h264"},
                                 {"Index": 1, "Type": "Audio", "Codec": "ac3", "Language": "eng", "Channels": 6},
                                 {"Index": 2, "Type": "Audio", "Codec": "aac", "Language": "dut", "Channels": 2},
                                 {"Index": 3, "Type": "Subtitle", "Codec": "subrip", "Language": "dut"}],
            }], "PlaySessionId": uuid.uuid4().hex}
        return 404, None


class NepJellyfin(_Server):
    SLEUTEL = "jl-geheime-sleutel-9876543210"

    def __init__(self) -> None:
        self.gebruikers: dict[str, dict[str, Any]] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self.userdata: dict[tuple[str, str], dict[str, Any]] = {}
        self.wachtwoorden: dict[str, str] = {}
        self.bibliotheken = [
            {"Name": "Films", "ItemId": "f" * 32, "Locations": ["/data/media/Films"]},
            {"Name": "Series", "ItemId": "e" * 32, "Locations": ["/data/media/Series"]},
        ]
        self.schrijfacties: list[tuple[str, str]] = []
        super().__init__()
        self.voeg_gebruiker("jlbeheer", {"IsAdministrator": True})

    def voeg_gebruiker(self, naam: str, beleid: dict[str, Any] | None = None) -> str:
        uid = uuid.uuid4().hex
        self.gebruikers[uid] = {
            "Id": uid, "Name": naam,
            "Policy": {"IsAdministrator": False, "IsHidden": True, "IsDisabled": False, "EnableAllFolders": True,
                       "EnabledFolders": [], "BlockedTags": [], "AllowedTags": [], "MaxParentalRating": None,
                       "EnableRemoteAccess": True, "EnableContentDownloading": True, "AccessSchedules": [],
                       "BlockUnratedItems": [], "AuthenticationProviderId": "Default", "PasswordResetProviderId": "Default",
                       **(beleid or {})},
            "Configuration": {"SubtitleMode": "Default", "RememberAudioSelections": True, "RememberSubtitleSelections": True,
                              "PlayDefaultAudioTrack": True},
        }
        return uid

    def voeg_item(self, item_id: str, type_: str, naam: str, pad: str, bib: str, provider: dict[str, str] | None = None,
                  grootte: int = 1000, **extra: Any) -> None:
        self.items[item_id] = {"Id": item_id, "Type": type_, "Name": naam, "Path": pad, "ProviderIds": provider or {},
                               "_bib": bib, "_grootte": grootte, **extra}

    def zichtbaar(self, uid: str) -> list[dict[str, Any]]:
        beleid = self.gebruikers[uid]["Policy"]
        uit = []
        for item in self.items.values():
            if not beleid.get("EnableAllFolders") and item["_bib"] not in beleid.get("EnabledFolders", []):
                continue
            if beleid.get("MaxParentalRating") is not None and item.get("_waarde", 0) > beleid["MaxParentalRating"]:
                continue
            uit.append(item)
        return sorted(uit, key=lambda i: (i["Name"], i["Id"]))

    def kijk(self, uid: str, item_id: str) -> Kijkgegevens:
        return Kijkgegevens.uit_userdata(self.userdata.get((uid, item_id)))

    def behandel(self, methode: str, pad: str, query: dict[str, str], body: Any, headers: dict[str, str]) -> tuple[int, Any]:
        if methode == "GET" and pad == "/System/Info/Public":
            return 200, {"LocalAddress": None, "ServerName": "nep-jl", "Version": "12.4.0", "ProductName": "Jellyfin Server",
                         "OperatingSystem": "", "Id": "jl-server-1", "StartupWizardCompleted": True}
        if f'Token="{self.SLEUTEL}"' not in headers.get("Authorization", ""):
            return 401, None
        delen = pad.strip("/").split("/")
        if methode == "GET":
            if pad == "/System/Info":
                return 200, {"Id": "jl-server-1", "ServerName": "nep-jl", "Version": "12.4.0", "ProductName": "Jellyfin Server"}
            if pad == "/Users":
                return 200, [copy.deepcopy(g) for g in self.gebruikers.values()]
            if len(delen) == 2 and delen[0] == "Users":
                return 200, copy.deepcopy(self.gebruikers[delen[1]])
            if pad == "/Items":
                uid = query.get("userId")
                items = self.zichtbaar(uid) if uid else sorted(self.items.values(), key=lambda i: (i["Name"], i["Id"]))
                if "ids" in query:
                    ids = set(query["ids"].split(","))
                    items = [i for i in items if i["Id"] in ids]
                dto = []
                for i in items:
                    d = {k: v for k, v in i.items() if not k.startswith("_")}
                    d["MediaSources"] = [{"Path": i["Path"], "Size": i["_grootte"]}]
                    if uid:
                        d["UserData"] = {"Played": False, "PlayCount": 0, "PlaybackPositionTicks": 0, "IsFavorite": False,
                                         **self.userdata.get((uid, i["Id"]), {})}
                    dto.append(d)
                return 200, _pagina(dto, query, "startIndex", "limit")
            if pad == "/Library/VirtualFolders":
                return 200, self.bibliotheken
            if pad == "/Localization/ParentalRatings":
                return 200, [{"Name": "G", "Value": 0}, {"Name": "PG", "Value": 10}, {"Name": "PG-13", "Value": 13},
                             {"Name": "R", "Value": 17}]
            if pad in ("/Persons", "/Artists", "/Genres", "/Studios"):
                return 200, {"Items": [], "TotalRecordCount": 0}
            if len(delen) == 3 and delen[0] == "Items" and delen[2] == "PlaybackInfo":
                item = self.items[delen[1]]
                return 200, {"MediaSources": [{
                    "Path": item["Path"], "Size": item["_grootte"], "DefaultAudioStreamIndex": 1,
                    "DefaultSubtitleStreamIndex": None,
                    "MediaStreams": [{"Index": 0, "Type": "Video", "Codec": "h264"},
                                     {"Index": 1, "Type": "Audio", "Codec": "ac3", "Language": "eng", "Channels": 6},
                                     {"Index": 2, "Type": "Audio", "Codec": "aac", "Language": "dut", "Channels": 2},
                                     {"Index": 3, "Type": "Subtitle", "Codec": "subrip", "Language": "dut"}],
                }]}
            return 404, None
        if methode == "POST":
            self.schrijfacties.append((methode, pad))
            if pad == "/Users/New":
                uid = self.voeg_gebruiker(body["Name"])
                self.wachtwoorden[uid] = body.get("Password") or ""
                return 200, copy.deepcopy(self.gebruikers[uid])
            if len(delen) == 3 and delen[0] == "Users" and delen[2] == "Policy":
                self.gebruikers[delen[1]]["Policy"] = body
                return 204, None
            if pad == "/Users/Configuration":
                self.gebruikers[query["userId"]]["Configuration"] = body
                return 204, None
            if len(delen) == 3 and delen[0] == "UserItems" and delen[2] == "UserData":
                uid, item_id = query["userId"], delen[1]
                if item_id not in {i["Id"] for i in self.zichtbaar(uid)}:
                    return 404, None
                ud = self.userdata.setdefault((uid, item_id), {})
                ud.update(body)
                return 200, {"Played": False, "PlayCount": 0, "PlaybackPositionTicks": 0, "IsFavorite": False, **ud}
            return 404, None
        return 405, None
