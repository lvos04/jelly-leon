using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// Contracttest van de foutcatalogus (contract 1.3 §5, JLT-68): dezelfde situatie geeft in elke module dezelfde
/// status en code, in de vaste volgorde authenticatie → rol → module → 413 → 400 → 422 → 428 → idempotentie.
/// </summary>
public sealed class FoutcatalogusTests : IDisposable
{
    private const string Sleutel = "5f0c2a8e-4b1d-4c3a-9e7f-1a2b3c4d5e6f";
    private readonly Harnas _h = new();

    public static TheoryData<string> Modules => ["devices", "quality"];

    public void Dispose() => _h.Dispose();

    private static string Vorm(Antwoord a)
    {
        // Alles behalve trace_id en de waarde van huidige_etag moet per module gelijk zijn.
        var kopie = a.Json!.DeepClone().AsObject();
        kopie.Remove("trace_id");
        if (kopie["details"]?["huidige_etag"] is not null)
        {
            kopie["details"]!["huidige_etag"] = "<etag>";
        }

        return a.Status + " " + kopie.ToJsonString();
    }

    private async Task<List<string>> Scenario(string module)
    {
        var uit = new List<string>();
        async Task Stap(string routeId, string? body = null, string[]? kop = null, byte[]? ruw = null) =>
            uit.Add(Vorm(await _h.Roep(module + "." + routeId, body, kop, ruw: ruw)));

        var groot = new byte[Fouten.MaxBodyBytes + 1];
        Array.Fill(groot, (byte)' ');

        // Niet aangemeld gaat vóór alles, ook vóór 413 en vóór "module uit".
        _h.Sessies.Wie = null;
        await Stap("settings.put", ruw: groot);
        await Stap("status");
        _h.Sessies.Wie = new SessieIdentiteit(Guid.NewGuid(), true, true);
        await Stap("status");
        _h.Sessies.Wie = new SessieIdentiteit(Guid.NewGuid(), false, false);
        await Stap("settings.get");
        _h.Sessies.Wie = new SessieIdentiteit(Guid.Parse("11111111-2222-4333-8444-555555555555"), true, false);

        // Module uit: 404, ook met een geldige sleutel en body.
        await Stap("status");
        await Stap("settings.put", "{\"bewaar_dagen\":7}", ["Idempotency-Key: " + Sleutel, "If-Match: \"x\""]);
        _h.Schakelaars.Zet(module, true);

        await Stap("settings.put", ruw: groot, kop: ["Idempotency-Key: " + Sleutel, "If-Match: \"x\""]);
        await Stap("settings.put", "{\"bewaar_dagen\":7}");
        await Stap("settings.put", "{\"bewaar_dagen\":7}", ["Idempotency-Key: geen-uuid"]);
        await Stap("settings.put", "{geen json", ["Idempotency-Key: " + Sleutel]);
        await Stap("settings.put", "[1]", ["Idempotency-Key: " + Sleutel]);
        await Stap("settings.put", "{\"bewaar_dagen\":7}", ["Idempotency-Key: " + Sleutel]);
        await Stap("settings.put", "{\"bewaar_dagen\":7}", ["Idempotency-Key: " + Sleutel, "If-Match: \"verkeerd\""]);
        await Stap("settings.put", "{\"bewaar_dagen\":9}", ["Idempotency-Key: " + Sleutel, "If-Match: \"verkeerd\""]);
        await Stap("settings.put", "{\"bewaar_dagen\":0}", ["Idempotency-Key: " + Guid.NewGuid(), "If-Match: \"x\""]);
        await Stap("settings.put", "{\"bewaar_dagen\":7,\"extra\":1}", ["Idempotency-Key: " + Guid.NewGuid(), "If-Match: \"x\""]);
        await Stap("settings.put", "{\"bewaar_dagen\":\"7\"}", ["Idempotency-Key: " + Guid.NewGuid(), "If-Match: \"x\""]);
        _h.Schakelaars.Zet(module, false);
        return uit;
    }

    [Fact]
    public async Task ZelfdeSituatie_ZelfdeFoutInElkeModule()
    {
        var devices = await Scenario("devices");
        var quality = await Scenario("quality");
        Assert.Equal(devices, quality);

        var codes = devices.Select(v => v.Split(' ')[0] + " " + JsonNode.Parse(v[(v.IndexOf(' ') + 1)..])!["code"]!.GetValue<string>()).ToArray();
        Assert.Equal(
            [
                "401 unauthorized", "401 unauthorized", "403 forbidden", "403 forbidden",
                "404 not_found", "404 not_found",
                "413 payload_too_large", "400 idempotency_key_required", "400 idempotency_key_invalid",
                "422 validation_error", "422 validation_error", "428 precondition_required",
                "412 precondition_failed", "422 idempotency_key_reused",
                "422 validation_error", "422 validation_error", "422 validation_error",
            ],
            codes);
        Assert.Contains("\"reason\":\"kid_profile\"", devices[2], StringComparison.Ordinal);
        Assert.Contains("\"reason\":\"admin_required\"", devices[3], StringComparison.Ordinal);
        Assert.Contains("\"max_bytes\":1048576", devices[6], StringComparison.Ordinal);
    }

    [Theory]
    [MemberData(nameof(Modules))]
    public async Task Instellingen_EtagHerhalingEnVerlorenUpdate(string module)
    {
        _h.Schakelaars.Zet(module, true);
        var begin = await _h.Roep(module + ".settings.get");
        Assert.Equal(200, begin.Status);
        var etag = begin.Kop["ETag"];

        string[] kop = ["Idempotency-Key: " + Sleutel, "If-Match: " + etag];
        var eerste = await _h.Roep(module + ".settings.put", "{\"bewaar_dagen\":14}", kop);
        Assert.Equal(200, eerste.Status);
        Assert.Equal(14, eerste.Json!["bewaar_dagen"]!.GetValue<int>());
        Assert.NotEqual(etag, eerste.Kop["ETag"]);
        Assert.False(eerste.Kop.ContainsKey("Idempotent-Replay"));

        // Dezelfde sleutel en hetzelfde verzoek: het oorspronkelijke antwoord, niets wordt opnieuw uitgevoerd.
        var herhaling = await _h.Roep(module + ".settings.put", "{\"bewaar_dagen\":14}", kop);
        Assert.Equal(200, herhaling.Status);
        Assert.Equal("true", herhaling.Kop["Idempotent-Replay"]);
        Assert.Equal(eerste.Kop["ETag"], herhaling.Kop["ETag"]);
        Assert.Equal(eerste.Json.ToJsonString(), herhaling.Json!.ToJsonString());

        // Dezelfde sleutel met een andere body: 422, nooit stil uitvoeren.
        var anders = await _h.Roep(module + ".settings.put", "{\"bewaar_dagen\":15}", kop);
        Assert.Equal((422, "idempotency_key_reused"), (anders.Status, anders.Code));

        // Een tweede schrijver met de oude ETag verliest: 412 met de huidige ETag.
        var oud = await _h.Roep(module + ".settings.put", "{\"bewaar_dagen\":30}", ["Idempotency-Key: " + Guid.NewGuid(), "If-Match: " + etag]);
        Assert.Equal((412, "precondition_failed"), (oud.Status, oud.Code));
        Assert.Equal(eerste.Kop["ETag"], oud.Json!["details"]!["huidige_etag"]!.GetValue<string>());
        Assert.Equal(14, (await _h.Roep(module + ".settings.get")).Json!["bewaar_dagen"]!.GetValue<int>());
    }

    [Fact]
    public void Catalogus_BevatElkeContractcodeMetDeJuisteStatus()
    {
        var verwacht = new Dictionary<string, int>
        {
            ["idempotency_key_required"] = 400, ["idempotency_key_invalid"] = 400, ["unauthorized"] = 401, ["forbidden"] = 403,
            ["not_found"] = 404, ["idempotency_in_progress"] = 409, ["conflict"] = 409, ["precondition_failed"] = 412,
            ["payload_too_large"] = 413, ["validation_error"] = 422, ["idempotency_key_reused"] = 422,
            ["item_in_playback"] = 423, ["precondition_required"] = 428, ["rate_limited"] = 429, ["capability_unavailable"] = 501,
            ["storage_unavailable"] = 503, ["replay_check_unavailable"] = 503, ["dependency_unavailable"] = 503,
            ["worker_unavailable"] = 503, ["mediaguard_unavailable"] = 503, ["engine_unavailable"] = 503,
        };
        Assert.Equal(verwacht.OrderBy(p => p.Key, StringComparer.Ordinal), Fouten.Catalogus.OrderBy(p => p.Key, StringComparer.Ordinal));

        JlException[] alle =
        [
            Fouten.NietGeauthenticeerd("invalid_token"), Fouten.Verboden("role_kind"), Fouten.NietGevonden(), Fouten.SleutelVerplicht(),
            Fouten.SleutelOngeldig(), Fouten.SleutelBezig(), Fouten.SleutelHergebruikt(), Fouten.Conflict("x"), Fouten.PreconditieMislukt("\"e\""),
            Fouten.PreconditieVerplicht(), Fouten.ItemWordtAfgespeeld(), Fouten.TeVeelVerzoeken(5), Fouten.TeGroot(), Fouten.Validatie(("v", "c", "m")), Fouten.NietBeschikbaar("x"),
            Fouten.OpslagOnbeschikbaar(), Fouten.ReplayControleOnbeschikbaar(), Fouten.AfhankelijkheidOnbeschikbaar("x"),
            Fouten.AfhankelijkheidOnbeschikbaar("worker"), Fouten.AfhankelijkheidOnbeschikbaar("mediaguard"), Fouten.AfhankelijkheidOnbeschikbaar("engine"),
        ];
        Assert.Equal(verwacht.Count, alle.Select(f => f.Code).Distinct(StringComparer.Ordinal).Count());
        foreach (var fout in alle)
        {
            Assert.Equal(Fouten.Catalogus[fout.Code], fout.Status);
            var antwoord = JlResult.Fout(fout, Guid.NewGuid().ToString());
            if (fout.Status is 429 or 503)
            {
                Assert.True(int.Parse(antwoord.Headers["Retry-After"], System.Globalization.CultureInfo.InvariantCulture) > 0);
            }

            var json = JsonNode.Parse(antwoord.Body!)!.AsObject();
            Assert.Equal(["code", "message", "details", "trace_id"], json.Select(p => p.Key));
            Assert.IsType<JsonObject>(json["details"]);
            Assert.False(string.IsNullOrWhiteSpace(json["message"]!.GetValue<string>()));
        }
    }

    [Fact]
    public async Task ElkeRoute_WeigertEenByteTeVeelMetEnZonderLengte()
    {
        _h.Koppel();
        _h.Schakelaars.Zet("devices", true);
        _h.Schakelaars.Zet("quality", true);
        var groot = new byte[Fouten.MaxBodyBytes + 1];
        var acties = typeof(JlRouteAttribute).Assembly.GetTypes().Where(t => typeof(ControllerBase).IsAssignableFrom(t))
            .SelectMany(t => t.GetMethods()).Where(m => m.GetCustomAttribute<JlRouteAttribute>() is not null)
            .ToDictionary(m => m.GetCustomAttribute<JlRouteAttribute>()!.Id, StringComparer.Ordinal);
        foreach (var route in RouteTable.Alle)
        {
            var actie = acties[route.Id];
            var grens = actie.GetCustomAttribute<RequestSizeLimitAttribute>() ?? actie.DeclaringType!.GetCustomAttribute<RequestSizeLimitAttribute>();
            Assert.Equal(Fouten.MaxBodyBytes, ((IRequestSizeLimitMetadata?)grens)?.MaxRequestBodySize);
            foreach (var chunked in new[] { false, true })
            {
                string[] kop = ["Authorization: Bearer " + _h.Hub.Token(_h.Klok.Nu, "admin")];
                var antwoord = await _h.Roep(route.Id, kop: kop, pad: new() { ["slug"] = "devices", ["id"] = "proef" }, ruw: groot, chunked: chunked);
                Assert.Equal((route.Id, chunked, 413, "payload_too_large"), (route.Id, chunked, antwoord.Status, antwoord.Code));
                Assert.Equal(Fouten.MaxBodyBytes, (int?)antwoord.Json!["details"]!["max_bytes"]);
                Assert.True(Guid.TryParseExact((string?)antwoord.Json["trace_id"], "D", out _));
            }
        }
    }

    [Theory]
    [InlineData(false, "", true)]
    [InlineData(false, "", false)]
    [InlineData(true, "", false)]
    [InlineData(true, "/jl-proef", false)]
    [InlineData(true, "/jl-proef", true)]
    public async Task Kestrel_StuurtDeContractfoutMetEnZonderLengte(bool spike, string basispad, bool aangemeld)
    {
        if (!aangemeld)
        {
            _h.Sessies.Wie = null;
        }

        var stop = TestContext.Current.CancellationToken;
        using var host = new HostBuilder().ConfigureWebHost(web => web
            .UseKestrel(opties => opties.Listen(IPAddress.Loopback, 0))
            .ConfigureServices(diensten =>
            {
                if (spike)
                {
                    diensten.AddTransient<IStartupFilter, JlStartupFilterSpike>();
                }

                diensten.AddSingleton(_h.Dienst<JlPipeline>());
                diensten.AddControllers().AddApplicationPart(typeof(JlRouteAttribute).Assembly);
            })
            .Configure(app =>
            {
                if (basispad.Length > 0)
                {
                    app.UsePathBase(basispad);
                }

                app.UseRouting();
                app.UseEndpoints(routes => routes.MapControllers());
            })).Build();
        await host.StartAsync(stop);
        try
        {
            var adressen = host.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!;
            using var client = new HttpClient { BaseAddress = new Uri(adressen.Addresses.Single()) };
            var teGroot = new byte[Fouten.MaxBodyBytes + 1];
            foreach (var chunked in new[] { false, true })
            {
                foreach (var (methode, pad) in new[] { (HttpMethod.Get, "/media/v1/modules"), (HttpMethod.Post, "/media/v1/hub-link/verify") })
                {
                    TestContext.Current.TestOutputHelper?.WriteLine($"{methode} {pad}, chunked={chunked}");
                    using var vraag = new HttpRequestMessage(methode, basispad + pad) { Content = new ByteArrayContent(teGroot) };
                    vraag.Headers.TransferEncodingChunked = chunked;
                    using var antwoord = await client.SendAsync(vraag, stop);
                    var verwacht413 = aangemeld || (spike && basispad.Length == 0 && !chunked);
                    Assert.Equal(verwacht413 ? HttpStatusCode.RequestEntityTooLarge : HttpStatusCode.Unauthorized, antwoord.StatusCode);
                    Assert.Equal("application/json", antwoord.Content.Headers.ContentType?.MediaType);
                    Assert.True(antwoord.Headers.CacheControl?.NoStore);
                    Assert.True(antwoord.Headers.ConnectionClose);
                    var fout = JsonNode.Parse(await antwoord.Content.ReadAsByteArrayAsync(stop))!.AsObject();
                    Assert.Equal(["code", "message", "details", "trace_id"], fout.Select(e => e.Key));
                    Assert.Equal(verwacht413 ? "payload_too_large" : "unauthorized", (string?)fout["code"]);
                    if (verwacht413)
                    {
                        Assert.Equal(Fouten.MaxBodyBytes, (int?)fout["details"]!["max_bytes"]);
                    }

                    Assert.True(Guid.TryParseExact((string?)fout["trace_id"], "D", out _));
                }
            }
        }
        finally
        {
            await host.StopAsync(stop);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task PreciesEenMiB_MagDoorNaarDeRoute(bool chunked)
    {
        var bytes = new byte[Fouten.MaxBodyBytes];
        var antwoord = await _h.Roep("modules.list", ruw: bytes, chunked: chunked);
        Assert.Equal(200, antwoord.Status);
        var ongeldigeJson = await _h.Roep("hublink.verify", ruw: bytes, chunked: chunked);
        Assert.Equal((422, "validation_error"), (ongeldigeJson.Status, ongeldigeJson.Code));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Volgorde_AuthenticatieGaatVoorDeBodygrens(bool chunked)
    {
        var groot = new byte[Fouten.MaxBodyBytes + 1];
        _h.Koppel();
        var zonder = await _h.Roep("connector.propose", ruw: groot, chunked: chunked);
        Assert.Equal(401, zonder.Status);
        var met = await _h.Roep("connector.propose", ruw: groot, chunked: chunked, kop: ["Authorization: Bearer " + _h.Hub.Token(_h.Klok.Nu, "admin")]);
        Assert.Equal((413, "payload_too_large"), (met.Status, met.Code));
    }
}
