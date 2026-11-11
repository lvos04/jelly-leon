using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Jellyfin.Plugin.JellyLeon.Core.Outbox;

/// <summary>
/// Bewaakt plan §10.4: connector-items en events bevatten alleen aantallen, codes, tijdstippen en ondoorzichtige
/// ID's — geen titels, bestandsnamen, paden, logregels, item-ID's, gebruikers- of apparaatnamen en geen IP-adressen.
/// </summary>
internal static partial class InhoudsBewaker
{
    /// <summary>Geeft het JSON-pad van de eerste verboden waarde, of <c>null</c> als de inhoud veilig is.</summary>
    public static string? EersteOvertreding(JsonNode? node, string pad = "$")
    {
        switch (node)
        {
            case null:
                return null;
            case JsonObject o:
                foreach (var (naam, waarde) in o)
                {
                    // Ook een veldnaam mag geen adres of ruwe ID zijn (bijvoorbeeld een telling per account).
                    if (!Code().IsMatch(naam) || Ipv4().IsMatch(naam) || Guid().IsMatch(naam))
                    {
                        return pad + "." + naam;
                    }

                    if (EersteOvertreding(waarde, pad + "." + naam) is { } gevonden)
                    {
                        return gevonden;
                    }
                }

                return null;
            case JsonArray a:
                for (var i = 0; i < a.Count; i++)
                {
                    if (EersteOvertreding(a[i], $"{pad}[{i}]") is { } gevonden)
                    {
                        return gevonden;
                    }
                }

                return null;
            default:
                var v = node.AsValue();
                if (v.GetValueKind() != JsonValueKind.String)
                {
                    return null;
                }

                var tekst = v.GetValue<string>();
                return VeiligeTekst(tekst) ? null : pad;
        }
    }

    public static bool VeiligeTekst(string tekst) =>
        Tijdstip().IsMatch(tekst) || OpaakId().IsMatch(tekst)
        || (Code().IsMatch(tekst) && !Ipv4().IsMatch(tekst) && !Guid().IsMatch(tekst));

    [GeneratedRegex(@"^[a-z0-9_.-]{1,64}$")]
    private static partial Regex Code();

    [GeneratedRegex(@"^o_[0-9a-f]{32}$")]
    private static partial Regex OpaakId();

    [GeneratedRegex(@"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,7})?Z$")]
    private static partial Regex Tijdstip();

    [GeneratedRegex(@"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")]
    private static partial Regex Ipv4();

    [GeneratedRegex(@"^[0-9a-f]{32}$|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
    private static partial Regex Guid();
}
