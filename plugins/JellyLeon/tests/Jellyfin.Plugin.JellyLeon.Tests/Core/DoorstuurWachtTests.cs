using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.ApplicationParts;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// S-G1-17 herstelronde 10, R-HARDE-EIS-20 (herreview 9): een eigen actie stuurde de browser met 307 en Location door naar
/// <c>/UserPlayedItems/&lt;id&gt;</c>, zonder één JL-fout: de status kwam uit een variabele en de kopnaam uit System.Net
/// (<c>HttpResponseHeader.Location.ToString()</c>). <c>JlRouteAttribute</c> controleerde alleen een <c>JlResult</c>. Nu zet het
/// de <see cref="DoorstuurWacht"/> op elk verzoek (<c>Response.OnStarting</c>), en de spike van ADR-0033 doet dat op elk
/// pluginpad. Deze tests draaien in een echte host (Kestrel op loopback, MVC, het echte <c>JlRouteAttribute</c> en de echte
/// <c>JlPipeline</c> uit de registratie van de plugin), met een client die zelf geen omleiding volgt. De tegenproef zonder wacht
/// laat zien dat dezelfde actie in deze host echt 307 met Location geeft.
/// </summary>
public sealed class DoorstuurWachtTests
{
    /// <summary>De vorm van de herreview en de varianten (elk type resultaat, ook zelf geschreven) via het echte filter.</summary>
    [Fact]
    public async Task ElkDoorsturendAntwoordVanEenEigenActie_WordtInDeEchtePipelineDeVasteFout()
    {
        var stop = TestContext.Current.CancellationToken;
        using var harnas = new Harnas();
        using var host = Start(harnas, spike: false);
        await host.StartAsync(stop);
        try
        {
            using var client = Client(host);

            // Tegenproef: dezelfde actie zonder [JlRoute] stuurt in deze host echt door.
            var zonder = await StuurAsync(client, HttpMethod.Delete, "/proef/zonder-wacht/bibliotheek-A", stop);
            Assert.Equal(307, zonder.Status);
            Assert.Equal("/UserPlayedItems/bibliotheek-A", zonder.Location);

            // De vorm van de herreview, plus de varianten: elk wordt de vaste fout 503, zonder Location en zonder de body van de
            // actie. Zonder body van de actie (StatusCodeResult, RedirectResult) als JSON uit de foutcatalogus; schreef de actie
            // of het resultaat zelf een body, dan zonder body.
            foreach (var pad in new[] { "verplaats", "redirect" })
            {
                AssertVasteFout(await StuurAsync(client, HttpMethod.Delete, "/media/v1/proef/" + pad + "/bibliotheek-A", stop), pad);
            }

            foreach (var pad in new[] { "met-body", "location-op-200", "zelf-geschreven" })
            {
                AssertVasteFout(await StuurAsync(client, HttpMethod.Delete, "/media/v1/proef/" + pad + "/bibliotheek-A", stop), pad, json: false);
            }

            // Gewone antwoorden gaan ongewijzigd door.
            var gewoon = await StuurAsync(client, HttpMethod.Delete, "/media/v1/proef/gewoon/bibliotheek-A", stop);
            Assert.Equal(200, gewoon.Status);
            Assert.Null(gewoon.Location);
            Assert.Equal("bibliotheek-A", (string?)gewoon.Json!["id"]);

            // Zonder 3xx, met alleen de Location-kop uit de vorm van de herreview: ook geweigerd.
            AssertVasteFout(await StuurAsync(client, HttpMethod.Delete, "/media/v1/proef/verplaats/bibliotheek-A?verplaatst=false", stop), "verplaatst=false");
        }
        finally
        {
            await host.StopAsync(stop);
        }
    }

    /// <summary>
    /// De spike van ADR-0033 (als die aan staat) zet de wacht op elk pluginpad, ook voor een antwoord dat niet uit een actie met
    /// [JlRoute] komt. Buiten de pluginpaden raakt de spike niets: daar komt de 307 ongewijzigd aan.
    /// </summary>
    [Fact]
    public async Task MetDeSpike_WordtElkDoorsturendAntwoordOpEenPluginpadDeVasteFout_EnDaarbuitenNiets()
    {
        var stop = TestContext.Current.CancellationToken;
        using var harnas = new Harnas();
        using var host = Start(harnas, spike: true);
        await host.StartAsync(stop);
        try
        {
            using var client = Client(host);

            AssertVasteFout(await StuurAsync(client, HttpMethod.Delete, "/media/v1/zonder-filter/bibliotheek-A", stop), "zonder-filter");
            AssertVasteFout(await StuurAsync(client, HttpMethod.Get, "/CONNECTOR/V1/zonder-filter/bibliotheek-A", stop), "connector");
            AssertVasteFout(await StuurAsync(client, HttpMethod.Delete, "/media/v1/proef/verplaats/bibliotheek-A", stop), "verplaats");
            AssertVasteFout(await StuurAsync(client, HttpMethod.Delete, "/media/v1/proef/met-body/bibliotheek-A", stop), "met-body", json: false);
            AssertVasteFout(await StuurAsync(client, HttpMethod.Get, "/media/v1/zonder-filter-body/bibliotheek-A", stop), "zonder-filter-body", json: false);

            var buiten = await StuurAsync(client, HttpMethod.Delete, "/proef/zonder-wacht/bibliotheek-A", stop);
            Assert.Equal(307, buiten.Status);
            Assert.Equal("/UserPlayedItems/bibliotheek-A", buiten.Location);
        }
        finally
        {
            await host.StopAsync(stop);
        }
    }

    private static void AssertVasteFout(Antwoord antwoord, string wat, bool json = true)
    {
        var context = wat + ": status " + antwoord.Status + ", body '" + antwoord.Tekst + "'\n" + string.Join("\n", Log.Regels);
        Assert.True(antwoord.Status == 503, context);
        Assert.True(antwoord.Location is null, wat + ": Location " + antwoord.Location);
        Assert.Equal("no-store", antwoord.CacheControl);
        Assert.DoesNotContain("UserPlayedItems", antwoord.Tekst, StringComparison.Ordinal);
        if (json)
        {
            Assert.True(antwoord.Json is not null, context);
            Assert.Equal("dependency_unavailable", (string?)antwoord.Json!["code"]);
            Assert.Equal("jelly-leon", (string?)antwoord.Json["details"]!["dependency"]);
            Assert.True(Guid.TryParseExact((string?)antwoord.Json["trace_id"], "D", out _), wat);
        }
        else
        {
            Assert.True(antwoord.Tekst.Length == 0, context);
        }
    }

    private static IHost Start(Harnas harnas, bool spike) => new HostBuilder()
        .ConfigureLogging(l => l.AddProvider(Log))
        .ConfigureWebHost(web => web
            .UseKestrel(o => o.Listen(IPAddress.Loopback, 0))
            .ConfigureServices(diensten =>
            {
                // De echte pipeline uit de registratie van de plugin (PluginServiceRegistrator, via het harnas).
                diensten.AddSingleton(harnas.Dienst<JlPipeline>());
                diensten.AddMvc().ConfigureApplicationPartManager(a =>
                {
                    a.ApplicationParts.Clear();
                    a.ApplicationParts.Add(new AlleenDeProefActies());
                });
            })
            .Configure(app =>
            {
                if (spike)
                {
                    app.Use(JlStartupFilterSpike.VoorAuthAsync);
                }

                app.UseRouting();
                app.UseEndpoints(e =>
                {
                    e.MapControllers();

                    // Een antwoord op een pluginpad dat niet uit een actie met [JlRoute] komt (alleen de spike ziet het).
                    e.Map("/media/v1/zonder-filter/{id}", http => ProefDoorstuurController.StuurDoor(http, (string)http.Request.RouteValues["id"]!));
                    e.Map("/connector/v1/zonder-filter/{id}", http => ProefDoorstuurController.StuurDoor(http, (string)http.Request.RouteValues["id"]!));
                    e.Map("/media/v1/zonder-filter-body/{id}", async http =>
                    {
                        await ProefDoorstuurController.StuurDoor(http, (string)http.Request.RouteValues["id"]!);
                        await http.Response.WriteAsync("{}", http.RequestAborted);
                    });
                });
            }))
        .Build();

    private static HttpClient Client(IHost host)
    {
        var adres = host.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
#pragma warning disable CA5399 // Een lokale testclient op loopback; geen certificaatcontrole nodig.
        var handler = new HttpClientHandler { AllowAutoRedirect = false };
#pragma warning restore CA5399
        return new HttpClient(handler, true) { BaseAddress = new Uri(adres) };
    }

    private static async Task<Antwoord> StuurAsync(HttpClient client, HttpMethod methode, string pad, CancellationToken stop)
    {
        using var verzoek = new HttpRequestMessage(methode, pad);
        verzoek.Headers.Add("Idempotency-Key", Guid.NewGuid().ToString());
        using var antwoord = await client.SendAsync(verzoek, stop);
        var tekst = await antwoord.Content.ReadAsStringAsync(stop);
        JsonNode? json = null;
        if (tekst.StartsWith('{'))
        {
            json = JsonNode.Parse(tekst);
        }

        return new Antwoord(
            (int)antwoord.StatusCode,
            antwoord.Headers.Location?.OriginalString,
            antwoord.Headers.CacheControl?.ToString(),
            tekst,
            json);
    }

    /// <summary>De logregels van de host (bij een fout in de melding, en de wacht meldt elke weigering).</summary>
    private static readonly Verzamelaar Log = new();

    private sealed class Verzamelaar : Microsoft.Extensions.Logging.ILoggerProvider, Microsoft.Extensions.Logging.ILogger
    {
        public System.Collections.Concurrent.ConcurrentQueue<string> Regels { get; } = new();

        public Microsoft.Extensions.Logging.ILogger CreateLogger(string categoryName) => this;

        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull => null;

        public bool IsEnabled(Microsoft.Extensions.Logging.LogLevel logLevel) => logLevel >= Microsoft.Extensions.Logging.LogLevel.Warning;

        public void Log<TState>(Microsoft.Extensions.Logging.LogLevel logLevel, Microsoft.Extensions.Logging.EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (IsEnabled(logLevel))
            {
                Regels.Enqueue(logLevel + ": " + formatter(state, exception) + (exception is null ? string.Empty : " | " + exception.GetType().Name + ": " + exception.Message + " @ " + exception.StackTrace));
            }
        }

        public void Dispose()
        {
        }
    }

    private sealed record Antwoord(int Status, string? Location, string? CacheControl, string Tekst, JsonNode? Json);

    /// <summary>Alleen de proefacties als onderdeel met controllers.</summary>
    private sealed class AlleenDeProefActies : ApplicationPart, IApplicationPartTypeProvider
    {
        public override string Name => "proef-doorsturen";

        public IEnumerable<TypeInfo> Types => new[] { typeof(ProefDoorstuurController).GetTypeInfo() };
    }
}

/// <summary>
/// Proefacties voor <see cref="DoorstuurWachtTests"/>: de vorm van herreview 9 en varianten met elk type resultaat. Ze dragen
/// [JlRoute] met een bestaande route uit de tabel (DELETE, beheerder, Idempotency-Key), zoals een echte eigen actie.
/// </summary>
[Route("")]
public sealed class ProefDoorstuurController : ControllerBase
{
    /// <summary>De vorm van de herreview: status uit een variabele, kopnaam uit System.Net, een <c>StatusCodeResult</c>.</summary>
    [HttpDelete("media/v1/proef/verplaats/{id}")]
    [JlRoute("hublink.delete")]
    public IActionResult Verplaats(string id, [FromQuery] bool verplaatst = true)
    {
        var status = verplaatst ? HttpStatusCode.TemporaryRedirect : HttpStatusCode.OK;
        Response.Headers[HttpResponseHeader.Location.ToString()] = "/UserPlayedItems/" + id;
        return StatusCode((int)status);
    }

    /// <summary>Een <c>ObjectResult</c> met body en een 308 uit een variabele.</summary>
    [HttpDelete("media/v1/proef/met-body/{id}")]
    [JlRoute("hublink.delete")]
    public IActionResult MetBody(string id)
    {
        Response.Headers[HttpResponseHeader.Location.ToString()] = "/UserPlayedItems/" + id;
        return new ObjectResult(new { id }) { StatusCode = Code(308) };
    }

    /// <summary>Alleen een Location-kop, op een gewoon 200-antwoord met body.</summary>
    [HttpDelete("media/v1/proef/location-op-200/{id}")]
    [JlRoute("hublink.delete")]
    public IActionResult LocationOp200(string id)
    {
        Response.Headers[HttpResponseHeader.Location.ToString()] = "/UserPlayedItems/" + id;
        return Ok(new { id });
    }

    /// <summary>Een gewone redirect van MVC (302 met Location, zonder body).</summary>
    [HttpDelete("media/v1/proef/redirect/{id}")]
    [JlRoute("hublink.delete")]
    public IActionResult Doorverwijzing(string id) => Redirect("/UserPlayedItems/" + id);

    /// <summary>Status en kop gezet en de body zelf geschreven, in de actie.</summary>
    [HttpDelete("media/v1/proef/zelf-geschreven/{id}")]
    [JlRoute("hublink.delete")]
    public async Task ZelfGeschreven(string id)
    {
        Response.StatusCode = Code(301);
        Response.Headers[HttpResponseHeader.Location.ToString()] = "/UserPlayedItems/" + id;
        await Response.WriteAsync("{\"id\":\"" + id + "\"}");
    }

    /// <summary>Een gewoon antwoord: gaat ongewijzigd door.</summary>
    [HttpDelete("media/v1/proef/gewoon/{id}")]
    [JlRoute("hublink.delete")]
    public IActionResult Gewoon(string id) => Ok(new { id });

    /// <summary>Tegenproef: dezelfde vorm zonder [JlRoute], buiten de pluginpaden.</summary>
    [HttpDelete("proef/zonder-wacht/{id}")]
    public IActionResult ZonderWacht(string id) => Verplaats(id);

    /// <summary>Een antwoord buiten MVC om, voor de spike.</summary>
    internal static Task StuurDoor(HttpContext http, string id)
    {
        http.Response.StatusCode = Code(307);
        http.Response.Headers[HttpResponseHeader.Location.ToString()] = "/UserPlayedItems/" + id;
        return Task.CompletedTask;
    }

    /// <summary>Een status die pas bij het draaien ontstaat.</summary>
    private static int Code(int waarde) => int.Parse(waarde.ToString(System.Globalization.CultureInfo.InvariantCulture), System.Globalization.CultureInfo.InvariantCulture);
}
