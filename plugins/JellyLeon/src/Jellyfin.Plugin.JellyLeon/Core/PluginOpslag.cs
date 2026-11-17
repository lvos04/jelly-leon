using System;
using System.IO;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Core;

/// <summary>
/// Eenmalige opslagbeslissing voor deze serverstart. Een weigering schakelt alleen de plugin uit; er volgt geen
/// hercontrole of reparatie tijdens het draaien. De strenge constructor van JlPaths blijft de opslaggrens bewaken.
/// </summary>
internal sealed class PluginOpslag
{
    private const string Melding = "De eigen opslag en modules van Jelly Leon zijn niet beschikbaar. "
        + "Controleer in TrueNAS bij Apps → deze app → Edit → Storage de eigen data- en cacheopslag, en bij "
        + "Datasets → Permissions → Edit de eigenaar van de onderliggende mappen (de app-gebruiker), "
        + "geen schrijfrechten voor groep, anderen of extra ACL-regels en geen symbolische koppelingen. "
        + "Herstel dit via de TrueNAS-UI en herstart daarna de app. De mediaserver blijft beschikbaar.";

    private readonly JlPaths? _paden;

    public PluginOpslag(string data, string cache, ILogger<PluginOpslag> log)
    {
        try
        {
            _paden = new JlPaths(data, cache);
        }
        catch (Exception fout) when (fout is IOException or UnauthorizedAccessException or PlatformNotSupportedException)
        {
            // Eén vaste melding, zonder paden, bestandsinhoud of geheimen. Nooit de server stoppen of rechten verruimen.
            log.LogWarning("Jelly Leon: onveilige of onleesbare eigen opslag; alleen de plugin is uitgeschakeld. {Melding}", Melding);
        }
    }

    public bool Beschikbaar => _paden is not null;

    public JlPaths Paden => _paden ?? throw Fout(false, TimeProvider.System.GetUtcNow());

    public JlException Fout(bool hub, DateTimeOffset nu)
    {
        var details = new JsonObject
        {
            ["reason"] = hub ? "not_linked" : "storage_disabled",
            ["modules_enabled"] = false,
            ["restart_required"] = true,
            ["health"] = new JsonObject
            {
                ["status"] = "down",
                ["observed_at"] = Outbox.Outbox.Iso(nu),
                ["reason_code"] = "storage_unavailable",
                ["checks"] = new JsonArray(ConnectorService.Check("storage", "down", nu)),
            },
        };
        // Zonder veilige sleutelpin is Hub-authenticatie niet mogelijk: 401/not_linked blijft gelden (contract §4.7).
        return new JlException(hub ? 401 : 503, hub ? "unauthorized" : "storage_unavailable", Melding, details, hub ? null : 30);
    }
}
