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
        gelijk = all({k: v for k, v in h.items() if k != "herhalingen"} == {k: v for k, v in w.items() if k not in (
            "herhalingen", "herhaalsessie")} for h in w.get("herhalingen", []) + ([w["herhaalsessie"]["waarde"]]
                                                                            if w.get("herhaalsessie") else []))
        interval, herhaling, binnen = "—", "runs + sessie 2" if w.get("herhaalsessie") else "runs", gelijk
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
    print("| Metriek | Systeem | Waarde (eerste meting) | 95 %-interval | Gate | Geldige runs | Herhaling(en) | Herhaling binnen interval |")
    print("|---|---|---|---|---|---|---|---|")
    for m in d["metingen"]:
        print(regel(m))
    return 0
