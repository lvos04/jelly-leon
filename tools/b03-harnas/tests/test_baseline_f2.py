import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from b03h import baseline_f2 as f2
from b03h import bewijs, f2_stock, meetslot
from b03h.f2_data import Dataset, utc
from b03h.f2_metrieken import Interactie, Item, Profiel, kandidaten
from b03h.statistiek import Interval


@pytest.fixture
def proefset():
    cat = {k: Item("Movie", frozenset(["Drama"])) for k in "abcdefgh"}
    profielen = {
        "eerste": Profiel(10, tuple(Interactie(k, i, i == 2) for i, k in enumerate("abcd", 1)), frozenset(["e"]), frozenset(cat)),
        "tweede": Profiel(25, (Interactie("h", 20),), frozenset(["a"]), frozenset(cat)),
    }
    return Dataset("D-SYN", "synthetisch", cat, profielen)


class StockRoutes:
    def __init__(self, naam, dataset, ids):
        self.admin_id, self.dataset, self.ids = naam, dataset, ids
        self.a = self
        self.geschiedenis, self.favorieten, self.aanroepen = {}, set(), []

    def items(self, _):
        return [{"Id": i, "UserData": {"Played": i in self.geschiedenis, "LastPlayedDate": self.geschiedenis.get(i),
                                       "IsFavorite": i in self.favorieten}} for i in self.ids.values()]

    def doe(self, methode, pad, query):
        assert query["userId"] == self.admin_id
        self.aanroepen.append((methode, pad))
        if methode == "POST":
            item = pad.rsplit("/", 1)[-1]
            if pad.startswith("/UserPlayedItems/"):
                self.geschiedenis[item] = query["datePlayed"]
            else:
                assert pad.startswith("/UserFavoriteItems/")
                self.favorieten.add(item)
            return {}
        rijen = [{"Id": self.ids[k]} for k in "abcdefg"]
        if pad == "/Movies/Recommendations":
            return [{"RecommendationType": "SimilarToRecentlyPlayed", "Items": rijen[1:4]},
                    {"RecommendationType": "SimilarToLikedItem", "Items": rijen[4:]}]
        if pad == "/Items/Latest":
            return rijen[::-1]
        if pad.endswith("/Similar") or pad == "/Items/Suggestions":
            return {"Items": rijen}
        raise AssertionError(pad)


def test_stockroutes_twee_runs_op_dezelfde_historie(monkeypatch, proefset):
    ids = {k: "server-" + k for k in proefset.catalogus}
    kijkers = {u: StockRoutes(u, proefset, ids) for u in proefset.profielen}
    monkeypatch.setattr(f2, "gebruiker", lambda _, u, **kw: kijkers[u])
    monkeypatch.setattr(meetslot, "loadavg", lambda: (1.0, 0.0, 0.0))

    @contextmanager
    def meet(_, nr, __):
        yield meetslot.RunLast("test", nr, "test")

    monkeypatch.setattr(meetslot, "run", meet)
    uit = f2.twee_runs(None, proefset, ids, "eigen-test")
    assert uit["geldige_runs"] == 2
    assert uit["geverifieerde_trainingsitems"] == {"voor": 5, "na": 5}
    assert uit["absoluut_verschil_runs"]["S-SIM"]["NDCG@10"] == 0
    eerste = kijkers["eerste"]
    assert eerste.favorieten == {"server-b"}
    assert eerste.geschiedenis["server-d"] == utc(4)
    sim = [pad for _, pad in eerste.aanroepen if pad.endswith("/Similar")]
    assert sim == [f"/Items/server-{k}/Similar" for k in "dcbdcb"]
    rijen = f2_stock.ranglijsten(eerste, proefset, "eerste", ids, {v: k for k, v in ids.items()})
    assert rijen["S-REC"] == list("becfdg")
    assert rijen["categorie/SimilarToLikedItem"] == list("efg")
    assert kandidaten(rijen["S-REC"], proefset.catalogus, proefset.profielen["eerste"]) == list("efg")
    assert proefset.pop("eerste") == list("abcdefgh")
    assert proefset.pop("tweede") == list("abcdhefg")
    eerste.geschiedenis["server-a"] = utc(6)
    with pytest.raises(ValueError, match="speeldatum"):
        f2_stock.controleer_historie(eerste, proefset.profielen["eerste"], ids, proefset)


def test_scan_moet_volledig_uniek_en_met_dezelfde_metadata_zijn(proefset):
    rijen = [{"Id": "jf-" + k, "ProviderIds": {"Dsyn": k}, "Type": "Movie", "Genres": ["Drama"]} for k in proefset.catalogus]
    api = SimpleNamespace(items=lambda _: rijen)
    assert f2_stock.stockcatalogus(api, proefset)["g"] == "jf-g"
    rijen.append(rijen[0])
    with pytest.raises(ValueError, match="dubbel"):
        f2_stock.stockcatalogus(api, proefset)
    rijen.pop()
    rijen.pop()
    with pytest.raises(ValueError, match="onvolledig"):
        f2_stock.stockcatalogus(api, proefset)
    rijen[0]["Genres"] = []
    with pytest.raises(ValueError, match="genres"):
        f2_stock.stockcatalogus(api, proefset)


def test_geen_zaaiactie_voor_verborgen_item(proefset):
    ids = {k: k for k in proefset.catalogus}
    api = StockRoutes("eerste", proefset, ids)
    p = Profiel(20, (Interactie("a", 1), Interactie("b", 2)), frozenset(["c"]), frozenset("ac"))
    with pytest.raises(ValueError, match="toegang"):
        f2_stock.zaai(api, p, ids)
    assert api.aanroepen == []


def test_afwezig_afgekeurd_en_volledig_basisbewijs(tmp_path):
    pad = tmp_path / "basis.json"
    assert len(f2.voorwaarde(pad, 8)) == 2
    f2.schrijf(pad, {"aangevraagd_label": "definitief-forkbasis", "pogingen": []})
    assert f2.voorwaarde(pad, 1)
    records = [bewijs.metriek(id="voorbeeld", functie="F2", omschrijving="test", methode="telling", systeem=s,
                              soort="proportie", image=f2.STOCK_IMAGE, seed=1,
                              runs=[{"last": {"geldig": True, "loadavg_voor": [1, 1, 1]}} for _ in range(3)],
                              waarde={"k": 3}, interval=Interval(1, 0.5, 1, "test"), n=3) for s in ("stock-standaard", "stock-best")]
    doc = {"schema": bewijs.SCHEMA, "label": "definitief-forkbasis", "images": {"stock": f2.STOCK_IMAGE}, "metingen": records}
    f2.schrijf(pad, doc)
    assert f2.voorwaarde(pad, 4.0) == []
    assert f2.voorwaarde(pad, 4.01)
    records[0]["runs"][0]["last"]["geldig"] = False
    f2.schrijf(pad, doc)
    assert f2.voorwaarde(pad, 1)
    doc["metingen"] = []
    f2.schrijf(pad, doc)
    assert f2.voorwaarde(pad, 1)


def test_cli_slaat_geweigerde_meting_op_zonder_server(monkeypatch, tmp_path, proefset):
    monkeypatch.setattr(f2, "lees_dsyn", lambda _: proefset)
    monkeypatch.setattr(meetslot, "exclusief_slot", lambda: pytest.fail("geen slot of server bij ontbrekende baseline"))
    uit = tmp_path / "poging.json"
    assert f2.main(["meet", "--basis", str(tmp_path / "ontbreekt"), "--dsyn", str(tmp_path), "--uit", str(uit)]) == 3
    doc = json.loads(uit.read_text())
    assert doc["status"] == f2.NIET_GEMETEN and doc["geldige_runs"] == 0
    assert doc["image"] == f2.STOCK_IMAGE and doc["broncontroles"]["B11"]["vereist_selectie"]
    assert "runs" not in doc and "scan_s" not in doc


def test_opruimen_na_mislukte_serverstart(monkeypatch, tmp_path, proefset):
    class MislukteServer(f2.StockServer):
        def start(self, schoon=True):
            self.map.mkdir(parents=True)
            raise RuntimeError("gesimuleerde startfout")

    monkeypatch.setattr(f2, "StockServer", MislukteServer)
    werk = tmp_path / "werk"
    with pytest.raises(RuntimeError, match="gesimuleerde startfout"):
        f2.stockproef(proefset, tmp_path, werk)
    assert list(werk.iterdir()) == []
