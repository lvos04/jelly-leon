using System;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Outbox;
using Jellyfin.Plugin.JellyLeon.Modules.Devices;
using Jellyfin.Plugin.JellyLeon.Modules.Quality;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Model.Session;
using Xunit;
using JlOutbox = Jellyfin.Plugin.JellyLeon.Core.Outbox.Outbox;

namespace Jellyfin.Plugin.JellyLeon.Tests.Modules;

/// <summary>De twee prototypemodules (ADR-0016): eigen opslag, eigen events, één gedeelde kern.</summary>
public sealed class ModuleTests : IDisposable
{
    private readonly Harnas _h = new();
    private readonly Guid _gebruiker = Guid.Parse("12121212-3434-4565-8787-909090909090");

    public void Dispose() => _h.Dispose();

    private string[] Events() => _h.Dienst<JlOutbox>().Lees(0, 100).Events.Select(e => e["event_type"]!.GetValue<string>()).ToArray();

    [Fact]
    public void Devices_AlleenTranscodesGevenEenEvent()
    {
        var devices = _h.Dienst<DevicesModule>();
        var nu = _h.Klok.Nu;
        devices.RegistreerStart([_gebruiker], "TV", "s-direct", "direct_play", false, nu);
        devices.RegistreerStart([_gebruiker], "TV", "s-stream", "direct_stream", false, nu);
        Assert.Empty(Events());

        devices.RegistreerStart([_gebruiker, Guid.NewGuid()], "TV", "s-trans", "transcode", true, nu);
        devices.RegistreerStart([_gebruiker], "TV", "s-trans", "transcode", true, nu);
        Assert.Equal(["media.transcode.started"], Events());

        devices.RegistreerStop("s-direct", nu.AddSeconds(10));
        devices.RegistreerStop("s-onbekend", nu.AddSeconds(10));
        Assert.Single(Events());
        devices.RegistreerStop("s-trans", nu.AddSeconds(90));
        devices.RegistreerStop("s-trans", nu.AddSeconds(95));
        Assert.Equal(["media.transcode.started", "media.transcode.stopped"], Events());

        var gestopt = _h.Dienst<JlOutbox>().Lees(0, 100).Events[1];
        Assert.Equal(90, gestopt["payload"]!["duur_s"]!.GetValue<long>());
        Assert.True(gestopt["payload"]!["hardware"]!.GetValue<bool>());
        Assert.Equal("playback_session", gestopt["entity"]!["type"]!.GetValue<string>());
        Assert.Matches("^o_[0-9a-f]{32}$", gestopt["entity"]!["id"]!.GetValue<string>());

        var status = devices.Status(nu.AddSeconds(100));
        Assert.Equal(3, status["sessies"]!.GetValue<long>());
        Assert.Equal(1, status["actief"]!.GetValue<long>());
        Assert.Equal(1, status["transcodes"]!.GetValue<long>());
        Assert.Equal(30, status["bewaar_dagen"]!.GetValue<int>());
        Assert.Null(InhoudsBewaker.EersteOvertreding(status));
        Assert.Null(InhoudsBewaker.EersteOvertreding(devices.Exporteer()));
        Assert.Equal(3, devices.Exporteer()["sessies"]!.GetValue<long>());
    }

    [Fact]
    public void Devices_BewaartNietLangerDanIngesteld()
    {
        var devices = _h.Dienst<DevicesModule>();
        var nu = _h.Klok.Nu;
        devices.RegistreerStart([_gebruiker], "TV", "oud", "direct_play", false, nu);
        devices.RegistreerStart([_gebruiker], "TV", "nog-net", "direct_play", false, nu.AddDays(29));
        Assert.Equal(2, devices.TelGebruiker(_gebruiker));
        devices.RegistreerStart([_gebruiker], "TV", "nieuw", "direct_play", false, nu.AddDays(31));
        Assert.Equal(2, devices.TelGebruiker(_gebruiker));

        var (_, etag) = devices.LeesInstellingen();
        devices.SchrijfInstellingen(1, etag);
        devices.RegistreerStart([_gebruiker], "TV", "nieuwst", "direct_play", false, nu.AddDays(33));
        Assert.Equal(1, devices.TelGebruiker(_gebruiker));
    }

    [Theory]
    [InlineData(PlayMethod.Transcode, "transcode")]
    [InlineData(PlayMethod.DirectStream, "direct_stream")]
    [InlineData(PlayMethod.DirectPlay, "direct_play")]
    [InlineData(null, "direct_play")]
    public void Devices_VertaaltDeAfspeelmethode(PlayMethod? methode, string verwacht)
    {
        Assert.Equal(verwacht, DevicesListener.Methode(methode));
    }

    [Fact]
    public void Quality_BevindingenOnderdrukkenEnScanEvent()
    {
        var quality = _h.Dienst<QualityModule>();
        var nu = _h.Klok.Nu;
        var item = Guid.Parse("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee");
        Assert.True(quality.MeldBevinding(item, "audio_clipping", "waarschuwing", nu));
        Assert.False(quality.MeldBevinding(item, "audio_clipping", "waarschuwing", nu));
        Assert.True(quality.MeldBevinding(item, "ondertitel_niet_synchroon", "info", nu));
        Assert.True(quality.MeldBevinding(Guid.NewGuid(), "audio_clipping", "fout", nu));
        Assert.Throws<ArgumentException>(() => quality.MeldBevinding(item, "audio_clipping", "kritiek", nu));
        Assert.Throws<ArgumentException>(() => quality.MeldBevinding(item, "/media/films/film.mkv", "info", nu));
        Assert.Throws<ArgumentException>(() => quality.MeldBevinding(item, "Geluid kraakt in De Film", "info", nu));

        quality.Onderdruk(item, "audio_clipping", _gebruiker, nu);
        quality.Onderdruk(item, "audio_clipping", _gebruiker, nu);
        var samenvatting = Assert.Single(quality.Items("quality_summary", nu));
        Assert.Equal(3, samenvatting["bevindingen"]!.GetValue<long>());
        Assert.Equal(1, samenvatting["onderdrukt"]!.GetValue<long>());
        Assert.Equal(2, samenvatting["per_code"]!["audio_clipping"]!.GetValue<long>());
        Assert.Null(samenvatting["laatste_scan"]);
        var bevindingen = quality.Items("quality_finding", nu);
        Assert.Equal(3, bevindingen.Count);
        Assert.Equal([true, false, false], bevindingen.Select(b => b["onderdrukt"]!.GetValue<bool>()));
        Assert.Equal(quality.ItemVerwijzing(item), bevindingen[0]["item"]!.GetValue<string>());
        Assert.All(bevindingen, b => Assert.Null(InhoudsBewaker.EersteOvertreding(b)));

        Assert.Empty(Events());
        var id = quality.RondScanAf(120, 3, nu.AddMinutes(5));
        Assert.Equal(["media.quality_scan.completed"], Events());
        var gebeurtenis = _h.Dienst<JlOutbox>().Lees(0, 10).Events[0];
        Assert.Equal("scan-" + id, gebeurtenis["entity"]!["id"]!.GetValue<string>());
        Assert.Equal("{\"bestanden\":120,\"bevindingen\":3}", gebeurtenis["payload"]!.ToJsonString());
        Assert.Equal("2026-11-11T10:05:00Z", quality.Status(nu.AddMinutes(6))["laatste_scan"]!.GetValue<string>());
        Assert.Equal(1, quality.Status(nu.AddMinutes(6))["scans"]!.GetValue<long>());
        Assert.Null(InhoudsBewaker.EersteOvertreding(quality.Exporteer()));
        Assert.DoesNotContain(_gebruiker.ToString("N"), quality.Exporteer().ToJsonString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Modules_HebbenElkEenEigenDatabaseEnEigenInstellingen()
    {
        var devices = _h.Dienst<DevicesModule>();
        var quality = _h.Dienst<QualityModule>();
        devices.ControleerOpslag();
        quality.ControleerOpslag();
        Assert.True(System.IO.File.Exists(System.IO.Path.Combine(_h.Map, "data", "jelly-leon", "devices", "devices.db")));
        Assert.True(System.IO.File.Exists(System.IO.Path.Combine(_h.Map, "data", "jelly-leon", "quality", "quality.db")));

        var (_, etag) = devices.LeesInstellingen();
        devices.SchrijfInstellingen(7, etag);
        Assert.Equal(7, devices.LeesInstellingen().Waarde["bewaar_dagen"]!.GetValue<int>());
        Assert.Equal(90, quality.LeesInstellingen().Waarde["bewaar_dagen"]!.GetValue<int>());
        Assert.NotEqual(devices.LeesInstellingen().Etag, quality.LeesInstellingen().Etag);
    }

    [Fact]
    public void Register_WeigertDubbeleNamenTypenEnEvents()
    {
        var devices = _h.Dienst<DevicesModule>();
        var quality = _h.Dienst<QualityModule>();
        var register = new ModuleRegistry([devices, quality], _h.Schakelaars);
        Assert.Equal(["devices", "quality"], register.Alle.Select(m => m.Slug));
        Assert.Empty(register.Actief);
        _h.Schakelaars.Zet("quality", true);
        Assert.Equal(["quality"], register.Actief.Select(m => m.Slug));
        Assert.False(register.IsAan("devices"));
        Assert.False(register.IsAan("bestaat-niet"));

        Assert.Throws<InvalidOperationException>(() => new ModuleRegistry([devices, devices], _h.Schakelaars));
        Assert.Throws<InvalidOperationException>(() => new ModuleRegistry([devices, new Dubbel("anders", devices.ItemTypes[0], "media.x.y", "x.job")], _h.Schakelaars));
        Assert.Throws<InvalidOperationException>(() => new ModuleRegistry([devices, new Dubbel("anders", "iets", devices.EventTypes[0], "x.job")], _h.Schakelaars));
        Assert.Throws<InvalidOperationException>(() => new ModuleRegistry([quality, new Dubbel("anders", "iets", "media.x.y", quality.JobTypes[0])], _h.Schakelaars));
        Assert.Equal(2, new ModuleRegistry([devices, new Dubbel("anders", "iets", "media.x.y", "x.job")], _h.Schakelaars).Alle.Count);

        // Elke module declareert events met precies drie segmenten in het domein media.
        Assert.All(register.Alle.SelectMany(m => m.EventTypes), e =>
        {
            Assert.Equal(3, e.Split('.').Length);
            Assert.StartsWith("media.", e);
        });
    }

    private sealed class Dubbel(string slug, string itemType, string eventType, string jobType) : IJellyLeonModule
    {
        public string Slug => slug;

        public string Naam => slug;

        public System.Collections.Generic.IReadOnlyList<string> ItemTypes => [itemType];

        public System.Collections.Generic.IReadOnlyList<string> EventTypes => [eventType];

        public System.Collections.Generic.IReadOnlyList<string> JobTypes => [jobType];

        public System.Collections.Generic.IReadOnlyList<PersoonsgegevenRegel> Persoonsgegevens => [];

        public System.Collections.Generic.IReadOnlyList<JsonObject> Items(string type, DateTimeOffset nu) => [];

        public int VerwijderGebruiker(Guid gebruiker) => 0;

        public int TelGebruiker(Guid gebruiker) => 0;

        public void WisSporen()
        {
        }

        public void ControleerOpslag()
        {
        }

        public JsonObject Exporteer() => [];
    }
}
