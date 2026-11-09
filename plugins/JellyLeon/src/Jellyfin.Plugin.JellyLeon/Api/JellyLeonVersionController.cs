using System;
using System.Net.Mime;
using MediaBrowser.Controller;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.JellyLeon.Api;

/// <summary>
/// Versie- en compatibiliteitsinformatie van de fork voor de Hub-pagina "Versie en clientcompatibiliteit" (B03-001).
/// Vereist een geldige Jellyfin-sessie of API-sleutel (geen anonieme toegang).
/// </summary>
[ApiController]
[Authorize]
[Route("media/v1")]
[Produces(MediaTypeNames.Application.Json)]
public class JellyLeonVersionController : ControllerBase
{
    private readonly IServerApplicationHost _host;
    private readonly TimeProvider _timeProvider;

    /// <summary>
    /// Initializes a new instance of the <see cref="JellyLeonVersionController"/> class.
    /// </summary>
    /// <param name="host">De servertoepassing (levert de technische versie en productnaam).</param>
    public JellyLeonVersionController(IServerApplicationHost host)
        : this(host, TimeProvider.System)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="JellyLeonVersionController"/> class (testbaar).
    /// </summary>
    /// <param name="host">De servertoepassing.</param>
    /// <param name="timeProvider">Klok.</param>
    internal JellyLeonVersionController(IServerApplicationHost host, TimeProvider timeProvider)
    {
        _host = host;
        _timeProvider = timeProvider;
    }

    /// <summary>
    /// Geeft forkversie, upstream-basis en of deze plugin bij de draaiende server past.
    /// </summary>
    /// <response code="200">Versie-informatie (ook bij status <c>afwijkend</c> of <c>unknown</c>).</response>
    /// <response code="401">Niet aangemeld.</response>
    /// <returns>De versie-informatie.</returns>
    [HttpGet("version")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public ActionResult<ForkVersionInfo> GetVersion()
    {
        var info = ForkInfo.Build(
            _host.ApplicationVersionString,
            _host.Name,
            ForkInfo.GetMetadata("JellyLeon.JellyfinVersion"),
            ForkInfo.GetMetadata("JellyLeon.ForkVersion"),
            ForkInfo.GetMetadata("JellyLeon.UpstreamTag"),
            ForkInfo.GetMetadata("JellyLeon.UpstreamCommit"),
            typeof(Plugin).Assembly.GetName().Version?.ToString() ?? "unknown",
            _timeProvider.GetUtcNow());
        return Ok(info);
    }
}
