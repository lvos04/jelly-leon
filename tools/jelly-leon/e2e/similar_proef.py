#!/usr/bin/env python3
"""B03-031. Vergelijk twee kopieën van dezelfde synthetische 12.x-bibliotheek via echte serverroutes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from contextlib import contextmanager
from pathlib import Path

from plugin_proef import BEHEER, KIJKER, PLUGIN_DLL, PLUGIN_ID, Server, Sessie, docker, eerste_beheerder, wacht_op_taken
from upstream_gedrag_runtime import maak_testfilm

HARNAS = Path(__file__).resolve().parents[2] / "b03-harnas/playwright/harnas.mjs"
CHECKS = {
    "similar_volgorde", "similar_exportvolgorde", "similar_zonder_cache", "similar_batch",
    "similar_gebruiker", "similar_home", "similar_bewaarreden", "similar_homevoorkeur",
}
FILMS = {
    "Bron": ("Avontuur", True), "Alfa": ("Avontuur", False), "Beta": ("Avontuur", False), "Zulu": ("Avontuur", True),
    "Bronfout": ("Proeffout", False), "Kernfout": ("Proeffout", False),
    "Bronduur": ("Proefduur", False), "Kernduur": ("Proefduur", False),
}
SERIES = ("Seriebron", "Seriegezelschap")
HERVATPUNTEN = (4_000_000, 15_000_000)
OPTIES = "/Library/VirtualFolders/LibraryOptions"


def eis(waar, melding):
    if not waar:
        raise ValueError(melding)


def maak_corpus(media, stock):
    media.mkdir()
    maak_testfilm(stock, media)
    video = media / "Proeffilm.mkv"
    for naam, (genre, kern) in FILMS.items():
        map_ = media / "films" / naam
        map_.mkdir(parents=True)
        os.link(video, map_ / (naam + ".mkv"))
        extra = "<tag>Kern</tag><studio>Kernstudio</studio><director>Kernregisseur</director>" if kern else ""
        if naam == "Beta":
            extra += "<tag>Afgeschermd</tag>"
        (map_ / "movie.nfo").write_text(f"<movie><title>{naam}</title><genre>{genre}</genre>{extra}</movie>", encoding="utf-8")
    for naam in SERIES:
        map_ = media / "series" / naam
        map_.mkdir(parents=True)
        os.link(video, map_ / (naam + " S01E01.mkv"))
        (map_ / "tvshow.nfo").write_text(f"<tvshow><title>{naam}</title><genre>Serietest</genre></tvshow>", encoding="utf-8")
    video.unlink()


@contextmanager
def draai(naam, image, werk, media, plugin=None):
    server = Server(werk.parent.name + "-" + naam, image, werk, media)
    try:
        if plugin:
            doel = server.config / "plugins/JellyLeon_0.1.0.0"
            doel.mkdir(parents=True)
            shutil.copyfile(plugin / PLUGIN_DLL, doel / PLUGIN_DLL)
        info = server.start()
        eis(info["Version"].startswith("12."), "de runtime is geen 12.x")
        yield server
        server.stop()
    finally:
        server.ruim_op()


def sessie(server, wie, wachtwoord):
    return Sessie(server, wie, wachtwoord, "F2-proef", "f2-" + wie)


def zaai(server, wachtwoord):
    beheer = eerste_beheerder(server, wachtwoord)
    api = beheer.http
    for naam, soort, typen in [("films", "movies", ["Movie"]), ("series", "tvshows", ["Series", "Season", "Episode"])]:
        opties = {"PathInfos": [{"Path": "/media/" + naam}], "EnableRealtimeMonitor": False, "SaveLocalMetadata": False,
                  "EnableChapterImageExtraction": False, "EnableTrickplayImageExtraction": False, "MetadataSavers": [],
                  "TypeOptions": [{"Type": t, "MetadataFetchers": [], "ImageFetchers": [],
                                   "SimilarItemProviders": [], "SimilarItemProviderOrder": []} for t in typen]}
        api.doe("POST", "/Library/VirtualFolders", {"name": naam, "collectionType": soort, "refreshLibrary": "false"},
                {"LibraryOptions": opties})
    api.doe("POST", "/Library/Refresh")
    einde = time.monotonic() + 180
    while time.monotonic() < einde:
        rijen = api.doe("GET", "/Items", {"recursive": "true", "includeItemTypes": "Movie,Series", "fields": "Genres"})["Items"]
        ids = {r["Name"]: r["Id"] for r in rijen if r.get("Genres")}
        if set(ids) == set(FILMS) | set(SERIES):
            break
        time.sleep(1)
    else:
        raise ValueError("de scan vond de tien synthetische titels met genres niet")
    wacht_op_taken(api)
    api.doe("POST", "/Users/New", body={"Name": KIJKER, "Password": wachtwoord})
    kijker = sessie(server, KIJKER, wachtwoord)
    kijker.http.doe("POST", "/UserPlayedItems/" + ids["Alfa"], {"userId": kijker.id})
    api.doe("POST", "/UserPlayedItems/" + ids["Bron"], {"userId": beheer.id})
    api.doe("POST", "/UserFavoriteItems/" + ids["Bron"], {"userId": beheer.id})
    for wie, positie in zip((beheer, kijker), HERVATPUNTEN, strict=True):
        wie.http.doe("POST", "/UserItems/" + ids["Beta"] + "/UserData", {"userId": wie.id},
                     {"PlaybackPositionTicks": positie, "Played": False})
    return beheer, kijker, ids


def similar(wie, bron):
    antwoord = wie.http.doe("GET", "/Items/" + bron + "/Similar", {"limit": 1})
    eis(len(antwoord["Items"]) == 1 and antwoord["Items"][0]["Id"] != bron, "Similar mist een unieke andere treffer")
    return antwoord["Items"][0]["Id"]


def batch(wie):
    groepen = wie.http.doe("GET", "/Movies/Recommendations", {"categoryLimit": 20, "itemLimit": 20})
    resultaat = {(g["RecommendationType"], g.get("BaselineItemName"), i["Id"]) for g in groepen for i in g["Items"]}
    eis(resultaat, "lege voorraadgroep bij Movies/Recommendations")
    return resultaat


def schema(wie):
    doc = wie.http.doe("GET", "/api-docs/openapi.json")
    antwoord = doc["paths"]["/Items/{itemId}/Similar"]["get"]["responses"]["200"]
    # Ook veranderingen achter geneste $ref-verwijzingen moeten de vergelijking laten falen.
    gevonden = {}

    def volg(knoop):
        if isinstance(knoop, dict):
            if "$ref" in knoop:
                naam = knoop["$ref"].split("/")[-1]
                if naam not in gevonden:
                    gevonden[naam] = doc["components"]["schemas"][naam]
                    volg(gevonden[naam])
            for waarde in knoop.values():
                volg(waarde)
        elif isinstance(knoop, list):
            for waarde in knoop:
                volg(waarde)

    volg(antwoord)
    eis("BaseItemDto" in gevonden, "Similar-responsschema verwijst niet naar BaseItemDto")
    return antwoord, gevonden


def stel_volgorde(wie, volgorde, selectie=False):
    for map_ in wie.http.doe("GET", "/Library/VirtualFolders"):
        opties = map_["LibraryOptions"]
        for typeoptie in opties["TypeOptions"]:
            typeoptie["SimilarItemProviderOrder"] = [] if selectie else volgorde
            typeoptie["SimilarItemProviders"] = volgorde if selectie else ["Local Genre/Tag"]
        wie.http.doe("POST", OPTIES, body={"Id": map_["ItemId"], "LibraryOptions": opties})


def schakel(wie, aan):
    _, _, headers = wie.http.ruw("GET", "/media/v1/modules")
    kop = {k.lower(): v for k, v in headers.items()}
    code, _, _ = wie.http.ruw("PUT", "/media/v1/modules/recommendations", body={"enabled": aan},
                              headers={"Idempotency-Key": str(uuid.uuid4()), "If-Match": kop["etag"]})
    standen = wie.http.doe("GET", "/media/v1/modules")["items"]
    eis(code == 200 and {m["slug"] for m in standen if m["enabled"]} == ({"recommendations"} if aan else set()),
        "de modulekeuze is niet teruggelezen")


def kenmerken(wie, ids):
    return {naam: wie.http.doe("GET", "/UserItems/" + ids[naam] + "/UserData", {"userId": wie.id})
            for naam in ("Bron", "Alfa", "Beta", "Zulu")}


def kijkreferentie(beheer, kijker, ids):
    gegevens = [kenmerken(wie, ids) for wie in (beheer, kijker)]
    eis(gegevens[0]["Bron"]["Played"] and gegevens[0]["Bron"]["IsFavorite"] and gegevens[1]["Alfa"]["Played"],
        "de gespeelde titels of de favoriet ontbreken op stock")
    eis(tuple(r["Beta"]["PlaybackPositionTicks"] for r in gegevens) == HERVATPUNTEN,
        "de twee afzonderlijke hervatpunten ontbreken op stock")
    return gegevens


def bibliotheekopties(wie, verwacht):
    for soort, typenaam in (("movies", "Movie"), ("tvshows", "Series")):
        opties = wie.http.doe("GET", "/Libraries/AvailableOptions", {"libraryContentType": soort})
        providers = next(t["SimilarItemProviders"] for t in opties["TypeOptions"] if t["Type"] == typenaam)
        eis(any(p["Name"] == "Local Genre/Tag" for p in providers), "de lokale voorraadprovider ontbreekt")
        eigen = [p for p in providers if p["Name"] == "Jelly Leon"]
        eis(len(eigen) == int(verwacht) and all(p["DefaultEnabled"] for p in eigen), "onverwachte providers in de bibliotheekopties")


def homevoorkeur(wie):
    pad, vraag = "/DisplayPreferences/" + uuid.uuid4().hex, {"userId": wie.id, "client": "f2-proef"}
    basis = wie.http.doe("GET", pad, vraag)
    wie.http.doe("POST", pad, vraag, {**basis, "CustomPrefs": {"homesection0": "resume", "homesection1": "f2-uitbreiding"}})
    voorkeur = wie.http.doe("GET", pad, vraag)["CustomPrefs"]
    eis(voorkeur.get("homesection0") == "resume" and voorkeur.get("homesection1") == "resume",
        "home-enum of terugval gewijzigd, beoordeel of de webhaak kan vervallen")


def home(server, wachtwoord):
    for layout in ("modern", "desktop-legacy"):
        invoer = {"browser": "chromium", "url": server.url, "gebruiker": BEHEER, "wachtwoord": wachtwoord,
                  "localStorage": {"layout": layout}}
        proc = subprocess.run(["node", str(HARNAS), "homescherm", "-"], input=json.dumps(invoer), capture_output=True,
                              text=True, check=False, timeout=120)
        eis(proc.returncode == 0, f"Playwright kon het startscherm van {layout} niet lezen")
        meting = json.loads(proc.stdout)
        eis(meting["layout"] == layout and meting["zichtbaar"] and meting["secties"] >= 1, f"startschermsecties ontbreken in {layout}")


def voorraad(beheer, kijker, ids):
    bibliotheekopties(beheer, False)
    verwachte = {naam: similar(beheer, ids[naam]) for naam in ("Bron", "Bronfout", "Bronduur", "Seriebron")}
    eis(verwachte["Bron"] == ids["Zulu"], "de voorraadprovider onderscheidt de sterkste metadataoverlap niet")
    eis(batch(beheer) == batch(beheer), "voorraad varieert op deze kleine vaste batchset")
    return verwachte, batch(beheer), schema(beheer), kijkreferentie(beheer, kijker, ids)


def normale_proef(server, wachtwoord, ids, basis, meet):
    beheer, kijker = sessie(server, BEHEER, wachtwoord), sessie(server, KIJKER, wachtwoord)
    verwachte, groepen, contractschema, voor = basis
    eis(voor == [kenmerken(w, ids) for w in (beheer, kijker)], "kijkgegevens wijken bij de pluginstart af van stock")
    eigen = [p for p in beheer.http.doe("GET", "/Plugins") if p["Id"].replace("-", "") == PLUGIN_ID]
    eis(len(eigen) == 1 and eigen[0]["Status"] == "Active", "de plugin is niet precies één keer Active")
    bibliotheekopties(beheer, True)
    eis(schema(beheer) == contractschema, "het Similar-responsschema wijkt af van stock")
    standen = beheer.http.doe("GET", "/media/v1/modules")["items"]
    eis(not any(m["enabled"] for m in standen), "een module staat standaard aan")
    eis(similar(beheer, ids["Bron"]) == verwachte["Bron"], "uitgeschakelde module verandert Similar")
    schakel(beheer, True)
    eis(similar(beheer, ids["Bron"]) == verwachte["Bron"], "zonder volgorde wijkt Similar af van stock")
    for selectie in (True, False):
        stel_volgorde(beheer, ["Jelly Leon"], selectie=selectie)
        eis(similar(beheer, ids["Bron"]) == ids["Alfa"], "de ingestelde providervolgorde levert niet de alfabetische genrekeuze")
    eis(similar(beheer, ids["Seriebron"]) == ids["Seriegezelschap"], "de serieprovider vindt geen soortgenoot")
    meet("similar_volgorde", "Movie en Series zichtbaar; providers-lijst en expliciete volgorde uitgelezen via Similar")
    eis(similar(kijker, ids["Bron"]) == ids["Beta"] and similar(beheer, ids["Bron"]) == ids["Alfa"], "gebruikers overlappen")
    beleidpad = f"/Users/{kijker.id}/Policy"
    beleid = beheer.http.doe("GET", "/Users/" + kijker.id)["Policy"]
    beheer.http.doe("POST", beleidpad, body={**beleid, "BlockedTags": ["Afgeschermd"]})
    try:
        code, _, _ = kijker.http.ruw("GET", "/Items/" + ids["Beta"] + "/Similar")
        eis(code == 404 and similar(kijker, ids["Bron"]) == ids["Zulu"],
            "een afgeschermde bron of genretreffer was zichtbaar voor het beperkte profiel")
    finally:
        beheer.http.doe("POST", beleidpad, body=beleid)
    meet("similar_gebruiker", "twee profielen apart; afgeschermde bron HTTP 404 en afgeschermde treffer uitgesloten")
    eis(batch(beheer) == groepen, "batchverzameling wijkt met de module aan af van stock")
    meet("similar_batch", f"{len(groepen)} categorieverwijzingen gelijk aan stock")
    # Ook de losse Similar-schakelaar moet direct effect hebben terwijl de module actief blijft.
    pad = "/Plugins/" + PLUGIN_ID + "/Configuration"
    cfg = beheer.http.doe("GET", pad)
    cfg["Recommendations"]["Similar"]["Enabled"] = False
    beheer.http.doe("POST", pad, body=cfg)
    eis(similar(beheer, ids["Bron"]) == verwachte["Bron"], "Similar uit wijkt met expliciete volgorde af van stock")
    schakel(beheer, False)
    eis(voor == [kenmerken(w, ids) for w in (beheer, kijker)], "kijkgegevens verschillen na de leesproeven")
    meet("kijkgegevens", "acht kijkrecords en twee afzonderlijke hervatpunten gelijk voor installatie, bij start en na de proef")
    homevoorkeur(beheer)
    meet("similar_homevoorkeur", "bekende sectie bewaard, onbekende sectie terug naar de enumstandaard")
    home(server, wachtwoord)
    meet("similar_home", "startscherm met gevulde secties zichtbaar in modern en desktop-legacy")


def waarnemersproef(server, wachtwoord, ids, basis, meet):
    beheer = sessie(server, BEHEER, wachtwoord)
    kijker = sessie(server, KIJKER, wachtwoord)

    def tel(bericht):
        log = docker("logs", server.container_id)
        return (log.stdout + log.stderr).count("F2-PROEF " + bericht)

    schakel(beheer, True)
    voor = tel("aanroep")
    eis(similar(beheer, ids["Bron"]) == basis[0]["Bron"] and tel("aanroep") == voor, "core vult limit=1, maar de plugin is aangeroepen")
    stel_volgorde(beheer, ["Jelly Leon"])
    for wie, naam in ((beheer, "Alfa"), (kijker, "Beta"), (beheer, "Alfa")):
        eis(similar(wie, ids["Bron"]) == ids[naam], "de provider zag het verkeerde profiel")
    eis(tel("aanroep") == voor + 3, "herhaalde lokale aanroepen bereikten de provider niet steeds opnieuw")
    meet("similar_exportvolgorde", "zonder volgorde nul aanroepen bij een volle core-uitkomst")
    meet("similar_zonder_cache", "drie verzoeken aan dezelfde bron bereikten de lokale provider drie keer")
    for naam, marker in (("Bronfout", "uitzondering"), ("Bronduur", "vertraging")):
        voor = tel(marker)
        start = time.monotonic()
        resultaat = similar(beheer, ids[naam])
        ms = round((time.monotonic() - start) * 1000)
        eis(tel(marker) == voor + 1 and resultaat == basis[0][naam], f"{marker} gaf geen gemeten terugval naar stock")
        if marker == "vertraging":
            eis(ms < 1500, "de HTTP-aanroep wachtte op de twee seconden durende proeflezing")
        meet(marker, f"stocktreffer terug via HTTP in {ms} ms")
    for pad, reden in (("/UserPlayedItems/", "TogglePlayed"), ("/UserFavoriteItems/", "UpdateUserRating")):
        voor = tel("bewaard " + reden)
        beheer.http.doe("POST", pad + ids["Beta"], {"userId": beheer.id})
        eis(tel("bewaard " + reden) == voor + 1, "opgeslagen testwijziging mist een gebeurtenis met de juiste reden")
    meet("similar_bewaarreden", "twee afzonderlijke opslagacties, TogglePlayed en UpdateUserRating waargenomen")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--stock-image", required=True)
    parser.add_argument("--werkmap", required=True, type=Path)
    parser.add_argument("--plugin-map", type=Path, help="gewone DLL voor een image die hem niet zelf installeert")
    parser.add_argument("--proef-plugin-map", type=Path, help="proefbouw op stock voor de teller, bewaargebeurtenis en foutinjectie")
    parser.add_argument("--rapport", type=Path, required=True)
    args = parser.parse_args(argv)
    os.umask(0o022)
    uit = {}
    fase = "voorraad"

    def meet(naam, detail):
        uit[naam] = detail
        print(f"{naam}: {detail}", flush=True)

    try:
        with tempfile.TemporaryDirectory(prefix="jl-f2-", dir=args.werkmap) as tmp:
            werk = Path(tmp)
            media = werk / "media"
            maak_corpus(media, args.stock_image)
            wachtwoord = uuid.uuid4().hex
            with draai("stock", args.stock_image, werk / "stock", media) as stock:
                beheer, kijker, ids = zaai(stock, wachtwoord)
                basis = voorraad(beheer, kijker, ids)
            fase = "gewone plugin"
            for naam, image, plugin, test in [("normaal", args.image, args.plugin_map, normale_proef),
                                              ("waarnemer", args.stock_image, args.proef_plugin_map, waarnemersproef)]:
                if naam == "waarnemer" and plugin is None:
                    continue
                fase = naam
                shutil.copytree(werk / "stock/config", werk / naam / "config")
                with draai(naam, image, werk / naam, media, plugin) as server:
                    test(server, wachtwoord, ids, basis, meet)
            vereist = CHECKS | {"kijkgegevens", "uitzondering", "vertraging"} if args.proef_plugin_map else (
                CHECKS - {"similar_zonder_cache", "similar_exportvolgorde", "similar_bewaarreden"} | {"kijkgegevens"}
            )
            eis(vereist <= uit.keys(), "een verplichte proef ontbreekt")
    except Exception as exc:
        # HTTP-fouten kunnen antwoorden met een sessiesleutel bevatten. Alleen eigen meldingen en het type tonen.
        fout = str(exc) if type(exc) is ValueError else type(exc).__name__
        eigen = [regel for regel in traceback.extract_tb(exc.__traceback__) if regel.filename == __file__]
        plek = f"{eigen[-1].name}/{eigen[-1].lineno}" if eigen else fase
        status = f" HTTP {exc.status}" if hasattr(exc, "status") else ""
        uit["fout"] = f"{fase} ({plek}): {fout}{status}"
    args.rapport.write_text(json.dumps(uit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(uit.get("fout", f"{len(uit)} controles uitgevoerd"))
    return int("fout" in uit)


if __name__ == "__main__":
    sys.exit(main())
