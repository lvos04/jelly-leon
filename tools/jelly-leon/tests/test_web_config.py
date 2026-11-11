"""Tests voor de generator van de web-config.json van de image (B03-017, deploy/allinone/web-config.mjs).

De generator draait in de web-bouwstap van de image (Node). Deze tests roepen hem echt aan; zonder Node op de
machine worden ze overgeslagen (de CI-runner heeft Node).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
GENERATOR = REPO / "deploy/allinone/web-config.mjs"
EIGEN = REPO / "deploy/allinone/web-config.jellyleon.json"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node niet beschikbaar op deze machine")

UPSTREAM = {
    "includeCorsCredentials": False,
    "multiserver": False,
    "themes": [{"name": "Dark", "id": "dark", "color": "#202020", "default": True}],
    "menuLinks": [],
    "servers": [],
    "plugins": ["playAccessValidation/plugin", "htmlVideoPlayer/plugin", "syncPlay/plugin"],
}


class Proef:
    def __init__(self, tmp: Path, eigen: dict | None = None, *, upstream: dict | None = None):
        self.src = tmp / "src"
        (self.src / "plugins/jellyLeon/watchTogether").mkdir(parents=True)
        (self.src / "plugins/jellyLeon/watchTogether/plugin.ts").write_text("export default class {}\n", encoding="utf-8")
        self.upstream = self.src / "config.json"
        # Bewust een eigen opmaak (4 spaties, geen slotregel): byte-gelijkheid moet echt van upstream komen.
        self.upstream.write_text(json.dumps(upstream or UPSTREAM, indent=4), encoding="utf-8")
        self.eigen = tmp / "eigen.json"
        self.eigen.write_text(json.dumps(eigen if eigen is not None else {"plugins": []}), encoding="utf-8")
        self.uit = tmp / "dist-config.json"

    def draai(self, *extra: str) -> subprocess.CompletedProcess[str]:
        opdracht = [NODE, str(GENERATOR), "--upstream", str(self.upstream), "--eigen", str(self.eigen)]
        opdracht += ["--plugins-map", str(self.src / "plugins"), "--uit", str(self.uit), *extra]
        return subprocess.run(opdracht, capture_output=True, text=True, check=False)


def test_zonder_eigen_plugins_is_het_resultaat_byte_gelijk_aan_upstream(tmp_path):
    proef = Proef(tmp_path)
    uitkomst = proef.draai()
    assert uitkomst.returncode == 0, uitkomst.stderr
    assert proef.uit.read_bytes() == proef.upstream.read_bytes()
    assert "3 upstream-plugins, 0 van Jelly Leon" in uitkomst.stdout
    assert proef.draai("--controleer").returncode == 0


def test_eigen_plugin_komt_achteraan_en_upstream_blijft_volledig(tmp_path):
    proef = Proef(tmp_path, {"plugins": ["jellyLeon/watchTogether/plugin"]})
    uitkomst = proef.draai()
    assert uitkomst.returncode == 0, uitkomst.stderr
    resultaat = json.loads(proef.uit.read_text(encoding="utf-8"))
    assert resultaat["plugins"] == [*UPSTREAM["plugins"], "jellyLeon/watchTogether/plugin"]
    assert {k: v for k, v in resultaat.items() if k != "plugins"} == {k: v for k, v in UPSTREAM.items() if k != "plugins"}
    assert proef.draai("--controleer").returncode == 0


def test_controle_meldt_een_ontbrekende_upstream_plugin(tmp_path):
    proef = Proef(tmp_path, {"plugins": ["jellyLeon/watchTogether/plugin"]})
    assert proef.draai().returncode == 0
    resultaat = json.loads(proef.uit.read_text(encoding="utf-8"))
    resultaat["plugins"].remove("syncPlay/plugin")
    proef.uit.write_text(json.dumps(resultaat), encoding="utf-8")
    uitkomst = proef.draai("--controleer")
    assert uitkomst.returncode == 1
    assert "upstream-plugin ontbreekt: syncPlay/plugin" in uitkomst.stderr


@pytest.mark.parametrize(
    ("wijziging", "melding"),
    [
        (lambda r: r["plugins"].reverse(), "volgorde van de upstream-plugins is gewijzigd"),
        (lambda r: r["plugins"].append("vreemd/plugin"), "onbekende plugin in het resultaat: vreemd/plugin"),
        (lambda r: r.update(multiserver=True), 'sleutel "multiserver" wijkt af van upstream'),
        (lambda r: r.update(extra=1), 'sleutel "extra" wijkt af van upstream'),
        (lambda r: r.pop("themes"), 'sleutel "themes" wijkt af van upstream'),
    ],
)
def test_controle_meldt_elke_afwijking_van_upstream(tmp_path, wijziging, melding):
    proef = Proef(tmp_path)
    assert proef.draai().returncode == 0
    resultaat = json.loads(proef.uit.read_text(encoding="utf-8"))
    wijziging(resultaat)
    proef.uit.write_text(json.dumps(resultaat, indent=4), encoding="utf-8")
    uitkomst = proef.draai("--controleer")
    assert uitkomst.returncode == 1
    assert melding in uitkomst.stderr


def test_controle_eist_byte_gelijkheid_zonder_eigen_plugins(tmp_path):
    proef = Proef(tmp_path)
    assert proef.draai().returncode == 0
    proef.uit.write_text(json.dumps(UPSTREAM, indent=2), encoding="utf-8")
    uitkomst = proef.draai("--controleer")
    assert uitkomst.returncode == 1
    assert "byte-gelijk aan upstream" in uitkomst.stderr


@pytest.mark.parametrize(
    ("eigen", "melding"),
    [
        ({"plugins": ["watchTogether/plugin"]}, "hoort de vorm jellyLeon/<naam>/plugin te hebben"),
        ({"plugins": ["jellyLeon/../syncPlay/plugin"]}, "hoort de vorm jellyLeon/<naam>/plugin te hebben"),
        ({"plugins": ["jellyLeon/bestaatNiet/plugin"]}, "heeft geen bronbestand onder"),
        ({"plugins": ["jellyLeon/watchTogether/plugin", "jellyLeon/watchTogether/plugin"]}, "lijst van unieke namen"),
        ({"plugins": [], "themes": []}, 'eigen sleutel "themes" is niet toegestaan'),
        ({"plugins": [], "servers": ["http://voorbeeld.invalid"]}, 'eigen sleutel "servers" is niet toegestaan'),
        ({}, "lijst van unieke namen"),
        ([], "moet een JSON-object zijn"),
    ],
)
def test_ongeldige_eigen_items_schrijven_niets(tmp_path, eigen, melding):
    proef = Proef(tmp_path, eigen)
    uitkomst = proef.draai()
    assert uitkomst.returncode == 1
    assert melding in uitkomst.stderr
    assert not proef.uit.exists()


def test_upstream_zonder_plugins_wordt_geweigerd(tmp_path):
    proef = Proef(tmp_path, upstream={"plugins": []})
    uitkomst = proef.draai()
    assert uitkomst.returncode == 1
    assert 'heeft geen "plugins"-lijst' in uitkomst.stderr
    assert not proef.uit.exists()


def test_onbekend_argument_is_een_gebruiksfout(tmp_path):
    proef = Proef(tmp_path)
    assert proef.draai("--onbekend").returncode == 3


def test_eigen_items_van_de_repo_zijn_geldig_en_in_golf_1_leeg(tmp_path):
    eigen = json.loads(EIGEN.read_text(encoding="utf-8"))
    assert set(eigen) == {"_toelichting", "plugins"}
    # Golf 1 levert nog geen webplugin: de config.json van de image blijft byte-gelijk aan upstream.
    assert eigen["plugins"] == []
    proef = Proef(tmp_path, eigen)
    assert proef.draai().returncode == 0
    assert proef.uit.read_bytes() == proef.upstream.read_bytes()


def test_de_image_bouwt_de_config_met_de_generator():
    dockerfile = (REPO / "deploy/allinone/Dockerfile").read_text(encoding="utf-8")
    assert "web-config.mjs" in dockerfile
    assert "--controleer" in dockerfile
