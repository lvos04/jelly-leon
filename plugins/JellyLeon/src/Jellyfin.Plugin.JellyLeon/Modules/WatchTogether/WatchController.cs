using System;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Outbox;
using MediaBrowser.Controller.Session;
using MediaBrowser.Controller.SyncPlay;
using MediaBrowser.Controller.SyncPlay.Requests;
using MediaBrowser.Model.SyncPlay;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.DependencyInjection;

namespace Jellyfin.Plugin.JellyLeon.Modules.WatchTogether;

/// <summary>Gebruikersroutes en de beheeractie van WT-1. Alle autorisatie loopt door de routepijplijn.</summary>
[Route("media/v1/watch")]
public sealed class WatchController(IServiceProvider services) : ControllerBase
{
    private SessieIdentiteit Wie => JlContext.Van(HttpContext).Sessie!;
    private ISyncPlayManager Manager => services.GetService<ISyncPlayManager>() ?? throw Fouten.AfhankelijkheidOnbeschikbaar("syncplay");
    private WatchTogetherModule Module => services.GetRequiredService<WatchTogetherModule>();
    private DateTimeOffset Nu => services.GetRequiredService<TimeProvider>().GetUtcNow();

    /// <summary>Geeft de actuele zelftest en de werkelijk beschikbare functies.</summary>
    /// <returns>De mogelijkheden van deze moduleversie.</returns>
    [HttpGet("capabilities")]
    [JlRoute("watch.capabilities")]
    public IActionResult Capabilities()
    {
        var (actief, status) = services.GetRequiredService<WatchBewaking>().Meet();
        return JlResult.Ok(new JsonObject
        {
            ["schema_version"] = "1.0", ["plugin_version"] = ForkInfo.GetMetadata("JellyLeon.ForkVersion"),
            ["jellyfin_version"] = ForkInfo.GetMetadata("JellyLeon.JellyfinVersion"), ["decorator_active"] = actief,
            ["health"] = status, ["observed_at"] = Outbox.Iso(Nu),
            ["features"] = new JsonObject
            {
                ["privacy"] = false, ["invites"] = false, ["laggard_policy"] = "uit", ["follow_mode"] = false,
                ["telemetry"] = false, ["chat"] = false, ["reactions"] = false, ["external"] = "uit",
            },
        });
    }

    /// <summary>Geeft een pagina uit de upstream-lijst voor deze gebruiker.</summary>
    /// <returns>Zichtbare groepen, oplopend op hun vaste ID.</returns>
    [HttpGet("groups")]
    [JlRoute("watch.groups")]
    public IActionResult Groepen()
    {
        var account = Wie.GebruikerId!.Value;
        if (!Wie.MagSyncPlay && !Manager.IsUserActive(account))
        {
            throw Fouten.Verboden("syncplay_access");
        }

        var limiet = 50;
        if (Request.Query.TryGetValue("limit", out var l)
            && (!int.TryParse(l, NumberStyles.None, CultureInfo.InvariantCulture, out limiet) || limiet is < 1 or > 200))
        {
            throw Fouten.Validatie(("limit", "bereik", "Kies een paginagrootte van 1 tot 200."));
        }

        var na = Guid.Empty;
        if (Request.Query.TryGetValue("cursor", out var c) && !Guid.TryParseExact(c, "D", out na))
        {
            throw Fouten.Validatie(("cursor", "formaat", "Gebruik de cursor van de vorige pagina."));
        }

        var sessie = EigenSessie(account);
        var pagina = Manager.ListGroups(sessie, new ListGroupsRequest())
            .Where(g => g.GroupId.CompareTo(na) > 0).OrderBy(g => g.GroupId).Take(limiet + 1).ToList();
        var items = new JsonArray();
        foreach (var groep in pagina.Take(limiet))
        {
            items.Add(new JsonObject
            {
                ["group_id"] = groep.GroupId.ToString(), ["name"] = groep.GroupName, ["state"] = groep.State.ToString(),
                ["visibility"] = "open", ["is_owner"] = Module.IsEigenaar(groep.GroupId, account),
                ["is_member"] = IsLid(groep, sessie, account), ["invited"] = false, ["participants_count"] = groep.Participants.Count,
                ["followers_count"] = 0, ["sync_quality"] = null,
            });
        }

        return JlResult.Ok(new JsonObject { ["items"] = items, ["next_cursor"] = pagina.Count > limiet ? pagina[limiet - 1].GroupId.ToString() : null });
    }

    /// <summary>Toont de deelnemers van een groep aan een lid of volwassen beheerder.</summary>
    /// <param name="id">Groeps-ID.</param>
    /// <returns>Diagnose met uitsluitend bekende gegevens.</returns>
    [HttpGet("groups/{id}/diagnostics")]
    [JlRoute("watch.diagnostics")]
    public IActionResult Diagnose(string id)
    {
        var account = Wie.GebruikerId!.Value;
        var isBeheerder = Wie.IsBeheerder && !Wie.IsKid;
        if (!Guid.TryParse(id, out var groepId)
            || (!isBeheerder && (services.GetService<ISyncPlayManager>() is not WatchDecorator decorator || !decorator.IsLid(groepId, account))))
        {
            throw Fouten.NietGevonden();
        }

        var sessie = EigenSessie(account);
        if (Manager.GetGroup(sessie, groepId) is not { } groep
            || (!isBeheerder && !IsLid(groep, sessie, account)))
        {
            throw Fouten.NietGevonden();
        }

        var deelnemers = new JsonArray();
        foreach (var naam in groep.Participants)
        {
            deelnemers.Add(new JsonObject
            {
                ["display_name"] = naam, ["is_self"] = string.Equals(naam, sessie.UserName, StringComparison.Ordinal),
                ["network"] = "onbekend", ["ping_ms"] = null, ["drift_ms"] = null,
                ["state"] = "onbekend", ["play_method"] = "onbekend", ["lane"] = "onbekend",
            });
        }

        return JlResult.Ok(new JsonObject { ["group_id"] = groepId.ToString(), ["observed_at"] = Outbox.Iso(Nu), ["participants"] = deelnemers });
    }

    /// <summary>Wist alle groepsmetadata, module-events en het WT-geheim vóór verwijderen.</summary>
    /// <returns>Het aantal gewiste rijen.</returns>
    [HttpPost("admin/purge")]
    [JlRoute("watch.purge")]
    public IActionResult Wis()
    {
        var body = new BodyLezer(JlContext.Van(HttpContext).Body);
        if (body.Tekst("confirm", true, 6) != "WISSEN")
        {
            body.Fout("confirm", "bevestiging", "Bevestig met WISSEN.");
        }

        body.Klaar();
        return new JlResult(202, Module.Wis());
    }

    private SessionInfo EigenSessie(Guid account)
    {
        var sessies = services.GetRequiredService<ISessionManager>();
        var bestaande = sessies.Sessions.FirstOrDefault(s => s.UserId == account);
        if (bestaande is not null)
        {
            return bestaande;
        }

        // Een geldig token kan de serverherstart overleven. GetGroup/ListGroups hebben alleen de geauthenticeerde
        // identiteit nodig. Dit lokale object meldt zich niet aan als afspeelsessie en schrijft geen kijkgegevens.
        var lezer = new SessionInfo(sessies, NullLogger.Instance) { UserId = account, UserName = Wie.Gebruikersnaam ?? string.Empty };
        Response.RegisterForDisposeAsync(lezer);
        return lezer;
    }

    private bool IsLid(GroupInfoDto groep, SessionInfo sessie, Guid account) =>
        Manager is WatchDecorator decorator && decorator.IsLid(groep.GroupId, account) && groep.Participants.Contains(sessie.UserName, StringComparer.Ordinal);
}
