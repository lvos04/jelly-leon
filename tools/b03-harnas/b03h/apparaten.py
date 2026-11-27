"""B03-060 en het webdeel van JLT-40, met het meetslot en de wegwerpservers van de stockbaseline."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import uuid
from contextlib import ExitStack
from itertools import batched, groupby
from pathlib import Path

from . import apparaatrapport as rapport
from . import apparaatset, baseline, bewijs, meetslot
from .corpus import CORPUS, UITVOER
from .corpus.manifest import sha256_bestand
from .stock import BIBLIOTHEKEN, KOPPELINGEN, STOCK_IMAGE, WERK, StockServer
from .web import UA, WebFout

CLIENTS = ("chromium", "firefox", "webkit", "webos", "tizen")
SYSTEMEN = ("stock-standaard", "stock-best")
UITGESTELD = "NIET GEMETEN (machinelast)"
BASIS = baseline.EVIDENCE_MAP / "b03-016-baseline-definitief-forkbasis.json"


class ApparaatFout(WebFout):
    """Een onvolledige meting met een bericht dat uitsluitend bevroren gevalnamen bevat."""


def basisprobleem(pad: Path) -> str | None:
    if not pad.is_file():
        return "De definitieve baseline van S-P40-50 ontbreekt."
    try:
        d = json.loads(pad.read_text())
    except (OSError, ValueError):
        return "Het bewijsbestand van S-P40-50 is onleesbaar."
    if not isinstance(d, dict) or not isinstance(d.get("images"), dict) or not isinstance(d.get("metingen"), list):
        return "De definitieve baseline van S-P40-50 is onvolledig."
    if d.get("label") != "definitief-forkbasis" or d["images"].get("stock") != STOCK_IMAGE:
        return "S-P40-50 ontbreekt voor de vastgezette forkbasis-digest."
    if bewijs.controleer(d) or d.get("fasefouten"):
        return "De definitieve baseline van S-P40-50 is onvolledig."
    verwacht = {(s, f"F5-{meting}-{b}") for s in SYSTEMEN for b in rapport.VERWACHT for meting in ("B1-dp-beslissing", "K3-dp-effectief")}
    geldig = {(m["systeem"], m["id"]) for m in d["metingen"] if m["image"] == STOCK_IMAGE and m["n"] == 25 and
              len({r["last"]["run"] for r in m["runs"] if r["last"]["geldig"]}) >= 3}
    if verwacht - geldig:
        return "Drie geldige dp- en orakelruns per stockprofiel en browser ontbreken in S-P40-50."
    return None


def devices_aan(sessie: baseline.Sessie) -> None:
    api = sessie.jf.a
    status, _, kop = api.ruw("GET", "/media/v1/modules")
    etag = {k.lower(): v for k, v in kop.items()}.get("etag")
    if status != 200 or not etag:
        raise ValueError("de lokale fork mist het moduleregister of de ETag")
    api.doe("PUT", "/media/v1/modules/devices", body={"enabled": True},
            headers={"If-Match": etag, "Idempotency-Key": str(uuid.uuid4())})
    standen = api.doe("GET", "/media/v1/modules")["items"]
    if not any(m["slug"] == "devices" and m["enabled"] is True for m in standen):
        raise ValueError("de module Devices is niet ingeschakeld op de testserver")


def lees_start(geval: dict, groep: str, i: dict) -> dict:
    if i.get("fout") or not i.get("besluit_gemeten") or not isinstance(i.get("geforceerd_ok"), bool):
        raise ApparaatFout(f"{geval['id']}: afspeelactie, PlaybackInfo of statische proef ontbreekt")
    duur = (i.get("laatste") or {}).get("t", 0)
    if i["besluit"] == "DirectPlay" and not i["orakel_ok"] and i["herstel_ms"] is None and duur < 60000:
        raise ApparaatFout(f"{geval['id']}: de observatie van automatisch herstel eindigde vóór de grens van 60 s")
    if geval.get("middel") and not i.get("foutmiddel_actief"):
        raise ApparaatFout(f"{geval['id']}: het bevroren foutmiddel was niet actief in de browser")
    if groep in ("ass", "srt") and not i["ondertitel"]:
        raise ApparaatFout(f"{geval['id']}: geen geselecteerd ondertitelspoor voor K7")
    # Alleen bewezen geschiktheid telt mee. De headless test heeft geen bevestigde HDR-uitvoer of client-tonemapper.
    return {"id": geval["id"], "groep": groep, "classificatie": (
                "onterechte Direct Play" if i["besluit"] == "DirectPlay" and not i["orakel_ok"] else i["besluit"]),
            "waargenomen_ms": round(duur), "hdr_toegestaan": i["videobereik"] == "SDR", "foutcodes": [e["err"] for e in i["fouten"]],
            **{k: i[k] for k in ("start", "besluit", "orakel_ok", "geforceerd_ok", "herstel_ms", "eerste_frame_ms", "tijd_tot_2s_ms",
                                 "redenen", "hls", "transcoding_info", "cpu_kernen", "ingebrand", "ondertitel", "extern_mogelijk",
                                 "videobereik", "audio_niet_stil", "foutmiddel_actief")}}


def meet_client(sessie: baseline.Sessie, client: str, groepen: dict, f5: Path, splits: set[str]) -> dict:
    rijen = []
    versies = set()
    standaard = sessie.jf.a.doe("GET", "/Users/Me")["Configuration"]
    try:
        for groep, plan in groepen.items():
            if groep in ("devset", "testset") and groep not in splits:
                continue
            ondertitel = groep in ("ass", "srt")
            config = {**standaard, "SubtitleLanguagePreference": "dut", "SubtitleMode": "Always"} if ondertitel else standaard
            sessie.jf.a.doe("POST", "/Users/Configuration", body=config)
            gevallen = [c for c in plan["gevallen"] if c.get("client", client) == client]
            for middel, deel in groupby(gevallen, key=lambda c: c.get("middel")):
                opties = {"containerId": sessie.s.container_id}
                if client in UA:
                    opties["ua"] = UA[client]
                if middel:
                    opties["initScript"] = str(f5 / middel)
                for batch in batched(deel, 4):
                    paden = [c["pad"] for c in batch]
                    if set(paden) - sessie.items.keys():
                        raise ValueError(f"{client}/{groep}: bevroren item ontbreekt in de bibliotheek")
                    try:
                        web = sessie.web("chromium" if client in UA else client, paden, "apparaten", **opties)
                    except WebFout as exc:
                        raise ApparaatFout(f"{client}/{groep}: browserharnas kon de afspeelproef niet uitvoeren") from exc
                    versies.add(web["versie"])
                    verwacht = [(sessie.items[c["pad"]]["Id"], start) for c in batch for start in (1, 2)]
                    if [(i["id"], i["start"]) for i in web["items"]] != verwacht:
                        raise ApparaatFout(f"{client}/{groep}: onvolledige of verwisselde starts")
                    for c, paar in zip(batch, batched(web["items"], 2), strict=True):
                        rijen.extend(lees_start(c, groep, i) for i in paar)
    finally:
        sessie.jf.a.doe("POST", "/Users/Configuration", body=standaard)
    if len(versies) != 1:
        raise ApparaatFout(f"{client}: geen eenduidige browserversie")
    metingen = {}
    for groep, deel in groupby(rijen, key=lambda r: r["groep"]):
        beide = list(deel)
        metingen[groep] = {start: rapport.metrieken([r for r in beide if r["start"] == start]) for start in (1, 2)}
    return {"browser_versie": versies.pop(), "rijen": rijen, "metingen": metingen}


def meet(d: dict, sets: Path, fork: str | None, runs: int, splits: set[str], uit: Path) -> bool:
    plan = apparaatset.controleer(sets, CORPUS)
    d["sets_sha256"] = {g: p["sha256"] for g, p in plan["groepen"].items()}
    historisch = json.loads((baseline.EVIDENCE_MAP / "b03-016-baseline-voormeting-12.4/dp-matrix.json").read_text())
    WERK.mkdir(parents=True, exist_ok=True)
    metingen_ok = True
    with ExitStack() as context:
        d["slot_wacht_s"] = context.enter_context(meetslot.exclusief_slot(bij_wachten=baseline.log))
        werk = Path(context.enter_context(tempfile.TemporaryDirectory(dir=WERK)))
        sessies = {}
        mounts = {**KOPPELINGEN, apparaatset.ASS_MAP: str(apparaatset.setmap(sets, "ass").resolve())}
        bibliotheken = [*BIBLIOTHEKEN, ("Apparaatproeven", "movies", [apparaatset.ASS_MAP])]
        images = {"stock": STOCK_IMAGE}
        if fork:
            images["jelly-leon"] = fork
        for naam, image in images.items():
            server = context.enter_context(StockServer(naam, image=image, werk=werk, koppelingen=mounts, gpu_verplicht=True, cpus="4"))
            # Elke sessie heeft een nieuwe tijdelijke werkmap. De fork controleert de rechten op beide volumes.
            for sub in ("config", "cache"):
                (server.map / sub).mkdir(mode=0o700, parents=True)
            server.start(schoon=False)
            server.inrichten(bibliotheken)
            sessies[naam] = baseline.Sessie(server)
            d["images"][naam] = {"referentie": image, "image_id": server.digest(), "serverversie": server.info["Version"]}
        if fork:
            devices_aan(sessies["jelly-leon"])
        f5 = apparaatset.setmap(sets, "f5-fouten")
        for r, systeem in meetslot.ab_volgorde(list(d["systemen"]), runs):
            sessie = sessies["jelly-leon" if systeem == "jelly-leon" else "stock"]
            sessie.systeem(systeem)
            for client, data in d["systemen"][systeem].items():
                last, run, ongeldig = baseline.geldige_run(
                    systeem, r, [s.s.container_id for s in sessies.values()],
                    lambda client=client, sessie=sessie: meet_client(sessie, client, plan["groepen"], f5, splits))
                data["runs"].append({**run, "last": last.als_dict(), "ongeldige_pogingen": ongeldig,
                                     "encoding_sha256": sessie.config_hash[systeem]})
                if r == 0 and systeem == "stock-standaard" and client in rapport.VERWACHT:
                    data["a5"] = rapport.vergelijking(run["rijen"], client, historisch["stock-standaard#0"]["zoals_webclient"][client])
                    metingen_ok &= not data["a5"]["verschillen_ter_beoordeling"]
                if r + 1 == runs:
                    data["herhaalbaarheid"] = rapport.herhaalbaarheid(data["runs"])
                    metingen_ok &= data["herhaalbaarheid"]["geldig"]
                rapport.schrijf(uit, d)
    negatief = sorted({r["id"] for data in d["systemen"]["stock-standaard"].values() for run in data["runs"]
                       for r in run["rijen"] if r["groep"] in splits and r["start"] == 1 and r["foutmiddel_actief"]
                       and r["classificatie"] == "onterechte Direct Play"})
    d["negatieve_controle"] = {"onterechte_direct_plays_eerste_start": negatief}
    if not negatief:
        d["redenen"].append("Geen eerste Direct Play met een actief liegend codecprofiel is door het orakel afgekeurd.")
    return metingen_ok and bool(negatief)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h apparaten")
    p.add_argument("--basis", type=Path, default=BASIS, help="definitief S-P40-50-bewijs op de vastgezette forkbasis")
    p.add_argument("--sets", type=Path, default=UITVOER, help="uitvoermap van de recepten f5-fouten en ass")
    p.add_argument("--split", choices=("devset", "testset", "beide"), default="beide")
    p.add_argument("--fork-image", help="meet in dezelfde sessie ook de lokale fork met Devices ingeschakeld")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--uit", type=Path, required=True, help="JSON met een Markdown-rapport ernaast")
    a = p.parse_args(argv)
    if a.runs < 3 or a.uit.suffix != ".json" or meetslot.LASTGRENS > 4:
        p.error("minstens drie runs, een .json-uitvoer en een lastgrens van hoogstens 4 zijn vereist")
    volgorde = ["stock-standaard", "jelly-leon", "stock-best"] if a.fork_image else SYSTEMEN
    last = meetslot.loadavg()
    d = {"schema": "b03-060/apparaten/1", "begin": meetslot.nu(), "status": "Meetpoging",
         "basis": a.basis.name, "runs_gevraagd": a.runs, "split": a.split, "meetsets": apparaatset.BEWIJS.name,
         "loadavg": [round(x, 2) for x in last], "grens": meetslot.LASTGRENS,
         "systemen": {s: {c: {"rol": ("tv-UA in Chromium" if c in UA else "webclient") + (" op fork" if s == "jelly-leon" else " op stock"),
                               "runs": []} for c in CLIENTS} for s in volgorde},
         "audio_niet_stil": "niet gemeten", "overgenomen_clientproeven": rapport.EXTERN, "images": {}, "redenen": []}
    if a.uit.resolve() == a.basis.resolve():
        p.error("kies voor de uitvoer een ander bestand dan de S-P40-50-baseline")
    vast = json.loads(apparaatset.BEWIJS.read_text())
    d["sets_sha256"] = {g: p["sha256"] for g, p in vast["groepen"].items()}
    probleem = basisprobleem(a.basis)
    if probleem:
        d["redenen"].append(probleem)
    if last[0] > meetslot.LASTGRENS:
        d["redenen"].append("De éénminuutslast overschrijdt de meetgrens.")
    code = 1
    if d["redenen"]:
        d["status"] = UITGESTELD
        for clients in d["systemen"].values():
            for data in clients.values():
                data["metingen"] = dict.fromkeys(rapport.OMSCHRIJVING)
    else:
        d["basis_sha256"] = sha256_bestand(a.basis)
        splits = {"testset", "devset"} if a.split == "beide" else {a.split}
        try:
            geldig = meet(d, a.sets, a.fork_image, a.runs, splits, a.uit)
            d["status"] = "Sim-getest" if geldig else "Afwijking in de matrix, herhaalbaarheid of negatieve controle"
            code = 0 if geldig else 1
        except baseline.GeenGeldigeRun as exc:
            d.update(status=UITGESTELD, ongeldige_pogingen=exc.pogingen)
            d["redenen"].append(str(exc))
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            d["status"] = "Meetproef afgebroken"
            # Ruwe HTTP- en procesfouten kunnen sessiegegevens bevatten. Alleen eigen, gecontroleerde meldingen publiceren.
            d["redenen"].append(str(exc) if type(exc) in (ValueError, ApparaatFout) else
                                f"{type(exc).__name__} tijdens de lokale meetproef")
    d["eind"] = meetslot.nu()
    rapport.schrijf(a.uit, d)
    print(d["status"])
    return code
