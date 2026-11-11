#!/usr/bin/env python3
"""Pluginproef van Jelly Leon (B03-017): JLT-68, JLT-64 en JLT-65 met de modules die nu bestaan (Core, Devices, Quality).

Opzet (alles in wegwerpcontainers op 127.0.0.1, als de aanroeper, zonder capabilities, media alleen-lezen):

1. **Zaai-run** op de stock-image zonder plugin: wizard, muziekbibliotheek, een kijker, één nummer als gespeeld en als
   favoriet gemarkeerd (kijkgeschiedenis), daarna stoppen.
2. De datamap wordt drie keer gekopieerd. **A1** en **A2** draaien op de stock-image zonder plugin: twee gelijke
   controle-runs, hun onderlinge verschil is de ruis (tijdstempels, sessie-ID's). **B** draait op de image onder test
   mét de plugin en doorloopt hetzelfde scenario (aanmelden, afspelen melden, een gebruiker aanmaken en verwijderen).
3. Tijdens B: de plugin laadt, de routetabel van de server is gelijk aan het OpenAPI-bestand, de Hub-simulator
   (hub_sim.py) probeert alle weigeringen, de foutcatalogus is per module gelijk, connector-uitvoer wordt tegen het
   schema gelegd en op namen, titels, paden en IP-adressen doorzocht, en na het verwijderen van de gebruiker staat
   zijn account-ID nergens meer in de bestanden van de plugin.
4. Na afloop: elke tabel van de serverdatabase van B tegen A1 (alles wat tussen A1 en A2 gelijk is moet in B exact
   gelijk zijn; UserData zonder enig masker), de bestandsboom, de sha256 van het mediacorpus en een scan van de logs
   op geheimen. Met `--plugin-map` volgt run **D**: plugin weggehaald → de server geeft weer dezelfde antwoorden.

Dit is een simulatie: geen echte Hub, geen echte NAS, geen echte clients. Exitcode 0 = alle onderdelen geslaagd.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

E2E = Path(__file__).resolve().parent
REPO = E2E.parents[2]
sys.path.insert(0, str(REPO / "tools" / "b03-harnas"))
sys.path.insert(0, str(E2E))

import proef_lib as pl  # noqa: E402
from b03h.jfapi import Http, wacht_klaar  # noqa: E402
from hub_sim import HubSim, Sleutel  # noqa: E402

PREFIXEN = ("/connector/v1", "/media/v1")
OPENAPI = REPO / "docs" / "openapi" / "jelly-leon-plugin.openapi.json"
PLUGIN_ID = "6a0c5f2e3b9d4c719e0a4f1d2b8c7e51"
PLUGIN_DLL = "Jellyfin.Plugin.JellyLeon.dll"
MUZIEK = "/media/muziek"
BEHEER, KIJKER, WEG = "jl-proef-beheer", "Kijker-Zeldzaam-7391", "Weg-Zeldzaam-5527"
TOESTEL_BEHEER, TOESTEL_WEG = "Beheertoestel-Zeldzaam-4418", "Toestel-Zeldzaam-8846"
# Bestanden die run B extra mag hebben ten opzichte van de controle-run (toegestane wijzigingslijst, JLT-65).
TOEGESTAAN_NIEUW = ("plugins/JellyLeon_", "plugins/configurations/Jellyfin.Plugin.JellyLeon.xml", "data/jelly-leon/",
                    "jelly-leon/datamap-versie", "log/")
# Tabellen waarvoor "ruis, geen uitspraak" niet genoeg is: hier moet de vergelijking echt slagen (HARDE EIS).
BESCHERMD = ("UserData", "BaseItems", "Users", "Permissions", "Preferences", "DisplayPreferences", "MediaSegments",
             "ItemValues", "ItemValuesMap", "MediaStreamInfos", "Chapters", "Peoples", "PeopleBaseItemMap",
             "AncestorIds", "BaseItemProviders", "BaseItemImageInfos", "ItemDisplayPreferences", "CustomItemDisplayPreferences")


def docker(*args: str, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True, timeout=timeout)


def vrije_poort() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def client(toestel: str, toestel_id: str, token: str = "") -> dict[str, str]:
    kop = f'MediaBrowser Client="jl-pluginproef", Device="{toestel}", DeviceId="{toestel_id}", Version="1.0"'
    return {"Authorization": kop + (f', Token="{token}"' if token else "")}


class Verslag:
    def __init__(self) -> None:
        self.regels: list[dict[str, Any]] = []
        self.geheimen: dict[str, str] = {}

    def test(self, jlt: str, naam: str, ok: bool, detail: str = "") -> bool:
        for geheim in self.geheimen.values():
            detail = detail.replace(geheim, "<geheim>")
        self.regels.append({"jlt": jlt, "test": naam, "geslaagd": bool(ok), "detail": detail[:600]})
        print(f"[{'OK  ' if ok else 'FOUT'}] {jlt} {naam}: {detail[:300]}", flush=True)
        return bool(ok)

    def geheim(self, naam: str, waarde: str) -> str:
        """Onthoudt een geheim (naam = `soort:welke`), zodat het nooit in het rapport komt en in de logs gezocht wordt."""
        self.geheimen[naam] = waarde
        return waarde


class Server:
    """Eén wegwerpcontainer op een eigen kopie van de datamap."""

    def __init__(self, naam: str, image: str, map_: Path, media: Path, geheugen: str = "2g") -> None:
        self.naam, self.image, self.map, self.media, self.geheugen = naam, image, map_, media, geheugen
        self.url = ""
        self.log = ""

    @property
    def config(self) -> Path:
        return self.map / "config"

    def start(self) -> dict[str, Any]:
        (self.map / "config").mkdir(parents=True, exist_ok=True)
        (self.map / "cache").mkdir(parents=True, exist_ok=True)
        poort = vrije_poort()
        docker("run", "-d", "--name", self.naam, "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--memory", self.geheugen, "-e", "TZ=UTC",
               "-p", f"127.0.0.1:{poort}:8096", "-v", f"{self.map / 'config'}:/config", "-v", f"{self.map / 'cache'}:/cache",
               "-v", f"{self.media}:{MUZIEK}:ro", self.image)
        self.url = f"http://127.0.0.1:{poort}"
        return wacht_klaar(self.url, timeout=300)

    def stop(self) -> None:
        docker("stop", "-t", "60", self.naam, check=False)
        uitvoer = docker("logs", self.naam, check=False)
        self.log = (uitvoer.stdout or "") + (uitvoer.stderr or "")
        docker("rm", "-f", self.naam, check=False)

    def logtekst(self) -> str:
        """Alles wat de server logde: de containeruitvoer en de logbestanden in de datamap."""
        bestanden = sorted(p for p in (self.config / "log").glob("*") if p.is_file()) if (self.config / "log").exists() else []
        return self.log + "\n" + "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in bestanden)


class Sessie:
    """Een aangemelde gebruiker op een server."""

    def __init__(self, server: Server, naam: str, wachtwoord: str, toestel: str, toestel_id: str) -> None:
        anoniem = Http(server.url, client(toestel, toestel_id))
        antwoord = anoniem.doe("POST", "/Users/AuthenticateByName", body={"Username": naam, "Pw": wachtwoord})
        self.token = antwoord["AccessToken"]
        self.id = antwoord["User"]["Id"]
        self.http = Http(server.url, client(toestel, toestel_id, self.token))


# ----------------------------------------------------------------------------------------------- zaaien
def zaai(server: Server, wachtwoorden: dict[str, str]) -> str:
    """Richt de stockserver in en zet echte kijkgeschiedenis neer via de officiële API. Geeft het audio-ID terug."""
    anoniem = Http(server.url, client(TOESTEL_BEHEER, "jl-proef-beheer"))
    for poging in range(30):
        status, _, _ = anoniem.ruw("POST", "/Startup/Configuration", body={
            "UICulture": "nl", "MetadataCountryCode": "NL", "PreferredMetadataLanguage": "nl"})
        if status in (200, 204):
            break
        if poging == 29:
            raise RuntimeError(f"wizard start niet (HTTP {status})")
        time.sleep(2)
    anoniem.doe("GET", "/Startup/User")
    anoniem.doe("POST", "/Startup/User", body={"Name": BEHEER, "Password": wachtwoorden[BEHEER]})
    anoniem.doe("POST", "/Startup/RemoteAccess", body={"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False})
    anoniem.doe("POST", "/Startup/Complete")
    beheer = Sessie(server, BEHEER, wachtwoorden[BEHEER], TOESTEL_BEHEER, "jl-proef-beheer")
    beheer.http.doe("POST", "/Library/VirtualFolders", {"name": "Muziek", "collectionType": "music", "paths": MUZIEK,
                                                       "refreshLibrary": "true"}, body={"LibraryOptions": {}})
    audio = ""
    einde = time.monotonic() + 240
    while time.monotonic() < einde and not audio:
        items = beheer.http.doe("GET", "/Items", {"recursive": "true", "includeItemTypes": "Audio"}).get("Items", [])
        audio = items[0]["Id"] if items else ""
        if not audio:
            beheer.http.doe("POST", "/Library/Refresh")
            time.sleep(3)
    if not audio:
        raise RuntimeError("de bibliotheekscan vond het testbestand niet")
    wacht_op_taken(beheer.http)
    beheer.http.doe("POST", "/Users/New", body={"Name": KIJKER, "Password": wachtwoorden[KIJKER]})
    kijker = Sessie(server, KIJKER, wachtwoorden[KIJKER], "Kijkertoestel-Zeldzaam-2207", "jl-proef-kijker")
    # Kijkgeschiedenis die behouden moet blijven: gespeeld en favoriet, voor de beheerder en voor de kijker.
    for wie in (beheer, kijker):
        wie.http.doe("POST", f"/UserPlayedItems/{audio}", {"userId": wie.id})
        wie.http.doe("POST", f"/UserFavoriteItems/{audio}", {"userId": wie.id})
    wacht_op_taken(beheer.http)
    return audio


def wacht_op_taken(beheer: Http, timeout: float = 240.0) -> None:
    """Wacht tot geen geplande taak meer loopt (twee peilingen na elkaar), zodat de kopieën gelijk beginnen."""
    einde, rustig = time.monotonic() + timeout, 0
    while time.monotonic() < einde:
        lopend = [t.get("Name") for t in beheer.doe("GET", "/ScheduledTasks") if t.get("State") != "Idle"]
        rustig = rustig + 1 if not lopend else 0
        if rustig >= 2:
            return
        time.sleep(2)
    raise RuntimeError("geplande taken blijven lopen")


# ----------------------------------------------------------------------------------------------- scenario
def opname(beheer: Sessie, audio: str) -> dict[str, Any]:
    """De vaste lijst Jellyfin-antwoorden van JLT-64 (status + JSON), als de beheerder."""
    h, uid = beheer.http, beheer.id
    vragen: list[tuple[str, str, str, dict[str, Any] | None, Any]] = [
        ("items", "GET", "/Items", {"userId": uid, "recursive": "true", "sortBy": "SortName",
                                    "fields": "Path,MediaSources,ProviderIds,DateCreated,Genres"}, None),
        ("users-items", "GET", f"/Users/{uid}/Items", {"recursive": "true", "sortBy": "SortName"}, None),
        ("item", "GET", f"/Items/{audio}", {"userId": uid}, None),
        ("userdata", "GET", f"/UserItems/{audio}/UserData", {"userId": uid}, None),
        ("playbackinfo", "POST", f"/Items/{audio}/PlaybackInfo", {"userId": uid}, {}),
        ("mediasegments", "GET", f"/MediaSegments/{audio}", None, None),
        ("syncplay", "GET", "/SyncPlay/List", None, None),
        ("similar", "GET", f"/Items/{audio}/Similar", {"userId": uid}, None),
        ("virtualfolders", "GET", "/Library/VirtualFolders", None, None),
        ("users", "GET", "/Users", None, None),
    ]
    uit: dict[str, Any] = {}
    for naam, methode, pad, query, body in vragen:
        status, ruw, _ = h.ruw(methode, pad, query, body)
        try:
            inhoud: Any = json.loads(ruw.decode("utf-8-sig")) if ruw else None
        except ValueError:
            inhoud = ruw.decode("utf-8", "replace")
        uit[naam] = {"status": status, "json": inhoud}
    return uit


def afspelen_en_verwijderen(server: Server, beheer: Sessie, audio: str, ww_weg: str, tussen: Any = None) -> str:
    """Het gedeelde scenario: een tijdelijke beheerder meldt zich aan, transcodeert en speelt af, en wordt verwijderd.

    Geeft het sessietoken van de tijdelijke gebruiker terug (voor de logscan).
    """
    weg_id = beheer.http.doe("POST", "/Users/New", body={"Name": WEG, "Password": ww_weg})["Id"]
    beleid = beheer.http.doe("GET", f"/Users/{weg_id}")["Policy"]
    beheer.http.doe("POST", f"/Users/{weg_id}/Policy", body={**beleid, "IsAdministrator": True})
    weg = Sessie(server, WEG, ww_weg, TOESTEL_WEG, "jl-proef-weg")
    sessie = "jl-proef-afspeelsessie"
    # Een echte transcode (WAV → MP3): de server erkent PlayMethod=Transcode alleen als er een transcodeertaak met dit
    # PlaySessionId bestaat; anders maakt hij er zelf DirectPlay van.
    status, geluid, _ = weg.http.ruw("GET", f"/Audio/{audio}/stream.mp3", {
        "static": "false", "audioCodec": "mp3", "audioBitRate": 64000, "playSessionId": sessie, "mediaSourceId": audio,
        "deviceId": "jl-proef-weg"})
    if status != 200 or len(geluid) < 500:
        raise RuntimeError(f"transcode leverde geen geluid (HTTP {status}, {len(geluid)} bytes)")
    basis = {"ItemId": audio, "MediaSourceId": audio, "PlaySessionId": sessie, "PlayMethod": "Transcode", "CanSeek": True}
    weg.http.doe("POST", "/Sessions/Playing", body={**basis, "PositionTicks": 0})
    weg.http.doe("POST", "/Sessions/Playing/Progress", body={**basis, "PositionTicks": 10_000_000})
    weg.http.doe("POST", "/Sessions/Playing/Stopped", body={**basis, "PositionTicks": 20_000_000})
    if tussen is not None:
        tussen(weg)
    beheer.http.doe("DELETE", f"/Users/{weg_id}")
    return weg.token


# ----------------------------------------------------------------------------------------------- plugincontroles
class Plugin:
    """De controles die alleen in run B draaien."""

    def __init__(self, v: Verslag, server: Server, beheer: Sessie, kijker: Sessie, doc: dict[str, Any]) -> None:
        self.v, self.server, self.beheer, self.kijker, self.doc = v, server, beheer, kijker, doc
        self.hub = HubSim()
        self.tokens: list[str] = []
        self.connector_uitvoer: list[Any] = []
        self.catalogus: dict[str, dict[str, tuple[int, str]]] = {}

    # -- kleine hulpjes
    def hub_vraag(self, methode: str, pad: str, token: str | None, query: dict[str, Any] | None = None,
                  body: Any = None) -> tuple[int, Any, bytes]:
        if token is not None and not token.startswith("svc_"):
            self.tokens.append(token)
        kop = {"Authorization": "Bearer " + token} if token is not None else {}
        status, ruw, _ = Http(self.server.url).ruw(methode, pad, query, body, kop)
        return status, _json(ruw), ruw

    def fout(self, jlt: str, naam: str, antwoord: tuple[int, Any, bytes], status: int, code: str,
             reden: str | None = None) -> bool:
        kreeg, inhoud, _ = antwoord
        vorm = isinstance(inhoud, dict) and set(inhoud) == {"code", "message", "details", "trace_id"}
        ok = vorm and kreeg == status and inhoud["code"] == code and _is_uuid(inhoud["trace_id"]) \
            and isinstance(inhoud["message"], str) and inhoud["message"] != ""
        if ok and reden is not None:
            ok = isinstance(inhoud["details"], dict) and inhoud["details"].get("reason") == reden
        schema = pl.antwoordschema(self.doc, *self._laatste, kreeg) if self._laatste else {}
        if ok and schema is None:
            ok = False
        kort = pl.tekst_van(inhoud)[:160] if not ok else ""
        return self.v.test(jlt, naam, ok, f"HTTP {kreeg} (verwacht {status} {code}{'/' + reden if reden else ''}) {kort}")

    _laatste: tuple[str, str] | None = None

    def schema(self, jlt: str, naam: str, methode: str, pad: str, antwoord: tuple[int, Any, bytes], status: int = 200) -> bool:
        kreeg, inhoud, _ = antwoord
        verwacht = pl.antwoordschema(self.doc, methode, pad, kreeg)
        if kreeg != status or verwacht is None:
            return self.v.test(jlt, naam, False, f"HTTP {kreeg} (verwacht {status}): {pl.tekst_van(inhoud)[:200]}")
        fouten = pl.valideer(inhoud, verwacht, self.doc)
        return self.v.test(jlt, naam, not fouten, f"HTTP {kreeg}, schema: {'in orde' if not fouten else '; '.join(fouten[:4])}")

    def sessie_vraag(self, wie: Sessie | None, methode: str, pad: str, body: Any = None,
                     kop: dict[str, str] | None = None) -> tuple[int, Any, dict[str, str]]:
        http = wie.http if wie is not None else Http(self.server.url)
        status, ruw, headers = http.ruw(methode, pad, None, body, kop)
        return status, _json(ruw), {k.lower(): w for k, w in headers.items()}

    # -- onderdelen
    def geladen(self) -> None:
        lijst = self.beheer.http.doe("GET", "/Plugins")
        eigen = [p for p in lijst if p.get("Id", "").replace("-", "") == PLUGIN_ID]
        self.v.test("JLT-68", "plugin geladen", len(eigen) == 1 and eigen[0].get("Status") == "Active",
                    f"{[(p.get('Name'), p.get('Version'), p.get('Status')) for p in eigen]}")

    def routetabel(self, stock_openapi: dict[str, Any]) -> None:
        status, ruw, _ = Http(self.server.url).ruw("GET", "/api-docs/openapi.json")
        server = _json(ruw) if status == 200 else {}
        ok = self.v.test("JLT-68", "endpointlijst van de server leesbaar", status == 200 and isinstance(server, dict),
                         f"/api-docs/openapi.json → HTTP {status} (een dubbele route laat deze lijst falen)")
        if not ok:
            return
        echt, beloofd = pl.routes(server, PREFIXEN), pl.routes(self.doc, PREFIXEN)
        self.v.test("JLT-68", "routetabel gelijk aan het OpenAPI-bestand", echt == beloofd,
                    f"{len(echt)} routes op de server, {len(beloofd)} in het bestand; alleen server: {sorted(echt - beloofd)}; "
                    f"alleen bestand: {sorted(beloofd - echt)}")
        # JLT-64: de plugin voegt alleen paden toe; elke upstream-route staat er nog precies zo in.
        zonder = {p: o for p, o in server.get("paths", {}).items() if not p.startswith(PREFIXEN)}
        stock = stock_openapi.get("paths", {})
        weg, erbij = sorted(set(stock) - set(zonder)), sorted(set(zonder) - set(stock))
        anders = sorted(p for p in set(stock) & set(zonder) if stock[p] != zonder[p])
        self.v.test("JLT-64", "OpenAPI: alleen nieuwe paden onder /media/v1 en /connector/v1", not weg and not erbij and not anders,
                    f"{len(stock)} upstream-paden; verdwenen: {weg[:5]}; erbij buiten de prefixen: {erbij[:5]}; gewijzigd: {anders[:5]}")
        schemas_stock = stock_openapi.get("components", {}).get("schemas", {})
        schemas = server.get("components", {}).get("schemas", {})
        kapot = sorted(n for n, s in schemas_stock.items() if schemas.get(n) != s)
        self.v.test("JLT-64", "OpenAPI: upstream-schema's ongewijzigd", not kapot,
                    f"{len(schemas_stock)} upstream-schema's; gewijzigd of verdwenen: {kapot[:5]}")

    def elke_route_antwoordt(self) -> None:
        """Zonder aanmelding geeft elke route het 401-foutbody van de plugin: precies één handler, geen 404/405/500."""
        mis = []
        for methode, pad in sorted(pl.routes(self.doc, PREFIXEN)):
            if pad == "/media/v1/version":
                continue
            echt_pad = pad.replace("{id}", "x").replace("{slug}", "devices")
            status, ruw, _ = Http(self.server.url).ruw(methode, echt_pad, body={} if methode in ("PUT", "POST") else None)
            inhoud = _json(ruw)
            if status != 401 or not isinstance(inhoud, dict) or inhoud.get("code") != "unauthorized":
                mis.append(f"{methode} {pad} → {status}")
        self.v.test("JLT-68", "elke route precies één keer (401 van de plugin zonder aanmelding)", not mis,
                    f"{len(pl.routes(self.doc, PREFIXEN)) - 1} routes gevraagd; afwijkend: {mis}")
        status, ruw, _ = self.beheer.http.ruw("GET", "/media/v1/version")
        self.v.test("JLT-68", "GET /media/v1/version", status == 200 and pl.valideer(
            _json(ruw), pl.antwoordschema(self.doc, "GET", "/media/v1/version", 200) or {}, self.doc) == [], f"HTTP {status}")

    def zonder_pin(self) -> None:
        self._laatste = ("GET", "/connector/v1/discover")
        self.fout("JLT-68", "Hub zonder pin → 401 unauthorized/not_linked",
                  self.hub_vraag("GET", "/connector/v1/discover", self.hub.token()), 401, "unauthorized", "not_linked")
        status, inhoud, _ = self.sessie_vraag(self.beheer, "GET", "/media/v1/hub-link")
        self.v.test("JLT-68", "hub-link begint als not_linked", status == 200 and inhoud.get("status") == "not_linked"
                    and inhoud.get("fingerprint") is None, f"HTTP {status} {pl.tekst_van(inhoud)[:160]}")

    def modules_uit(self, moment: str) -> None:
        status, inhoud, _ = self.sessie_vraag(self.beheer, "GET", "/media/v1/modules")
        standen = {m["slug"]: m["enabled"] for m in inhoud.get("items", [])} if status == 200 else {}
        self.v.test("JLT-64", f"modules staan uit ({moment})", standen == {"devices": False, "quality": False}, f"{standen}")
        for slug in ("devices", "quality"):
            for pad in (f"/media/v1/{slug}/status", f"/media/v1/{slug}/settings"):
                self._laatste = ("GET", pad)
                antwoord = self.sessie_vraag(self.beheer, "GET", pad)
                self.fout("JLT-64", f"module {slug} uit → GET {pad} is weg ({moment})", (antwoord[0], antwoord[1], b""), 404, "not_found")
            uit = self.sessie_vraag(self.beheer, "GET", f"/media/v1/{slug}/status")
            self.catalogus.setdefault("module uit → GET status", {})[slug] = self._code(uit)

    def pin(self) -> None:
        set_, afdruk = self.hub.sleutelset(), self.hub.vingerafdruk()
        status, inhoud, _ = self.sessie_vraag(self.beheer, "POST", "/media/v1/hub-link/verify", {"keyset": set_})
        self.v.test("JLT-68", "verify rekent dezelfde vingerafdruk als de Hub-simulator",
                    status == 200 and inhoud.get("fingerprint") == afdruk,
                    f"HTTP {status}; plugin {inhoud.get('fingerprint')}, simulator {afdruk}")
        verkeerd = HubSim().vingerafdruk()
        body = {"keyset": set_, "fingerprint": verkeerd, "service_id": self.hub.service_id}
        self._laatste = ("PUT", "/media/v1/hub-link")
        a = self.sessie_vraag(self.beheer, "PUT", "/media/v1/hub-link", body, {"Idempotency-Key": str(uuid.uuid4())})
        ok = self.fout("JLT-68", "pinnen met een verkeerde vingerafdruk geweigerd", (a[0], a[1], b""), 422, "validation_error")
        if ok:
            self.v.test("JLT-68", "weigering noemt vingerafdruk_klopt_niet", "vingerafdruk_klopt_niet" in pl.tekst_van(a[1]), "")
        a = self.sessie_vraag(self.kijker, "PUT", "/media/v1/hub-link", {**body, "fingerprint": afdruk}, {"Idempotency-Key": str(uuid.uuid4())})
        self.fout("JLT-68", "een gewone kijker mag niet pinnen", (a[0], a[1], b""), 403, "forbidden", "admin_required")
        a = self.sessie_vraag(self.beheer, "PUT", "/media/v1/hub-link", {**body, "fingerprint": afdruk})
        self.fout("JLT-68", "pinnen zonder Idempotency-Key", (a[0], a[1], b""), 400, "idempotency_key_required")
        sleutel = str(uuid.uuid4())
        goed = {**body, "fingerprint": afdruk.lower().replace("-", " ")}
        status, inhoud, _ = self.sessie_vraag(self.beheer, "PUT", "/media/v1/hub-link", goed, {"Idempotency-Key": sleutel})
        self.v.test("JLT-68", "pinnen na overtikken van de vingerafdruk", status == 200 and inhoud.get("status") == "linked"
                    and inhoud.get("fingerprint") == afdruk and inhoud.get("service_id") == self.hub.service_id
                    and pl.valideer(inhoud, pl.antwoordschema(self.doc, "PUT", "/media/v1/hub-link", 200) or {}, self.doc) == [],
                    f"HTTP {status} {pl.tekst_van(inhoud)[:200]}")
        status2, inhoud2, _ = self.sessie_vraag(self.beheer, "PUT", "/media/v1/hub-link", goed, {"Idempotency-Key": sleutel})
        self.v.test("JLT-68", "zelfde Idempotency-Key en body → zelfde antwoord", (status2, inhoud2) == (status, inhoud), f"HTTP {status2}")

    def hub_weigeringen(self) -> None:
        d = ("GET", "/connector/v1/discover")
        self._laatste = d
        hub = self.hub
        self.schema("JLT-68", "Hub met pin, rol admin → discover", *d, self.hub_vraag(*d, hub.token(rollen=["admin"])))
        self.schema("JLT-68", "Hub dienst-JWT (hub_service) → discover", *d, self.hub_vraag(*d, hub.token(gebruik="hub_service")))
        gevallen: list[tuple[str, str | None, int, str, str | None]] = [
            ("rol kind → 403", hub.token(rollen=["kind"]), 403, "forbidden", "role_kind"),
            ("rol kind naast viewer → 403", hub.token(rollen=["viewer", "kind"]), 403, "forbidden", "role_kind"),
            ("verlopen token", hub.token(nu=time.time() - 600), 401, "unauthorized", "token_expired"),
            ("onbekende kid", hub.token(sleutel=Sleutel("onbekend-1")), 401, "unauthorized", "unknown_key"),
            ("bekende kid, andere sleutel", hub.token(sleutel=Sleutel(hub.jwt.kid)), 401, "unauthorized", "invalid_token"),
            ("gebroken handtekening", hub.token(vervals=True), 401, "unauthorized", "invalid_token"),
            ("alg none", hub.token(kop={"alg": "none"}), 401, "unauthorized", "invalid_token"),
            ("verkeerde audience", hub.token(wijzig={"aud": "mediaguard"}), 401, "unauthorized", "invalid_token"),
            ("verkeerde issuer", hub.token(wijzig={"iss": "iemand"}), 401, "unauthorized", "invalid_token"),
            ("levensduur langer dan 120 s", hub.token(levensduur=600), 401, "unauthorized", "invalid_token"),
            ("policy-sleutel als JWT-sleutel", hub.token(sleutel=hub.policy), 401, "unauthorized", "unknown_key"),
            ("servicetoken svc_…", "svc_" + uuid.uuid4().hex, 401, "unauthorized", "service_token_not_accepted"),
            ("zonder jti", hub.token(weglaten=("jti",)), 401, "unauthorized", "jti_missing"),
            ("dienst-JWT met andere service_id", hub.token(gebruik="hub_service", wijzig={"service_id": str(uuid.uuid4())}),
             401, "unauthorized", "token_use_invalid"),
            ("gebruikers-JWT zonder rollen", hub.token(wijzig={"roles": []}), 401, "unauthorized", "token_use_invalid"),
            ("onbekende token_use", hub.token(wijzig={"token_use": "iets"}), 401, "unauthorized", "token_use_invalid"),
            ("zonder Authorization", None, 401, "unauthorized", None),
        ]
        for naam, token, status, code, reden in gevallen:
            self.fout("JLT-68", f"Hub: {naam}", self.hub_vraag(*d, token), status, code, reden)
        # Een tweede mutatie met dezelfde jti is een herhaling; de eerste krijgt het eerlijke 501.
        token = hub.token()
        for route in ("propose", "apply", "rollback"):
            self._laatste = ("POST", f"/connector/v1/{route}")
            self.fout("JLT-68", f"POST /connector/v1/{route} bestaat nog niet → 501",
                      self.hub_vraag("POST", f"/connector/v1/{route}", hub.token() if route != "propose" else token, body={}),
                      501, "capability_unavailable")
        self._laatste = ("POST", "/connector/v1/propose")
        self.fout("JLT-68", "tweede mutatie met dezelfde jti → 401 token_replayed",
                  self.hub_vraag("POST", "/connector/v1/propose", token, body={}), 401, "unauthorized", "token_replayed")
        self._laatste = ("GET", "/connector/v1/evidence/{id}")
        self.fout("JLT-68", "GET /connector/v1/evidence/{id} → 501",
                  self.hub_vraag("GET", "/connector/v1/evidence/abc", hub.token()), 501, "capability_unavailable")
        self._laatste = ("POST", "/connector/v1/propose")
        self.fout("JLT-68", "connector: body groter dan 1 MiB → 413",
                  self.hub_vraag("POST", "/connector/v1/propose", hub.token(), body={"x": "a" * 1_100_000}), 413, "payload_too_large")
        self._laatste = ("GET", "/connector/v1/items")
        self.fout("JLT-68", "items van een onbekend type → 422",
                  self.hub_vraag("GET", "/connector/v1/items", hub.token(), {"type": "titels"}), 422, "validation_error")

    def modules_aan(self) -> None:
        for slug in ("devices", "quality"):
            _, _, kop = self.sessie_vraag(self.beheer, "GET", "/media/v1/modules")
            etag = kop.get("etag", "")
            pad = f"/media/v1/modules/{slug}"
            self._laatste = ("PUT", "/media/v1/modules/{slug}")
            a = self.sessie_vraag(self.beheer, "PUT", pad, {"enabled": True}, {"Idempotency-Key": str(uuid.uuid4())})
            self.fout("JLT-68", f"module {slug} aanzetten zonder If-Match → 428", (a[0], a[1], b""), 428, "precondition_required")
            a = self.sessie_vraag(self.beheer, "PUT", pad, {"enabled": True}, {"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"oud"'})
            self.fout("JLT-68", f"module {slug} aanzetten met een oude If-Match → 412", (a[0], a[1], b""), 412, "precondition_failed")
            status, inhoud, _ = self.sessie_vraag(self.beheer, "PUT", pad, {"enabled": True},
                                                  {"Idempotency-Key": str(uuid.uuid4()), "If-Match": etag})
            aan = {m["slug"]: m["enabled"] for m in inhoud.get("items", [])} if status == 200 else {}
            self.v.test("JLT-68", f"module {slug} aangezet", status == 200 and aan.get(slug) is True, f"HTTP {status} {aan}")
        a = self.sessie_vraag(self.beheer, "PUT", "/media/v1/modules/bestaatniet", {"enabled": True},
                              {"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"x"'})
        self.fout("JLT-68", "onbekende module → 404", (a[0], a[1], b""), 404, "not_found")

    @staticmethod
    def _code(antwoord: tuple[int, Any, Any]) -> tuple[int, str]:
        return antwoord[0], antwoord[1].get("code", "") if isinstance(antwoord[1], dict) else ""

    def foutcatalogus(self) -> None:
        """Dezelfde situatie geeft in elke module dezelfde status en code (één catalogus, ADR-0030)."""
        verwacht = {
            "zonder aanmelding": (401, "unauthorized"), "gewone kijker": (403, "forbidden"),
            "zonder Idempotency-Key": (400, "idempotency_key_required"), "ongeldige Idempotency-Key": (400, "idempotency_key_invalid"),
            "zonder If-Match": (428, "precondition_required"), "oude If-Match": (412, "precondition_failed"),
            "ongeldige body": (422, "validation_error"), "geen JSON-object": (422, "validation_error"),
            "onbekend veld": (422, "validation_error"), "groter dan 1 MiB": (413, "payload_too_large"),
            "geslaagd": (200, ""), "herhaling zelfde sleutel en body": (200, ""),
            "zelfde sleutel, andere body": (422, "idempotency_key_reused"), "module uit → GET status": (404, "not_found"),
        }
        for slug in ("devices", "quality"):
            pad = f"/media/v1/{slug}/settings"
            status, inhoud, kop = self.sessie_vraag(self.beheer, "GET", pad)
            etag = kop.get("etag", "")
            self.v.test("JLT-68", f"{slug}: instellingen leesbaar met ETag", status == 200 and bool(etag) and pl.valideer(
                inhoud, pl.antwoordschema(self.doc, "GET", pad, 200) or {}, self.doc) == [], f"HTTP {status}, ETag {etag}")
            nieuw = {"bewaar_dagen": 14 if slug == "devices" else 60}

            def k(**extra: str) -> dict[str, str]:
                return {"Idempotency-Key": str(uuid.uuid4()), "If-Match": etag, **extra}  # noqa: B023 - direct gebruikt

            vast = {"Idempotency-Key": str(uuid.uuid4()), "If-Match": etag}
            situaties: list[tuple[str, tuple[int, Any, Any]]] = [
                ("zonder aanmelding", self.sessie_vraag(None, "PUT", pad, nieuw, k())),
                ("gewone kijker", self.sessie_vraag(self.kijker, "PUT", pad, nieuw, k())),
                ("zonder Idempotency-Key", self.sessie_vraag(self.beheer, "PUT", pad, nieuw, {"If-Match": etag})),
                ("ongeldige Idempotency-Key", self.sessie_vraag(self.beheer, "PUT", pad, nieuw, {"Idempotency-Key": "abc", "If-Match": etag})),
                ("zonder If-Match", self.sessie_vraag(self.beheer, "PUT", pad, nieuw, {"Idempotency-Key": str(uuid.uuid4())})),
                ("oude If-Match", self.sessie_vraag(self.beheer, "PUT", pad, nieuw, k(**{"If-Match": '"oud"'}))),
                ("ongeldige body", self.sessie_vraag(self.beheer, "PUT", pad, {"bewaar_dagen": 0}, k())),
                ("geen JSON-object", self.sessie_vraag(self.beheer, "PUT", pad, [1, 2], k())),
                ("onbekend veld", self.sessie_vraag(self.beheer, "PUT", pad, {**nieuw, "extra": 1}, k())),
                ("groter dan 1 MiB", self.sessie_vraag(self.beheer, "PUT", pad, {**nieuw, "x": "a" * 1_100_000}, k())),
                ("geslaagd", self.sessie_vraag(self.beheer, "PUT", pad, nieuw, vast)),
                ("herhaling zelfde sleutel en body", self.sessie_vraag(self.beheer, "PUT", pad, nieuw, vast)),
                ("zelfde sleutel, andere body", self.sessie_vraag(self.beheer, "PUT", pad, {"bewaar_dagen": 15}, vast)),
            ]
            for naam, antwoord in situaties:
                self.catalogus.setdefault(naam, {})[slug] = self._code(antwoord)
                vorm = antwoord[0] == 200 or (isinstance(antwoord[1], dict) and set(antwoord[1]) == {"code", "message", "details", "trace_id"})
                if not vorm or pl.antwoordschema(self.doc, "PUT", pad, antwoord[0]) is None:
                    self.v.test("JLT-68", f"{slug}: {naam} heeft het vaste foutbody en een beschreven status", False,
                                f"HTTP {antwoord[0]} {pl.tekst_van(antwoord[1])[:160]}")
            status, inhoud, _ = self.sessie_vraag(self.beheer, "GET", pad)
            self.v.test("JLT-68", f"{slug}: alleen de geslaagde wijziging is doorgevoerd", inhoud == nieuw, f"{inhoud}")
            self.schema("JLT-68", f"{slug}: status volgt het schema", "GET", f"/media/v1/{slug}/status",
                        (*self.sessie_vraag(self.beheer, "GET", f"/media/v1/{slug}/status")[:2], b""))
        for naam, per_module in sorted(self.catalogus.items()):
            gelijk = len(set(per_module.values())) == 1 and set(per_module) == {"devices", "quality"}
            self.v.test("JLT-68", f"foutcatalogus: {naam}", gelijk and per_module["devices"] == verwacht[naam],
                        f"{per_module} (verwacht {verwacht[naam]})")

    def connector(self, verboden: dict[str, str]) -> None:
        hub = self.hub
        status, discover, _ = antwoord = self.hub_vraag("GET", "/connector/v1/discover", hub.token())
        self.schema("JLT-68", "discover volgt het schema", "GET", "/connector/v1/discover", antwoord)
        self.connector_uitvoer.append(discover)
        typen = sorted(t for t in discover.get("limits", {}).get("max_age_s", {}) if t != "health") if status == 200 else []
        self.v.test("JLT-68", "discover noemt de itemtypes van de actieve modules",
                    typen == ["backups", "device", "playback_stats", "quality_finding", "quality_summary"]
                    and discover.get("app_id") == "jelly-leon" and discover.get("capabilities") == ["read"], f"{typen}")
        status, health, _ = antwoord = self.hub_vraag("GET", "/connector/v1/health", hub.token(gebruik="hub_service"))
        self.schema("JLT-68", "health volgt het schema", "GET", "/connector/v1/health", antwoord)
        self.connector_uitvoer.append(health)
        checks = {c["name"]: c["status"] for c in health.get("checks", [])} if status == 200 else {}
        self.v.test("JLT-68", "health: database, modules en mediamount gemeten; werker eerlijk onbekend",
                    checks.get("database") == "healthy" and checks.get("module.devices") == "healthy"
                    and checks.get("module.quality") == "healthy" and checks.get("media_mount") == "healthy"
                    and checks.get("worker") == "unknown" and health.get("status") == "unknown",
                    f"totaal {health.get('status')} ({health.get('reason_code')}); {checks}")
        aantal = 0
        for soort in typen:
            status, pagina, _ = antwoord = self.hub_vraag("GET", "/connector/v1/items", hub.token(), {"type": soort})
            self.schema("JLT-68", f"items {soort} volgen het schema", "GET", "/connector/v1/items", antwoord)
            self.connector_uitvoer.append(pagina)
            aantal += len(pagina.get("items", [])) if status == 200 else 0
        status, events, _ = antwoord = self.hub_vraag("GET", "/connector/v1/events", hub.token())
        self.schema("JLT-68", "events volgen het schema", "GET", "/connector/v1/events", antwoord)
        self.connector_uitvoer.append(events)
        lijst = events.get("items", []) if status == 200 else []
        soorten = sorted({e.get("event_type", "") for e in lijst})
        self.v.test("JLT-68", "events: minstens één echt event en elk event_type heeft drie segmenten",
                    len(lijst) >= 2 and all(len(s.split(".")) == 3 for s in soorten)
                    and {"media.transcode.started", "media.transcode.stopped"} <= set(soorten),
                    f"{len(lijst)} events {soorten}; {aantal} items over {len(typen)} types")
        volgende = events.get("next_cursor") if status == 200 else None
        if volgende is None:
            self.v.test("JLT-68", "events: de cursor geeft daarna niets dubbel", False, "geen next_cursor gekregen")
        else:
            status, leeg, _ = self.hub_vraag("GET", "/connector/v1/events", hub.token(), {"cursor": volgende})
            self.v.test("JLT-68", "events: de cursor geeft daarna niets dubbel",
                        status == 200 and leeg.get("items") == [] and leeg.get("next_cursor") == volgende, f"HTTP {status}, cursor {volgende}")
        self._laatste = ("GET", "/connector/v1/events")
        self.fout("JLT-68", "events: een verzonnen cursor wordt geweigerd",
                  self.hub_vraag("GET", "/connector/v1/events", hub.token(), {"cursor": "abc"}), 422, "validation_error")
        tekst = pl.tekst_van(self.connector_uitvoer)
        gevonden = sorted(naam for naam, waarde in verboden.items() if waarde and waarde.lower() in tekst.lower())
        adressen = sorted(set(pl.IPV4.findall(tekst)))
        self.v.test("JLT-68", "connector-uitvoer zonder titels, namen, account-ID's, paden of IP-adressen",
                    not gevonden and not adressen, f"{len(tekst)} tekens doorzocht op {len(verboden)} waarden; gevonden: {gevonden} {adressen}")


def _json(ruw: bytes) -> Any:
    try:
        return json.loads(ruw.decode("utf-8-sig")) if ruw else None
    except ValueError:
        return ruw[:200].decode("utf-8", "replace")


def _is_uuid(waarde: Any) -> bool:
    try:
        return isinstance(waarde, str) and str(uuid.UUID(waarde)) == waarde.lower()
    except ValueError:
        return False


# ----------------------------------------------------------------------------------------------- vergelijkingen
def vergelijk_opnames(v: Verslag, naam: str, a1: dict[str, Any], a2: dict[str, Any], b: dict[str, Any]) -> None:
    ruis = pl.verschillen(a1, a2)
    gelijk = pl.masker(b, ruis) == pl.masker(a1, ruis)
    anders = sorted(pl.pad_tekst(p) for p in pl.verschillen(pl.masker(a1, ruis), pl.masker(b, ruis)))
    statussen = {k: w["status"] for k, w in a1.items()}
    v.test("JLT-64", f"Jellyfin-antwoorden gelijk aan stock ({naam})", gelijk,
           f"{len(a1)} routes {statussen}; {len(ruis)} ruisvelden gemaskeerd; afwijkend: {anders[:6]}")


def vergelijk_databases(v: Verslag, werk: Path, a1: Server, a2: Server, b: Server) -> dict[str, Any]:
    bestanden = sorted(p.relative_to(a1.config).as_posix() for p in a1.config.rglob("*.db")
                       if "jelly-leon" not in p.relative_to(a1.config).parts)
    rapport: dict[str, Any] = {}
    for relatief in bestanden:
        kopieen = [pl.kopieer_db(s.config / relatief, werk / "db" / s.naam / relatief.replace("/", "_")) for s in (a1, a2, b)]
        if not kopieen[2].exists():
            v.test("JLT-65", f"database {relatief} bestaat ook in run B", False, "ontbreekt")
            continue
        uitkomst = pl.vergelijk_db(*kopieen)
        rapport[relatief] = uitkomst
        telling: dict[str, int] = {}
        for oordeel in uitkomst.values():
            telling[oordeel["oordeel"]] = telling.get(oordeel["oordeel"], 0) + 1
        afwijking = sorted(t for t, o in uitkomst.items() if o["oordeel"] == "afwijking")
        v.test("JLT-65", f"{relatief}: geen tabel wijkt af van de controle-run", not afwijking,
               f"{len(uitkomst)} tabellen {telling}; afwijkend: {afwijking}")
        onbeslist = sorted(t for t, o in uitkomst.items() if o["oordeel"] == "ruis_onvergelijkbaar")
        beschermd = [t for t in onbeslist if t in BESCHERMD]
        v.test("JLT-65", f"{relatief}: beschermde tabellen zijn echt vergeleken", not beschermd,
               f"zonder uitspraak (ruis tussen de controle-runs): {onbeslist}; daarvan beschermd: {beschermd}")
        if "UserData" in uitkomst:
            o = uitkomst["UserData"]
            v.test("JLT-65", "UserData (kijkgeschiedenis) exact gelijk, zonder masker", o["oordeel"] == "gelijk" and o["rijen"]["b"] > 0,
                   f"{o['oordeel']}, rijen {o['rijen']}, masker {o['masker']}")
    v.test("JLT-65", "serverdatabase gevonden en vergeleken", any("UserData" in u for u in rapport.values()), f"{bestanden}")
    return rapport


def vergelijk_bomen(v: Verslag, a1: Server, a2: Server, b: Server) -> None:
    ba1, ba2, bb = pl.boom(a1.config), pl.boom(a2.config), pl.boom(b.config)
    nieuw = sorted(p for p in set(bb) - set(ba1) if not p.startswith(TOEGESTAAN_NIEUW))
    weg = sorted(p for p in set(ba1) - set(bb) if p in ba2 and not p.startswith("log/"))
    v.test("JLT-65", "nieuwe bestanden alleen op de toegestane plekken", not nieuw,
           f"{len(set(bb) - set(ba1))} nieuwe bestanden in B; buiten de lijst {TOEGESTAAN_NIEUW}: {nieuw[:8]}")
    v.test("JLT-65", "geen bestand van de server verdwenen", not weg, f"verdwenen: {weg[:8]}")
    vast = [p for p in ba1 if ba2.get(p) == ba1[p] and not p.endswith((".db", ".db-wal", ".db-shm")) and not p.startswith("log/")]
    gewijzigd = sorted(p for p in vast if p in bb and bb[p] != ba1[p])
    v.test("JLT-65", "instellingen en overige bestanden van de server byte-gelijk", not gewijzigd,
           f"{len(vast)} bestanden die tussen de controle-runs gelijk zijn "
           f"(o.a. {sorted(p for p in vast if p.endswith('.xml'))[:6]}); gewijzigd in B: {gewijzigd[:8]}")


def geheimen_scan(v: Verslag, b: Server, plugin: Plugin, zout: bytes, extra_tekst: str,
                  stock: dict[tuple[str, str, str], int]) -> dict[str, Any]:
    """Zoekt alle geheimen van de proef in de logs, de pluginconfiguratie en de plugindata van run B.

    `stock` zijn de logregels waarin de controle-runs zónder plugin zelf een geheim schreven (upstream-gedrag). Die
    tellen niet als fout van de plugin, maar worden wel gemeld; alles wat daar niet in staat is een fout.
    """
    naalden: dict[str, str] = dict(v.geheimen)
    for i, token in enumerate(plugin.tokens):
        naalden[f"hubtoken:{i}"] = token
        naalden[f"hubhandtekening:{i}"] = token.rsplit(".", 1)[1]
    if zout:
        naalden.update({"zout:hex": zout.hex(), "zout:HEX": zout.hex().upper(), "zout:base64": base64.b64encode(zout).decode(),
                        "zout:base64url": base64.urlsafe_b64encode(zout).rstrip(b"=").decode()})
    tekst = b.logtekst()
    gevonden = pl.log_handtekeningen(tekst, naalden)
    upstream = {k: n for k, n in gevonden.items() if k in stock and k[0] in ("sessietoken", "wachtwoord") and "JellyLeon" not in k[1]}
    eigen = {k: n for k, n in gevonden.items() if k not in upstream}
    ruw_zout = bool(zout) and zout in tekst.encode("utf-8", "surrogateescape")
    plugin_regels = sum(1 for regel in tekst.splitlines() if "JellyLeon" in regel or "Jelly Leon" in regel)
    v.test("JLT-65", "logs: de plugin schrijft geen wachtwoorden, sessietokens, Hub-tokens of sleutelmateriaal",
           not eigen and not ruw_zout and len(tekst.splitlines()) > 20,
           f"{len(tekst.splitlines())} logregels ({plugin_regels} van de plugin) doorzocht op {len(naalden)} waarden; treffers van de plugin "
           f"of alleen in deze run: {sorted(eigen)}; regels die upstream zelf ook zonder plugin schrijft: {sorted(upstream)}")
    byte_naalden = {naam: waarde.encode() for naam, waarde in naalden.items()}
    if zout:
        byte_naalden["zout:ruw"] = zout
    xml = b.config / "plugins" / "configurations" / "Jellyfin.Plugin.JellyLeon.xml"
    in_xml = sorted(naam for naam, naald in byte_naalden.items() if xml.exists() and naald in xml.read_bytes())
    in_api = sorted(naam for naam, naald in byte_naalden.items() if naald in extra_tekst.encode())
    v.test("JLT-65", "pluginconfiguratie (XML en GET /Plugins/{id}/Configuration) zonder geheimen",
           xml.exists() and not in_xml and not in_api,
           f"XML {xml.stat().st_size if xml.exists() else 0} bytes; in XML: {in_xml}; via de API: {in_api}")
    buiten = pl.ruwe_treffers(b.config / "data" / "jelly-leon", byte_naalden, overslaan=("secrets/",))
    v.test("JLT-65", "plugindata buiten de geheimenmap zonder geheimen", not buiten, f"treffers: {dict(list(buiten.items())[:4])}")
    map_ = b.config / "data" / "jelly-leon" / "secrets"
    modi = {p.name: stat.S_IMODE(p.stat().st_mode) for p in [map_, *sorted(map_.glob("*"))]} if map_.exists() else {}
    goed = bool(modi) and modi.get("secrets") == 0o700 and all(m == 0o600 for n, m in modi.items() if n != "secrets")
    v.test("JLT-65", "geheimenmap 0700 en bestanden 0600", goed, f"{ {n: oct(m) for n, m in modi.items()} }")
    return {"upstream_logt_zelf": [{"soort": k[0], "logcategorie": k[1], "sjabloon": k[2], "aantal": n} for k, n in sorted(upstream.items())]}


def corpus(media: Path) -> dict[str, tuple[str, int, int]]:
    return {p.relative_to(media).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(media.rglob("*")) if p.is_file()}


# ----------------------------------------------------------------------------------------------- hoofdprogramma
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pluginproef JLT-64/65/68 (B03-017) in wegwerpcontainers.")
    parser.add_argument("--image", required=True, help="image onder test (stock 12.x met --plugin-map, of de jelly-leon-image)")
    parser.add_argument("--stock-image", default=None, help="stock 12.x-image voor de zaai- en controle-runs (standaard: --image)")
    parser.add_argument("--plugin-map", type=Path, default=None, help="map met de gebouwde plugin-DLL; weglaten als de image hem meelevert")
    parser.add_argument("--werkmap", default=None, help="map met minstens 2 GiB vrij (geen tmpfs)")
    parser.add_argument("--rapport", type=Path)
    args = parser.parse_args(argv)
    stock = args.stock_image or args.image
    if args.plugin_map is not None and not (args.plugin_map / PLUGIN_DLL).is_file():
        print(f"[FOUT] {args.plugin_map / PLUGIN_DLL} bestaat niet", file=sys.stderr)
        return 2
    werk = Path(tempfile.mkdtemp(prefix="jl-pluginproef-", dir=args.werkmap))
    media = werk / "media"
    media.mkdir()
    subprocess.run([sys.executable, str(E2E / "make_test_media.py"), str(media)], check=True, capture_output=True)
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    v = Verslag()
    ww = {BEHEER: v.geheim("wachtwoord:beheer", uuid.uuid4().hex), KIJKER: v.geheim("wachtwoord:kijker", uuid.uuid4().hex)}
    ww_weg = v.geheim("wachtwoord:tijdelijk", uuid.uuid4().hex)
    pid = os.getpid()
    servers: list[Server] = []
    info: dict[str, Any] = {}
    db_rapport: dict[str, Any] = {}
    log_rapport: dict[str, Any] = {}
    stock_log: dict[tuple[str, str, str], int] = {}
    try:
        corpus_voor = corpus(media)
        zaaier = Server(f"jl-pp-zaai-{pid}", stock, werk / "zaai", media)
        servers.append(zaaier)
        zaaier.start()
        audio = zaai(zaaier, ww)
        zaaier.stop()
        print(f"[INFO] zaai-run klaar (audio {audio})", flush=True)

        runs: dict[str, Server] = {}
        opnames: dict[str, dict[str, Any]] = {}
        openapi_stock: dict[str, Any] = {}
        for naam, image in (("a1", stock), ("a2", stock)):
            s = Server(f"jl-pp-{naam}-{pid}", image, werk / naam, media)
            shutil.copytree(zaaier.map, s.map, symlinks=True)
            servers.append(s)
            runs[naam] = s
            s.start()
            beheer = Sessie(s, BEHEER, ww[BEHEER], TOESTEL_BEHEER, "jl-proef-beheer")
            v.geheim(f"sessietoken:{naam}-beheer", beheer.token)
            v.geheim(f"sessietoken:{naam}-kijker", Sessie(s, KIJKER, ww[KIJKER], "Kijkertoestel-Zeldzaam-2207", "jl-proef-kijker").token)
            opnames[f"{naam}-voor"] = opname(beheer, audio)
            v.geheim(f"sessietoken:{naam}-tijdelijk", afspelen_en_verwijderen(s, beheer, audio, ww_weg))
            opnames[f"{naam}-na"] = opname(beheer, audio)
            if naam == "a1":
                openapi_stock = beheer.http.doe("GET", "/api-docs/openapi.json")
                status, _, _ = Http(s.url).ruw("GET", "/connector/v1/discover")
                v.test("JLT-64", "stock zonder plugin kent de pluginroutes niet", status == 404, f"GET /connector/v1/discover → HTTP {status}")
            s.stop()
            for sleutel, aantal in pl.log_handtekeningen(s.logtekst(), v.geheimen).items():
                stock_log[sleutel] = stock_log.get(sleutel, 0) + aantal
            print(f"[INFO] controle-run {naam} klaar ({len(stock_log)} soorten logregels met een geheim van upstream zelf)", flush=True)

        # ---- run B: de image onder test met de plugin
        b = Server(f"jl-pp-b-{pid}", args.image, werk / "b", media)
        shutil.copytree(zaaier.map, b.map, symlinks=True)
        if args.plugin_map is not None:
            doel = b.config / "plugins" / "JellyLeon_0.1.0.0"
            doel.mkdir(parents=True)
            shutil.copy2(args.plugin_map / PLUGIN_DLL, doel / PLUGIN_DLL)
        servers.append(b)
        info = b.start()
        beheer = Sessie(b, BEHEER, ww[BEHEER], TOESTEL_BEHEER, "jl-proef-beheer")
        kijker = Sessie(b, KIJKER, ww[KIJKER], "Kijkertoestel-Zeldzaam-2207", "jl-proef-kijker")
        v.geheim("sessietoken:b-beheer", beheer.token)
        v.geheim("sessietoken:b-kijker", kijker.token)
        plugin = Plugin(v, b, beheer, kijker, doc)
        plugin.geladen()
        plugin.routetabel(openapi_stock)
        plugin.elke_route_antwoordt()
        plugin.zonder_pin()
        plugin.modules_uit("begin")
        opnames["b-voor"] = opname(beheer, audio)
        vergelijk_opnames(v, "plugin geladen, modules uit", opnames["a1-voor"], opnames["a2-voor"], opnames["b-voor"])
        plugin.pin()
        plugin.hub_weigeringen()
        plugin.modules_aan()
        plugin.foutcatalogus()

        data = b.config / "data" / "jelly-leon"
        zout_pad = data / "secrets" / "opaque-id.salt"
        gemeten: dict[str, Any] = {}

        def tussen(weg: Sessie) -> None:
            """De tijdelijke beheerder wijzigt nog een instelling; daarna moet zijn account-ID in de plugindata staan."""
            v.geheim("sessietoken:b-tijdelijk", weg.token)
            _, _, kop = plugin.sessie_vraag(weg, "GET", "/media/v1/devices/settings")
            status, _, _ = plugin.sessie_vraag(weg, "PUT", "/media/v1/devices/settings", {"bewaar_dagen": 21},
                                               {"Idempotency-Key": str(uuid.uuid4()), "If-Match": kop.get("etag", "")})
            zout = zout_pad.read_bytes() if zout_pad.exists() else b""
            pseudoniem = "o_" + hmac.new(zout, b"user\n" + uuid.UUID(weg.id).hex.encode(), hashlib.sha256).digest()[:16].hex()
            gemeten.update({"id": weg.id, "zout": zout, "naalden": {**pl.guid_vormen(weg.id), "pseudoniem": pseudoniem.encode()}})
            voor = pl.ruwe_treffers(data, gemeten["naalden"])
            v.test("JLT-65", "controle vooraf: account-ID en pseudoniem staan in de plugindata",
                   status == 200 and "N" in voor and "pseudoniem" in voor,
                   f"PUT → HTTP {status}; gevonden vormen: { {n: p for n, p in voor.items()} }")
            verboden = {"titel": "Sinus 440 Hz", "album": "Smoketest", "artiest": "Jelly Leon Test", "beheerder": BEHEER, "kijker": KIJKER,
                        "tijdelijke gebruiker": WEG, "toestel beheer": TOESTEL_BEHEER, "toestel tijdelijk": TOESTEL_WEG,
                        "toestel-id": "jl-proef-weg", "mediapad": "/media/", "configpad": "/config", "afspeelsessie": "jl-proef-afspeelsessie",
                        "id tijdelijk N": uuid.UUID(weg.id).hex, "id tijdelijk D": str(uuid.UUID(weg.id)),
                        "id beheer N": uuid.UUID(beheer.id).hex, "id beheer D": str(uuid.UUID(beheer.id)),
                        "id kijker N": uuid.UUID(kijker.id).hex, "audio-id": uuid.UUID(audio).hex}
            plugin.connector(verboden)

        afspelen_en_verwijderen(b, beheer, audio, ww_weg, tussen)
        na: dict[str, list[str]] = {"nog": ["niet gemeten"]}
        einde = time.monotonic() + 20
        while time.monotonic() < einde and na:
            na = pl.ruwe_treffers(data, gemeten.get("naalden", {})) if gemeten else na
            if na:
                time.sleep(0.5)
        v.test("JLT-65", "na UserDeleted 0 treffers op het account-ID (alle schrijfwijzen) en het pseudoniem", bool(gemeten) and not na,
               f"{len(gemeten.get('naalden', {}))} schrijfwijzen in {len(pl.boom(data))} bestanden onder data/jelly-leon; treffers: {na}")
        blijft = pl.ruwe_treffers(data, {"pseudoniem beheerder": ("o_" + hmac.new(
            gemeten.get("zout", b""), b"user\n" + uuid.UUID(beheer.id).hex.encode(), hashlib.sha256).digest()[:16].hex()).encode()})
        v.test("JLT-65", "gegevens van de overige gebruikers blijven staan", "pseudoniem beheerder" in blijft, f"{blijft}")
        status, register, _ = plugin.sessie_vraag(beheer, "GET", "/media/v1/privacy/register")
        plugin.schema("JLT-65", "register van persoonsgegevens volgt het schema", "GET", "/media/v1/privacy/register", (status, register, b""))
        opnames["b-na"] = opname(beheer, audio)
        vergelijk_opnames(v, "modules aan, na het scenario", opnames["a1-na"], opnames["a2-na"], opnames["b-na"])
        status, ruw, _ = beheer.http.ruw("GET", f"/Plugins/{PLUGIN_ID}/Configuration")
        config_tekst = ruw.decode("utf-8", "replace")
        v.test("JLT-65", "GET /Plugins/{id}/Configuration bevat alleen schakelaars", status == 200 and "Enabled" in config_tekst,
               f"HTTP {status}, {len(ruw)} bytes")
        # Modules weer uit: de routes en het gedrag van die modules zijn weg, de rest is ongewijzigd.
        for slug in ("devices", "quality"):
            _, _, kop = plugin.sessie_vraag(beheer, "GET", "/media/v1/modules")
            plugin.sessie_vraag(beheer, "PUT", f"/media/v1/modules/{slug}", {"enabled": False},
                                {"Idempotency-Key": str(uuid.uuid4()), "If-Match": kop.get("etag", "")})
        plugin.modules_uit("na uitzetten")
        status, discover, _ = plugin.hub_vraag("GET", "/connector/v1/discover", plugin.hub.token())
        over = sorted(t for t in discover.get("limits", {}).get("max_age_s", {}) if t != "health") if status == 200 else ["?"]
        v.test("JLT-64", "modules uit: de connector biedt alleen nog de kern aan", over == ["backups"], f"{over}")
        opnames["b-uit"] = opname(beheer, audio)
        vergelijk_opnames(v, "modules weer uit", opnames["a1-na"], opnames["a2-na"], opnames["b-uit"])
        status, inhoud, _ = plugin.sessie_vraag(beheer, "DELETE", "/media/v1/hub-link", None, {"Idempotency-Key": str(uuid.uuid4())})
        v.test("JLT-68", "pin verwijderen → not_linked", status == 200 and inhoud.get("status") == "not_linked", f"HTTP {status}")
        plugin._laatste = ("GET", "/connector/v1/discover")
        plugin.fout("JLT-68", "na het verwijderen van de pin weigert de connector weer",
                    plugin.hub_vraag("GET", "/connector/v1/discover", plugin.hub.token()), 401, "unauthorized", "not_linked")
        b.stop()
        print("[INFO] run B klaar", flush=True)

        log_rapport = geheimen_scan(v, b, plugin, gemeten.get("zout", b""), config_tekst, stock_log)
        db_rapport = vergelijk_databases(v, werk, runs["a1"], runs["a2"], b)
        vergelijk_bomen(v, runs["a1"], runs["a2"], b)
        corpus_na = corpus(media)
        v.test("JLT-65", "mediacorpus ongewijzigd (sha256, grootte, wijzigingstijd)", corpus_na == corpus_voor and len(corpus_voor) > 0,
               f"{len(corpus_voor)} bestanden, {sum(g for _, g, _ in corpus_voor.values())} bytes")

        # ---- run D: plugin weggehaald (kan alleen als de image hem niet zelf terugzet)
        if args.plugin_map is not None:
            d = Server(f"jl-pp-d-{pid}", stock, werk / "d", media)
            shutil.copytree(b.map, d.map, symlinks=True)
            for map_ in (d.config / "plugins").glob("JellyLeon_*"):
                shutil.rmtree(map_)
            data_voor = pl.boom(d.config / "data" / "jelly-leon")
            servers.append(d)
            d.start()
            beheer_d = Sessie(d, BEHEER, ww[BEHEER], TOESTEL_BEHEER, "jl-proef-beheer")
            status, _, _ = Http(d.url).ruw("GET", "/connector/v1/discover")
            v.test("JLT-64", "plugin verwijderd: de server start en de pluginroutes zijn weg", status == 404,
                   f"GET /connector/v1/discover → HTTP {status}")
            opnames["d"] = opname(beheer_d, audio)
            vergelijk_opnames(v, "plugin verwijderd", opnames["a1-na"], opnames["a2-na"], opnames["d"])
            d.stop()
            v.test("JLT-65", "plugin verwijderd: de plugindata blijft onaangeroerd staan (nooit automatisch wissen)",
                   pl.boom(d.config / "data" / "jelly-leon") == data_voor and len(data_voor) > 0, f"{len(data_voor)} bestanden")
    except (RuntimeError, subprocess.SubprocessError, OSError, KeyError, ValueError) as fout:
        v.test("opzet", "de proef liep vast", False, f"{type(fout).__name__}: {str(fout)[:400]}")
    finally:
        for s in servers:
            docker("rm", "-f", s.naam, check=False)
        shutil.rmtree(werk, ignore_errors=True)
    geslaagd = bool(v.regels) and all(r["geslaagd"] for r in v.regels)
    per_jlt = {j: {"geslaagd": sum(r["geslaagd"] for r in v.regels if r["jlt"] == j), "totaal": sum(1 for r in v.regels if r["jlt"] == j)}
               for j in sorted({r["jlt"] for r in v.regels})}
    if args.rapport:
        args.rapport.parent.mkdir(parents=True, exist_ok=True)
        args.rapport.write_text(json.dumps({
            "schema": "jelly-leon/pluginproef/1", "image": args.image, "stock_image": stock,
            "plugin": "los gebouwde DLL" if args.plugin_map is not None else "meegeleverd in de image",
            "server": {"versie": info.get("Version"), "product": info.get("ProductName")},
            "tijd": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "geslaagd": geslaagd, "per_test": per_jlt,
            "tests": v.regels, "databases": db_rapport, "logs": log_rapport,
            "soort": "Sim-getest (wegwerpcontainers op 127.0.0.1, Hub-simulator; geen echte Hub, NAS of clients)",
        }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RESULTAAT: {'GESLAAGD' if geslaagd else 'MISLUKT'} {per_jlt}")
    return 0 if geslaagd else 1


if __name__ == "__main__":
    sys.exit(main())
