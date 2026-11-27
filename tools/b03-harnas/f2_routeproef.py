"""Kleine integratieproef van de stockroutes, zonder tijdmeting of rangschikkingscijfers."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from b03h.f2_data import Dataset, lees_dsyn, lokaal
from b03h.f2_metrieken import Interactie, Profiel
from b03h.f2_stock import controleer_historie, gebruiker, ranglijsten, stockcatalogus, zaai
from b03h.stock import WERK, StockServer


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsyn", required=True, type=Path)
    bron = p.parse_args().dsyn.resolve()
    volledig = lees_dsyn(bron)
    gegevens = json.loads((bron / "grondwaarheid.json").read_text())["items"]
    kind = volledig.profielen["kind"].toegang
    films = [i for i in gegevens if i["type"] == "Movie"]
    selectie = ([i for i in films if i["id"] in kind][:4] + [i for i in films if i["id"] not in kind][:2]
                + [next(i for i in gegevens if i["type"] == "Series" and i["id"] in kind)])
    ids = [i["id"] for i in selectie]
    t = volledig.profielen["kind"].splitsing
    profielen = {
        "volwassene": Profiel(t, (Interactie(ids[0], t - 2, True), Interactie(ids[-1], t - 1)), frozenset([ids[4]]), frozenset(ids)),
        "kind": Profiel(t, (Interactie(ids[1], t - 1),), frozenset([ids[2]]), frozenset(ids) & kind),
    }
    ds = Dataset("D-SYN", volledig.sha256, {k: volledig.catalogus[k] for k in ids}, profielen)
    lokaal(WERK).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=WERK, prefix="f2-route-") as werk:
        map_ = Path(werk)
        for i in selectie:
            rel = Path("Series", i["titel"]) if i["type"] == "Series" else Path("Films", f"{i['titel']} ({i['jaar']})")
            shutil.copytree(bron / rel, map_ / rel)
        mounts = {"/media/films": "Films", "/media/series": "Series"}
        with StockServer("f2-route", corpus=map_, koppelingen=mounts, werk=map_, cpus="2", gpu=False) as srv:
            srv.start()
            srv.inrichten([("Films", "movies", ["/media/films"]), ("Series", "tvshows", ["/media/series"])])
            assert srv.jf is not None
            stock = stockcatalogus(srv.jf, ds)
            terug = {v: k for k, v in stock.items()}
            for naam, profiel in profielen.items():
                kijker = gebruiker(srv.jf, naam, kind=naam == "kind")
                zaai(kijker, profiel, stock)
                controleer_historie(kijker, profiel, stock, ds)
                rijen = ranglijsten(kijker, ds, naam, stock, terug)
                if not rijen["S-RND"] or not rijen["S-LAT"]:
                    raise ValueError("lege Suggestions of Latest in de routeproef")
                if naam == "kind":
                    status, _, _ = kijker.a.ruw("GET", f"/Items/{stock[ids[4]]}/Similar", {"userId": kijker.admin_id})
                    if status != 404:
                        raise ValueError(f"verborgen bron gaf HTTP {status}")
                controleer_historie(kijker, profiel, stock, ds)
    print("Zeven corpus-ID's, twee testprofielen, vier stockroutes, 404 voor verborgen titel en gelijke kijkgegevens na teruglezen.")


if __name__ == "__main__":
    main()
