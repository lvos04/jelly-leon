using System;
using System.Globalization;
using System.Linq;
using System.Reflection;

namespace Jellyfin.Plugin.JellyLeon;

/// <summary>
/// Bouwt de versie-/compatibiliteitsinformatie. Puur en testbaar: alle invoer komt als parameters binnen.
/// </summary>
public static class ForkInfo
{
    /// <summary>De technische productnaam die stock clients verwachten (ADR-0003).</summary>
    public const string ExpectedProductName = "Jellyfin Server";

    /// <summary>
    /// Leest een <see cref="AssemblyMetadataAttribute"/> uit de plugin-assembly; leeg wordt <c>unknown</c>.
    /// </summary>
    /// <param name="key">Sleutel, bv. <c>JellyLeon.ForkVersion</c>.</param>
    /// <returns>De waarde of <c>unknown</c>.</returns>
    public static string GetMetadata(string key)
    {
        var value = typeof(ForkInfo).Assembly
            .GetCustomAttributes<AssemblyMetadataAttribute>()
            .FirstOrDefault(a => string.Equals(a.Key, key, StringComparison.Ordinal))?.Value;
        return string.IsNullOrWhiteSpace(value) ? "unknown" : value;
    }

    /// <summary>
    /// Bepaalt of de plugin bij de draaiende server past en of de technische identiteit intact is.
    /// </summary>
    /// <param name="serverVersion">Versie die de server meldt (<c>IServerApplicationHost.ApplicationVersionString</c>).</param>
    /// <param name="serverProductName">Productnaam die de server meldt.</param>
    /// <param name="builtAgainst">Jellyfin-versie waartegen de plugin is gebouwd.</param>
    /// <param name="forkVersion">Forkversie uit baseline.json.</param>
    /// <param name="upstreamTag">Upstream-tag uit baseline.json.</param>
    /// <param name="upstreamCommit">Upstream-commit uit baseline.json.</param>
    /// <param name="pluginVersion">Assemblyversie van de plugin.</param>
    /// <param name="now">Tijdstip van waarneming.</param>
    /// <returns>Het antwoord voor <c>GET /media/v1/version</c>.</returns>
    public static ForkVersionInfo Build(
        string? serverVersion,
        string? serverProductName,
        string builtAgainst,
        string forkVersion,
        string upstreamTag,
        string upstreamCommit,
        string pluginVersion,
        DateTimeOffset now)
    {
        var server = string.IsNullOrWhiteSpace(serverVersion) ? "unknown" : serverVersion.Trim();
        var product = string.IsNullOrWhiteSpace(serverProductName) ? "unknown" : serverProductName.Trim();

        string status;
        string reason;
        string message;
        if (server == "unknown" || product == "unknown" || builtAgainst == "unknown")
        {
            status = "unknown";
            reason = "version_unknown";
            message = "Versie van server of plugin is onbekend; compatibiliteit kan niet worden vastgesteld.";
        }
        else if (!string.Equals(product, ExpectedProductName, StringComparison.Ordinal))
        {
            status = "afwijkend";
            reason = "technical_identity_changed";
            message = $"De server meldt productnaam '{product}' in plaats van '{ExpectedProductName}'; stock clients kunnen hierdoor falen.";
        }
        else if (!SameVersion(server, builtAgainst))
        {
            status = "afwijkend";
            reason = "plugin_abi_mismatch";
            message = $"Plugin gebouwd tegen Jellyfin {builtAgainst}, maar de server is {server}. Installeer de plugin die bij deze serverversie hoort.";
        }
        else
        {
            status = "compatibel";
            reason = "ok";
            message = $"Plugin en server gebruiken dezelfde Jellyfin-versie ({server}); technische identiteit ongewijzigd.";
        }

        return new ForkVersionInfo
        {
            ForkVersion = forkVersion,
            UpstreamTag = upstreamTag,
            UpstreamCommit = upstreamCommit,
            PluginBuiltAgainst = builtAgainst,
            PluginVersion = pluginVersion,
            ServerVersion = server,
            ServerProductName = product,
            Status = status,
            ReasonCode = reason,
            Message = message,
            ObservedAt = now.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture),
        };
    }

    /// <summary>
    /// Vergelijkt versies numeriek; <c>10.11.11</c> en <c>10.11.11.0</c> zijn gelijk.
    /// </summary>
    /// <param name="left">Eerste versie.</param>
    /// <param name="right">Tweede versie.</param>
    /// <returns><c>true</c> als beide versies gelijk zijn.</returns>
    public static bool SameVersion(string left, string right)
    {
        if (Version.TryParse(Normalize(left), out var a) && Version.TryParse(Normalize(right), out var b))
        {
            return a == b;
        }

        return string.Equals(left, right, StringComparison.Ordinal);
    }

    private static string Normalize(string value)
    {
        var parts = value.Split('.');
        return parts.Length switch
        {
            2 => value + ".0.0",
            3 => value + ".0",
            _ => value,
        };
    }
}
