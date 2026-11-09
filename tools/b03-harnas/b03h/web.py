"""Brug naar het Node/Playwright-harnas (playwright/harnas.mjs)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

WEB = Path(__file__).resolve().parents[1] / "playwright"
UA = {
    "webos": "Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.211 Safari/537.36 "
             "WebAppManager",
    "tizen": "Mozilla/5.0 (SMART-TV; LINUX; Tizen 8.0) AppleWebKit/537.36 (KHTML, like Gecko) 120.0.6099.5/8.0 TV Safari/537.36",
}


class WebFout(RuntimeError):
    pass


def harnas(opdracht: str, cfg: dict[str, Any], timeout: float = 1800, pogingen: int = 2) -> dict[str, Any]:
    """Draait het Playwright-harnas; een fout vóór het eerste item (inloggen) wordt één keer opnieuw geprobeerd."""
    for poging in range(pogingen):
        try:
            return _harnas(opdracht, cfg, timeout)
        except WebFout:
            if poging == pogingen - 1:
                raise
    raise AssertionError("onbereikbaar")


def _harnas(opdracht: str, cfg: dict[str, Any], timeout: float) -> dict[str, Any]:
    if not (WEB / "node_modules" / "playwright").exists():
        raise WebFout(f"Playwright ontbreekt: draai eerst `npm ci` in {WEB}")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cfg, f)
        pad = f.name
    try:
        uit = subprocess.run(["node", str(WEB / "harnas.mjs"), opdracht, pad], capture_output=True, text=True,
                             timeout=timeout, cwd=WEB, env={**os.environ, "NODE_NO_WARNINGS": "1"}, check=False)
    finally:
        os.unlink(pad)
    regels = [r for r in uit.stdout.splitlines() if r.startswith("{")]
    if not regels:
        raise WebFout(f"harnas gaf geen JSON (exit {uit.returncode}): {uit.stderr[-600:]}")
    data = json.loads(regels[-1])
    if data.get("fout") and not data.get("items"):
        raise WebFout(f"harnas faalde: {data['fout']}")
    return data
