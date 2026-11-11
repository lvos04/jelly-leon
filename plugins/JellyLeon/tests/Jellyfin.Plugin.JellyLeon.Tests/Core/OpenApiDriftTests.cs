using System;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// Driftcontrole (contract §5): docs/openapi/jelly-leon-plugin.openapi.json is exact wat de routetabel oplevert.
/// Bijwerken: draai de tests één keer met de omgevingsvariabele <c>JL_SCHRIJF_OPENAPI=1</c>.
/// </summary>
public sealed class OpenApiDriftTests
{
    private static string RepoBestand([CallerFilePath] string hier = "") =>
        Path.GetFullPath(Path.Combine(Path.GetDirectoryName(hier)!, "..", "..", "..", "..", "..", "docs", "openapi", "jelly-leon-plugin.openapi.json"));

    [Fact]
    public void GepubliceerdDocument_IsGelijkAanDeRoutetabel()
    {
        var verwacht = OpenApiBouwer.Tekst();
        if (Environment.GetEnvironmentVariable("JL_SCHRIJF_OPENAPI") == "1")
        {
            File.WriteAllText(RepoBestand(), verwacht);
        }

        var gepubliceerd = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "jelly-leon-plugin.openapi.json"));
        if (Environment.GetEnvironmentVariable("JL_SCHRIJF_OPENAPI") == "1")
        {
            gepubliceerd = File.ReadAllText(RepoBestand());
        }

        Assert.True(
            string.Equals(verwacht, gepubliceerd, StringComparison.Ordinal),
            "docs/openapi/jelly-leon-plugin.openapi.json loopt achter op de routetabel. Draai de tests één keer met JL_SCHRIJF_OPENAPI=1 en commit het resultaat.");
    }

    [Fact]
    public void ElkeRoute_StaatPreciesEenKeerInHetDocument()
    {
        var paden = OpenApiBouwer.Bouw()["paths"]!.AsObject();
        var operaties = paden.SelectMany(p => p.Value!.AsObject().Select(o => o.Key.ToUpperInvariant() + " " + p.Key)).ToList();
        Assert.Equal(operaties.Count, operaties.Distinct(StringComparer.Ordinal).Count());
        Assert.Equal(
            RouteTable.Alle.Select(r => r.Methode + " " + r.Pad).Append("GET /media/v1/version").OrderBy(s => s, StringComparer.Ordinal),
            operaties.OrderBy(s => s, StringComparer.Ordinal));

        var ids = paden.SelectMany(p => p.Value!.AsObject().Select(o => o.Value!["operationId"]!.GetValue<string>())).ToList();
        Assert.Equal(ids.Count, ids.Distinct(StringComparer.Ordinal).Count());
    }

    [Fact]
    public void ElkeVerwijzing_BestaatEnMuterendeRoutesNoemenHunKoppen()
    {
        var document = OpenApiBouwer.Bouw();
        var schemas = document["components"]!["schemas"]!.AsObject();
        void Loop(JsonNode? node)
        {
            switch (node)
            {
                case JsonObject o:
                    if (o["$ref"] is JsonNode verwijzing)
                    {
                        Assert.True(schemas.ContainsKey(verwijzing.GetValue<string>().Split('/')[^1]), "Onbekend schema: " + verwijzing);
                    }

                    foreach (var (_, kind) in o)
                    {
                        Loop(kind);
                    }

                    break;
                case JsonArray a:
                    foreach (var kind in a)
                    {
                        Loop(kind);
                    }

                    break;
            }
        }

        Loop(document);
        foreach (var route in RouteTable.Alle)
        {
            var operatie = document["paths"]![route.Pad]![route.Methode.ToLowerInvariant()]!;
            var koppen = (operatie["parameters"] as JsonArray ?? []).Where(p => p!["in"]!.GetValue<string>() == "header").Select(p => p!["name"]!.GetValue<string>()).ToList();
            Assert.Equal(route.Idempotentie == JlIdem.Verplicht, koppen.Contains("Idempotency-Key"));
            Assert.Equal(route.IfMatch, koppen.Contains("If-Match"));
            Assert.Equal(route.Auth == JlAuth.Hub ? "HubJwt" : "CustomAuthentication", operatie["security"]![0]!.AsObject().Single().Key);
        }
    }
}
