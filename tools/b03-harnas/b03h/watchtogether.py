"""B03-020: voormeting met twee stock-clients in één SyncPlay-groep."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import secrets
import subprocess
import sys
import tempfile
from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from pathlib import Path

from . import bewijs, meetslot, watchmeting, watchomgeving, web
from .baseline import _lees_transcodelog
from .corpus import CORPUS, UITVOER, manifest
from .corpus.ffmpeg import Ffmpeg
from .corpus.generator import BEVROREN, RECEPTEN, setnaam
from .desktop import CLIENTBUILD, DESKTOP_IMAGE
from .jfapi import HttpFout
from .stock import STOCK_IMAGE, WERK, StockServer, profiel
from .watchrollen import rollenproef

BEWIJSMAP = BEVROREN.parent
FRAME = BEVROREN / "f1-framecode.v1.vol.manifest.json"
SCENARIOS = {
    "S1": ("hero", "chromium", "firefox"),
    "S2": ("hevc", "firefox", "chromium"),
    "S3": ("hero", "chromium", "firefox"),
    "S4": ("framecode", "chromium", "desktop"),
    "S5": ("sintel", "firefox", "chromium"),
}
BRONNEN = {"hero": "bron/blender/hero/hero.mp4", "hevc": "bron/jellyfin-testvideos/Test_Jellyfin_1080p_HEVC_10bit_10M.mp4",
           "sintel": "bron/blender/sintel/Sintel.2010.1080p.mkv"}
UITGESTELD = "NIET GEMETEN (machinelast)"
OPEN_CLIENTS = {"android-web": "geen groepsrun in S1–S5", "androidtv": "geen SyncPlay-client in deze stockmatrix",
                "Swiftfin": "NIET GEVALIDEERD (Mac/Xcode)", "echte tv": "NIET GEVALIDEERD (hardware)"}


def bewaar(pad: Path, data: dict) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=pad.parent, encoding="utf-8", delete=False) as f:
        try:
            json.dump(data, f, ensure_ascii=False, allow_nan=False, indent=2)
            f.write("\n")
        except BaseException:
            Path(f.name).unlink(missing_ok=True)
            raise
    Path(f.name).replace(pad)


def controle_baseline(pad: Path) -> bool:
    if not pad.exists():
        return False
    d = json.loads(pad.read_text(encoding="utf-8"))
    if (not isinstance(d, dict) or not isinstance(d.get("images"), dict) or not isinstance(d.get("metingen"), list)
            or bewijs.controleer(d) or d["label"] != "definitief-forkbasis" or d["images"].get("stock") != STOCK_IMAGE
            or d.get("fasefouten") or not d.get("metingen")):
        raise ValueError("S-P40-50 leverde geen geldige definitieve stockbaseline op de forkdigest")
    for systeem in watchmeting.SYSTEMEN:
        metingen = [m for m in d["metingen"] if m["systeem"] == systeem]
        if not metingen or any(m["image"] != STOCK_IMAGE or m["n"] <= 0 or len({r["last"].get("run") for r in m["runs"]}) < 3 or
                               not all(r["last"]["geldig"] is True for r in m["runs"]) for m in metingen):
            raise ValueError(f"onvolledige of ongeldige S-P40-50-runs voor {systeem}")
    return True


def bronmedia(werk: Path, frame_set: Path) -> tuple[dict, dict, float]:
    bevroren = json.loads(FRAME.read_text(encoding="utf-8"))
    if manifest.controleer(frame_set, bevroren):
        raise ValueError("framecodeset komt niet overeen met het bevroren manifest")
    bron = {sleutel: CORPUS / rel for sleutel, rel in BRONNEN.items()}
    bron["framecode"] = frame_set / "sync/hero-framecode.mkv"
    ff = Ffmpeg("docker", alleen_lezen=[CORPUS, frame_set], schrijfbaar=[werk], cpus=1)
    koppelingen, herkomst = {}, {}
    frameperiode = 0.0
    for sleutel, pad in bron.items():
        duur = float(ff.ffprobe(pad)["format"]["duration"])
        if sleutel == "framecode":
            frameperiode = duur * 1000
        doel = pad
        if duur < 370:
            # Geen herstart van de groep tijdens het vijfminutenvenster, ook niet bij de korte HEVC-testclip.
            doel = werk / (sleutel + pad.suffix)
            ff.ffmpeg(["-stream_loop", "-1", "-i", str(pad), "-t", "370", "-map", "0:v:0", "-map", "0:a?",
                       "-c", "copy", "-fflags", "+bitexact", "-map_metadata", "-1", str(doel)])
        koppelingen[f"/media/movies/{sleutel}/{sleutel}{pad.suffix}"] = str(doel)
        herkomst[sleutel] = {"bron_sha256": manifest.sha256_bestand(pad), "afspeelbestand_sha256": manifest.sha256_bestand(doel),
                             "bronduur_s": duur, "verlengd_met_streamcopy": doel != pad}
    return koppelingen, herkomst, frameperiode


@contextmanager
def meetvenster():
    """Sluit ook de andere gedeelde testsloten uit. Een door stackslot geërfd fd 9 houden we zelf open."""
    with ExitStack() as stapel:
        for naam in (meetslot.STACK_LOCK, "stack2.lock", "stack3.lock", *meetslot.ZWARE_SLOTEN):
            pad = meetslot.LOCK_DIR / naam
            if naam != meetslot.STACK_LOCK and not pad.exists():
                continue
            try:
                geerfd = os.path.samestat(os.fstat(9), pad.stat())
            except OSError:
                geerfd = False
            if geerfd and os.environ.get("STACKSLOT"):
                continue
            # Zware bouwsloten worden door meetslot.run gecontroleerd. De emulator neemt gradle.lock zelf.
            if naam in meetslot.ZWARE_SLOTEN:
                if meetslot.slot_bezet(pad):
                    yield naam
                    return
                continue
            f = stapel.enter_context(pad.open("rb") if pad.exists() else pad.open("a+b"))
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as fout:
                if fout.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                yield naam
                return
        yield None


def maak_kijkers(server: StockServer, wachtwoord: str, prefix: str) -> list[str]:
    assert server.jf
    namen = [prefix + "-a", prefix + "-b"]
    for naam in namen:
        server.jf.gebruiker(naam, wachtwoord, {"SyncPlayAccess": "CreateAndJoinGroups"})
    return namen


def startcontrole(pad: Path) -> dict:
    last = list(meetslot.loadavg())
    baseline = controle_baseline(pad)
    return {"datum": meetslot.nu(), "loadavg": last, "lastgrens": min(4.0, meetslot.LASTGRENS),
            "baseline_s_p40_50": "aanwezig" if baseline else "ontbreekt",
            "meten": baseline and last[0] <= min(4.0, meetslot.LASTGRENS)}


def meet_run(systeem: str, nr: int, containers: list[str], actie: Callable, grens: float) -> tuple[dict, dict | None]:
    spoor = None
    bezet = None
    with meetslot.run(systeem, nr, containers, grens=grens) as last, ExitStack() as sloten:
        if last.loadavg_voor[0] <= grens and not last.zware_sloten_voor:
            # Geen bouwstart tussen twee lastpeilingen. Vóór de eindpeiling zijn de eigen sloten weer vrij.
            for naam in meetslot.ZWARE_SLOTEN:
                pad = meetslot.LOCK_DIR / naam
                f = sloten.enter_context(pad.open("rb") if pad.exists() else pad.open("a+b"))
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    bezet = naam
                    break
            if bezet is None:
                spoor = actie()
    if bezet:
        last.geldig = False
        last.reden = f"ander zwaar slot actief: {bezet}"
    if last.loadavg_na[0] > grens:
        last.geldig = False
        last.reden = (last.reden + " " if last.reden else "") + "loadavg na de run boven de grens"
    return last.als_dict(), spoor


def vereis_afspeelpad(scenario: str, sessies: list, nieuwe_logs: list[Path]) -> None:
    if len(sessies) != 2:
        raise ValueError("twee actieve deelnemers vereist")
    if scenario == "S1" and any(s["methode"] != "DirectPlay" for s in sessies):
        raise ValueError("S1 vereiste twee Direct Play-sessies")
    if scenario == "S2" and (not sessies[1]["video_transcode"] or sessies[0]["video_transcode"] or
                             not any(_lees_transcodelog(p)["video_encoder"].endswith("_qsv") for p in nieuwe_logs)):
        raise ValueError("S2 mist bewijs voor precies één QSV-videotranscode bij Chromium")


def meet(a: argparse.Namespace, document: dict, logmap: Path, poging: Path) -> int:
    grens = document["startcontrole"]["lastgrens"]
    WERK.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stapel:
        werk = Path(stapel.enter_context(tempfile.TemporaryDirectory(dir=WERK))).resolve()
        mounts, document["media"], frameperiode = bronmedia(werk, a.framecode_set.resolve())
        server = StockServer("watchtogether", image=STOCK_IMAGE, werk=werk, koppelingen=mounts, gpu_verplicht=True)
        stapel.callback(server.verwijder)
        server.start()
        server.inrichten([("Meetfilms", "movies", ["/media/movies"])])
        assert server.jf
        jf = server.jf
        document["server"] = {"versie": server.info["Version"], "image_id": server.digest()}
        encoding = profiel("stock-best")["encoding"]
        gemeten = jf.zet_encoding(encoding)
        if any(gemeten.get(k) != v for k, v in encoding.items()):
            raise ValueError("de handmatige QSV-instellingen zijn niet bevestigd")
        document["encoding"] = encoding
        document["stock_best_client"] = profiel("stock-best")["client"]["syncplay_correctie"]["localStorage"]
        items = {Path(i["Path"]).stem: i["Id"] for i in jf.items()}
        if set(items) != {"hero", "sintel", "framecode", "hevc"}:
            raise ValueError("scan mist een van de vier meetfilms")
        net = stapel.enter_context(watchomgeving.netwerk(server))
        wachtwoord = secrets.token_urlsafe(24)
        namen = maak_kijkers(server, wachtwoord, "meetklok")
        cfg = {"url": server.url, "namen": namen, "wachtwoord": wachtwoord, "beheer": jf.a.headers["Authorization"],
               "framePeriodeMs": frameperiode}
        scenario_status = document["scenarios"]
        desktopbewijs = json.loads((BEWIJSMAP / "b03-016-desktop-spike.json").read_text(encoding="utf-8"))
        heeft_desktop = desktopbewijs.get("status") == "Sim-getest"
        if not heeft_desktop:
            scenario_status["S4"] = {"status": "Geblokkeerd", "reden": "desktoprooktest S-P40-90 ontbreekt"}
        # Een nieuw desktopvenster per proef houdt aanmelding, hervatpunt en profiel gescheiden.
        with ExitStack() as kalibratie:
            cdp = kalibratie.enter_context(watchomgeving.desktop(server, net, a.desktopbouw, a.desktop_image, werk)) if heeft_desktop else {}

            def kalibreer():
                uit = {}
                for browser in ("chromium", "firefox"):
                    r = web.harnas("watchklok", {**cfg, **(cdp if browser == "chromium" else {}), "browser": browser, "item": items["hero"]},
                                   pogingen=1)
                    uit[browser] = {naam: watchmeting.nulproef(rij) for naam, rij in r.items()}
                return uit

            containers = [server.container_id] + ([cdp["cid"]] if cdp else [])
            last, kalibraties = meet_run("stock-standaard", 0, containers, kalibreer, grens)
        document["kalibratie_last"] = last
        if not last["geldig"]:
            document["status"] = UITGESTELD
            bewaar(poging, document)
            return 3
        assert kalibraties
        document["kalibratie"] = kalibraties
        for reeks in kalibraties.values():
            for methode, proef in reeks.items():
                proef["bruikbaar_voor_M1"] = proef["max_ms"] <= (20 if methode == "currentTime" else 100)
        if any(r["currentTime"]["max_ms"] > 20 for r in kalibraties.values()):
            raise ValueError("meetonzekerheid currentTime boven de S1-marge van 20 ms")
        if heeft_desktop and kalibraties["chromium"]["Xvfb"]["max_ms"] > 100:
            raise ValueError("Xvfb-onzekerheid boven 100 ms, S4-drift niet aantoonbaar")
        adb = watchomgeving.adb_nulproef(werk)
        adb["bruikbaar_voor_M1"] = "max_ms" in adb and adb["max_ms"] <= 100
        document["kalibratie"]["adb exec-out screencap"] = adb
        document["rollenproef"] = rollenproef(server, wachtwoord)
        # De doorvoer geldt uitsluitend voor de tweede deelnemer van S3.
        url_b, scenario_status["S3"] = stapel.enter_context(watchomgeving.netem(server, net))
        for scenario, (film, eerste, tweede) in SCENARIOS.items():
            if (scenario == "S3" and not url_b) or (scenario == "S4" and not heeft_desktop):
                continue
            per_systeem = {s: [] for s in watchmeting.SYSTEMEN}
            for nr, systeem in meetslot.ab_volgorde(watchmeting.SYSTEMEN, a.runs):
                bestand = f"{scenario}-{systeem}-{nr + 1}.json"
                run_cfg = {**cfg, "browser": eerste, "tweede": tweede, "item": items[film], "scenario": scenario, "systeem": systeem}
                if systeem == "stock-best":
                    run_cfg["instellingen"] = document["stock_best_client"]
                if scenario == "S3":
                    run_cfg["urlB"] = url_b
                run_cfg["namen"] = maak_kijkers(server, wachtwoord, f"meet-{scenario.lower()}-{systeem}-{nr}")
                voor_logs = set(server.transcodelogs())
                with ExitStack() as klienten:
                    containers = [server.container_id]
                    if scenario == "S4":
                        cdp = klienten.enter_context(watchomgeving.desktop(server, net, a.desktopbouw, a.desktop_image, werk))
                        run_cfg.update(cdp)
                        containers.append(cdp["cid"])
                    last, spoor = meet_run(systeem, nr, containers,
                                           lambda run_cfg=run_cfg: web.harnas("watchtogether", run_cfg, timeout=540, pogingen=1), grens)
                record = {"last": last, "log": logmap.name + "/" + bestand}
                bewaar(logmap / bestand, {"last": last, "spoor": spoor})
                per_systeem[systeem].append(record)
                if not last["geldig"]:
                    document.update(status=UITGESTELD, afgewezen_run=record)
                    bewaar(poging, document)
                    return 3
                assert spoor
                vereis_afspeelpad(scenario, spoor["sessies"], list(set(server.transcodelogs()) - voor_logs))
                record["uitkomst"] = watchmeting.beoordeel_spoor(spoor, scenario)
                record["sessies"] = spoor["sessies"]
                record["regressies"] = spoor["regressies"]
                document["clientdekking"][eerste] = document["clientdekking"][tweede] = "groepsrun waargenomen"
            for systeem, runs in per_systeem.items():
                document["metingen"] += watchmeting.metrieken(scenario, systeem, STOCK_IMAGE, runs)
            scenario_status[scenario] = {**scenario_status.get(scenario, {}), "status": "Sim-getest", "runs_per_stockprofiel": a.runs}
        document.update(schema=bewijs.SCHEMA, status="Sim-getest", eind=meetslot.nu())
        bewijs.schrijf(a.uit, document)
        return 0


def functieproef(a: argparse.Namespace) -> int:
    """Functionele stockproef zonder prestatiewaarden. Een afwijking blijft zichtbaar in het regressierapport."""
    doc = {"schema": "jelly-leon/b03-020-functieproef/1", "image": STOCK_IMAGE, "begin": meetslot.nu()}
    WERK.mkdir(parents=True, exist_ok=True)
    with meetslot.exclusief_slot(), ExitStack() as stapel:
        werk = Path(stapel.enter_context(tempfile.TemporaryDirectory(dir=WERK))).resolve()
        meerdere_sporen = "afgeleid/formaten/tos-multiaudio-5.1-me-subs.mkv"
        mounts = {"/media/movies/Hero/Hero.mp4": BRONNEN["hero"], "/media/movies/Sintel/Sintel.mkv": BRONNEN["sintel"],
                  "/media/movies/Versieproef/Versieproef - Basis.mp4": BRONNEN["hero"],
                  "/media/movies/Versieproef/Versieproef - Multispoor.mkv": meerdere_sporen}
        server = StockServer("watchfunctie", werk=werk, koppelingen=mounts, gpu=False, cpus="2")
        stapel.callback(server.verwijder)
        server.start()
        server.inrichten([("Meetfilms", "movies", ["/media/movies"])])
        assert server.jf
        jf = server.jf
        doc["server"] = {"versie": server.info["Version"], "image_id": server.digest()}
        wachtwoord = secrets.token_urlsafe(24)
        doc["zichtbaarheid"] = rollenproef(server, wachtwoord)
        bewaar(a.uit, doc)
        with watchomgeving.netwerk(server) as net, watchomgeving.netem(server, net) as (_, netproef):
            doc["tc_proef"] = netproef
        bewaar(a.uit, doc)
        items = jf.items()
        hero = next(i for i in items if i["Path"].endswith("/Hero/Hero.mp4"))
        sintel = next(i for i in items if i["Path"].endswith("/Sintel/Sintel.mkv"))
        versie = next((i for i in items if len(i.get("MediaSources", [])) > 1 and "/Versieproef/" in i["Path"]), {})
        namen = maak_kijkers(server, wachtwoord, "meetkijker")
        cfg = {"url": server.url, "namen": namen, "wachtwoord": wachtwoord, "beheer": jf.a.headers["Authorization"],
               "browser": "firefox", "tweede": "chromium", "item": hero["Id"], "volgende": sintel["Id"],
               "duurTicks": hero["RunTimeTicks"], "versieItem": versie.get("Id"), "systeem": "stock-standaard"}
        doc["regressies"] = web.harnas("watchfunctie", cfg, pogingen=1, timeout=300)
        doc["eind"] = meetslot.nu()
        bewaar(a.uit, doc)
        afwijkingen = [k for k, r in doc["regressies"].items() if r.get("ok") is False]
        print("Stockafwijkingen: " + ", ".join(afwijkingen) if afwijkingen else "Functionele proef uitgevoerd")
        return int(bool(afwijkingen))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h watchtogether")
    p.add_argument("--functieproef", action="store_true", help="test groepsbediening, rollen, netem en upstream-regressies")
    p.add_argument("--baseline", type=Path, default=BEWIJSMAP / "b03-016-baseline-definitief-forkbasis.json",
                   help="definitief S-P40-50-bewijs op dezelfde stockdigest")
    p.add_argument("--uit", type=Path, required=True, help="nieuwe meet-JSON, mislukte of uitgestelde poging krijgt een eigen bestand")
    p.add_argument("--framecode-set", type=Path, default=UITVOER / setnaam(RECEPTEN["f1-framecode"], "vol", watchmeting.SEED))
    p.add_argument("--desktopbouw", type=Path, default=CLIENTBUILD)
    p.add_argument("--desktop-image", default=DESKTOP_IMAGE)
    p.add_argument("--label", choices=sorted(bewijs.LABELS), default="definitief-forkbasis")
    p.add_argument("--runs", type=int, default=5)
    a = p.parse_args(argv)
    if a.runs < watchmeting.MIN_RUNS:
        p.error("minstens vijf runs per scenario en systeem")
    a.uit = a.uit.resolve()
    poging = a.uit.with_name(a.uit.stem + "-meetpoging.json")
    doc = {"schema": "jelly-leon/b03-020-meetpoging/1", "werkpakket": "B03-020", "label": a.label, "images": {"stock": STOCK_IMAGE},
           "framecode_set_sha256": json.loads(FRAME.read_text(encoding="utf-8"))["set_sha256"], "metingen": [],
           "scenarios": {}, "clientdekking": dict(OPEN_CLIENTS)}
    try:
        if a.functieproef:
            return functieproef(a)
        doc["startcontrole"] = startcontrole(a.baseline)
        if not doc["startcontrole"]["meten"]:
            doc["status"] = UITGESTELD
            bewaar(poging, doc)
            print(UITGESTELD)
            return 3
        with meetvenster() as bezet:
            if bezet:
                doc.update(status=UITGESTELD, bezet_slot=bezet)
                bewaar(poging, doc)
                print(UITGESTELD)
                return 3
            # Geen oude meetbestanden vervangen als de herhaling onvolledig eindigt.
            a.uit.parent.mkdir(parents=True, exist_ok=True)
            logmap = Path(tempfile.mkdtemp(prefix=a.uit.stem + "-runs-", dir=a.uit.parent))
            code = meet(a, doc, logmap, poging)
        print(doc["status"])
        return code
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as fout:
        # Geen ruwe server-, autorisatie- of browseruitvoer naar het meetbewijs.
        reden = type(fout).__name__
        if type(fout) is ValueError or isinstance(fout, web.WebFout) and str(fout).startswith("harnas faalde: Watch Together: "):
            reden = str(fout)
        if isinstance(fout, HttpFout):
            reden = f"lokale testserver gaf HTTP {fout.status}"
        doc.update(status="Meting onderbroken", reden=reden)
        bewaar(poging, doc)
        print(f"Meting onderbroken ({reden})", file=sys.stderr)
        return 1
