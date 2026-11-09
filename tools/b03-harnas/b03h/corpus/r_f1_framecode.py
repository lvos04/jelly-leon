"""F1 — framecode-raster (B03 2.0 F1.9.3, J-TEST H-ALG-5/K-ALG-12).

Per frame 16 zwart/wit-blokken bovenin (binair framenummer, bit 0 links) plus een tijdcode onderin; het beeld van
``hero.mp4`` staat ertussen. Zo is de afspeelpositie ook af te lezen bij clients zonder DOM-toegang (emulator, desktop):
screenshot → blokken → framenummer → tijd. De grondwaarheid legt geometrie, fps en decodeerregel vast.
"""

from __future__ import annotations

from .basis import Context
from .ffmpeg import BITEXACT, FONT

BLOKKEN, BLOK_B, STRIP_H, STRIP_Y = 16, 80, 64, 14
BREEDTE, HOOGTE, BEELD_H = 1280, 720, 536
FPS_NUM, FPS_DEN = 24000, 1001


def maak(ctx: Context) -> None:
    hero = ctx.bron("blender/hero/hero.mp4")
    duur = float(ctx.parameters.get("duur", 236.0 if ctx.vol else 4.0))
    start = float(ctx.parameters.get("start", 0.0))
    rate = f"{FPS_NUM}/{FPS_DEN}"
    marge = (HOOGTE - BEELD_H) // 2
    code = (f"color=c=black:s={BREEDTE}x{STRIP_H}:r={rate}:d={duur:.3f},"
            f"geq=lum='if(lt(mod(X\\,{BLOK_B})\\,{BLOK_B - 8})*gt(Y\\,6)*lt(Y\\,{STRIP_H - 6})\\,"
            f"255*mod(floor(N/pow(2\\,floor(X/{BLOK_B})))\\,2)\\,0)':cb=128:cr=128,format=yuv420p[code]")
    tekst = (f"drawtext=fontfile={FONT}:text='%{{pts\\:hms}}  frame %{{frame_num}}':fontcolor=white:fontsize=28:"
             f"x=20:y={HOOGTE - marge + 30}")
    beeld = (f"[0:v]fps={rate},scale={BREEDTE}:{BEELD_H},setsar=1,pad={BREEDTE}:{HOOGTE}:0:{marge}:black,"
             f"format=yuv420p,trim=duration={duur:.3f},setpts=PTS-STARTPTS[b]")
    doel = ctx.pad("sync/hero-framecode.mkv")
    ctx.ff.ffmpeg(["-ss", f"{start:.3f}", "-i", str(hero), "-filter_complex",
                   f"{beeld};{code};[b][code]overlay=0:{STRIP_Y}:eof_action=endall,{tekst}[v];"
                   f"[0:a]atrim=duration={duur:.3f},asetpts=PTS-STARTPTS[a]",
                   "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                   "-g", "24", "-c:a", "aac", "-b:a", "128k", *BITEXACT, str(doel)])
    frames = round(duur * FPS_NUM / FPS_DEN)
    ctx.json("sync/hero-framecode.grondwaarheid.json", {
        "recept": "f1-framecode", "bron": "blender/hero/hero.mp4", "bron_start_s": start, "duur_s": duur,
        "fps": {"teller": FPS_NUM, "noemer": FPS_DEN}, "frames_ongeveer": frames, "resolutie": [BREEDTE, HOOGTE],
        "raster": {"blokken": BLOKKEN, "blok_breedte": BLOK_B, "y_boven": STRIP_Y + 6, "y_onder": STRIP_Y + STRIP_H - 6,
                   "bit_volgorde": "blok 0 (links) = minst significante bit", "wit": "1", "zwart": "0",
                   "lees_punt": "midden van elk blok: x = i*80 + 36, y = 46"},
        "tijd_van_frame": "t = frame * 1001 / 24000 s (vanaf bron_start_s)",
        "tijdcode": "drawtext %{pts:hms} en frame %{frame_num} onderin (alleen voor mensen; de blokken zijn de waarheid)",
        "maximum_frames": 2 ** BLOKKEN,
    })
    ctx.tel("framecode-video")


def lees_framecode(grijs: bytes, breedte: int = BREEDTE) -> int:
    """Leest het framenummer uit één grijswaardenframe (bytes per pixel, rij voor rij)."""
    y = STRIP_Y + STRIP_H // 2
    waarde = 0
    for i in range(BLOKKEN):
        x = i * BLOK_B + (BLOK_B - 8) // 2
        if grijs[y * breedte + x] >= 128:
            waarde |= 1 << i
    return waarde
