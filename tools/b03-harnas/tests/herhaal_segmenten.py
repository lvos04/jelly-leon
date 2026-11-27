"""Herlees hetzelfde vaste API-voorbeeld voor elk item van de bevroren set. Dit is een proef van de meetlat."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_segmenten import ITEM, Testserver

from b03h.segmentbron import lees_item
from b03h.segmenten import bevroren_set
from b03h.segmentmeting import evalueer, ticks


def herlees(items: list[dict]) -> dict:
    kandidaten, gepubliceerd = {}, {}
    for item in items:
        server = Testserver()
        server.kandidaat["duration_s"] = item["duur_s"]
        pad = item["bestand"]
        kandidaten[pad], gepubliceerd[pad] = lees_item(server, ITEM, ticks(item["duur_s"]), kandidaat=True)
    return evalueer(items, kandidaten, gepubliceerd)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("set", type=Path)
    parser.add_argument("manifest_sha256")
    a = parser.parse_args()
    items = bevroren_set(a.set, a.manifest_sha256)
    eerste = herlees(items)
    if eerste != herlees(items):
        raise ValueError("hetzelfde voorbeeld geeft verschillende cijfers")
    digest = hashlib.sha256(json.dumps(eerste, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    print(json.dumps({"soort": "vaste API-fixture", "herhalingen": 2, "items": eerste["items"], "scores_sha256": digest,
                      "n_per_type": {s: m["n"] for s, m in eerste["per_type"].items()}, "beschermd": eerste["beschermd"]["n"],
                      "n_per_deelgroep": {s: m["n"] for s, m in eerste["deelgroepen"].items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
