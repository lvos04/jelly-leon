"""Tests voor de configuratiepagina van de plugin in Node (S-G1-17 herstelronde 9, R-HARDE-EIS-18, ADR-0032).

De pagina draait in de browser van de beheerder, met zijn token. Deze tests voeren de echte code van de pagina uit met een
nep-ApiClient en een nep-DOM: (1) alle knoppen en het laden vragen alleen eigen paden van Jelly Leon; (2) vraag() weigert
elk ander pad en elke andere methode vóór er een verzoek vertrekt (fail-closed). Zonder Node op de machine worden ze
overgeslagen (de CI-runner heeft Node). De statische controle van elke ingebedde webbron staat in
plugins/JellyLeon/tests/…/Core/BrowserTussenpersoonTests.cs.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PAGINA = REPO / "plugins/JellyLeon/src/Jellyfin.Plugin.JellyLeon/Configuration/configPage.html"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node niet beschikbaar op deze machine")

NEP = r"""
const vm = require('vm');
const invoer = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const verzoeken = [];
const koppen = {};
const ApiClient = {
  getUrl(pad) { return 'http://server/' + pad; },
  fetch(o) {
    verzoeken.push(o.type + ' ' + o.url);
    koppen[o.type + ' ' + o.url] = o.headers;
    const json = o.url.endsWith('/media/v1/modules')
      ? { items: invoer.modules || [{ slug: 'devices', naam: 'Apparaten', enabled: false }] }
      : o.url.endsWith('/watch/capabilities') ? invoer.watch
      : (invoer.hubstatus || { status: 'linked', fingerprint: 'ab', items: [] });
    return Promise.resolve({ text: () => Promise.resolve(JSON.stringify(json)), headers: { get: () => '"e1"' } });
  },
};
function element() {
  const e = { value: '{}', textContent: '', checked: false, style: {}, handlers: {}, kinderen: [] };
  e.addEventListener = (type, fn) => { e.handlers[type] = fn; };
  e.appendChild = (k) => { e.kinderen.push(k); };
  e.setAttribute = () => {};
  e.querySelector = (sel) => elementen[sel] || (elementen[sel] = element());
  return e;
}
const elementen = {};
const gemaakt = [];
const document = {
  querySelector: (sel) => elementen[sel] || (elementen[sel] = element()),
  createElement: () => { const e = element(); gemaakt.push(e); return e; },
};
const window = { crypto: globalThis.crypto };
const context = vm.createContext({ ApiClient, document, window, Promise, JSON, Uint8Array, Array, Error });
const wacht = () => new Promise((r) => setImmediate(r));
(async () => {
  if (invoer.modus === 'pagina') {
    vm.runInContext(invoer.script, context);
    const pagina = elementen['#JellyLeonConfigPage'];
    pagina.handlers.pageshow();
    await wacht(); await wacht();
    const hubstatus = pagina.querySelector('#jlHubStatus').textContent;
    if (invoer.watch) {
      const melding = pagina.querySelector('#jlWatchStatus');
      const verborgen = pagina.querySelector('#jlWatch').hidden;
      console.log(JSON.stringify({ tekst: melding.textContent, kleur: melding.style.color, verborgen }));
      return;
    }
    for (const knop of ['#jlBereken', '#jlKoppel', '#jlOntkoppel']) { pagina.querySelector(knop).handlers.click(); }
    for (const e of gemaakt) { if (e.handlers.change) { e.checked = true; e.handlers.change(); } }
    await wacht(); await wacht();
    console.log(JSON.stringify({ verzoeken, koppen, hubstatus }));
  } else {
    vm.runInContext(invoer.script + '\nthis.vraag = vraag;', context);
    const uit = [];
    for (const [methode, pad] of invoer.gevallen) {
      const voor = verzoeken.length;
      let geweigerd = false;
      try { context.vraag(methode, pad); } catch (e) { geweigerd = true; }
      uit.push({ methode, pad, geweigerd, verzoeken: verzoeken.length - voor });
    }
    console.log(JSON.stringify({ uit }));
  }
})();
"""


def script() -> str:
    tekst = PAGINA.read_text(encoding="utf-8")
    blokken = re.findall(r"<script[^>]*>(.*?)</script>", tekst, flags=re.S)
    assert len(blokken) == 1, "de pagina hoort precies één inline script te hebben"
    return blokken[0]


def vraag_deel(bron: str) -> str:
    """EIGEN_PAD, METHODEN, uuid() en vraag() uit de pagina, letterlijk (zonder de rest van de IIFE)."""
    stukken = []
    for begin in ("var EIGEN_PAD", "var METHODEN", "function uuid(", "function vraag("):
        i = bron.index(begin)
        if begin.startswith("var"):
            stukken.append(bron[i : bron.index(";\n", i) + 1])
            continue
        diepte = 0
        for j in range(bron.index("{", i), len(bron)):
            diepte += {"{": 1, "}": -1}.get(bron[j], 0)
            if diepte == 0:
                stukken.append(bron[i : j + 1])
                break
    return "\n".join(stukken)


def draai(invoer: dict) -> dict:
    uitkomst = subprocess.run(
        [NODE, "-e", NEP], input=json.dumps(invoer), capture_output=True, text=True, check=False, timeout=60
    )
    assert uitkomst.returncode == 0, uitkomst.stderr
    return json.loads(uitkomst.stdout.strip().splitlines()[-1])


def test_de_pagina_vraagt_alleen_eigen_paden():
    verzoeken = draai({"modus": "pagina", "script": script()})["verzoeken"]
    assert sorted(set(verzoeken)) == [
        "DELETE http://server/media/v1/hub-link",
        "GET http://server/media/v1/hub-link",
        "GET http://server/media/v1/modules",
        "POST http://server/media/v1/hub-link/verify",
        "PUT http://server/media/v1/hub-link",
        "PUT http://server/media/v1/modules/devices",
    ]


def test_hubbeheer_toont_onleesbare_pin_en_gebruikt_de_verplichte_koppen():
    uit = draai({"modus": "pagina", "script": script(), "hubstatus": {"status": "not_linked", "reason": "koppelstatus_onleesbaar"}})
    assert "onleesbaar" in uit["hubstatus"]
    koppen = uit["koppen"]
    assert "Idempotency-Key" not in koppen["POST http://server/media/v1/hub-link/verify"]
    for methode in ("PUT", "DELETE"):
        assert len(koppen[f"{methode} http://server/media/v1/hub-link"]["Idempotency-Key"]) == 36
    assert koppen["PUT http://server/media/v1/modules/devices"]["If-Match"] == '"e1"'


def test_watch_toont_rode_melding_bij_uitval_met_gasten():
    zichtbaar = draai({"modus": "pagina", "script": script(), "modules": [{"slug": "watch", "naam": "Watch Together", "enabled": True}],
                       "watch": {"decorator_active": False, "health": "down"}})
    assert zichtbaar["verborgen"] is False
    assert zichtbaar["kleur"] == "#ff6868"
    assert "gasten en kinderen" in zichtbaar["tekst"] and "SyncPlayAccess = Geen" in zichtbaar["tekst"]


GOED = [
    ("GET", "media/v1/hub-link"),
    ("POST", "media/v1/hub-link/verify"),
    ("PUT", "media/v1/modules/devices"),
    ("DELETE", "connector/v1/propose"),
]

FOUT = [
    ("DELETE", "UserPlayedItems/bibliotheek-A"),
    ("GET", "Items"),
    ("DELETE", "/media/v1/hub-link"),
    ("DELETE", "media/v1/../UserPlayedItems/x"),
    ("DELETE", "media/v1/%2e%2e/UserPlayedItems/x"),
    ("DELETE", "media/v1\\..\\UserPlayedItems"),
    ("GET", "media/v1/x?userId=y"),
    ("GET", "media/v1/x#y"),
    ("GET", "media/v1/x\n"),
    ("GET", "media/v1/"),
    ("GET", "http://elders/media/v1/x"),
    ("GET", "//elders/media/v1/x"),
    ("GET", None),
    ("PATCH", "media/v1/hub-link"),
    ("delete", "media/v1/hub-link"),
]


def test_vraag_weigert_elk_ander_pad_voor_er_een_verzoek_vertrekt():
    uit = draai({"modus": "vraag", "script": vraag_deel(script()), "gevallen": GOED + FOUT})["uit"]
    assert [(u["methode"], u["pad"], u["geweigerd"], u["verzoeken"]) for u in uit] == [
        (m, p, False, 1) for m, p in GOED
    ] + [(m, p, True, 0) for m, p in FOUT]
