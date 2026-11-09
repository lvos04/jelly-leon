"""Zet een baselinebewijs om naar een Markdown-tabel (voor BOUWVERIFICATIE_B03-016.md).

    python -m b03h rapport docs/platform-v2/test-evidence/b03-016-baseline-voormeting-12.4.json
"""

from __future__ import annotations

import json
import sys
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
        herhaling = w.get("herhalingen_k", w.get("herhalingen"))
        binnen = w.get("herhaling_binnen_interval")
    elif m["soort"] == "continu":
        punt = f"{_getal(w['gemiddelde'])} {m.get('eenheid', '')}".strip()
        interval = f"[{_getal(iv['onder'])}; {_getal(iv['boven'])}]" if iv else "—"
        herhaling = [_getal(x) for x in w.get("waarden", [])]
        binnen = w.get("herhaling_binnen_interval_eerste_runs")
    else:
        punt = ", ".join(f"{k}={v}" for k, v in w.items() if k != "herhalingen")
        interval, herhaling, binnen = "—", "zie runs", None
    geldig = f"{m.get('runs_geldig')}/{len(m.get('runs', []))}"
    binnen_t = {True: "ja", False: "**nee**", None: "—"}[binnen]
    return (f"| {m['id']} | {m['systeem']} | {punt} | {interval} | {m.get('gate') or '—'} | {geldig} | {herhaling} | {binnen_t} |")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("gebruik: python -m b03h rapport <baseline.json>", file=sys.stderr)
        return 2
    d = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    print(f"Label: **{d['label']}** · image `{d['images']['stock']}` · server {d['server']['versie']} · {d['begin']} – {d['eind']}\n")
    print("| Metriek | Systeem | Waarde (eerste meting) | 95 %-interval | Gate | Geldige runs | Herhalingen | Herhaling binnen interval |")
    print("|---|---|---|---|---|---|---|---|")
    for m in d["metingen"]:
        print(regel(m))
    return 0
