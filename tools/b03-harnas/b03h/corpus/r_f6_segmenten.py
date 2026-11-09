"""F6 — segmenttestset met augmentatie en post-credit-varianten (B03 2.0 F6.1.3, F6.9.2).

Andere seeds, posities en bronfragmenten dan de devset (de 8 bestaande synthetische afleveringen). Streef-n (vol):
intro ≥ 60, outro ≥ 60, recap ≥ 40, preview ≥ 30, beschermde scènes (post-/mid-credit en previews na een ED) ≥ 30,
intro buiten het Intro Skipper-venster (min(25 %, 10 min)) ≥ 20, seizoensvariant/nieuwe OP ≥ 20. Zes series ("families")
× 10 afleveringen; elke aflevering krijgt een eigen augmentatie (volume, helderheid, ruis, bijsnijden).
"""

from __future__ import annotations

import random

from .basis import Context, Segment, keten

INHOUD = [("blender/tos/uitgepakt/tears_of_steel_1080p.mov", 30, 640), ("blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4", 60, 520),
          ("blender/caminandes/Caminandes_Llamigos-1080p.mp4", 20, 120), ("blender/ed/elephantsdream-720-h264-st-aac.mov", 150, 540),
          ("blender/cosmos/Cosmos_Laundromat_First_Cycle_2k.mp4", 90, 600), ("blender/spring/Spring-Blender-Open-Movie.mkv", 60, 380)]
PIONEER = [(f"pioneer-one/Pioneer.One.S01E0{i}.720p.x264-VODO.mp4", 200, 2400) for i in range(1, 7)]
# Familie: intro S01, intro S02 (nieuwe OP), aftiteling, preview?, beschermd? (post/mid-credit)
FAMILIES = {
    "A": {"intro": ("blender/cosmos/Cosmos_Laundromat_First_Cycle_2k.mp4", 40, 20, None, 0),
          "intro2": ("blender/cosmos/Cosmos_Laundromat_First_Cycle_2k.mp4", 300, 16, None, 0),
          "outro": ("blender/sintel/Sintel.2010.1080p.mkv", 744, 40, None, 0), "preview": False, "beschermd": True},
    "B": {"intro": ("blender/spring/Spring-Blender-Open-Movie.mkv", 30, 25, "blender/ed/1-TheWires.mp3", 0),
          "intro2": ("blender/spring/Spring-Blender-Open-Movie.mkv", 200, 25, "blender/ed/1-TheWires.mp3", 45),
          "outro": ("blender/sintel/Sintel.2010.1080p.mkv", 790, 35, "blender/ed/5-EndTitle.mp3", 0), "preview": True,
          "beschermd": False},
    "C": {"intro": ("blender/ed/elephantsdream-720-h264-st-aac.mov", 120, 18, None, 0),
          "intro2": ("blender/ed/elephantsdream-720-h264-st-aac.mov", 400, 18, None, 0),
          "outro": ("blender/ed/elephantsdream-720-h264-st-aac.mov", 600, 40, None, 0), "preview": False, "beschermd": True},
    "D": {"intro": ("blender/caminandes/Caminandes_Llamigos-1080p.mp4", 2, 18, "blender/ed/1-TheWires.mp3", 25),
          "intro2": ("blender/caminandes/02_gran_dillama_1080p.mp4", 2, 18, "blender/ed/5-EndTitle.mp3", 60),
          "outro": ("blender/caminandes/02_gran_dillama_1080p.mp4", 118, 22, "blender/ed/5-EndTitle.mp3", 20), "preview": True,
          "beschermd": False},
    "E": {"intro": ("blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4", 30, 22, None, 0),
          "intro2": ("blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4", 330, 20, None, 0),
          "outro": ("blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4", 600, 30, None, 0), "preview": False,
          "beschermd": True},
    "F": {"intro": ("blender/tos/uitgepakt/tears_of_steel_1080p.mov", 10, 20, None, 0),
          "intro2": ("blender/tos/uitgepakt/tears_of_steel_1080p.mov", 400, 20, None, 0),
          "outro": ("blender/tos/uitgepakt/tears_of_steel_1080p.mov", 660, 40, None, 0), "preview": True, "beschermd": False},
}
POST = ("blender/hero/hero.mp4", 20, 200)
AFLEVERINGEN = [(1, e) for e in range(1, 7)] + [(2, e) for e in range(1, 5)]
BUITEN_VENSTER = {3, 6, 9}
BUITEN_VENSTER_EXTRA = {"A": {10}, "B": {10}}


def _seg(ctx: Context, spec: tuple, label: str, aug: dict) -> Segment:
    rel, start, duur, audio_rel, audio_start = spec
    return Segment(ctx.bron(rel), float(start), float(duur), label,
                   audio=ctx.bron(audio_rel) if audio_rel else None, audio_start=float(audio_start), augment=aug)


def maak(ctx: Context) -> None:
    families = list(FAMILIES) if ctx.vol else ["B"]
    afleveringen = AFLEVERINGEN if ctx.vol else AFLEVERINGEN[:2]
    pool = INHOUD + (PIONEER if ctx.parameters.get("beperkte_bronnen", False) else [])
    index = []
    for fam in families:
        f = FAMILIES[fam]
        vorige_inhoud: list[tuple] = []
        for volgnr, (seizoen, ep) in enumerate(afleveringen, start=1):
            rng = random.Random(f"{ctx.seed}:f6:{fam}:{seizoen}:{ep}")
            aug = {"volume_db": round(rng.uniform(-4, 4), 2), "helderheid": round(rng.uniform(-0.04, 0.04), 3),
                   "ruis": rng.choice([0, 0, 4, 8]), "bijsnijden": rng.choice([0, 0, 0.02, 0.03])}
            aug = {k: v for k, v in aug.items() if v}
            inhoud = []
            for _ in range(rng.choice([2, 3])):
                rel, lo, hi = rng.choice(pool)
                duur = rng.randint(25, 45)
                inhoud.append((rel, rng.randint(lo, hi - duur), duur, None, 0))
            segmenten: list[Segment] = []
            if ep > 1 and vorige_inhoud:
                for rel, s, d, _, _ in vorige_inhoud[:2]:
                    segmenten.append(_seg(ctx, (rel, s + 3, min(8, d - 4), None, 0), "recap", aug))
            buiten = volgnr in BUITEN_VENSTER or volgnr in BUITEN_VENSTER_EXTRA.get(fam, set())
            cold = inhoud[0]
            if buiten:
                segmenten.append(_seg(ctx, cold, "cold_open", aug))
                segmenten.append(_seg(ctx, inhoud[1], "inhoud", aug))
            else:
                segmenten.append(_seg(ctx, (cold[0], cold[1], min(cold[2], rng.randint(12, 20)), None, 0), "cold_open", aug))
            segmenten.append(_seg(ctx, f["intro2"] if seizoen == 2 else f["intro"], "intro", aug))
            for blok in (inhoud[2:] if buiten else inhoud[1:]):
                segmenten.append(_seg(ctx, blok, "inhoud", aug))
            rel_o, s_o, d_o, a_o, as_o = f["outro"]
            mid = f["beschermd"] and volgnr % 2 == 1
            if mid:
                helft = d_o // 2
                segmenten.append(_seg(ctx, (rel_o, s_o, helft, a_o, as_o), "aftiteling", aug))
                segmenten.append(_seg(ctx, (POST[0], rng.randint(POST[1], POST[2]), rng.randint(6, 12), None, 0), "mid_credit", aug))
                segmenten.append(_seg(ctx, (rel_o, s_o + helft, d_o - helft, a_o, as_o + helft), "aftiteling", aug))
            else:
                segmenten.append(_seg(ctx, f["outro"], "aftiteling", aug))
            if f["beschermd"] and not mid:
                segmenten.append(_seg(ctx, (POST[0], rng.randint(POST[1], POST[2]), rng.randint(8, 15), None, 0), "post_credit", aug))
            if f["preview"]:
                rel, lo, hi = rng.choice(pool)
                segmenten.append(_seg(ctx, (rel, rng.randint(lo, hi - 12), rng.randint(8, 12), None, 0), "preview", aug))
            rel = f"series/B03 Testset {fam}/Season {seizoen:02d}/B03 Testset {fam} S{seizoen:02d}E{ep:02d}.mkv"
            waarheid = keten(ctx, segmenten, ctx.pad(rel))
            duur = waarheid[-1]["eind"]
            intro_start = next(s["start"] for s in waarheid if s["label"] == "intro")
            is_venster = min(0.25 * duur, 600.0)
            labels = [s["label"] for s in waarheid]
            info = {"bestand": rel, "familie": fam, "seizoen": seizoen, "aflevering": ep, "duur_s": duur, "segmenten": waarheid,
                    "augmentatie": aug, "intro_buiten_is_venster": intro_start >= is_venster,
                    "is_venster_s": round(is_venster, 3), "nieuwe_op": seizoen == 2,
                    "beschermd": [s for s in waarheid if s["label"] in ("post_credit", "mid_credit", "preview")]}
            index.append(info)
            ctx.tel("intro")
            ctx.tel("outro")
            for lab in ("recap", "preview", "post_credit", "mid_credit"):
                if lab in labels:
                    ctx.tel(lab)
            if any(lab in labels for lab in ("post_credit", "mid_credit", "preview")):
                ctx.tel("beschermd")
            if info["intro_buiten_is_venster"]:
                ctx.tel("intro_buiten_is_venster")
            if seizoen == 2:
                ctx.tel("seizoensvariant_nieuwe_op")
            vorige_inhoud = inhoud
    ctx.json("grondwaarheid.json", {
        "recept": "f6-segmenten", "labels": ["intro", "recap", "aftiteling", "preview", "post_credit", "mid_credit", "cold_open",
                                              "inhoud"],
        "streef_n": {"intro": 60, "outro": 60, "recap": 40, "preview": 30, "beschermd": 30, "intro_buiten_is_venster": 20,
                     "seizoensvariant_nieuwe_op": 20},
        "regel": "devset = de 8 bestaande synthetische afleveringen; deze testset alleen voor de gate, bevroren vóór B03-072",
        "is_venster": "Intro Skipper: 'within the first 25% of an episode or the first 10 minutes, whichever is smaller'",
        "afleveringen": index,
    })
