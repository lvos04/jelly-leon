"""Zet een baselinebewijs om naar een Markdown-tabel (voor BOUWVERIFICATIE_B03-016.md).

    python -m b03h rapport docs/platform-v2/test-evidence/b03-016-baseline-voormeting-12.4.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _getal(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".").replace(".", ",")


def regel(m: dict[str, Any]) -> str:
    iv = m.get("interval") or {}
    w = m.get("waarde") or {}
    if m["soort"] == "proportie":
        k = w.get("k", w.get("k_dp_effectief"))
        punt = f"{k}/{m['n']}"
        interval = f"[{_getal(iv['onder'])}; {_getal(iv['boven'])}]" if iv else "—"
        hs = w.get("herhaalsessie") or {}
        herhaling = (w.get("herhalingen_k") or []) + ([f"sessie 2: {hs['k']}"] if hs else [])
        binnen = w.get("herhaling_binnen_interval")
        if hs:
            binnen = hs.get("binnen_wilson_interval") if binnen is None else (binnen and hs.get("binnen_wilson_interval"))
    elif m["soort"] == "continu":
        punt = f"{_getal(w['gemiddelde'])} {m.get('eenheid', '')}".strip()
        interval = f"[{_getal(iv['onder'])}; {_getal(iv['boven'])}]" if iv else "—"
        herhaling = [_getal(x) for x in (w.get("herhaalsessie") or {}).get("waarden", [])] or "—"
        binnen = (w.get("herhaalsessie") or {}).get("binnen_voorspellingsinterval")
    else:
        punt = ", ".join(f"{k}={v}" for k, v in w.items() if k not in ("herhalingen", "herhaalsessie"))
        herhaald = list(w.get("herhalingen", []))
        if w.get("herhaalsessie"):
            tweede = w["herhaalsessie"]["waarde"]
            herhaald += [tweede, *tweede.get("herhalingen", [])]
        eerste = {k: v for k, v in w.items() if k not in ("herhalingen", "herhaalsessie")}
        binnen = all({k: v for k, v in h.items() if k != "herhalingen"} == eerste for h in herhaald) if herhaald else None
        interval = "—"
        herhaling = "runs + sessie 2" if w.get("herhaalsessie") else len(herhaald)
    geldig = f"{m.get('runs_geldig')}/{len(m.get('runs', []))}"
    binnen_t = {True: "ja", False: "**nee**", None: "—"}[binnen]
    return (f"| {m['id']} | {m['systeem']} | {punt} | {interval} | {m.get('gate') or '—'} | {geldig} | {herhaling} | {binnen_t} |")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="b03h rapport", description="Toon het baselinebewijs en de meetomstandigheden per metriek.")
    parser.add_argument("baseline", type=Path, help="JSON-bestand van b03h baseline")
    d = json.loads(parser.parse_args(argv).baseline.read_text(encoding="utf-8"))
    print(f"Label: **{d['label']}** · image `{d['images']['stock']}` · server {d['server']['versie']} · {d['begin']} – {d['eind']}\n")
    print("| Metriek | Systeem | Waarde (eerste meting) | 95 %-interval | Gate | Geldige runs | Herhaling(en) | Herhaling binnen interval |")
    print("|---|---|---|---|---|---|---|---|")
    for m in d["metingen"]:
        print(regel(m))
    print("\n### Meetomstandigheden\n")
    namen = {ref: naam for naam, ref in d["images"].items()}
    for ref, naam in namen.items():
        print(f"- **{naam}** gebruikt `{ref}`.")
    print("\nDe loadavg is het éénminuutsgemiddelde vóór elke run, in meetvolgorde. Een streep betekent dat de meting ontbreekt.")
    print("\n| Metriek | Systeem | Image | n | Seed | Loadavg | Loadavg herhaalsessie |")
    print("|---|---|---|---:|---|---|---|")
    for m in d["metingen"]:
        tweede = (m["waarde"].get("herhaalsessie") or {}).get("runs", [])
        eerste_last = _lastreeks(m["runs"])
        tweede_last = _lastreeks(tweede)
        seed = "geen toeval" if m["seed"] is None else m["seed"]
        print(f"| {m['id']} | {m['systeem']} | {namen.get(m['image'], m['image'])} | {m['n']} | {seed} | {eerste_last} | {tweede_last} |")
    return 0


def _lastreeks(runs: list[dict[str, Any]]) -> str:
    return " / ".join(_getal(r['last']['loadavg_voor'][0]) for r in runs) or "—"
