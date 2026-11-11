"""Tests voor analyzer_proef.py (B03-017, ADR-0032): de beoordeling van de bouwlog van de proefassembly."""

from __future__ import annotations

import analyzer_proef

BRON = """using System.IO;
class X {
  void A(string p) { File.Delete(p); } // VERWACHT: JL0002
  void B(ILibraryManager l) { l.QueueLibraryScan(); } // VERWACHT: JL0001
  void C() { var s = "jellyfin.db"; } // VERWACHT: JL0003
  void D() { Process.Start("x"); } // VERWACHT: JL0004
  void E(string p) { File.Exists(p); }
}
"""


def logregel(regel: int, code: str, bestand: str = "/src/plugins/x/VerbodenAanroepen.cs") -> str:
    return f"{bestand}({regel},13): error {code}: tekst [/src/plugins/x/Proef.csproj]"


GOED = "\n".join([logregel(3, "JL0002"), logregel(4, "JL0001"), logregel(5, "JL0003"), logregel(6, "JL0004"), "Build FAILED."])


def test_markeringen_worden_per_regel_gelezen():
    assert analyzer_proef.verwachte_fouten(BRON) == {(3, "JL0002"), (4, "JL0001"), (5, "JL0003"), (6, "JL0004")}


def test_precies_de_verwachte_fouten_is_in_orde():
    assert analyzer_proef.beoordeel(BRON, GOED, exitcode=1) == []
    # MSBuild herhaalt elke fout in de samenvatting: dubbele regels tellen één keer.
    assert analyzer_proef.beoordeel(BRON, GOED + "\n" + GOED, exitcode=1) == []


def test_ontbrekende_fout_wordt_gemeld():
    log = "\n".join(r for r in GOED.splitlines() if "JL0001" not in r)
    assert analyzer_proef.beoordeel(BRON, log, exitcode=1) == ["regel 4: verwachte bouwfout JL0001 ontbreekt"]


def test_fout_op_een_toegestane_regel_wordt_gemeld():
    assert analyzer_proef.beoordeel(BRON, GOED + "\n" + logregel(7, "JL0002"), exitcode=1) == ["regel 7: onverwachte bouwfout JL0002"]


def test_verkeerde_regel_id_is_zowel_ontbrekend_als_onverwacht():
    log = GOED.replace(logregel(3, "JL0002"), logregel(3, "JL0001"))
    assert analyzer_proef.beoordeel(BRON, log, exitcode=1) == [
        "regel 3: verwachte bouwfout JL0002 ontbreekt",
        "regel 3: onverwachte bouwfout JL0001",
    ]


def test_geslaagde_build_is_een_afwijking():
    problemen = analyzer_proef.beoordeel(BRON, "Build succeeded.", exitcode=0)
    assert problemen[0] == "de build van de proefassembly is geslaagd; hij hoort te falen"
    assert len(problemen) == 5


def test_andere_bouwfout_wordt_niet_als_bewijs_geteld():
    log = GOED + "\n/src/plugins/x/VerbodenAanroepen.cs(2,1): error CS0246: type niet gevonden [/src/x.csproj]"
    assert analyzer_proef.beoordeel(BRON, log, exitcode=1) == [
        "de build faalt ook om een andere reden (CS0246); alleen de eigen regels mogen hem laten falen"
    ]
    assert analyzer_proef.beoordeel(BRON, GOED + "\nMSBUILD : error MSB1009: project ontbreekt", exitcode=1) != []


def test_jl_fout_in_een_ander_bestand_telt_niet_mee():
    log = GOED + "\n" + logregel(9, "JL0001", "/src/plugins/JellyLeon/src/Echt.cs")
    assert analyzer_proef.beoordeel(BRON, log, exitcode=1) == [
        "de build faalt ook om een andere reden (JL0001); alleen de eigen regels mogen hem laten falen"
    ]


def test_proefbron_zonder_een_regel_wordt_geweigerd():
    bron = "\n".join(r for r in BRON.splitlines() if "JL0004" not in r)
    log = "\n".join(r for r in GOED.splitlines() if "JL0004" not in r)
    assert analyzer_proef.beoordeel(bron, log, exitcode=1) == ["de proefbron bevat geen enkele verwachte fout voor JL0004"]


def test_de_echte_proefbron_dekt_elke_regel():
    bron = analyzer_proef.PROEF_BRON.read_text(encoding="utf-8")
    verwacht = analyzer_proef.verwachte_fouten(bron)
    assert len(verwacht) >= 50
    assert {code for _, code in verwacht} == set(analyzer_proef.REGELS)
    assert analyzer_proef.PROEF_PROJECT.is_file()
    # De proefassembly hoort niet in de solution: hij mag de gewone build nooit laten falen.
    solution = (analyzer_proef.REPO_ROOT / "plugins/JellyLeon.Plugins.sln").read_text(encoding="utf-8")
    assert "VerbodenProef" not in solution
