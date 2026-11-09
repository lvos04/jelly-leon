"""Kleine Jellyfin-API-client (alleen stdlib) voor de wegwerp-stockserver van het harnas."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

CLIENT = 'MediaBrowser Client="b03-016-harnas", Device="harnas", DeviceId="jl-b03016-harnas", Version="1.0"'


class HttpFout(RuntimeError):
    def __init__(self, status: int, tekst: str) -> None:
        super().__init__(tekst)
        self.status = status


class Http:
    def __init__(self, basis: str, headers: dict[str, str] | None = None, timeout: float = 120.0) -> None:
        self.basis = basis.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout

    def ruw(self, methode: str, pad: str, query: dict[str, Any] | None = None, body: Any = None,
            headers: dict[str, str] | None = None) -> tuple[int, bytes, dict[str, str]]:
        url = self.basis + pad + ("?" + urllib.parse.urlencode(query, doseq=True) if query else "")
        data = json.dumps(body).encode() if body is not None else (b"" if methode in ("POST", "DELETE") else None)
        h = {"Accept": "application/json", **self.headers, **(headers or {})}
        if body is not None:
            h["Content-Type"] = "application/json"
        verzoek = urllib.request.Request(url, data=data, method=methode, headers=h)  # noqa: S310 - lokaal testadres
        try:
            with urllib.request.urlopen(verzoek, timeout=self.timeout) as antwoord:  # noqa: S310
                return antwoord.status, antwoord.read(), dict(antwoord.headers)
        except urllib.error.HTTPError as fout:
            return fout.code, fout.read(), dict(fout.headers or {})

    def doe(self, methode: str, pad: str, query: dict[str, Any] | None = None, body: Any = None,
            verwacht: tuple[int, ...] = (200, 204), headers: dict[str, str] | None = None) -> Any:
        status, ruw, _ = self.ruw(methode, pad, query, body, headers)
        if status not in verwacht:
            raise HttpFout(status, f"{methode} {pad} → HTTP {status}: {ruw[:300]!r}")
        if not ruw:
            return None
        try:
            return json.loads(ruw.decode("utf-8-sig"))
        except ValueError:
            return ruw.decode("utf-8", "replace")


def wacht_klaar(url: str, timeout: float = 240.0) -> dict[str, Any]:
    """Wacht tot /System/Info/Public geldige JSON met een versie geeft (12.x toont tijdens het laden HTML)."""
    einde = time.time() + timeout
    laatste = ""
    while time.time() < einde:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/System/Info/Public", timeout=5) as a:  # noqa: S310
                data = json.loads(a.read().decode("utf-8-sig"))
                if isinstance(data, dict) and data.get("Version"):
                    return data
        except (urllib.error.URLError, OSError, ValueError) as fout:
            laatste = str(fout)
        time.sleep(2)
    raise RuntimeError(f"{url} niet klaar binnen {timeout:.0f} s ({laatste})")


class Jellyfin:
    """Wizard, gebruikers, bibliotheken en de paar routes die het harnas meet."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.anoniem = Http(self.url, {"Authorization": CLIENT})
        self.admin: Http | None = None
        self.admin_id = ""
        self.token = ""

    def wizard(self, gebruiker: str, wachtwoord: str) -> None:
        a = self.anoniem
        for poging in range(30):
            try:
                a.doe("POST", "/Startup/Configuration", body={"UICulture": "nl", "MetadataCountryCode": "NL",
                                                             "PreferredMetadataLanguage": "nl"})
                break
            except HttpFout as fout:
                if fout.status != 503 or poging == 29:
                    raise
                time.sleep(2)
        a.doe("GET", "/Startup/User")
        a.doe("POST", "/Startup/User", body={"Name": gebruiker, "Password": wachtwoord})
        a.doe("POST", "/Startup/RemoteAccess", body={"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False})
        a.doe("POST", "/Startup/Complete")
        self.login(gebruiker, wachtwoord)

    def login(self, gebruiker: str, wachtwoord: str) -> None:
        auth = self.anoniem.doe("POST", "/Users/AuthenticateByName", body={"Username": gebruiker, "Pw": wachtwoord})
        self.token = auth["AccessToken"]
        self.admin_id = auth["User"]["Id"]
        self.admin = Http(self.url, {"Authorization": CLIENT + f', Token="{self.token}"'})

    @property
    def a(self) -> Http:
        if self.admin is None:
            raise RuntimeError("eerst inloggen")
        return self.admin

    def gebruiker(self, naam: str, wachtwoord: str, beleid: dict[str, Any] | None = None) -> str:
        uid = self.a.doe("POST", "/Users/New", body={"Name": naam, "Password": wachtwoord})["Id"]
        if beleid:
            huidig = self.a.doe("GET", f"/Users/{uid}")["Policy"]
            self.a.doe("POST", f"/Users/{uid}/Policy", body={**huidig, **beleid})
        return uid

    def bibliotheek(self, naam: str, soort: str, paden: list[str]) -> None:
        typen = {"movies": ["Movie"], "tvshows": ["Series", "Season", "Episode"]}.get(soort, ["Movie"])
        opties = {
            "EnableRealtimeMonitor": False, "SaveLocalMetadata": False, "EnableChapterImageExtraction": False,
            "ExtractChapterImagesDuringLibraryScan": False, "EnableTrickplayImageExtraction": False,
            "ExtractTrickplayImagesDuringLibraryScan": False, "SaveSubtitlesWithMedia": False,
            "SaveTrickplayWithMedia": False, "SaveLyricsWithMedia": False, "EnableEmbeddedTitles": False,
            "PathInfos": [{"Path": p} for p in paden], "MetadataSavers": [], "DisabledSubtitleFetchers": [],
            "SubtitleDownloadLanguages": [],
            # Geen online metadata: meetserver zonder internetverkeer, gelijke metadata voor alle systemen (ADR-0026).
            "TypeOptions": [{"Type": t, "MetadataFetchers": [], "MetadataFetcherOrder": [], "ImageFetchers": [],
                             "ImageFetcherOrder": []} for t in typen],
        }
        self.a.doe("POST", "/Library/VirtualFolders", {"name": naam, "collectionType": soort, "refreshLibrary": "false"},
                   body={"LibraryOptions": opties})

    def scan(self, timeout: float = 900.0) -> float:
        begin = time.time()
        self.a.doe("POST", "/Library/Refresh")
        time.sleep(3)
        while time.time() - begin < timeout:
            taken = self.a.doe("GET", "/ScheduledTasks", {"isHidden": "false"})
            if not any(t.get("State") == "Running" for t in taken):
                return time.time() - begin
            time.sleep(2)
        raise RuntimeError("bibliotheekscan duurt te lang")

    def items(self, extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        q = {"userId": self.admin_id, "recursive": "true", "includeItemTypes": "Movie,Episode",
             "fields": "Path,MediaStreams,MediaSources", "limit": "2000", **(extra or {})}
        return self.a.doe("GET", "/Items", q)["Items"]

    def encoding(self) -> dict[str, Any]:
        return self.a.doe("GET", "/System/Configuration/encoding")

    def zet_encoding(self, wijzigingen: dict[str, Any]) -> dict[str, Any]:
        nieuw = {**self.encoding(), **wijzigingen}
        self.a.doe("POST", "/System/Configuration/encoding", body=nieuw)
        return self.encoding()

    def playbackinfo(self, item_id: str, profiel: dict[str, Any], gebruiker: str | None = None,
                     extra: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {"DeviceProfile": profiel, "MaxStreamingBitrate": 120000000, "EnableDirectPlay": True,
                "EnableDirectStream": True, "EnableTranscoding": True, "AllowVideoStreamCopy": True,
                "AllowAudioStreamCopy": True, "AutoOpenLiveStream": False, **(extra or {})}
        return self.a.doe("POST", f"/Items/{item_id}/PlaybackInfo", {"userId": gebruiker or self.admin_id}, body=body)
