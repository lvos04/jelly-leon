using System;
using Jellyfin.Data.Events.Users;
using Jellyfin.Plugin.JellyLeon.Core;
using Jellyfin.Plugin.JellyLeon.Core.Budget;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Core.Idempotency;
using Jellyfin.Plugin.JellyLeon.Core.MediaGuard;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Outbox;
using Jellyfin.Plugin.JellyLeon.Core.Planner;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Core.Werker;
using Jellyfin.Plugin.JellyLeon.Modules.Devices;
using Jellyfin.Plugin.JellyLeon.Modules.Quality;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller;
using MediaBrowser.Controller.Events;
using MediaBrowser.Controller.Plugins;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace Jellyfin.Plugin.JellyLeon;

/// <summary>
/// Registreert Core en de modules van de ene Jelly Leon-plugin (ADR-0016). Core bestaat één keer; elke module krijgt
/// dezelfde Core-diensten, zodat er geen gedeelde dienst is die per module verschilt.
/// </summary>
public sealed class PluginServiceRegistrator : IPluginServiceRegistrator
{
    /// <inheritdoc />
    public void RegisterServices(IServiceCollection serviceCollection, IServerApplicationHost applicationHost)
    {
        serviceCollection.TryAddSingleton(TimeProvider.System);
        serviceCollection.AddSingleton(sp =>
        {
            var paden = sp.GetRequiredService<IApplicationPaths>();
            return new JlPaths(paden.DataPath, paden.CachePath);
        });
        serviceCollection.AddSingleton<CoreDatabase>();
        serviceCollection.AddSingleton<SecretStore>();
        serviceCollection.AddSingleton<InternalWriteScope>();
        serviceCollection.AddSingleton<HubPin>();
        serviceCollection.AddSingleton<JtiStore>();
        serviceCollection.AddSingleton<IdempotencyStore>();
        serviceCollection.AddSingleton<Outbox>();
        serviceCollection.AddSingleton<IModuleSwitches, PluginModuleSwitches>();

        // Modules: elk met een eigen schakelaar, eigen SQLite-bestand en eigen routes.
        serviceCollection.AddSingleton<DevicesModule>();
        serviceCollection.AddSingleton<IJellyLeonModule>(sp => sp.GetRequiredService<DevicesModule>());
        serviceCollection.AddSingleton<QualityModule>();
        serviceCollection.AddSingleton<IJellyLeonModule>(sp => sp.GetRequiredService<QualityModule>());
        serviceCollection.AddSingleton<ModuleRegistry>();

        serviceCollection.AddSingleton<PrivacyService>();
        serviceCollection.AddSingleton<ISessionAuthenticator, JellyfinSessionAuthenticator>();
        serviceCollection.AddSingleton<JlPipeline>();
        serviceCollection.AddSingleton<IMediaMappen, BibliotheekMappen>();
        serviceCollection.AddSingleton<ConnectorService>();
        serviceCollection.AddScoped<IEventConsumer<UserDeletedEventArgs>, UserDeletedConsumer>();
        serviceCollection.AddHostedService<DevicesListener>();

        // De ene MediaGuard-viewerclient (B03-009, ADR-0034). Standaard is er geen weg naar MediaGuard: status onbekend.
        serviceCollection.TryAddSingleton<IMediaGuardVervoer, GeenMediaGuardVervoer>();
        serviceCollection.AddSingleton<MediaGuardClient>();
        serviceCollection.AddSingleton<IHealthBron, MediaGuardHealthBron>();
        serviceCollection.AddHostedService<MediaGuardPoller>();

        // De ene planner en de ene budgetbeslisser (B03-018, ADR-0035). Zonder werker draait er geen zwaar werk.
        serviceCollection.TryAddSingleton<IWerker, GeenWerker>();
        serviceCollection.AddSingleton<ISessieBron, ServerSessies>();
        serviceCollection.AddSingleton<LeesfoutBreker>();
        serviceCollection.AddSingleton<BudgetBeslisser>();
        serviceCollection.AddSingleton<BatchPlanner>();
        serviceCollection.AddHostedService(sp => sp.GetRequiredService<BatchPlanner>());

        // Spike (ADR-0033): 1 MiB vóór routing en authenticatie; standaard uit, de controle per route blijft altijd staan.
        if (JlStartupFilterSpike.IsAan(Environment.GetEnvironmentVariable))
        {
            serviceCollection.AddTransient<IStartupFilter, JlStartupFilterSpike>();
        }
    }
}
