using System;
using System.Collections.Generic;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Modules.Recommendations.Engine;

/// <summary>Momentopname van bibliotheekmetadata. De engine leest uitsluitend deze waarden.</summary>
internal sealed record Titel(string Id, string Soort)
{
    public string[] Genres { get; init; } = [];
    public string[] Tags { get; init; } = [];
    public string[] Studios { get; init; } = [];
    public string[] Regisseurs { get; init; } = [];
    public string[] Schrijvers { get; init; } = [];
    public string[] Acteurs { get; init; } = [];
    public string[] Collecties { get; init; } = [];
    public string? Serie { get; init; }
    public string? Keur { get; init; }
    public int? Jaar { get; init; }
    public double? Waardering { get; init; }
    public DateTimeOffset? Toegevoegd { get; init; }
    public bool AnimeBibliotheek { get; init; }
    public string[] AnimeGenres { get; init; } = ["Anime"];
    public string[] Landen { get; init; } = [];

    public bool Anime => AnimeBibliotheek || Genres.Intersect(AnimeGenres, StringComparer.OrdinalIgnoreCase).Any()
        || (Genres.Any(g => Kenmerken.Genre(g) == "animation") && Landen.Contains("Japan", StringComparer.OrdinalIgnoreCase));

    public string QuotumType => Anime ? "Anime" : Soort;
}

// Eén actuele toestand per item. De optionele log is standaard uit.
internal sealed record Kijktoestand(string Item, DateTimeOffset? Tijd, bool Bekeken = false, bool Favoriet = false,
    double? Rating = null, bool? Likes = null, double Fractie = 0, bool Minder = false, bool Gemarkeerd = false)
{
    public double Gewicht(DateTimeOffset nu)
    {
        var dagen = Tijd.HasValue ? (nu - Tijd.Value).TotalDays : 0;
        var gewicht = Bekeken ? (Gemarkeerd ? 0.5 : 1.0) : 0;
        gewicht += Favoriet ? 1 : 0;
        gewicht += Rating >= 7 ? 0.5 : 0;
        gewicht += Likes == true ? 0.5 : 0;
        gewicht -= Likes == false || Minder ? 1 : 0;
        gewicht -= !Bekeken && Fractie is > 0 and < 0.2 && dagen > 14 ? 0.3 : 0;
        return gewicht * Math.Pow(0.5, dagen / 365);
    }
}

internal sealed record Deler(string Id, string Huishouden, bool Volwassen, bool Deelt, HashSet<string> Bekeken);

internal sealed record Kijkprofiel(string Id, HashSet<string> Toegang, Kijktoestand[] Toestand)
{
    public HashSet<string> NietInteressant { get; init; } = [];
    public HashSet<string> Volgende { get; init; } = [];
    public string[] OnboardingGenres { get; init; } = [];
    public HashSet<string> OnboardingTitels { get; init; } = [];
    public bool Exploratie { get; init; } = true;
    public bool Volwassen { get; init; }
    public bool HuishoudenAan { get; init; }
    public string? Huishouden { get; init; }
    public bool Ontvangt { get; init; }
    public int MinimumDelers { get; init; } = 3;
    public Deler[] Delers { get; init; } = [];

    public Dictionary<string, double> Huishoudscores()
    {
        if (!Volwassen || !HuishoudenAan || !Ontvangt || string.IsNullOrEmpty(Huishouden))
        {
            return [];
        }

        var anderen = Delers.Where(d => d.Volwassen && d.Deelt && d.Huishouden == Huishouden && d.Id != Id)
            .DistinctBy(d => d.Id).ToArray();
        var minimum = Math.Clamp(MinimumDelers, 3, 10);
        return anderen.SelectMany(d => d.Bekeken).Where(Toegang.Contains)
            .CountBy(id => id).Where(k => k.Value >= minimum)
            .ToDictionary(k => k.Key, k => (double)k.Value / anderen.Length, StringComparer.Ordinal);
    }
}

internal sealed record Reden(string Code, string? RefItemId = null);

internal sealed record Aanbeveling(string Item, double Score, Reden[] Redenen, bool Exploratie);
