using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.Versioning;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Data.Events.Users;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Plugin.JellyLeon.Core;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller;
using MediaBrowser.Controller.Events;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Net;
using MediaBrowser.Controller.Session;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Mvc.ApplicationParts;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>Echte host, registratie, achtergrondtaken, MVC en routes; uitsluitend tijdelijke synthetische opslag.</summary>
[SupportedOSPlatform("linux")]
public sealed class OpslagTerugvalTests : IDisposable
{
    private readonly string _map = Directory.CreateTempSubdirectory("jl-terugval-").FullName;
    private readonly NepSessies _auth = new();
    private readonly Mock<ISessionManager> _sessies = new(MockBehavior.Strict);
    private readonly ProefLog _log = new();

    public void Dispose() => Directory.Delete(_map, true);

    [Theory]
    [InlineData("eigenaar")]
    [InlineData("data-groep")]
    [InlineData("data-anderen")]
    [InlineData("cache-groep")]
    [InlineData("cache-anderen")]
    [InlineData("data-koppeling")]
    [InlineData("cache-koppeling")]
    [InlineData("ouder-groep")]
    [InlineData("ouder-anderen")]
    [InlineData("ouder-koppeling")]
    [InlineData("core-koppeling")] // De drie hostproeven van R-TECH-2 (deel 1e) ...
    [InlineData("core-groep")]
    [InlineData("submap-groep")]
    [InlineData("wal-koppeling")] // ... en elk naastbestand van SQLite,
    [InlineData("shm-koppeling")]
    [InlineData("journal-koppeling")]
    [InlineData("wal-groep")]
    [InlineData("modulemap-koppeling")] // een onveilige map dieper in de boom die de start opent,
    [InlineData("modulemap-groep")]
    [InlineData("moduledb-koppeling")]
    [InlineData("core-eigenaar")] // en een bestand van een andere eigenaar.
    public async Task OnveiligeOpslag_HostStartDoorAllePluginroutesDichtEnNietsGeschreven(string geval)
    {
        var (data, cache) = Opzet(geval);
        var voor = Boom(_map);
        var vreemd = geval is "eigenaar" or "core-eigenaar" ? data : null;
        var vreemdVoor = vreemd is null ? null : Boom(vreemd);
        using var host = Host(data, cache);
        var stop = TestContext.Current.CancellationToken;
        await host.StartAsync(stop); // Oude registratie gooit hier: de HELE host startte niet.
        try
        {
            using var client = Client(host);
            Assert.Equal("synthetische kijkgegevens beschikbaar", await client.GetStringAsync("/serverproef", stop));
            await ControleerRoutes(client, stop);
            var schakelaars = host.Services.GetRequiredService<IModuleSwitches>();
            Assert.False(schakelaars.IsAan("devices"));
            Assert.False(schakelaars.IsAan("quality"));
            Assert.Equal("storage_unavailable", Assert.Throws<JlException>(() => schakelaars.Zet("devices", true)).Code);
            foreach (var consumer in host.Services.GetServices<IEventConsumer<UserDeletedEventArgs>>())
            {
                await consumer.OnEvent(new UserDeletedEventArgs(new User("proef", "standaard", "standaard")));
            }

            _sessies.VerifyNoOtherCalls(); // Geen listener of planner aangemaakt; dus geen abonnementen of timers.
            Assert.Single(_log.Regels, r => r.Contains("opslag", StringComparison.OrdinalIgnoreCase));
            Assert.Contains("TrueNAS", _log.Regels.Single(r => r.Contains("opslag", StringComparison.OrdinalIgnoreCase)), StringComparison.Ordinal);
        }
        finally
        {
            await host.StopAsync(stop);
        }

        Assert.Equal(voor, Boom(_map));
        if (vreemdVoor is not null)
        {
            Assert.Equal(vreemdVoor, Boom(vreemd!));
        }
    }

    [Fact]
    public async Task RechtenHerstellen_ZetPluginPasNaHerstartWeerAan()
    {
        var (data, cache) = Opzet("data-groep");
        var stop = TestContext.Current.CancellationToken;
        using (var host = Host(data, cache))
        {
            await host.StartAsync(stop);
            try
            {
                File.SetUnixFileMode(Path.Combine(data, "jelly-leon"), (UnixFileMode)448);
                var voor = Boom(_map);
                using var client = Client(host);
                await ControleerRoutes(client, stop);
                Assert.Equal(voor, Boom(_map));
                Assert.Single(_log.Regels, r => r.Contains("opslag", StringComparison.OrdinalIgnoreCase));
            }
            finally
            {
                await host.StopAsync(stop);
            }
        }

        // Een nieuwe host bepaalt de opslagtoestand opnieuw; alle normale achtergrondtaken mogen weer starten.
        SessiesToegestaan();
        using var herstart = Host(data, cache);
        await herstart.StartAsync(stop);
        try
        {
            using var client = Client(herstart);
            using var antwoord = await client.GetAsync("/media/v1/modules", stop);
            Assert.Equal(HttpStatusCode.OK, antwoord.StatusCode);
            _sessies.VerifyAdd(s => s.PlaybackStart += It.IsAny<EventHandler<PlaybackProgressEventArgs>>(), Times.AtLeastOnce);
        }
        finally
        {
            await herstart.StopAsync(stop);
        }
    }

    [Fact]
    public async Task NaDeStart_OnveiligeOpslagGooitGeenRuweFoutNaarDeServer()
    {
        var stop = TestContext.Current.CancellationToken;
        var data = Maak(Path.Combine(_map, "data"));
        var cache = Maak(Path.Combine(_map, "cache"));
        var eigen = Maak(Path.Combine(data, "jelly-leon"));
        var kijk = Path.Combine(_map, "kijkgegevens.db");
        await File.WriteAllTextAsync(kijk, "synthetische kijkgegevens", stop);
        SessiesToegestaan();
        using var host = Host(data, cache);
        await host.StartAsync(stop);
        try
        {
            Assert.True(host.Services.GetRequiredService<PluginOpslag>().Beschikbaar);
            // Na de start worden een nog niet geopende moduledatabase, het zout van de pseudoniemen en de Hub-pin koppelingen.
            File.CreateSymbolicLink(Path.Combine(Maak(Path.Combine(eigen, "quality")), "quality.db"), kijk);
            var geheimen = Maak(Path.Combine(eigen, "secrets"));
            File.CreateSymbolicLink(Path.Combine(geheimen, "opaque-id.salt"), kijk);
            File.CreateSymbolicLink(Path.Combine(geheimen, "hub-pin.json"), kijk);

            // Zoals EventManager.PublishInternal van de server: eerst alle afhandelaars aanmaken, buiten zijn foutafhandeling;
            // daarna elke OnEvent binnen zijn try/catch. Het aanmaken mag dus niets openen.
            using var scope = host.Services.CreateScope();
            var afhandelaars = scope.ServiceProvider.GetServices<IEventConsumer<UserDeletedEventArgs>>().ToList();
            foreach (var afhandelaar in afhandelaars)
            {
                _ = await Record.ExceptionAsync(() => afhandelaar.OnEvent(new UserDeletedEventArgs(new User("proef", "standaard", "standaard"))));
            }

            // Pseudoniem bij een sessiegebeurtenis van de server (Devices-listener vangt alleen JlException): 503, geen ruwe fout.
            Assert.Equal("storage_unavailable", Assert.Throws<JlException>(() => host.Services.GetRequiredService<SecretStore>().OpaakId("sessie", "proef")).Code);
            // Hub-pin via een koppeling: de route antwoordt met 503 uit de foutcatalogus (JlRouteAttribute), geen ruwe fout.
            Assert.Equal("storage_unavailable", Assert.Throws<JlException>(() => host.Services.GetRequiredService<HubPin>().Huidig).Code);
            var hubRoute = RouteTable.Alle.First(r => r.Auth == JlAuth.Hub);
            using var client = Client(host);
            using var verzoek = new HttpRequestMessage(new HttpMethod(hubRoute.Methode), hubRoute.Pad.Replace("{slug}", "devices", StringComparison.Ordinal).Replace("{id}", "proef", StringComparison.Ordinal));
            using var antwoord = await client.SendAsync(verzoek, stop);
            Assert.Equal(HttpStatusCode.ServiceUnavailable, antwoord.StatusCode);
            Assert.Equal("storage_unavailable", (string?)JsonNode.Parse(await antwoord.Content.ReadAsStringAsync(stop))!["code"]);
        }
        finally
        {
            await host.StopAsync(stop);
        }

        Assert.Equal("synthetische kijkgegevens", await File.ReadAllTextAsync(kijk, stop));
    }

    private void SessiesToegestaan()
    {
        _sessies.SetupAdd(s => s.PlaybackStart += It.IsAny<EventHandler<PlaybackProgressEventArgs>>());
        _sessies.SetupAdd(s => s.PlaybackStopped += It.IsAny<EventHandler<PlaybackStopEventArgs>>());
        _sessies.SetupRemove(s => s.PlaybackStart -= It.IsAny<EventHandler<PlaybackProgressEventArgs>>());
        _sessies.SetupRemove(s => s.PlaybackStopped -= It.IsAny<EventHandler<PlaybackStopEventArgs>>());
        _sessies.SetupGet(s => s.Sessions).Returns([]);
    }

    private (string Data, string Cache) Opzet(string geval)
    {
        var ouder = Maak(Path.Combine(_map, "ouder"));
        var data = Maak(Path.Combine(ouder, "data"));
        var cache = Maak(Path.Combine(ouder, "cache"));
        var eigenData = Maak(Path.Combine(data, "jelly-leon"));
        var eigenCache = Maak(Path.Combine(cache, "jelly-leon"));
        var buiten = Maak(Path.Combine(_map, "buiten"));
        File.WriteAllText(Path.Combine(buiten, "kijkgegevens.db"), "synthetische kijkgegevens");
        File.WriteAllText(Path.Combine(eigenData, "bestaand"), "bestaande plugininhoud");
        // Dit koppelingsdoel mag zelfs nooit als pin gelezen worden; er is geen uitvoerbare sleutel of echt account.
        Maak(Path.Combine(eigenData, "secrets"));
        File.CreateSymbolicLink(Path.Combine(eigenData, "secrets", "hub-pin.json"), Path.Combine(buiten, "kijkgegevens.db"));
        if (OnveiligStartbestand(eigenData, Path.Combine(buiten, "kijkgegevens.db"), geval))
        {
            return (data, cache);
        }

        if (geval == "eigenaar")
        {
            // Gewone tijdelijke map, in de testvoorbereiding door een wegwerpcontainer van een andere UID gemaakt.
            data = Environment.GetEnvironmentVariable("JL_VREEMDE_OPSLAG") ?? throw new InvalidOperationException("JL_VREEMDE_OPSLAG ontbreekt; maak eerst de tijdelijke eigenaarfixture.");
            Assert.True(Directory.Exists(data));
            // Bewaak de echte eigendomsfout: een read-only mount of ontbrekende fixture is geen vervangend bewijs.
            Assert.Contains("niet van de eigen gebruiker", Assert.Throws<UnauthorizedAccessException>(() => new JlPaths(data, cache)).Message, StringComparison.Ordinal);
        }
        else if (geval == "core-eigenaar")
        {
            // Eigen, veilige mappen met daarin core/core.db (0644) van een andere UID, in de testvoorbereiding gemaakt in een
            // wegwerpcontainer zonder netwerk. Alleen het bestand is vreemd; de wortelmappen keurt JlPaths goed.
            data = Environment.GetEnvironmentVariable("JL_VREEMDE_KERN") ?? throw new InvalidOperationException("JL_VREEMDE_KERN ontbreekt; maak eerst de tijdelijke eigenaarfixture.");
            var db = Path.Combine(data, "jelly-leon", "core", "core.db");
            _ = new JlPaths(data, cache);
            Assert.Equal((UnixFileMode)420, File.GetUnixFileMode(db));
            Assert.Throws<UnauthorizedAccessException>(() => File.SetUnixFileMode(db, (UnixFileMode)420));
        }
        else if (geval.EndsWith("koppeling", StringComparison.Ordinal))
        {
            var pad = geval == "data-koppeling" ? eigenData : geval == "cache-koppeling" ? eigenCache : ouder;
            Directory.Move(pad, pad + "-origineel");
            Directory.CreateSymbolicLink(pad, buiten);
        }
        else
        {
            var pad = geval.StartsWith("data-", StringComparison.Ordinal) ? eigenData : geval.StartsWith("cache-", StringComparison.Ordinal) ? eigenCache : ouder;
            File.SetUnixFileMode(pad, (UnixFileMode)448 | (geval.EndsWith("groep", StringComparison.Ordinal) ? UnixFileMode.GroupWrite : UnixFileMode.OtherWrite));
        }

        return (data, cache);
    }

    /// <summary>Deel 1e (R-TECH-2): veilige wortelmappen, maar een onveilig bestand of een onveilige submap die de start opent.</summary>
    private static bool OnveiligStartbestand(string eigenData, string kijk, string geval)
    {
        var kern = Path.Combine(eigenData, "core");
        var db = Path.Combine(kern, "core.db");
        switch (geval)
        {
            case "core-koppeling":
                File.CreateSymbolicLink(Path.Combine(Maak(kern), "core.db"), kijk);
                return true;
            case "core-groep":
                Bestand(Path.Combine(Maak(kern), "core.db"), (UnixFileMode)432);
                return true;
            case "submap-groep":
                File.SetUnixFileMode(Maak(kern), (UnixFileMode)504);
                return true;
            case "wal-koppeling" or "shm-koppeling" or "journal-koppeling":
                Bestand(Path.Combine(Maak(kern), "core.db"), (UnixFileMode)384);
                File.CreateSymbolicLink(db + "-" + geval.Split('-')[0], kijk);
                return true;
            case "wal-groep":
                Bestand(Path.Combine(Maak(kern), "core.db"), (UnixFileMode)384);
                Bestand(db + "-wal", (UnixFileMode)432);
                return true;
            case "modulemap-koppeling":
                // Devices opent zijn database bij de start (via de listener); de map wijst naar buiten.
                Directory.CreateSymbolicLink(Path.Combine(eigenData, "devices"), Path.GetDirectoryName(kijk)!);
                return true;
            case "modulemap-groep":
                File.SetUnixFileMode(Maak(Path.Combine(eigenData, "quality")), (UnixFileMode)504);
                return true;
            case "moduledb-koppeling":
                File.CreateSymbolicLink(Path.Combine(Maak(Path.Combine(eigenData, "quality")), "quality.db"), kijk);
                return true;
            default:
                return false;
        }
    }

    private static void Bestand(string pad, UnixFileMode modus)
    {
        File.WriteAllBytes(pad, []);
        File.SetUnixFileMode(pad, modus);
    }

    private async Task ControleerRoutes(HttpClient client, CancellationToken stop)
    {
        Assert.NotEmpty(RouteTable.Alle);
        foreach (var route in RouteTable.Alle)
        {
            using var verzoek = new HttpRequestMessage(new HttpMethod(route.Methode), route.Pad.Replace("{slug}", "devices", StringComparison.Ordinal).Replace("{id}", "proef", StringComparison.Ordinal));
            using var antwoord = await client.SendAsync(verzoek, stop);
            var tekst = await antwoord.Content.ReadAsStringAsync(stop);
            var json = JsonNode.Parse(tekst)!;
            // Geen veilige pin beschikbaar: Hub blijft dicht met 401/not_linked (contract §4.7).
            Assert.True((int)antwoord.StatusCode == (route.Auth == JlAuth.Hub ? 401 : 503), route.Id + ": " + tekst);
            Assert.Equal(route.Auth == JlAuth.Hub ? "unauthorized" : "storage_unavailable", (string?)json["code"]);
            Assert.Contains("TrueNAS", (string?)json["message"], StringComparison.Ordinal);
            Assert.Contains("herstart", (string?)json["message"], StringComparison.Ordinal);
            Assert.Equal("down", (string?)json["details"]?["health"]?["status"]);
            Assert.False((bool?)json["details"]?["modules_enabled"]);
            Assert.Equal("no-store", antwoord.Headers.CacheControl?.ToString());
            if (route.Auth == JlAuth.SessieBeheerder)
            {
                Assert.Equal(TimeSpan.FromSeconds(30), antwoord.Headers.RetryAfter?.Delta);
            }
            Assert.DoesNotContain("synthetische kijkgegevens", tekst, StringComparison.Ordinal);
        }

        _auth.Wie = null;
        using var anoniem = await client.GetAsync("/media/v1/modules", stop);
        Assert.Equal(HttpStatusCode.Unauthorized, anoniem.StatusCode);
        _auth.Wie = new SessieIdentiteit(Guid.NewGuid(), false, false);
        using var onbevoegd = await client.GetAsync("/media/v1/modules", stop);
        Assert.Equal(HttpStatusCode.Forbidden, onbevoegd.StatusCode);
        _auth.Wie = new SessieIdentiteit(Guid.NewGuid(), true, false);
    }

    private IHost Host(string data, string cache) => new HostBuilder()
        .ConfigureLogging(l => l.AddProvider(_log))
        .ConfigureWebHost(web => web.UseKestrel(o => o.Listen(IPAddress.Loopback, 0))
            .ConfigureServices(diensten =>
            {
                var paden = new Mock<IApplicationPaths>();
                paden.SetupGet(p => p.DataPath).Returns(data);
                paden.SetupGet(p => p.CachePath).Returns(cache);
                diensten.AddSingleton(paden.Object);
                diensten.AddSingleton(_sessies.Object);
                diensten.AddSingleton(Mock.Of<ILibraryManager>());
                diensten.AddSingleton(Mock.Of<IAuthService>());
                new PluginServiceRegistrator().RegisterServices(diensten, Mock.Of<IServerApplicationHost>());
                diensten.AddSingleton<ISessionAuthenticator>(_auth);
                diensten.AddSingleton<IMediaMappen>(new NepMedia());
                diensten.AddMvc().ConfigureApplicationPartManager(m =>
                {
                    m.ApplicationParts.Clear();
                    m.ApplicationParts.Add(new AssemblyPart(typeof(Plugin).Assembly));
                });
            })
            .Configure(app =>
            {
                app.UseRouting();
                app.UseEndpoints(e =>
                {
                    e.MapControllers();
                    e.MapGet("/serverproef", () => "synthetische kijkgegevens beschikbaar");
                });
            }))
        .Build();

    private static HttpClient Client(IHost host) => new()
    {
        BaseAddress = new Uri(host.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single()),
    };

    private static string Maak(string pad)
    {
        Directory.CreateDirectory(pad, (UnixFileMode)448);
        return pad;
    }

    private static string[] Boom(string map)
    {
        var regels = new List<string>();
        void Lees(string pad)
        {
            var info = new FileInfo(pad);
            var link = info.LinkTarget;
            regels.Add(Path.GetRelativePath(map, pad) + ":" + (link is not null ? "koppeling:" + link : Directory.Exists(pad) ? "map:" + File.GetUnixFileMode(pad) : Convert.ToHexString(File.ReadAllBytes(pad))));
            if (link is null && Directory.Exists(pad))
            {
                foreach (var kind in Directory.EnumerateFileSystemEntries(pad).Order(StringComparer.Ordinal))
                {
                    Lees(kind);
                }
            }
        }

        Lees(map);
        return regels.ToArray();
    }

    private sealed class ProefLog : ILoggerProvider, ILogger
    {
        public ConcurrentQueue<string> Regels { get; } = new();

        public ILogger CreateLogger(string categoryName) => this;

        public void Dispose() { }

        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            Regels.Enqueue(formatter(state, exception));
        }
    }
}
