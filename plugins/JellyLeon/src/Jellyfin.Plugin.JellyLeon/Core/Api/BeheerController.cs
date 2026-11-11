using System;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Core.Api;

/// <summary>
/// Beheerroutes van Core voor een beheerder met een serversessie: de Hub-koppeling (JL4), de moduleschakelaars en het
/// register van persoonsgegevens.
/// </summary>
[Route("media/v1")]
public sealed class BeheerController : ControllerBase
{
    private readonly HubPin _pin;
    private readonly ModuleRegistry _modules;
    private readonly IModuleSwitches _schakelaars;
    private readonly PrivacyService _privacy;
    private readonly TimeProvider _klok;
    private readonly ILogger<BeheerController> _log;

    /// <summary>Initializes a new instance of the <see cref="BeheerController"/> class.</summary>
    /// <param name="services">De dienstverlener van de server.</param>
    /// <param name="log">Het logboek.</param>
    public BeheerController(IServiceProvider services, ILogger<BeheerController> log)
    {
        _pin = (HubPin)services.GetService(typeof(HubPin))!;
        _modules = (ModuleRegistry)services.GetService(typeof(ModuleRegistry))!;
        _schakelaars = (IModuleSwitches)services.GetService(typeof(IModuleSwitches))!;
        _privacy = (PrivacyService)services.GetService(typeof(PrivacyService))!;
        _klok = (TimeProvider)services.GetService(typeof(TimeProvider))!;
        _log = log;
    }

    /// <summary>Status van de Hub-koppeling.</summary>
    /// <returns>De status en de vingerafdruk van de gepinde sleutelset.</returns>
    [HttpGet("hub-link")]
    [JlRoute("hublink.get")]
    public IActionResult HubLink() => JlResult.Ok(HubLinkJson());

    /// <summary>Berekent de vingerafdruk van een geplakte sleutelset zonder iets te wijzigen.</summary>
    /// <returns>De vingerafdruk om met de Hub te vergelijken.</returns>
    [HttpPost("hub-link/verify")]
    [JlRoute("hublink.verify")]
    public IActionResult HubLinkVerify()
    {
        var lezer = new BodyLezer(JlContext.Van(HttpContext).Body);
        var keyset = lezer.Node("keyset", true);
        lezer.Klaar();
        var sleutels = HubKeySet.Parse(keyset, "keyset");
        return JlResult.Ok(new JsonObject
        {
            ["fingerprint"] = sleutels.Vingerafdruk,
            ["jwt_sleutels"] = sleutels.JwtSleutels.Count,
            ["policy_sleutels"] = sleutels.PolicySleutels.Count,
        });
    }

    /// <summary>Pint de sleutelset van de Hub nadat de beheerder de vingerafdruk heeft overgetikt.</summary>
    /// <returns>De nieuwe status van de koppeling.</returns>
    [HttpPut("hub-link")]
    [JlRoute("hublink.put")]
    public IActionResult HubLinkZet()
    {
        var lezer = new BodyLezer(JlContext.Van(HttpContext).Body);
        var keyset = lezer.Node("keyset", true);
        var getypt = lezer.Tekst("fingerprint", true, 64);
        var serviceId = lezer.Tekst("service_id", true, 36);
        if (serviceId is not null && !Guid.TryParseExact(serviceId, "D", out _))
        {
            lezer.Fout("service_id", "uuid", "Verwacht de service_id (UUID) uit de Hub.");
        }

        lezer.Klaar();
        var sleutels = HubKeySet.Parse(keyset, "keyset");
        if (!sleutels.VingerafdrukKlopt(getypt!))
        {
            throw Fouten.Validatie(("fingerprint", "vingerafdruk_klopt_niet", "De overgetikte vingerafdruk hoort niet bij deze sleutelset."));
        }

        _pin.Zet(sleutels, serviceId!.ToLowerInvariant(), _klok.GetUtcNow());
        _log.LogInformation("Jelly Leon: Hub-sleutelset gepind ({Aantal} JWT-sleutels).", sleutels.JwtSleutels.Count);
        return JlResult.Ok(HubLinkJson());
    }

    /// <summary>Verwijdert de pin; daarna weigert elke Hub-route met not_linked.</summary>
    /// <returns>De nieuwe status van de koppeling.</returns>
    [HttpDelete("hub-link")]
    [JlRoute("hublink.delete")]
    public IActionResult HubLinkWis()
    {
        _pin.Wis();
        _log.LogInformation("Jelly Leon: Hub-koppeling verwijderd.");
        return JlResult.Ok(HubLinkJson());
    }

    /// <summary>De modules met hun schakelaar.</summary>
    /// <returns>De lijst van modules.</returns>
    [HttpGet("modules")]
    [JlRoute("modules.list")]
    public IActionResult Modules() => JlResult.Ok(ModulesJson(), _schakelaars.Etag);

    /// <summary>Zet één module aan of uit.</summary>
    /// <param name="slug">De korte naam van de module.</param>
    /// <returns>De lijst van modules na de wijziging.</returns>
    [HttpPut("modules/{slug}")]
    [JlRoute("modules.put")]
    public IActionResult ModuleZet([FromRoute] string slug)
    {
        var context = JlContext.Van(HttpContext);
        var lezer = new BodyLezer(context.Body);
        var aan = lezer.Bool("enabled", true);
        lezer.Klaar();
        if (_modules.Zoek(slug) is null)
        {
            throw Fouten.NietGevonden();
        }

        if (!string.Equals(context.IfMatch, _schakelaars.Etag, StringComparison.Ordinal))
        {
            throw Fouten.PreconditieMislukt(_schakelaars.Etag);
        }

        _schakelaars.Zet(slug, aan!.Value);
        return JlResult.Ok(ModulesJson(), _schakelaars.Etag);
    }

    /// <summary>Het register van persoonsgegevens per module.</summary>
    /// <returns>De regels van het register.</returns>
    [HttpGet("privacy/register")]
    [JlRoute("privacy.register")]
    public IActionResult PrivacyRegister()
    {
        var regels = _privacy.Register().Select(r => (JsonNode)new JsonObject
        {
            ["module"] = r.Module,
            ["tabel"] = r.Tabel,
            ["gegeven"] = r.Gegeven,
            ["doel"] = r.Doel,
            ["bewaartermijn"] = r.Bewaartermijn,
        }).ToArray();
        return JlResult.Ok(new JsonObject { ["items"] = new JsonArray(regels) });
    }

    private JsonObject HubLinkJson()
    {
        var pin = _pin.Huidig;
        return new JsonObject
        {
            ["status"] = pin is null ? "not_linked" : "linked",
            ["fingerprint"] = pin?.Sleutels.Vingerafdruk,
            ["service_id"] = pin?.ServiceId,
            ["gepind_op"] = pin?.GepindOp,
            ["jwt_sleutels"] = pin?.Sleutels.JwtSleutels.Count ?? 0,
            ["policy_sleutels"] = pin?.Sleutels.PolicySleutels.Count ?? 0,
            ["audience"] = HubTokenValidator.Audience,
        };
    }

    private JsonObject ModulesJson() => new()
    {
        ["items"] = new JsonArray(_modules.Alle.Select(m => (JsonNode)new JsonObject
        {
            ["slug"] = m.Slug,
            ["naam"] = m.Naam,
            ["enabled"] = _schakelaars.IsAan(m.Slug),
            ["item_types"] = new JsonArray(m.ItemTypes.Select(t => (JsonNode)t).ToArray()),
            ["event_types"] = new JsonArray(m.EventTypes.Select(t => (JsonNode)t).ToArray()),
            ["job_types"] = new JsonArray(m.JobTypes.Select(t => (JsonNode)t).ToArray()),
        }).ToArray()),
    };
}
