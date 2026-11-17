using System.Globalization;
using MediaBrowser.Model.Session;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// Nep-actie voor <see cref="HostOptiesDraaienTests"/>: de route en de handtekening van
/// <c>PlaystateController.ReportPlaybackStopped</c>; geeft het ontvangen <c>PositionTicks</c> als tekst terug.
/// </summary>
[ApiController]
public sealed class NepPlaystateController : ControllerBase
{
    [HttpPost("Sessions/Playing/Stopped")]
    public ActionResult ReportPlaybackStopped([FromBody] PlaybackStopInfo playbackStopInfo) =>
        Content(playbackStopInfo.PositionTicks?.ToString(CultureInfo.InvariantCulture) ?? "leeg", "text/plain");
}
