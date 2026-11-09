"""F3 — ondertitelgenerators per fouttype (B03 2.0 F3.3, "Generators per fouttype").

Per split en per fouttype ≥ 20 varianten (schaal vol) met verschillende seeds, in vensters van 25 cues. Kalibratiesplit
= Tears of Steel + Sintel; testsplit = Pioneer One S01E01 (REFIX-EN als bron, Nederlandse fanvertaling als referentie;
NC + fanondertitels → alleen lokaal, de set wordt dan als beperkt gemarkeerd). Goede documenten = de menselijke
referentie per venster (OPUS-MT-uitvoer bestaat hier niet; die komt uit de optionele mt-app in P5).
"""

from __future__ import annotations

import random
import re

from .basis import Context, Cue, lees_srt, schrijf_srt

VENSTER = 25
TYPEN = {
    "verkeerde_taal": "blokkade (taal)",
    "onvertaald": "blokkade of score < 0,60",
    "geschud": "score < 0,80 (lengte- en syncpatroon)",
    "afgekapt": "blokkade (lege cues) of score < 0,60",
    "gehallucineerd": "score < 0,80 (herhaling, lengteverhouding)",
    "verschoven": "score < 0,80 (sync)",
    "inhoudelijk_verkeerd": "onzeker; zonder rondreis-chrF vermoedelijk niet te vangen",
}


def _bronnen(ctx: Context, split: str) -> list[dict]:
    if split == "kalibratie":
        tos = "blender/tos/subs/"
        andere = [f"{tos}TOS-{t}.srt" for t in ("de", "es", "fr-orig", "it", "no", "Dansk")]
        uit = [{"film": "tos", "bron": lees_srt(ctx.bron(f"{tos}TOS-en.srt")), "ref": lees_srt(ctx.bron(f"{tos}TOS-nl.srt")),
                "andere": {a.rsplit("TOS-", 1)[1].removesuffix(".srt"): lees_srt(ctx.bron(a)) for a in andere}}]
        sintel_en = ctx.uit / ".sintel-eng.srt"
        ctx.ff.ffmpeg(["-i", str(ctx.bron("blender/sintel/Sintel.2010.1080p.mkv")), "-map", "0:s:m:language:eng",
                       "-c:s", "srt", str(sintel_en)])
        sub = "blender/sintel/subs/"
        uit.append({"film": "sintel", "bron": lees_srt(sintel_en), "ref": lees_srt(ctx.bron(f"{sub}sintel_nl.srt")),
                    "andere": {t: lees_srt(ctx.bron(f"{sub}sintel_{t}.srt")) for t in ("fr", "swe", "pl", "da", "ru")}})
        sintel_en.unlink()
        return uit
    sub = "pioneer-one/subs/"
    return [{"film": "pioneer-one-s01e01", "bron": lees_srt(ctx.bron(f"{sub}S01E01.en.REFIX-VODO.English.updated.Addic7ed.com.srt")),
             "ref": lees_srt(ctx.bron(f"{sub}S01E01.nl.Dutch.updated.Addic7ed.com.srt")), "andere": {}}]


def _vensters(cues: list[Cue]) -> list[list[Cue]]:
    return [cues[i:i + VENSTER] for i in range(0, len(cues) - VENSTER + 1, VENSTER)]


def _overlap(a: Cue, b: Cue) -> float:
    return max(0.0, min(a.eind, b.eind) - max(a.start, b.start))


def _engels_bij(nl: Cue, en: list[Cue]) -> Cue | None:
    beste = max(en, key=lambda e: _overlap(nl, e), default=None)
    return beste if beste and _overlap(nl, beste) > 0 else None


def _maak_variant(soort: str, rng: random.Random, venster: list[Cue], film: dict, alle_ref: list[Cue]) -> tuple[list[Cue], dict]:
    v = [Cue(c.start, c.eind, c.tekst) for c in venster]
    t0, t1 = v[0].start, v[-1].eind
    if soort == "verkeerde_taal":
        taal = rng.choice(sorted(film["andere"]))
        andere = [c for c in film["andere"][taal] if c.eind > t0 and c.start < t1] or film["andere"][taal][:VENSTER]
        return andere, {"taal": taal}
    if soort == "onvertaald":
        aandeel = rng.choice([0.25, 0.5, 1.0])
        k = round(aandeel * len(v))
        for i in sorted(rng.sample(range(len(v)), k)):
            en = _engels_bij(v[i], film["bron"])
            if en:
                v[i].tekst = en.tekst
        return v, {"aandeel_engels": aandeel}
    if soort == "geschud":
        teksten = [c.tekst for c in v]
        rng.shuffle(teksten)
        for c, t in zip(v, teksten, strict=True):
            c.tekst = t
        return v, {"wijze": "binnen venster"}
    if soort == "afgekapt":
        k = rng.uniform(0.3, 0.8)
        grens = round(k * len(v))
        leeg = rng.random() < 0.5
        for c in v[grens:]:
            c.tekst = "" if leeg else c.tekst[: max(1, len(c.tekst) // 3)]
        return v, {"na_aandeel": round(k, 3), "wijze": "leeg" if leeg else "afgebroken"}
    if soort == "gehallucineerd":
        if rng.random() < 0.5:
            zin = rng.choice(v).tekst
            for i in rng.sample(range(len(v)), max(3, len(v) // 4)):
                v[i].tekst = zin
            return v, {"wijze": "herhaalde zin"}
        vreemd = [c.tekst for c in alle_ref if c.start > t1 + 60 or c.eind < t0 - 60]
        for i in rng.sample(range(len(v)), max(3, len(v) // 4)):
            v[i].tekst = v[i].tekst + "\n" + rng.choice(vreemd or ["Dat had ik nooit gedacht."])
        return v, {"wijze": "ingevoegde vreemde NL-zinnen"}
    if soort == "verschoven":
        if rng.random() < 0.5:
            d = rng.choice([-1, 1]) * rng.uniform(2.0, 5.0)
            for c in v:
                c.start, c.eind = c.start + d, c.eind + d
            return v, {"verschuiving_s": round(d, 3)}
        f = rng.choice([25 / 23.976, 23.976 / 25])
        for c in v:
            c.start, c.eind = c.start * f, c.eind * f
        return v, {"drift_factor": round(f, 6)}
    if soort == "inhoudelijk_verkeerd":
        kandidaten = [c for c in alle_ref if c.start > t1 + 30 or c.eind < t0 - 30]
        for c in v:
            gelijk = sorted(kandidaten, key=lambda k: abs(len(k.tekst) - len(c.tekst)))[:8]
            if gelijk:
                c.tekst = rng.choice(gelijk).tekst
        return v, {"wijze": "vloeiende NL-tekst van een andere scène met vergelijkbare lengte"}
    raise ValueError(soort)


def maak(ctx: Context) -> None:
    per_type = int(ctx.parameters.get("per_type", 20 if ctx.vol else 2))
    splits = ["kalibratie"] + ([] if ctx.parameters.get("zonder_beperkt", not ctx.vol) else ["test"])
    index = []
    for split in splits:
        films = _bronnen(ctx, split)
        for film in films:
            for wi, venster in enumerate(_vensters(film["ref"])):
                rel = f"{split}/goed/{film['film']}-venster{wi:02d}.nl.srt"
                ctx.tekst(rel, schrijf_srt(venster))
                index.append({"bestand": rel, "split": split, "film": film["film"], "type": "goed_menselijk",
                              "venster": wi, "verwacht": "score ≥ drempel"})
                ctx.tel(f"{split}:goed")
        for soort, verwacht in TYPEN.items():
            if soort == "verkeerde_taal" and not any(f["andere"] for f in films):
                # Testsplit (Pioneer One) heeft geen menselijke ondertitels in andere talen: die met kalibratiebronnen.
                continue
            for n in range(per_type):
                rng = random.Random(f"{ctx.seed}:{split}:{soort}:{n}")
                film = rng.choice([f for f in films if soort != "verkeerde_taal" or f["andere"]])
                vensters = _vensters(film["ref"])
                wi = rng.randrange(len(vensters))
                cues, params = _maak_variant(soort, rng, vensters[wi], film, film["ref"])
                rel = f"{split}/{soort}/{film['film']}-v{n:02d}.nl.srt"
                ctx.tekst(rel, schrijf_srt(cues))
                index.append({"bestand": rel, "split": split, "film": film["film"], "type": soort, "venster": wi,
                              "parameters": params, "verwacht": verwacht})
                ctx.tel(f"{split}:{soort}")
    ctx.json("grondwaarheid.json", {
        "recept": "f3-ondertitels", "venster_cues": VENSTER, "per_type": per_type, "splits": splits,
        "regel": "drempels alleen op de kalibratiesplit vaststellen en daarna bevriezen; testsplit alleen voor de gate",
        "varianten": index,
    })


def taalcode(pad: str) -> str:
    m = re.search(r"\.([a-z]{2,3})\.srt$", pad)
    return m.group(1) if m else ""
