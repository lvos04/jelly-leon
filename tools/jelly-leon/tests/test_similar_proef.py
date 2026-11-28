"""De bewijsvergelijkingen van B03-031 moeten op lege of afwijkende gegevens rood worden."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import similar_webbron

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

import similar_proef as proef  # noqa: E402


class Antwoorden:
    def __init__(self, body):
        self.body = body

    def doe(self, *args):
        return self.body


def test_geen_gelijkheid_op_lege_stockresultaten():
    with pytest.raises(ValueError, match="lege voorraadgroep"):
        proef.batch(SimpleNamespace(http=Antwoorden([])))
    for rijen in ([], [{"Id": "bron"}], [{"Id": "een"}, {"Id": "twee"}]):
        with pytest.raises(ValueError, match="unieke andere treffer"):
            proef.similar(SimpleNamespace(http=Antwoorden({"Items": rijen})), "bron")


def test_similar_schema_volgt_ook_geneste_en_recursieve_verwijzingen():
    def schema(soort):
        ref = {"$ref": "#/components/schemas/BaseItemDto"}
        doc = {"paths": {"/Items/{itemId}/Similar": {"get": {"responses": {"200": ref}}}},
               "components": {"schemas": {"BaseItemDto": {"items": {"$ref": "#/components/schemas/Veld"}},
                                          "Veld": {"type": soort, "parent": ref}}}}
        return proef.schema(SimpleNamespace(http=Antwoorden(doc)))

    assert schema("string") != schema("number")


def test_kijkreferentie_weigert_ontbrekende_of_verwisselde_hervatpunten(monkeypatch):
    def kijkdata(positie):
        return {"Bron": {"Played": True, "IsFavorite": True}, "Alfa": {"Played": True},
                "Beta": {"PlaybackPositionTicks": positie}}

    data = [kijkdata(p) for p in proef.HERVATPUNTEN]
    monkeypatch.setattr(proef, "kenmerken", lambda profiel, _ids: data[profiel])
    assert proef.kijkreferentie(0, 1, {}) == data
    for posities in [(0, 0), tuple(reversed(proef.HERVATPUNTEN))]:
        data[:] = [kijkdata(p) for p in posities]
        with pytest.raises(ValueError, match="afzonderlijke hervatpunten"):
            proef.kijkreferentie(0, 1, {})


def test_alle_acht_runtimeproeven_staan_in_het_register_en_blokkeren_de_sync():
    repo = Path(__file__).resolve().parents[3]
    register = (repo / "docs/platform-v2/UPSTREAM_GEDRAG.md").read_text()
    regels = [regel for regel in register.splitlines() if regel.startswith("| UG-F2-")]
    assert len(regels) == len(proef.CHECKS) == 8
    assert {regel.rsplit("runtime:", 1)[1].split()[0] for regel in regels} == proef.CHECKS
    for dienst in [".forgejo", ".github"]:
        sync = (repo / dienst / "workflows/upstream-sync.yml").read_text()
        assert 'similar_proef.py --image "$NIEUWE_RUNTIME" --stock-image "$NIEUWE_RUNTIME"' in sync
        assert "--proef-plugin-map" in sync


def test_webanker_weigert_gewijzigde_aanroep(tmp_path):
    for pad, bron in zip(similar_webbron.ANKERS, [
        "export function loadSections(elem, apiClient, user, userSettings)",
        "homeSections.loadSections(view.querySelector('.sections'), apiClient, user, userSettings)",
        "depends = 'hometab'; import(../../../apps/legacy/controllers/${depends})",
    ], strict=True):
        doel = tmp_path / pad
        doel.parent.mkdir(parents=True)
        doel.write_text(bron, encoding="utf-8")
    assert similar_webbron.controleer(tmp_path) is None
    (tmp_path / next(iter(similar_webbron.ANKERS))).write_text("export function loadSections(elem)", encoding="utf-8")
    assert "webanker gewijzigd" in similar_webbron.controleer(tmp_path)


def test_opwarmen_wacht_op_een_koude_terugval_maar_blijft_rood_zonder_eigen_antwoord(monkeypatch):
    """Een koude eerste lezing mag terugvallen op stock (termijn 300 ms); blijft het eigen antwoord uit, dan rood."""
    ids, gemeten = {"Bron": "bron", "Alfa": "alfa"}, {}
    antwoorden = iter(["zulu", "zulu", "alfa"])
    monkeypatch.setattr(proef.time, "sleep", lambda _s: None)
    monkeypatch.setattr(proef, "similar", lambda _wie, _bron: next(antwoorden))
    proef.opwarmen(None, ids, gemeten.__setitem__, "normaal")
    assert gemeten == {"similar_koude_start_normaal": "eigen antwoord binnen de termijn na 3 poging(en)"}
    monkeypatch.setattr(proef, "similar", lambda _wie, _bron: "zulu")
    with pytest.raises(ValueError, match="herkent de gedeelde schrijvers niet"):
        proef.opwarmen(None, ids, gemeten.__setitem__, "waarnemer")
