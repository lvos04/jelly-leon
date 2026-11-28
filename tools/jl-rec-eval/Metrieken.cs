using System.Text.Json;

namespace JellyLeon.Evaluatie;

internal static class Metrieken
{
    private static string[] Lijst(JsonElement veld) => veld.EnumerateArray().Select(s => s.GetString()!).ToArray();

    internal static int Controleer(Stream bron)
    {
        using var document = JsonDocument.Parse(bron);
        var wortel = document.RootElement;
        var genres = wortel.GetProperty("catalogus").EnumerateObject()
            .ToDictionary(p => p.Name, p => Lijst(p.Value).ToHashSet(StringComparer.Ordinal));
        var gevallen = wortel.GetProperty("gevallen").EnumerateArray().ToArray();
        if (gevallen.Length < 2 || genres.Count == 0) { throw new InvalidDataException("Onvoldoende handvoorbeelden."); }
        var titels = new HashSet<string>();
        static void Vergelijk(double getal, JsonElement verwacht)
        {
            if (Math.Abs(getal - verwacht.GetDouble()) > 1e-12) { throw new InvalidDataException("Handvoorbeeld wijkt af."); }
        }

        for (var i = 0; i < gevallen.Length; i++)
        {
            var g = gevallen[i];
            var top = Lijst(g.GetProperty("top"));
            var relevant = Lijst(g.GetProperty("holdout")).ToHashSet();
            if (relevant.Count == 0 || top.Length > 10 || top.Distinct().Count() != top.Length || top.Any(id => !genres.ContainsKey(id)))
            {
                throw new InvalidDataException("Ongeldige holdout of top 10.");
            }

            var treffers = top.Select((id, index) => (id, index)).Where(t => relevant.Contains(t.id)).ToArray();
            var dcg = treffers.Sum(t => 1 / Math.Log2(t.index + 2));
            var ideaal = Enumerable.Range(0, Math.Min(10, relevant.Count)).Sum(r => 1 / Math.Log2(r + 2));
            var afstanden = new List<double>();
            for (var a = 0; a < top.Length; a++)
            {
                for (var b = 0; b < a; b++)
                {
                    var unie = genres[top[a]].Union(genres[top[b]]).Count();
                    afstanden.Add(unie == 0 ? 0 : 1.0 - (double)genres[top[a]].Intersect(genres[top[b]]).Count() / unie);
                }
            }

            Vergelijk(dcg / ideaal, g.GetProperty("NDCG@10"));
            Vergelijk((double)treffers.Length / relevant.Count, g.GetProperty("Recall@10"));
            Vergelijk(afstanden.Count == 0 ? 0 : afstanden.Average(), g.GetProperty("ILD"));
            titels.UnionWith(top);
            if (i < 2) { Vergelijk((double)titels.Count / genres.Count, wortel.GetProperty(i == 0 ? "coverage_eerste" : "coverage_eerste_twee")); }
        }

        Console.WriteLine($"{gevallen.Length} handvoorbeelden en 2 coverage-controles gelijk binnen 1e-12.");
        return 0;
    }
}
