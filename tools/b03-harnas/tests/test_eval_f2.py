import json
from dataclasses import replace

import pytest

from b03h.f2_data import Dataset, Film
from b03h.f2_evaluatie import METRIEKEN, SCENARIOS, controleer_rij, opname, samenvatting, validatiewinnaar
from b03h.f2_metrieken import SEED, Interactie, Item, Profiel, geschudde_holdout
from b03h.f2_vergelijking import STOCK, buiten_interval, gate, intervallen


def dataset():
    cat = {i: Item("Movie", frozenset(["Drama"])) for i in "abcdefgh"}
    profielen = {u: Profiel(10, (Interactie("h", 5, True),), frozenset([u]), frozenset(cat) - {"g"}) for u in "abc"}
    films = {i: Film("Testfilm", item.genres, 2, 3 if i == "f" else 1, 3) for i, item in cat.items()}
    return Dataset("D-ML", "fixture", cat, profielen, films, 10)


def rij(id_):
    return [{"item": id_, "redenen": [{"code": "recently_added"}], "exploratie": False}]


def test_snapshot_zonder_antwoorden_of_toekomst_van_andere_gebruiker():
    d = dataset()
    d.profielen["b"] = replace(d.profielen["b"], splitsing=30, training=(Interactie("e", 20),))
    data = opname(d, None)
    assert "holdout" not in json.dumps(data) and "verborgen_voorkeur" not in json.dumps(data)
    p = data["profielen"][0]["profiel"]
    assert p["id"] == "a" and "g" not in p["toegang"] and p["toestand"][0]["item"] == "h"
    delers = {r["id"]: r["bekeken"] for r in p["delers"]}
    assert delers == {"b": [], "c": ["h"]}
    assert not opname(d, None, valideren=True)["profielen"][0]["profiel"]["delers"]


def test_gelekte_geschudde_ranglijst_en_toegangsgrens_worden_herkend():
    d = dataset()
    geschud = geschudde_holdout(d.profielen, SEED)
    bewust_gelekt = {u: {s: rij(next(iter(geschud[u]))) for s in SCENARIOS} for u in d.profielen}
    assert samenvatting(d, bewust_gelekt)["warm"]["geschud_min_POP"]["onder"] > 0
    with pytest.raises(ValueError, match="toegangsgefilterde"):
        controleer_rij(rij("g"), d, d.profielen["a"])
    onjuist = rij("a")
    onjuist[0]["redenen"][0]["refItemId"] = "g"
    with pytest.raises(ValueError, match="profielvreemde"):
        controleer_rij(onjuist, d, d.profielen["a"])
    del bewust_gelekt["a"]["warm"]
    with pytest.raises(ValueError, match="onvolledige"):
        samenvatting(d, bewust_gelekt)


def test_winnaar_alleen_op_validatie_met_vaste_gelijkspelregel():
    d = dataset()
    rijen = {u: {"basis": rij("f"), "inhoud": rij(u), "zaad": rij(u)} for u in d.profielen}
    assert validatiewinnaar(d, rijen)["keuze"] == "inhoud"
    for u in d.profielen:
        rijen[u]["basis"] = rij(u)
    assert validatiewinnaar(d, rijen)["keuze"] == "basis"


def test_herhaling_mist_interval_of_valt_erbuiten():
    systemen = {s: {m: {"punt": 0.45, "onder": 0.4, "boven": 0.5} for m in METRIEKEN} for s in STOCK}
    run = {"last": {"geldig": True}, "systemen": systemen}
    basis = {"dataset_sha256": "set", "image": "digest", "geldige_runs": 0, "runs": []}
    with pytest.raises(ValueError, match="geen twee"):
        intervallen(basis, "D-SYN", "set", "digest")
    eerste = intervallen(basis | {"geldige_runs": 2, "runs": [run, run]}, "D-SYN", "set", "digest")
    nieuw = json.loads(json.dumps(eerste))
    assert not buiten_interval(nieuw, eerste)
    nieuw["S-REC"]["NDCG@10"]["punt"] = 0.51
    assert buiten_interval(nieuw, eerste) == ["S-REC NDCG@10"]


def test_claim_vraagt_cohort_compleet_stock_meer_dan_pop_en_lekvrije_holdout():
    d = dataset()
    functies = {s: {m: {"punt": 0.9} for m in METRIEKEN} | {"min_aantal": 10, "geschud_min_POP": {"onder": 0}} for s in SCENARIOS}
    scores = {s: {m: {k: {"punt": 0.1, "onder": 0.05, "baseline": 0.5}
                      for k in ("stock_a", "S-BEST", "S-REC", "S-LAT", "POP")} for m in METRIEKEN} for s in SCENARIOS}
    assert gate(d, functies, scores)["M1"] == "niet aangetoond"
    d.profielen = {str(i): d.profielen["a"] for i in range(100)}
    assert gate(d, functies, scores)["M1"] == "beter dan de standaardinstelling"
    scores["warm"]["NDCG@10"]["S-TMDB"] = {"onder": 0}
    assert gate(d, functies, scores)["M1"] == "aantoonbaar beter"
    functies["warm"]["geschud_min_POP"]["onder"] = 0.001
    assert gate(d, functies, scores)["M1"] == "niet aangetoond"
    functies["warm"]["geschud_min_POP"]["onder"] = 0
    scores["warm"]["Recall@10"]["POP"]["onder"] = 0
    assert gate(d, functies, scores)["M1"] == "niet aangetoond"
    scores["koud-0-opt-in"]["NDCG@10"]["POP"]["onder"] = -0.021
    assert not gate(d, functies, scores)["M2"]["koud-0-opt-in"]
