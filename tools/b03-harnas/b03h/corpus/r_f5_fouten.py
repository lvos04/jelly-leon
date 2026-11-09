"""F5 — gecontroleerde-foutenset (B03 2.0 F5.9.3, J-TEST F5-2 / H-ALG-5).

(1) Playwright-init-scripts die ``HTMLMediaElement.canPlayType`` en ``MediaSource.isTypeSupported`` voor één
codec/container laten liegen (Chromium en Firefox); (2) een geforceerd Android-profiel dat AC3/E-AC3/DTS als Direct Play
aanbiedt (de emulator mist die decoders); (3) het echte geval WebKit + Sintel. Devset = 3 combinaties (afstemmen),
testset = ≥ 5 andere combinaties × 3 clients, bevroren vóór het afstemmen. Plus het ASS-recept (K7).
"""

from __future__ import annotations

import json

from .basis import Context
from .r_ass_groot import maak_ass

# (sleutel, codecpatroon in canPlayType/isTypeSupported, corpusitem dat zo'n stroom heeft)
DEV = [
    {"id": "dev-chromium-hevc8", "client": "chromium", "liegt_over": ["hvc1", "hev1"],
     "item": "jellyfin-testvideos/Test_Jellyfin_1080p_HEVC_8bit_10M.mp4"},
    {"id": "dev-firefox-ac3", "client": "firefox", "liegt_over": ["ac-3", "ac3"], "item": "blender/sintel/Sintel.2010.1080p.mkv"},
    {"id": "dev-webkit-sintel-echt", "client": "webkit", "liegt_over": [], "item": "blender/sintel/Sintel.2010.1080p.mkv",
     "toelichting": "echt geval: WebKit/Linux kiest Direct Play voor mkv + AC3 en blijft op readyState 0 (analyse 5 §6.2)"},
]
TEST_COMBOS = [
    {"id": "hevc10-hdr10", "liegt_over": ["hvc1.2", "hev1.2"], "item": "jellyfin-testvideos/Test_Jellyfin_1080p_HEVC_HDR10_10M.mp4"},
    {"id": "eac3-51", "liegt_over": ["ec-3", "eac3"], "item": "afgeleid:formaten/sintel-30s-av1-svt.mkv"},
    {"id": "dv-p5", "liegt_over": ["dvh1", "dvhe"], "item": "jellyfin-testvideos/Test_Jellyfin_1080p_DV_P5.mp4"},
    {"id": "flac-51-mkv", "liegt_over": ["flac"], "item": "afgeleid:formaten/sintel-30s-hevc8-flac.mkv"},
    {"id": "mpeg2-ts", "liegt_over": ["mp2t", "mpeg2", "mp2v"], "item": "afgeleid:formaten/sintel-30s-mpeg2-ac3.ts"},
    {"id": "h264-10bit", "liegt_over": ["avc1.6e", "avc1.6E"], "item": "afgeleid:formaten/sintel-30s-h264-10bit.mkv"},
]
TEST_CLIENTS = ["chromium", "firefox", "android-telefoon"]
ONTBREKEND = {
    "dts": "geen DTS-bron met licentie in het corpus (CORPUS §4); combinatie Geblokkeerd",
    "pgs": "PGS/VobSub niet te maken uit tekst (gemeten: '-c:s dvdsub' uit SRT faalt); combinatie Geblokkeerd",
}


def init_script(patronen: list[str]) -> str:
    """JS voor page.addInitScript: meldt 'probably'/true voor de patronen, ongeacht wat de decoder kan."""
    lijst = json.dumps([p.lower() for p in patronen])
    return (
        "(() => {\n"
        f"  const LIEGT = {lijst};\n"
        "  const raakt = (t) => LIEGT.some((p) => String(t || '').toLowerCase().includes(p));\n"
        "  const cpt = HTMLMediaElement.prototype.canPlayType;\n"
        "  HTMLMediaElement.prototype.canPlayType = function (t) { return raakt(t) ? 'probably' : cpt.call(this, t); };\n"
        "  if (window.MediaSource && MediaSource.isTypeSupported) {\n"
        "    const its = MediaSource.isTypeSupported.bind(MediaSource);\n"
        "    MediaSource.isTypeSupported = (t) => (raakt(t) ? true : its(t));\n"
        "  }\n"
        "  window.__b03_liegt = LIEGT;\n"
        "})();\n"
    )


def android_profiel() -> dict:
    """Geforceerd DeviceProfile (telefoonemulator): AC3/E-AC3/DTS als Direct Play terwijl de decoders ontbreken."""
    return {
        "Name": "b03-geforceerd-android-ac3-eac3-dts", "MaxStreamingBitrate": 120000000,
        "DirectPlayProfiles": [{"Container": "mkv,mp4,mov,ts", "Type": "Video", "VideoCodec": "h264,hevc,vp9,av1",
                                "AudioCodec": "aac,mp3,opus,flac,ac3,eac3,dts"}],
        "TranscodingProfiles": [{"Container": "ts", "Type": "Video", "VideoCodec": "h264", "AudioCodec": "aac",
                                 "Protocol": "hls", "Context": "Streaming"}],
        "CodecProfiles": [], "SubtitleProfiles": [{"Format": "srt", "Method": "External"}],
        "_toelichting": "liegt over ac3/eac3/dts; de emulator heeft die decoders niet (analyse 5 §2.2)",
    }


def maak(ctx: Context) -> None:
    ctx.synthetisch()
    for combo in DEV:
        if not combo["item"].startswith("afgeleid:"):
            ctx.bron(combo["item"])
        if combo["liegt_over"]:
            ctx.tekst(f"init-scripts/{combo['id']}.js", init_script(combo["liegt_over"]))
    test = []
    for combo in TEST_COMBOS:
        if not combo["item"].startswith("afgeleid:"):
            ctx.bron(combo["item"])
        for client in TEST_CLIENTS:
            cid = f"test-{client}-{combo['id']}"
            if client == "android-telefoon":
                bron = "android-profielen/geforceerd-ac3-eac3-dts.json"
            else:
                bron = f"init-scripts/{cid}.js"
                ctx.tekst(bron, init_script(combo["liegt_over"]))
            test.append({**combo, "id": cid, "client": client, "middel": bron,
                         "verwacht": "eerste start: Direct Play gekozen en het orakel faalt (onterechte DP); "
                                     "tweede start na leren: 0 onterechte DP (K1)"})
            ctx.tel("testset-combinatie")
    ctx.json("android-profielen/geforceerd-ac3-eac3-dts.json", android_profiel())
    ctx.tel("devset-combinatie", len(DEV))
    ctx.json("grondwaarheid.json", {
        "recept": "f5-fouten", "devset": DEV, "testset": test, "ontbrekend": ONTBREKEND,
        "orakel": "faalt als binnen 10 s geen currentTime ≥ 2 s, videoWidth = 0, een error-event of stilte bij een item met audio",
        "regel": "devset alleen voor RestrictThreshold/StallTimeoutSeconds; testset bevroren vóór het afstemmen; rapport met n en "
                 "Wilson-interval",
        "afgeleid_prefix": "items met 'afgeleid:' verwijzen naar media-corpus/afgeleid/ (bestaand corpus, niet opnieuw gemaakt)",
    })
    maak_ass(ctx)
