using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Modules.Devices;
using Jellyfin.Plugin.JellyLeon.Modules.Quality;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;
using JlOutbox = Jellyfin.Plugin.JellyLeon.Core.Outbox.Outbox;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>De ene connector (contract §6): discover, health, items en events; alleen aantallen en ondoorzichtige ID's.</summary>
public sealed class ConnectorTests : IDisposable
{
    private static readonly JsonObject _openapi = OpenApiBouwer.Bouw();
    private readonly Harnas _h = new();

    public ConnectorTests()
    {
        _h.Koppel();
    }

    public void Dispose() => _h.Dispose();

    private string Token => _h.Hub.Token(_h.Klok.Nu);

    private static JsonNode Check(Antwoord health, string naam) =>
        Assert.Single(health.Json!["checks"]!.AsArray(), c => c!["name"]!.GetValue<string>() == naam)!;

    [Fact]
    public async Task Discover_NoemtAlleenWatAanStaat()
    {
        _h.Schakelaars.Zet("devices", true);
        _h.Schakelaars.Zet("quality", true);
        var beide = await _h.RoepHub("connector.discover", Token);
        Assert.Equal(200, beide.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Discover", beide.Json));
        Assert.Equal("no-store", beide.Kop.GetValueOrDefault("Cache-Control", "no-store"));
        var rechten = beide.Json!["permissions"]!.AsArray().Select(p => p!.GetValue<string>()).ToList();
        Assert.Equal(
            ["events:read", "health:read", "items:backups:read", "items:device:read", "items:playback_stats:read", "items:quality_finding:read", "items:quality_summary:read"],
            rechten.Order(StringComparer.Ordinal));
        Assert.Equal(["read"], beide.Json["capabilities"]!.AsArray().Select(c => c!.GetValue<string>()));
        Assert.Equal(200, beide.Json["limits"]!["max_page_size"]!.GetValue<int>());
        Assert.Equal(1048576, beide.Json["limits"]!["max_body_bytes"]!.GetValue<int>());
        Assert.Equal(900, beide.Json["limits"]!["max_age_s"]!["health"]!.GetValue<int>());

        _h.Schakelaars.Zet("quality", false);
        var zonder = await _h.RoepHub("connector.discover", Token);
        Assert.DoesNotContain(zonder.Json!["permissions"]!.AsArray(), p => p!.GetValue<string>().Contains("quality", StringComparison.Ordinal));
        var items = await _h.RoepHub("connector.items", Token, query: "type=quality_summary");
        Assert.Equal(422, items.Status);
        Assert.Equal("validation_error", items.Code);
        Assert.Equal("type", items.Json!["details"]!["fouten"]![0]!["veld"]!.GetValue<string>());
        Assert.Equal("onbekend_type", items.Json["details"]!["fouten"]![0]!["code"]!.GetValue<string>());

        // Een dienst-JWT van de Hub (de pollende Hub) krijgt hetzelfde antwoord.
        Assert.Equal(200, (await _h.RoepHub("connector.discover", _h.Hub.DienstToken(_h.Klok.Nu))).Status);
    }

    [Fact]
    public async Task Health_TotaalIsDeSlechtsteCheckEnDeWerkerIsNooitGespeeldGroen()
    {
        // Geen module aan en de server kent nog geen mediamappen: onbekend, niet "in orde".
        var leeg = await _h.RoepHub("connector.health", Token);
        Assert.Equal(200, leeg.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Health", leeg.Json));
        Assert.Equal("unknown", leeg.Json!["status"]!.GetValue<string>());
        Assert.Equal("media_mount_unknown", leeg.Json["reason_code"]!.GetValue<string>());
        Assert.Equal("healthy", Check(leeg, "database")["status"]!.GetValue<string>());
        var jobs = Check(leeg, "jobs");
        Assert.Equal("healthy", jobs["status"]!.GetValue<string>());
        Assert.Equal(0, jobs["detail"]!["wachtrij"]!.GetValue<long>());
        Assert.Equal(0, jobs["detail"]!["bezig"]!.GetValue<long>());
        Assert.True(jobs["detail"]!.AsObject().ContainsKey("laatste_job_klaar"));
        Assert.Equal("healthy", Check(leeg, "worker")["status"]!.GetValue<string>());
        Assert.False(Check(leeg, "worker")["detail"]!["nodig"]!.GetValue<bool>());
        Assert.DoesNotContain(leeg.Json["checks"]!.AsArray(), c => c!["name"]!.GetValue<string>().StartsWith("module.", StringComparison.Ordinal));

        // Devices heeft geen jobs: geen werker nodig.
        _h.Schakelaars.Zet("devices", true);
        var devices = await _h.RoepHub("connector.health", Token);
        Assert.Equal("healthy", Check(devices, "worker")["status"]!.GetValue<string>());
        Assert.Equal("healthy", Check(devices, "module.devices")["status"]!.GetValue<string>());

        // Quality heeft een jobtype; zonder werkerbewaker is de werker onbekend.
        _h.Schakelaars.Zet("quality", true);
        var quality = await _h.RoepHub("connector.health", Token);
        var werker = Check(quality, "worker");
        Assert.Equal("unknown", werker["status"]!.GetValue<string>());
        Assert.True(werker["detail"]!["nodig"]!.GetValue<bool>());
        Assert.Equal("werker_niet_beschikbaar", werker["detail"]!["reden"]!.GetValue<string>());
        Assert.Equal("unknown", quality.Json!["status"]!.GetValue<string>());

        // Een schrijfbare mediamap is een afwijking (media hoort alleen-lezen gekoppeld te zijn).
        _h.Media.Mappen.Add(_h.Map);
        var schrijfbaar = await _h.RoepHub("connector.health", Token);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Health", schrijfbaar.Json));
        var media = Check(schrijfbaar, "media_mount");
        Assert.Equal("degraded", media["status"]!.GetValue<string>());
        Assert.Equal("media_schrijfbaar", media["detail"]!["reden"]!.GetValue<string>());
        Assert.Equal(1, media["detail"]!["schrijfbaar"]!.GetValue<int>());
        Assert.Equal("degraded", schrijfbaar.Json!["status"]!.GetValue<string>());
        Assert.Equal("media_mount_degraded", schrijfbaar.Json["reason_code"]!.GetValue<string>());

        // Geen enkele check lekt een pad.
        Assert.DoesNotContain(_h.Map, schrijfbaar.Json.ToJsonString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Health_VerouderdeMetingWordtOnbekendEnEenEchteWerkercheckVervangtDeStandaard()
    {
        var nu = _h.Klok.Nu;
        _h.Schakelaars.Zet("quality", true);
        ConnectorService Met(params JsonObject[] checks) => new(
            _h.Dienst<ModuleRegistry>(), _h.Dienst<JlOutbox>(), _h.Dienst<CoreDatabase>(), _h.Dienst<JlPaths>(), _h.Media, [new NepBron(checks)]);
        static JsonNode Zoek(JsonObject health, string naam) => Assert.Single(health["checks"]!.AsArray(), c => c!["name"]!.GetValue<string>() == naam)!;

        var vers = Met(ConnectorService.Check("worker", "healthy", nu.AddSeconds(-900))).Health(nu);
        Assert.Equal("healthy", Zoek(vers, "worker")["status"]!.GetValue<string>());

        var oud = Met(ConnectorService.Check("worker", "healthy", nu.AddSeconds(-901), new JsonObject { ["pid"] = 1 })).Health(nu);
        Assert.Equal("unknown", Zoek(oud, "worker")["status"]!.GetValue<string>());
        Assert.Equal("meting_verouderd", Zoek(oud, "worker")["detail"]!["reden"]!.GetValue<string>());

        var plat = Met(ConnectorService.Check("worker", "down", nu), ConnectorService.Check("quality_mediaguard", "unknown", nu)).Health(nu);
        Assert.Equal("down", plat["status"]!.GetValue<string>());
        Assert.Equal("worker_down", plat["reason_code"]!.GetValue<string>());
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Health", plat));
    }

    [Fact]
    public async Task Items_AlleenAantallenEnOndoorzichtigeIdsMetPaginering()
    {
        _h.Schakelaars.Zet("devices", true);
        _h.Schakelaars.Zet("quality", true);
        var gebruiker = Guid.Parse("12121212-3434-4565-8787-909090909090");
        var item = Guid.Parse("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee");
        var devices = _h.Dienst<DevicesModule>();
        devices.RegistreerStart([gebruiker], "TV Woonkamer", "sessie-1", "transcode", true, _h.Klok.Nu);
        devices.RegistreerStart([gebruiker], "Telefoon van Leon", "sessie-2", "direct_play", false, _h.Klok.Nu);
        devices.RegistreerStart([gebruiker], "192.168.1.10", "sessie-3", "direct_stream", false, _h.Klok.Nu);
        var quality = _h.Dienst<QualityModule>();
        quality.MeldBevinding(item, "audio_clipping", "waarschuwing", _h.Klok.Nu);
        quality.Onderdruk(item, "audio_clipping", gebruiker, _h.Klok.Nu);

        var teksten = new List<string>();
        foreach (var type in new[] { "playback_stats", "device", "quality_summary", "quality_finding", "backups" })
        {
            var antwoord = await _h.RoepHub("connector.items", Token, query: "type=" + type);
            Assert.Equal(200, antwoord.Status);
            Assert.Empty(SchemaControle.Afwijkingen(_openapi, "ItemsPagina", antwoord.Json));
            Assert.Equal(type, antwoord.Json!["type"]!.GetValue<string>());
            Assert.NotEmpty(antwoord.Json["items"]!.AsArray());
            teksten.Add(antwoord.Json.ToJsonString());
        }

        foreach (var tekst in teksten)
        {
            foreach (var verboden in new[] { "TV Woonkamer", "Leon", "192.168.1.10", "sessie-1", gebruiker.ToString("N"), gebruiker.ToString("D"), item.ToString("N"), item.ToString("D"), _h.Map })
            {
                Assert.DoesNotContain(verboden, tekst, StringComparison.OrdinalIgnoreCase);
            }
        }

        var stats = (await _h.RoepHub("connector.items", Token, query: "type=playback_stats")).Json!["items"]![0]!;
        Assert.Equal(3, stats["sessies"]!.GetValue<long>());
        Assert.Equal(1, stats["transcodes"]!.GetValue<long>());
        Assert.Equal(1, stats["hardware_transcodes"]!.GetValue<long>());
        Assert.Equal(1, stats["direct_play"]!.GetValue<long>());
        Assert.Equal(1, stats["direct_stream"]!.GetValue<long>());

        var bevinding = (await _h.RoepHub("connector.items", Token, query: "type=quality_finding")).Json!["items"]![0]!;
        Assert.Matches("^o_[0-9a-f]{32}$", bevinding["item"]!.GetValue<string>());
        Assert.True(bevinding["onderdrukt"]!.GetValue<bool>());

        var backups = (await _h.RoepHub("connector.items", Token, query: "type=backups")).Json!["items"]!.AsArray();
        Assert.Equal(["core", "devices", "quality"], backups.Select(b => b!["id"]!.GetValue<string>()));
        Assert.All(backups, b => Assert.Equal("onbekend", b!["dekking"]!.GetValue<string>()));

        // Paginering: drie apparaten, twee per pagina.
        var eerste = await _h.RoepHub("connector.items", Token, query: "type=device&limit=2");
        Assert.Equal(2, eerste.Json!["items"]!.AsArray().Count);
        Assert.Equal("2", eerste.Json["next_cursor"]!.GetValue<string>());
        Assert.All(eerste.Json["items"]!.AsArray(), d => Assert.Matches("^o_[0-9a-f]{32}$", d!["id"]!.GetValue<string>()));
        var tweede = await _h.RoepHub("connector.items", Token, query: "type=device&limit=2&cursor=2");
        Assert.Single(tweede.Json!["items"]!.AsArray());
        Assert.Null(tweede.Json["next_cursor"]);

        foreach (var (query, veld, code) in new[]
        {
            ("limit=2", "type", "onbekend_type"),
            ("type=films", "type", "onbekend_type"),
            ("type=device&cursor=abc", "cursor", "cursor_ongeldig"),
            ("type=device&cursor=-1", "cursor", "cursor_ongeldig"),
            ("type=device&cursor=1234567890123456789", "cursor", "cursor_ongeldig"),
            ("type=device&limit=0", "limit", "bereik"),
            ("type=device&limit=201", "limit", "bereik"),
            ("type=device&limit=veel", "limit", "bereik"),
        })
        {
            var fout = await _h.RoepHub("connector.items", Token, query: query);
            Assert.Equal(422, fout.Status);
            Assert.Equal("validation_error", fout.Code);
            Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Fout", fout.Json));
            Assert.Equal(veld, fout.Json!["details"]!["fouten"]![0]!["veld"]!.GetValue<string>());
            Assert.Equal(code, fout.Json["details"]!["fouten"]![0]!["code"]!.GetValue<string>());
        }
    }

    [Fact]
    public async Task Events_DeHubPoltMetEenCursorEnElkEventHeeftDrieSegmenten()
    {
        _h.Schakelaars.Zet("devices", true);
        _h.Schakelaars.Zet("quality", true);
        var gebruiker = Guid.Parse("12121212-3434-4565-8787-909090909090");
        var devices = _h.Dienst<DevicesModule>();
        devices.RegistreerStart([gebruiker], "TV Woonkamer", "sessie-1", "transcode", true, _h.Klok.Nu);
        _h.Klok.Nu = _h.Klok.Nu.AddSeconds(42);
        devices.RegistreerStop("sessie-1", _h.Klok.Nu);
        _h.Dienst<QualityModule>().RondScanAf(12, 3, _h.Klok.Nu);

        var alles = await _h.RoepHub("connector.events", Token);
        Assert.Equal(200, alles.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "EventsPagina", alles.Json));
        var events = alles.Json!["items"]!.AsArray();
        Assert.Equal(
            ["media.transcode.started", "media.transcode.stopped", "media.quality_scan.completed"],
            events.Select(e => e!["event_type"]!.GetValue<string>()));
        Assert.All(events, e => Assert.Equal(3, e!["event_type"]!.GetValue<string>().Split('.').Length));
        Assert.All(events, e => Assert.Equal("jelly-leon", e!["source_app"]!.GetValue<string>()));
        Assert.Equal(42, events[1]!["payload"]!["duur_s"]!.GetValue<long>());
        Assert.Equal(12, events[2]!["payload"]!["bestanden"]!.GetValue<int>());
        var declared = _h.Dienst<ModuleRegistry>().Alle.SelectMany(m => m.EventTypes).ToHashSet(StringComparer.Ordinal);
        Assert.All(events, e => Assert.Contains(e!["event_type"]!.GetValue<string>(), declared));
        foreach (var verboden in new[] { "TV Woonkamer", "sessie-1", gebruiker.ToString("N"), gebruiker.ToString("D") })
        {
            Assert.DoesNotContain(verboden, alles.Json.ToJsonString(), StringComparison.OrdinalIgnoreCase);
        }

        // Pollen: één per keer, daarna dezelfde cursor zolang er niets nieuws is.
        var eerste = await _h.RoepHub("connector.events", Token, query: "limit=1");
        var cursor = eerste.Json!["next_cursor"]!.GetValue<string>();
        Assert.Equal("media.transcode.started", eerste.Json["items"]![0]!["event_type"]!.GetValue<string>());
        var rest = await _h.RoepHub("connector.events", Token, query: "cursor=" + cursor);
        Assert.Equal(2, rest.Json!["items"]!.AsArray().Count);
        var eind = rest.Json["next_cursor"]!.GetValue<string>();
        var niets = await _h.RoepHub("connector.events", Token, query: "cursor=" + eind);
        Assert.Empty(niets.Json!["items"]!.AsArray());
        Assert.Equal(eind, niets.Json["next_cursor"]!.GetValue<string>());

        Assert.Equal(422, (await _h.RoepHub("connector.events", Token, query: "cursor=x")).Status);
        Assert.Equal(422, (await _h.RoepHub("connector.events", Token, query: "limit=500")).Status);
    }

    [Fact]
    public async Task Connector_WeigertEenGewoneServeraanmelding()
    {
        // Een Jellyfin-sessie of API-sleutel is op /connector/v1 geen geldig bewijs.
        var antwoord = await _h.Roep("connector.health", kop: ["Authorization: MediaBrowser Token=\"abc\""]);
        Assert.Equal(401, antwoord.Status);
        Assert.Equal("invalid_token", antwoord.Reden);
        var zonder = await _h.Roep("connector.items", query: "type=backups");
        Assert.Equal(401, zonder.Status);
    }

    private sealed class NepBron(JsonObject[] checks) : IHealthBron
    {
        public IEnumerable<JsonObject> Checks(DateTimeOffset nu) => checks.Select(c => (JsonObject)c.DeepClone());
    }
}
