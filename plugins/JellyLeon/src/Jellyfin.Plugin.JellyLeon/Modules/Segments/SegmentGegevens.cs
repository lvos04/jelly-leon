using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Jellyfin.Database.Implementations.Enums;
using Jellyfin.Plugin.JellyLeon.Core.Errors;

namespace Jellyfin.Plugin.JellyLeon.Modules.Segments;

internal sealed record Tijdvak(MediaSegmentType Type, long Start, long Einde, string Bron, double Zekerheid)
{
    [JsonIgnore]
    public bool Publiceerbaar => Bron is "manual" or "confirmed" ||
        (Bron != "hint" && Zekerheid >= (Type == MediaSegmentType.Intro ? .80 : .85));
}

internal sealed record SegmentItem(
    Guid ItemId, Guid Bibliotheek, Guid? Serie, int? Seizoen, int? Aflevering, long Duur,
    long Mtime, string? Herkomst, Tijdvak[] Kandidaten, bool Bevestigd = false, bool Wees = false, bool Heruitlijnen = false)
{
    public void Controleer()
    {
        if (ItemId == Guid.Empty || Bibliotheek == Guid.Empty || Serie == Guid.Empty || Duur <= 0 ||
            Mtime < 0 || Seizoen < 0 || Aflevering < 0 || (Herkomst is not null &&
            (Herkomst.Length != 64 || !Herkomst.All(char.IsAsciiHexDigit))) || Kandidaten is null || Kandidaten.Length > 2048)
        {
            throw Fouten.Validatie(("item", "invalid_item", "Ongeldige itemgegevens."));
        }

        ControleerVakken(Duur, Kandidaten);
    }

    internal static void ControleerVakken(long duur, IEnumerable<Tijdvak> vakken)
    {
        long einde = 0;
        foreach (var vak in vakken)
        {
            if (vak is null || vak.Type is not (MediaSegmentType.Intro or MediaSegmentType.Outro or
                MediaSegmentType.Recap or MediaSegmentType.Preview or MediaSegmentType.Commercial))
            {
                throw Fouten.Validatie(("segments", "unknown_type", "Onbekend segmenttype."));
            }

            if (vak.Start < einde || vak.Start >= vak.Einde || vak.Einde > duur ||
                !double.IsFinite(vak.Zekerheid) || vak.Zekerheid is < 0 or > 1 ||
                vak.Bron is not ("chapter" or "detected" or "manual" or "confirmed" or "hint" or "propagated"))
            {
                throw Fouten.Validatie(("segments", "invalid_interval", "Controleer duur, volgorde, overlap, bron en zekerheid."));
            }

            einde = vak.Einde;
        }
    }
}

internal static class SegmentGegevens
{
    internal static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        Converters = { new JsonStringEnumConverter<MediaSegmentType>(allowIntegerValues: false) },
    };

    public static string Hash(string inhoud) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(inhoud)));

    public static Tijdvak[] UitHoofdstukken(IEnumerable<(long Start, string? Naam)> hoofdstukken, long duur)
    {
        var grenzen = hoofdstukken.Where(h => h.Start >= 0 && h.Start < duur).OrderBy(h => h.Start).ToArray();
        var uit = new List<Tijdvak>();
        for (var i = 0; i < grenzen.Length; i++)
        {
            var type = grenzen[i].Naam?.Trim().ToLowerInvariant() switch
            {
                "intro" or "opening" or "opening credits" => MediaSegmentType.Intro,
                "recap" or "samenvatting" or "previously on" => MediaSegmentType.Recap,
                "credits" or "end credits" or "aftiteling" or "ending" => MediaSegmentType.Outro,
                "preview" or "vooruitblik" => MediaSegmentType.Preview,
                _ => MediaSegmentType.Unknown,
            };
            var einde = i + 1 < grenzen.Length ? grenzen[i + 1].Start : duur;
            // Een titel wijst alleen het eigen hoofdstuk aan. Ook onbekende hoofdstukken begrenzen het vorige.
            if (type != MediaSegmentType.Unknown && einde > grenzen[i].Start && (i == 0 || grenzen[i - 1].Start != grenzen[i].Start))
            {
                uit.Add(new Tijdvak(type, grenzen[i].Start, einde, "chapter", .9));
            }
        }

        return uit.ToArray();
    }
}
