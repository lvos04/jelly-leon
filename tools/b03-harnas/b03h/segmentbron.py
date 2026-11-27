"""Lezers van SegmentView en MediaSegments. Alle testsessies gebruiken de synthetische beheerfixture van B03-016."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import uuid
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from ipaddress import ip_address
from pathlib import Path

from .corpus.manifest import sha256_bestand
from .jfapi import Jellyfin
from .segmentmeting import SKIP, Vak, ticks, tijdvak
from .stock import GEBRUIKER, STOCK_IMAGE, WACHTWOORD, WERK, StockServer, docker

IS_VERSIE = "12.0.8.0"
IS_ZIP_SHA = "a898f2e451a5421e02d09efb9c11d7fe3226ea122605260a3c57811ce01963ff"
BIBLIOTHEKEN = [("Meetseries", "tvshows", ["/media/f6/series"]), ("Meetfilms", "movies", ["/media/f6/films"])]
PROFIELEN = ("stock-standaard", "is-standaard", "is-ruim", "jelly-leon")


def zelfde_id(a: str, b: str) -> bool:
    return uuid.UUID(a) == uuid.UUID(b)


def lees_item(jf: Jellyfin, item_id: str, duur: int, *, kandidaat: bool, schaduw: bool = False) -> tuple[list[Vak], list[Vak]]:
    def vak(soort: str, begin: int, eind: int) -> Vak:
        soort = soort.lower()
        if soort not in SKIP:
            raise ValueError("onbekend overslaantype")
        return tijdvak(soort, begin, eind, duur)

    r = jf.a.doe("GET", f"/MediaSegments/{item_id}")
    if not isinstance(r["Items"], list) or len(r["Items"]) != r["TotalRecordCount"]:
        raise ValueError("onvolledig MediaSegments-antwoord")
    gepubliceerd = []
    for s in r["Items"]:
        if not zelfde_id(s["ItemId"], item_id):
            raise ValueError("MediaSegments van een ander item")
        gepubliceerd.append(vak(s["Type"], s["StartTicks"], s["EndTicks"]))
    gepubliceerd.sort()
    if not kandidaat:
        return gepubliceerd, gepubliceerd
    r = jf.a.doe("GET", f"/media/v1/segments/{item_id}", {"view": "candidate"})
    if (not zelfde_id(r["item_id"], item_id) or r["view"] != "candidate" or r["analysis_state"] != "ok"
            or r["publication"] != ("shadow" if schaduw else "published") or not isinstance(r["segments"], list)):
        raise ValueError("kandidaatset onvolledig, uitgeschakeld of in de verkeerde publicatiemodus")
    if abs(ticks(r["duration_s"]) - duur) > ticks(0.1):
        raise ValueError("mediaduur kandidaatantwoord verschilt")
    kandidaten = []
    for s in r["segments"]:
        if s["status"] == "suppressed":
            continue
        soort = "outro" if s["type"] == "credits" else s["type"]
        if soort != s["jellyfin_type"].lower() or s["status"] not in ("published", "review", "shadow"):
            raise ValueError("type of status kandidaat wijkt af")
        kandidaten.append(vak(s["jellyfin_type"], s["start_ticks"], s["end_ticks"]))
    kandidaten.sort()
    if not schaduw and kandidaten != gepubliceerd:
        raise ValueError("kandidaatset verschilt van GET /MediaSegments in publicatiemodus")
    return kandidaten, gepubliceerd


def lees_set(jf: Jellyfin, items: list[dict], kandidaat: bool, schaduw: bool) -> tuple[dict, dict]:
    verwacht = {item["bestand"]: ticks(item["duur_s"]) for item in items}
    kandidaten, gepubliceerd = {}, {}
    for item in jf.items():
        pad = Path(item["Path"]).relative_to("/media/f6").as_posix()
        if pad not in verwacht or pad in kandidaten or abs(item["RunTimeTicks"] - verwacht[pad]) > ticks(0.1):
            raise ValueError("onverwacht, dubbel of afwijkend bestand in de testbibliotheek")
        kandidaten[pad], gepubliceerd[pad] = lees_item(jf, item["Id"], item["RunTimeTicks"], kandidaat=kandidaat, schaduw=schaduw)
    if kandidaten.keys() != verwacht.keys() or not kandidaten:
        raise ValueError("onvolledige testbibliotheek")
    return kandidaten, gepubliceerd


def _is_installeren(server: StockServer, pakket: Path) -> None:
    if sha256_bestand(pakket) != IS_ZIP_SHA:
        raise ValueError("Intro Skipper-pakket wijkt af van de ongewijzigde release")
    doel = server.map / "config" / "plugins" / f"Intro Skipper_{IS_VERSIE}"
    doel.mkdir(parents=True)
    with zipfile.ZipFile(pakket) as archief, archief.open("IntroSkipper.dll") as bron, (doel / "IntroSkipper.dll").open("wb") as dll:
        shutil.copyfileobj(bron, dll)


def _analyse(jf: Jellyfin, profiel: str) -> dict:
    plugin = next((p for p in jf.a.doe("GET", "/Plugins") if p["Name"] == "Intro Skipper"), None)
    if not plugin or plugin["Status"] != "Active" or plugin["Version"] != IS_VERSIE:
        raise ValueError("S-IS geblokkeerd: de vastgezette Intro Skipper-versie is niet actief")
    pad = f"/Plugins/{plugin['Id']}/Configuration"
    config = jf.a.doe("GET", pad)
    venster = (50, 20) if profiel == "is-ruim" else (25, 10)
    if profiel == "is-ruim":
        jf.a.doe("POST", pad, body={**config, "AnalysisPercent": venster[0], "AnalysisLengthLimit": venster[1]})
    actueel = jf.a.doe("GET", pad)
    if (actueel["AnalysisPercent"], actueel["AnalysisLengthLimit"]) != venster:
        raise ValueError("verkeerd Intro Skipper-venster")
    taak = next(t for t in jf.a.doe("GET", "/ScheduledTasks") if t["Key"] == "IntroSkipperDetectSegmentsTask")
    vorig = taak.get("LastExecutionResult")
    taakpad = f"/ScheduledTasks/{taak['Id']}"
    jf.a.doe("POST", f"/ScheduledTasks/Running/{taak['Id']}")
    einde = time.monotonic() + 3600
    while time.monotonic() < einde:
        taak = jf.a.doe("GET", taakpad)
        resultaat = taak.get("LastExecutionResult")
        if taak["State"] == "Idle" and resultaat and resultaat != vorig:
            if resultaat["Status"] != "Completed":
                raise ValueError("Intro Skipper kon de detectie niet voltooien")
            return {"versie": IS_VERSIE, "pakket_sha256": IS_ZIP_SHA, "venster_procent": venster[0], "venster_minuten": venster[1]}
        time.sleep(2)
    raise TimeoutError("geen nieuwe voltooide Intro Skipper-analyse")


@contextmanager
def stock_sessie(profiel: str, corpus: Path, pakket: Path | None) -> Iterator[tuple[Jellyfin, str, dict]]:
    WERK.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=WERK) as werk:
        koppelingen = {"/media/f6/" + deel: deel for deel in ("series", "films") if (corpus / deel).is_dir()}
        with StockServer("jlt50", werk=Path(werk), corpus=corpus, koppelingen=koppelingen, gpu=False, cpus="2") as server:
            if profiel in ("is-standaard", "is-ruim"):
                if pakket is None:
                    raise ValueError("Intro Skipper-pakket ontbreekt")
                _is_installeren(server, pakket)
            server.start(schoon=False)
            server.inrichten(BIBLIOTHEKEN)
            assert server.jf
            info = {"image": STOCK_IMAGE, "image_id": server.digest()}
            if pakket and profiel in ("is-standaard", "is-ruim"):
                info["intro_skipper"] = _analyse(server.jf, profiel)
            yield server.jf, server.container_id, info


def lokale_jelly(container: str, setmap: Path) -> tuple[Jellyfin, str, dict]:
    """Accepteer alleen een expliciet gemarkeerde lokale proefcontainer op de stock-basis met de bevroren set alleen-lezen."""
    def inspecteer(veld: str):
        return json.loads(docker("inspect", "--type", "container", "--format", "{{json " + veld + "}}", "--", container).stdout)
    if inspecteer(".Config.Labels").get("org.jelly-leon.proef") != "jlt50":
        raise ValueError("proefcontainer mist label org.jelly-leon.proef=jlt50")
    mounts = {m["Destination"]: m for m in inspecteer(".Mounts") if m["Destination"].startswith("/media")}
    for deel in ("series", "films"):
        mount = mounts.pop(f"/media/f6/{deel}", {})
        if not mount or mount["RW"] or Path(mount["Source"]).resolve() != (setmap / deel).resolve():
            raise ValueError("verkeerde of schrijfbare koppeling van de testset")
    if mounts:
        raise ValueError("onverwachte mediamount in de proefcontainer")
    poorten = inspecteer(".NetworkSettings.Ports").get("8096/tcp") or []
    if len(poorten) != 1 or not ip_address(poorten[0]["HostIp"]).is_loopback:
        raise ValueError("testpoort is niet uitsluitend lokaal gepubliceerd")
    image_id = inspecteer(".Image")
    def lagen(ref: str) -> list[str]:
        return json.loads(docker("image", "inspect", "--format", "{{json .RootFS.Layers}}", ref).stdout)
    basis = lagen(STOCK_IMAGE)
    if not basis or lagen(image_id)[:len(basis)] != basis:
        raise ValueError("Jelly Leon draait niet op de vastgezette stockbasis")
    jf = Jellyfin(f"http://localhost:{int(poorten[0]['HostPort'])}")
    jf.login(GEBRUIKER, WACHTWOORD)
    return jf, inspecteer(".Id"), {"image_id": image_id, "basis": STOCK_IMAGE}
