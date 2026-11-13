using System;
using System.Linq;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Session;

namespace Jellyfin.Plugin.JellyLeon.Core.Planner;

/// <summary>Aantallen van dit moment; geen namen, titels of apparaten.</summary>
internal sealed record SessieBeeld(int Sessies, int SoftwareTranscodes);

/// <summary>Waar de planner de kijksessies vandaan haalt. Onafhankelijk van elke moduleschakelaar: niet uit te zetten.</summary>
internal interface ISessieBron
{
    /// <summary>Een kijksessie begint (Direct Play, hardware- of software-transcode: regel G6a).</summary>
    event EventHandler? Gestart;

    /// <summary>Een kijksessie eindigt.</summary>
    event EventHandler? Gestopt;

    SessieBeeld Lees();
}

/// <summary>De sessies van de server, alleen gelezen via de officiële sessiemanager.</summary>
internal sealed class ServerSessies : ISessieBron, IDisposable
{
    private readonly ISessionManager _sessies;

    public ServerSessies(ISessionManager sessies)
    {
        _sessies = sessies;
        _sessies.PlaybackStart += BijStart;
        _sessies.PlaybackStopped += BijStop;
    }

    public event EventHandler? Gestart;

    public event EventHandler? Gestopt;

    /// <summary>Software-transcode: video wordt omgezet en er is geen hardwareversnelling bij gemeld.</summary>
    public static bool IsSoftware(bool heeftTranscode, bool videoDirect, string? hardware) =>
        heeftTranscode && !videoDirect && (string.IsNullOrEmpty(hardware) || string.Equals(hardware, "none", StringComparison.OrdinalIgnoreCase));

    public SessieBeeld Lees()
    {
        var actief = _sessies.Sessions.Where(s => s.NowPlayingItem is not null).ToList();
        var software = actief.Count(s => IsSoftware(s.TranscodingInfo is not null, s.TranscodingInfo?.IsVideoDirect ?? true, s.TranscodingInfo?.HardwareAccelerationType?.ToString()));
        return new SessieBeeld(actief.Count, software);
    }

    public void Dispose()
    {
        _sessies.PlaybackStart -= BijStart;
        _sessies.PlaybackStopped -= BijStop;
    }

    private void BijStart(object? sender, PlaybackProgressEventArgs e) => Gestart?.Invoke(this, EventArgs.Empty);

    private void BijStop(object? sender, PlaybackStopEventArgs e) => Gestopt?.Invoke(this, EventArgs.Empty);
}
