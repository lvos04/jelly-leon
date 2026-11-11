using System;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.JellyLeon.Core.Connector;

/// <summary>
/// De ene connector van Jelly Leon voor de Hub (contract 1.3 §6). Alleen lezen; propose, apply en rollback geven 501.
/// Authenticatie loopt via de gepinde sleutelset van de Hub, niet via een serversessie.
/// </summary>
[Route("connector/v1")]
public sealed class ConnectorController : ControllerBase
{
    private readonly ConnectorService _connector;
    private readonly TimeProvider _klok;

    /// <summary>Initializes a new instance of the <see cref="ConnectorController"/> class.</summary>
    /// <param name="services">De dienstverlener van de server.</param>
    public ConnectorController(IServiceProvider services)
    {
        _connector = (ConnectorService)services.GetService(typeof(ConnectorService))!;
        _klok = (TimeProvider)services.GetService(typeof(TimeProvider))!;
    }

    /// <summary>Wat Jelly Leon aanbiedt.</summary>
    /// <returns>Het discover-antwoord.</returns>
    [HttpGet("discover")]
    [JlRoute("connector.discover")]
    public IActionResult Discover() => JlResult.Ok(_connector.Discover(_klok.GetUtcNow()));

    /// <summary>Gezondheid; het totaal is de slechtste check.</summary>
    /// <returns>Het health-antwoord.</returns>
    [HttpGet("health")]
    [JlRoute("connector.health")]
    public IActionResult Health() => JlResult.Ok(_connector.Health(_klok.GetUtcNow()));

    /// <summary>Items van één type.</summary>
    /// <returns>Een pagina met items.</returns>
    [HttpGet("items")]
    [JlRoute("connector.items")]
    public IActionResult Items() => JlResult.Ok(_connector.Items(Vraag("type"), Vraag("cursor"), Vraag("limit"), _klok.GetUtcNow()));

    /// <summary>De outbox van Jelly Leon.</summary>
    /// <returns>Een pagina met events.</returns>
    [HttpGet("events")]
    [JlRoute("connector.events")]
    public IActionResult Events() => JlResult.Ok(_connector.Events(Vraag("cursor"), Vraag("limit")));

    /// <summary>Bewijs: nog niet beschikbaar.</summary>
    /// <returns>Altijd 501.</returns>
    [HttpGet("evidence/{id}")]
    [JlRoute("connector.evidence")]
    public IActionResult Evidence() => throw Fouten.NietBeschikbaar("evidence");

    /// <summary>Voorstellen: niet beschikbaar.</summary>
    /// <returns>Altijd 501.</returns>
    [HttpPost("propose")]
    [JlRoute("connector.propose")]
    public IActionResult Propose() => throw Fouten.NietBeschikbaar("propose");

    /// <summary>Toepassen: niet beschikbaar.</summary>
    /// <returns>Altijd 501.</returns>
    [HttpPost("apply")]
    [JlRoute("connector.apply")]
    public IActionResult Apply() => throw Fouten.NietBeschikbaar("apply");

    /// <summary>Terugdraaien: niet beschikbaar.</summary>
    /// <returns>Altijd 501.</returns>
    [HttpPost("rollback")]
    [JlRoute("connector.rollback")]
    public IActionResult Rollback() => throw Fouten.NietBeschikbaar("rollback");

    private string? Vraag(string naam)
    {
        var waarde = Request.Query[naam].ToString();
        return waarde.Length == 0 ? null : waarde;
    }
}
