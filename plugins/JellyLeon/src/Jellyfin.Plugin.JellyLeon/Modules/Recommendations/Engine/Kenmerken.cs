using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Modules.Recommendations.Engine;

internal sealed class Kenmerken
{
    private readonly HashSet<string> _zeldzaam;

    public Kenmerken(IEnumerable<Titel> titels)
    {
        var termen = titels.ToDictionary(t => t.Id, Termen, StringComparer.Ordinal);
        var frequenties = termen.Values.SelectMany(t => t).CountBy(t => t).ToArray();
        _zeldzaam = frequenties.Where(p => p.Value <= 0.2 * termen.Count).Select(p => p.Key).ToHashSet(StringComparer.Ordinal);
        var gewichten = frequenties.ToDictionary(p => p.Key, p => 1 + Math.Log((1.0 + termen.Count) / (1 + p.Value)), StringComparer.Ordinal);
        Vectoren = termen.ToDictionary(p => p.Key, p => Normaliseer(p.Value.ToDictionary(k => k, k => gewichten[k])), StringComparer.Ordinal);
    }

    public Dictionary<string, Dictionary<string, double>> Vectoren { get; }

    public bool HeeftZeldzaam(string id, HashSet<string> voorkeur) =>
        Vectoren[id].Keys.Any(k => _zeldzaam.Contains(k) && voorkeur.Contains(k));

    internal static string Genre(string naam) => naam.Trim().ToLowerInvariant() switch
    {
        "animatie" => "animation",
        "sci-fi" or "sciencefiction" or "science fiction" or "sci-fi & fantasy" => "sciencefiction",
        "avontuur" => "adventure",
        "actie" => "action",
        "komedie" => "comedy",
        "misdaad" => "crime",
        "familie" => "family",
        "geschiedenis" => "history",
        "muziek" => "music",
        "oorlog" => "war",
        "romantiek" => "romance",
        "documentaire" => "documentary",
        var ander => ander,
    };

    private static string[] Termen(Titel t)
    {
        var termen = new SortedSet<string>(StringComparer.Ordinal);
        void VoegToe(string prefix, IEnumerable<string> waarden)
        {
            foreach (var waarde in waarden.Where(s => !string.IsNullOrWhiteSpace(s)))
            {
                termen.Add(prefix + waarde.Trim().ToLowerInvariant());
            }
        }

        VoegToe("genre/", t.Genres.Select(Genre));
        VoegToe("tag/", t.Tags);
        VoegToe("studio/", t.Studios);
        VoegToe("regisseur/", t.Regisseurs);
        VoegToe("schrijver/", t.Schrijvers);
        VoegToe("acteur/", t.Acteurs.Take(5));
        VoegToe("collectie/", t.Collecties);
        VoegToe("type/", [t.Soort]);
        if (t.Keur is not null) { VoegToe("keur/", [t.Keur]); }
        if (t.Jaar is > 0) { termen.Add("decennium/" + (t.Jaar.Value / 10).ToString(CultureInfo.InvariantCulture)); }
        if (t.Waardering.HasValue) { termen.Add("rating/" + Math.Floor(t.Waardering.Value / 2).ToString(CultureInfo.InvariantCulture)); }
        if (t.Anime) { termen.Add("anime"); }
        return [.. termen];
    }

    public static Dictionary<string, double> Normaliseer(Dictionary<string, double> waarden)
    {
        var lengte = Math.Sqrt(waarden.Values.Sum(x => x * x));
        if (lengte > 0)
        {
            foreach (var sleutel in waarden.Keys) { waarden[sleutel] /= lengte; }
        }

        return waarden;
    }

    public static double Cosinus(Dictionary<string, double> a, Dictionary<string, double> b)
    {
        if (a.Count > b.Count) { (a, b) = (b, a); }
        var som = 0.0;
        foreach (var (kenmerk, gewicht) in a) { som += gewicht * b.GetValueOrDefault(kenmerk); }
        return som;
    }
}
