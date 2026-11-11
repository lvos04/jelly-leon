using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Modules;

namespace Jellyfin.Plugin.JellyLeon.Core.MediaGuard;

/// <summary>Wat Jelly Leon over MediaGuard weet. Alles behalve <see cref="Ok"/> betekent: geen uitspraak, dus geen batch.</summary>
internal enum MgStatus
{
    /// <summary>Geen weg naar MediaGuard of nog niet gemeten.</summary>
    Onbekend,

    /// <summary>Rol viewer bevestigd en de laatste meting is gelukt.</summary>
    Ok,

    /// <summary>De rol is niet viewer: fail-closed, er wordt niets meer opgevraagd tot de volgende rolcontrole.</summary>
    Geweigerd,

    /// <summary>MediaGuard antwoordde niet of niet bruikbaar.</summary>
    Onbereikbaar,
}

/// <summary>Eén encoder-lane uit <c>/app/status</c> (alleen de vier velden van de witte lijst).</summary>
internal sealed record MgLane(string Lane, int? Running, int? Slots, bool? Paused);

/// <summary>Momentopname van de ene viewerclient; onveranderlijk, zodat lezers nooit een half beeld zien.</summary>
internal sealed record MgBeeld(
    MgStatus Status,
    string Reden,
    DateTimeOffset? GemetenOp,
    bool? EncoderBereikbaar,
    IReadOnlyList<MgLane> Lanes,
    bool? KijkpauzeActief,
    bool? ServerVerbonden,
    string? ServerSoort)
{
    public static MgBeeld Zonder(MgStatus status, string reden, DateTimeOffset? gemetenOp = null) =>
        new(status, reden, gemetenOp, null, [], null, null, null);
}

/// <summary>
/// De ene MediaGuard-viewerclient van de plugin (B03-009, contract 1.3 §2.3, ADR-0034). Alleen rol viewer (controle via
/// <c>auth/me</c> bij de start en daarna elk uur; een andere rol is fail-closed), alleen routes en velden van de witte
/// lijst, alleen lezen. Ruwe antwoorden verlaten deze klasse niet: ze worden niet gelogd en niet bewaard.
/// </summary>
internal sealed class MediaGuardClient : IDisposable
{
    /// <summary>Interval van de poller in seconden (plan §10.5: <c>MediaGuard.PollSeconds</c>).</summary>
    public const int PollSeconds = 20;

    /// <summary>Interval van de rol- en koppelcontrole in minuten (plan §10.5: <c>MediaGuard.LinkCheckMinutes</c>).</summary>
    public const int LinkCheckMinutes = 60;

    private readonly IMediaGuardVervoer _vervoer;
    private readonly TimeProvider _klok;
    private readonly ConcurrentDictionary<string, int> _aanroepen = new(StringComparer.Ordinal);
    private readonly SemaphoreSlim _slot = new(1, 1);
    private volatile MgBeeld _beeld = MgBeeld.Zonder(MgStatus.Onbekend, "nog_niet_gemeten");
    private DateTimeOffset? _rolGecontroleerd;
    private bool _rolViewer;
    private JsonObject? _server;

    public MediaGuardClient(IMediaGuardVervoer vervoer, TimeProvider klok)
    {
        _vervoer = vervoer;
        _klok = klok;
    }

    public void Dispose() => _slot.Dispose();

    /// <summary>Gets de laatste momentopname.</summary>
    public MgBeeld Beeld => _beeld;

    /// <summary>Gets a value indicating whether er een weg naar MediaGuard is (anders hoeft niemand te pollen).</summary>
    public bool HeeftVervoer => _vervoer.Beschikbaar;

    /// <summary>Gets het aantal aanroepen per route-ID sinds de start (alleen tellers, geen inhoud).</summary>
    public IReadOnlyDictionary<string, int> Aanroepen => _aanroepen;

    /// <summary>Eén ronde: rolcontrole als die aan de beurt is, daarna de leesroutes. Gooit nooit; de uitkomst staat in <see cref="Beeld"/>.</summary>
    public async Task VerversAsync(CancellationToken annulering)
    {
        await _slot.WaitAsync(annulering).ConfigureAwait(false);
        try
        {
            _beeld = await MeetAsync(annulering).ConfigureAwait(false);
        }
        finally
        {
            _slot.Release();
        }
    }

    private async Task<MgBeeld> MeetAsync(CancellationToken annulering)
    {
        var nu = _klok.GetUtcNow();
        if (!_vervoer.Beschikbaar)
        {
            return MgBeeld.Zonder(MgStatus.Onbekend, "geen_route_via_hub", nu);
        }

        try
        {
            var rolAanDeBeurt = _rolGecontroleerd is not DateTimeOffset laatst || nu - laatst >= TimeSpan.FromMinutes(LinkCheckMinutes);
            if (rolAanDeBeurt)
            {
                _rolViewer = false;
                _server = null;
                var ik = await LeesAsync(MediaGuardWitteLijst.AuthMe, annulering).ConfigureAwait(false);
                if (ik is null)
                {
                    return MgBeeld.Zonder(MgStatus.Onbereikbaar, "auth_me_mislukt", nu);
                }

                _rolGecontroleerd = nu;
                _rolViewer = Tekst(ik["role"]) == "viewer";
            }

            if (!_rolViewer)
            {
                // Fail-closed: geen enkele andere aanroep tot de volgende rolcontrole (volgende start of over een uur).
                return MgBeeld.Zonder(MgStatus.Geweigerd, "rol_niet_viewer", nu);
            }

            if (rolAanDeBeurt)
            {
                _server = await LeesAsync(MediaGuardWitteLijst.MediaserverStatus, annulering).ConfigureAwait(false);
            }

            var app = await LeesAsync(MediaGuardWitteLijst.AppStatus, annulering).ConfigureAwait(false);
            if (app is null)
            {
                return MgBeeld.Zonder(MgStatus.Onbereikbaar, "app_status_mislukt", nu);
            }

            var lanes = new List<MgLane>();
            foreach (var lane in app["encoder"]?["lanes"] as JsonArray ?? [])
            {
                if (Tekst(lane?["lane"]) is string naam)
                {
                    lanes.Add(new MgLane(naam, Getal(lane?["running"]), Getal(lane?["slots"]), WaarOnwaar(lane?["paused"])));
                }
            }

            return new MgBeeld(
                MgStatus.Ok,
                "gemeten",
                nu,
                WaarOnwaar(app["encoder"]?["reachable"]),
                lanes,
                WaarOnwaar(_server?["hold"]?["active"]),
                WaarOnwaar(_server?["connected"]),
                Tekst(_server?["kind"]));
        }
        catch (OperationCanceledException) when (annulering.IsCancellationRequested)
        {
            throw;
        }
#pragma warning disable CA1031 // De poller mag de server nooit laten stoppen; elke fout wordt "onbereikbaar".
        catch (Exception)
#pragma warning restore CA1031
        {
            return MgBeeld.Zonder(MgStatus.Onbereikbaar, "vervoer_fout", nu);
        }
    }

    /// <summary>Vraagt één route op en geeft alleen de velden van de witte lijst terug; <c>null</c> bij elk onbruikbaar antwoord.</summary>
    private async Task<JsonObject?> LeesAsync(MgRoute route, CancellationToken annulering)
    {
        if (!MediaGuardWitteLijst.Bevat(route) || !route.Bruikbaar)
        {
            throw new InvalidOperationException("Deze MediaGuard-route staat niet op de witte lijst: " + route.Id);
        }

        _aanroepen.AddOrUpdate(route.Id, 1, (_, n) => n + 1);
        var antwoord = await _vervoer.VraagAsync(route, annulering).ConfigureAwait(false);
        if (antwoord.Status != 200 || antwoord.Body.Length == 0 || antwoord.Body.Length > Fouten.MaxBodyBytes)
        {
            return null;
        }

        try
        {
            return MediaGuardWitteLijst.Filter(JsonNode.Parse(antwoord.Body.Span), route.Velden);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static string? Tekst(JsonNode? node) =>
        node is JsonValue v && v.GetValueKind() == JsonValueKind.String ? v.GetValue<string>() : null;

    private static bool? WaarOnwaar(JsonNode? node) => node is JsonValue v
        ? v.GetValueKind() switch { JsonValueKind.True => true, JsonValueKind.False => false, _ => null }
        : null;

    private static int? Getal(JsonNode? node) =>
        node is JsonValue v && v.GetValueKind() == JsonValueKind.Number && v.TryGetValue<int>(out var getal) ? getal : null;
}

/// <summary>
/// Health-check <c>mediaguard</c> (contract 1.3 §6): alleen woorden uit een vaste lijst, nooit inhoud van MediaGuard.
/// Zolang geen actieve module batchwerk heeft is "onbekend" geen probleem; anders is het eerlijk <c>unknown</c>.
/// </summary>
internal sealed class MediaGuardHealthBron : IHealthBron
{
    private readonly MediaGuardClient _client;
    private readonly ModuleRegistry _modules;

    public MediaGuardHealthBron(MediaGuardClient client, ModuleRegistry modules)
    {
        _client = client;
        _modules = modules;
    }

    public IEnumerable<JsonObject> Checks(DateTimeOffset nu)
    {
        var beeld = _client.Beeld;
        var nodig = _modules.Actief.Any(m => m.JobTypes.Count > 0);
        var status = beeld.Status switch
        {
            MgStatus.Ok => "healthy",
            MgStatus.Geweigerd => "degraded",
            _ => nodig ? "unknown" : "healthy",
        };
#pragma warning disable CA1308 // De koppelwoorden zijn kleine letters in het contract.
        var detail = new JsonObject { ["nodig"] = nodig, ["koppeling"] = beeld.Status.ToString().ToLowerInvariant(), ["reden"] = beeld.Reden };
#pragma warning restore CA1308

        // Zonder weg naar MediaGuard is de vaststelling "geen route" van nu; met een weg telt de leeftijd van de meting.
        var gemeten = _client.HeeftVervoer ? beeld.GemetenOp ?? DateTimeOffset.MinValue.AddYears(2000) : nu;
        yield return ConnectorService.Check("mediaguard", status, gemeten, detail);
    }
}
