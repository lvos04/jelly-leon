using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;

namespace Jellyfin.Plugin.JellyLeon.Core.Modules;

/// <summary>Een privé modulebundel. Alleen lokaal gevalideerde waarden uit het voorbeeld bereiken de import.</summary>
internal abstract class ModuleOverdracht
{
    private readonly object _slot = new();
    private readonly Dictionary<string, Voorbeeld> _voorbeelden = new(StringComparer.Ordinal);

    public abstract string Slug { get; }

    protected virtual bool HadVersielozeExport => false;

    protected virtual IReadOnlyList<string> ExportTellingen => [];

    protected sealed record Herstelplan(JsonObject Aantallen, Action PasToe);

    private sealed record Voorbeeld(string Hash, DateTimeOffset Vervalt, Herstelplan Plan);

    public JsonObject Exporteer()
    {
        var bundel = ExportInhoud();
        bundel["preview_hash"] = InhoudHash(bundel);
        return bundel;
    }

    public JsonObject ImporteerVoorbeeld(JsonObject bundel, string aanvrager, DateTimeOffset nu)
    {
        var lezer = new BodyLezer(bundel);
        var module = lezer.Tekst("module", true, 64);
        // Oudere Watch Together-exports hadden uitsluitend de modulenaam.
        var versie = lezer.Tekst("schema_version", !HadVersielozeExport || bundel.Count != 1, 16);
        if (module != Slug || (versie is not null && versie != "1.0"))
        {
            throw Fouten.Validatie(("module", "export_schema", "De bundel hoort bij een andere module of schemaversie."));
        }

        var meegegeven = lezer.Tekst("preview_hash", false, 64);
        foreach (var veld in ExportTellingen)
        {
            // Historische tellingen beschrijven de bron. Er worden nooit afspeelsessies of auteurs uit gereconstrueerd.
            var node = lezer.Node(veld, true);
            if (node?.GetValueKind() != JsonValueKind.Number ||
                !long.TryParse(node.ToJsonString(), NumberStyles.None, CultureInfo.InvariantCulture, out _))
            {
                lezer.Fout(veld, "telling", "Verwacht een niet-negatief geheel getal.");
            }
        }

        var hash = InhoudHash(bundel);
        if (bundel.ContainsKey("preview_hash") && meegegeven != hash)
        {
            throw Fouten.Conflict("preview_hash_mismatch");
        }

        var plan = LeesHerstel(lezer);
        lezer.Klaar();
        lock (_slot)
        {
            foreach (var sleutel in _voorbeelden.Where(p => p.Value.Vervalt <= nu).Select(p => p.Key).ToArray())
            {
                _voorbeelden.Remove(sleutel);
            }

            if (_voorbeelden.Count >= 8 && !_voorbeelden.ContainsKey(aanvrager))
            {
                throw Fouten.TeVeelVerzoeken(60);
            }

            _voorbeelden[aanvrager] = new Voorbeeld(hash, nu.AddMinutes(15), plan);
        }

        return new JsonObject { ["counts"] = plan.Aantallen.DeepClone(), ["preview_hash"] = hash };
    }

    public JsonObject Importeer(string previewHash, string aanvrager, DateTimeOffset nu)
    {
        lock (_slot)
        {
            if (!_voorbeelden.TryGetValue(aanvrager, out var voorbeeld) || voorbeeld.Hash != previewHash || voorbeeld.Vervalt <= nu)
            {
                throw Fouten.Conflict("preview_hash_mismatch");
            }

            voorbeeld.Plan.PasToe();
            _voorbeelden.Remove(aanvrager);
            return new JsonObject { ["counts"] = voorbeeld.Plan.Aantallen.DeepClone(), ["applied"] = true };
        }
    }

    protected virtual JsonObject ExportInhoud() => new() { ["module"] = Slug, ["schema_version"] = "1.0" };

    protected virtual Herstelplan LeesHerstel(BodyLezer lezer) => new(new JsonObject(), () => { });

    private static string InhoudHash(JsonObject bundel)
    {
        var inhoud = new JsonObject();
        foreach (var (naam, waarde) in bundel.Where(p => p.Key != "preview_hash").OrderBy(p => p.Key, StringComparer.Ordinal))
        {
            inhoud.Add(naam, Sorteer(waarde));
        }

        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(inhoud.ToJsonString())));
    }

    private static JsonNode? Sorteer(JsonNode? waarde) => waarde switch
    {
        JsonObject obj => new JsonObject(obj.OrderBy(p => p.Key, StringComparer.Ordinal)
            .Select(p => KeyValuePair.Create(p.Key, Sorteer(p.Value)))),
        JsonArray lijst => new JsonArray(lijst.Select(Sorteer).ToArray()),
        _ => waarde?.DeepClone(),
    };
}
