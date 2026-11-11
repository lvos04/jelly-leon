using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.MediaGuard;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// De ene MediaGuard-viewerclient (B03-009, ADR-0034) tegen een nagebootste MediaGuard achter een nagebootste weg via
/// de Hub: alleen rol viewer, alleen routes en velden van de witte lijst, alleen lezen, niets bewaren. Geen echte
/// MediaGuard en geen echte Hub.
/// </summary>
public sealed class MediaGuardTests : IDisposable
{
    private const string Merk = "Geheime-Titel-9917";
    private readonly Harnas _h = new();

    public void Dispose() => _h.Dispose();

    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact]
    public async Task Zonder_weg_naar_MediaGuard_blijft_de_status_onbekend_en_gaat_er_niets_de_deur_uit()
    {
        using var client = new MediaGuardClient(new GeenMediaGuardVervoer(), _h.Klok);
        Assert.Equal((MgStatus.Onbekend, "nog_niet_gemeten"), (client.Beeld.Status, client.Beeld.Reden));

        await client.VerversAsync(Ct);

        Assert.Equal((MgStatus.Onbekend, "geen_route_via_hub"), (client.Beeld.Status, client.Beeld.Reden));
        Assert.Empty(client.Aanroepen);
        Assert.False(client.HeeftVervoer);
    }

    [Fact]
    public async Task De_standaardregistratie_heeft_geen_weg_naar_MediaGuard()
    {
        Assert.IsType<GeenMediaGuardVervoer>(_h.Dienst<IMediaGuardVervoer>());
        var client = _h.Dienst<MediaGuardClient>();
        await client.VerversAsync(Ct);
        Assert.Equal(MgStatus.Onbekend, client.Beeld.Status);

        // De poller meet één keer en stopt dan: zonder weg loopt er geen timer.
        using var poller = new MediaGuardPoller(client, _h.Klok);
        await poller.StartAsync(Ct);
        await poller.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(10), Ct);
        Assert.True(poller.ExecuteTask.IsCompletedSuccessfully);
    }

    [Fact]
    public async Task Viewer_leest_alleen_de_velden_van_de_witte_lijst()
    {
        var mg = new NepMediaGuard();
        using var client = new MediaGuardClient(mg, _h.Klok);

        await client.VerversAsync(Ct);

        var beeld = client.Beeld;
        Assert.Equal((MgStatus.Ok, "gemeten"), (beeld.Status, beeld.Reden));
        Assert.Equal(_h.Klok.Nu, beeld.GemetenOp);
        Assert.True(beeld.EncoderBereikbaar);
        Assert.Equal([new MgLane("gpu", 1, 1, false), new MgLane("cpu", 0, 2, true)], beeld.Lanes);
        Assert.True(beeld.KijkpauzeActief);
        Assert.True(beeld.ServerVerbonden);
        Assert.Equal("emby", beeld.ServerSoort);
        Assert.Equal(["GET /api/v1/auth/me", "GET /api/v1/mediaserver/status", "GET /api/v1/app/status"], mg.Verzoeken);

        // Niets van wat MediaGuard over kijkers of titels zegt komt in het beeld terecht.
        var tekst = JsonSerializer.Serialize(beeld);
        Assert.DoesNotContain(Merk, tekst, StringComparison.Ordinal);
        Assert.DoesNotContain("192.0.2.", tekst, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Het_ritme_is_rol_en_koppeling_elk_uur_en_de_lanes_elke_ronde()
    {
        var mg = new NepMediaGuard();
        using var client = new MediaGuardClient(mg, _h.Klok);

        for (var ronde = 0; ronde < 3; ronde++)
        {
            await client.VerversAsync(Ct);
            _h.Klok.Nu = _h.Klok.Nu.AddSeconds(MediaGuardClient.PollSeconds);
        }

        Assert.Equal(1, client.Aanroepen["auth.me"]);
        Assert.Equal(1, client.Aanroepen["mediaserver.status"]);
        Assert.Equal(3, client.Aanroepen["app.status"]);

        _h.Klok.Nu = _h.Klok.Nu.AddMinutes(MediaGuardClient.LinkCheckMinutes);
        await client.VerversAsync(Ct);

        Assert.Equal(2, client.Aanroepen["auth.me"]);
        Assert.Equal(2, client.Aanroepen["mediaserver.status"]);
        Assert.Equal(4, client.Aanroepen["app.status"]);
        Assert.All(mg.Verzoeken, v => Assert.StartsWith("GET ", v, StringComparison.Ordinal));
        Assert.Equal(3, client.Aanroepen.Count);
    }

    [Theory]
    [InlineData("operator")]
    [InlineData("admin")]
    [InlineData("Viewer")]
    [InlineData("")]
    public async Task Een_andere_rol_dan_viewer_is_fail_closed(string rol)
    {
        var mg = new NepMediaGuard { Rol = rol };
        using var client = new MediaGuardClient(mg, _h.Klok);

        await client.VerversAsync(Ct);
        _h.Klok.Nu = _h.Klok.Nu.AddMinutes(30);
        await client.VerversAsync(Ct);

        Assert.Equal((MgStatus.Geweigerd, "rol_niet_viewer"), (client.Beeld.Status, client.Beeld.Reden));
        Assert.Empty(client.Beeld.Lanes);
        Assert.Equal(["GET /api/v1/auth/me"], mg.Verzoeken);

        // Na een uur wordt alleen de rol opnieuw gevraagd; is die dan viewer, dan mag de rest weer.
        _h.Klok.Nu = _h.Klok.Nu.AddMinutes(30);
        mg.Rol = "viewer";
        await client.VerversAsync(Ct);
        Assert.Equal(MgStatus.Ok, client.Beeld.Status);
    }

    [Fact]
    public async Task Een_viewer_die_later_een_andere_rol_krijgt_wordt_bij_de_uurcontrole_geweigerd()
    {
        var mg = new NepMediaGuard();
        using var client = new MediaGuardClient(mg, _h.Klok);
        await client.VerversAsync(Ct);
        Assert.Equal(MgStatus.Ok, client.Beeld.Status);

        mg.Rol = "operator";
        _h.Klok.Nu = _h.Klok.Nu.AddMinutes(MediaGuardClient.LinkCheckMinutes);
        mg.Verzoeken.Clear();
        await client.VerversAsync(Ct);

        Assert.Equal(MgStatus.Geweigerd, client.Beeld.Status);
        Assert.Equal(["GET /api/v1/auth/me"], mg.Verzoeken);
        Assert.Null(client.Beeld.KijkpauzeActief);
    }

    [Theory]
    [InlineData("fout")]
    [InlineData("500")]
    [InlineData("geen_json")]
    [InlineData("te_groot")]
    [InlineData("leeg")]
    public async Task Een_onbruikbaar_antwoord_is_onbereikbaar_en_nooit_ok(string soort)
    {
        var mg = new NepMediaGuard();
        using var client = new MediaGuardClient(mg, _h.Klok);
        await client.VerversAsync(Ct);
        Assert.Equal(MgStatus.Ok, client.Beeld.Status);

        mg.Storing = soort;
        _h.Klok.Nu = _h.Klok.Nu.AddSeconds(MediaGuardClient.PollSeconds);
        await client.VerversAsync(Ct);

        Assert.Equal(MgStatus.Onbereikbaar, client.Beeld.Status);
        Assert.Empty(client.Beeld.Lanes);
        Assert.Null(client.Beeld.EncoderBereikbaar);

        // Ook de rolcontrole zelf kan mislukken: dan is er geen uitspraak en wordt ze de volgende ronde opnieuw geprobeerd.
        _h.Klok.Nu = _h.Klok.Nu.AddMinutes(MediaGuardClient.LinkCheckMinutes);
        await client.VerversAsync(Ct);
        Assert.Equal(MgStatus.Onbereikbaar, client.Beeld.Status);
        mg.Storing = null;
        await client.VerversAsync(Ct);
        Assert.Equal(MgStatus.Ok, client.Beeld.Status);
    }

    [Fact]
    public void De_routewitte_lijst_bevat_alleen_lezen()
    {
        Assert.All(MediaGuardWitteLijst.Alle, r => Assert.StartsWith("/api/v1/", r.Pad, StringComparison.Ordinal));
        Assert.DoesNotContain(MediaGuardWitteLijst.Alle, r => r.Pad.Contains("control", StringComparison.OrdinalIgnoreCase));
        Assert.Equal(["audio.inspect"], MediaGuardWitteLijst.Alle.Where(r => r.Methode != "GET").Select(r => r.Id));
        Assert.Equal("POST", MediaGuardWitteLijst.Alle.Single(r => r.Id == "audio.inspect").Methode);
        Assert.Equal(MediaGuardWitteLijst.Alle.Count, MediaGuardWitteLijst.Alle.Select(r => r.Id).Distinct().Count());
        Assert.Equal(["app.status", "auth.me", "mediaserver.status"], MediaGuardWitteLijst.Alle.Where(r => r.Bruikbaar).Select(r => r.Id).Order());

        // Een route die er net zo uitziet maar niet het object van de lijst is, telt niet.
        Assert.False(MediaGuardWitteLijst.Bevat(new MgRoute("app.control", "POST", "/api/v1/app/control", ["x"])));
        Assert.False(MediaGuardWitteLijst.Bevat(MediaGuardWitteLijst.AppStatus with { Pad = "/api/v1/app/control" }));
        foreach (var verboden in new[] { "sessions", "reason", "actions", "tests", "last" })
        {
            Assert.DoesNotContain(MediaGuardWitteLijst.Alle.SelectMany(r => r.Velden), v => v.Split('.').Contains(verboden));
        }
    }

    [Fact]
    public void Het_veldenfilter_neemt_alleen_bladeren_van_de_witte_lijst_over()
    {
        var ruw = JsonNode.Parse(NepMediaGuard.Mediaserver)!;
        var uit = MediaGuardWitteLijst.Filter(ruw, MediaGuardWitteLijst.MediaserverStatus.Velden);

        Assert.Equal(
            """{"kind":"emby","url":"http://192.0.2.10:8096","connected":true,"hold":{"active":true},"subtitles":{"source":"bazarr","nl_wanted":3,"nl_auto":false,"missing":7}}""",
            uit.ToJsonString());

        // Een object of lijst op de plek van een blad vervalt; een verkeerde vorm geeft een leeg resultaat, geen fout.
        var raar = JsonNode.Parse("""{"kind":{"naam":"x"},"connected":[true],"hold":"nee","subtitles":{"missing":null}}""");
        Assert.Equal("""{"subtitles":{}}""", MediaGuardWitteLijst.Filter(raar, MediaGuardWitteLijst.MediaserverStatus.Velden).ToJsonString());
        Assert.Equal("{}", MediaGuardWitteLijst.Filter(JsonNode.Parse("[1,2]"), MediaGuardWitteLijst.AppStatus.Velden).ToJsonString());
        Assert.Equal("{}", MediaGuardWitteLijst.Filter(null, MediaGuardWitteLijst.AppStatus.Velden).ToJsonString());

        var lanes = MediaGuardWitteLijst.Filter(JsonNode.Parse(NepMediaGuard.App), MediaGuardWitteLijst.AppStatus.Velden);
        Assert.Equal(
            """{"encoder":{"reachable":true,"lanes":[{"lane":"gpu","running":1,"slots":1,"paused":false},{"lane":"cpu","running":0,"slots":2,"paused":true}]}}""",
            lanes.ToJsonString());
    }

    [Fact]
    public async Task Ruwe_antwoorden_staan_nergens_op_schijf()
    {
        var mg = new NepMediaGuard();
        using var client = new MediaGuardClient(mg, _h.Klok);
        _h.Schakelaars.Zet("devices", true);
        _h.Schakelaars.Zet("quality", true);
        _h.Koppel();
        await client.VerversAsync(Ct);
        await _h.RoepHub("connector.health", _h.Hub.Token(_h.Klok.Nu));
        Assert.Equal(MgStatus.Ok, client.Beeld.Status);

        foreach (var bestand in Directory.EnumerateFiles(_h.Map, "*", SearchOption.AllDirectories))
        {
            var inhoud = Encoding.Latin1.GetString(await File.ReadAllBytesAsync(bestand, Ct));
            Assert.DoesNotContain(Merk, inhoud, StringComparison.Ordinal);
            Assert.DoesNotContain("192.0.2.10", inhoud, StringComparison.Ordinal);
        }
    }

    [Fact]
    public async Task Health_meldt_alleen_vaste_woorden_en_is_eerlijk_over_onbekend()
    {
        _h.Koppel();
        JsonNode Check(Antwoord health) =>
            Assert.Single(health.Json!["checks"]!.AsArray(), c => c!["name"]!.GetValue<string>() == "mediaguard")!;
        string Token() => _h.Hub.Token(_h.Klok.Nu);

        // Geen module met batchwerk: "onbekend" is dan geen probleem en trekt de totaalstatus niet omlaag.
        var leeg = Check(await _h.RoepHub("connector.health", Token()));
        Assert.Equal("healthy", leeg["status"]!.GetValue<string>());
        Assert.Equal("""{"nodig":false,"koppeling":"onbekend","reden":"nog_niet_gemeten"}""", leeg["detail"]!.ToJsonString());

        // Quality heeft batchwerk: zonder MediaGuard-beeld is dat eerlijk "unknown".
        _h.Schakelaars.Zet("quality", true);
        await _h.Dienst<MediaGuardClient>().VerversAsync(Ct);
        var nodig = Check(await _h.RoepHub("connector.health", Token()));
        Assert.Equal("unknown", nodig["status"]!.GetValue<string>());
        Assert.Equal("""{"nodig":true,"koppeling":"onbekend","reden":"geen_route_via_hub"}""", nodig["detail"]!.ToJsonString());

        // Met een weg: ok → healthy, verkeerde rol → degraded, en een oude meting telt als onbekend.
        var mg = new NepMediaGuard();
        using var client = new MediaGuardClient(mg, _h.Klok);
        var bron = new MediaGuardHealthBron(client, _h.Dienst<ModuleRegistry>());
        Assert.Equal("unknown", bron.Checks(_h.Klok.Nu).Single()["status"]!.GetValue<string>());
        await client.VerversAsync(Ct);
        var ok = bron.Checks(_h.Klok.Nu).Single();
        Assert.Equal("healthy", ok["status"]!.GetValue<string>());
        Assert.Equal("""{"nodig":true,"koppeling":"ok","reden":"gemeten"}""", ok["detail"]!.ToJsonString());
        Assert.DoesNotContain("gpu", ok.ToJsonString(), StringComparison.Ordinal);

        mg.Rol = "operator";
        _h.Klok.Nu = _h.Klok.Nu.AddMinutes(MediaGuardClient.LinkCheckMinutes);
        await client.VerversAsync(Ct);
        var geweigerd = bron.Checks(_h.Klok.Nu).Single();
        Assert.Equal("degraded", geweigerd["status"]!.GetValue<string>());
        Assert.Equal("rol_niet_viewer", geweigerd["detail"]!["reden"]!.GetValue<string>());
    }

    /// <summary>Een nagebootste MediaGuard met antwoorden die méér bevatten dan Jelly Leon mag overnemen.</summary>
    private sealed class NepMediaGuard : IMediaGuardVervoer
    {
        public const string Mediaserver = """
            {"kind":"emby","url":"http://192.0.2.10:8096","connected":true,
             "hold":{"active":true,"reason":"Kijker-Zeldzaam kijkt Geheime-Titel-9917"},
             "sessions":[{"user":"Kijker-Zeldzaam","item":"Geheime-Titel-9917","client":"192.0.2.44"}],
             "actions":[{"naam":"Geheime-Titel-9917"}],"tests":{"laatste":"Geheime-Titel-9917"},"last":{"item":"Geheime-Titel-9917"},
             "subtitles":{"source":"bazarr","nl_wanted":3,"nl_auto":false,"missing":7,"titels":["Geheime-Titel-9917"]}}
            """;

        public const string App = """
            {"version":"9.9.9","api_key":"Geheime-Titel-9917","encoder":{"reachable":true,"host":"192.0.2.20",
             "lanes":[{"lane":"gpu","running":1,"slots":1,"paused":false,"reason_nl":"Geheime-Titel-9917","job":{"titel":"Geheime-Titel-9917"}},
                      {"lane":"cpu","running":0,"slots":2,"paused":true,"current":"Geheime-Titel-9917"}]}}
            """;

        public string Rol { get; set; } = "viewer";

        public string? Storing { get; set; }

        public List<string> Verzoeken { get; } = [];

        public bool Beschikbaar => true;

        public Task<MgAntwoord> VraagAsync(MgRoute route, CancellationToken annulering)
        {
            Verzoeken.Add(route.Methode + " " + route.Pad);
            var body = route.Id switch
            {
                "auth.me" => "{\"role\":\"" + Rol + "\",\"name\":\"Geheime-Titel-9917\",\"key_id\":\"k1\"}",
                "app.status" => App,
                "mediaserver.status" => Mediaserver,
                _ => throw new InvalidOperationException("De client vroeg een route op die niet bruikbaar is: " + route.Id),
            };
            return Storing switch
            {
                "fout" => Task.FromException<MgAntwoord>(new IOException("verbinding verbroken")),
                "500" => Task.FromResult(new MgAntwoord(500, Encoding.UTF8.GetBytes(body))),
                "geen_json" => Task.FromResult(new MgAntwoord(200, Encoding.UTF8.GetBytes("<html>"))),
                "te_groot" => Task.FromResult(new MgAntwoord(200, new byte[1048577])),
                "leeg" => Task.FromResult(new MgAntwoord(200, ReadOnlyMemory<byte>.Empty)),
                _ => Task.FromResult(new MgAntwoord(200, Encoding.UTF8.GetBytes(body))),
            };
        }
    }
}
