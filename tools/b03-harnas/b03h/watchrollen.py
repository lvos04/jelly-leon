"""Zichtbaarheid in één bekende proefgroep met lokale testrollen. Bewijs bevat uitsluitend aantallen en HTTP-statussen."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

from .jfapi import CLIENT, Http
from .stock import StockServer

ROLLEN = {
    "eigenaar": (True, "CreateAndJoinGroups"),
    "deelnemer": (True, "JoinGroups"),
    "huishouden": (True, "JoinGroups"),
    "gast": (False, "JoinGroups"),
    "kind": (False, "JoinGroups"),
    "zonder_recht": (False, "None"),
}


def tel(antwoord: tuple, groep: str, verwacht_zichtbaar: bool, lijst: bool) -> dict:
    status, body, _ = antwoord
    gevonden = []
    if status == 200:
        data = json.loads(body)
        if not isinstance(data, list if lijst else dict):
            raise ValueError("onverwachte SyncPlay-respons")
        gevonden = [g for g in (data if lijst else [data]) if g["GroupId"] == groep]
    elif status not in (401, 403, 404):
        raise ValueError(f"onverwachte HTTP-status {status} bij de rollenproef")
    namen = {naam for g in gevonden for naam in g["Participants"]}
    return {"http": status, "groepen": len(gevonden), "deelnemersnamen": len(namen),
            "gelekte_groepen": 0 if verwacht_zichtbaar else len(gevonden), "gelekte_namen": 0 if verwacht_zichtbaar else len(namen)}


def rollenproef(server: StockServer, wachtwoord: str) -> dict:
    assert server.jf
    beheer = server.jf
    rollen = {}
    for rol, (_, recht) in ROLLEN.items():
        naam = f"meetrol-{rol}"
        beleid = {"SyncPlayAccess": recht}
        if rol == "kind":
            beleid["MaxParentalRating"] = 10
        uid = beheer.gebruiker(naam, wachtwoord, beleid)
        apparaat = CLIENT.replace('DeviceId="jl-b03016-harnas"', f'DeviceId="meetrol-{rol}"')
        api = Http(server.url, {"Authorization": apparaat})
        auth = api.doe("POST", "/Users/AuthenticateByName", body={"Username": naam, "Pw": wachtwoord})
        api.headers["Authorization"] = apparaat + ', Token="' + auth["AccessToken"] + '"'
        rollen[rol] = (uid, api)
    eigenaar = rollen["eigenaar"][1]
    groep = eigenaar.doe("POST", "/SyncPlay/New", body={"GroupName": "Proefhuishouden"})["GroupId"]
    detail = "/SyncPlay/" + groep
    rollen["deelnemer"][1].doe("POST", "/SyncPlay/Join", body={"GroupId": groep})
    matrix = {}
    for rol, (_, api) in rollen.items():
        zichtbaar = ROLLEN[rol][0]
        matrix[rol] = {"lijst": tel(api.ruw("GET", "/SyncPlay/List"), groep, zichtbaar, True),
                       "detail": tel(api.ruw("GET", detail), groep, zichtbaar, False)}
    for route in ("lijst", "detail"):
        if matrix["eigenaar"][route]["deelnemersnamen"] != 2 or matrix["eigenaar"][route]["groepen"] != 1:
            raise ValueError("positieve controle mist de eigen groep met twee deelnemers")
        if matrix["zonder_recht"][route]["http"] not in (401, 403):
            raise ValueError("negatieve controle: rol zonder SyncPlay-recht niet geweigerd")

    # In de actieve groep een toegangsschema toepassen dat pas over twee dagen opent (testserver in UTC).
    uid, lid = rollen["deelnemer"]
    beleid = beheer.a.doe("GET", f"/Users/{uid}")["Policy"]
    dagen = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dag = dagen[(datetime.now(UTC) + timedelta(days=2)).weekday()]
    beheer.a.doe("POST", f"/Users/{uid}/Policy", body={**beleid, "AccessSchedules": [{"DayOfWeek": dag, "StartHour": 8, "EndHour": 9}]})
    t0 = time.monotonic()
    metingen = []
    while True:
        groepinfo = eigenaar.doe("GET", detail)
        aanwezig = "meetrol-deelnemer" in groepinfo["Participants"]
        metingen.append({"na_s": round(time.monotonic() - t0, 2), "in_groep": aanwezig, "http_lijst": lid.ruw("GET", "/SyncPlay/List")[0]})
        if not aanwezig or time.monotonic() - t0 >= 90:
            break
        time.sleep(2)
    eigenaar.doe("POST", "/SyncPlay/Leave")
    if aanwezig:
        lid.ruw("POST", "/SyncPlay/Leave")
    return {"rollen": matrix, "toegangstijd": metingen}
