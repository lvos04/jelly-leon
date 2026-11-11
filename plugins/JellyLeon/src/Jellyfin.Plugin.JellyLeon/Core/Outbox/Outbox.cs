using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Core.Outbox;

/// <summary>
/// De ene outbox van de plugin (contract 1.3 §7). Modules melden events hier aan; de Hub haalt ze op met
/// <c>GET /connector/v1/events</c>. Een event dat de regels schendt wordt geweigerd (nooit stil aangepast).
/// </summary>
internal sealed partial class Outbox
{
    public const int MaxPayloadBytes = 16384;
    private const int BewaarSeconden = 30 * 86400;
    private readonly JlDatabase _db;
    private readonly TimeProvider _klok;

    public Outbox(CoreDatabase db, TimeProvider klok)
    {
        _db = db.Db;
        _klok = klok;
    }

    public static string Iso(DateTimeOffset moment) => moment.UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);

    /// <summary>Bouwt en controleert de envelop; gooit <see cref="ArgumentException"/> bij een ongeldig event.</summary>
    public static JsonObject Envelop(string eventType, string entityType, string entityId, JsonObject payload, DateTimeOffset nu, string actorType = "system", string actorId = "jelly-leon", string? correlationId = null)
    {
        if (eventType.Length > 128 || !EventType().IsMatch(eventType)
            || !(eventType.StartsWith("media.", StringComparison.Ordinal) || eventType == "app.health.changed"))
        {
            throw new ArgumentException("event_type moet drie segmenten hebben in het domein media (of app.health.changed).", nameof(eventType));
        }

        if (!EntityType().IsMatch(entityType) || entityId.Length is 0 or > 200 || !InhoudsBewaker.VeiligeTekst(entityId))
        {
            throw new ArgumentException("entity moet een veilig type en een ondoorzichtige ID hebben.", nameof(entityId));
        }

        if (actorType is not ("system" or "user" or "ai" or "flow") || actorId.Length is 0 or > 128 || !InhoudsBewaker.VeiligeTekst(actorId))
        {
            throw new ArgumentException("actor is ongeldig.", nameof(actorId));
        }

        if (InhoudsBewaker.EersteOvertreding(payload) is { } pad)
        {
            throw new ArgumentException("payload bevat een verboden waarde op " + pad + " (alleen aantallen, codes en ondoorzichtige ID's).", nameof(payload));
        }

        var inhoud = (JsonObject)payload.DeepClone();
        if (Encoding.UTF8.GetByteCount(inhoud.ToJsonString()) > MaxPayloadBytes)
        {
            inhoud = new JsonObject { ["_ingekort"] = true };
        }

        var eventId = Guid.NewGuid().ToString();
        return new JsonObject
        {
            ["schema_version"] = "1.0",
            ["event_id"] = eventId,
            ["source_app"] = "jelly-leon",
            ["source_event_id"] = "jl-" + eventId,
            ["event_type"] = eventType,
            ["entity"] = new JsonObject { ["type"] = entityType, ["id"] = entityId },
            ["timestamp_utc"] = Iso(nu),
            ["trace_id"] = Guid.NewGuid().ToString(),
            ["correlation_id"] = correlationId,
            ["actor"] = new JsonObject { ["type"] = actorType, ["id"] = actorId },
            ["classification"] = "internal",
            ["payload"] = inhoud,
            ["payload_ref"] = null,
        };
    }

    public string Meld(string module, string eventType, string entityType, string entityId, JsonObject payload, string actorType = "system", string actorId = "jelly-leon")
    {
        var nu = _klok.GetUtcNow();
        var envelop = Envelop(eventType, entityType, entityId, payload, nu, actorType, actorId);
        var eventId = envelop["event_id"]!.GetValue<string>();
        _db.Met(v =>
        {
            JlDatabase.Voer(v, "DELETE FROM outbox WHERE gemaakt < $grens", ("$grens", nu.ToUnixTimeSeconds() - BewaarSeconden));
            JlDatabase.Voer(
                v,
                "INSERT INTO outbox(event_id, module, json, gemaakt) VALUES($id, $m, $j, $nu)",
                ("$id", eventId),
                ("$m", module),
                ("$j", envelop.ToJsonString()),
                ("$nu", nu.ToUnixTimeSeconds()));
        });
        return eventId;
    }

    /// <summary>Events na <paramref name="na"/> (volgnummer), oplopend, hooguit <paramref name="limiet"/>.</summary>
    public (List<JsonNode> Events, long Laatste) Lees(long na, int limiet)
    {
        return _db.Met(v =>
        {
            var events = new List<JsonNode>();
            var laatste = na;
            foreach (var rij in JlDatabase.Rijen(v, "SELECT seq, json FROM outbox WHERE seq > $na ORDER BY seq LIMIT $l", ("$na", na), ("$l", limiet)))
            {
                laatste = (long)rij[0]!;
                events.Add(JsonNode.Parse((string)rij[1]!)!);
            }

            return (events, laatste);
        });
    }

    public void VerwijderModule(string module) =>
        _db.Met(v => JlDatabase.Voer(v, "DELETE FROM outbox WHERE module=$m", ("$m", module)));

    [GeneratedRegex(@"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$")]
    private static partial Regex EventType();

    [GeneratedRegex(@"^[a-z0-9_.-]{1,64}$")]
    private static partial Regex EntityType();
}
