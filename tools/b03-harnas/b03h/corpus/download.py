"""Downloaden voor het corpus: altijd naar een tijdelijk bestand, sha256 controleren, dan atomair hernoemen.

Les uit analyse 5 §5.2: twee schrijvers op hetzelfde doelbestand leverden een corrupte 4K-HDR10-clip op. Daarom houdt
elke download een exclusief slot op ``<doel>.lock`` vast, schrijft hij naar ``.<naam>.deel-<pid>`` in dezelfde map en
wordt het doel pas na een kloppende sha256 met ``os.replace`` neergezet. download.blender.org geeft bij parallelle
verzoeken HTTP 429 met ``Retry-After``; dat wordt gerespecteerd.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .manifest import sha256_bestand


class DownloadFout(RuntimeError):
    pass


def download(url: str, doel: Path, sha256: str | None, *, pogingen: int = 4, timeout: float = 60.0,
             wacht: float = 2.0) -> str:
    """Haalt url op naar doel. Bestaat doel al met de juiste sha256, dan gebeurt er niets.

    Zonder verwachte sha256 wordt alleen de gemeten sha256 teruggegeven (eerste opname in een manifest).
    """
    if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise DownloadFout(f"alleen https (of een lokaal testadres): {url}")
    doel.parent.mkdir(parents=True, exist_ok=True)
    slot = os.open(doel.with_name(doel.name + ".lock"), os.O_RDWR | os.O_CREAT, 0o664)
    try:
        fcntl.flock(slot, fcntl.LOCK_EX)
        if doel.exists() and sha256 and sha256_bestand(doel) == sha256:
            return sha256
        laatste: Exception | None = None
        for poging in range(pogingen):
            tijdelijk = doel.with_name(f".{doel.name}.deel-{os.getpid()}")
            try:
                gemeten = _haal(url, tijdelijk, timeout)
                if sha256 and gemeten != sha256:
                    raise DownloadFout(f"sha256 {gemeten} ≠ verwacht {sha256} ({url})")
                os.replace(tijdelijk, doel)  # atomair binnen dezelfde map
                return gemeten
            except urllib.error.HTTPError as fout:
                laatste = fout
                na = fout.headers.get("Retry-After") if fout.headers else None
                time.sleep(float(na) if na and na.isdigit() else wacht * (2 ** poging))
            except (urllib.error.URLError, OSError, DownloadFout) as fout:
                laatste = fout
                time.sleep(wacht * (2 ** poging))
            finally:
                tijdelijk.unlink(missing_ok=True)
        raise DownloadFout(f"download mislukt na {pogingen} pogingen: {laatste}")
    finally:
        fcntl.flock(slot, fcntl.LOCK_UN)
        os.close(slot)


def _haal(url: str, tijdelijk: Path, timeout: float) -> str:
    h = hashlib.sha256()
    verzoek = urllib.request.Request(url, headers={"User-Agent": "jelly-leon-b03-016-corpus/1"})  # noqa: S310
    with urllib.request.urlopen(verzoek, timeout=timeout) as antwoord, open(tijdelijk, "wb") as uit:  # noqa: S310
        while blok := antwoord.read(1 << 20):
            h.update(blok)
            uit.write(blok)
        uit.flush()
        os.fsync(uit.fileno())
    return h.hexdigest()
