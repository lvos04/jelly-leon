using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// Spike IStartupFilter (B03-017, ADR-0033): de laag vóór routing en authenticatie weigert alleen een te grote
/// Content-Length op een pluginroute en laat al het andere ongewijzigd door. De meting op een echte server staat in
/// tools/jelly-leon/e2e/startupfilter_spike.py.
/// </summary>
public sealed class StartupFilterSpikeTests
{
    private static async Task<(int Status, JsonObject? Body, bool Door)> Roep(string pad, long? lengte)
    {
        var http = new DefaultHttpContext();
        http.Request.Method = "POST";
        http.Request.Path = pad;
        http.Request.ContentLength = lengte;
        using var uit = new MemoryStream();
        http.Response.Body = uit;
        var door = false;
        await JlStartupFilterSpike.VoorAuthAsync(http, _ =>
        {
            door = true;
            return Task.CompletedTask;
        });
        var tekst = System.Text.Encoding.UTF8.GetString(uit.ToArray());
        return (http.Response.StatusCode, tekst.Length == 0 ? null : JsonNode.Parse(tekst)!.AsObject(), door);
    }

    [Theory]
    [InlineData("/connector/v1/propose")]
    [InlineData("/media/v1/modules/devices")]
    [InlineData("/MEDIA/V1/hub-link")]
    public async Task Te_groot_op_een_pluginroute_geeft_413_zonder_de_rest_van_de_pipeline(string pad)
    {
        var (status, body, door) = await Roep(pad, Fouten.MaxBodyBytes + 1);

        Assert.Equal(413, status);
        Assert.False(door);
        Assert.Equal("payload_too_large", (string?)body!["code"]);
        Assert.Equal(Fouten.MaxBodyBytes, (int?)body["details"]!["max_bytes"]);
        Assert.True(Guid.TryParseExact((string?)body["trace_id"], "D", out _));
        Assert.Equal(4, body.Count);
    }

    [Theory]
    [InlineData("/connector/v1/propose", (long)Fouten.MaxBodyBytes)]
    [InlineData("/connector/v1/propose", 0L)]
    [InlineData("/connector/v1/propose", null)]
    [InlineData("/Users/AuthenticateByName", (long)Fouten.MaxBodyBytes + 1)]
    [InlineData("/media/v10/iets", (long)Fouten.MaxBodyBytes + 1)]
    [InlineData("/mediax/v1", (long)Fouten.MaxBodyBytes + 1)]
    [InlineData("/Items/media/v1/x", (long)Fouten.MaxBodyBytes + 1)]
    public async Task Al_het_andere_gaat_ongewijzigd_door(string pad, long? lengte)
    {
        var (status, body, door) = await Roep(pad, lengte);

        Assert.True(door);
        Assert.Equal(200, status);
        Assert.Null(body);
    }

    [Theory]
    [InlineData("1", true)]
    [InlineData(null, false)]
    [InlineData("", false)]
    [InlineData("0", false)]
    [InlineData("true", false)]
    [InlineData(" 1", false)]
    public void Alleen_de_waarde_1_zet_de_spike_aan(string? waarde, bool verwacht)
    {
        Assert.Equal(verwacht, JlStartupFilterSpike.IsAan(naam => naam == JlStartupFilterSpike.Schakelaar ? waarde : "1"));
    }

    /// <summary>
    /// S-G1-17 herstelronde 8 (R-HARDE-EIS-17, besluit punt 3): in een echte host (Kestrel op loopback, de spike geregistreerd
    /// zoals <c>PluginServiceRegistrator</c> dat doet, daarna routing en een endpoint zoals de server) komt een verzoek buiten
    /// de pluginpaden ongewijzigd aan: methode, pad, padbasis, query, Authorization, lengte, body en routewaarde. Ook een klein
    /// verzoek op een pluginpad gaat ongewijzigd door. Een te groot verzoek op een pluginpad krijgt 413 en bereikt het endpoint
    /// niet: dat bewijst dat de spike echt in de pijplijn zit.
    /// </summary>
    [Fact]
    public async Task In_een_echte_host_komt_een_verzoek_buiten_de_pluginpaden_ongewijzigd_aan()
    {
        var stop = TestContext.Current.CancellationToken;
        var bereikt = 0;
        using var host = new HostBuilder()
            .ConfigureWebHost(web => web
                .UseKestrel(o => o.Listen(IPAddress.Loopback, 0))
                .ConfigureServices(diensten =>
                {
                    diensten.AddRouting();
                    diensten.AddTransient<IStartupFilter, JlStartupFilterSpike>();
                })
                .Configure(app =>
                {
                    app.UseRouting();
                    app.UseEndpoints(e => e.Map("{**pad}", async http =>
                    {
                        Interlocked.Increment(ref bereikt);
                        await EchoAsync(http);
                    }));
                }))
            .Build();
        await host.StartAsync(stop);
        try
        {
            var adres = host.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
            using var client = new HttpClient { BaseAddress = new Uri(adres) };
            const string Token = "MediaBrowser Token=\"token-van-de-client\"";
            var groot = new byte[Fouten.MaxBodyBytes + 1];
            groot[^1] = 42;
            var gevallen = new (HttpMethod Methode, string Pad, string Query, byte[]? Body)[]
            {
                (HttpMethod.Delete, "/UserPlayedItems/bibliotheek-A", "?userId=gebruiker-B", null),
                (HttpMethod.Get, "/Items", "?ParentId=bibliotheek-A&Recursive=true", null),
                (HttpMethod.Post, "/Sessions/Playing/Stopped", string.Empty, Encoding.UTF8.GetBytes("{\"ItemId\":\"x\",\"PositionTicks\":5}")),
                (HttpMethod.Post, "/Users/AuthenticateByName", string.Empty, groot),
                (HttpMethod.Post, "/Items/media/v1/x", "?a=1", groot),
                (HttpMethod.Post, "/media/v1/modules/devices", "?b=2", Encoding.UTF8.GetBytes("{}")),
            };

            foreach (var (methode, pad, query, body) in gevallen)
            {
                using var verzoek = new HttpRequestMessage(methode, pad + query);
                verzoek.Headers.TryAddWithoutValidation("Authorization", Token);
                if (body is not null)
                {
                    verzoek.Content = new ByteArrayContent(body);
                }

                using var antwoord = await client.SendAsync(verzoek, stop);
                Assert.Equal(HttpStatusCode.OK, antwoord.StatusCode);
                var echo = JsonNode.Parse(await antwoord.Content.ReadAsStringAsync(stop))!.AsObject();
                Assert.Equal(methode.Method, (string?)echo["methode"]);
                Assert.Equal(pad, (string?)echo["pad"]);
                Assert.Equal(string.Empty, (string?)echo["padbasis"]);
                Assert.Equal(query, (string?)echo["query"]);
                Assert.Equal(Token, (string?)echo["authorization"]);
                Assert.Equal((long?)body?.Length, (long?)echo["lengte"]);
                Assert.Equal(Convert.ToHexString(SHA256.HashData(body ?? [])), (string?)echo["body"]);
                Assert.Equal(pad.TrimStart('/'), (string?)echo["routepad"]);
            }

            Assert.Equal(gevallen.Length, bereikt);

            using var teGroot = new HttpRequestMessage(HttpMethod.Post, "/connector/v1/propose") { Content = new ByteArrayContent(groot) };
            using var geweigerd = await client.SendAsync(teGroot, stop);
            Assert.Equal(HttpStatusCode.RequestEntityTooLarge, geweigerd.StatusCode);
            Assert.Equal(gevallen.Length, bereikt);
        }
        finally
        {
            await host.StopAsync(stop);
        }
    }

    [Fact]
    public async Task Het_filter_zet_de_laag_voor_de_rest_van_de_pipeline()
    {
        var volgorde = new System.Collections.Generic.List<string>();
        var bouwer = new ApplicationBuilder(new ServiceCollection().BuildServiceProvider());
        new JlStartupFilterSpike().Configure(app =>
        {
            volgorde.Add("startup");
            app.Run(_ =>
            {
                volgorde.Add("rest");
                return Task.CompletedTask;
            });
        })(bouwer);
        var pijplijn = bouwer.Build();

        var groot = new DefaultHttpContext();
        groot.Request.Path = "/connector/v1/apply";
        groot.Request.ContentLength = Fouten.MaxBodyBytes + 1;
        groot.Response.Body = new MemoryStream();
        await pijplijn(groot);
        Assert.Equal(413, groot.Response.StatusCode);
        Assert.Equal(["startup"], volgorde);

        var klein = new DefaultHttpContext();
        klein.Request.Path = "/connector/v1/apply";
        klein.Request.ContentLength = 10;
        await pijplijn(klein);
        Assert.Equal(["startup", "rest"], volgorde);
    }

    /// <summary>Het endpoint van de proef: geeft terug wat er van het verzoek aankwam (de body als sha256).</summary>
    private static async Task EchoAsync(HttpContext http)
    {
        using var inhoud = new MemoryStream();
        await http.Request.Body.CopyToAsync(inhoud);
        var echo = new JsonObject
        {
            ["methode"] = http.Request.Method,
            ["pad"] = http.Request.Path.Value,
            ["padbasis"] = http.Request.PathBase.Value ?? string.Empty,
            ["query"] = http.Request.QueryString.Value ?? string.Empty,
            ["authorization"] = http.Request.Headers.Authorization.ToString(),
            ["lengte"] = http.Request.ContentLength,
            ["body"] = Convert.ToHexString(SHA256.HashData(inhoud.ToArray())),
            ["routepad"] = http.Request.RouteValues["pad"]?.ToString(),
        };
        http.Response.ContentType = "application/json";
        await http.Response.WriteAsync(echo.ToJsonString());
    }
}
