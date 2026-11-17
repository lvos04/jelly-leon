using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Jellyfin.Extensions.Json;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Model.Session;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.ApplicationParts;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// S-G1-17 herstelronde 9, R-HARDE-EIS-19: het gevolg van een instelling van de host bij het draaien, en dezelfde bron als
/// bouwfout. De vormen hieronder worden met Roslyn gecompileerd en (1) met de analyzer bekeken: elke vorm geeft JL0001, dus
/// hij kan de plugin niet meer in; en (2) zonder analyzer geladen in een echte host (Kestrel op loopback) met de JSON-instelling
/// van de server, letterlijk uit <c>Jellyfin.Server/Extensions/ApiServiceCollectionExtensions.cs</c> (<c>AddJellyfinApi</c>), en
/// een nep-actie met de route en de handtekening van <c>PlaystateController.ReportPlaybackStopped</c>. De registratie van de
/// plugin komt eerst, zoals in de server (<c>appHost.Init</c> met <c>PluginManager.RegisterServices</c> vóór
/// <c>Startup.ConfigureServices</c>). Met <c>PostConfigure</c> of een eigen <c>IPostConfigureOptions</c> krijgt de serveractie
/// een ander <c>PositionTicks</c> dan de client stuurde; in de serverbron (v12.4) zet <c>UserDataManager.UpdatePlayState</c>
/// het item dan op gezien en wist het hervatpunt.
/// </summary>
public class HostOptiesDraaienTests
{
    /// <summary>De vormen, als plugincode. Elke regel met een markering geeft precies die code.</summary>
    internal const string Vormen = """
        using System;
        using System.Text.Json;
        using System.Text.Json.Serialization;
        using Microsoft.Extensions.DependencyInjection;
        using Microsoft.Extensions.Options;

        namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
        {
            public sealed class TicksAlsSeconden : JsonConverter<long>
            {
                public override long Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) => reader.GetInt64() * 10_000_000;

                public override void Write(Utf8JsonWriter writer, long value, JsonSerializerOptions options) => writer.WriteNumberValue(value);
            }

            public sealed class JsonInstellingen : IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions> // JL0001
            {
                public void PostConfigure(string name, Microsoft.AspNetCore.Mvc.JsonOptions options) => options.JsonSerializerOptions.Converters.Add(new TicksAlsSeconden()); // JL0001
            }

            public static class Vormen
            {
                public static void Configure(IServiceCollection diensten) =>
                    diensten.Configure<Microsoft.AspNetCore.Mvc.JsonOptions>(o => o.JsonSerializerOptions.Converters.Add(new TicksAlsSeconden())); // JL0001

                public static void PostConfigure(IServiceCollection diensten) =>
                    diensten.PostConfigure<Microsoft.AspNetCore.Mvc.JsonOptions>(o => o.JsonSerializerOptions.Converters.Add(new TicksAlsSeconden())); // JL0001

                public static void Klasse(IServiceCollection diensten) => diensten.AddSingleton<IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>, JsonInstellingen>(); // JL0001
            }
        }
        """;

    private const long EenUur = 36_000_000_000;

    [Fact]
    public async Task Vormen_GevenElkJL0001_MaarZonderAnalyzerWijzigtPostConfigureHetArgumentVanEenServeractie()
    {
        var stop = TestContext.Current.CancellationToken;

        // (1) De bouw: elke vorm geeft JL0001 op precies de gemarkeerde regels.
        var gevonden = await AnalyzerHarnas.AnalyseerAsync(Vormen, null, stop);
        var verwacht = Vormen.Split('\n')
            .Select((tekst, index) => (Regel: index + 1, tekst))
            .Where(r => Regex.IsMatch(r.tekst, @"//\s*JL0001"))
            .Select(r => (r.Regel, "JL0001"))
            .ToHashSet();
        Assert.Equal(5, verwacht.Count);
        Assert.Equal(verwacht, gevonden.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.All(gevonden, b => Assert.Contains("gebruikt een instelling van de host", b.Tekst, StringComparison.Ordinal));

        // (2) Het gevolg: dezelfde bron zonder analyzer gecompileerd en geladen.
        var compilatie = AnalyzerHarnas.Compileer(Vormen);
        using var stroom = new MemoryStream();
        var uitkomst = compilatie.Emit(stroom, cancellationToken: stop);
        Assert.True(uitkomst.Success, string.Join("\n", uitkomst.Diagnostics));
        var vormen = Assembly.Load(stroom.ToArray()).GetType("Jellyfin.Plugin.JellyLeon.Modules.Proef.Vormen", true)!;

        Action<IServiceCollection>? Vorm(string naam) => d => vormen.GetMethod(naam)!.Invoke(null, new object[] { d });

        Assert.Equal(EenUur, await ServeractieKrijgtAsync(null, stop));
        // Configure komt vóór de server en wordt door Converters.Clear() van de server gewist.
        Assert.Equal(EenUur, await ServeractieKrijgtAsync(Vorm("Configure"), stop));
        // PostConfigure en een eigen IPostConfigureOptions komen na de server: de serveractie krijgt een ander getal.
        Assert.Equal(EenUur * 10_000_000, await ServeractieKrijgtAsync(Vorm("PostConfigure"), stop));
        Assert.Equal(EenUur * 10_000_000, await ServeractieKrijgtAsync(Vorm("Klasse"), stop));
    }

    /// <summary>
    /// S-G1-16: dezelfde open fabrieksregistratie geeft nu een bouwfout en zet zonder analyzer
    /// een eerder ingestelde hostoptie terug. Alleen synthetische instellingen in een eigen dienstcontainer.
    /// </summary>
    [Fact]
    public async Task OpenFabriek_IsJL0001_EnZetZonderAnalyzerDeHostinstellingTerug()
    {
        const string Bron = """
            using Microsoft.Extensions.DependencyInjection;
            using Microsoft.Extensions.Options;
            namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
            {
                public sealed class Alles<T> : IOptionsFactory<T> where T : class, new() // JL0001
                {
                    public T Create(string name) => new T();
                }
                public static class Fabriek
                {
                    public static void Registreer(IServiceCollection diensten) =>
                        diensten.AddSingleton(typeof(IOptionsFactory<>), typeof(Alles<>)); // JL0001
                }
            }
            """;
        var stop = TestContext.Current.CancellationToken;
        var gevonden = await AnalyzerHarnas.AnalyseerAsync(Bron, null, stop);
        var verwacht = Bron.Split('\n').Select((regel, index) => (regel, nummer: index + 1))
            .Where(r => r.regel.Contains("// JL0001", StringComparison.Ordinal))
            .Select(r => (r.nummer, "JL0001")).ToHashSet();
        Assert.Equal(2, verwacht.Count);
        Assert.Equal(verwacht, gevonden.Select(b => (b.Regel, b.Id)).ToHashSet());

        using var stroom = new MemoryStream();
        var compilatie = AnalyzerHarnas.Compileer(Bron).Emit(stroom, cancellationToken: stop);
        Assert.True(compilatie.Success, string.Join("\n", compilatie.Diagnostics));
        var fabriek = Assembly.Load(stroom.ToArray()).GetType("Jellyfin.Plugin.JellyLeon.Modules.Proef.Fabriek", true)!;
        var diensten = new ServiceCollection();
        diensten.AddOptions();
        diensten.Configure<JsonOptions>(o => o.JsonSerializerOptions.WriteIndented = true);
        using var voor = diensten.BuildServiceProvider();
        Assert.True(voor.GetRequiredService<Microsoft.Extensions.Options.IOptions<JsonOptions>>().Value.JsonSerializerOptions.WriteIndented);
        fabriek.GetMethod("Registreer")!.Invoke(null, new object[] { diensten });
        using var na = diensten.BuildServiceProvider();
        Assert.False(na.GetRequiredService<Microsoft.Extensions.Options.IOptions<JsonOptions>>().Value.JsonSerializerOptions.WriteIndented);
    }

    /// <summary>Start een host zoals de server, met eerst de registratie van de plugin, en stuurt een stopmelding van één uur.</summary>
    private static async Task<long> ServeractieKrijgtAsync(Action<IServiceCollection>? plugin, System.Threading.CancellationToken stop)
    {
        using var host = new HostBuilder()
            .ConfigureServices(diensten => plugin?.Invoke(diensten))
            .ConfigureWebHost(web => web
                .UseKestrel(o => o.Listen(IPAddress.Loopback, 0))
                .ConfigureServices(diensten => diensten
                    .AddMvc()
                    .ConfigureApplicationPartManager(a =>
                    {
                        a.ApplicationParts.Clear();
                        a.ApplicationParts.Add(new AlleenDeNepActie());
                    })
                    .AddJsonOptions(options =>
                    {
                        // Letterlijk uit AddJellyfinApi (v12.4).
                        var jsonOptions = JsonDefaults.PascalCaseOptions;
                        options.JsonSerializerOptions.ReadCommentHandling = jsonOptions.ReadCommentHandling;
                        options.JsonSerializerOptions.WriteIndented = jsonOptions.WriteIndented;
                        options.JsonSerializerOptions.DefaultIgnoreCondition = jsonOptions.DefaultIgnoreCondition;
                        options.JsonSerializerOptions.NumberHandling = jsonOptions.NumberHandling;
                        options.JsonSerializerOptions.Converters.Clear();
                        foreach (var converter in jsonOptions.Converters)
                        {
                            options.JsonSerializerOptions.Converters.Add(converter);
                        }

                        options.JsonSerializerOptions.PropertyNamingPolicy = jsonOptions.PropertyNamingPolicy;
                    }))
                .Configure(app =>
                {
                    app.UseRouting();
                    app.UseEndpoints(e => e.MapControllers());
                }))
            .Build();
        await host.StartAsync(stop);
        try
        {
            var adres = host.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
            using var client = new HttpClient { BaseAddress = new Uri(adres) };
            var body = "{\"ItemId\":\"" + Guid.NewGuid().ToString() + "\",\"PositionTicks\":" + EenUur.ToString(CultureInfo.InvariantCulture) + "}";
            using var inhoud = new StringContent(body, Encoding.UTF8, "application/json");
            using var antwoord = await client.PostAsync("/Sessions/Playing/Stopped", inhoud, stop);
            Assert.Equal(HttpStatusCode.OK, antwoord.StatusCode);
            return long.Parse(await antwoord.Content.ReadAsStringAsync(stop), CultureInfo.InvariantCulture);
        }
        finally
        {
            await host.StopAsync(stop);
        }
    }

    /// <summary>Alleen de nep-actie als onderdeel met controllers (de server wist de onderdelen ook eerst).</summary>
    private sealed class AlleenDeNepActie : ApplicationPart, IApplicationPartTypeProvider
    {
        public override string Name => "nep-playstate";

        public IEnumerable<TypeInfo> Types => new[] { typeof(NepPlaystateController).GetTypeInfo() };
    }
}
