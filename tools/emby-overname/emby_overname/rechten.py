"""Rechten, ouderlijk toezicht en voorkeuren van Emby vertalen naar Jelly Leon (B03-015 A4, JLT-70).

Uitgangspunt: **een kind ziet in Jelly Leon nooit meer dan in Emby.** Wat niet exact te vertalen is, wordt *strenger*
ingesteld en komt op de afhandellijst; nooit ruimer. Elk veld krijgt een status: `gelijk`, `strenger`, `ruimer`
(alleen bij een bestaande gebruiker die de tool niet aanraakt — altijd een verschil dat akkoord vraagt) of
`niet_van_toepassing` (Emby-instelling zonder tegenhanger die geen toegang raakt).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .hulp import normaliseer_naam, sha256_json
from .koppelen import Padvertaling, vertaal_pad

# Booleans met dezelfde naam en betekenis in Emby en Jellyfin 12.x. True = meer toegang (behalve de "beperkende").
TOEGANG_BOOL = (
    "IsAdministrator", "EnableUserPreferenceAccess", "EnableRemoteControlOfOtherUsers", "EnableSharedDeviceControl",
    "EnableRemoteAccess", "EnableLiveTvManagement", "EnableLiveTvAccess", "EnableMediaPlayback",
    "EnableAudioPlaybackTranscoding", "EnableVideoPlaybackTranscoding", "EnablePlaybackRemuxing", "EnableContentDeletion",
    "EnableContentDownloading", "EnableSubtitleManagement", "EnableSyncTranscoding", "EnableMediaConversion",
    "EnablePublicSharing",
)
BEPERKEND_BOOL = ("IsDisabled",)  # True = minder toegang
NEUTRAAL_BOOL = ("IsHidden",)  # alleen zichtbaarheid op het inlogscherm
EMBY_ZONDER_TEGENHANGER = (
    "IsHiddenRemotely", "IsHiddenFromUnusedDevices", "EnableTranscodingQuality", "AutoRemoteQuality", "RestrictedFeatures",
    "EnableSubtitleDownloading", "AllowCameraUpload", "AllowSharingPersonalItems",
)
UNRATED_JL = {"Movie", "Trailer", "Series", "Music", "Book", "LiveTvChannel", "LiveTvProgram", "ChannelContent", "Other"}
CONFIG_KOPIE = (
    "AudioLanguagePreference", "SubtitleLanguagePreference", "PlayDefaultAudioTrack", "SubtitleMode",
    "DisplayMissingEpisodes", "HidePlayedInLatest", "RememberAudioSelections", "RememberSubtitleSelections",
    "EnableNextEpisodeAutoPlay",
)
CONFIG_BIBLIOTHEEKLIJSTEN = ("OrderedViews", "LatestItemsExcludes", "MyMediaExcludes")
CONFIG_ZONDER_TEGENHANGER = ("HidePlayedInMoreLikeThis", "HidePlayedInSuggestions", "ResumeRewindSeconds", "IntroSkipMode",
                             "EnableLocalPassword")
SUBTITLE_MODI = {"Default", "Always", "OnlyForced", "None", "Smart"}


@dataclass
class RechtRegel:
    veld: str
    emby: Any
    jelly_leon: Any
    status: str  # gelijk | strenger | ruimer | niet_van_toepassing | handmatig
    uitleg: str = ""

    def naar_json(self) -> dict[str, Any]:
        return {"veld": self.veld, "emby": self.emby, "jelly_leon": self.jelly_leon, "status": self.status, "uitleg": self.uitleg}


@dataclass
class Bibliotheekkoppeling:
    emby_naar_jl: dict[str, str]  # Emby-bibliotheek-ID (Guid of ItemId) → Jelly Leon-ItemId
    niet_gekoppeld: list[str]  # Emby-bibliotheeknamen zonder tegenhanger
    namen_emby: dict[str, str]
    namen_jl: dict[str, str]


def koppel_bibliotheken(emby_bib: list[dict[str, Any]], jl_bib: list[dict[str, Any]],
                        paden: list[Padvertaling]) -> Bibliotheekkoppeling:
    resultaat: dict[str, str] = {}
    niet: list[str] = []
    namen_emby: dict[str, str] = {}
    namen_jl = {str(b.get("ItemId")): str(b.get("Name")) for b in jl_bib}
    for b in emby_bib:
        vertaald = {vertaal_pad(p, paden) for p in b.get("locaties") or []}
        op_locatie = [j for j in jl_bib if vertaald and vertaald <= set(j.get("Locations") or [])]
        op_naam = [j for j in jl_bib if normaliseer_naam(str(j.get("Name"))) == normaliseer_naam(str(b.get("naam")))]
        keuze = op_locatie if len(op_locatie) == 1 else op_naam if len(op_naam) == 1 else []
        for sleutel in {str(b.get("id")), str(b.get("item_id"))}:
            namen_emby[sleutel] = str(b.get("naam"))
            if keuze:
                resultaat[sleutel] = str(keuze[0].get("ItemId"))
        if not keuze:
            niet.append(str(b.get("naam")))
    return Bibliotheekkoppeling(resultaat, sorted(set(niet)), namen_emby, namen_jl)


def _classificatie_score(rij: dict[str, Any]) -> int | None:
    score = rij.get("RatingScore")
    if isinstance(score, dict) and isinstance(score.get("score"), int):
        return score["score"]
    waarde = rij.get("Value")
    return waarde if isinstance(waarde, int) else None


def vertaal_leeftijdsgrens(emby_max: int | None, emby_tabel: list[dict[str, Any]],
                           jl_tabel: list[dict[str, Any]]) -> tuple[int | None, RechtRegel]:
    """Emby-maximum → Jelly Leon-maximum via de naam van de classificatie; anders strenger (laagste score) + handmatig."""
    if emby_max is None:
        return None, RechtRegel("MaxParentalRating", None, None, "gelijk", "geen leeftijdsgrens")
    namen = sorted({str(r.get("naam")) for r in emby_tabel if r.get("waarde") == emby_max})
    jl_scores = {normaliseer_naam(str(r.get("Name"))): _classificatie_score(r) for r in jl_tabel}
    gevonden = [jl_scores[normaliseer_naam(n)] for n in namen if jl_scores.get(normaliseer_naam(n)) is not None]
    emby_tekst = f"{emby_max} ({', '.join(namen) or 'onbekende naam'})"
    if gevonden:
        doel = min(gevonden)  # type: ignore[type-var]
        return doel, RechtRegel("MaxParentalRating", emby_tekst, doel, "gelijk",
                                f"via de classificatienaam ({', '.join(namen)}); Jelly Leon-score {doel}")
    scores = [s for s in jl_scores.values() if s is not None and s >= 0]
    doel = min(scores) if scores else 0
    return doel, RechtRegel(
        "MaxParentalRating", emby_tekst, doel, "strenger",
        "Jelly Leon kent deze classificatienaam niet in het ingestelde land; voorlopig de strengste grens ingesteld. "
        "Stel de leeftijdsgrens handmatig in (nooit ruimer dan in Emby).",
    )


def vertaal_beleid(emby_beleid: dict[str, Any], jl_basis: dict[str, Any], bib: Bibliotheekkoppeling,
                   emby_classificaties: list[dict[str, Any]], jl_classificaties: list[dict[str, Any]],
                   jl_gebruiker_id: str | None) -> tuple[dict[str, Any], list[RechtRegel]]:
    """Doelbeleid voor een door de tool aangemaakte gebruiker (op basis van het huidige Jelly Leon-beleid)."""
    doel = dict(jl_basis)
    regels: list[RechtRegel] = []
    for veld in (*TOEGANG_BOOL, *BEPERKEND_BOOL, *NEUTRAAL_BOOL):
        if veld in emby_beleid:
            doel[veld] = bool(emby_beleid[veld])
            regels.append(RechtRegel(veld, bool(emby_beleid[veld]), doel[veld], "gelijk"))
    # Bibliotheektoegang (incl. uitgesloten submappen: die bibliotheek dan helemaal niet → strenger).
    uitgesloten = [str(p) for p in emby_beleid.get("ExcludedSubFolders") or []]
    getroffen = {sleutel for sleutel in bib.emby_naar_jl if any(str(p).startswith(sleutel) for p in uitgesloten)}
    if any(not any(p.startswith(s) for s in bib.emby_naar_jl) for p in uitgesloten):
        getroffen = set(bib.emby_naar_jl)  # niet toe te wijzen uitsluiting → geen enkele bibliotheek (strengst)
    alle_jl_gekoppeld = set(bib.namen_jl) <= set(bib.emby_naar_jl.values())
    if emby_beleid.get("EnableAllFolders", True) and not uitgesloten and not bib.niet_gekoppeld and alle_jl_gekoppeld:
        doel["EnableAllFolders"], doel["EnabledFolders"] = True, []
        regels.append(RechtRegel("Bibliotheektoegang", "alle bibliotheken", "alle bibliotheken", "gelijk"))
    else:
        if emby_beleid.get("EnableAllFolders", True):
            bronnen = sorted({k for k in bib.emby_naar_jl if k in bib.namen_emby})
        else:
            bronnen = [str(f) for f in emby_beleid.get("EnabledFolders") or []]
        toegestaan = sorted({bib.emby_naar_jl[f] for f in bronnen if f in bib.emby_naar_jl and f not in getroffen})
        weg = sorted({bib.namen_emby.get(f, f) for f in bronnen if f not in bib.emby_naar_jl or f in getroffen})
        doel["EnableAllFolders"], doel["EnabledFolders"] = False, toegestaan
        emby_tekst = ("alle bibliotheken" if emby_beleid.get("EnableAllFolders", True)
                      else ", ".join(sorted(bib.namen_emby.get(f, f) for f in bronnen)) or "geen")
        jl_tekst = ", ".join(sorted(bib.namen_jl.get(t, t) for t in toegestaan)) or "geen"
        extra_jl = sorted(n for k, n in bib.namen_jl.items() if k not in set(bib.emby_naar_jl.values()))
        status = "strenger" if weg or uitgesloten or (emby_beleid.get("EnableAllFolders", True) and extra_jl) else "gelijk"
        uitleg = ""
        if weg:
            uitleg = f"niet toegekend (geen tegenhanger of uitgesloten submappen): {', '.join(weg)}"
        if emby_beleid.get("EnableAllFolders", True) and extra_jl:
            uitleg += (" · " if uitleg else "") + f"Jelly Leon-bibliotheken zonder Emby-tegenhanger niet toegekend: {', '.join(extra_jl)}"
        if uitgesloten:
            uitleg += (" · " if uitleg else "") + f"Emby sluit {len(uitgesloten)} submap(pen) uit; Jelly Leon kent dat niet"
        regels.append(RechtRegel("Bibliotheektoegang", emby_tekst, jl_tekst, status, uitleg))
    # Leeftijdsgrens.
    maximum, regel = vertaal_leeftijdsgrens(emby_beleid.get("MaxParentalRating"), emby_classificaties, jl_classificaties)
    doel["MaxParentalRating"] = maximum
    doel["MaxParentalSubRating"] = None
    regels.append(regel)
    # Tags.
    geblokkeerd = sorted({str(t) for t in emby_beleid.get("BlockedTags") or []})
    doel["BlockedTags"] = geblokkeerd
    regels.append(RechtRegel("Geblokkeerde tags", geblokkeerd, geblokkeerd, "gelijk"))
    toegestane_tags = sorted({str(t) for t in emby_beleid.get("IncludeTags") or []}) if emby_beleid.get("IsTagBlockingModeInclusive") else []
    doel["AllowedTags"] = toegestane_tags
    if toegestane_tags:
        regels.append(RechtRegel("Alleen tags", toegestane_tags, toegestane_tags, "gelijk"))
    if emby_beleid.get("AllowTagOrRating"):
        regels.append(RechtRegel("AllowTagOrRating", True, "tags én leeftijd beide afgedwongen", "strenger",
                                 "Emby laat een item toe op tag óf leeftijd; Jelly Leon dwingt beide af"))
    # Items zonder classificatie blokkeren.
    blok = [str(x) for x in emby_beleid.get("BlockUnratedItems") or []]
    doel["BlockUnratedItems"] = sorted(x for x in blok if x in UNRATED_JL)
    vervallen = sorted(x for x in blok if x not in UNRATED_JL)
    regels.append(RechtRegel("Items zonder classificatie blokkeren", sorted(blok), doel["BlockUnratedItems"], "gelijk",
                             f"geen Jelly Leon-soort voor: {', '.join(vervallen)}" if vervallen else ""))
    # Tijdschema's.
    schema = [
        {"DayOfWeek": s.get("DayOfWeek"), "StartHour": s.get("StartHour"), "EndHour": s.get("EndHour"),
         **({"UserId": jl_gebruiker_id} if jl_gebruiker_id else {})}
        for s in emby_beleid.get("AccessSchedules") or []
    ]
    doel["AccessSchedules"] = schema
    if schema:
        regels.append(RechtRegel("Toegangstijden", emby_beleid.get("AccessSchedules"), schema, "gelijk"))
    # Kanalen en apparaten: ID's verschillen per server → bij een beperking alles dicht (strenger) + handmatig.
    for alles, lijst, naam in (("EnableAllChannels", "EnabledChannels", "Kanalen"), ("EnableAllDevices", "EnabledDevices", "Apparaten")):
        if emby_beleid.get(alles, True):
            doel[alles], doel[lijst] = True, []
            regels.append(RechtRegel(naam, "alle", "alle", "gelijk"))
        else:
            doel[alles], doel[lijst] = False, []
            regels.append(RechtRegel(naam, emby_beleid.get(lijst) or [], "geen", "strenger",
                                     "ID's verschillen per server; stel de toegestane kanalen/apparaten handmatig in"))
    verwijderen = [bib.emby_naar_jl[f] for f in emby_beleid.get("EnableContentDeletionFromFolders") or [] if f in bib.emby_naar_jl]
    doel["EnableContentDeletionFromFolders"] = sorted(verwijderen)
    # Bitrate en gelijktijdige streams.
    if "RemoteClientBitrateLimit" in emby_beleid:
        doel["RemoteClientBitrateLimit"] = int(emby_beleid.get("RemoteClientBitrateLimit") or 0)
        regels.append(RechtRegel("Bitrategrens buitenshuis", emby_beleid.get("RemoteClientBitrateLimit"),
                                 doel["RemoteClientBitrateLimit"], "gelijk"))
    streams = int(emby_beleid.get("SimultaneousStreamLimit") or 0)
    if streams:
        doel["MaxActiveSessions"] = streams
        regels.append(RechtRegel("Gelijktijdige streams", streams, f"max. {streams} actieve sessies", "strenger",
                                 "Jelly Leon begrenst sessies (ruimer begrip dan streams), dus nooit meer streams"))
    for veld in EMBY_ZONDER_TEGENHANGER:
        if emby_beleid.get(veld) not in (None, False, [], 0):
            regels.append(RechtRegel(veld, emby_beleid.get(veld), None, "niet_van_toepassing",
                                     "Emby-instelling zonder tegenhanger in Jelly Leon; raakt geen toegang tot media"))
    return doel, regels


def vertaal_configuratie(emby_config: dict[str, Any], jl_basis: dict[str, Any], bib: Bibliotheekkoppeling
                         ) -> tuple[dict[str, Any], list[RechtRegel]]:
    doel = dict(jl_basis)
    regels: list[RechtRegel] = []
    for veld in CONFIG_KOPIE:
        if veld not in emby_config:
            continue
        waarde = emby_config[veld]
        if veld == "SubtitleMode" and waarde not in SUBTITLE_MODI:
            regels.append(RechtRegel(veld, waarde, doel.get(veld), "handmatig", "onbekende ondertitelmodus"))
            continue
        if veld in ("AudioLanguagePreference", "SubtitleLanguagePreference") and not waarde:
            waarde = None
        doel[veld] = waarde
        regels.append(RechtRegel(veld, emby_config[veld], waarde, "gelijk"))
    for veld in CONFIG_BIBLIOTHEEKLIJSTEN:
        bron = [str(x) for x in emby_config.get(veld) or []]
        doel[veld] = [bib.emby_naar_jl[x] for x in bron if x in bib.emby_naar_jl]
        if len(doel[veld]) != len(bron):
            regels.append(RechtRegel(veld, bron, doel[veld], "niet_van_toepassing", "niet elke bibliotheek heeft een tegenhanger"))
    for veld in CONFIG_ZONDER_TEGENHANGER:
        if emby_config.get(veld) not in (None, False, [], 0, "ShowButton"):
            regels.append(RechtRegel(veld, emby_config.get(veld), None, "niet_van_toepassing", "Emby-voorkeur zonder tegenhanger"))
    return doel, regels


# --- vergelijken (bestaande gebruiker of controle na het schrijven) ------------------------------------------------

def vergelijk_beleid(doel: dict[str, Any], werkelijk: dict[str, Any], bib: Bibliotheekkoppeling) -> list[RechtRegel]:
    """Vergelijkt het vertaalde Emby-beleid met het werkelijke Jelly Leon-beleid; `ruimer` = Jelly Leon geeft meer toegang."""
    regels: list[RechtRegel] = []
    for veld in TOEGANG_BOOL:
        if veld in doel:
            a, b = bool(doel[veld]), bool(werkelijk.get(veld))
            regels.append(RechtRegel(veld, a, b, "gelijk" if a == b else ("ruimer" if b and not a else "strenger")))
    for veld in BEPERKEND_BOOL:
        if veld in doel:
            a, b = bool(doel[veld]), bool(werkelijk.get(veld))
            regels.append(RechtRegel(veld, a, b, "gelijk" if a == b else ("ruimer" if a and not b else "strenger")))
    for veld in NEUTRAAL_BOOL:
        if veld in doel:
            a, b = bool(doel[veld]), bool(werkelijk.get(veld))
            regels.append(RechtRegel(veld, a, b, "gelijk" if a == b else "handmatig"))
    a_alle, b_alle = bool(doel.get("EnableAllFolders")), bool(werkelijk.get("EnableAllFolders"))
    a_set = set(doel.get("EnabledFolders") or [])
    b_set = set(werkelijk.get("EnabledFolders") or [])
    if a_alle and b_alle:
        status = "gelijk"
    elif b_alle and not a_alle:
        status = "ruimer"
    elif a_alle and not b_alle:
        status = "strenger"
    else:
        status = "gelijk" if a_set == b_set else ("ruimer" if b_set - a_set else "strenger")
    regels.append(RechtRegel("Bibliotheektoegang",
                             "alle" if a_alle else sorted(bib.namen_jl.get(x, x) for x in a_set),
                             "alle" if b_alle else sorted(bib.namen_jl.get(x, x) for x in b_set), status))
    a_max, b_max = doel.get("MaxParentalRating"), werkelijk.get("MaxParentalRating")
    if a_max == b_max:
        status = "gelijk"
    elif b_max is None or (a_max is not None and b_max > a_max):
        status = "ruimer"
    else:
        status = "strenger"
    regels.append(RechtRegel("MaxParentalRating", a_max, b_max, status))
    a_tags, b_tags = set(doel.get("BlockedTags") or []), set(werkelijk.get("BlockedTags") or [])
    regels.append(RechtRegel("Geblokkeerde tags", sorted(a_tags), sorted(b_tags),
                             "gelijk" if a_tags == b_tags else ("ruimer" if a_tags - b_tags else "strenger")))
    a_allow, b_allow = set(doel.get("AllowedTags") or []), set(werkelijk.get("AllowedTags") or [])
    if a_allow or b_allow:
        if a_allow == b_allow:
            status = "gelijk"
        elif not b_allow or (a_allow and b_allow - a_allow):
            status = "ruimer"
        else:
            status = "strenger"
        regels.append(RechtRegel("Alleen tags", sorted(a_allow), sorted(b_allow), status))
    a_unr, b_unr = set(doel.get("BlockUnratedItems") or []), set(werkelijk.get("BlockUnratedItems") or [])
    regels.append(RechtRegel("Items zonder classificatie blokkeren", sorted(a_unr), sorted(b_unr),
                             "gelijk" if a_unr == b_unr else ("ruimer" if a_unr - b_unr else "strenger")))
    a_sch = sorted((s.get("DayOfWeek"), s.get("StartHour"), s.get("EndHour")) for s in doel.get("AccessSchedules") or [])
    b_sch = sorted((s.get("DayOfWeek"), s.get("StartHour"), s.get("EndHour")) for s in werkelijk.get("AccessSchedules") or [])
    if a_sch or b_sch:
        regels.append(RechtRegel("Toegangstijden", a_sch, b_sch, "gelijk" if a_sch == b_sch else ("ruimer" if not b_sch else "handmatig")))
    return regels


def vergelijk_configuratie(doel: dict[str, Any], werkelijk: dict[str, Any]) -> list[RechtRegel]:
    regels: list[RechtRegel] = []
    for veld in CONFIG_KOPIE:
        if veld in doel:
            a, b = doel.get(veld), werkelijk.get(veld)
            regels.append(RechtRegel(veld, a, b, "gelijk" if (a or None) == (b or None) else "handmatig"))
    return regels


def normaliseer_instellingen(waarden: dict[str, Any]) -> dict[str, Any]:
    """Vergelijkbare vorm van beleid/configuratie: GUID's zonder streepjes, lijsten gesorteerd, tijdschema's zonder Id."""
    uit: dict[str, Any] = {}
    for k, v in sorted(waarden.items()):
        if k == "AccessSchedules":
            v = sorted([s.get("DayOfWeek"), s.get("StartHour"), s.get("EndHour")] for s in v or [])
        elif isinstance(v, list):
            v = sorted(str(x).replace("-", "").casefold() if isinstance(x, str) else str(x) for x in v)
        elif v == "":
            v = None
        uit[k] = v
    return uit


def instellingen_sha(waarden: dict[str, Any], sleutels: list[str]) -> str:
    return sha256_json(normaliseer_instellingen({k: waarden.get(k) for k in sleutels}))
