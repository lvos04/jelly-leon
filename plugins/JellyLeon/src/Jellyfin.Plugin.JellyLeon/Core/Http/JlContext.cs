using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Microsoft.AspNetCore.Http;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>De geauthenticeerde aanroeper van een pluginroute.</summary>
internal sealed record JlPrincipal(string Id, bool IsHub, bool IsDienst, IReadOnlyList<string> Rollen);

/// <summary>Wat de pipeline voor een actie heeft klaargezet.</summary>
internal sealed class JlContext
{
    public const string Sleutel = "JellyLeon.Context";

    public required string TraceId { get; init; }

    public required JlPrincipal Wie { get; init; }

    public required RouteSpec Route { get; init; }

    public JsonObject? Body { get; init; }

    public string? IfMatch { get; init; }

    public string? IdemScope { get; init; }

    public string? IdemSleutel { get; init; }

    public JlResult? Herhaling { get; init; }

    public static JlContext Van(HttpContext http) =>
        http.Items[Sleutel] as JlContext ?? throw new InvalidOperationException("Route zonder [JlRoute]: de pipeline is niet gelopen.");
}

/// <summary>Strikte lezer van een JSON-body: onbekende velden en verkeerde typen worden 422 (nooit afkappen).</summary>
internal sealed class BodyLezer
{
    private readonly JsonObject _body;
    private readonly HashSet<string> _gelezen = new(StringComparer.Ordinal);
    private readonly List<(string Veld, string Code, string Melding)> _fouten = [];

    public BodyLezer(JsonObject? body)
    {
        _body = body ?? new JsonObject();
    }

    public string? Tekst(string naam, bool verplicht, int maxLengte)
    {
        var node = Neem(naam, verplicht);
        if (node is null)
        {
            return null;
        }

        if (node.GetValueKind() != JsonValueKind.String)
        {
            Fout(naam, "type", "Verwacht tekst.");
            return null;
        }

        var tekst = node.GetValue<string>();
        if (tekst.Length == 0 || tekst.Length > maxLengte)
        {
            Fout(naam, "lengte", $"Verwacht 1 tot {maxLengte} tekens.");
            return null;
        }

        return tekst;
    }

    public bool? Bool(string naam, bool verplicht)
    {
        var node = Neem(naam, verplicht);
        if (node is null)
        {
            return null;
        }

        if (node.GetValueKind() is not (JsonValueKind.True or JsonValueKind.False))
        {
            Fout(naam, "type", "Verwacht true of false.");
            return null;
        }

        return node.GetValue<bool>();
    }

    public int? Geheel(string naam, bool verplicht, int min, int max)
    {
        var node = Neem(naam, verplicht);
        if (node is null)
        {
            return null;
        }

        if (node.GetValueKind() != JsonValueKind.Number || !node.AsValue().TryGetValue<int>(out var getal) || getal < min || getal > max)
        {
            Fout(naam, "bereik", $"Verwacht een geheel getal van {min} tot {max}.");
            return null;
        }

        return getal;
    }

    public JsonNode? Node(string naam, bool verplicht) => Neem(naam, verplicht);

    public void Fout(string veld, string code, string melding) => _fouten.Add((veld, code, melding));

    /// <summary>Sluit het lezen af: onbekende velden zijn een fout; bij fouten volgt 422 validation_error.</summary>
    public void Klaar()
    {
        foreach (var (naam, _) in _body)
        {
            if (!_gelezen.Contains(naam))
            {
                Fout(naam.Length > 64 ? naam[..64] : naam, "onbekend_veld", "Dit veld bestaat niet.");
            }
        }

        if (_fouten.Count > 0)
        {
            throw Fouten.Validatie(_fouten.Take(50).ToArray());
        }
    }

    private JsonNode? Neem(string naam, bool verplicht)
    {
        _gelezen.Add(naam);
        var node = _body[naam];
        if (node is null && verplicht)
        {
            Fout(naam, "verplicht", "Dit veld is verplicht.");
        }

        return node;
    }
}
