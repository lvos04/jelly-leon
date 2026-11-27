"""Stockroutes op de door het harnas gestarte wegwerpserver. Alleen de bevroren stubs zijn aangekoppeld."""

from __future__ import annotations

import math
import re
import time
from collections import defaultdict

from .corpus.generator import REPO
from .f2_data import Dataset, tijd, utc
from .f2_metrieken import Profiel, rondgaand
from .jfapi import Jellyfin
from .statistiek import kwantiel
from .stock import WACHTWOORD


def gebruiker(beheer: Jellyfin, naam: str, *, kind: bool = False) -> Jellyfin:
    uid = beheer.gebruiker("f2-" + naam, WACHTWOORD, {"MaxParentalRating": 9} if kind else None)
    kijker = Jellyfin(beheer.url)
    kijker.login("f2-" + naam, WACHTWOORD)
    if kijker.admin_id != uid:
        raise ValueError("aangemeld als een ander testprofiel")
    return kijker


def stockcatalogus(beheer: Jellyfin, dataset: Dataset) -> dict[str, str]:
    """Bewijs dat ieder film- of serie-ID precies één keer is ingescand."""
    rijen = beheer.items({"fields": "ProviderIds,Genres,Tags,DateCreated", "includeItemTypes": "Movie,Series",
                         "limit": len(dataset.catalogus) + 1})
    provider = "dsyn" if dataset.naam == "D-SYN" else "dml"
    ids = {}
    for rij in rijen:
        item = next((v for k, v in rij.get("ProviderIds", {}).items() if k.lower() == provider), None)
        if item not in dataset.catalogus or item in ids:
            raise ValueError("onverwacht of dubbel corpus-ID in de bibliotheekscan")
        verwacht = dataset.catalogus[item]
        if rij["Type"] != verwacht.soort or frozenset(rij.get("Genres", [])) != verwacht.genres:
            raise ValueError("type of genres in de scan wijken af van de corpusmetadata")
        if dataset.naam == "D-ML":
            film = dataset.films[item]
            if (tijd(rij["DateCreated"]) != film.eerste or set(rij.get("Tags", [])) != film.tags
                    or not math.isclose(rij["CommunityRating"], 2 * film.som / film.aantal, abs_tol=0.0001)):
                raise ValueError("de stockmetadata wijken af van de D-ML-kenmerken vóór T")
        ids[item] = rij["Id"]
    if ids.keys() != dataset.catalogus.keys() or len(set(ids.values())) != len(ids):
        raise ValueError("stubbibliotheek onvolledig of dubbel gescand")
    return ids


def zaai(kijker: Jellyfin, profiel: Profiel, ids: dict[str, str]) -> int:
    # Valideer de volledige invoer vóór de eerste schrijfactie op de testserver.
    if any(i.tijd >= profiel.splitsing or i.item not in ids or i.item not in profiel.toegang for i in profiel.training):
        raise ValueError("ongeldige tijd of toegang in trainingsgeschiedenis")
    for i in profiel.training:
        uid = ids[i.item]
        kijker.a.doe("POST", f"/UserPlayedItems/{uid}", {"userId": kijker.admin_id, "datePlayed": utc(i.tijd)})
        if i.favoriet:
            kijker.a.doe("POST", f"/UserFavoriteItems/{uid}", {"userId": kijker.admin_id})
    return len(profiel.training)


def controleer_historie(kijker: Jellyfin, profiel: Profiel, ids: dict[str, str], dataset: Dataset) -> int:
    """Lees na het zaaien en na beide runs alle Played- en favorietvlaggen van het testprofiel terug."""
    items = kijker.items({"includeItemTypes": "Movie,Series", "fields": "", "enableUserData": "true", "limit": len(ids) + 1})
    staat = {r["Id"]: r["UserData"] for r in items}
    if set(staat) != {ids[i] for i in profiel.toegang}:
        raise ValueError("stocktoegang en het gemeenschappelijke kandidatenfilter verschillen")
    gezien = {ids[i] for i in profiel.gezien}
    favoriet = {ids[i.item] for i in profiel.training if i.favoriet}
    if gezien != {i for i, r in staat.items() if r["Played"]} or favoriet != {i for i, r in staat.items() if r["IsFavorite"]}:
        raise ValueError("teruggelezen Played of favorieten wijken af van de testgeschiedenis")
    # Een serie bewaart de speeldatum op de afleveringen; de vlag hierboven is de som over de serie.
    for i in profiel.training:
        if dataset.catalogus[i.item].soort == "Movie":
            gemeten = staat[ids[i.item]].get("LastPlayedDate", "")
            if gemeten[:19] != utc(i.tijd)[:19]:
                raise ValueError("teruggelezen speeldatum wijkt af van de gescripte geschiedenis")
    return len(gezien)


def ranglijsten(kijker: Jellyfin, dataset: Dataset, naam: str, ids: dict[str, str], omgekeerd: dict[str, str]) -> dict:
    p = dataset.profielen[naam]
    limiet = min(len(ids), len(p.gezien) + 10)
    q = {"userId": kijker.admin_id}

    def vertaal(rijen):
        return [omgekeerd[r["Id"]] for r in rijen if r["Id"] in omgekeerd]

    groepen = kijker.a.doe("GET", "/Movies/Recommendations", {**q, "categoryLimit": 5, "itemLimit": limiet})
    categorieen = defaultdict(list)
    rec = []
    for groep in groepen:
        rij = vertaal(groep["Items"])
        rec.append(rij)
        categorieen["categorie/" + groep["RecommendationType"]].append(rij)
    laatst = sorted(p.training, key=lambda i: (i.tijd, i.item), reverse=True)[:3]
    sim = [vertaal(kijker.a.doe("GET", f"/Items/{ids[i.item]}/Similar", {**q, "limit": limiet})["Items"]) for i in laatst]
    recent = kijker.a.doe("GET", "/Items/Latest", {**q, "limit": limiet, "includeItemTypes": "Movie,Series"})
    willekeurig = kijker.a.doe("GET", "/Items/Suggestions", {**q, "limit": limiet, "type": "Movie,Series"})
    return {"S-REC": list(rondgaand(rec)), "S-SIM": list(rondgaand(sim)), "S-LAT": vertaal(recent),
            "S-RND": vertaal(willekeurig["Items"]), "POP": dataset.pop(naam),
            **{k: list(rondgaand(v)) for k, v in categorieen.items()}}


def bronproeven() -> dict:
    """B9 en B11 zijn broncontroles in het oorspronkelijke protocol."""
    home = REPO / "src/Jellyfin.Database/Jellyfin.Database.Implementations/Enums/HomeSectionType.cs"
    typen = re.findall(r"^\s*(\w+)\s*=\s*\d+", home.read_text(), flags=re.MULTILINE)
    tmdb = (REPO / "MediaBrowser.Providers/Plugins/Tmdb/Movies/TmdbMovieSimilarProvider.cs").read_text()
    selectie = (REPO / "Emby.Server.Implementations/Library/SimilarItems/SimilarItemsManager.cs").read_text()
    if not typen or "LatestMedia" not in typen or "IRemoteSimilarItemsProvider<Movie>" not in tmdb:
        raise ValueError("bron voor B9 of B11 gewijzigd, herbeoordeling nodig")
    return {"B9": {"bron": "HomeSectionType", "sectietypen": typen,
                   "persoonlijke_aanbevelingsrij": any("recommend" in t.lower() for t in typen)},
            "B11": {"bron": "TmdbMovieSimilarProvider en SimilarItemsManager",
                    "remote_aanbevelingen": "GetMovieRecommendationsPageAsync" in tmdb,
                    "vereist_selectie": "typeOptions?.SimilarItemProviders?.Length > 0" in selectie,
                    "meting": "niet gemeten: S-TMDB vraagt de externe dienst"}}


def functieproef(beheer: Jellyfin, dataset: Dataset, ids: dict[str, str]) -> dict:
    """B1–B11 op aparte synthetische profielen. De meetgebruikers worden alleen door de rangschikkingsproef gebruikt."""
    koud = gebruiker(beheer, "proef-koud")
    warm = gebruiker(beheer, "proef-warm")
    kind = gebruiker(beheer, "proef-kind", kind=True)

    def rec(k):
        return k.a.doe("GET", "/Movies/Recommendations", {"userId": k.admin_id, "categoryLimit": 5, "itemLimit": 8})

    def rnd(k):
        return [i["Id"] for i in k.a.doe("GET", "/Items/Suggestions", {"userId": k.admin_id, "limit": 10})["Items"]]

    def sim(k, bron):
        return [i["Id"] for i in k.a.doe("GET", f"/Items/{bron}/Similar", {"userId": k.admin_id, "limit": 20})["Items"]]

    a, b = rnd(koud), rnd(koud)
    uit = {"B1": {"categorieen_koud": len(rec(koud))}, "B2": {"suggesties": len(a), "herhaling_gelijk": a == b}}
    p = dataset.profielen["ouder1"]
    films = [i for i in p.training if dataset.catalogus[i.item].soort == "Movie"][:3]
    for i in films:
        warm.a.doe("POST", "/UserPlayedItems/" + ids[i.item], {"userId": warm.admin_id, "datePlayed": utc(i.tijd)})
    warm.a.doe("POST", "/UserFavoriteItems/" + ids[films[0].item], {"userId": warm.admin_id})
    groepen = rec(warm)
    aanbod = [r["Id"] for g in groepen for r in g["Items"]]
    uit["B3"] = {"gezaaid": len(films), "categorieen": len(groepen), "aanbevolen": len(set(aanbod))}
    if aanbod:
        afkeer = aanbod[0]
        warm.a.doe("POST", f"/UserItems/{afkeer}/Rating", {"userId": warm.admin_id, "likes": "false"})
        uit["B4"] = {"nog_in_rec": any(i["Id"] == afkeer for g in rec(warm) for i in g["Items"]),
                     "nog_in_similar": any(afkeer in sim(warm, ids[i.item]) for i in films)}
    else:
        uit["B4"] = {"status": "niet gemeten", "reden": "stock gaf geen aanbeveling om af te wijzen"}
    serie = next(ids[k] for k in sorted(ids) if dataset.catalogus[k].soort == "Series")
    een, twee = sim(warm, serie), sim(warm, serie)
    uit["B5"] = {"similar_serie": len(een), "herhaling_gelijk": een == twee}
    zichtbaar = {r["Id"] for r in kind.items({"includeItemTypes": "Movie,Series", "fields": "", "limit": len(ids) + 1})}
    verborgen = set(ids.values()) - zichtbaar
    if not zichtbaar or not verborgen:
        raise ValueError("B6 vereist zowel zichtbare als afgeschermde stubs")
    lekken = sum(i in verborgen for bron in sorted(zichtbaar)[:20] for i in sim(kind, bron)) + len(set(rnd(kind)) & verborgen)
    status, _, _ = kind.a.ruw("GET", f"/Items/{min(verborgen)}/Similar", {"userId": kind.admin_id})
    if lekken or status != 404:
        raise ValueError("B6: verborgen stubs kwamen terug of werden niet geweigerd")
    uit["B6"] = {"zichtbaar": len(zichtbaar), "verborgen": len(verborgen), "lekken": lekken, "status_verborgen": status}
    uit["B7"] = {}
    for naam, actie in (("similar_film", lambda: sim(warm, ids[films[0].item])), ("similar_serie", lambda: sim(warm, serie)),
                         ("recommendations", lambda: rec(warm)), ("suggestions", lambda: rnd(warm))):
        ms = []
        for _ in range(15):
            begin = time.monotonic()
            actie()
            ms.append(1000 * (time.monotonic() - begin))
        uit["B7"][naam] = {"n": len(ms), "mediaan_ms": kwantiel(ms, 0.5), "p95_ms": kwantiel(ms, 0.95)}
    uit["B8"] = {"items": len(ids), "met_genre": sum(bool(i.genres) for i in dataset.catalogus.values())}
    uit["B10"] = {"categorie_met_bron": sum(bool(g.get("BaselineItemName")) for g in groepen),
                  "categorie_met_type": sum(bool(g.get("RecommendationType")) for g in groepen)}
    return uit | bronproeven()
