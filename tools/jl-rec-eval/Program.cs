using System.Text.Json;
using System.Text.Json.Serialization;
using Jellyfin.Plugin.JellyLeon.Modules.Recommendations.Engine;

namespace JellyLeon.Evaluatie;

internal sealed record Aanvraag(DateTimeOffset Tijd, Kijkprofiel Profiel);
internal sealed record Momentopname(Titel[] Catalogus, Aanvraag[] Profielen);

internal sealed class VasteKlok(DateTimeOffset tijd) : TimeProvider
{
    public override DateTimeOffset GetUtcNow() => tijd;
}

internal static class Program
{
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        RespectRequiredConstructorParameters = true,
        RespectNullableAnnotations = true,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
    };

    public static int Main(string[] args)
    {
        if (args.Length != 1 || args[0] is not ("rangschik" or "valideer" or "handvoorbeelden"))
        {
            Console.Error.WriteLine("Gebruik: jl-rec-eval rangschik|valideer|handvoorbeelden < invoer.json");
            return 2;
        }

        try
        {
            using var invoer = Console.OpenStandardInput();
            if (args[0] == "handvoorbeelden")
            {
                return Metrieken.Controleer(invoer);
            }

            var opname = JsonSerializer.Deserialize<Momentopname>(invoer, Json);
            if (opname?.Catalogus is not { Length: > 0 } || opname.Profielen is not { Length: > 0 })
            {
                throw new InvalidDataException("Lege momentopname.");
            }

            var rijen = new Dictionary<string, Dictionary<string, IReadOnlyList<Aanbeveling>>>();
            foreach (var vraag in opname.Profielen)
            {
                var klok = new VasteKlok(vraag.Tijd);
                var p = vraag.Profiel;
                var rijenGebruiker = new Dictionary<string, IReadOnlyList<Aanbeveling>>();
                rijen.Add(p.Id, rijenGebruiker);
                if (args[0] == "valideer")
                {
                    // Vaste volgorde bij gelijke validatie-NDCG. Geen gewichten als argument in de testmodus.
                    foreach (var (naam, gewicht) in new (string, ScoreGewichten)[]
                    {
                        ("basis", new(0.55, 0.25)), ("inhoud", new(0.60, 0.20)), ("zaad", new(0.50, 0.30)),
                    })
                    {
                        rijenGebruiker[naam] = new KlassiekeEngine(klok, gewicht).Rangschik(opname.Catalogus, p, evaluatie: true);
                    }

                    continue;
                }

                var engine = new KlassiekeEngine(klok);
                rijenGebruiker["warm"] = engine.Rangschik(opname.Catalogus, p, evaluatie: true);
                for (var aantal = 0; aantal <= 2; aantal++)
                {
                    var kort = p.Toestand.OrderByDescending(t => t.Tijd).ThenBy(t => t.Item, StringComparer.Ordinal).Take(aantal).ToArray();
                    var koud = p with { Toestand = kort, Ontvangt = false };
                    rijenGebruiker[$"koud-{aantal}"] = engine.Rangschik(opname.Catalogus, koud, evaluatie: true);
                    rijenGebruiker[$"koud-{aantal}-opt-in"] = engine.Rangschik(opname.Catalogus, koud with { Ontvangt = true }, evaluatie: true);
                }
            }

            Console.WriteLine(JsonSerializer.Serialize(rijen, Json));
            return 0;
        }
        catch (Exception ex) when (ex is JsonException or ArgumentException or InvalidDataException or InvalidOperationException)
        {
            Console.Error.WriteLine("Ongeldige evaluatie-invoer: " + ex.Message);
            return 1;
        }
    }
}
