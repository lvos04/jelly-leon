"""F4 — testset T-QC (gate) en N-QC-rommelig (vals alarm, realistisch); B03 2.0 F4.1.5 en F4.9.3.

T-QC per klasse met andere seeds, posities, groottes, bronfragmenten, codecs en containers. Grondwaarheid
"effectief beschadigd" via framemd5 tegen de referentie (een beschadiging die geen frame verandert telt niet als positief)
en de pakkettijd van de beschadigde bytes. Streef-n (vol): hoog-klassen ≥ 30 per codecklasse, middel-klassen ≥ 20.
N-QC-rommelig: TS met instap halverwege en CC-fouten, remux met tijdstempelgaten of ontbrekende pts, interlaced, VFR,
gefragmenteerde MP4, oude AVI zonder index; verwacht hooguit een *aanwijzing*.
"""

from __future__ import annotations

import os
import random
import shutil
from pathlib import Path
from typing import Any

from .basis import Context, Cue, lees_srt, schrijf_srt
from .ffmpeg import BITEXACT

VIDEO_ENC = {
    "h264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-g", "48", "-pix_fmt", "yuv420p"],
    "hevc8": ["-c:v", "libx265", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p", "-g", "48",
              "-x265-params", "pools=1:frame-threads=1:log-level=error"],
    "hevc10": ["-c:v", "libx265", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p10le", "-g", "48",
               "-x265-params", "pools=1:frame-threads=1:log-level=error"],
    "av1": ["-c:v", "libsvtav1", "-preset", "12", "-crf", "45", "-pix_fmt", "yuv420p", "-g", "48",
            "-svtav1-params", "lp=1"],
    "mpeg2": ["-c:v", "mpeg2video", "-q:v", "4", "-g", "24"],
    "vp9": ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "0", "-crf", "40", "-threads", "1",
            "-row-mt", "0", "-g", "48"],
    "mpeg4": ["-c:v", "mpeg4", "-q:v", "5", "-g", "24"],
}
AUDIO_ENC = {
    "aac": ["-c:a", "aac", "-b:a", "128k"], "ac3": ["-c:a", "ac3", "-b:a", "192k"], "eac3": ["-c:a", "eac3", "-b:a", "192k"],
    "flac": ["-c:a", "flac"], "opus": ["-c:a", "libopus", "-b:a", "96k"], "mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
}
CONTAINERS = {
    "h264": ["mkv", "mp4", "mp4-moov-achter", "ts", "avi"], "hevc8": ["mkv", "mp4", "ts"], "hevc10": ["mkv", "mp4", "ts"],
    "av1": ["mkv", "mp4", "webm"], "mpeg2": ["ts", "mkv", "mp4"], "vp9": ["webm", "mkv", "mp4"], "mpeg4": ["avi", "mkv", "mp4"],
}
EXT = {"mkv": "mkv", "mp4": "mp4", "mp4-moov-achter": "mp4", "ts": "ts", "avi": "avi", "webm": "webm"}
AUDIO_VOOR = {"webm": "opus", "avi": "mp3", "ts": "aac"}
LAYOUTS = {"2.0": "stereo", "5.1": "5.1", "7.1": "7.1"}
PAN = {"2.0": "stereo|FL=c0|FR=c1",
       "5.1": "5.1|FL=c0|FR=c1|FC=0.5*c0+0.5*c1|LFE=0.3*c0+0.3*c1|BL=0.7*c0|BR=0.7*c1",
       "7.1": "7.1|FL=c0|FR=c1|FC=0.5*c0+0.5*c1|LFE=0.3*c0+0.3*c1|BL=0.7*c0|BR=0.7*c1|SL=0.6*c0|SR=0.6*c1"}
VRIJE_BRONNEN = [
    "blender/spring/Spring-Blender-Open-Movie.mkv", "blender/cosmos/Cosmos_Laundromat_First_Cycle_2k.mp4",
    "blender/ed/elephantsdream-720-h264-st-aac.mov", "blender/caminandes/02_gran_dillama_1080p.mp4",
    "blender/caminandes/Caminandes_Llamigos-1080p.mp4", "blender/tos/uitgepakt/tears_of_steel_1080p.mov",
    "blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4",
]
BEPERKTE_BRONNEN = [f"pioneer-one/Pioneer.One.S01E0{i}.720p.x264-VODO.mp4" for i in (2, 3, 4)]
GROOTTES_VIDEO = [4 << 10, 16 << 10, 64 << 10, 256 << 10]
GROOTTES_AUDIO = [512, 2 << 10, 8 << 10, 32 << 10]
_DUUR: dict[str, float] = {}


class Maker:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.vol = ctx.vol
        self.bronnen = list(VRIJE_BRONNEN) + (BEPERKTE_BRONNEN if ctx.parameters.get("beperkte_bronnen", ctx.vol) else [])
        self.index: list[dict[str, Any]] = []
        self.ref_map = ctx.uit / ".referenties"

    def duur(self, rel: str) -> float:
        if rel not in _DUUR:
            _DUUR[rel] = float(self.ctx.ff.ffprobe(self.ctx.bron(rel))["format"]["duration"])
        return _DUUR[rel]

    def kies_fragment(self, rng: random.Random, lengte: float) -> tuple[str, float]:
        rel = rng.choice(self.bronnen)
        start = rng.uniform(5.0, max(6.0, self.duur(rel) - lengte - 30.0))
        return rel, round(start, 2)

    def clip(self, doel: Path, rel: str, start: float, lengte: float, vcodec: str = "h264", container: str = "mkv",
             acodec: str | None = "aac", layout: str = "2.0", af: str = "", grootte: tuple[int, int] = (640, 360),
             zonder_audio: bool = False) -> Path:
        bron = self.ctx.bron(rel)
        b, h = grootte
        # Exacte lengte via trim/atrim in de filters (niet via -t): met de multithreaded ffmpeg-planner kan een -t-grens
        # per run een frame/pakket verschillen, en dan is het recept niet meer reproduceerbaar.
        vf = (f"scale={b}:{h}:force_original_aspect_ratio=decrease,pad={b}:{h}:(ow-iw)/2:(oh-ih)/2,fps=24,setsar=1,"
              f"format={'yuv420p10le' if vcodec == 'hevc10' else 'yuv420p'},trim=duration={lengte:.3f},setpts=PTS-STARTPTS")
        args = ["-ss", f"{start:.3f}", "-t", f"{lengte + 1:.3f}", "-i", str(bron), "-map", "0:v:0"]
        if not zonder_audio:
            args += ["-map", "0:a:0"]
        args += ["-vf", vf, *VIDEO_ENC[vcodec]]
        if container in ("mp4", "mp4-moov-achter") and vcodec.startswith("hevc"):
            args += ["-tag:v", "hvc1"]
        if not zonder_audio and acodec:
            pan = PAN[layout]
            filt = f"aresample=48000,pan={pan}{(',' + af) if af else ''},atrim=duration={lengte:.3f},asetpts=PTS-STARTPTS"
            args += ["-af", filt, *AUDIO_ENC[acodec]]
        if container == "mp4":
            args += ["-movflags", "+faststart"]
        args += [*BITEXACT, str(doel)]
        doel.parent.mkdir(parents=True, exist_ok=True)
        self.ctx.ff.ffmpeg(args)
        return doel

    def registreer(self, rel: str, klasse: str, set_: str, **gegevens: Any) -> None:
        self.index.append({"bestand": rel, "klasse": klasse, "set": set_, **gegevens})
        self.ctx.tel(f"{set_}:{klasse}")
        if gegevens.get("effectief") is True:
            self.ctx.tel(f"{set_}:{klasse}:effectief")  # alleen effectief beschadigde varianten tellen als positief (n van de gate)


def _overschrijf(pad: Path, offset: int, data: bytes) -> None:
    with open(pad, "r+b") as f:
        f.seek(offset)
        f.write(data)


def _decode_error_video(m: Maker) -> None:
    ctx = m.ctx
    refs_per = 6 if m.vol else 1
    per_ref = 5 if m.vol else 1
    for codec in VIDEO_ENC:
        for r in range(refs_per):
            rng = random.Random(f"{ctx.seed}:dec-v:{codec}:{r}")
            container = CONTAINERS[codec][r % len(CONTAINERS[codec])]
            rel_bron, start = m.kies_fragment(rng, 10.0)
            ref = m.clip(m.ref_map / f"v-{codec}-{r}.{EXT[container]}", rel_bron, start, 10.0, codec, container,
                         AUDIO_VOOR.get(container, "aac"))
            pakketten = ctx.ff.pakketten(ref, "v:0")
            ref_md5 = ctx.ff.framemd5(ref, "v:0")
            for k in range(per_ref):
                pos = rng.uniform(0.05, 0.95)
                grootte = GROOTTES_VIDEO[(r * per_ref + k) % len(GROOTTES_VIDEO)]
                doel_t = pos * 10.0
                pak = next((p for p in pakketten if float(p.get("pts_time") or p.get("dts_time") or 0) >= doel_t), pakketten[-1])
                rel = f"t-qc/decode_error_video/{codec}/{codec}-r{r}-v{k}.{EXT[container]}"
                doel = ctx.pad(rel)
                shutil.copyfile(ref, doel)
                offset = int(pak["pos"]) + min(16, int(pak["size"]) // 4)
                grootte = min(grootte, ref.stat().st_size - offset - 1024)
                _overschrijf(doel, offset, rng.randbytes(max(grootte, 64)))
                md5 = ctx.ff.framemd5(doel, "v:0")
                verschil = next((i for i, (a, b) in enumerate(zip(ref_md5, md5, strict=False)) if a != b),
                                None if len(ref_md5) == len(md5) else min(len(ref_md5), len(md5)))
                m.registreer(rel, "decode_error", "T-QC", codecklasse=codec, container=container, bron=rel_bron,
                             bron_start_s=start, positie=round(pos, 3), bytes=grootte, offset=offset,
                             pakkettijd_s=float(pak.get("pts_time") or pak.get("dts_time") or 0),
                             effectief=verschil is not None, eerste_afwijkend_frame=verschil, ernst="hoog")


def _decode_error_audio(m: Maker) -> None:
    ctx = m.ctx
    refs_per = 4 if m.vol else 1
    per_ref = 5 if m.vol else 1
    for acodec in AUDIO_ENC:
        for r in range(refs_per):
            rng = random.Random(f"{ctx.seed}:dec-a:{acodec}:{r}")
            container = "mkv" if r % 2 == 0 or acodec == "mp3" else "mp4"
            rel_bron, start = m.kies_fragment(rng, 12.0)
            ref = m.clip(m.ref_map / f"a-{acodec}-{r}.{EXT[container]}", rel_bron, start, 12.0, "h264", container, acodec,
                         layout=["2.0", "5.1"][r % 2] if acodec not in ("mp3", "opus") else "2.0", grootte=(320, 180))
            pakketten = ctx.ff.pakketten(ref, "a:0")
            ref_md5 = ctx.ff.framemd5(ref, "a:0")
            for k in range(per_ref):
                pos = rng.uniform(0.05, 0.9)
                budget = GROOTTES_AUDIO[(r * per_ref + k) % len(GROOTTES_AUDIO)]
                i0 = next((i for i, p in enumerate(pakketten) if float(p.get("pts_time") or 0) >= pos * 12.0), 0)
                rel = f"t-qc/decode_error_audio/{acodec}/{acodec}-r{r}-v{k}.{EXT[container]}"
                doel = ctx.pad(rel)
                shutil.copyfile(ref, doel)
                gebruikt, eerste_t = 0, float(pakketten[i0].get("pts_time") or 0)
                for p in pakketten[i0:]:
                    if gebruikt >= budget:
                        break
                    lengte = min(int(p["size"]) - 1, budget - gebruikt)
                    if lengte > 0:
                        _overschrijf(doel, int(p["pos"]) + 1, rng.randbytes(lengte))
                        gebruikt += lengte
                md5 = ctx.ff.framemd5(doel, "a:0")
                verschil = next((i for i, (a, b) in enumerate(zip(ref_md5, md5, strict=False)) if a != b),
                                None if len(ref_md5) == len(md5) else min(len(ref_md5), len(md5)))
                m.registreer(rel, "decode_error_audio", "T-QC", audiocodec=acodec, container=container, bron=rel_bron,
                             bron_start_s=start, positie=round(pos, 3), bytes=gebruikt, pakkettijd_s=eerste_t,
                             effectief=verschil is not None, eerste_afwijkend_frame=verschil, ernst="hoog",
                             toelichting="alleen bytes binnen audiopakketten overschreven")


def _afgekapt(m: Maker) -> None:
    ctx = m.ctx
    varianten = [("mkv", "mkv"), ("mp4", "mp4"), ("mp4-moov-achter", "mp4"), ("ts", "ts")]
    refs = 8 if m.vol else 1
    per_ref = 4 if m.vol else 1
    for r in range(refs):
        rng = random.Random(f"{ctx.seed}:afgekapt:{r}")
        container, ext = varianten[r % len(varianten)]
        rel_bron, start = m.kies_fragment(rng, 20.0)
        ref = m.clip(m.ref_map / f"t-{r}.{ext}", rel_bron, start, 20.0, "h264", container, "aac")
        pakketten = ctx.ff.pakketten(ref, "v:0")
        grootte = ref.stat().st_size
        for k in range(per_ref):
            frac = rng.uniform(0.10, 0.95)
            punt = int(grootte * frac)
            rel = f"t-qc/afgekapt/{container}-r{r}-v{k}.{ext}"
            doel = ctx.pad(rel)
            with open(ref, "rb") as f_in, open(doel, "wb") as f_uit:
                f_uit.write(f_in.read(punt))
            laatste = max((float(p.get("pts_time") or 0) for p in pakketten if int(p["pos"]) + int(p["size"]) <= punt), default=0.0)
            klasse = "container_error" if container == "mp4-moov-achter" else "truncated"
            m.registreer(rel, klasse, "T-QC", container=container, bron=rel_bron, bron_start_s=start,
                         afkappunt=round(frac, 3), afkap_bytes=punt, laatste_heel_pakket_s=round(laatste, 3),
                         bron_duur_s=20.0, ernst="hoog")


def _audio_klassen(m: Maker) -> None:
    ctx = m.ctx
    n = 20 if m.vol else 1
    codecs = ["aac", "ac3", "eac3", "flac", "opus"]
    for klasse in ("no_audio_track", "silent_track", "channel_silent", "audio_shorter_than_video", "audio_dropout",
                   "audio_clipping"):
        for k in range(n):
            rng = random.Random(f"{ctx.seed}:{klasse}:{k}")
            layout = ["2.0", "5.1", "7.1"][k % 3]
            acodec = codecs[k % len(codecs)]
            if acodec == "opus" and layout != "2.0":
                acodec = "aac"
            if acodec in ("ac3", "eac3") and layout == "7.1":
                layout = "5.1"
            rel_bron, start = m.kies_fragment(rng, 20.0)
            af, details = "", {}
            if klasse == "silent_track":
                af = "volume=0"
            elif klasse == "channel_silent":
                kanaal = "FR" if layout == "2.0" else rng.choice(["FC", "FL", "BR"])
                af = f"pan={LAYOUTS[layout]}|" + "|".join(
                    f"{c}={'0*c' + str(i) if c == kanaal else 'c' + str(i)}" for i, c in enumerate(_kanalen(layout)))
                details = {"stil_kanaal": kanaal}
            elif klasse == "audio_shorter_than_video":
                frac = rng.uniform(0.4, 0.9)
                af = f"atrim=duration={20.0 * frac:.3f}"
                details = {"audio_duur_s": round(20.0 * frac, 3), "video_duur_s": 20.0}
            elif klasse == "audio_dropout":
                lengte = rng.uniform(0.5, 10.0)
                t0 = rng.uniform(1.0, 19.0 - lengte)
                af = f"volume=enable='between(t,{t0:.3f},{t0 + lengte:.3f})':volume=0"
                details = {"van_s": round(t0, 3), "tot_s": round(t0 + lengte, 3)}
            elif klasse == "audio_clipping":
                lengte = rng.uniform(0.5, 6.0)
                t0 = rng.uniform(1.0, 19.0 - lengte)
                versterking = rng.choice([20, 24, 30])
                af = f"volume=enable='between(t,{t0:.3f},{t0 + lengte:.3f})':volume={versterking}dB,aformat=sample_fmts=s16"
                details = {"van_s": round(t0, 3), "tot_s": round(t0 + lengte, 3), "versterking_db": versterking}
            rel = f"t-qc/{klasse}/{klasse}-v{k:02d}.mkv"
            m.clip(ctx.pad(rel), rel_bron, start, 20.0, "h264", "mkv", None if klasse == "no_audio_track" else acodec,
                   layout, af, grootte=(320, 180), zonder_audio=klasse == "no_audio_track")
            m.registreer(rel, klasse, "T-QC", bron=rel_bron, bron_start_s=start, layout=layout,
                         audiocodec=None if klasse == "no_audio_track" else acodec, ernst="middel" if klasse in (
                             "audio_dropout", "audio_clipping", "channel_silent") else "hoog", **details)


def _kanalen(layout: str) -> list[str]:
    return {"2.0": ["FL", "FR"], "5.1": ["FL", "FR", "FC", "LFE", "BL", "BR"],
            "7.1": ["FL", "FR", "FC", "LFE", "BL", "BR", "SL", "SR"]}[layout]


def _ondertitel_klassen(m: Maker) -> None:
    ctx = m.ctx
    n = 20 if m.vol else 1
    tos = "blender/tos/uitgepakt/tears_of_steel_1080p.mov"
    subs = {"nl": lees_srt(ctx.bron("blender/tos/subs/TOS-nl.srt")), "en": lees_srt(ctx.bron("blender/tos/subs/TOS-en.srt")),
            "de": lees_srt(ctx.bron("blender/tos/subs/TOS-de.srt")), "es": lees_srt(ctx.bron("blender/tos/subs/TOS-es.srt")),
            "fr": lees_srt(ctx.bron("blender/tos/subs/TOS-fr-orig.srt"))}
    clips: dict[float, Path] = {}

    def clip_op(start: float) -> Path:
        if start not in clips:
            clips[start] = m.clip(m.ref_map / f"tos-{int(start)}.mkv", tos, start, 120.0, "h264", "mkv", "aac",
                                  grootte=(320, 180))
        return clips[start]

    def cues(taal: str, start: float) -> list[Cue]:
        return [Cue(c.start - start, c.eind - start, c.tekst) for c in subs[taal] if c.start >= start and c.eind <= start + 120]

    starts = [60.0, 240.0, 420.0, 560.0] if m.vol else [60.0]
    for klasse in ("subtitle_offset", "framerate_drift", "wrong_version", "subtitle_language_mismatch"):
        for k in range(n):
            rng = random.Random(f"{ctx.seed}:{klasse}:{k}")
            start = starts[k % len(starts)]
            taal = rng.choice(["nl", "en"])
            basis = cues(taal, start)
            details: dict[str, Any] = {}
            tag = taal
            if klasse == "subtitle_offset":
                d = rng.choice([-1, 1]) * rng.uniform(0.5, 5.0)
                uit = [Cue(c.start + d, c.eind + d, c.tekst) for c in basis]
                details = {"verschuiving_s": round(d, 3)}
            elif klasse == "framerate_drift":
                f = rng.choice([25 / 23.976, 23.976 / 25, 1.001, 1 / 1.001])
                uit = [Cue(c.start * f, c.eind * f, c.tekst) for c in basis]
                details = {"factor": round(f, 6)}
            elif klasse == "wrong_version":
                knip_t = rng.uniform(20.0, 80.0)
                knip_l = rng.uniform(3.0, 20.0)
                uit = [Cue(c.start + (knip_l if c.start >= knip_t else 0), c.eind + (knip_l if c.start >= knip_t else 0),
                           c.tekst) for c in basis]
                details = {"andere_montage": f"vanaf {knip_t:.1f} s {knip_l:.1f} s verschoven (scène ingevoegd)"}
            else:
                werkelijk = rng.choice(["en", "de", "fr", "es"])
                lang = rng.random() < 0.5
                uit = cues(werkelijk, start)
                if not lang:
                    uit = uit[:5]
                if rng.random() < 0.3:
                    uit = [Cue(c.start, c.eind, "[MUZIEK]\n" + c.tekst) for c in uit]
                    details["sdh"] = True
                tag = "nl"
                details |= {"getagd": "nl", "werkelijke_taal": werkelijk, "spoorlengte": "lang" if lang else "kort"}
            map_ = f"t-qc/{klasse}/v{k:02d}"
            media = ctx.pad(f"{map_}/clip.mkv")
            os.link(clip_op(start), media)
            ctx.tekst(f"{map_}/clip.{tag}.srt", schrijf_srt(uit))
            m.registreer(f"{map_}/clip.mkv", klasse, "T-QC", ondertitel=f"{map_}/clip.{tag}.srt", bron=tos,
                         bron_start_s=start, taal_bron=taal, ernst="middel", **details)


def _rommelig(m: Maker) -> None:
    ctx = m.ctx
    n = 5 if m.vol else 1
    for k in range(n):
        rng = random.Random(f"{ctx.seed}:rommelig:{k}")
        rel_bron, start = m.kies_fragment(rng, 30.0)
        ts = m.clip(m.ref_map / f"r-{k}.ts", rel_bron, start, 30.0, "h264", "ts", "aac")
        data = ts.read_bytes()
        cut = (int(len(data) * rng.uniform(0.3, 0.6)) // 188) * 188
        ctx.pad(f"n-qc-rommelig/ts_instap_halverwege-v{k}.ts").write_bytes(data[cut:])
        m.registreer(f"n-qc-rommelig/ts_instap_halverwege-v{k}.ts", "ts_instap_halverwege", "N-QC-rommelig", bron=rel_bron,
                     afgeknipt_bytes=cut, verwacht="hooguit aanwijzing")
        pakket = bytearray(data)
        weg = sorted(rng.sample(range(1, max(2, int(len(data) * 0.1) // 188)), 6), reverse=True)
        for i in weg:
            del pakket[i * 188:(i + 1) * 188]
        ctx.pad(f"n-qc-rommelig/ts_cc_fouten-v{k}.ts").write_bytes(bytes(pakket))
        m.registreer(f"n-qc-rommelig/ts_cc_fouten-v{k}.ts", "ts_cc_fouten", "N-QC-rommelig", bron=rel_bron,
                     weggelaten_ts_pakketten=sorted(weg), verwacht="hooguit aanwijzing")
        # Remux met tijdstempelgat (concat-demuxer met een te lange duur voor deel A).
        deel_a = m.clip(m.ref_map / f"r-{k}-a.mkv", rel_bron, start, 10.0, "h264", "mkv", "aac")
        deel_b = m.clip(m.ref_map / f"r-{k}-b.mkv", rel_bron, start + 10.0, 10.0, "h264", "mkv", "aac")
        gat = round(rng.uniform(2.0, 8.0), 2)
        lijst = m.ref_map / f"r-{k}.txt"
        lijst.write_text(f"file '{deel_a}'\nduration {10.0 + gat}\nfile '{deel_b}'\n", encoding="utf-8")
        rel = f"n-qc-rommelig/remux_tijdstempelgat-v{k}.mkv"
        ctx.ff.ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lijst), "-c", "copy", *BITEXACT, str(ctx.pad(rel))])
        m.registreer(rel, "remux_tijdstempelgat", "N-QC-rommelig", bron=rel_bron, gat_s=gat, verwacht="hooguit aanwijzing")
        # Ontbrekende pts: ruwe H.264 (Annex B) opnieuw gemuxt.
        ruw = m.ref_map / f"r-{k}.h264"
        ctx.ff.ffmpeg(["-i", str(deel_a), "-map", "0:v", "-c", "copy", "-bsf:v", "h264_mp4toannexb", "-f", "h264", str(ruw)])
        # AVI kent geen pts (alleen de volgorde in de index): het klassieke "remux zonder pts"-geval.
        rel = f"n-qc-rommelig/ontbrekende_pts-v{k}.avi"
        ctx.ff.ffmpeg(["-r", "24", "-i", str(ruw), "-c", "copy", *BITEXACT, str(ctx.pad(rel))])
        m.registreer(rel, "ontbrekende_pts", "N-QC-rommelig", bron=rel_bron, verwacht="hooguit aanwijzing")
        # Interlaced H.264 in TS.
        rel = f"n-qc-rommelig/interlaced_h264-v{k}.ts"
        ctx.ff.ffmpeg(["-ss", f"{start:.3f}", "-t", "11", "-i", str(ctx.bron(rel_bron)), "-map", "0:v:0", "-map", "0:a:0",
                       "-vf", "trim=duration=10,setpts=PTS-STARTPTS,scale=720:576,setsar=16/15,fps=50,"
                              "tinterlace=mode=interleave_top,format=yuv420p",
                       "-af", "atrim=duration=10,asetpts=PTS-STARTPTS",
                       "-c:v", "libx264", "-preset", "veryfast", "-flags", "+ilme+ildct", "-x264-params", "tff=1",
                       "-c:a", "aac", *BITEXACT, str(ctx.pad(rel))])
        m.registreer(rel, "interlaced", "N-QC-rommelig", bron=rel_bron, verwacht="hooguit aanwijzing")
        # VFR.
        rel = f"n-qc-rommelig/vfr-v{k}.mkv"
        ctx.ff.ffmpeg(["-ss", f"{start:.3f}", "-t", "11", "-i", str(ctx.bron(rel_bron)), "-map", "0:v:0", "-map", "0:a:0",
                       "-vf", "trim=duration=10,scale=640:360,setsar=1,fps=24,setpts='(N/24+0.012*sin(N*1.7))/TB',format=yuv420p",
                       "-af", "atrim=duration=10,asetpts=PTS-STARTPTS", "-fps_mode", "vfr", "-c:v", "libx264", "-preset", "veryfast",
                       "-c:a", "aac", *BITEXACT, str(ctx.pad(rel))])
        m.registreer(rel, "vfr", "N-QC-rommelig", bron=rel_bron, verwacht="hooguit aanwijzing")
        # Gefragmenteerde MP4.
        rel = f"n-qc-rommelig/gefragmenteerd-v{k}.mp4"
        ctx.ff.ffmpeg(["-i", str(deel_a), "-c", "copy", "-movflags", "frag_keyframe+empty_moov+default_base_moof",
                       *BITEXACT, str(ctx.pad(rel))])
        m.registreer(rel, "gefragmenteerde_mp4", "N-QC-rommelig", bron=rel_bron, verwacht="hooguit aanwijzing")
        # Oude AVI zonder index.
        avi = m.clip(m.ref_map / f"r-{k}.avi", rel_bron, start, 10.0, "mpeg4", "avi", "mp3")
        data = avi.read_bytes()
        idx = data.rfind(b"idx1")
        rel = f"n-qc-rommelig/avi_zonder_index-v{k}.avi"
        ctx.pad(rel).write_bytes(data[:idx] if idx > 0 else data)
        m.registreer(rel, "avi_zonder_index", "N-QC-rommelig", bron=rel_bron, index_verwijderd=idx > 0,
                     verwacht="hooguit aanwijzing")


def maak(ctx: Context) -> None:
    m = Maker(ctx)
    m.ref_map.mkdir(parents=True, exist_ok=True)
    try:
        _decode_error_video(m)
        _decode_error_audio(m)
        _afgekapt(m)
        _audio_klassen(m)
        _ondertitel_klassen(m)
        _rommelig(m)
    finally:
        shutil.rmtree(m.ref_map, ignore_errors=True)
    n_qc = ["kwaliteit/sintel-60s-referentie.mkv"] + [f"formaten/{x}" for x in (
        "dv-p8.1-als.mkv", "dv-p8.1-rpu-gestript-hdr10.mkv", "hdr10-hevc-als.ts", "sintel-30s-vp9-p2-10bit.webm",
        "sintel-30s-av1-svt.mkv", "sintel-30s-h264-10bit.mkv", "sintel-30s-mpeg2-ac3.ts", "sintel-30s-mpeg4-mp3.avi",
        "sintel-30s-hevc8-flac.mkv", "tos-multiaudio-5.1-me-subs.mkv")]
    ctx.json("grondwaarheid.json", {
        "recept": "f4-tqc", "streef_n": {"decode_error per codecklasse": 30, "audio per codec": 20, "truncated/container": 30,
                                         "middel-klassen": 20},
        "effectief_regel": "framemd5 van de betreffende stroom wijkt af van de referentie; effectief=false telt niet als positief",
        "n_qc_schoon_uit_corpus": {"afgeleid": n_qc, "echte_films": [
            "blender/sintel/Sintel.2010.1080p.mkv", "blender/tos/uitgepakt/tears_of_steel_1080p.mov",
            "blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4", "blender/ed/elephantsdream-720-h264-st-aac.mov"]},
        "varianten": m.index,
    })
