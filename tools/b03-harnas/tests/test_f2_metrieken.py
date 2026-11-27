import json
from pathlib import Path

import pytest

from b03h.f2_metrieken import (
    Interactie,
    Item,
    Profiel,
    beoordeel_ranglijsten,
    coverage,
    gepaard,
    geschudde_holdout,
    kandidaten,
    metrieken,
    rondgaand,
)


def film(*genres):
    return Item("Movie", frozenset(genres))


def test_handvoorbeelden_ook_voor_jl_rec_eval():
    vb = json.loads((Path(__file__).parent / "voorbeelden/f2-metrieken.json").read_text())
    cat = {item: film(*genres) for item, genres in vb["catalogus"].items()}
    gevallen = vb["gevallen"]
    for g in gevallen:
        uit = metrieken(g["top"], frozenset(g["holdout"]), cat)
        assert uit == pytest.approx({m: g[m] for m in uit}, abs=1e-12)
    assert coverage([g["top"] for g in gevallen[:2]], cat) == vb["coverage_eerste_twee"]
    assert coverage([gevallen[0]["top"]], cat) == vb["coverage_eerste"]


def test_filter_identifier_type_toegang_training_en_dubbelen_voor_afkappen():
    ids = [str(i) for i in range(16)]
    cat = {i: film() for i in ids} | {"3": Item("Episode", frozenset()), "4": Item("Series", frozenset())}
    p = Profiel(20, (Interactie("1", 19),), frozenset(["5"]), frozenset(ids[1:]))
    assert kandidaten(["onbekend", "0", "1", "2", "2", "3", *ids[4:]], cat, p) == ["2", *ids[4:13]]
    assert list(rondgaand([["a", "b"], [], ["c", "d", "e"]])) == ["a", "c", "b", "d", "e"]


@pytest.mark.parametrize("tijd", [20, 21])
def test_grens_geen_training_op_of_na_t(tijd):
    with pytest.raises(ValueError, match="op of na T"):
        Profiel(20, (Interactie("b", tijd),), frozenset(["a"]), frozenset(["a", "b"]))


def test_geen_lege_of_gelekte_holdout():
    with pytest.raises(ValueError, match="lege holdout"):
        Profiel(20, (), frozenset(), frozenset())
    with pytest.raises(ValueError, match="overlap"):
        Profiel(20, (Interactie("a", 1),), frozenset(["a"]), frozenset(["a"]))


def test_bootstrap_is_gepaard_en_schudden_heeft_geen_vaste_punten():
    p = {str(i): Profiel(10, (), frozenset([str(i)]), frozenset()) for i in range(9)}
    om = geschudde_holdout(p, 41)
    assert sorted(map(sorted, om.values())) == [[u] for u in sorted(p)]
    assert all(om[u] != p[u].holdout for u in p)
    assert om == geschudde_holdout(dict(reversed(list(p.items()))), 41)
    iv = gepaard({"a": 0.5, "b": 1.0}, {"b": 0.75, "a": 0.25}, 41)
    assert (iv.onder, iv.punt, iv.boven) == (0.25, 0.25, 0.25)
    with pytest.raises(ValueError, match="groep"):
        gepaard({"a": 1.0}, {"b": 1.0}, 1)


def test_stockselectie_over_cohort_en_lekproef_met_positieve_controle():
    cat = {u: film() for u in "abcd"}
    profielen = {u: Profiel(10, (), frozenset([u]), frozenset(cat)) for u in cat}
    andere = geschudde_holdout(profielen, 41)
    rijen = {u: {"S-REC": [], "S-SIM": [], "S-LAT": [], "S-RND": [], "POP": [],
                 "categorie/A": [u] if u in "ab" else [], "categorie/B": [u] if u in "cd" else []}
             for u in cat}
    systeem = beoordeel_ranglijsten(rijen, profielen, cat, 41)["systemen"]
    assert systeem["S-REC-best"]["NDCG@10"]["punt"] == systeem["S-BEST"]["Recall@10"]["punt"] == 0.5
    assert systeem["S-BEST"]["volledig"] is False
    assert systeem["S-REC-best"]["geschud_NDCG_verschil_met_POP"]["boven"] == 0
    # Positieve controle van de lektest: een ranglijst die de geschudde antwoorden kent, wordt gedetecteerd.
    for u in rijen:
        rijen[u]["S-SIM"] = list(andere[u])
    lek = beoordeel_ranglijsten(rijen, profielen, cat, 41)["systemen"]["S-SIM"]["geschud_NDCG_verschil_met_POP"]
    assert lek["onder"] == 1
    del rijen["a"]["S-RND"]
    with pytest.raises(ValueError, match="ontbreekt"):
        beoordeel_ranglijsten(rijen, profielen, cat, 41)
