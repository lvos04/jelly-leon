using System;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.JellyLeon.Modules.Quality;

/// <summary>Routes van module Quality. Staat de module uit, dan geeft elke route 404.</summary>
[Route("media/v1/quality")]
public sealed class QualityController : ControllerBase
{
    private readonly IServiceProvider _diensten;

    private QualityModule Module => (QualityModule)_diensten.GetService(typeof(QualityModule))!;
    private TimeProvider Klok => (TimeProvider)_diensten.GetService(typeof(TimeProvider))!;

    /// <summary>Initializes a new instance of the <see cref="QualityController"/> class.</summary>
    /// <param name="services">De dienstverlener van de server.</param>
    public QualityController(IServiceProvider services)
    {
        _diensten = services;
    }

    /// <summary>Status van de module (alleen aantallen).</summary>
    /// <returns>De status.</returns>
    [HttpGet("status")]
    [JlRoute("quality.status")]
    public IActionResult Status() => ModuleRoutes.Status(Module, Klok.GetUtcNow());

    /// <summary>De instellingen van de module, met ETag.</summary>
    /// <returns>De instellingen.</returns>
    [HttpGet("settings")]
    [JlRoute("quality.settings.get")]
    public IActionResult Instellingen() => ModuleRoutes.LeesInstellingen(Module);

    /// <summary>Wijzigt de instellingen (If-Match en Idempotency-Key verplicht).</summary>
    /// <returns>De nieuwe instellingen.</returns>
    [HttpPut("settings")]
    [JlRoute("quality.settings.put")]
    public IActionResult InstellingenZet() => ModuleRoutes.SchrijfInstellingen(Module, JlContext.Van(HttpContext));
}
