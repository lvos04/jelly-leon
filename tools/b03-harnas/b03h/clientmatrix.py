"""Rooktest van de clientmatrix (B03-016 deel b; B03 2.0 §10.14).

Acceptatie: elke client start en speelt hero.mp4 af in een rooktest, of staat met reden op Geblokkeerd (desktop zonder
geslaagde spike) of NIET GEVALIDEERD (Swiftfin, echte apparaten); emulatorruns onder gradle.lock zonder
geheugenoverschrijding.

    python -m b03h clientmatrix [--onderdelen web,ua,webdir,legacy,telefoon,tablet,tv,tv36] [--uit …json]
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import legacy, meetslot
from .android import APKS, AVDS, Emulator, haal_apks, maak_avd
from .stock import GEBRUIKER, STOCK_IMAGE, WACHTWOORD, WERK, StockServer, docker
from .web import UA, harnas

REPO = Path(__file__).resolve().parents[3]
HERO = "/media/movies/hero/hero.mp4"
ANDROID_GEBRUIKER, ANDROID_WACHTWOORD = "b03android", "B03Android2026"  # wegwerpaccount, alleen 127.0.0.1-server
NIET_HIER = [
    {"client": "Swiftfin 1.6.1 (iOS/tvOS), Safari, Apple TV", "rol": "stock-native", "status": "NIET GEVALIDEERD (Mac/Xcode)",
     "reden": "geen Mac/Xcode in deze bouwomgeving"},
    {"client": "echte tv's, telefoons, tablets, receivers, Chromecast, DLNA", "rol": "alle", "status": "NIET GEVALIDEERD (hardware)",
     "reden": "geen echte apparaten; D15 onbekend (JLT-69)"},
]


def log(tekst: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {tekst}", flush=True)


def _web(server: StockServer, browser: str, label: str, ua: str | None = None, scherm: Path | None = None) -> dict[str, Any]:
    assert server.jf
    hero = next(i for i in server.jf.items() if i["Path"] == HERO)
    cfg: dict[str, Any] = {"browser": browser, "url": server.url, "gebruiker": GEBRUIKER, "wachtwoord": WACHTWOORD,
                           "items": [{"id": hero["Id"], "naam": "hero"}], "orakelMs": 15000, "label": label}
    if ua:
        cfg["ua"] = ua
    if scherm:
        cfg["schermMap"] = str(scherm)
    d = harnas("profiel" if ua else "speel", cfg)
    item = d["items"][0]
    profiel = d.get("deviceProfile") or {}
    return {"browser": f"{browser} {d.get('versie')}", "ua": (d.get("ua_effectief") or "")[:120], "besluit": item.get("besluit"),
            "orakel_ok": item.get("orakel_ok"), "eerste_frame_ms": item.get("eerste_frame_ms"),
            "tijd_tot_2s_ms": item.get("tijd_tot_2s_ms"), "audio_gedecodeerd": item.get("audio_gedecodeerd"),
            "laatste_stand": item.get("laatste"), "orakel_reden": item.get("orakel_reden"),
            "fout": item.get("fout"), "profiel_directplay": [(p.get("Container"), p.get("VideoCodec"), p.get("AudioCodec"))
                                                             for p in profiel.get("DirectPlayProfiles", [])][:6] if ua else None}


def stockweb_uit_image(image: str, doel: Path) -> Path:
    """Haalt de ongewijzigde jellyfin-web uit de stock-image (voor --webdir tegen een andere server)."""
    shutil.rmtree(doel, ignore_errors=True)
    doel.parent.mkdir(parents=True, exist_ok=True)
    cid = docker("create", image).stdout.strip()
    try:
        docker("cp", f"{cid}:/jellyfin/jellyfin-web", str(doel))
    finally:
        docker("rm", "-f", cid, check=False)
    return doel


# --- Android ------------------------------------------------------------------------------------------------------

def _speel_via_afstandsbediening(server: StockServer, client_patroon: str, timeout: float = 90) -> dict[str, Any]:
    """Start hero.mp4 op de sessie van de app via de officiële route en meet aan de serverkant of hij echt loopt."""
    assert server.jf
    hero = next(i for i in server.jf.items() if i["Path"] == HERO)
    einde = time.monotonic() + timeout
    sessie = None
    while time.monotonic() < einde and sessie is None:
        for s in server.jf.a.doe("GET", "/Sessions"):
            if client_patroon.lower() in (s.get("Client") or "").lower() and s.get("UserName") == ANDROID_GEBRUIKER:
                sessie = s
                break
        time.sleep(2)
    if sessie is None:
        return {"ok": False, "reden": f"geen sessie van {client_patroon} gevonden"}
    server.jf.a.doe("POST", f"/Sessions/{sessie['Id']}/Playing", {"playCommand": "PlayNow", "itemIds": hero["Id"]})
    t0 = time.monotonic()
    posities = []
    while time.monotonic() - t0 < timeout:
        s = next((x for x in server.jf.a.doe("GET", "/Sessions") if x["Id"] == sessie["Id"]), {})
        np = (s.get("NowPlayingItem") or {}).get("Id")
        pos = (s.get("PlayState") or {}).get("PositionTicks") or 0
        if np == hero["Id"]:
            posities.append(round(pos / 1e7, 2))
            if pos >= 2e7:
                return {"ok": True, "sessie_client": sessie.get("Client"), "apparaat": sessie.get("DeviceName"),
                        "app_versie": sessie.get("ApplicationVersion"), "tijd_tot_2s_s": round(time.monotonic() - t0, 1),
                        "posities_s": posities[-5:], "afspeelmethode": (s.get("PlayState") or {}).get("PlayMethod")}
        time.sleep(1)
    return {"ok": False, "reden": "hero.mp4 bereikte geen 2 s afspeelpositie", "posities_s": posities[-5:],
            "sessie_client": sessie.get("Client")}


def _inloggen_telefoon(emu: Emulator, url: str) -> list[str]:
    stappen = []
    emu.sh("monkey -p org.jellyfin.mobile -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1")
    for _ in range(3):  # toestemmingsdialogen (meldingen) wegklikken
        k = emu.wacht_op(r"^(Allow|Toestaan|Don.t allow|Niet toestaan)$", timeout=8)
        if k:
            emu.tik(k)
            stappen.append(f"dialoog: {k.tekst}")
    veld = emu.wacht_op(r"host|server|address|adres", timeout=60, klasse="EditText")
    if not veld:
        raise RuntimeError(f"geen serveradresveld; scherm: {emu.teksten()}")
    emu.tik(veld)
    emu.typ(url)
    emu.toets("KEYCODE_ENTER")
    stappen.append("serveradres ingevuld")
    knop = emu.wacht_op(r"^(Connect|Verbinden)$", timeout=5)
    if knop:
        emu.tik(knop)
    velden: list = []
    for _ in range(45):  # de webweergave laadt jellyfin-web van de server: wachten op gebruikersnaam + wachtwoord
        velden = [k for k in emu.dump() if "EditText" in k.klasse]
        if len(velden) >= 2:
            break
        time.sleep(2)
    if len(velden) < 2:
        raise RuntimeError(f"geen inlogvelden in de webweergave; scherm: {emu.teksten()}")
    emu.tik(velden[0])
    emu.typ(ANDROID_GEBRUIKER)
    emu.tik(velden[1])
    emu.typ(ANDROID_WACHTWOORD)
    emu.toets("KEYCODE_ENTER")
    stappen.append("ingelogd in de webweergave (jellyfin-web van de server)")
    return stappen


def _inloggen_tv(emu: Emulator, url: str) -> list[str]:
    stappen = []
    emu.sh("monkey -p org.jellyfin.androidtv -c android.intent.category.LEANBACK_LAUNCHER 1 >/dev/null 2>&1")
    knop = emu.wacht_op(r"Add server|Server toevoegen|Connect|Verbind", timeout=90)
    if knop:
        emu.tik(knop)
        stappen.append(f"knop: {knop.tekst or knop.omschrijving}")
    veld = emu.wacht_op(r".*", timeout=30, klasse="EditText")
    if not veld:
        raise RuntimeError(f"geen serveradresveld; scherm: {emu.teksten()}")
    emu.tik(veld)
    emu.typ(url)
    emu.toets("KEYCODE_ENTER")
    stappen.append("serveradres ingevuld")
    time.sleep(3)
    k = emu.wacht_op(r"Connect|Verbinden|OK", timeout=10)
    if k and "EditText" not in k.klasse:
        emu.tik(k)
    # Gebruikerskeuze: handmatig inloggen (gebruikers zijn niet zichtbaar op het inlogscherm).
    k = emu.wacht_op(r"Sign in manually|Handmatig|Add user|Gebruiker toevoegen|Login|Aanmelden", timeout=60)
    if k:
        emu.tik(k)
        stappen.append(f"knop: {k.tekst or k.omschrijving}")
    velden = []
    for _ in range(15):
        velden = [x for x in emu.dump() if "EditText" in x.klasse]
        if len(velden) >= 2:
            break
        time.sleep(2)
    if len(velden) < 2:
        raise RuntimeError(f"geen inlogvelden; scherm: {emu.teksten()}")
    emu.tik(velden[0])
    emu.typ(ANDROID_GEBRUIKER)
    emu.tik(velden[1])
    emu.typ(ANDROID_WACHTWOORD)
    emu.toets("KEYCODE_ENTER")
    k = emu.wacht_op(r"^(Sign in|Aanmelden|Inloggen|Connect)$", timeout=5)
    if k:
        emu.tik(k)
    stappen.append("ingelogd (native tv-app)")
    return stappen


def android_rooktest(server: StockServer, soort: str, uitmap: Path) -> dict[str, Any]:
    apks = haal_apks()
    a = AVDS[soort]
    resultaat: dict[str, Any] = {"client": f"officiële {'jellyfin-android 2.7.3' if a['app'] == 'android' else 'jellyfin-androidtv 0.19.10'}"
                                           f" ({soort}-emulator, {a['image']}, {a['apparaat']})",
                                 "rol": "Jelly Leon-webclient (webweergave)" if a["app"] == "android" else "stock-native",
                                 "apk": {"bestand": apks[a["app"]].name, "sha256": APKS[a["app"]]["sha256"]}}
    with meetslot.exclusief_slot("gradle.lock", bij_wachten=log) as wacht:
        resultaat["gradle_lock_wacht_s"] = round(wacht, 1)
        maak_avd(soort)
        emu = Emulator(soort)
        try:
            resultaat["boot_s"] = round(emu.start(apks[a["app"]].parent), 1)
            inst = emu.adb("install", "-r", f"/apk/{apks[a['app']].name}", timeout=300)
            resultaat["installatie"] = (inst.stdout + inst.stderr).strip()[-120:]
            url = f"http://10.0.2.2:{server.poort}"
            try:
                resultaat["stappen"] = (_inloggen_telefoon if a["app"] == "android" else _inloggen_tv)(emu, url)
                resultaat["afspelen"] = _speel_via_afstandsbediening(server, "Android")
            except RuntimeError as fout:
                resultaat["afspelen"] = {"ok": False, "reden": str(fout)[:600]}
            emu.schermafdruk(uitmap / f"android-{soort}.png")
            resultaat["geheugen"] = emu.geheugen()
        finally:
            emu.stop()
    ok = resultaat["afspelen"].get("ok") and not resultaat.get("geheugen", {}).get("oom_kill")
    resultaat["status"] = "Sim-getest (rooktest geslaagd)" if ok else "Sim-mislukt"
    return resultaat


# --- hoofdprogramma -----------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h clientmatrix")
    p.add_argument("--onderdelen", default="web,ua,webdir,legacy,telefoon,tablet,tv,tv36")
    p.add_argument("--uit", type=Path, default=REPO / "docs/platform-v2/test-evidence/b03-016-clientmatrix-rooktest.json")
    a = p.parse_args(argv)
    delen = a.onderdelen.split(",")
    uitmap = a.uit.with_suffix("")
    uitmap.mkdir(parents=True, exist_ok=True)
    clients: list[dict[str, Any]] = []
    begin = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    koppelingen = {"/media/movies/hero": "bron/blender/hero", "/media/movies/sintel": "bron/blender/sintel"}
    with meetslot.exclusief_slot(bij_wachten=log):
        server = StockServer("clientmatrix", koppelingen=koppelingen).start()
        try:
            server.inrichten([("Films", "movies", ["/media/movies"])])
            assert server.jf
            server.jf.gebruiker(ANDROID_GEBRUIKER, ANDROID_WACHTWOORD)
            if "web" in delen:
                for b in ("chromium", "firefox", "webkit"):
                    r = _web(server, b, f"web-{b}", scherm=uitmap)
                    clients.append({"client": r["browser"] + " (Playwright 1.63, headless)", "rol": "stock-web (uit de stock-image)",
                                    **r, "status": "Sim-getest (rooktest geslaagd)" if r["orakel_ok"] else "Sim-mislukt",
                                    "opmerking": "WebKit op Linux is geen Safari" if b == "webkit" else ""})
                    log(f"web {b}: {clients[-1]['status']}")
            if "ua" in delen:
                for naam, ua in UA.items():
                    r = _web(server, "chromium", f"ua-{naam}", ua=ua, scherm=uitmap)
                    clients.append({"client": f"{naam} via UA-simulatie (Chromium-engine)", "rol": "Jelly Leon-webclient (profielcode)",
                                    **r, "status": "Sim-getest (UA-simulatie, geen echte decoder)" if r["orakel_ok"] else "Sim-mislukt",
                                    "opmerking": "alleen de takken in browserDeviceProfile.js; echte tv NIET GEVALIDEERD (hardware)"})
                    log(f"ua {naam}: {clients[-1]['status']}")
            if "legacy" in delen:
                hero = next(i for i in server.jf.items() if i["Path"] == HERO)
                server.jf.login(GEBRUIKER, WACHTWOORD)
                statussen = legacy.meet(server.url, server.jf.token, server.jf.admin_id, hero["Id"])
                stream_ok = statussen["x_emby_token"]["stream_statisch"] in (200, 206)
                clients.append({"client": "derden-client met legacy-headers (gesimuleerd: X-Emby-Token, X-MediaBrowser-Token, "
                                          "X-Emby-Authorization, api_key)", "rol": "stock-native (derden)",
                                "status_per_vorm": statussen,
                                "status": "Sim-getest (gemeten: legacy-auth geweigerd op API-routes; statische stream speelt)"
                                if stream_ok else "Sim-mislukt",
                                "opmerking": "12.4: EnableLegacyAuthorization uit → 401 voor X-Emby-Token/api_key op API-routes; "
                                             "?ApiKey= en Authorization: MediaBrowser Token=… werken; /Videos/{id}/stream?static=true "
                                             "geeft 206 ook zonder token (ADR-0009). Besluit derden-clients: BG-01"})
            for soort in ("telefoon", "tablet", "tv", "tv36"):
                if soort in delen:
                    try:
                        r = android_rooktest(server, soort, uitmap)
                    except Exception as fout:  # noqa: BLE001 - elke emulatorfout wordt eerlijk gerapporteerd
                        r = {"client": f"Android-{soort}-emulator", "status": "Sim-mislukt", "fout": str(fout)[:800]}
                    clients.append(r)
                    log(f"android {soort}: {r['status']} {r.get('afspelen', {}).get('reden', '')}")
        finally:
            server.verwijder()
        if "webdir" in delen:
            web = stockweb_uit_image(STOCK_IMAGE, WERK / "stockweb")
            server = StockServer("clientmatrix-webdir", koppelingen=koppelingen, webdir=web, gpu=False).start()
            try:
                server.inrichten([("Films", "movies", ["/media/movies"])])
                r = _web(server, "chromium", "webdir-chromium", scherm=uitmap)
                clients.append({"client": r["browser"] + " tegen een server met --webdir (stock-web uit de stock-image)",
                                "rol": "stock-web via --webdir", **r,
                                "status": "Sim-getest (rooktest geslaagd)" if r["orakel_ok"] else "Sim-mislukt",
                                "opmerking": "mechanisme voor 'stock-web tegen de Jelly Leon-server' (JLT-05/09); hier tegen stock"})
            finally:
                server.verwijder()
                shutil.rmtree(web, ignore_errors=True)
    document = {"schema": "jelly-leon/b03-016-clientmatrix/1", "begin": begin, "eind": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "server": STOCK_IMAGE, "testitem": "bron/blender/hero/hero.mp4 (CC BY 4.0)", "clients": clients,
                "desktop": {"client": "jellyfin-desktop 2.0.0 onder Xvfb", "status": "zie b03-016-desktop-spike.json"},
                "niet_hier": NIET_HIER}
    a.uit.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"clientmatrix geschreven: {a.uit}")
    return 0
