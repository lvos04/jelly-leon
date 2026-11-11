using System;
using System.IO;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
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
}
