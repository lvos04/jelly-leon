from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HARNAS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNAS))


def ffmpeg_beschikbaar() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _srt(n: int, taal: str, stap: float = 11.0) -> str:
    regels = []
    for i in range(n):
        s, e = 5 + i * stap, 5 + i * stap + 3.5
        regels.append(f"{i + 1}\n{_t(s)} --> {_t(e)}\n[{taal}] regel {i} met wat tekst {i * 7 % 13}\n")
    return "\n".join(regels) + "\n"


def _t(x: float) -> str:
    ms = int(round(x * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


@pytest.fixture(scope="session")
def mini_corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Klein synthetisch 'corpus' met dezelfde paden als het echte (alleen lavfi-materiaal, geen rechten van derden).

    Lage resolutie en 2 fps, zodat lange bronnen (de recepten zoeken tot ~830 s) in een paar seconden te maken zijn."""
    if not ffmpeg_beschikbaar():
        pytest.skip("ffmpeg ontbreekt")
    corpus = tmp_path_factory.mktemp("corpus")
    bron = corpus / "bron"

    def video(rel: str, duur: float, extra_in: list[str] | None = None, extra_uit: list[str] | None = None) -> None:
        pad = bron / rel
        pad.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=128x72:r=2:d={duur}",
                        "-f", "lavfi", "-i", f"sine=f=440:r=48000:d={duur}", *(extra_in or []), "-map", "0:v", "-map", "1:a",
                        *(extra_uit or []), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-g", "4",
                        "-c:a", "aac", "-b:a", "48k", "-shortest", str(pad)], check=True)

    video("blender/hero/hero.mp4", 30)
    for rel in ("blender/spring/Spring-Blender-Open-Movie.mkv", "blender/cosmos/Cosmos_Laundromat_First_Cycle_2k.mp4",
                "blender/ed/elephantsdream-720-h264-st-aac.mov", "blender/caminandes/02_gran_dillama_1080p.mp4",
                "blender/caminandes/Caminandes_Llamigos-1080p.mp4", "blender/tos/uitgepakt/tears_of_steel_1080p.mov",
                "blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4"):
        video(rel, 900)
    subs = corpus / "tmp-subs"
    subs.mkdir()
    (subs / "eng.srt").write_text(_srt(60, "en"), encoding="utf-8")
    (subs / "dut.srt").write_text(_srt(60, "nl"), encoding="utf-8")
    video("blender/sintel/Sintel.2010.1080p.mkv", 900,
          extra_in=["-i", str(subs / "eng.srt"), "-i", str(subs / "dut.srt")],
          extra_uit=["-map", "2:s", "-map", "3:s", "-c:s", "srt", "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=dut"])
    shutil.rmtree(subs)
    for rel in ("blender/ed/1-TheWires.mp3", "blender/ed/5-EndTitle.mp3"):
        pad = bron / rel
        pad.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=330:d=95", "-c:a", "libmp3lame", str(pad)],
                       check=True)
    tos = bron / "blender/tos/subs"
    tos.mkdir(parents=True)
    for taal in ("en", "nl", "de", "es", "fr-orig", "it", "no", "Dansk"):
        (tos / f"TOS-{taal}.srt").write_text(_srt(64, taal), encoding="utf-8")
    sintel = bron / "blender/sintel/subs"
    sintel.mkdir(parents=True)
    for taal in ("nl", "fr", "swe", "pl", "da", "ru"):
        (sintel / f"sintel_{taal}.srt").write_text(_srt(60, taal), encoding="utf-8")
    jf = bron / "jellyfin-testvideos"
    jf.mkdir(parents=True)
    for naam in ("Test_Jellyfin_1080p_HEVC_8bit_10M.mp4", "Test_Jellyfin_1080p_HEVC_HDR10_10M.mp4", "Test_Jellyfin_1080p_DV_P5.mp4"):
        shutil.copyfile(bron / "blender/hero/hero.mp4", jf / naam)
    return corpus
