"""Gemeenschappelijke bouwstenen van de recepten: context, bronnen met licentie, JSON/SRT-hulpen en segmentketens."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ffmpeg import BITEXACT, Ffmpeg
from .manifest import sha256_bestand

# Licentie per bronmap (CORPUS.md §2). 'beperkt' = nooit in een repo of image, alleen lokaal (BG-37).
LICENTIES: list[tuple[str, str, bool]] = [
    ("pioneer-one/subs/", "fanondertitels (Addic7ed), licentie onduidelijk — niet herverspreiden", True),
    ("pioneer-one/", "CC BY-NC-SA (Pioneer One, VODO) — alleen lokaal (BG-37)", True),
    ("blender/sintel/", "CC BY 3.0 (Blender Foundation, Sintel)", False),
    ("blender/tos/", "CC BY 3.0 (Blender Foundation, Tears of Steel)", False),
    ("blender/bbb/", "CC BY 3.0 (Blender Foundation, Big Buck Bunny)", False),
    ("blender/ed/", "CC BY 2.5 (Blender Foundation / NIMk, Elephants Dream)", False),
    ("blender/cosmos/", "CC BY-SA 4.0 (Blender Foundation, Cosmos Laundromat)", False),
    ("blender/caminandes/", "CC BY 3.0 (Blender Foundation, Caminandes)", False),
    ("blender/spring/", "CC BY 4.0 (Blender Studio, Spring)", False),
    ("blender/hero/", "CC BY 4.0 (Blender Studio, Hero)", False),
    ("jellyfin-testvideos/", "CC BY-SA 4.0 (Jellyfin-testvideo's, Gnattu)", False),
]
SYNTHETISCH = "eigen synthetisch materiaal (lavfi), geen rechten van derden"


def licentie_van(rel: str) -> tuple[str, bool]:
    for prefix, licentie, beperkt in LICENTIES:
        if rel.startswith(prefix):
            return licentie, beperkt
    raise KeyError(f"geen licentie bekend voor bron {rel}; voeg die eerst toe aan CORPUS.md en LICENTIES")


_SHA_CACHE: dict[str, str] = {}


def bekende_sha256(corpus: Path) -> dict[str, str]:
    """sha256 per bronbestand uit SHA256SUMS.bron.txt en SHA256SUMS.ondertitels.txt (relatief aan bron/)."""
    uit: dict[str, str] = {}
    for naam in ("SHA256SUMS.bron.txt", "SHA256SUMS.ondertitels.txt"):
        pad = corpus / naam
        if pad.exists():
            for regel in pad.read_text(encoding="utf-8").splitlines():
                if "  " in regel:
                    h, rel = regel.split("  ", 1)
                    uit[rel.removeprefix("./").removeprefix("bron/")] = h
    return uit


@dataclass
class Context:
    corpus: Path
    uit: Path
    seed: int
    schaal: str
    ff: Ffmpeg
    parameters: dict[str, Any] = field(default_factory=dict)
    bronnen: dict[str, dict[str, Any]] = field(default_factory=dict)
    licenties: set[str] = field(default_factory=set)
    beperkt: bool = False
    aantallen: dict[str, int] = field(default_factory=dict)
    controleer_bron: bool = True

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self._bekend = bekende_sha256(self.corpus) if self.controleer_bron else {}

    @property
    def vol(self) -> bool:
        return self.schaal == "vol"

    def bron(self, rel: str) -> Path:
        """Pad naar een bronbestand; legt licentie en sha256 vast en controleert die tegen het corpusmanifest."""
        pad = self.corpus / "bron" / rel
        if not pad.is_file():
            raise FileNotFoundError(f"bron ontbreekt: {pad}")
        licentie, beperkt = licentie_van(rel)
        if rel not in self.bronnen:
            sha = _SHA_CACHE.get(str(pad)) or sha256_bestand(pad)
            _SHA_CACHE[str(pad)] = sha
            verwacht = self._bekend.get(rel)
            if self.controleer_bron and verwacht and verwacht != sha:
                raise ValueError(f"bron {rel}: sha256 wijkt af van het corpusmanifest — corpus eerst herstellen")
            self.bronnen[rel] = {"pad": rel, "sha256": sha, "licentie": licentie, "beperkt": beperkt,
                                 "in_corpusmanifest": verwacht is not None}
        self.licenties.add(licentie)
        self.beperkt = self.beperkt or beperkt
        return pad

    def synthetisch(self) -> None:
        self.licenties.add(SYNTHETISCH)

    def tel(self, klasse: str, aantal: int = 1) -> None:
        self.aantallen[klasse] = self.aantallen.get(klasse, 0) + aantal

    def pad(self, rel: str) -> Path:
        pad = self.uit / rel
        pad.parent.mkdir(parents=True, exist_ok=True)
        return pad

    def json(self, rel: str, data: Any) -> Path:
        pad = self.pad(rel)
        pad.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return pad

    def tekst(self, rel: str, inhoud: str) -> Path:
        pad = self.pad(rel)
        pad.write_text(inhoud, encoding="utf-8")
        return pad


# --- video: genormaliseerde segmentketen (analyse 5 §5.2) ---------------------------------------------------------

@dataclass
class Segment:
    """Eén stuk uit een bron (start, duur in s) met een label voor de grondwaarheid."""

    bron: Path
    start: float
    duur: float
    label: str
    audio: Path | None = None  # aparte audiobron (bv. soundtrack over ander beeld); anders de audio van `bron`
    audio_start: float | None = None
    augment: dict[str, float] = field(default_factory=dict)


def keten(ctx: Context, segmenten: list[Segment], doel: Path, *, breedte: int = 640, hoogte: int = 360, fps: int = 24,
          crf: int = 28, extra_uit: list[str] | None = None) -> list[dict[str, Any]]:
    """Plakt segmenten genormaliseerd aan elkaar (concat-filter) en geeft de exacte grondwaarheid terug."""
    invoer: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    t = 0.0
    waarheid = []
    n_in = 0
    for i, s in enumerate(segmenten):
        invoer += ["-ss", f"{s.start:.3f}", "-t", f"{s.duur + 0.5:.3f}", "-i", str(s.bron)]
        vi = ai = n_in
        n_in += 1
        if s.audio is not None:
            invoer += ["-ss", f"{(s.audio_start if s.audio_start is not None else 0.0):.3f}", "-t", f"{s.duur + 0.5:.3f}",
                       "-i", str(s.audio)]
            ai = n_in
            n_in += 1
        aug = s.augment
        vext = ""
        if aug.get("helderheid"):
            vext += f",eq=brightness={aug['helderheid']:.3f}"
        if aug.get("ruis"):
            # Vaste ruis-seed (standaard kiest het noise-filter een willekeurige seed → niet reproduceerbaar).
            vext += f",noise=alls={int(aug['ruis'])}:allf=t:all_seed={int(aug.get('ruis_seed', 20261109))}"
        if aug.get("bijsnijden"):
            c = aug["bijsnijden"]
            vext += f",crop=iw*{1 - c:.3f}:ih*{1 - c:.3f},scale={breedte}:{hoogte}"
        aext = ""
        if aug.get("volume_db"):
            aext += f",volume={aug['volume_db']:.2f}dB"
        filters.append(f"[{vi}:v]scale={breedte}:{hoogte}:force_original_aspect_ratio=decrease,"
                       f"pad={breedte}:{hoogte}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p,setsar=1{vext},"
                       f"trim=duration={s.duur:.3f},setpts=PTS-STARTPTS[v{i}]")
        filters.append(f"[{ai}:a]aresample=48000,aformat=channel_layouts=stereo{aext},atrim=duration={s.duur:.3f},"
                       f"asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
        waarheid.append({"label": s.label, "start": round(t, 3), "eind": round(t + s.duur, 3),
                         "bron": s.bron.name, "bron_start": s.start, **({"augmentatie": aug} if aug else {})})
        t += s.duur
    filters.append("".join(labels) + f"concat=n={len(segmenten)}:v=1:a=1[v][a]")
    ctx.ff.ffmpeg([*invoer, "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-c:a", "aac", "-b:a", "96k",
                   *(extra_uit or []), *BITEXACT, str(doel)])
    return waarheid


# --- ondertitels ----------------------------------------------------------------------------------------------------

_TIJD = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")


@dataclass
class Cue:
    start: float
    eind: float
    tekst: str


def lees_srt(pad: Path) -> list[Cue]:
    """Tolerant: ook cues waar de tekst direct achter de tijdcode staat (sintel_nl.srt, CORPUS §2.1)."""
    ruw = pad.read_bytes().decode("utf-8-sig", "replace").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []
    for regel_blok in re.split(r"\n\s*\n", ruw):
        regels = [r for r in regel_blok.split("\n") if r.strip()]
        for i, r in enumerate(regels):
            tijden = _TIJD.findall(r)
            if len(tijden) >= 2 and "-->" in r:
                na = r.split("-->", 1)[1]
                rest_na = _TIJD.sub("", na, count=1).strip()
                tekst = "\n".join(([rest_na] if rest_na else []) + regels[i + 1:]).strip()
                cues.append(Cue(_sec(tijden[0]), _sec(tijden[1]), tekst))
                break
    return cues


def _sec(t: tuple[str, str, str, str]) -> float:
    h, m, s, ms = t
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def _tijd(sec: float) -> str:
    sec = max(sec, 0.0)
    ms = int(round(sec * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def schrijf_srt(cues: list[Cue]) -> str:
    return "".join(f"{i}\n{_tijd(c.start)} --> {_tijd(c.eind)}\n{c.tekst}\n\n" for i, c in enumerate(cues, 1))
