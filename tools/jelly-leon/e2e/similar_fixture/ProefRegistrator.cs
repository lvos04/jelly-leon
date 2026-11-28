using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Modules.Recommendations;
using MediaBrowser.Controller;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Plugins;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon;

/// <summary>Injecteert uitsluitend bij de proefbouw een fout of vertraging aan de bibliotheekgrens.</summary>
public sealed class SimilarProefRegistrator : IPluginServiceRegistrator
{
    /// <inheritdoc />
    public void RegisterServices(IServiceCollection serviceCollection, IServerApplicationHost applicationHost)
    {
        serviceCollection.Replace(ServiceDescriptor.Singleton<LeesSimilarMetadata>(sp =>
        {
            var bibliotheek = sp.GetRequiredService<ILibraryManager>();
            var log = sp.GetRequiredService<ILogger<SimilarProefRegistrator>>();
            return query =>
            {
                log.LogInformation("F2-PROEF aanroep");
                if (query.Genres.Contains("Proeffout"))
                {
                    log.LogInformation("F2-PROEF uitzondering");
                    throw new InvalidOperationException();
                }

                if (query.Genres.Contains("Proefduur"))
                {
                    log.LogInformation("F2-PROEF vertraging");
                    Thread.Sleep(TimeSpan.FromSeconds(2));
                }

                return bibliotheek.GetItemList(query, false);
            };
        }));
        serviceCollection.AddHostedService<OpslagWaarnemer>();
    }

    private sealed class OpslagWaarnemer(IUserDataManager gegevens, ILogger<OpslagWaarnemer> log) : IHostedService
    {
        public Task StartAsync(CancellationToken cancellationToken)
        {
            gegevens.UserDataSaved += Bewaard;
            return Task.CompletedTask;
        }

        public Task StopAsync(CancellationToken cancellationToken)
        {
            gegevens.UserDataSaved -= Bewaard;
            return Task.CompletedTask;
        }

        private void Bewaard(object? sender, UserDataSaveEventArgs args) => log.LogInformation("F2-PROEF bewaard {Reden}", args.SaveReason);
    }
}
