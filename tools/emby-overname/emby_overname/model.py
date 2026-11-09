"""Datamodel: kijkgegevens, iteminformatie en spoorkeuzes, met exacte (de)serialisatie."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .hulp import datum_naar_ticks, normaliseer_pad, ticks_naar_datum

# Afspeelbare items: kijkgegevens (gezien, aantal, datum, hervatpunt) horen bij het item zelf.
AFSPEELBAAR = {"Movie", "Episode", "Video", "MusicVideo", "Audio", "AudioBook", "Trailer"}
# Containers: gezien/aantal zijn afgeleid van de onderliggende items en worden niet los overgezet; alleen favoriet en
# beoordeling zijn eigen kijkgegevens.
CONTAINER = {"Series", "Season", "MusicAlbum", "BoxSet", "Playlist", "Folder", "CollectionFolder", "UserView",
             "Person", "MusicArtist", "Genre", "MusicGenre", "Studio", "PhotoAlbum", "Photo"}
# Typen die de tool kan koppelen; andere typen met kijkgegevens komen op de afhandellijst (nooit stil weg).
ONDERSTEUND = {"Movie", "Episode", "Video", "MusicVideo", "Audio", "Series", "Season", "MusicAlbum", "BoxSet",
               "Person", "MusicArtist", "Genre", "Studio"}
BENOEMD = {"Person": "/Persons", "MusicArtist": "/Artists", "Genre": "/Genres", "Studio": "/Studios"}
PROVIDER_VOLGORDE = ("imdb", "tmdb", "tvdb")


@dataclass(frozen=True)
class Kijkgegevens:
    gezien: bool = False
    aantal: int = 0
    laatst: int | None = None  # 100-ns-ticks sinds 1970 (exact)
    positie: int = 0  # hervatpunt in ticks (exact)
    favoriet: bool = False
    beoordeling: float | None = None
    vind_ik_leuk: bool | None = None

    @classmethod
    def uit_userdata(cls, ud: dict[str, Any] | None) -> Kijkgegevens:
        ud = ud or {}
        beoordeling = ud.get("Rating")
        return cls(
            gezien=bool(ud.get("Played", False)),
            aantal=int(ud.get("PlayCount") or 0),
            laatst=datum_naar_ticks(ud.get("LastPlayedDate")),
            positie=int(ud.get("PlaybackPositionTicks") or 0),
            favoriet=bool(ud.get("IsFavorite", False)),
            beoordeling=float(beoordeling) if beoordeling is not None else None,
            vind_ik_leuk=ud.get("Likes") if isinstance(ud.get("Likes"), bool) else None,
        )

    def heeft_gegevens(self, item_type: str) -> bool:
        eigen = self.favoriet or self.beoordeling is not None or self.vind_ik_leuk is not None
        if item_type in CONTAINER:
            return eigen
        return eigen or self.gezien or self.aantal > 0 or self.positie > 0 or self.laatst is not None

    def naar_json(self) -> dict[str, Any]:
        return {
            "gezien": self.gezien, "aantal": self.aantal, "laatst": ticks_naar_datum(self.laatst), "positie": self.positie,
            "favoriet": self.favoriet, "beoordeling": self.beoordeling, "vind_ik_leuk": self.vind_ik_leuk,
        }

    @classmethod
    def van_json(cls, data: dict[str, Any] | None) -> Kijkgegevens:
        data = data or {}
        return cls(
            gezien=bool(data.get("gezien", False)), aantal=int(data.get("aantal") or 0),
            laatst=datum_naar_ticks(data.get("laatst")), positie=int(data.get("positie") or 0),
            favoriet=bool(data.get("favoriet", False)),
            beoordeling=float(data["beoordeling"]) if data.get("beoordeling") is not None else None,
            vind_ik_leuk=data.get("vind_ik_leuk") if isinstance(data.get("vind_ik_leuk"), bool) else None,
        )


@dataclass
class ItemInfo:
    id: str
    type: str
    naam: str
    jaar: int | None = None
    provider_ids: dict[str, str] = field(default_factory=dict)
    pad: str | None = None
    grootte: int | None = None
    serie_id: str | None = None
    serie_naam: str | None = None
    seizoen: int | None = None
    aflevering: int | None = None
    classificatie: str | None = None
    bron_paden: list[str] = field(default_factory=list)  # alleen bij meerdere versies (mediabronnen) in één item

    @classmethod
    def uit_api(cls, item: dict[str, Any]) -> ItemInfo:
        provider = {str(k).casefold(): str(v).strip() for k, v in (item.get("ProviderIds") or {}).items()
                    if v is not None and str(v).strip()}
        return cls(
            id=str(item["Id"]), type=str(item.get("Type") or "Onbekend"), naam=str(item.get("Name") or ""),
            jaar=item.get("ProductionYear"), provider_ids=provider, pad=normaliseer_pad(item.get("Path")),
            grootte=_grootte(item), serie_id=item.get("SeriesId"), serie_naam=item.get("SeriesName"),
            seizoen=item.get("ParentIndexNumber"), aflevering=item.get("IndexNumber"),
            classificatie=item.get("OfficialRating"),
            bron_paden=_bron_paden(item),
        )

    def naar_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def van_json(cls, data: dict[str, Any]) -> ItemInfo:
        return cls(**data)

    def omschrijving(self) -> str:
        if self.type == "Episode":
            nummer = f"S{self.seizoen:02d}E{self.aflevering:02d}" if self.seizoen is not None and self.aflevering is not None else "S?E?"
            return f"{self.serie_naam or '?'} {nummer} — {self.naam}"
        if self.jaar:
            return f"{self.naam} ({self.jaar})"
        return self.naam


def _bron_paden(item: dict[str, Any]) -> list[str]:
    paden = sorted({p for p in (normaliseer_pad(b.get("Path")) for b in item.get("MediaSources") or []) if p})
    return paden if len(paden) > 1 else []


def _grootte(item: dict[str, Any]) -> int | None:
    if isinstance(item.get("Size"), int):
        return item["Size"]
    for bron in item.get("MediaSources") or []:
        if isinstance(bron.get("Size"), int):
            return bron["Size"]
    return None


@dataclass(frozen=True)
class Spoor:
    """Beschrijving van een gekozen spoor, los van het indexnummer (de nummering verschilt per server)."""

    type: str
    codec: str | None
    taal: str | None
    titel: str | None
    kanalen: int | None = None

    @classmethod
    def uit_stream(cls, stream: dict[str, Any]) -> Spoor:
        return cls(type=str(stream.get("Type")), codec=(stream.get("Codec") or None),
                   taal=(stream.get("Language") or None),
                   titel=(stream.get("Title") or None),
                   kanalen=stream.get("Channels") if stream.get("Type") == "Audio" else None)

    def naar_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def van_json(cls, data: dict[str, Any] | None) -> Spoor | None:
        return cls(**data) if data else None

    def gelijk_aan(self, ander: Spoor | None) -> bool:
        if ander is None:
            return False
        taal_a = _taal(self.taal)
        taal_b = _taal(ander.taal)
        return self.type == ander.type and (self.codec or "").casefold() == (ander.codec or "").casefold() and taal_a == taal_b

    def leesbaar(self) -> str:
        delen = [self.taal or "taal onbekend", self.codec or "?"]
        if self.titel:
            delen.append(f"“{self.titel}”")
        return " · ".join(delen)


_TAALCODES = {"dut": "nld", "nl": "nld", "en": "eng", "de": "deu", "ger": "deu", "fr": "fra", "fre": "fra"}


def _taal(code: str | None) -> str | None:
    if not code:
        return None
    code = code.casefold()
    return _TAALCODES.get(code, code)


def effectieve_spoorkeuze(afspeelinfo: dict[str, Any]) -> dict[str, Any]:
    """Uit PlaybackInfo: de sporen die de server voor deze gebruiker kiest (incl. onthouden keuze), plus het bestand."""
    bronnen = afspeelinfo.get("MediaSources") or []
    if not bronnen:
        return {}
    bron = bronnen[0]
    streams = {s.get("Index"): s for s in bron.get("MediaStreams") or []}
    resultaat: dict[str, Any] = {"bestand": {"pad": normaliseer_pad(bron.get("Path")), "grootte": bron.get("Size")}}
    for soort, sleutel in (("audio", "DefaultAudioStreamIndex"), ("ondertitel", "DefaultSubtitleStreamIndex")):
        index = bron.get(sleutel)
        if index is None or index < 0 or index not in streams:
            resultaat[soort] = None
        else:
            resultaat[soort] = Spoor.uit_stream(streams[index]).naar_json()
    return resultaat
