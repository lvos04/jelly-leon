using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Jellyfin.Plugin.JellyLeon.Core;

/// <summary>Maakt een achtergrondtaak uitsluitend aan bij veilige opslag; uit betekent ook geen timers of abonnementen.</summary>
internal sealed class OpslagDienst<T> : IHostedService
    where T : class, IHostedService
{
    private readonly T? _dienst;

    public OpslagDienst(PluginOpslag opslag, IServiceProvider diensten)
    {
        _dienst = opslag.Beschikbaar ? diensten.GetRequiredService<T>() : null;
    }

    public Task StartAsync(CancellationToken cancellationToken) => _dienst?.StartAsync(cancellationToken) ?? Task.CompletedTask;

    public Task StopAsync(CancellationToken cancellationToken) => _dienst?.StopAsync(cancellationToken) ?? Task.CompletedTask;
}
