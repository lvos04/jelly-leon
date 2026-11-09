"""Baselinemetingen tegen STOCK jellyfin/jellyfin (B03-016 deel c; B03 2.0 §10.15).

Twee baselines op dezelfde server en dezelfde datamap: (a) stock-standaard en (b) stock-best (profielen/stock-best.json:
handmatige QSV met tonemapping en low-power op de iGPU van de ontwikkelmachine). Meetprotocol: exclusief meetslot onder
stack.lock, A/B afwisselend, ≥ 3 runs, loadavg en CPU per run, een run boven de lastgrens is ongeldig; proporties met n en
Wilson-95 %-interval (gate-label of 'smoke-gate (n = …)'), continue waarden met een t-interval over de runs; elke metriek
krijgt een herhaling die binnen het interval van de eerste meting moet vallen.

Metingen:
  dp         Direct Play-beslissingen met de echte jellyfin-web-profielen (Chromium, Firefox, WebKit) — F5 B1/K3
  orakel     effectieve Direct Play: elk item echt afspelen (currentTime ≥ 2 s, beeld, geen fout, geen stilte) — F5 K1/K3
  transcode  DV P8.1 en HEVC10-HDR10 in een echte websessie: snelheid, CPU per mediaseconde, eerste frame — F5 B5/B5b/K6, F1 B11
  functies   API-baselines F2 (koude start), F3 (NL-ondertitels zoeken), F4 (kwaliteitsmeldingen), F6 (MediaSegments)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import bewijs, meetslot, statistiek
from .stock import GEBRUIKER, STOCK_IMAGE, WACHTWOORD, StockServer, docker, profiel
from .web import WebFout, harnas

REPO = Path(__file__).resolve().parents[3]
EVIDENCE_MAP = REPO / "docs" / "platform-v2" / "test-evidence"
BROWSERS = ["chromium", "firefox", "webkit"]
# De 25 items van analyse 5 §6.2 (vergelijkbaar houden) + ToS en BBB als aparte extra set (F5.9.3).
A5_SET = [f"/media/movies/blender/{p}" for p in (
    "caminandes/01_llama_drama_1080p.mp4", "caminandes/02_gran_dillama_1080p.mp4", "caminandes/Caminandes_Llamigos-1080p.mp4",
    "cosmos/Cosmos_Laundromat_First_Cycle_2k.mp4", "ed/elephantsdream-720-h264-st-aac.mov", "hero/hero.mp4",
    "sintel/Sintel.2010.1080p.mkv", "spring/Spring-Blender-Open-Movie.mkv")] + [
    f"/media/movies/jellyfin-testvideos/Test_Jellyfin_{n}.mp4" for n in (
        "1080p_AV1_10bit_10M", "1080p_AV1_HDR10_10M", "1080p_AVC_10M", "1080p_DV_P5", "1080p_DV_P8.1", "1080p_DV_P8.4",
        "1080p_HEVC_10bit_10M", "1080p_HEVC_8bit_10M", "1080p_HEVC_HDR10_10M", "4K_DV_P8.1", "4K_HEVC_HDR10_40M")] + [
    f"/media/series/Pioneer One/Pioneer.One.S01E0{i}.720p.x264-VODO.mp4" for i in range(1, 7)]
EXTRA_SET = ["/media/movies/blender/tos/uitgepakt/tears_of_steel_1080p.mov",
             "/media/movies/blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4"]
TRANSCODE_ITEMS = {"dv-p8.1-1080p": "/media/movies/jellyfin-testvideos/Test_Jellyfin_1080p_DV_P8.1.mp4",
                   "hevc10-hdr10-1080p": "/media/movies/jellyfin-testvideos/Test_Jellyfin_1080p_HEVC_HDR10_10M.mp4"}
SEGMENT_ITEMS_PREFIX = ("/media/afgeleid/series/", "/media/series/Pioneer One/")
KWALITEIT = {
    "beschadigd-midden": "/media/afgeleid/kwaliteit/sintel-60s-beschadigd-midden.mkv",
    "afgekapt-70pct": "/media/afgeleid/kwaliteit/sintel-60s-afgekapt-70pct.mkv",
    "stilte-25-33s": "/media/afgeleid/kwaliteit/sintel-60s-audio-stilte-25-33s.mkv",
    "clipping-40-43s": "/media/afgeleid/kwaliteit/sintel-60s-audio-clipping-40-43s.mkv",
    "zonder-audio": "/media/afgeleid/kwaliteit/sintel-60s-zonder-audio.mkv",
    "verkeerde-taaltags": "/media/afgeleid/kwaliteit/tos-120s-verkeerde-taaltags.mkv",
    "me-als-hoofdspoor": "/media/afgeleid/kwaliteit/tos-120s-me-als-hoofdspoor.mkv",
    "hlg-tag-op-hdr10": "/media/afgeleid/formaten/hdr10-als-hlg-tag.mkv",
}
ONDERTITEL_ITEMS = ["/media/movies/blender/sintel/Sintel.2010.1080p.mkv", "/media/movies/blender/tos/uitgepakt/tears_of_steel_1080p.mov",
                    "/media/movies/blender/hero/hero.mp4", "/media/movies/blender/spring/Spring-Blender-Open-Movie.mkv"]
TICKS = 10_000_000


def log(tekst: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {tekst}", flush=True)


class Sessie:
    """Eén server, twee systemen (encoding-profiel wisselen per run), alles onder het meetslot."""

    def __init__(self, server: StockServer) -> None:
        self.s = server
        assert server.jf
        self.jf = server.jf
        self.items = {it["Path"]: it for it in self.jf.items()}
        self.standaard_encoding = self.jf.encoding()
        self.best = profiel("stock-best")
        self.config_hash: dict[str, str] = {}
        self.huidig = ""

    def systeem(self, naam: str) -> None:
        if naam == self.huidig:
            return
        doel = {**self.standaard_encoding, **(self.best["encoding"] if naam == "stock-best" else {})}
        na = self.jf.zet_encoding(doel)
        afwijkend = {k: (na.get(k), v) for k, v in doel.items() if na.get(k) != v}
        if afwijkend:
            raise RuntimeError(f"encoding-profiel {naam} niet overgenomen: {afwijkend}")
        self.config_hash[naam] = hashlib.sha256(json.dumps(na, sort_keys=True).encode()).hexdigest()
        self.huidig = naam

    def web(self, browser: str, items: list[str], opdracht: str = "speel", **extra: Any) -> dict[str, Any]:
        cfg = {"browser": browser, "url": self.s.url, "gebruiker": GEBRUIKER, "wachtwoord": WACHTWOORD,
               "items": [{"id": self.items[p]["Id"], "naam": Path(p).stem} for p in items], **extra}
        return harnas(opdracht, cfg)


def _run_record(last: meetslot.RunLast, **waarden: Any) -> dict[str, Any]:
    return {"last": last.als_dict(), **waarden}


def geldige_run(systeem: str, r: int, containers: list[str], actie: Any, pogingen: int = 3) -> tuple[meetslot.RunLast, Any, list[dict]]:
    """Herhaalt een tijdgevoelige run (begrensd) tot hij geldig is; ongeldige pogingen blijven in het bewijs staan."""
    ongeldig: list[dict] = []
    for poging in range(pogingen):
        wacht = meetslot.wacht_op_rust(max_wacht=120)
        with meetslot.run(systeem, r, containers) as last:
            uitkomst = actie()
        if last.geldig or poging == pogingen - 1:
            last_d = last
            if not last.geldig:
                log(f"  run {systeem}#{r} blijft ongeldig na {pogingen} pogingen: {last.reden}")
            return last_d, uitkomst, ongeldig
        log(f"  run {systeem}#{r} ongeldig ({last.reden}); opnieuw (wachttijd vooraf {wacht:.0f} s)")
        ongeldig.append({"poging": poging, "last": last.als_dict()})
    raise AssertionError("onbereikbaar")


# --- dp: beslissingen ---------------------------------------------------------------------------------------------

def meet_dp(sessie: Sessie, runs: int, uitmap: Path) -> list[dict[str, Any]]:
    profielen: dict[str, dict[str, Any]] = {}
    sessie.systeem("stock-standaard")
    for b in BROWSERS:
        d = sessie.web(b, ["/media/movies/blender/sintel/Sintel.2010.1080p.mkv"], "profiel", orakelMs=4000)
        if not d.get("deviceProfile"):
            raise RuntimeError(f"geen DeviceProfile van {b}: {d.get('items')}")
        profielen[b] = {"versie": d["versie"], "profiel": d["deviceProfile"]}
        (uitmap / f"deviceprofile-{b}.json").write_text(json.dumps(d["deviceProfile"], indent=1) + "\n", encoding="utf-8")
    per: dict[tuple[str, str], list[dict[str, Any]]] = {}
    matrix: dict[str, Any] = {}
    for r, systeem in meetslot.ab_volgorde(["stock-standaard", "stock-best"], runs):
        sessie.systeem(systeem)
        with meetslot.run(systeem, r, [sessie.s.container_id]) as last:
            uitkomst: dict[str, Any] = {}
            kaal: dict[str, Any] = {}
            for b in BROWSERS:
                besluiten, kale = {}, {}
                for p in A5_SET + EXTRA_SET:
                    it = sessie.items[p]
                    besluiten[Path(p).name] = _besluit(sessie.jf.playbackinfo(it["Id"], profielen[b]["profiel"], extra=_als_web(it)))
                    kale[Path(p).name] = _besluit(sessie.jf.playbackinfo(it["Id"], profielen[b]["profiel"]))
                uitkomst[b] = besluiten
                kaal[b] = kale
        for b in BROWSERS:
            k = sum(1 for p in A5_SET if uitkomst[b][Path(p).name].startswith("DirectPlay"))
            k_kaal = sum(1 for p in A5_SET if kaal[b][Path(p).name].startswith("DirectPlay"))
            afwijkend = sorted(n for n in uitkomst[b] if uitkomst[b][n] != kaal[b][n])
            per.setdefault((systeem, b), []).append(_run_record(last, k=k, n=len(A5_SET), k_kale_aanvraag=k_kaal,
                                                                kale_aanvraag_wijkt_af=afwijkend))
        matrix[f"{systeem}#{r}"] = {"zoals_webclient": uitkomst, "kale_aanvraag": kaal}
    (uitmap / "dp-matrix.json").write_text(json.dumps(matrix, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    metingen = []
    for (systeem, b), rs in sorted(per.items()):
        eerste = rs[0]
        iv = statistiek.wilson(eerste["k"], eerste["n"])
        herhaald = [x["k"] / x["n"] for x in rs[1:]]
        metingen.append(bewijs.metriek(
            id=f"F5-B1-dp-beslissing-{b}", functie="F5", systeem=systeem, soort="proportie", image=STOCK_IMAGE, seed=None,
            omschrijving=f"Direct Play-beslissingen met het echte jellyfin-web-profiel van {b} {profielen[b]['versie']} (25 items, A5-set)",
            methode="DeviceProfile gevangen uit POST /Items/{id}/PlaybackInfo van de echte webclient; daarna PlaybackInfo per item "
                    "via de API met dezelfde velden als de webclient (MediaSourceId, AudioStreamIndex = standaard audiospoor, "
                    "SubtitleStreamIndex -1, IsPlayback, StartTimeTicks 0); DirectPlay = MediaSources[0].SupportsDirectPlay. "
                    "Ter vergelijking ook de 'kale' aanvraag zonder die velden (gemeten: 12.4 toetst de audiocodec dan niet)",
            runs=rs, n=eerste["n"], waarde={"k": eerste["k"], "herhalingen_k": [x["k"] for x in rs[1:]],
                                            "herhaling_binnen_interval": all(iv.bevat(h) for h in herhaald),
                                            "k_kale_aanvraag": eerste["k_kale_aanvraag"],
                                            "kale_aanvraag_wijkt_af": eerste["kale_aanvraag_wijkt_af"]},
            interval=iv, gate=statistiek.gate_label(eerste["n"], 20), eenheid="aandeel items",
            opmerking="beslissing alleen (niet of het echt speelt; zie F5-K3-dp-effectief); WebKit op Linux is geen Safari"))
    return metingen


def _besluit(pi: dict[str, Any]) -> str:
    ms = (pi.get("MediaSources") or [{}])[0]
    tu = ms.get("TranscodingUrl") or ""
    besluit = ("DirectPlay" if ms.get("SupportsDirectPlay") else "DirectStream" if ms.get("SupportsDirectStream")
               else "Transcode" if ms.get("SupportsTranscoding") else "Geen")
    m = re.search(r"TranscodeReasons=([^&]*)", tu)
    return besluit + (f" ({m.group(1)})" if m else "")


def _als_web(item: dict[str, Any]) -> dict[str, Any]:
    """De velden die jellyfin-web 12.4 zelf meestuurt. Gemeten: zonder MediaSourceId + AudioStreamIndex toetst 12.4 de
    audiocodec niet en meldt het DirectPlay voor mkv + AC3, ook als het profiel geen AC3 kent."""
    audio = [s for s in item.get("MediaStreams") or [] if s.get("Type") == "Audio"]
    standaard = next((s for s in audio if s.get("IsDefault")), audio[0] if audio else None)
    extra: dict[str, Any] = {"MediaSourceId": item["Id"], "SubtitleStreamIndex": -1, "IsPlayback": True, "StartTimeTicks": 0}
    if standaard is not None:
        extra["AudioStreamIndex"] = standaard["Index"]
    return extra


# --- orakel: effectieve Direct Play ---------------------------------------------------------------------------------

def meet_orakel(sessie: Sessie, uitmap: Path) -> list[dict[str, Any]]:
    resultaten: dict[tuple[str, str], list[dict[str, Any]]] = {}
    fouten: list[dict[str, Any]] = []
    for r, systeem in [(0, "stock-standaard"), (0, "stock-best"), (1, "stock-standaard")]:
        sessie.systeem(systeem)
        for b in BROWSERS:
            try:
                last, d, ongeldig = geldige_run(systeem, r, [sessie.s.container_id],
                                                lambda b=b: sessie.web(b, A5_SET + EXTRA_SET, "speel", orakelMs=10000))
            except WebFout as fout:
                log(f"orakel {systeem} {b} run {r}: harnasfout {fout}")
                fouten.append({"systeem": systeem, "browser": b, "run": r, "fout": str(fout)[:400]})
                continue
            items = d["items"]
            a5 = [i for i in items if any(Path(p).stem == i["naam"] for p in A5_SET)]
            dp = [i for i in a5 if i.get("besluit") == "DirectPlay"]
            dp_ok = [i for i in dp if i.get("orakel_ok")]
            alle_ok = [i for i in a5 if i.get("orakel_ok")]
            (uitmap / f"orakel-{systeem}-{b}-run{r}.json").write_text(
                json.dumps({**d, "items": [{k: v for k, v in i.items() if k != "spoor"} for i in items]}, indent=1,
                           ensure_ascii=False) + "\n", encoding="utf-8")
            resultaten.setdefault((systeem, b), []).append(_run_record(
                last, n=len(a5), dp=len(dp), dp_ok=len(dp_ok), speelt=len(alle_ok),
                onterechte_dp=[i["naam"] for i in dp if not i.get("orakel_ok")],
                niet_speelbaar=[i["naam"] for i in a5 if not i.get("orakel_ok")],
                eerste_frame_ms=[i.get("eerste_frame_ms") for i in a5], ongeldige_pogingen=ongeldig))
            log(f"orakel {systeem} {b} run {r}: DP {len(dp)}, DP speelt {len(dp_ok)}, speelt {len(alle_ok)}/{len(a5)}")
    metingen = []
    for (systeem, b), rs in sorted(resultaten.items()):
        geldig = [x for x in rs if x["last"]["geldig"]]
        eerste = (geldig or rs)[0]
        rs = [eerste] + [x for x in rs if x is not eerste]
        iv = statistiek.wilson(eerste["dp_ok"], eerste["n"])
        iv_alle = statistiek.wilson(eerste["speelt"], eerste["n"])
        herhaling = [x["dp_ok"] / x["n"] for x in rs[1:]]
        metingen.append(bewijs.metriek(
            id=f"F5-K3-dp-effectief-{b}", functie="F5", systeem=systeem, soort="proportie", image=STOCK_IMAGE, seed=None,
            omschrijving=f"Direct Play-starts die het orakel halen, {b} (A5-set, 25 items)",
            methode="elk item via de UI starten (Playwright 1.63); orakel = binnen 10 s currentTime ≥ 2 s, videoWidth > 0, geen "
                    "error-event en geen stilte bij een item met audio (Chromium/WebKit: webkitAudioDecodedByteCount; Firefox: "
                    "mozHasAudio); daarna DELETE /Videos/ActiveEncodings",
            runs=rs, n=eerste["n"], interval=iv, gate=statistiek.gate_label(eerste["n"], 20), eenheid="aandeel items",
            waarde={"k_dp_effectief": eerste["dp_ok"], "dp_gekozen": eerste["dp"], "onterechte_dp": eerste["onterechte_dp"],
                    "speelt_totaal": eerste["speelt"], "speelt_interval": iv_alle.als_dict(),
                    "niet_speelbaar": eerste["niet_speelbaar"], "herhalingen_k": [x["dp_ok"] for x in rs[1:]],
                    "herhaling_binnen_interval": all(iv.bevat(h) for h in herhaling) if herhaling else None},
            opmerking="WebKit op Linux is geen Safari; headless browsers zonder HDR-scherm"))
    if fouten:
        (uitmap / "orakel-harnasfouten.json").write_text(json.dumps(fouten, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return metingen


# --- transcode: iGPU ----------------------------------------------------------------------------------------------

_VOORTGANG = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)\s.*?speed=\s*([\d.]+)x")


def _lees_transcodelog(pad: Path) -> dict[str, Any]:
    tekst = pad.read_text(encoding="utf-8", errors="replace")
    treffers = _VOORTGANG.findall(tekst)
    uit: dict[str, Any] = {"log": pad.name}
    if treffers:
        h, m, s, snelheid = treffers[-1]
        uit["media_s"] = int(h) * 3600 + int(m) * 60 + float(s)
        uit["snelheid_x"] = float(snelheid)
    cmd = next((r for r in tekst.splitlines() if "ffmpeg" in r and " -i " in r), "")
    uit["video_encoder"] = next((e for e in ("h264_qsv", "hevc_qsv", "av1_qsv", "h264_vaapi", "libx264", "libx265", "copy")
                                 if f"-codec:v:0 {e}" in cmd or f"-c:v {e}" in cmd or f"-vcodec {e}" in cmd), "onbekend")
    uit["tonemap"] = next((t for t in ("tonemap_opencl", "vpp_qsv", "tonemap_vaapi", "tonemapx", "zscale") if t in cmd), None)
    uit["hwaccel"] = (re.search(r"-hwaccel (\w+)", cmd) or [None, None])[1]
    return uit


def meet_transcode(sessie: Sessie, runs: int, uitmap: Path) -> list[dict[str, Any]]:
    per: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r, systeem in meetslot.ab_volgorde(["stock-standaard", "stock-best"], runs):
        sessie.systeem(systeem)
        for sleutel, pad in TRANSCODE_ITEMS.items():
            staat: dict[str, Any] = {}

            def actie(pad: str = pad, staat: dict[str, Any] = staat) -> dict[str, Any]:
                staat["voor"] = {p.name for p in sessie.s.transcodelogs()}
                staat["cpu0"] = meetslot.container_cpu_seconden(sessie.s.container_id) or 0.0
                d = sessie.web("chromium", [pad], "speel", orakelMs=15000, duurMs=20000)
                staat["cpu1"] = meetslot.container_cpu_seconden(sessie.s.container_id) or 0.0
                return d

            last, d, ongeldig = geldige_run(systeem, r, [sessie.s.container_id], actie)
            cpu = staat["cpu1"] - staat["cpu0"]
            nieuw = [p for p in sessie.s.transcodelogs() if p.name not in staat["voor"]]
            info = _lees_transcodelog(nieuw[-1]) if nieuw else {"log": None}
            item = d["items"][0]
            media_s = info.get("media_s") or 0.0
            rec = _run_record(last, ongeldige_pogingen=ongeldig, eerste_frame_ms=item.get("eerste_frame_ms"),
                              orakel_ok=item.get("orakel_ok"), besluit=item.get("besluit"), redenen=item.get("redenen"),
                              container_cpu_s=round(cpu, 2), cpu_s_per_media_s=round(cpu / media_s, 3) if media_s else None,
                              kernen_tijdens_transcode=round(cpu / (media_s / info["snelheid_x"]), 2)
                              if media_s and info.get("snelheid_x") else None, **info)
            per.setdefault((systeem, sleutel), []).append(rec)
            log(f"transcode {systeem} {sleutel} run {r}: {info.get('snelheid_x')}x {info.get('video_encoder')} "
                f"{info.get('tonemap')} eerste frame {item.get('eerste_frame_ms')} ms, geldig={last.geldig} {last.reden}")
    (uitmap / "transcode-runs.json").write_text(json.dumps({f"{k[0]}|{k[1]}": v for k, v in per.items()}, indent=1) + "\n",
                                                encoding="utf-8")
    metingen = []
    for (systeem, sleutel), rs in sorted(per.items()):
        geldig = [x for x in rs if x["last"]["geldig"] and x.get("snelheid_x")]
        for veld, eenheid, label in (("snelheid_x", "× realtime", "snelheid"), ("cpu_s_per_media_s", "CPU-s per media-s", "cpu"),
                                     ("eerste_frame_ms", "ms", "eerste-frame")):
            waarden = [float(x[veld]) for x in geldig if x.get(veld) is not None]
            if not waarden:
                continue
            iv = statistiek.t_interval(waarden)
            metingen.append(bewijs.metriek(
                id=f"F5-K6-transcode-{sleutel}-{label}", functie="F5", systeem=systeem, soort="continu", image=STOCK_IMAGE,
                seed=None, eenheid=eenheid,
                omschrijving=f"{sleutel} → H.264 SDR in een echte Chromium-websessie (VideoCodecNotSupported), {label}",
                methode="Chromium 153 speelt 20 s via de UI; snelheid en mediatijd uit het FFmpeg.Transcode-log van de server, "
                        "CPU uit de cgroup van de container (server + ffmpeg), eerste frame = 'playing' − klik",
                runs=rs, n=len(waarden), interval=iv, gate=statistiek.gate_label(len(waarden), 3),
                waarde={"gemiddelde": round(statistiek.gemiddelde(waarden), 3), "waarden": waarden,
                        "encoder": sorted({x.get("video_encoder") for x in geldig}), "tonemap": sorted({str(x.get("tonemap")) for x in geldig}),
                        "voorspellingsinterval": statistiek.voorspellingsinterval(waarden).als_dict()},
                opmerking=("Intel-iGPU-getest (ontwikkelmachine): Meteor Lake-iGPU via /dev/dri/renderD128; geen capaciteit van A310/UHD 770 "
                           "(NIET GEVALIDEERD (hardware))") if systeem == "stock-best" else "software (stock zet HW-versnelling niet zelf aan)",
                validatie="Sim-getest; NIET GEVALIDEERD (hardware)"))
    return metingen


# --- functies: F2/F3/F4/F6 ----------------------------------------------------------------------------------------

def _functies_een_run(sessie: Sessie) -> dict[str, Any]:
    jf = sessie.jf
    seg_items = [p for p in sessie.items if p.startswith(SEGMENT_ITEMS_PREFIX)]
    segmenten = {Path(p).name: jf.a.doe("GET", f"/MediaSegments/{sessie.items[p]['Id']}").get("TotalRecordCount", 0) for p in seg_items}
    ondertitels = {}
    for p in ONDERTITEL_ITEMS:
        res = jf.a.doe("GET", f"/Items/{sessie.items[p]['Id']}/RemoteSearch/Subtitles/nld", verwacht=(200, 204, 404))
        ondertitels[Path(p).name] = len(res) if isinstance(res, list) else 0
    meldingen = jf.a.doe("GET", "/System/ActivityLog/Entries", {"limit": "500"}).get("Items", [])
    waarschuwingen = [m for m in meldingen if m.get("Severity") in ("Warning", "Error", "Critical")]
    kwaliteit = {}
    referentie = sessie.items.get("/media/afgeleid/kwaliteit/sintel-60s-referentie.mkv", {})
    for sleutel, p in KWALITEIT.items():
        it = sessie.items.get(p)
        if not it:
            kwaliteit[sleutel] = {"ontbreekt": True}
            continue
        naam = it.get("Name", "")
        gemeld = [m.get("Name") for m in waarschuwingen if naam and naam in json.dumps(m, ensure_ascii=False)]
        streams = (it.get("MediaStreams") or [])
        kwaliteit[sleutel] = {
            "gemeld": bool(gemeld), "meldingen": gemeld,
            "waarneming": {"runtime_s": round((it.get("RunTimeTicks") or 0) / TICKS, 2),
                           "referentie_runtime_s": round((referentie.get("RunTimeTicks") or 0) / TICKS, 2),
                           "audio_sporen": [f"{s.get('Codec')}/{s.get('Language')}" for s in streams if s.get("Type") == "Audio"],
                           "videorange": next((s.get("VideoRangeType") for s in streams if s.get("Type") == "Video"), None)}}
    aanbevelingen = jf.a.doe("GET", "/Movies/Recommendations", {"userId": jf.admin_id, "categoryLimit": "6", "itemLimit": "8"})
    suggesties = jf.a.doe("GET", "/Items/Suggestions", {"userId": jf.admin_id, "limit": "12"})
    serie = jf.a.doe("GET", "/Items", {"userId": jf.admin_id, "recursive": "true", "includeItemTypes": "Series",
                                       "searchTerm": "Pioneer"}).get("Items", [])
    similar_serie = jf.a.doe("GET", f"/Items/{serie[0]['Id']}/Similar", {"userId": jf.admin_id, "limit": "12"})["Items"] if serie else []
    similar_sintel = jf.a.doe("GET", f"/Items/{sessie.items['/media/movies/blender/sintel/Sintel.2010.1080p.mkv']['Id']}/Similar",
                              {"userId": jf.admin_id, "limit": "12"})["Items"]
    return {"segmenten": segmenten, "ondertitels_nld": ondertitels, "kwaliteit": kwaliteit,
            "aanbevelingen": {"categorieen": len(aanbevelingen or []),
                              "suggesties": len((suggesties or {}).get("Items", [])),
                              "similar_serie_pioneer": len(similar_serie), "similar_sintel": [i.get("Name") for i in similar_sintel]}}


def meet_functies(sessie: Sessie, runs: int, uitmap: Path) -> list[dict[str, Any]]:
    per: dict[str, list[dict[str, Any]]] = {}
    for r, systeem in meetslot.ab_volgorde(["stock-standaard", "stock-best"], runs):
        sessie.systeem(systeem)
        with meetslot.run(systeem, r, [sessie.s.container_id]) as last:
            uit = _functies_een_run(sessie)
        per.setdefault(systeem, []).append(_run_record(last, **uit))
    (uitmap / "functies-runs.json").write_text(json.dumps(per, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    metingen = []
    for systeem, rs in per.items():
        e = rs[0]

        def herhaald(sleutel: str, functie: Any, rs: list[dict[str, Any]] = rs) -> list[int]:
            return [functie(x[sleutel]) for x in rs[1:]]

        n_seg = len(e["segmenten"])
        k_seg = sum(1 for v in e["segmenten"].values() if v > 0)
        metingen.append(bewijs.metriek(
            id="F6-a-mediasegments", functie="F6", systeem=systeem, soort="proportie", image=STOCK_IMAGE, seed=None,
            omschrijving="afleveringen met bekende intro/recap/aftiteling/OP/ED waarvoor stock ≥ 1 MediaSegment publiceert",
            methode="GET /MediaSegments/{itemId} voor 8 synthetische afleveringen (devset) en 6 echte Pioneer One-afleveringen",
            runs=rs, n=n_seg, interval=statistiek.wilson(k_seg, n_seg), gate=statistiek.gate_label(n_seg, 30),
            waarde={"k": k_seg, "per_item": e["segmenten"],
                    "herhalingen_k": herhaald("segmenten", lambda v: sum(1 for x in v.values() if x > 0))},
            eenheid="aandeel items", opmerking="voormeting; de F6-testset (n ≥ 60) komt uit de corpusgenerator (B03-070)"))
        n_ot = len(e["ondertitels_nld"])
        k_ot = sum(1 for v in e["ondertitels_nld"].values() if v > 0)
        metingen.append(bewijs.metriek(
            id="F3-a-ondertitels-nld-zoeken", functie="F3", systeem=systeem, soort="proportie", image=STOCK_IMAGE, seed=None,
            omschrijving="films waarvoor stock NL-ondertitels vindt (RemoteSearch, geen provider geïnstalleerd)",
            methode="GET /Items/{id}/RemoteSearch/Subtitles/nld", runs=rs, n=n_ot, interval=statistiek.wilson(k_ot, n_ot),
            gate=statistiek.gate_label(n_ot, 20), waarde={"k": k_ot, "per_item": e["ondertitels_nld"],
                                                          "herhalingen_k": herhaald("ondertitels_nld",
                                                                                    lambda v: sum(1 for x in v.values() if x > 0))},
            eenheid="aandeel items"))
        n_q = len([v for v in e["kwaliteit"].values() if not v.get("ontbreekt")])
        k_q = sum(1 for v in e["kwaliteit"].values() if v.get("gemeld"))
        metingen.append(bewijs.metriek(
            id="F4-a-kwaliteitsmeldingen", functie="F4", systeem=systeem, soort="proportie", image=STOCK_IMAGE, seed=None,
            omschrijving="bekende kwaliteitsfouten die stock meldt (activiteitslog Warning/Error over het item)",
            methode="na de scan: GET /System/ActivityLog/Entries; plus waarnemingen per item (runtime, audiosporen, VideoRangeType)",
            runs=rs, n=n_q, interval=statistiek.wilson(k_q, n_q), gate=statistiek.gate_label(n_q, 20),
            waarde={"k": k_q, "per_geval": e["kwaliteit"],
                    "herhalingen_k": herhaald("kwaliteit", lambda v: sum(1 for x in v.values() if x.get("gemeld")))},
            eenheid="aandeel gevallen", opmerking="R-QC-dev-gevallen (voormeting); de gate rust op T-QC uit de corpusgenerator"))
        metingen.append(bewijs.metriek(
            id="F2-a-koude-start", functie="F2", systeem=systeem, soort="telling", image=STOCK_IMAGE, seed=None,
            omschrijving="aanbevelingen zonder kijkgeschiedenis (koude start) en 'vergelijkbaar' voor de echte serie",
            methode="GET /Movies/Recommendations, /Items/Suggestions, /Items/{serie}/Similar, /Items/{Sintel}/Similar (admin, lege historie)",
            runs=rs, n=1, interval=None, waarde=e["aanbevelingen"] | {"herhalingen": [x["aanbevelingen"] for x in rs[1:]]},
            eenheid="aantal", opmerking="online metadata uit (zelfde metadata voor alle systemen); de echte F2-baseline (NDCG@10) "
                                         "vraagt D-SYN/MovieLens (B03-030)"))
    return metingen


# --- herhaling ----------------------------------------------------------------------------------------------------

def herbereken(document: dict[str, Any]) -> dict[str, Any]:
    """Afgeleide velden opnieuw uit de runs: herhalingen binnen het Wilson-interval (proporties) en het
    voorspellingsinterval (continu)."""
    for m in document.get("metingen", []):
        w = m.get("waarde") or {}
        iv = m.get("interval")
        if m["soort"] == "proportie" and iv and "herhalingen_k" in w and w["herhalingen_k"]:
            w["herhaling_binnen_interval"] = all(iv["onder"] <= k / m["n"] <= iv["boven"] for k in w["herhalingen_k"])
        if m["soort"] == "continu" and w.get("waarden"):
            w.pop("herhaling_binnen_interval_eerste_runs", None)
            w["voorspellingsinterval"] = statistiek.voorspellingsinterval([float(x) for x in w["waarden"]]).als_dict()
    return document


def voeg_herhaalsessie_toe(document: dict[str, Any], nieuw: list[dict[str, Any]], sessie: dict[str, Any]) -> list[str]:
    """Koppelt een volledig nieuwe meetsessie (nieuwe server) aan de bestaande metrieken: valt de herhaling binnen het
    interval van de eerste meting? Geeft de afwijkingen terug."""
    afwijkend = []
    index = {(m["id"], m["systeem"]): m for m in document.get("metingen", [])}
    for n in nieuw:
        oud = index.get((n["id"], n["systeem"]))
        if not oud:
            continue
        w, nw = oud["waarde"], n["waarde"]
        if oud["soort"] == "continu" and nw.get("waarden"):
            vi = w.get("voorspellingsinterval") or statistiek.voorspellingsinterval([float(x) for x in w["waarden"]]).als_dict()
            binnen = all(vi["onder"] <= float(x) <= vi["boven"] for x in nw["waarden"])
            w["herhaalsessie"] = {"waarden": nw["waarden"], "gemiddelde": nw.get("gemiddelde"), "runs": n["runs"],
                                  "binnen_voorspellingsinterval": binnen, **sessie}
        elif oud["soort"] == "proportie" and oud.get("interval"):
            k = nw.get("k", nw.get("k_dp_effectief"))
            binnen = oud["interval"]["onder"] <= k / n["n"] <= oud["interval"]["boven"]
            w["herhaalsessie"] = {"k": k, "n": n["n"], "binnen_wilson_interval": binnen, "runs": n["runs"], **sessie}
        else:
            w["herhaalsessie"] = {"waarde": nw, "runs": n["runs"], **sessie}
            binnen = True
        if not binnen:
            afwijkend.append(f"{n['id']} ({n['systeem']})")
    return afwijkend


# --- hoofdprogramma -----------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h baseline")
    p.add_argument("--metingen", default="dp,orakel,transcode,functies")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--label", default="voormeting-12.4", choices=sorted(bewijs.LABELS))
    p.add_argument("--uit", type=Path, default=EVIDENCE_MAP / "b03-016-baseline-voormeting-12.4.json")
    p.add_argument("--image", default=STOCK_IMAGE)
    p.add_argument("--browsers", default=",".join(BROWSERS), help="beperk dp/orakel tot deze browsers (komma-gescheiden)")
    p.add_argument("--herhaalsessie", action="store_true",
                   help="nieuwe meetsessie als herhaling van een bestaand bewijs: valt hij binnen het interval van de eerste meting?")
    p.add_argument("--aanvullen", action="store_true",
                   help="metingen toevoegen aan een bestaand bewijs (zelfde id + systeem wordt vervangen)")
    a = p.parse_args(argv)
    BROWSERS[:] = [b for b in a.browsers.split(",") if b]
    if a.runs < 3:
        print("meetprotocol: ≥ 3 runs (B03 2.0 §10.15)", file=sys.stderr)
        return 2
    metingen_gevraagd = a.metingen.split(",")
    uitmap = a.uit.with_suffix("")
    uitmap.mkdir(parents=True, exist_ok=True)
    begin = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with meetslot.exclusief_slot(bij_wachten=log) as wacht:
        log(f"meetslot stack.lock verkregen (na {wacht:.0f} s)")
        server = StockServer("baseline", image=a.image).start()
        try:
            scan_s = server.inrichten()
            log(f"stock {server.info.get('Version')} op {server.url}, scan {scan_s:.0f} s")
            sessie = Sessie(server)
            metingen: list[dict[str, Any]] = []
            fasefouten: dict[str, str] = {}
            fasen = {"dp": lambda: meet_dp(sessie, a.runs, uitmap), "orakel": lambda: meet_orakel(sessie, uitmap),
                     "transcode": lambda: meet_transcode(sessie, a.runs, uitmap),
                     "functies": lambda: meet_functies(sessie, a.runs, uitmap)}
            for m in metingen_gevraagd:
                log(f"meting {m} …")
                try:
                    metingen += fasen[m]()
                except Exception as fout:  # noqa: BLE001 - een mislukte fase wordt gemeld, de andere metingen blijven staan
                    log(f"meting {m} mislukt: {fout}")
                    fasefouten[m] = str(fout)[:600]
            repo_digests = docker("image", "inspect", "--format", "{{json .RepoDigests}}", a.image.split("@")[0], check=False).stdout
            lspci = subprocess.run(["lspci"], capture_output=True, text=True, check=False).stdout
            document = {
                "schema": bewijs.SCHEMA, "label": a.label, "begin": begin, "eind": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "images": {"stock": a.image}, "image_id_container": server.digest(), "repo_digests": repo_digests.strip(),
                "server": {"versie": server.info.get("Version"), "scan_s": round(scan_s, 1)},
                "machine": meetslot.machine() | {"gpu": [r for r in lspci.splitlines() if "VGA" in r or "Display" in r]},
                "protocol": {"meetslot": "stack.lock (exclusief), zware sloten gradle.lock/docker-build.lock gecontroleerd per run",
                             "lastgrens": meetslot.LASTGRENS, "runs": a.runs, "volgorde": "A/B gebalanceerd afwisselend (a,b | b,a | a,b)",
                             "ongeldig": "loadavg(1 min) > grens vóór de run, andere processen > grens kernen tijdens de run, "
                                         "of een ander zwaar slot actief",
                             "systemen": {"stock-standaard": "profielen/stock-standaard.json", "stock-best": "profielen/stock-best.json"},
                             "config_sha256": sessie.config_hash},
                "metingen": metingen, "fasefouten": fasefouten,
                "validatie_toelichting": "Sim-getest op de ontwikkelmachine; stock-best-transcodes zijn Intel-iGPU-getest (ontwikkelmachine). "
                                         "A310/UHD 770, NAS en echte apparaten: NIET GEVALIDEERD.",
            }
            if a.herhaalsessie and a.uit.exists():
                oud = json.loads(a.uit.read_text(encoding="utf-8"))
                afwijkend = voeg_herhaalsessie_toe(oud, metingen, {"begin": begin, "server_scan_s": round(scan_s, 1),
                                                                   "config_sha256": sessie.config_hash})
                oud.setdefault("herhaalsessies", []).append({"begin": begin, "metingen": metingen_gevraagd,
                                                             "buiten_interval": afwijkend, "fasefouten": fasefouten})
                document = herbereken(oud)
            elif a.aanvullen and a.uit.exists():
                oud = json.loads(a.uit.read_text(encoding="utf-8"))
                nieuw = {(m["id"], m["systeem"]) for m in metingen}
                document["metingen"] = [m for m in oud.get("metingen", []) if (m["id"], m["systeem"]) not in nieuw] + metingen
                document["fasefouten"] = {**{k: v for k, v in oud.get("fasefouten", {}).items() if k not in metingen_gevraagd},
                                          **fasefouten}
                document["eerdere_sessies"] = oud.get("eerdere_sessies", []) + [{k: oud.get(k) for k in ("begin", "eind", "server")}]
                document["protocol"]["config_sha256"] = {**oud.get("protocol", {}).get("config_sha256", {}), **sessie.config_hash}
            bewijs.schrijf(a.uit, herbereken(document))
            log(f"bewijs geschreven: {a.uit}")
        finally:
            server.verwijder()
    return 0
