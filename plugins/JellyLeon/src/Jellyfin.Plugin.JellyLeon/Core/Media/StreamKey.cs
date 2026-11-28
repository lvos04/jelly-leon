using System;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Serialization;

namespace Jellyfin.Plugin.JellyLeon.Core.Media;

/// <summary>Stabiele sleutel van één stream (plan §10.12), gedeeld door alle modules.</summary>
internal sealed record StreamKey([property: JsonPropertyName("track_key")] string Waarde)
{
    /// <summary>Leest de bestandskenmerken van een extern spoor uit de bibliotheek.</summary>
    public static StreamKey Extern(string pad)
    {
        var bestand = new FileInfo(pad);
        return new(Extern(pad, bestand.Length, bestand.LastWriteTimeUtc));
    }

    /// <summary><c>emb:&lt;index&gt;:&lt;codec&gt;:&lt;taal&gt;:&lt;kanalen&gt;:&lt;titelhash&gt;</c>.</summary>
    public static string Ingebed(int index, string? codec, string? taal, int? kanalen, string? titel) => string.Create(
        CultureInfo.InvariantCulture,
        $"emb:{index}:{Veld(codec)}:{Veld(taal)}:{kanalen ?? 0}:{Hash(titel ?? string.Empty)[..12]}");

    /// <summary><c>ext:&lt;sha256 van pad, grootte en mtime&gt;</c>.</summary>
    public static string Extern(string pad, long grootte, DateTime mtimeUtc) =>
        "ext:" + Hash(string.Create(CultureInfo.InvariantCulture, $"{pad}\n{grootte}\n{new DateTimeOffset(mtimeUtc, TimeSpan.Zero).ToUnixTimeSeconds()}"));

    private static string Veld(string? waarde) =>
        string.IsNullOrEmpty(waarde) ? "und" : waarde.ToLowerInvariant().Replace(':', '_');

    private static string Hash(string tekst) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(tekst)));
}
