using System;
using System.Linq;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Modules.Segments;
using Microsoft.Extensions.DependencyInjection;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Planner;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Core.Api;

/// <summary>
/// Beheerroutes van Core voor een beheerder met een serversessie: de Hub-koppeling (JL4), de moduleschakelaars en het
/// register van persoonsgegevens met de beoordeling van kinderprofielen.
/// </summary>
[Route("media/v1")]
public sealed class BeheerController : ControllerBase
{
    private readonly IServiceProvider _diensten;
    private readonly ILogger<BeheerController> _log;

    private HubPin Pin => (HubPin)_diensten.GetService(typeof(HubPin))!;
    private ModuleRegistry Register => (ModuleRegistry)_diensten.GetService(typeof(ModuleRegistry))!;
    private IModuleSwitches Schakelaars => (IModuleSwitches)_diensten.GetService(typeof(IModuleSwitches))!;
    private PrivacyService Privacy => (PrivacyService)_diensten.GetService(typeof(PrivacyService))!;
    private KidPolicy Kindbeleid => (KidPolicy)_diensten.GetService(typeof(KidPolicy))!;
    private BatchPlanner Batch => (BatchPlanner)_diensten.GetService(typeof(BatchPlanner))!;
    private TimeProvider Klok => (TimeProvider)_diensten.GetService(typeof(TimeProvider))!;

    /// <summary>Initializes a new instance of the <see cref="BeheerController"/> class.</summary>
    /// <param name="services">De dienstverlener van de server.</param>
    /// <param name="log">Het logboek.</param>
    public BeheerController(IServiceProvider services, ILogger<BeheerController> log)
    {
        _diensten = services;
        _log = log;
    }

    /// <summary>Status van de Hub-koppeling.</summary>
    /// <returns>De status en de vingerafdruk van de gepinde sleutelset.</returns>
    [HttpGet("hub-link")]
    [JlRoute("hublink.get")]
    public IActionResult HubLink()
    {
        var (pin, onleesbaar) = Pin.LeesStatus();
        var status = HubLinkJson(pin);
        if (onleesbaar)
        {
            status["reason"] = "koppelstatus_onleesbaar";
        }

        return JlResult.Ok(status);
    }

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

        var pin = Pin.Zet(sleutels, serviceId!.ToLowerInvariant(), Klok.GetUtcNow());
        _log.LogInformation("Jelly Leon: Hub-sleutelset gepind ({Aantal} JWT-sleutels).", sleutels.JwtSleutels.Count);
        return JlResult.Ok(HubLinkJson(pin));
    }

    /// <summary>Verwijdert de pin; daarna weigert elke Hub-route met not_linked.</summary>
    /// <returns>De nieuwe status van de koppeling.</returns>
    [HttpDelete("hub-link")]
    [JlRoute("hublink.delete")]
    public IActionResult HubLinkWis()
    {
        Pin.Wis();
        _log.LogInformation("Jelly Leon: Hub-koppeling verwijderd.");
        return JlResult.Ok(HubLinkJson(null));
    }

    /// <summary>De modules met hun schakelaar.</summary>
    /// <returns>De lijst van modules.</returns>
    [HttpGet("modules")]
    [JlRoute("modules.list")]
    public IActionResult Modules() => JlResult.Ok(ModulesJson(), Schakelaars.Etag);

    /// <summary>Zet één module aan of uit.</summary>
    /// <param name="slug">De korte naam van de module.</param>
    /// <returns>De lijst van modules na de wijziging.</returns>
    [HttpPut("modules/{slug}")]
    [JlRoute("modules.put")]
    public async Task<IActionResult> ModuleZet([FromRoute] string slug)
    {
        var context = JlContext.Van(HttpContext);
        var lezer = new BodyLezer(context.Body);
        var aan = lezer.Bool("enabled", true);
        lezer.Klaar();
        if (Register.Zoek(slug) is null)
        {
            throw Fouten.NietGevonden();
        }

        if (!string.Equals(context.IfMatch, Schakelaars.Etag, StringComparison.Ordinal))
        {
            throw Fouten.PreconditieMislukt(Schakelaars.Etag);
        }

        if (slug == SegmentsModule.ModuleSlug && aan == false)
        {
            await _diensten.GetRequiredService<SegmentDienst>().Uitzetten(HttpContext.RequestAborted).ConfigureAwait(false);
        }
        else
        {
            Schakelaars.Zet(slug, aan!.Value);
            if (slug == SegmentsModule.ModuleSlug)
            {
                _diensten.GetRequiredService<SegmentDienst>().PlanControle();
            }
        }
        return JlResult.Ok(ModulesJson(), Schakelaars.Etag);
    }

    /// <summary>Het register van persoonsgegevens per module.</summary>
    /// <returns>De regels van het register.</returns>
    [HttpGet("privacy/register")]
    [JlRoute("privacy.register")]
    public IActionResult PrivacyRegister()
    {
        var regels = Privacy.Register().Select(r => (JsonNode)new JsonObject
        {
            ["module"] = r.Module,
            ["tabel"] = r.Tabel,
            ["gegeven"] = r.Gegeven,
            ["doel"] = r.Doel,
            ["bewaartermijn"] = r.Bewaartermijn,
        }).ToArray();
        return JlResult.Ok(new JsonObject { ["items"] = new JsonArray(regels) });
    }

    /// <summary>Beoordeelt het gekozen account op de actuele signalen en geeft de vastgelegde profielstatus.</summary>
    /// <param name="id">De account-ID uit het gebruikersbeheer van Jellyfin.</param>
    /// <returns>De profielstatus met de ETag voor de bevestiging.</returns>
    [HttpGet("privacy/kid-profiles/{id}")]
    [JlRoute("privacy.kid.get")]
    public IActionResult KinderprofielLees([FromRoute] string id)
    {
        if (!AccountId(id, out var account))
        {
            throw Fouten.NietGevonden();
        }

        return ProfielAntwoord(Kindbeleid.VoorAccount(account));
    }

    /// <summary>Legt de keuze van de beheerder voor een voorgesteld of eerder bevestigd account vast.</summary>
    /// <returns>De nieuwe profielstatus met ETag.</returns>
    [HttpPost("privacy/kid-profiles/confirm")]
    [JlRoute("privacy.kid.confirm")]
    public IActionResult KinderprofielBevestig()
    {
        var context = JlContext.Van(HttpContext);
        var lezer = new BodyLezer(context.Body);
        var id = lezer.Tekst("user_id", true, 36);
        var kind = lezer.Bool("is_kid", true);
        if (!AccountId(id, out var account))
        {
            lezer.Fout("user_id", "uuid", "Verwacht een geldige account-ID.");
        }

        lezer.Klaar();
        return ProfielAntwoord(Kindbeleid.Bevestig(account, kind!.Value, context.IfMatch!));
    }

    private static bool AccountId(string? id, out Guid account) =>
        (Guid.TryParseExact(id, "D", out account) || Guid.TryParseExact(id, "N", out account)) && account != Guid.Empty;

    private static JlResult ProfielAntwoord(Kinderprofiel profiel) =>
        JlResult.Ok(new JsonObject { ["status"] = profiel.Status, ["is_kid"] = profiel.IsKid }, profiel.Etag);

    /// <summary>De stand van de planner: mag er batchwerk draaien, en zo niet, waarom niet.</summary>
    /// <returns>Aantallen, tijden en vaste woorden; geen titels, namen of paden.</returns>
    [HttpGet("planner")]
    [JlRoute("planner.status")]
    public IActionResult Planner() => JlResult.Ok(Batch.Status());

    private static JsonObject HubLinkJson(HubPinState? pin)
    {
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
        ["items"] = new JsonArray(Register.Alle.Select(m => (JsonNode)new JsonObject
        {
            ["slug"] = m.Slug,
            ["naam"] = m.Naam,
            ["enabled"] = Schakelaars.IsAan(m.Slug),
            ["item_types"] = new JsonArray(m.ItemTypes.Select(t => (JsonNode)t).ToArray()),
            ["event_types"] = new JsonArray(m.EventTypes.Select(t => (JsonNode)t).ToArray()),
            ["job_types"] = new JsonArray(m.JobTypes.Select(t => (JsonNode)t).ToArray()),
        }).ToArray()),
    };
}
