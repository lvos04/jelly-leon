using System;
using System.Linq;
using Jellyfin.Plugin.JellyLeon.Modules.WatchTogether;
using MediaBrowser.Controller.SyncPlay;
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
using Jellyfin.Plugin.JellyLeon.Modules.Recommendations;
using Jellyfin.Plugin.JellyLeon.Modules.Segments;
using MediaBrowser.Controller.MediaSegments;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller;
using MediaBrowser.Controller.Events;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Net;
using MediaBrowser.Controller.Plugins;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;

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
            return new PluginOpslag(paden.DataPath, paden.CachePath, sp.GetRequiredService<ILogger<PluginOpslag>>());
        });
        serviceCollection.AddSingleton(sp => sp.GetRequiredService<PluginOpslag>().Paden);
        serviceCollection.AddSingleton<CoreDatabase>();
        serviceCollection.AddSingleton<SecretStore>();
        serviceCollection.AddSingleton<InternalWriteScope>();
        serviceCollection.AddSingleton<HubPin>();
        serviceCollection.AddSingleton<JtiStore>();
        serviceCollection.AddSingleton<IdempotencyStore>();
        serviceCollection.AddSingleton<Outbox>();
        serviceCollection.AddSingleton<PluginModuleSwitches>();
        serviceCollection.AddSingleton<IModuleSwitches>(sp => sp.GetRequiredService<PluginModuleSwitches>());

        // Modules: elk met een eigen schakelaar, eigen SQLite-bestand en eigen routes.
        serviceCollection.AddSingleton<DevicesModule>();
        serviceCollection.AddSingleton<IJellyLeonModule>(sp => sp.GetRequiredService<DevicesModule>());
        serviceCollection.AddSingleton<QualityModule>();
        serviceCollection.AddSingleton<IJellyLeonModule>(sp => sp.GetRequiredService<QualityModule>());
        serviceCollection.AddSingleton<IJellyLeonModule, RecommendationsModule>();
        serviceCollection.AddSingleton<Func<Configuration.AnimeOptions>>(sp => sp.GetRequiredService<PluginModuleSwitches>().AnimeInstellingen);
        serviceCollection.AddSingleton<AanbevelingsBibliotheek>();
        serviceCollection.TryAddSingleton<LeesSimilarMetadata>(sp => sp.GetRequiredService<AanbevelingsBibliotheek>().Similar);
        serviceCollection.AddSingleton<SegmentsModule>();
        serviceCollection.AddSingleton<IJellyLeonModule>(sp => sp.GetRequiredService<SegmentsModule>());
        serviceCollection.AddSingleton<IMediaSegmentProvider, SegmentProvider>();
        serviceCollection.AddSingleton<SegmentBibliotheek>();
        serviceCollection.AddSingleton<SegmentPublicatie>();
        serviceCollection.AddSingleton<WatchTogetherModule>();
        serviceCollection.AddSingleton<IJellyLeonModule>(sp => sp.GetRequiredService<WatchTogetherModule>());
        RegistreerWatchTogether(serviceCollection);

        serviceCollection.AddSingleton<SegmentDienst>();
        serviceCollection.AddSingleton<IHealthBron, SegmentHealthBron>();
        serviceCollection.AddHostedService<OpslagDienst<SegmentDienst>>();
        serviceCollection.AddSingleton<ModuleRegistry>();

        serviceCollection.AddSingleton<PrivacyService>();
        serviceCollection.AddSingleton<KidPolicy>();
        serviceCollection.AddSingleton<ISessionAuthenticator>(sp => new JellyfinSessionAuthenticator(
            sp.GetRequiredService<IAuthService>(),
            sp.GetRequiredService<PluginOpslag>().Beschikbaar ? sp.GetRequiredService<KidPolicy>() : null));
        serviceCollection.AddSingleton<JlPipeline>();
        serviceCollection.AddSingleton<IMediaMappen, BibliotheekMappen>();
        serviceCollection.AddSingleton<ConnectorService>();
        serviceCollection.AddScoped<IEventConsumer<UserDeletedEventArgs>>(sp => new UserDeletedConsumer(
            sp.GetRequiredService<PluginOpslag>().Beschikbaar ? sp.GetRequiredService<PrivacyService> : null,
            sp.GetRequiredService<ILogger<UserDeletedConsumer>>()));
        serviceCollection.AddSingleton<DevicesListener>();
        serviceCollection.AddHostedService<OpslagDienst<DevicesListener>>();

        // De ene MediaGuard-viewerclient (B03-009, ADR-0034). Standaard is er geen weg naar MediaGuard: status onbekend.
        serviceCollection.TryAddSingleton<IMediaGuardVervoer, GeenMediaGuardVervoer>();
        serviceCollection.AddSingleton<MediaGuardClient>();
        serviceCollection.AddSingleton<IHealthBron, MediaGuardHealthBron>();
        serviceCollection.AddSingleton<MediaGuardPoller>();
        serviceCollection.AddHostedService<OpslagDienst<MediaGuardPoller>>();

        // De ene planner en de ene budgetbeslisser (B03-018, ADR-0035). Zonder werker draait er geen zwaar werk.
        serviceCollection.TryAddSingleton<IWerker, GeenWerker>();
        serviceCollection.AddSingleton<ISessieBron, ServerSessies>();
        serviceCollection.AddSingleton<LeesfoutBreker>();
        serviceCollection.AddSingleton<BudgetBeslisser>();
        serviceCollection.AddSingleton<BatchPlanner>();
        serviceCollection.AddHostedService<OpslagDienst<BatchPlanner>>();

        // Spike (ADR-0033): 1 MiB vóór routing en authenticatie; standaard uit, de controle per route blijft altijd staan.
        if (JlStartupFilterSpike.IsAan(Environment.GetEnvironmentVariable))
        {
            serviceCollection.AddTransient<IStartupFilter, JlStartupFilterSpike>();
        }
    }

    private static void RegistreerWatchTogether(IServiceCollection diensten)
    {
        var registraties = diensten.Where(d => !d.IsKeyedService && d.ServiceType == typeof(ISyncPlayManager)).ToArray();
        if (registraties is [var origineel] && origineel.Lifetime == ServiceLifetime.Singleton
            && origineel.ImplementationType is { FullName: "Emby.Server.Implementations.SyncPlay.SyncPlayManager" } type)
        {
            // DI houdt de oorspronkelijke singleton en zijn Dispose in eigendom. Geen tweede SyncPlayManager.
            diensten.Remove(origineel);
            diensten.AddKeyedSingleton(typeof(ISyncPlayManager), typeof(WatchDecorator), type);
            diensten.AddSingleton<Func<WatchTogetherModule>>(sp => sp.GetRequiredService<WatchTogetherModule>);
            diensten.AddSingleton<ISyncPlayManager>(sp => new WatchDecorator(
                sp.GetRequiredKeyedService<ISyncPlayManager>(typeof(WatchDecorator)),
                sp.GetRequiredService<MediaBrowser.Controller.Session.ISessionManager>(), sp.GetRequiredService<IModuleSwitches>(),
                sp.GetRequiredService<Func<WatchTogetherModule>>(), sp.GetRequiredService<TimeProvider>(), sp.GetRequiredService<ILogger<WatchDecorator>>()));
        }

        diensten.AddSingleton<Func<ISyncPlayManager?>>(sp => sp.GetService<ISyncPlayManager>);
        diensten.AddSingleton<WatchBewaking>();
        diensten.AddSingleton<IHealthBron>(sp => sp.GetRequiredService<WatchBewaking>());
        diensten.AddHostedService<OpslagDienst<WatchBewaking>>();
    }
}
