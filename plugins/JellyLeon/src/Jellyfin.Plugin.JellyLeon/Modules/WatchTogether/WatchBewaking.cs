using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Outbox;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Session;
using MediaBrowser.Controller.SyncPlay;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Modules.WatchTogether;

internal sealed class WatchBewaking(Func<ISyncPlayManager?> manager, ISessionManager sessies, IServiceProvider diensten,
    IModuleSwitches schakelaars, WatchTogetherModule module, Outbox outbox, TimeProvider klok,
    ILogger<WatchBewaking> log) : BackgroundService, IHealthBron
{
    private readonly Lock _slot = new();
    private string? _vorigeStatus;

    public (bool Actief, string Status) Meet()
    {
        var actief = manager() is WatchDecorator;
        lock (_slot)
        {
            var status = "healthy";
            if (!actief)
            {
                try
                {
                    status = schakelaars.HeeftGasten || diensten.GetRequiredService<IUserManager>().GetUsers().Any(u => diensten.GetRequiredService<KidPolicy>().IsKid(u)) ? "down" : "degraded";
                }
                catch (JlException)
                {
                    status = "down";
                }

                if (_vorigeStatus != status)
                {
                    outbox.Meld(module.Slug, "media.watchgroup.degraded", "module", module.Slug,
                        new JsonObject { ["reason"] = "decorator_inactive" });
                }
            }

            _vorigeStatus = status;
            return (actief, status);
        }
    }

    public IEnumerable<JsonObject> Checks(DateTimeOffset nu)
    {
        if (schakelaars.IsAan(module.Slug))
        {
            var (actief, status) = Meet();
            yield return ConnectorService.Check("watch_together", status, nu, new JsonObject { ["decorator_active"] = actief });
        }
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var decorator = manager() as WatchDecorator; // Laat upstream zich als eerste op SessionEnded abonneren.
        void SessieEinde(object? sender, SessionEventArgs args) => decorator?.ControleerSessies(args.SessionInfo);

        sessies.SessionEnded += SessieEinde;
        try
        {
            using var timer = new PeriodicTimer(TimeSpan.FromSeconds(30), klok);
            do
            {
                try
                {
                    module.Start(klok.GetUtcNow());
                    decorator?.ControleerSessies(null);
                    if (schakelaars.IsAan(module.Slug))
                    {
                        Meet();
                    }
                }
                catch (JlException)
                {
                    log.LogWarning("Watch Together kon de eigen opslag niet controleren.");
                }
            }
            while (await timer.WaitForNextTickAsync(stoppingToken).ConfigureAwait(false));
        }
        finally
        {
            sessies.SessionEnded -= SessieEinde;
        }
    }
}
