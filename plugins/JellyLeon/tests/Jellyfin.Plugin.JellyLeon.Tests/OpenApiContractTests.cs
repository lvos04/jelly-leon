using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests;

/// <summary>
/// Driftcontrole (contract §5): het gepubliceerde docs/openapi/jelly-leon-plugin.openapi.json moet exact het
/// antwoordschema van <see cref="ForkVersionInfo"/> en alle mogelijke status-/redencodes beschrijven.
/// </summary>
public class OpenApiContractTests
{
    private static readonly DateTimeOffset Now = new(2026, 11, 9, 12, 0, 0, TimeSpan.Zero);

    private static JsonElement Schema()
    {
        var specPath = Path.Combine(AppContext.BaseDirectory, "jelly-leon-plugin.openapi.json");
        using var doc = JsonDocument.Parse(File.ReadAllText(specPath));
        return doc.RootElement.GetProperty("components").GetProperty("schemas").GetProperty("ForkVersionInfo").Clone();
    }

    private static string[] SerializedNames()
        => typeof(ForkVersionInfo)
            .GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Select(p => p.GetCustomAttribute<JsonPropertyNameAttribute>()?.Name ?? p.Name)
            .OrderBy(n => n, StringComparer.Ordinal)
            .ToArray();

    private static string[] EnumValues(JsonElement schema, string property)
        => schema.GetProperty("properties").GetProperty(property).GetProperty("enum")
            .EnumerateArray().Select(e => e.GetString()!).OrderBy(v => v, StringComparer.Ordinal).ToArray();

    [Fact]
    public void Schema_PropertiesMatchSerializedRecord()
    {
        var documented = Schema().GetProperty("properties").EnumerateObject()
            .Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray();
        Assert.Equal(SerializedNames(), documented);
    }

    [Fact]
    public void Schema_RequiresEveryField()
    {
        var required = Schema().GetProperty("required").EnumerateArray()
            .Select(e => e.GetString()!).OrderBy(n => n, StringComparer.Ordinal).ToArray();
        Assert.Equal(SerializedNames(), required);
    }

    [Fact]
    public void Schema_EnumsMatchEveryOutcomeOfForkInfo()
    {
        var outcomes = new List<ForkVersionInfo>
        {
            ForkInfo.Build("12.4.0", "Jellyfin Server", "12.4.0", "f", "t", "c", "p", Now),
            ForkInfo.Build("12.5.0", "Jellyfin Server", "12.4.0", "f", "t", "c", "p", Now),
            ForkInfo.Build("12.4.0", "Jelly Leon Server", "12.4.0", "f", "t", "c", "p", Now),
            ForkInfo.Build(null, "Jellyfin Server", "12.4.0", "f", "t", "c", "p", Now),
        };
        var statuses = outcomes.Select(o => o.Status).Distinct().OrderBy(v => v, StringComparer.Ordinal).ToArray();
        var reasons = outcomes.Select(o => o.ReasonCode).Distinct().OrderBy(v => v, StringComparer.Ordinal).ToArray();

        Assert.Equal(EnumValues(Schema(), "status"), statuses);
        Assert.Equal(EnumValues(Schema(), "reason_code"), reasons);
    }
}
