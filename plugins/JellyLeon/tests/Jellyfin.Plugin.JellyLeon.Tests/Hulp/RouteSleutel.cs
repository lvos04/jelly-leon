using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;

namespace Jellyfin.Plugin.JellyLeon.Tests.Hulp;

/// <summary>
/// De sleutel waarop de server twee routes als dezelfde ziet (R-TECH-5, S-G1-17): de routing van ASP.NET Core is
/// hoofdletterongevoelig, de naam van een padparameter telt niet en een slash aan het eind ook niet. Een
/// uniekheidscontrole op de letterlijke tekst zou <c>GET /media/v1/hub-link</c> en <c>GET /media/v1/Hub-link</c> als
/// twee routes tellen.
/// </summary>
internal static partial class RouteSleutel
{
    public static string Van(string methode, string pad) =>
        methode.ToUpperInvariant() + " " + Parameter().Replace(pad.ToUpperInvariant(), "{}").TrimEnd('/');

    /// <summary>De sleutels die meer dan één keer voorkomen.</summary>
    public static IReadOnlyList<string> Dubbel(IEnumerable<(string Methode, string Pad)> routes) =>
        routes.GroupBy(r => Van(r.Methode, r.Pad), StringComparer.Ordinal).Where(g => g.Count() > 1).Select(g => g.Key).ToList();

    [GeneratedRegex(@"\{[^}]*\}", RegexOptions.CultureInvariant)]
    private static partial Regex Parameter();
}
