using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Hosting;

namespace Jellyfin.Plugin.JellyLeon.Core.MediaGuard;

/// <summary>
/// De ene poller van de viewerclient: bij de start en daarna elke <see cref="MediaGuardClient.PollSeconds"/> seconden
/// één ronde. Zonder weg naar MediaGuard meet hij één keer ("onbekend") en stopt; er loopt dan geen timer.
/// </summary>
internal sealed class MediaGuardPoller : BackgroundService
{
    private readonly MediaGuardClient _client;
    private readonly TimeProvider _klok;

    public MediaGuardPoller(MediaGuardClient client, TimeProvider klok)
    {
        _client = client;
        _klok = klok;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            await _client.VerversAsync(stoppingToken).ConfigureAwait(false);
            if (!_client.HeeftVervoer)
            {
                return;
            }

            using var timer = new PeriodicTimer(TimeSpan.FromSeconds(MediaGuardClient.PollSeconds), _klok);
            while (await timer.WaitForNextTickAsync(stoppingToken).ConfigureAwait(false))
            {
                await _client.VerversAsync(stoppingToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException)
        {
            // De server stopt.
        }
    }
}
