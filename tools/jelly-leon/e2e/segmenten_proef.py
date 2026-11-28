"""JLT-56 op drie kopieën van één gevulde wegwerpserver. Alle padwijzigingen betreffen het eigen corpus."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

import plugin_proef as pp
import proef_lib as pl

PROVIDER = "89c1fd4ffb135be83ede19aa4ba67b06"
BASIS = "/media/v1/segments"
DB = Path("data/jellyfin.db")
EIGEN = Path("data/jelly-leon/segments/segments.db")


def lees_db(pad: Path) -> sqlite3.Connection:
    return sqlite3.connect(pad.resolve().as_uri() + "?mode=ro", uri=True)


def opname(pad: Path, doel: Path) -> tuple[int, int]:
    """Leg ook de WAL vast. Filter uitsluitend het vaste provider-ID in de meetkopie."""
    doel.parent.mkdir(parents=True, exist_ok=True)
    with closing(lees_db(pad)) as bron, closing(sqlite3.connect(doel)) as kopie:
        bron.backup(kopie)
        eigen = kopie.execute("DELETE FROM MediaSegments WHERE SegmentProviderId = ?", (PROVIDER,)).rowcount
        vreemd = kopie.execute("SELECT COUNT(*) FROM MediaSegments WHERE SegmentProviderId = 'proefbron'").fetchone()[0]
        kopie.commit()
    return eigen, vreemd


def beoordeel_tabellen(oordeel: dict) -> tuple[list[str], list[str]]:
    afwijkend = [t for t, o in oordeel.items() if o["oordeel"] == "afwijking"]
    # Alleen variërende serverklokken uit twee onafhankelijke stockruns mogen worden gemaskeerd.
    klokken = {"DateCreated", "DateModified", "DateLastActivity", "LastActivityDate", "LastLoginDate", "RowVersion",
               "Timestamp", "DateLastRefreshed", "LastSaved", "DateLastSaved", "DateLastMediaAdded"}
    onbeslist = [t for t, o in oordeel.items() if o["oordeel"] == "ruis_onvergelijkbaar" or
                 (set(o["masker"]) - klokken) or (t in ("UserData", "MediaSegments") and o["masker"])]
    return afwijkend, onbeslist


def controleer_tabellen(a1: Path, a2: Path, b: Path) -> tuple[list[str], list[str]]:
    return beoordeel_tabellen(pl.vergelijk_db(a1, a2, b))


def wacht(lezen, akkoord, naam: str, seconden: int = 65):
    einde = time.monotonic() + seconden
    while time.monotonic() < einde:
        waarde = lezen()
        if akkoord(waarde):
            return waarde
        time.sleep(1)
    raise RuntimeError(f"Geen bevestigde toestand bij {naam}")


def mutatie(http: pp.Http, methode: str, pad: str, body: dict, etag: str | None = None):
    kop = {"Idempotency-Key": str(uuid.uuid4())}
    if etag:
        kop["If-Match"] = etag
    return http.doe(methode, pad, body=body, headers=kop)


def schakel(http: pp.Http, aan: bool) -> None:
    status, _, kop = http.ruw("GET", "/media/v1/modules")
    if status != 200:
        raise RuntimeError(f"Modules lezen gaf HTTP {status}")
    etag = next(v for k, v in kop.items() if k.lower() == "etag")
    mutatie(http, "PUT", "/media/v1/modules/segments", {"enabled": aan}, etag)


def stand(http: pp.Http, bib: str, modus: str, reden: str | None = None) -> None:
    body = {"library_id": bib, "mode": modus}
    if reden:
        body["override_reason"] = reden
    pad = BASIS + "/publication"
    preview = mutatie(http, "PUT", pad, {**body, "dry_run": True})
    mutatie(http, "PUT", pad, {**body, "dry_run": False, "preview_hash": preview["preview_hash"]})


def kijkstand(http: pp.Http, item: str, gebruiker: str) -> tuple:
    data = http.doe("GET", f"/UserItems/{item}/UserData", {"userId": gebruiker})
    return tuple(data.get(k) for k in ("PlaybackPositionTicks", "Played", "IsFavorite", "Rating", "Likes"))


@contextmanager
def waarneem_media(media: Path):
    """Tel op Linux ook voor schrijven geopende en ongewijzigd gesloten bestanden op de eigen mediamount."""
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "inotify voor het proefcorpus openen")
    # modify, attrib, close_write, moved_from/to, create, delete, delete_self, move_self
    schrijfmasker = 0x0002 | 0x0004 | 0x0008 | 0x0040 | 0x0080 | 0x0100 | 0x0200 | 0x0400 | 0x0800
    kop = struct.Struct("iIII")

    def tel():
        aantal = 0
        while True:
            try:
                blok = os.read(fd, 65536)
            except BlockingIOError:
                return aantal
            pos = 0
            while pos < len(blok):
                _, masker, _, naamgrootte = kop.unpack_from(blok, pos)
                if masker & 0x4000:  # IN_Q_OVERFLOW
                    raise RuntimeError("De kernelwachtrij voor het proefcorpus is volgelopen")
                aantal += bool(masker & schrijfmasker)
                pos += kop.size + naamgrootte

    try:
        for map_ in [media, *(p for p in media.rglob("*") if p.is_dir())]:
            if libc.inotify_add_watch(fd, os.fsencode(map_), schrijfmasker) < 0:
                raise OSError(ctypes.get_errno(), "proefmap observeren")
        yield tel
    finally:
        os.close(fd)


def maak_corpus(werk: Path, stock: str) -> Path:
    media = werk / "bronmedia"
    media.mkdir()
    subprocess.run([sys.executable, str(pp.E2E / "make_test_media.py"), str(media / "muziek")], check=True, capture_output=True)
    origineel = werk / "mkv" / Path(pp.FILM_REL).name
    pp.maak_sporenfilm(stock, origineel, werk / "ondertitels")
    mp4 = (media / "films" / pp.FILM_REL).with_suffix(".mp4")
    mp4.parent.mkdir(parents=True)
    pp.docker("run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
              "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffmpeg", "-v", f"{origineel.parent}:/in:ro", "-v", f"{mp4.parent}:/out",
              stock, "-loglevel", "error", "-i", f"/in/{origineel.name}", "-map", "0", "-c", "copy", "-c:s", "mov_text",
              "-threads", "1", f"/out/{mp4.name}")
    mp4.with_suffix(".nfo").write_text('<movie><title>Proeffilm</title><uniqueid type="imdb" default="true">tt0000001</uniqueid></movie>')
    vervanging = werk / "vervanging"
    vervanging.mkdir()
    pp.docker("run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
              "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffmpeg", "-v", f"{mp4.parent}:/in:ro", "-v", f"{vervanging}:/out",
              stock, "-loglevel", "error", "-i", f"/in/{mp4.name}", "-map", "0", "-c", "copy",
              "-metadata", "title=Vervangen proeffilm", f"/out/{mp4.name}")
    if mp4.read_bytes() == (vervanging / mp4.name).read_bytes():
        raise RuntimeError("Vervanger en origineel hebben dezelfde bytes")
    return media


def film_id(http: pp.Http) -> str | None:
    items = http.doe("GET", "/Items", {"recursive": "true", "includeItemTypes": "Movie"})["Items"]
    if len(items) > 1:
        raise RuntimeError("Meer dan één testfilm gevonden")
    return items[0]["Id"] if items else None


def scan(http: pp.Http) -> None:
    http.doe("POST", "/Library/Refresh")
    pp.wacht_op_taken(http)


def items(http: pp.Http) -> list:
    return http.doe("GET", BASIS + "/export")["items"]


def importeer(http: pp.Http, bundel: dict) -> None:
    preview = http.doe("POST", BASIS + "/import/preview", body=bundel)
    mutatie(http, "POST", BASIS + "/import/apply", {"preview_hash": preview["preview_hash"]})


def migratie_proef(server: pp.Server, kop: dict, werk: Path, v: pp.Verslag) -> None:
    """Test zowel een geslaagde als een falende upgrade van een echte, gevulde modulekopie."""
    for goed in (True, False):
        naam = "migratie-goed" if goed else "migratie-fout"
        proef = pp.Server(f"{werk.name}-{naam}", server.image, werk / naam, server.media)
        shutil.copytree(server.config, proef.config)
        pad = proef.config / EIGEN
        with closing(sqlite3.connect(pad)) as db:
            versie = db.execute("PRAGMA user_version").fetchone()[0]
            origineel = db.execute("SELECT id, inhoud FROM items ORDER BY id").fetchall()
            if goed:
                db.execute("DROP TABLE weesmoment")
            # Bij de foutproef bestaat de doel-tabel opzettelijk al in de oude testdatabase.
            db.execute(f"PRAGMA user_version={versie - 1}")
            db.commit()
        try:
            proef.start()
            http = pp.Http(proef.url, kop)
            status = http.ruw("GET", BASIS + "/status")[0]
            proef.stop()
            with closing(lees_db(pad)) as db:
                na = db.execute("SELECT id, inhoud FROM items ORDER BY id").fetchall()
                nieuw = db.execute("PRAGMA user_version").fetchone()[0]
                integer = db.execute("PRAGMA integrity_check").fetchone()[0]
            backups = list(pad.parent.glob("*.bak"))
            kopie_ok = False
            for backup in backups:
                with closing(lees_db(backup)) as db:
                    if db.execute("PRAGMA user_version").fetchone()[0] == versie - 1:
                        kopie_ok |= db.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and db.execute(
                            "SELECT id, inhoud FROM items ORDER BY id").fetchall() == origineel
            v.test("JLT-56d", naam, bool(origineel) and origineel == na and integer == "ok" and kopie_ok
                   and (status == 200 and nieuw == versie if goed else status >= 500 and nieuw == versie - 1),
                   f"HTTP {status}, versie {versie - 1} naar {nieuw}, back-up met correcties {kopie_ok}")
        finally:
            proef.ruim_op()


def herstel_proef(server: pp.Server, kop: dict, archief: str, bundel: dict, film: str, kijker: str,
                  voor: tuple, werk: Path, v: pp.Verslag) -> None:
    """Herstel een officiële back-up op een afzonderlijke kopie en vul de lege module met de export."""
    proef = pp.Server(f"{werk.name}-herstel", server.image, werk / "herstel", server.media)
    shutil.copytree(server.config, proef.config)
    try:
        proef.start()
        http = pp.Http(proef.url, kop)
        http.doe("DELETE" if voor[2] else "POST", f"/UserFavoriteItems/{film}", {"userId": kijker})
        if kijkstand(http, film, kijker) == voor:
            raise RuntimeError("De herstelmarker in de proefkopie is niet gewijzigd")
        http.doe("POST", "/Backup/Restore", body={"ArchiveFileName": Path(archief).name})
        # De server sluit de huidige host en voert het herstel tijdens zijn eigen herstart uit.
        def verwerkt():
            try:
                return kijkstand(http, film, kijker) == voor
            except (RuntimeError, OSError):
                return False
        time.sleep(3)
        toestand = pp.docker("inspect", "--format", "{{.State.Running}}", proef.container_id).stdout.strip()
        if toestand == "false":
            pp.docker("start", proef.container_id)
        pp.wacht_klaar(proef.url)
        wacht(verwerkt, bool, "Jellyfin-herstel")
        proef.stop()
        # Verplaats de herstelde pluginopslag uitsluitend op de gestopte proefkopie.
        (proef.config / EIGEN).parent.rename(werk / "herstelde-modulekopie")
        proef.start()
        http = pp.Http(proef.url, kop)
        leeg = items(http) == []
        importeer(http, bundel)
        v.test("JLT-56e", "Officiële back-up hersteld en export in lege module geïmporteerd",
               leeg and items(http) == bundel["items"] and kijkstand(http, film, kijker) == voor)
    finally:
        proef.ruim_op()


def meet_run(naam: str, server: pp.Server, zaai: pp.Server, kop: dict, kijker: str, eerste: str, werk: Path,
             v: pp.Verslag, standen: dict, pluginmap: Path | None) -> None:
    fork = naam == "b"
    shutil.copytree(zaai.config, server.config)
    if fork and pluginmap:
        doel = server.config / "plugins/JellyLeon_0.1.0.0"
        doel.mkdir(parents=True)
        shutil.copy2(pluginmap / pp.PLUGIN_DLL, doel / pp.PLUGIN_DLL)
    voortgang = server.map / "mediaguard-proef.db"
    with closing(sqlite3.connect(voortgang)) as db:
        db.execute("CREATE TABLE voortgang(taak INTEGER PRIMARY KEY, stap INTEGER NOT NULL)")
        db.execute("INSERT INTO voortgang VALUES(4,19)")
        db.commit()

    def begin():
        server.start()
        return pp.Http(server.url, kop, timeout=180)

    def foto(moment: str):
        doel = werk / "metingen" / moment / (naam + ".db")
        aantallen = opname(server.config / DB, doel)
        if fork and (doel.parent / "a1.db").is_file():
            oordeel = pl.vergelijk_db(doel.parent / "a1.db", doel.parent / "a2.db", doel)
            afwijkend, onbeslist = beoordeel_tabellen(oordeel)
            kolommen = {t: oordeel[t].get("afwijkende_kolommen", oordeel[t]["masker"]) for t in afwijkend + onbeslist}
            v.test("JLT-56", f"Alle tabellen bij {moment}", not afwijkend and not onbeslist,
                   f"afwijkend {afwijkend}, onvergelijkbaar {onbeslist}, kolommen {kolommen}")
            if afwijkend:
                raise RuntimeError("Afwijking buiten de eigen providerrijen bij " + moment)
        return aantallen

    media = server.media
    mp4 = (media / "films" / pp.FILM_REL).with_suffix(".mp4")
    mkv = mp4.with_suffix(".mkv")
    http = begin()
    bib = next(b["ItemId"] for b in http.doe("GET", "/Library/VirtualFolders") if b["Name"] == "Films")
    voor = kijkstand(http, eerste, kijker)
    if not (voor[0] and voor[2]):
        raise RuntimeError("De kijker mist het gezaaide hervatpunt of de favoriet")
    v.test("JLT-56", f"{naam} gezaaide kijkgegevens en simulatievoortgang aanwezig", True)
    if fork:
        schakel(http, True)
        stand(http, bib, "shadow")
        wacht(lambda: items(http), lambda rijen: len(rijen) == 1 and bool(rijen[0]["kandidaten"]), "hoofdstuk als schaduwsignaal")
        bundel = http.doe("GET", BASIS + "/export")
        rij = bundel["items"][0]
        rij["kandidaten"][0].update(bron="manual", zekerheid=1)
        rij["bevestigd"] = True
        # Een bestaande correctie uit een vorige installatie komt via de officiële import terug.
        server.stop()
        (server.config / EIGEN).parent.rename(werk / "schaduw-opslag")
        http = begin()
        importeer(http, bundel)
        stand(http, bib, "shadow")
        tijdvak = rij["kandidaten"][0]
        v.test("JLT-56", "Schaduw bevat de menselijke correctie en publiceert niets",
               foto("schaduw")[0] == 0 and http.doe("GET", f"{BASIS}/{eerste}")["segments"] == [])
        stand(http, bib, "published", "Steekproef op de synthetische film bevestigd")
    else:
        # Ook stock doorloopt de herstart van de kopie waarmee de historische correctie werd ingevoerd.
        server.stop()
        http = begin()
    eigenaar, vreemd = foto("publicatie")
    v.test("JLT-56", f"{naam} eigendom en bestaande vreemde rij bij publicatie", eigenaar == int(fork) and vreemd == 1,
           f"eigen {eigenaar}, vreemd {vreemd}")

    if fork:
        stand(http, bib, "shadow")
    eigen_na, vreemd_na = foto("depublicatie")
    v.test("JLT-56i", f"{naam} depublicatie behoudt de vreemde referentierij", eigen_na == 0 and vreemd_na == 1)
    if fork:
        stand(http, bib, "published", "Menselijke correctie op proefkopie vrijgegeven")
        bundel = http.doe("GET", BASIS + "/export")
        gebruikers = http.doe("GET", "/Users")
        tekst = json.dumps(bundel).lower().replace("-", "")
        v.test("JLT-56e", "Export bevat geen account-ID’s of meldingen", bool(bundel["items"])
               and all(g["Id"].lower().replace("-", "") not in tekst for g in gebruikers) and "notification" not in tekst)
    manifest = http.doe("POST", "/Backup/Create", body={"Database": True})
    server.stop()
    if fork:
        migratie_proef(server, kop, werk, v)
        herstel_proef(server, kop, manifest["Path"], bundel, eerste, kijker, voor, werk, v)
    http = begin()

    # De schrijver is de proef zelf, vóór de scan. Alle drie de kopieën krijgen dezelfde bytes en mtime.
    vervanger = server.map / "vervanger.mp4"
    shutil.copy2(werk / "vervanging" / mp4.name, vervanger)
    os.utime(vervanger, ns=(mp4.stat().st_atime_ns, mp4.stat().st_mtime_ns + 120_000_000_000))
    vervanger.replace(mp4)
    scan(http)
    if fork:
        def correctie(lijst):
            return any(tijdvak in r["kandidaten"] and r["heruitlijnen"] for r in lijst)
        wacht(lambda: items(http), correctie, "behoud na vervanging")
        v.test("JLT-56a", "Vervanging bewaart de correctie voor review", foto("vervanging")[0] == 0)
    else:
        foto("vervanging")
    standen[naam, "a"] = kijkstand(http, eerste, kijker)

    def herbeoordeling(film: str):
        if http.doe("GET", BASIS + "/orphans")["frozen"]:
            mutatie(http, "POST", BASIS + "/orphans/unfreeze", {"reason": "Eigen testbestand is terug"})
        stand(http, bib, "shadow")
        wacht(lambda: items(http), lambda rs: any(r["item_id"].replace("-", "").lower() == film.replace("-", "").lower()
              and not r["wees"] and tijdvak in r["kandidaten"] for r in rs), "herkoppeling na een padwissel")

    shutil.copy2(werk / "mkv" / mkv.name, mkv)
    mp4.unlink()
    scan(http)
    film = wacht(lambda: film_id(http), bool, "MKV in de bibliotheek")
    if fork:
        herbeoordeling(film)
        v.test("JLT-56b", "Containerwissel bewaart de bestaande handgrenzen", True)
    foto("padwissel")
    standen[naam, "b"] = kijkstand(http, film, kijker)

    apart = server.map / "afwezig"
    mkv.rename(apart)
    scan(http)
    wacht(lambda: film_id(http), lambda id_: id_ is None, "verwijderde testfilm")
    if fork:
        wacht(lambda: http.doe("GET", BASIS + "/orphans"), lambda r: r["count"] > 0, "wees na verwijdering")
    apart.rename(mkv)
    scan(http)
    film = wacht(lambda: film_id(http), bool, "teruggezette testfilm")
    if fork:
        herbeoordeling(film)
        v.test("JLT-56c", "Teruggezet item heeft zijn correctie", True)
    foto("teruggezet")
    standen[naam, "c"] = kijkstand(http, film, kijker)

    # Open de eigen kopie opnieuw met een schrijfbare bindmount. Verander het corpus tijdens de meting niet.
    voor_media = pp.corpus(media)
    voor_items = items(http) if fork else []
    server.stop()
    server.media_schrijfbaar = True
    with waarneem_media(media) as tel:
        http = begin()
        if fork:
            gezondheid = http.doe("GET", BASIS + "/status")
            v.test("JLT-56f", "Schrijfbare mount blokkeert analyse en geeft rode status",
                   gezondheid["health"] == "down" and gezondheid["reason"] == "media_mount_writable" and items(http) == voor_items)
        server.stop()
        aantal = tel()
    v.test("JLT-56f", f"{naam} schrijfbare mount behoudt het corpus zonder schrijfgebeurtenissen",
           aantal == 0 and pp.corpus(media) == voor_media, f"{aantal} schrijfgebeurtenissen")
    server.media_schrijfbaar = False
    http = begin()

    groep = media / "films" / "Weesproef"
    groep.mkdir()
    for nummer in range(6):
        doel = groep / f"Proefwezen {nummer:02} (2026)"
        doel.mkdir()
        os.link(mkv, doel / (doel.name + ".mkv"))
    scan(http)
    if fork:
        wacht(lambda: items(http), lambda rs: len(rs) >= 7, "zeven bestaande films")
        aantal = len(items(http))
    groep.rename(server.map / "tijdelijk-weg")
    scan(http)
    if fork:
        wezen = wacht(lambda: http.doe("GET", BASIS + "/orphans"), lambda r: r["frozen"] and r["count"] >= 6, "massale wezen")
        v.test("JLT-56g", "Tijdelijk verdwenen deel van de bibliotheek bevriest en behoudt alle items",
               len(items(http)) == aantal, f"{wezen['count']} wezen van {aantal}")
    foto("wezen")
    if fork:
        schakel(http, False)
    eigen, _ = foto("uit")
    pad = "/MediaSegments/" + film
    standen[naam, "i"] = http.doe("GET", pad)
    v.test("JLT-56i", f"{naam} geen eigen rijen na uitzetten", eigen == 0)
    server.stop()
    if fork:
        aanwezig = (server.config / EIGEN).is_file()
        if not aanwezig:
            raise RuntimeError("segments.db verdween bij uitzetten")
        behouden = hashlib.sha256((server.config / EIGEN).read_bytes()).hexdigest()
        for dll in (server.config / "plugins").glob("JellyLeon_*/" + pp.PLUGIN_DLL):
            dll.unlink()
        server.image = zaai.image
    http = begin()
    if fork:
        v.test("JLT-56i", "Stock start na verwijderen en kan de bestaande kijkgegevens lezen",
               http.ruw("GET", BASIS + "/status")[0] == 404 and kijkstand(http, film, kijker) == standen[naam, "c"])
    foto("verwijderd")
    server.stop()
    if fork:
        v.test("JLT-56i", "Stock laat de gedocumenteerde eigen database intact",
               hashlib.sha256((server.config / EIGEN).read_bytes()).hexdigest() == behouden)
    with closing(lees_db(voortgang)) as db:
        v.test("JLT-56", f"{naam} voortgang van de afzonderlijke MediaGuard-simulator blijft leesbaar",
               db.execute("SELECT taak, stap FROM voortgang").fetchall() == [(4, 19)])


def voer_uit(args: argparse.Namespace) -> int:
    v = pp.Verslag()
    stock = args.stock_image or args.image
    with tempfile.TemporaryDirectory(dir=args.werkmap, prefix="jl-segmentproef-") as tmp:
        werk = Path(tmp).resolve()
        servers = []
        try:
            media = maak_corpus(werk, stock)
            bron = pp.Server(werk.name + "-zaai", stock, werk / "zaai", media)
            servers.append(bron)
            bron.start()
            ww = {n: v.geheim("wachtwoord:" + n, uuid.uuid4().hex) for n in (pp.BEHEER, pp.KIJKER)}
            _, film = pp.zaai(bron, ww)
            beheer = pp.Sessie(bron, pp.BEHEER, ww[pp.BEHEER], pp.TOESTEL_BEHEER, "jl-proef-beheer")
            kijker = pp.Sessie(bron, pp.KIJKER, ww[pp.KIJKER], "Kijkertoestel-Zeldzaam-2207", "jl-proef-kijker")
            for rol, sessie in (("beheer", beheer), ("kijker", kijker)):
                v.geheim("sessie:" + rol, sessie.token)
            bron.stop()
            pp.zaai_hoofdstuk_en_segment(bron.config, film)
            with closing(sqlite3.connect(bron.config / DB)) as db:
                db.execute("UPDATE Chapters SET Name='Intro' WHERE Name='Proefhoofdstuk'")
                db.execute("INSERT INTO Chapters(ItemId,ChapterIndex,StartPositionTicks,Name) "
                           "SELECT ItemId,ChapterIndex+1,20000000,'Hoofddeel' FROM Chapters WHERE Name='Intro'")
                db.commit()
            standen = {}
            voor = pp.corpus(media)
            for naam in ("a1", "a2", "b"):
                kopie = werk / naam / "media"
                shutil.copytree(media, kopie)
                run = pp.Server(werk.name + "-" + naam, args.image if naam == "b" else stock, werk / naam, kopie)
                servers.append(run)
                meet_run(naam, run, bron, beheer.http.headers, kijker.id, film, werk, v, standen, args.plugin_map)
            for stap in ("a", "b", "c", "i"):
                v.test("JLT-56" + stap, "Kijkgegevens of segmentantwoord gelijk aan beide stockkopieën",
                       standen["a1", stap] == standen["a2", stap] == standen["b", stap])
            v.test("JLT-56f", "Oorspronkelijk mediacorpus behoudt SHA-256, omvang en mtimes", pp.corpus(media) == voor)
        except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error, subprocess.SubprocessError) as fout:
            v.test("JLT-56", "Uitvoering onderbroken", False, str(fout)[:350])
        finally:
            for s in servers:
                s.ruim_op()
    if args.rapport:
        args.rapport.write_text(json.dumps({"geslaagd": v.geslaagd, "tests": v.regels}, ensure_ascii=False, indent=2) + "\n")
    print(f"JLT-56: {sum(r['geslaagd'] for r in v.regels)}/{len(v.regels)} controles positief")
    return 0 if v.geslaagd else 1
