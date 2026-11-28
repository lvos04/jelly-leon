using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Database.Implementations.Enums;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Media;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Modules.Segments;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.MediaSegments;
using MediaBrowser.Model;
using MediaBrowser.Model.Entities;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Segments;

/// <summary>JLT-56 in de plugin met tijdelijke SQLite, gesimuleerde bibliotheek en werkelijke routefilters.</summary>
public sealed class SegmentBeheerTests : IDisposable
{
    private readonly Harnas _h = new();
    private readonly Guid _bib = Guid.NewGuid();
    private readonly Guid _serie = Guid.NewGuid();
    private SegmentsModule Module => _h.Dienst<SegmentsModule>();
    private SegmentItem Nieuw(int ep = 1) => new(Guid.NewGuid(), _bib, _serie, 1, ep, 100, 12345,
        SegmentGegevens.Hash("synthetisch-" + ep), [new(MediaSegmentType.Intro, 10, 30, "chapter", .9)]);
    private void Aan() => _h.Schakelaars.Zet("segments", true);
    private static string[] Sleutel() => ["Idempotency-Key: " + Guid.NewGuid().ToString("D")];

    [Fact]
    public void SteekproefVraagtDrieVerschillendeAfleveringenPerSeizoenEnWeigertHints()
    {
        var eerste = Nieuw() with { Bevestigd = true };
        var tweede = Nieuw(2) with { Bevestigd = true };
        var derde = Nieuw(3) with { Bevestigd = true, Kandidaten = [new(MediaSegmentType.Intro, 10, 30, "hint", 1)] };
        foreach (var i in new[] { eerste, tweede, eerste with { ItemId = Guid.NewGuid() } })
        {
            Module.BewaarAnalyse(i);
        }

        var fout = Assert.Throws<JlException>(() => Module.LegPublicatieVast(_bib, null, "published", Module.Versie, null, "beheer", _h.Klok.Nu));
        Assert.Equal("qc_sample_incomplete", fout.Details["reason"]!.GetValue<string>());
        Assert.Empty(Module.Gepubliceerd(eerste.ItemId));
        Module.BewaarAnalyse(derde);
        Module.LegPublicatieVast(_bib, null, "published", Module.Versie, null, "beheer", _h.Klok.Nu);
        Assert.Equal(eerste.Kandidaten, Module.Gepubliceerd(eerste.ItemId));
        Assert.Empty(Module.Gepubliceerd(derde.ItemId));
        Assert.Equal(0, SegmentsModule.Steekproef([eerste, tweede, derde, Nieuw() with { Seizoen = 2 }]));
    }

    [Fact]
    public async Task ProviderLeestAlleenEigenOpslagEnRespecteertBibliotheekEnSchakelaar()
    {
        var item = Nieuw();
        var video = new Movie { Id = item.ItemId };
        var map = new Folder { Id = _bib };
        _h.Bibliotheek.Setup(b => b.GetCollectionFolders(video)).Returns([map]);
        var provider = _h.Dienst<IMediaSegmentProvider>();
        var request = new MediaSegmentGenerationRequest { ItemId = item.ItemId, ExistingSegments = [] };
        Assert.False(await provider.Supports(video));
        Assert.False(Module.HeeftDatabase);
        Aan();
        Assert.False(await provider.Supports(video));
        Module.BewaarAnalyse(item);
        Module.LegPublicatieVast(_bib, null, "shadow", Module.Versie, null, "beheer", _h.Klok.Nu);
        Assert.True(await provider.Supports(video));
        Assert.False(await provider.Supports(map));
        Assert.Empty(await provider.GetMediaSegments(request, TestContext.Current.CancellationToken));
        Module.LegPublicatieVast(_bib, null, "published", Module.Versie, "menselijke controle", "beheer", _h.Klok.Nu);
        Assert.Single(await provider.GetMediaSegments(request, TestContext.Current.CancellationToken));
        _h.Hoofdstukken.VerifyNoOtherCalls();
        Module.AllesIntrekken();
        Assert.Empty(await provider.GetMediaSegments(request, TestContext.Current.CancellationToken));
        Assert.Equal(item.Kandidaten, Module.Vind(item.ItemId)!.Kandidaten);
    }

    [Fact]
    public async Task VerborgenItemEnOntbrekendeRolWordenDoorDeWerkelijkeRouteGeweigerd()
    {
        var item = Nieuw();
        var video = new Movie { Id = item.ItemId, RunTimeTicks = item.Duur, DateModified = new DateTime(item.Mtime, DateTimeKind.Utc) };
        var pad = new Dictionary<string, string> { ["itemId"] = item.ItemId.ToString() };
        var gebruiker = Guid.NewGuid();
        _h.Sessies.Wie = new SessieIdentiteit(gebruiker, false, false);
        _h.Gebruikers.Setup(g => g.GetUserById(gebruiker)).Returns((Jellyfin.Database.Implementations.Entities.User?)null);
        Assert.Equal(404, (await _h.Roep("segments.item", pad: pad)).Status);
        Aan();
        Assert.Equal(404, (await _h.Roep("segments.item", pad: pad, query: "view=candidate")).Status);
        var account = new Jellyfin.Database.Implementations.Entities.User("fixture", "fixture", "fixture") { Id = gebruiker };
        _h.Gebruikers.Setup(g => g.GetUserById(gebruiker)).Returns(account);
        Assert.Equal(404, (await _h.Roep("segments.item", pad: pad)).Status);
        _h.Bibliotheek.Setup(b => b.GetItemById<Video>(item.ItemId, account)).Returns(video);
        _h.Bibliotheek.Setup(b => b.GetCollectionFolders(video)).Returns([new Folder { Id = _bib }]);
        Assert.Equal(403, (await _h.Roep("segments.item", pad: pad, query: "view=candidate")).Status);
        Assert.Equal(403, (await _h.Roep("segments.export")).Status);
        var kijker = await _h.Roep("segments.item", pad: pad);
        Assert.Equal(200, kijker.Status);
        Assert.False(kijker.Json!.AsObject().ContainsKey("evidence"));
        _h.Schakelaars.Editors.Add(gebruiker);
        Assert.Equal(200, (await _h.Roep("segments.item", pad: pad, query: "view=candidate")).Status);
        _h.Sessies.Wie = new SessieIdentiteit(gebruiker, false, true);
        Assert.Equal("kid_profile", (await _h.Roep("segments.item", pad: pad, query: "view=candidate")).Reden);
        _h.Sessies.Wie = null;
        Assert.Equal(401, (await _h.Roep("segments.item", pad: pad)).Status);
    }

    [Fact]
    public async Task ImportIsToevoegendPersoonsvrijEnVerwerptVerlopenEnVerouderdeVoorbeelden()
    {
        Aan();
        var item = Nieuw() with { Bevestigd = true };
        Module.BewaarAnalyse(item);
        var export = await _h.Roep("segments.export");
        Assert.Equal(200, export.Status);
        var inhoud = export.Json!.ToJsonString();
        Assert.DoesNotContain(_h.Sessies.Wie!.GebruikerId!.Value.ToString(), inhoud, StringComparison.OrdinalIgnoreCase);
        using var leeg = new Harnas();
        leeg.Schakelaars.Zet("segments", true);
        var preview = await leeg.Roep("segments.import.preview", inhoud);
        Assert.Equal(200, preview.Status);
        Assert.Empty(leeg.Dienst<SegmentsModule>().Selectie());
        var hash = preview.Json!["preview_hash"]!.GetValue<string>();
        var body = new JsonObject { ["preview_hash"] = hash }.ToJsonString();
        Assert.Equal(400, (await leeg.Roep("segments.import.apply", body)).Status);
        var kop = Sleutel();
        Assert.Equal(200, (await leeg.Roep("segments.import.apply", body, kop)).Status);
        Assert.Equal("true", (await leeg.Roep("segments.import.apply", body, kop)).Kop["Idempotent-Replay"]);
        var na = await leeg.Roep("segments.export");
        Assert.True(JsonNode.DeepEquals(export.Json["items"], na.Json!["items"]));
        Assert.Empty(leeg.Dienst<SegmentsModule>().Gepubliceerd(item.ItemId));
        var p = Module.OnthoudImport(export.Json.AsObject(), "actor", _h.Klok.Nu);
        Assert.Throws<JlException>(() => Module.PasImportToe(p["preview_hash"]!.GetValue<string>(), "andere", _h.Klok.Nu));
        Assert.Throws<JlException>(() => Module.PasImportToe(p["preview_hash"]!.GetValue<string>(), "actor", _h.Klok.Nu.AddMinutes(15)));
        Module.BewaarAnalyse(Nieuw(2));
        Assert.Throws<JlException>(() => Module.PasImportToe(p["preview_hash"]!.GetValue<string>(), "actor", _h.Klok.Nu));
        var ongeldig = export.Json.DeepClone();
        ongeldig["items"]![0]!["gebruiker"] = Guid.NewGuid();
        Assert.Equal(422, (await _h.Roep("segments.import.preview", ongeldig.ToJsonString())).Status);
    }

    [Fact]
    public void MassaleWezenBevriezenEnOpruimenVraagtRecentePassendeExport()
    {
        var set = Enumerable.Range(1, 100).Select(i => Nieuw(i)).ToArray();
        foreach (var item in set)
        {
            Module.BewaarAnalyse(item);
        }

        Module.VerwerkWezen(set.Take(5).Select(i => i.ItemId).ToHashSet(), _h.Klok.Nu);
        Assert.False(Module.Bevroren);
        Module.VerwerkWezen(new HashSet<Guid> { set[5].ItemId }, _h.Klok.Nu.AddMinutes(5));
        Assert.True(Module.Bevroren);
        Assert.Equal(100, Module.Selectie().Count);
        var exp = Module.Exporteer(_bib, _h.Klok.Nu);
        var exportId = exp["export_id"]!.GetValue<Guid>();
        Assert.Equal("orphans_frozen", Assert.Throws<JlException>(() => Module.RuimWezen(exportId, true, null, "beheer", _h.Klok.Nu)).Details["reason"]!.GetValue<string>());
        Module.Ontdooi("synthetische controle", "beheer", _h.Klok.Nu);
        Assert.Throws<JlException>(() => Module.RuimWezen(exportId, true, null, "beheer", _h.Klok.Nu.AddHours(25)));
        var voorbeeld = Module.RuimWezen(exportId, true, null, "beheer", _h.Klok.Nu);
        Assert.Equal(6, voorbeeld["would_delete"]!.GetValue<int>());
        Assert.Throws<JlException>(() => Module.RuimWezen(exportId, false, "verouderd", "beheer", _h.Klok.Nu));
        Assert.Equal(100, Module.Selectie().Count);
        Module.RuimWezen(exportId, false, voorbeeld["preview_hash"]!.GetValue<string>(), "beheer", _h.Klok.Nu);
        Assert.Equal(94, Module.Selectie().Count);
        Assert.True(OrphanBreaker.MoetBevriezen(5000, 51));
    }

    [Fact]
    public async Task CacheOpruimenBewijstBehoudVanCorrectieEnPublicatie()
    {
        Aan();
        var item = Nieuw() with { Bevestigd = true };
        Module.BewaarAnalyse(item);
        Module.LegPublicatieVast(_bib, null, "published", Module.Versie, "Bevestigde proef", "beheer", _h.Klok.Nu);
        var versie = Module.Versie;
        var map = Path.Combine(_h.Dienst<JlPaths>().CacheRoot, "segments");
        Directory.CreateDirectory(map);
        var eigen = Path.Combine(map, item.ItemId.ToString("N") + ".features");
        var ander = Path.Combine(map, Guid.NewGuid().ToString("N") + ".features");
        await File.WriteAllTextAsync(eigen, "eigen cache", TestContext.Current.CancellationToken);
        await File.WriteAllTextAsync(ander, "tweede cache", TestContext.Current.CancellationToken);

        var provider = Assert.Single(_h.Dienst<IEnumerable<IMediaSegmentProvider>>().OfType<SegmentProvider>());
        await provider.CleanupExtractedData(item.ItemId, TestContext.Current.CancellationToken);

        Assert.False(File.Exists(eigen));
        Assert.Equal("tweede cache", await File.ReadAllTextAsync(ander, TestContext.Current.CancellationToken));
        Assert.Equal(versie, Module.Versie);
        Assert.Equal(item.Kandidaten, Module.Gepubliceerd(item.ItemId));
        Assert.False(Module.Vind(item.ItemId)!.Heruitlijnen);
        Module.BewaarAnalyse(item with { Duur = 12, Kandidaten = [] });
        Assert.True(Module.Vind(item.ItemId)!.Heruitlijnen);
        Assert.Equal(item.Kandidaten, Module.Vind(item.ItemId)!.Kandidaten);
        Assert.Empty(Module.Gepubliceerd(item.ItemId));
    }

    [Fact]
    public void PadwisselEnTerugzettenBewarenMenselijkeGrenzenInReview()
    {
        var item = Nieuw() with { Bevestigd = true };
        Module.BewaarAnalyse(item);
        Module.VerwerkWezen(new HashSet<Guid> { item.ItemId }, _h.Klok.Nu);
        Module.Ontdooi("bibliotheek hersteld", "beheer", _h.Klok.Nu);
        var nieuw = item with { ItemId = Guid.NewGuid(), Kandidaten = [], Bevestigd = false, Mtime = item.Mtime + 1 };
        Module.BewaarAnalyse(nieuw);
        var herstel = Assert.Single(Module.Selectie());
        Assert.Equal(nieuw.ItemId, herstel.ItemId);
        Assert.Equal(item.Kandidaten, herstel.Kandidaten);
        Assert.True(herstel.Heruitlijnen);
        Assert.Empty(Module.Gepubliceerd(nieuw.ItemId));
        Module.VerwerkWezen(new HashSet<Guid> { nieuw.ItemId }, _h.Klok.Nu);
        Module.Ontdooi("item terug", "beheer", _h.Klok.Nu);
        Module.BewaarAnalyse(nieuw);
        Assert.Equal(item.Kandidaten, Assert.Single(Module.Selectie()).Kandidaten);
    }

    [Fact]
    public async Task SchrijfbareMountStartGeenAnalyseEnBewaartCorpus()
    {
        Aan();
        var map = Path.Combine(_h.Map, "synthetisch");
        Directory.CreateDirectory(map);
        var bestand = Path.Combine(map, "aflevering");
        await File.WriteAllBytesAsync(bestand, [8, 13, 21], TestContext.Current.CancellationToken);
        var voor = SHA256.HashData(await File.ReadAllBytesAsync(bestand, TestContext.Current.CancellationToken));
        _h.Bibliotheek.Setup(b => b.GetVirtualFolders()).Returns([new VirtualFolderInfo { ItemId = _bib.ToString(), Locations = [map] }]);
        Module.LegPublicatieVast(_bib, null, "shadow", Module.Versie, null, "beheer", _h.Klok.Nu);
        await _h.Dienst<SegmentDienst>().Controleer(TestContext.Current.CancellationToken);
        _h.Bibliotheek.Verify(b => b.GetItemList(It.IsAny<InternalItemsQuery>()), Times.Never);
        _h.Hoofdstukken.VerifyNoOtherCalls();
        Assert.Equal("down", _h.Dienst<SegmentDienst>().Status()["health"]!.GetValue<string>());
        Assert.Equal(voor, SHA256.HashData(await File.ReadAllBytesAsync(bestand, TestContext.Current.CancellationToken)));
    }

    /// <inheritdoc />
    public void Dispose() => _h.Dispose();
}
