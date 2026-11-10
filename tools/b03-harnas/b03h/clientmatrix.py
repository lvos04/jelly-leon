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
from .jfapi import Jellyfin
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
        # De nieuwste bestuurbare sessie van deze app (oude sessies van eerdere emulators blijven even in de lijst staan).
        kandidaten = [s for s in server.jf.a.doe("GET", "/Sessions")
                      if client_patroon.lower() == (s.get("Client") or "").lower() and s.get("UserName") == ANDROID_GEBRUIKER
                      and s.get("SupportsMediaControl")]
        if kandidaten:
            sessie = max(kandidaten, key=lambda s: s.get("LastActivityDate") or "")
        else:
            time.sleep(2)
    if sessie is None:
        return {"ok": False, "reden": f"geen sessie van {client_patroon} gevonden"}
    vooraf = (sessie.get("PlayState") or {}).get("PositionTicks")
    server.jf.a.doe("POST", f"/Sessions/{sessie['Id']}/Playing", {"playCommand": "PlayNow", "itemIds": hero["Id"]})
    t0 = time.monotonic()
    posities: list[float] = []
    while time.monotonic() - t0 < timeout:
        # Gemeten (jellyfin-android 2.7.3): de native speler meldt de voortgang via een eigen sessieregel met een ander
        # DeviceId dan de webweergave. Elke sessie van de (aparte) testgebruiker met dezelfde client telt.
        rijen = [x for x in server.jf.a.doe("GET", "/Sessions") if x.get("UserName") == ANDROID_GEBRUIKER
                 and (x.get("Client") or "").lower() == client_patroon.lower()]
        s = next((x for x in rijen if (x.get("NowPlayingItem") or {}).get("Id") == hero["Id"]), {})
        np = (s.get("NowPlayingItem") or {}).get("Id")
        ps = s.get("PlayState") or {}
        pos = (ps.get("PositionTicks") or 0) / 1e7
        if np == hero["Id"] and not ps.get("IsPaused"):
            posities.append(round(pos, 2))
            # Echt afspelen = de positie loopt ná het commando minstens 2 s op (een oude sessiestand telt niet).
            if len(posities) >= 2 and posities[-1] - posities[0] >= 2.0 and posities[-1] > posities[-2]:
                return {"ok": True, "sessie_client": sessie.get("Client"), "apparaat": sessie.get("DeviceName"),
                        "app_versie": sessie.get("ApplicationVersion"), "tijd_tot_2s_opgelopen_s": round(time.monotonic() - t0, 1),
                        "posities_s": posities[-6:], "positie_vooraf_s": round((vooraf or 0) / 1e7, 2),
                        "afspeelmethode": ps.get("PlayMethod")}
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
    veld = emu.wacht_op(r".*", timeout=60, klasse="EditText")  # het (lege) veld onder het label 'Host'
    if not veld:
        raise RuntimeError(f"geen serveradresveld; scherm: {emu.teksten()}")
    emu.tik(veld)
    emu.typ(url)
    emu.toets("KEYCODE_ENTER")
    stappen.append("serveradres ingevuld")
    knop = emu.wacht_op(r"^(Connect|Verbinden)$", timeout=5)
    if knop:
        emu.tik(knop)
    # De melding over batterij-optimalisatie niet aantikken: 'OK' opent de systeeminstellingen en verlaat de app.
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
    # Met Tab naar het wachtwoordveld: na het typen schuift het toetsenbord de pagina op, dus oude coördinaten kloppen niet
    # meer (gemeten op de tablet: het wachtwoord kwam dan in het gebruikersveld terecht).
    emu.toets("KEYCODE_TAB")
    time.sleep(1)
    emu.typ(ANDROID_WACHTWOORD)
    # Enter verstuurt het formulier; niet op 'Sign In' tikken: de batterijmelding kan erover liggen.
    emu.toets("KEYCODE_ENTER")
    if not emu.wacht_op(r"^(My Media|Mijn media|Home|Startscherm)$", timeout=45):
        raise RuntimeError(f"inloggen in de webweergave niet gelukt; scherm: {emu.teksten()}")
    stappen.append("ingelogd in de webweergave (jellyfin-web van de server)")
    return stappen


def _inloggen_tv(emu: Emulator, url: str, server: StockServer) -> list[str]:
    """Gemeten flow van androidtv 0.19.10: 'Enter server address' → adres → 'Add account' → Quick Connect-code; de code
    wordt via de officiële route POST /QuickConnect/Authorize door de testgebruiker goedgekeurd (geen wachtwoord typen)."""
    stappen = []
    emu.sh("monkey -p org.jellyfin.androidtv -c android.intent.category.LEANBACK_LAUNCHER 1 >/dev/null 2>&1")
    knop = emu.wacht_op(r"^Enter server address$", timeout=90)
    if not knop:
        raise RuntimeError(f"geen startscherm van de tv-app; scherm: {emu.teksten()}")
    emu.tik(knop)
    velden = []
    for _ in range(15):
        velden = [x for x in emu.dump() if "EditText" in x.klasse]
        if velden:
            break
        time.sleep(1)
    if not velden:
        raise RuntimeError(f"geen serveradresveld; scherm: {emu.teksten()}")
    emu.tik(velden[0])
    emu.typ(url)
    emu.toets("KEYCODE_ENTER")
    stappen.append("serveradres ingevuld")
    k = emu.wacht_op(r"^(Add account|Account toevoegen)$", timeout=60)
    if not k:
        raise RuntimeError(f"geen gebruikersscherm na verbinden; scherm: {emu.teksten()}")
    emu.tik(k)
    code_knoop = emu.wacht_op(r"quick_connect_code", timeout=30)
    if not code_knoop:
        raise RuntimeError(f"geen Quick Connect-code; scherm: {emu.teksten()}")
    code = code_knoop.tekst.replace(" ", "")
    jf = Jellyfin(server.url)
    jf.login(ANDROID_GEBRUIKER, ANDROID_WACHTWOORD)
    if jf.a.doe("POST", "/QuickConnect/Authorize", {"code": code, "userId": jf.admin_id}) is not True:
        raise RuntimeError("Quick Connect-autorisatie geweigerd")
    stappen.append("Quick Connect-code goedgekeurd via POST /QuickConnect/Authorize (testgebruiker)")
    if not emu.wacht_op(r"^(My media|Mijn media|Home|Startscherm)$", timeout=60):
        raise RuntimeError(f"startscherm van de tv-app niet bereikt; scherm: {emu.teksten()}")
    stappen.append("ingelogd (native tv-app)")
    return stappen


def _android_poging(server: StockServer, soort: str, apks: dict[str, Path], uitmap: Path, geheugen_gib: int) -> dict[str, Any]:
    a = AVDS[soort]
    poging: dict[str, Any] = {"geheugenlimiet_gib": geheugen_gib}
    maak_avd(soort)
    emu = Emulator(soort, geheugen_gib=geheugen_gib)
    try:
        poging["boot_s"] = round(emu.start(apks[a["app"]].parent), 1)
        inst = emu.adb("install", "-r", f"/apk/{apks[a['app']].name}", timeout=300)
        poging["installatie"] = (inst.stdout + inst.stderr).strip()[-120:]
        url = f"http://10.0.2.2:{server.poort}"
        try:
            if a["app"] == "android":
                poging["stappen"] = _inloggen_telefoon(emu, url)
                poging["afspelen"] = _speel_via_afstandsbediening(server, "Jellyfin for Android")
            else:
                poging["stappen"] = _inloggen_tv(emu, url, server)
                poging["afspelen"] = _speel_via_afstandsbediening(server, "Jellyfin Android TV")
        except RuntimeError as fout:
            poging["afspelen"] = {"ok": False, "reden": str(fout)[:600]}
        emu.schermafdruk(uitmap / f"android-{soort}-{geheugen_gib}gib.png")
        poging["geheugen"] = emu.geheugen()
    finally:
        emu.stop()
    poging["ok"] = bool(poging["afspelen"].get("ok")) and not poging.get("geheugen", {}).get("oom_kill")
    return poging


def android_rooktest(server: StockServer, soort: str, uitmap: Path) -> dict[str, Any]:
    """Eerst binnen de plan-limiet van 4 GiB; wordt de emulator daar door de OOM-killer gestopt, dan één keer met 5 GiB
    (afwijking van het plan, met beide pogingen in het bewijs)."""
    apks = haal_apks()
    a = AVDS[soort]
    resultaat: dict[str, Any] = {"client": f"officiële {'jellyfin-android 2.7.3' if a['app'] == 'android' else 'jellyfin-androidtv 0.19.10'}"
                                           f" ({soort}-emulator, {a['image']}, {a['apparaat']} {a['config'] or ''})",
                                 "rol": "Jelly Leon-webclient (webweergave)" if a["app"] == "android" else "stock-native",
                                 "apk": {"bestand": apks[a["app"]].name, "sha256": APKS[a["app"]]["sha256"]}, "pogingen": []}
    with meetslot.exclusief_slot("gradle.lock", bij_wachten=log) as wacht:
        resultaat["gradle_lock_wacht_s"] = round(wacht, 1)
        for gib in (4, 5):
            poging = _android_poging(server, soort, apks, uitmap, gib)
            resultaat["pogingen"].append(poging)
            if poging["ok"] or not poging.get("geheugen", {}).get("oom_kill"):
                break
    laatste = resultaat["pogingen"][-1]
    resultaat["afspelen"] = laatste["afspelen"]
    oom_4 = resultaat["pogingen"][0].get("geheugen", {}).get("oom_kill")
    if laatste["ok"] and not oom_4:
        resultaat["status"] = "Sim-getest (rooktest geslaagd binnen 4 GiB)"
    elif laatste["ok"]:
        resultaat["status"] = "Sim-getest (rooktest geslaagd met 5 GiB; binnen 4 GiB OOM-kill)"
    else:
        resultaat["status"] = "Sim-mislukt"
    return resultaat


# --- hoofdprogramma -----------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h clientmatrix")
    p.add_argument("--onderdelen", default="web,ua,webdir,legacy,telefoon,tablet,tv,tv36")
    p.add_argument("--uit", type=Path, default=REPO / "docs/platform-v2/test-evidence/b03-016-clientmatrix-rooktest.json")
    p.add_argument("--aanvullen", action="store_true", help="clients toevoegen aan een bestaand bewijs (zelfde client vervangen)")
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
    if a.aanvullen and a.uit.exists():
        oud = json.loads(a.uit.read_text(encoding="utf-8"))
        nieuw = {c["client"] for c in clients}
        document["clients"] = [c for c in oud.get("clients", []) if c["client"] not in nieuw] + clients
        document["eerdere_sessies"] = oud.get("eerdere_sessies", []) + [{"begin": oud.get("begin"), "eind": oud.get("eind")}]
    a.uit.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"clientmatrix geschreven: {a.uit}")
    return 0
