"""Tweede F6-recept. Lange afleveringen uit genormaliseerde fragmenten, zonder ontwikkelafleveringen of beperkte bronnen."""

from __future__ import annotations

import json
import random
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .basis import Context
from .ffmpeg import BITEXACT
from .r_f6_segmenten import AFLEVERINGEN, BUITEN_VENSTER, BUITEN_VENSTER_EXTRA, POST

STREEF = {"intro": 60, "outro": 60, "recap": 40, "preview": 30, "beschermd": 30,
          "intro_buiten_is_venster": 20, "seizoensvariant_nieuwe_op": 20}
BBB = "blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4"
ED = "blender/ed/elephantsdream-720-h264-st-aac.mov"
TOS = "blender/tos/uitgepakt/tears_of_steel_1080p.mov"
SINTEL = "blender/sintel/Sintel.2010.1080p.mkv"
COSMOS = "blender/cosmos/Cosmos_Laundromat_First_Cycle_2k.mp4"
EDE = "blender/ed/5-EndTitle.mp3"
MIX = "blender/ed/ED-ME-5.1-DVD.ac3"
LAMA = "blender/caminandes/Caminandes_Llamigos-1080p.mp4"
DILLA = "blender/caminandes/02_gran_dillama_1080p.mp4"

# Binnenbeelden buiten de titels en alle in de acht ontwikkelafleveringen gebruikte uitsneden.
BINNEN = [
    (BBB, 100, 194), (ED, 150, 510), (TOS, 295, 395), (SINTEL, 210, 665), (COSMOS, 95, 550),
]
# Intro, nieuwe opening en aftiteling per familie. Ook de losse audiobronnen zijn van de devset gescheiden.
FAMILIES = {
    "A": ((COSMOS, 72, 20, None, 0), (COSMOS, 302, 16, None, 0), (SINTEL, 835, 40, None, 0)),
    "B": ((LAMA, 22, 25, EDE, 35), (DILLA, 37, 25, EDE, 62), (ED, 617, 35, MIX, 310)),
    "C": ((ED, 120, 18, None, 0), (ED, 400, 18, None, 0), (ED, 600, 40, None, 0)),
    "D": ((LAMA, 4, 18, MIX, 90), (DILLA, 4, 18, MIX, 150), (DILLA, 118, 22, EDE, 37)),
    "E": ((BBB, 29, 22, None, 0), (BBB, 404, 20, None, 0), (BBB, 600, 30, None, 0)),
    "F": ((TOS, 12, 20, None, 0), (TOS, 306, 20, None, 0), (TOS, 695, 30, None, 0)),
}
VARIANTEN = ("referentie", "luid_plus6", "luid_min6", "ingekort", "pal", "effect_over_intro",
             "snel_plus2", "snel_min2", "andere_mix", "herencode")
SCENE = (POST[0], 75, 16, None, 0)
ZWART = (POST[0], 45, 12, None, 0)
EFFECT = (TOS, 300)
ZIJBEELD = (BBB, 120)


def bronscheiding(corpus: Path) -> dict:
    codes = {"BB": BBB, "CL": COSMOS, "SP": "blender/spring/Spring-Blender-Open-Movie.mkv", "TS": TOS, "SI": SINTEL,
             "HE": POST[0], "EDE": EDE, "EDW": "blender/ed/1-TheWires.mp3", "ED": ED}
    bestanden = list((corpus / "afgeleid/series").rglob("*.grondwaarheid.json"))
    if len(bestanden) != 8:
        raise ValueError("voor de bronscheiding zijn de acht synthetische ontwikkelafleveringen nodig")
    dev = set()
    for pad in bestanden:
        segmenten = json.loads(pad.read_text())["segmenten"]
        if not segmenten:
            raise ValueError("bronvensters ontbreken in ontwikkelaflevering")
        for s in segmenten:
            for stuk in s["bron"].split(" + "):
                match = re.fullmatch(r"(?:audio )?([A-Z]+) (\d+)-(\d+)s", stuk)
                if not match or match[1] not in codes or int(match[2]) >= int(match[3]):
                    raise ValueError("onbekend bronvenster in ontwikkelset")
                dev.add((codes[match[1]], int(match[2]), int(match[3])))
    vensters = set(BINNEN)
    fragmenten = [deel for familie in FAMILIES.values() for deel in familie]
    for bron, begin, duur, audio, offset in [*fragmenten, SCENE, ZWART]:
        vensters.add((bron, begin, begin + duur))
        if audio:
            vensters.add((audio, offset, offset + duur))
    for bron, begin in (EFFECT, ZIJBEELD):
        vensters.add((bron, begin, begin + max(deel[2] for deel in fragmenten)))
    if any(f == g and min(b, d) > max(a, c) for f, a, b in vensters for g, c, d in dev):
        raise ValueError("bronfragment overlapt met de ontwikkelset")
    return {"ontwikkelafleveringen": len(bestanden), "ontwikkelvensters": len(dev), "receptvensters": len(vensters), "overlap": 0}


@dataclass(frozen=True)
class Fragment:
    bestand: Path
    begin: int
    duur: int
    label: str


class Montage:
    def __init__(self, ctx: Context, werk: Path):
        self.ctx = ctx
        self.werk = werk
        self.cache: dict[tuple, Path] = {}

    def fragment(self, spec: tuple, label: str, variant: str = "referentie") -> Fragment:
        bron, start, duur, muziek, muziek_start = spec
        duur = int(duur)
        factor = {"pal": 25 / (24000 / 1001), "snel_plus2": 1.02, "snel_min2": 0.98}.get(variant, 1.0)
        lengte = int(duur / factor) - (4 if variant == "ingekort" else 0)
        sleutel = (*spec, variant)
        if sleutel not in self.cache:
            pad = self.werk / f"deel-{len(self.cache):04d}.mkv"
            args = ["-threads", "1", "-ss", str(start), "-i", str(self.ctx.bron(bron))]
            audio = "0:a:0"
            if muziek:
                args += ["-ss", str(muziek_start), "-i", str(self.ctx.bron(muziek))]
                audio = "1:a:0"
            video = ("[0:v:0]scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,"
                     f"setsar=1,setpts=(PTS-STARTPTS)/{factor},fps=24,format=yuv420p")
            geluid = f"[{audio}]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS"
            if factor != 1:
                geluid += f",asetrate={round(48000 * factor)},aresample=48000"
            if variant in ("luid_plus6", "luid_min6"):
                geluid += ",volume=" + ("6dB" if variant == "luid_plus6" else "-6dB")
            elif variant == "andere_mix":
                geluid += ",pan=5.1|FL=FL|FR=FR|FC=0.4*FL+0.4*FR|LFE=0*FL|BL=0.3*FL|BR=0.3*FR,aformat=channel_layouts=stereo"
            elif variant == "effect_over_intro":
                args += ["-ss", str(EFFECT[1]), "-i", str(self.ctx.bron(EFFECT[0]))]
                extra = 2 if muziek else 1
                geluid += f"[orig];[{extra}:a:0]aresample=48000,volume=0.4[effect];[orig][effect]amix=inputs=2:normalize=0"
            elif variant == "zwart":
                video += ",drawbox=color=black:t=fill"
                geluid += ",volume=0"
            elif variant == "beeld_ernaast":
                args += ["-threads", "1", "-ss", str(ZIJBEELD[1]), "-i", str(self.ctx.bron(ZIJBEELD[0]))]
                extra = 2 if muziek else 1
                video += f",scale=320:360[links];[{extra}:v:0]scale=320:360,setsar=1,fps=24[rechts];[links][rechts]hstack"
            # Vaste GOP van één seconde en PCM maken een exacte uitsnede mogelijk bij het samenvoegen.
            self.ctx.ff.ffmpeg([*args, "-filter_complex_threads", "1", "-filter_complex", f"{video}[v];{geluid}[a]",
                                "-map", "[v]", "-map", "[a]", "-t", str(lengte), "-c:v", "libx264", "-preset", "veryfast",
                                "-crf", "28", "-g", "24", "-keyint_min", "24", "-sc_threshold", "0", "-bf", "0",
                                "-c:a", "pcm_s16le", *BITEXACT, str(pad)])
            self.cache[sleutel] = pad
        return Fragment(self.cache[sleutel], 0, lengte, label)

    def schrijf(self, rel: str, delen: list[Fragment], herencode: bool) -> dict:
        regels = ["ffconcat version 1.0"]
        waarheid = []
        tijd = 0
        for deel in delen:
            regels.extend([f"file {deel.bestand.name}", f"inpoint {deel.begin}", f"outpoint {deel.begin + deel.duur}",
                           f"duration {deel.duur}"])
            if waarheid and waarheid[-1]["label"] == deel.label:
                waarheid[-1]["eind"] += deel.duur
            else:
                waarheid.append({"label": deel.label, "start": tijd, "eind": tijd + deel.duur})
            tijd += deel.duur
        lijst = self.werk / "montage.txt"
        lijst.write_text("\n".join(regels) + "\n", encoding="ascii")
        codec = (["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "pools=none:frame-threads=1:log-level=error",
                  "-crf", "33", "-c:a", "ac3", "-b:a", "160k"] if herencode else ["-c:v", "copy", "-c:a", "aac", "-b:a", "96k"])
        doel = self.ctx.pad(rel)
        self.ctx.ff.ffmpeg(["-f", "concat", "-safe", "1", "-i", str(lijst), "-map", "0:v:0", "-map", "0:a:0",
                            "-af", "aresample=async=1:first_pts=0", *codec, "-t", str(tijd), *BITEXACT, str(doel)])
        gemeten = float(self.ctx.ff.ffprobe(doel, "-show_entries", "format=duration")["format"]["duration"])
        if abs(gemeten - tijd) > 0.1:
            raise ValueError(f"mediaduur verschilt van de grondwaarheid voor {rel}")
        return {"bestand": rel, "duur_s": tijd, "segmenten": waarheid}


def opvulling(pool: list[Fragment], rng: random.Random, duur: int, label: str) -> list[Fragment]:
    delen = []
    while duur:
        bron = rng.choice(pool)
        lengte = min(duur, rng.randint(35, 60))
        delen.append(Fragment(bron.bestand, rng.randrange(bron.duur - lengte + 1), lengte, label))
        duur -= lengte
    return delen


def maak(ctx: Context) -> None:
    rng = random.Random(f"jlt50:{ctx.seed}")
    index = []
    with tempfile.TemporaryDirectory(dir=ctx.uit) as tijdelijk:
        montage = Montage(ctx, Path(tijdelijk))
        pool = [montage.fragment((bron, rng.randint(lo, hi - 80), 80, None, 0), "inhoud")
                for bron, lo, hi in BINNEN for _ in range(2)]
        scene = montage.fragment(SCENE, "post_credit")
        zwart = montage.fragment(ZWART, "inhoud", "zwart")
        # Het fragment na de ED van E04 opent ook E05.
        vooruit = Fragment(pool[-1].bestand, 35, 12, "preview")
        families = FAMILIES if ctx.vol else {"B": FAMILIES["B"]}
        for fam, familie in families.items():
            vorige: list[Fragment] = []
            for nr, (seizoen, ep) in enumerate(AFLEVERINGEN if ctx.vol else AFLEVERINGEN[:2], 1):
                variant = VARIANTEN[(nr - 1 + ord(fam) - ord("A")) % len(VARIANTEN)]
                nieuwe_op = seizoen == 2 or (fam == "B" and ep >= 3)
                intro = montage.fragment(familie[1 if nieuwe_op else 0], "intro", variant)
                aftiteling = montage.fragment(familie[2], "aftiteling", "beeld_ernaast" if nr == 4 else variant)
                beschermd = fam in ("A", "C", "E")
                midden = beschermd and nr % 2 == 1
                staart = [aftiteling]
                if midden:
                    helft = aftiteling.duur // 2
                    staart = [Fragment(aftiteling.bestand, 0, helft, "aftiteling"),
                              Fragment(scene.bestand, 0, 9, "mid_credit"),
                              Fragment(aftiteling.bestand, helft, aftiteling.duur - helft, "aftiteling")]
                elif beschermd:
                    staart.extend([zwart, scene] if nr == 2 else [scene])
                if not beschermd:
                    staart += [vooruit] if (fam, seizoen, ep) == ("B", 1, 4) else opvulling(pool, rng, 12, "preview")
                delen = []
                if ep > 1:
                    delen += [Fragment(d.bestand, d.begin, 20, "recap") for d in vorige[:2]]
                laat = nr in BUITEN_VENSTER or nr in BUITEN_VENSTER_EXTRA.get(fam, set())
                introstart = rng.randint(661, 685) if laat else (90 if delen else 45)
                if (fam, seizoen, ep) == ("B", 1, 5):
                    delen.append(Fragment(vooruit.bestand, vooruit.begin, vooruit.duur, "cold_open"))
                delen += opvulling(pool, rng, introstart - sum(d.duur for d in delen), "cold_open")
                delen.append(intro)
                vorige = opvulling(pool, rng, 1320 - introstart - intro.duur - sum(d.duur for d in staart), "inhoud")
                reeks = f"B03 Meetserie {fam}"
                rel = f"series/{reeks}/Season {seizoen:02d}/{reeks} S{seizoen:02d}E{ep:02d}.mkv"
                info = montage.schrijf(rel, delen + vorige + staart, variant == "herencode")
                index.append({**info, "familie": fam, "seizoen": seizoen, "aflevering": ep, "augmentatie": variant,
                              "intro_buiten_is_venster": laat, "nieuwe_op": nieuwe_op})
                if sum(p.stat().st_size for p in ctx.uit.rglob("*.mkv")) > 15_000_000_000:
                    raise ValueError("F6-testset overschrijdt 15 GB")
        titels = montage.fragment(FAMILIES["A"][2], "aftiteling", "beeld_ernaast")
        if ctx.vol:
            zonder_intro = opvulling(pool, rng, 1320 - titels.duur - scene.duur, "inhoud") + [titels, scene]
            rel = "series/B03 Meetserie A/Season 02/B03 Meetserie A S02E05.mkv"
            index.append({**montage.schrijf(rel, zonder_intro, False), "familie": "A", "seizoen": 2, "aflevering": 5,
                          "augmentatie": "zonder_intro", "intro_buiten_is_venster": False, "nieuwe_op": False})
        film = opvulling(pool, rng, 330, "inhoud") + [titels, Fragment(scene.bestand, 4, 8, "mid_credit"), titels, zwart, scene]
        index.append({**montage.schrijf("films/Meetfilm/Meetfilm.mkv", film, False), "familie": "film",
                      "augmentatie": "beeld_ernaast", "intro_buiten_is_venster": False, "nieuwe_op": False})
    for item in index:
        labels = [s["label"] for s in item["segmenten"]]
        for lab, klasse in (("intro", "intro"), ("aftiteling", "outro"), ("recap", "recap"), ("preview", "preview"),
                            ("post_credit", "post_credit"), ("mid_credit", "mid_credit")):
            ctx.tel(klasse, labels.count(lab))
        ctx.tel("beschermd", sum(labels.count(lab) for lab in ("post_credit", "mid_credit", "preview")))
        ctx.tel("intro_buiten_is_venster", int(item["intro_buiten_is_venster"]))
        ctx.tel("seizoensvariant_nieuwe_op", int(item["nieuwe_op"]))
    ctx.json("grondwaarheid.json", {"recept": "f6-segmenten", "streef_n": STREEF, "afleveringen": index})
