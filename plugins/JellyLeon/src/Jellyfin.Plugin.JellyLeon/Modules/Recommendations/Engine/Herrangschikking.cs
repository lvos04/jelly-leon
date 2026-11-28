using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace Jellyfin.Plugin.JellyLeon.Modules.Recommendations.Engine;

internal static class Herrangschikking
{
    public static List<Aanbeveling> Kies(List<Kandidaat> kandidaten, Dictionary<string, int> voorkeur,
        int limiet, bool exploratie, string gebruiker, DateTimeOffset nu, CancellationToken stop)
    {
        var doel = VerdeelTypen(voorkeur, kandidaten, limiet);
        var aantallen = new Dictionary<string, int>();
        var groepen = new Dictionary<string, int>();
        var overlap = new Dictionary<string, double>();
        var uit = new List<Aanbeveling>();
        var dagseed = gebruiker + "/" + nu.UtcDateTime.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) + "/";
        while (uit.Count < limiet && kandidaten.Count > 0)
        {
            stop.ThrowIfCancellationRequested();
            var vrij = kandidaten.Where(k => Groepen(k.Titel).All(g => groepen.GetValueOrDefault(g) < 2)).ToList();
            if (vrij.Count == 0) { break; }
            var quotum = vrij.Where(k => aantallen.GetValueOrDefault(k.Titel.QuotumType) < doel.GetValueOrDefault(k.Titel.QuotumType)).ToList();
            if (quotum.Count > 0) { vrij = quotum; }
            var ontdek = exploratie && (uit.Count + 1) % 10 == 0;
            var gekozen = ontdek
                ? vrij.MinBy(k => Lot(dagseed, k.Titel.Id), StringComparer.Ordinal)!
                : vrij.OrderByDescending(k => 0.7 * k.Score - 0.3 * overlap.GetValueOrDefault(k.Titel.Id))
                    .ThenBy(k => k.Titel.Id, StringComparer.Ordinal).First();

            Reden[] redenen = ontdek && gekozen.Reden.Code != "exploration" ? [gekozen.Reden, new("exploration")] : [gekozen.Reden];
            uit.Add(new(gekozen.Titel.Id, gekozen.Score, redenen, ontdek));
            kandidaten.Remove(gekozen);
            var type = gekozen.Titel.QuotumType;
            aantallen[type] = aantallen.GetValueOrDefault(type) + 1;
            foreach (var groep in Groepen(gekozen.Titel)) { groepen[groep] = groepen.GetValueOrDefault(groep) + 1; }
            foreach (var k in kandidaten)
            {
                overlap[k.Titel.Id] = Math.Max(overlap.GetValueOrDefault(k.Titel.Id), Kenmerken.Cosinus(k.Vector, gekozen.Vector));
            }
        }

        return uit;
    }

    private static IEnumerable<string> Groepen(Titel t)
    {
        if (t.Serie is not null) { yield return "s/" + t.Serie; }
        foreach (var groep in t.Collecties.Where(g => !string.IsNullOrWhiteSpace(g)).Distinct(StringComparer.Ordinal))
        {
            yield return "c/" + groep;
        }
    }

    private static string Lot(string dagseed, string id) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(dagseed + id)));

    private static Dictionary<string, int> VerdeelTypen(Dictionary<string, int> voorkeur, List<Kandidaat> kandidaten, int limiet)
    {
        var beschikbaar = kandidaten.Select(k => k.Titel.QuotumType).ToHashSet();
        var aandelen = voorkeur.Where(p => beschikbaar.Contains(p.Key))
            .OrderByDescending(p => p.Value).ThenBy(p => p.Key, StringComparer.Ordinal).Take(limiet).ToArray();
        var doel = aandelen.ToDictionary(p => p.Key, _ => 1);
        var totaal = aandelen.Sum(p => p.Value);
        for (var plek = doel.Count; totaal > 0 && plek < limiet; plek++)
        {
            var type = aandelen.MaxBy(p => (double)p.Value / totaal * limiet - doel[p.Key]).Key;
            doel[type]++;
        }

        return doel;
    }
}
