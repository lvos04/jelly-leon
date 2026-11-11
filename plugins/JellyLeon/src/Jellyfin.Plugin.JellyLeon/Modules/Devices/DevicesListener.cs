using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Session;
using MediaBrowser.Model.Session;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Modules.Devices;

/// <summary>
/// Luistert naar de officiële sessiegebeurtenissen van de server (alleen lezen). Staat de module uit, dan gebeurt
/// er niets. Een fout hier mag het afspelen nooit raken en wordt daarom alleen gelogd.
/// </summary>
internal sealed class DevicesListener : IHostedService
{
    private readonly ISessionManager _sessies;
    private readonly DevicesModule _module;
    private readonly IModuleSwitches _schakelaars;
    private readonly TimeProvider _klok;
    private readonly ILogger<DevicesListener> _log;

    public DevicesListener(ISessionManager sessies, DevicesModule module, IModuleSwitches schakelaars, TimeProvider klok, ILogger<DevicesListener> log)
    {
        _sessies = sessies;
        _module = module;
        _schakelaars = schakelaars;
        _klok = klok;
        _log = log;
    }

    public static string Methode(PlayMethod? methode) => methode switch
    {
        PlayMethod.Transcode => "transcode",
        PlayMethod.DirectStream => "direct_stream",
        _ => "direct_play",
    };

    public Task StartAsync(CancellationToken cancellationToken)
    {
        _sessies.PlaybackStart += BijStart;
        _sessies.PlaybackStopped += BijStop;
        return Task.CompletedTask;
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        _sessies.PlaybackStart -= BijStart;
        _sessies.PlaybackStopped -= BijStop;
        return Task.CompletedTask;
    }

    private void BijStart(object? sender, PlaybackProgressEventArgs e)
    {
        if (!_schakelaars.IsAan(DevicesModule.ModuleSlug) || e.Users is null || e.Users.Count == 0)
        {
            return;
        }

        try
        {
            var transcode = e.Session?.TranscodingInfo;
            var hardware = transcode is { IsVideoDirect: false, HardwareAccelerationType: not null }
                && !string.Equals(transcode.HardwareAccelerationType.ToString(), "none", StringComparison.OrdinalIgnoreCase);
            _module.RegistreerStart(e.Users.Select(u => u.Id), e.DeviceId ?? "onbekend", Sessie(e), Methode(e.Session?.PlayState?.PlayMethod), hardware, _klok.GetUtcNow());
        }
        catch (JlException fout)
        {
            _log.LogWarning("Jelly Leon Devices: sessiestart niet vastgelegd ({Code}).", fout.Code);
        }
    }

    private void BijStop(object? sender, PlaybackStopEventArgs e)
    {
        if (!_schakelaars.IsAan(DevicesModule.ModuleSlug))
        {
            return;
        }

        try
        {
            _module.RegistreerStop(Sessie(e), _klok.GetUtcNow());
        }
        catch (JlException fout)
        {
            _log.LogWarning("Jelly Leon Devices: sessie-einde niet vastgelegd ({Code}).", fout.Code);
        }
    }

    private static string Sessie(PlaybackProgressEventArgs e) =>
        !string.IsNullOrEmpty(e.PlaySessionId) ? e.PlaySessionId : (e.Session?.Id ?? "onbekend") + ":" + (e.MediaSourceId ?? string.Empty);
}
