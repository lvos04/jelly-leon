using System;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Outbox;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;
using JlOutbox = Jellyfin.Plugin.JellyLeon.Core.Outbox.Outbox;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>De ene outbox (contract §7): envelopvorm, drie segmenten, en nooit titels, namen, paden of IP-adressen.</summary>
public sealed class OutboxTests : IDisposable
{
    private const string Opaak = "o_0123456789abcdef0123456789abcdef";
    private readonly Harnas _h = new();

    public void Dispose() => _h.Dispose();

    [Fact]
    public void Envelop_HeeftDeContractvorm()
    {
        var envelop = JlOutbox.Envelop("media.transcode.started", "playback_session", Opaak, new JsonObject { ["hardware"] = true }, _h.Klok.Nu);
        Assert.Empty(SchemaControle.Afwijkingen(OpenApiBouwer.Bouw(), "Event", envelop));
        Assert.Equal("2026-11-11T10:00:00Z", envelop["timestamp_utc"]!.GetValue<string>());
        Assert.Equal("jl-" + envelop["event_id"]!.GetValue<string>(), envelop["source_event_id"]!.GetValue<string>());
        Assert.Equal("internal", envelop["classification"]!.GetValue<string>());
        Assert.Null(envelop["payload_ref"]);
        Assert.Equal("system", envelop["actor"]!["type"]!.GetValue<string>());
        Assert.Equal(3, envelop["event_type"]!.GetValue<string>().Split('.').Length);

        // app.health.changed is het enige event buiten het domein media.
        Assert.NotNull(JlOutbox.Envelop("app.health.changed", "app", "jelly-leon", new JsonObject { ["status"] = "degraded" }, _h.Klok.Nu));
    }

    [Theory]
    [InlineData("media.transcode")]
    [InlineData("media.transcode.started.extra")]
    [InlineData("service.health.changed")]
    [InlineData("jellyleon.transcode.started")]
    [InlineData("Media.Transcode.Started")]
    [InlineData("media.transcode.gestart nu")]
    public void Envelop_WeigertAndereNamenDanDrieSegmentenInHetMediadomein(string eventType)
    {
        Assert.Throws<ArgumentException>(() => JlOutbox.Envelop(eventType, "playback_session", Opaak, [], _h.Klok.Nu));
    }

    [Theory]
    [InlineData("De Film (2024)")]
    [InlineData("Leon V")]
    [InlineData("/mnt/media/films/film.mkv")]
    [InlineData("192.168.1.10")]
    [InlineData("client-192.168.1.10")]
    [InlineData("11111111-2222-4333-8444-555555555555")]
    [InlineData("11111111222243338444555555555555")]
    [InlineData("TV Woonkamer")]
    [InlineData("C:\\media\\film.mkv")]
    public void Envelop_WeigertTitelsNamenPadenIpAdressenEnRuweIds(string waarde)
    {
        Assert.Throws<ArgumentException>(() => JlOutbox.Envelop("media.quality_scan.completed", "quality_scan", "scan-1", new JsonObject { ["veld"] = waarde }, _h.Klok.Nu));
        Assert.Throws<ArgumentException>(() => JlOutbox.Envelop("media.quality_scan.completed", "quality_scan", "scan-1", new JsonObject { ["diep"] = new JsonArray(new JsonObject { ["veld"] = waarde }) }, _h.Klok.Nu));
        Assert.Throws<ArgumentException>(() => JlOutbox.Envelop("media.quality_scan.completed", "quality_scan", waarde, [], _h.Klok.Nu));
        Assert.Throws<ArgumentException>(() => JlOutbox.Envelop("media.quality_scan.completed", "quality_scan", "scan-1", [], _h.Klok.Nu, "user", waarde));
        Assert.Throws<ArgumentException>(() => JlOutbox.Envelop("media.quality_scan.completed", "quality_scan", "scan-1", new JsonObject { [waarde] = 1 }, _h.Klok.Nu));
    }

    [Fact]
    public void Envelop_WeigertEenOnbekendeActorEnKortEenTeGrotePayloadIn()
    {
        Assert.Throws<ArgumentException>(() => JlOutbox.Envelop("media.quality_scan.completed", "quality_scan", "scan-1", [], _h.Klok.Nu, "beheerder", "x"));

        var groot = new JsonObject { ["codes"] = new JsonArray(Enumerable.Range(0, 4000).Select(i => (JsonNode)("code_" + i)).ToArray()) };
        var envelop = JlOutbox.Envelop("media.quality_scan.completed", "quality_scan", "scan-1", groot, _h.Klok.Nu);
        Assert.Equal("{\"_ingekort\":true}", envelop["payload"]!.ToJsonString());
        Assert.True(System.Text.Encoding.UTF8.GetByteCount(envelop.ToJsonString()) < JlOutbox.MaxPayloadBytes);
    }

    [Fact]
    public void InhoudsBewaker_WijstDePlekAan()
    {
        Assert.Null(InhoudsBewaker.EersteOvertreding(new JsonObject { ["aantal"] = 3, ["code"] = "audio_clipping", ["op"] = "2026-11-11T10:00:00Z", ["item"] = Opaak, ["leeg"] = null, ["aan"] = true }));
        var fout = new JsonObject { ["a"] = new JsonArray(1, new JsonObject { ["b"] = "Een Titel" }) };
        Assert.Equal("$.a[1].b", InhoudsBewaker.EersteOvertreding(fout));
        Assert.Equal("$.Naam", InhoudsBewaker.EersteOvertreding(new JsonObject { ["Naam"] = 1 }));
        Assert.False(InhoudsBewaker.VeiligeTekst("o_0123456789ABCDEF0123456789abcdef"));
        Assert.False(InhoudsBewaker.VeiligeTekst(new string('a', 65)));
    }

    [Fact]
    public void Outbox_LeestOplopendWistPerModuleEnBewaartDertigDagen()
    {
        var outbox = _h.Dienst<JlOutbox>();
        var a = outbox.Meld("quality", "media.quality_scan.completed", "quality_scan", "scan-1", new JsonObject { ["bestanden"] = 1 });
        var b = outbox.Meld("devices", "media.transcode.started", "playback_session", Opaak, new JsonObject { ["hardware"] = false });
        var c = outbox.Meld("quality", "media.quality_scan.completed", "quality_scan", "scan-2", new JsonObject { ["bestanden"] = 2 });

        var (eerste, cursor) = outbox.Lees(0, 2);
        Assert.Equal([a, b], eerste.Select(e => e["event_id"]!.GetValue<string>()));
        var (rest, eind) = outbox.Lees(cursor, 2);
        Assert.Equal([c], rest.Select(e => e["event_id"]!.GetValue<string>()));
        var (leeg, zelfde) = outbox.Lees(eind, 2);
        Assert.Empty(leeg);
        Assert.Equal(eind, zelfde);

        outbox.VerwijderModule("quality");
        Assert.Equal([b], outbox.Lees(0, 10).Events.Select(e => e["event_id"]!.GetValue<string>()));

        _h.Klok.Nu = _h.Klok.Nu.AddDays(31);
        var d = outbox.Meld("devices", "media.transcode.stopped", "playback_session", Opaak, new JsonObject { ["hardware"] = false, ["duur_s"] = 5 });
        Assert.Equal([d], outbox.Lees(0, 10).Events.Select(e => e["event_id"]!.GetValue<string>()));
    }

    [Fact]
    public void Outbox_SlaatEenOngeldigEventNietOp()
    {
        var outbox = _h.Dienst<JlOutbox>();
        Assert.Throws<ArgumentException>(() => outbox.Meld("devices", "media.transcode.started", "playback_session", "TV Woonkamer", []));
        Assert.Empty(outbox.Lees(0, 10).Events);
    }
}
