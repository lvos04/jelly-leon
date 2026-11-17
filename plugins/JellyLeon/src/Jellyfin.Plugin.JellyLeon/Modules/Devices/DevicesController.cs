using System;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.JellyLeon.Modules.Devices;

/// <summary>Routes van module Devices. Staat de module uit, dan geeft elke route 404.</summary>
[Route("media/v1/devices")]
public sealed class DevicesController : ControllerBase
{
    private readonly IServiceProvider _diensten;

    private DevicesModule Module => (DevicesModule)_diensten.GetService(typeof(DevicesModule))!;
    private TimeProvider Klok => (TimeProvider)_diensten.GetService(typeof(TimeProvider))!;

    /// <summary>Initializes a new instance of the <see cref="DevicesController"/> class.</summary>
    /// <param name="services">De dienstverlener van de server.</param>
    public DevicesController(IServiceProvider services)
    {
        _diensten = services;
    }

    /// <summary>Status van de module (alleen aantallen).</summary>
    /// <returns>De status.</returns>
    [HttpGet("status")]
    [JlRoute("devices.status")]
    public IActionResult Status() => ModuleRoutes.Status(Module, Klok.GetUtcNow());

    /// <summary>De instellingen van de module, met ETag.</summary>
    /// <returns>De instellingen.</returns>
    [HttpGet("settings")]
    [JlRoute("devices.settings.get")]
    public IActionResult Instellingen() => ModuleRoutes.LeesInstellingen(Module);

    /// <summary>Wijzigt de instellingen (If-Match en Idempotency-Key verplicht).</summary>
    /// <returns>De nieuwe instellingen.</returns>
    [HttpPut("settings")]
    [JlRoute("devices.settings.put")]
    public IActionResult InstellingenZet() => ModuleRoutes.SchrijfInstellingen(Module, JlContext.Van(HttpContext));
}
