"""ASS-recept (F5 K7, JLT-47) en het grote testbestand (≤ 20 GB via stream-copy, jury haalbaarheid A-11)."""

from __future__ import annotations

import shutil

from .basis import Context
from .ffmpeg import BITEXACT

MAX_GROOT = 20 * 1000**3
MARGE = 10 * 1000**3


def maak_ass(ctx: Context) -> None:
    """Sintel 120–180 s met het ingebedde Nederlandse spoor (dut) als ASS (-c:s ass, tekst → tekst)."""
    sintel = ctx.bron("blender/sintel/Sintel.2010.1080p.mkv")
    start, duur = float(ctx.parameters.get("start", 120.0)), float(ctx.parameters.get("duur", 60.0 if ctx.vol else 8.0))
    doel = ctx.pad("formaten/sintel-60s-ass.mkv")
    ctx.ff.ffmpeg(["-ss", f"{start:.3f}", "-t", f"{duur:.3f}", "-i", str(sintel), "-map", "0:v:0", "-map", "0:a:0",
                   "-map", "0:s:m:language:dut", "-c:v", "copy", "-c:a", "copy", "-c:s", "ass",
                   "-metadata:s:s:0", "language=dut", *BITEXACT, str(doel)])
    ctx.json("formaten/sintel-60s-ass.grondwaarheid.json", {
        "recept": "ass", "bron": "blender/sintel/Sintel.2010.1080p.mkv", "start_s": start, "duur_s": duur,
        "sporen": {"video": "h264 (copy)", "audio": "ac3 5.1 (copy)", "ondertitel": "ass (uit ingebed SRT 'dut')"},
        "verwacht": "tekstondertitel: een client die ASS extern kan tonen hoeft niet in te branden (K7); na een geleerde "
                    "terugval 0 keer ingebrand",
    })
    ctx.tel("ass")


def maak_groot(ctx: Context) -> None:
    """Groot bestand door Sintel herhaald te stream-copiëren tot de doelgrootte (standaard klein; max 20 GB)."""
    sintel = ctx.bron("blender/sintel/Sintel.2010.1080p.mkv")
    doel_bytes = int(ctx.parameters.get("doel_bytes", 4 * 1000**3 if ctx.vol else 30 * 1000**2))
    if doel_bytes > MAX_GROOT:
        raise ValueError(f"doelgrootte {doel_bytes} > 20 GB (plan: ≤ 20 GB)")
    vrij = shutil.disk_usage(ctx.uit).free
    marge = MARGE if doel_bytes >= 1000**3 else doel_bytes
    if vrij < doel_bytes + marge:
        raise ValueError(f"te weinig vrije schijfruimte: {vrij / 1e9:.1f} GB vrij, nodig {(doel_bytes + marge) / 1e9:.1f} GB "
                         "(doel + marge van 10 GB vanaf 1 GB; ontwikkelschijf is ~90 % vol)")
    bron_bytes = sintel.stat().st_size
    if doel_bytes < bron_bytes:
        # Klein doel (CI/unittest): alleen het begin van Sintel, ook via stream-copy.
        duur = max(5.0, 888.0 * doel_bytes / bron_bytes)
        doel = ctx.pad("groot/sintel-groot.mkv")
        ctx.ff.ffmpeg(["-t", f"{duur:.3f}", "-i", str(sintel), "-map", "0", "-c", "copy", *BITEXACT, str(doel)])
        herhalingen = 0
    else:
        herhalingen = -(-doel_bytes // bron_bytes)
        lijst = ctx.pad("groot/.concat.txt")
        lijst.write_text("".join(f"file '{sintel}'\n" for _ in range(herhalingen)), encoding="utf-8")
        doel = ctx.pad("groot/sintel-groot.mkv")
        ctx.ff.ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lijst), "-map", "0", "-c", "copy", *BITEXACT, str(doel)],
                      timeout=7200)
        lijst.unlink()
    ctx.json("groot/sintel-groot.grondwaarheid.json", {
        "recept": "groot-bestand", "bron": "blender/sintel/Sintel.2010.1080p.mkv", "doel_bytes": doel_bytes,
        "herhalingen": herhalingen, "werkelijk_bytes": doel.stat().st_size, "methode": "stream-copy (-c copy), geen hercodering",
        "verwacht": "bestand van remux-achtige grootte voor doorvoer/scan; de inhoud is herhaalde Sintel",
    })
    ctx.tel("groot-bestand")
