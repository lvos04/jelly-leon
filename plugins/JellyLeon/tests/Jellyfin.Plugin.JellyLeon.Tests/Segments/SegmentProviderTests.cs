using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Jellyfin.Database.Implementations.Enums;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Modules.Segments;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.MediaSegments;
using MediaBrowser.Model.Configuration;
using MediaBrowser.Model.MediaSegments;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Segments;

/// <summary>ABI, herhaalbare publicatie, grenzen en migratie op synthetische data.</summary>
public sealed class SegmentProviderTests
{
    [Fact]
    public async Task IdentiekeTijdcodesVanAndereProviderBlijvenBijPublicerenEnDepubliceren()
    {
        Assert.Equal("89c1fd4ffb135be83ede19aa4ba67b06", SegmentProvider.ProviderId);
        var video = new Movie { Id = Guid.NewGuid(), RunTimeTicks = 100 };
        Tijdvak vak = new(MediaSegmentType.Intro, 11, 32, "chapter", .9);
        var vreemd = SegmentProvider.MaakDto(video.Id, vak);
        var rijen = new Dictionary<Guid, (string Provider, MediaSegmentDto Rij)> { [vreemd.Id] = ("andere", vreemd) };
        var manager = new Mock<IMediaSegmentManager>(MockBehavior.Strict);
        manager.Setup(m => m.GetSupportedProviders(video)).Returns([(SegmentProvider.VasteNaam, SegmentProvider.ProviderId), ("andere", "vreemd")]);
        manager.Setup(m => m.GetSegmentsAsync(video, null, It.IsAny<LibraryOptions>(), true))
            .Returns((BaseItem _, IEnumerable<MediaSegmentType>? _, LibraryOptions opties, bool _) =>
                Task.FromResult(rijen.Values.Where(r => !opties.DisabledMediaSegmentProviders.Contains(r.Provider)).Select(r => r.Rij)));
        manager.Setup(m => m.CreateSegmentAsync(It.IsAny<MediaSegmentDto>(), SegmentProvider.ProviderId))
            .Returns((MediaSegmentDto s, string _) =>
            {
                rijen.Add(s.Id, (SegmentProvider.VasteNaam, s));
                return Task.FromResult(s);
            });
        manager.Setup(m => m.DeleteSegmentAsync(It.IsAny<Guid>())).Returns((Guid id) =>
        {
            Assert.NotEqual(vreemd.Id, id);
            Assert.True(rijen.Remove(id));
            return Task.CompletedTask;
        });

        var publicatie = new SegmentPublicatie(manager.Object);
        await Assert.ThrowsAsync<JlException>(() => publicatie.StemAf(video, [vak with { Type = MediaSegmentType.Unknown }]));
        Assert.Equal((1, 0), await publicatie.StemAf(video, [vak]));
        Assert.Equal(2, rijen.Count);
        Assert.Equal((0, 0), await publicatie.StemAf(video, [vak]));
        Assert.Equal((0, 1), await publicatie.StemAf(video, []));
        Assert.Same(vreemd, Assert.Single(rijen).Value.Rij);
    }

    [Fact]
    public async Task DubbelProviderIdStoptVoorDeEersteLezingOfWijziging()
    {
        var video = new Movie { Id = Guid.NewGuid(), RunTimeTicks = 100 };
        var manager = new Mock<IMediaSegmentManager>(MockBehavior.Strict);
        manager.Setup(m => m.GetSupportedProviders(video)).Returns([
            (SegmentProvider.VasteNaam, SegmentProvider.ProviderId),
            (SegmentProvider.VasteNaam.ToUpperInvariant(), SegmentProvider.ProviderId)]);
        var fout = await Assert.ThrowsAsync<JlException>(() => new SegmentPublicatie(manager.Object).StemAf(video, []));
        Assert.Equal("conflict", fout.Code);
        manager.Verify(m => m.GetSupportedProviders(video), Times.Once);
        manager.VerifyNoOtherCalls();
    }

    [Fact]
    public void HoofdstukkenZijnBegrensdGesorteerdEnOverlappenNiet()
    {
        var toeval = new Random(716);
        for (var proef = 0; proef < 1000; proef++)
        {
            var duur = toeval.Next(1, 1000);
            string?[] namen = ["intro", null, "Post credits", "end credits", "preview", "aflevering"];
            var invoer = Enumerable.Range(0, 25).Select(_ => ((long)toeval.Next(-5, duur + 10), namen[toeval.Next(namen.Length)])).ToList();
            var vakken = SegmentGegevens.UitHoofdstukken(invoer, duur);
            var item = new SegmentItem(Guid.NewGuid(), Guid.NewGuid(), null, null, null, duur, 0, null, vakken);
            item.Controleer();
            Assert.All(vakken, vak => Assert.True(vak.Start >= 0 && vak.Start < vak.Einde && vak.Einde <= duur));
            Assert.True(vakken.Zip(vakken.Skip(1)).All(paar => paar.First.Einde <= paar.Second.Start));
        }

        var duidelijk = SegmentGegevens.UitHoofdstukken([(0, "Opening"), (20, "Verhaal"), (80, "credits"), (90, "Post credits")], 100);
        Assert.Equal([(0L,20L), (80L,90L)], duidelijk.Select(v => (v.Start,v.Einde)));
    }

    [Fact]
    public void SchaduwEnHervalidatieBewarenMensenwerk()
    {
        using var h = new Harnas();
        var module = h.Dienst<SegmentsModule>();
        SegmentItem item = new(Guid.NewGuid(), Guid.NewGuid(), null, null, null, 100, 1, null, [new(MediaSegmentType.Intro, 3, 30, "manual", 1)], true);
        module.BewaarAnalyse(item);
        Assert.Empty(module.Gepubliceerd(item.ItemId));
        module.Verouder(item.ItemId);
        module.BewaarAnalyse(item with { Duur = 10, Mtime = 2, Bevestigd = false, Kandidaten = [] });
        var behouden = Assert.IsType<SegmentItem>(module.Vind(item.ItemId));
        Assert.True(behouden.Heruitlijnen);
        Assert.Equal(item.Kandidaten, behouden.Kandidaten);
        Assert.Throws<JlException>(() => module.BewaarAnalyse(item with { Kandidaten = [new(MediaSegmentType.Unknown, 4, 10, "chapter", 1)] }));
        Assert.Empty(module.Gepubliceerd(item.ItemId));
    }

    [Fact]
    public void MislukteMigratieBehoudtVorigeVersieEnCorrecties()
    {
        using var h = new Harnas();
        var paden = h.Dienst<JlPaths>();
        var pad = paden.ModuleDb("segments");
        const string schema = "CREATE TABLE correctie(waarde TEXT); INSERT INTO correctie VALUES('synthetisch');";
        var eerste = new JlDatabase(paden, pad, [schema]);
        Assert.Equal("synthetisch", eerste.Met(v => JlDatabase.Scalar(v, "SELECT waarde FROM correctie")));
        var poging = new JlDatabase(paden, pad, [schema, "CREATE TABLE nieuw(id INTEGER);", "ONGELDIGE MIGRATIE"]);
        Assert.Throws<JlException>(() => poging.Met(v => JlDatabase.Getal(v, "SELECT 1")));
        Assert.Equal(1, eerste.Met(v => JlDatabase.Getal(v, "PRAGMA user_version")));
        Assert.Equal(0, eerste.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM sqlite_master WHERE name='nieuw'")));
        Assert.Equal("synthetisch", eerste.Met(v => JlDatabase.Scalar(v, "SELECT waarde FROM correctie")));
        var kopie = Assert.Single(Directory.GetFiles(Path.GetDirectoryName(pad)!, "*.bak"));
        var herstel = new JlDatabase(paden, kopie, [schema]);
        Assert.Equal("ok", herstel.Met(v => JlDatabase.Scalar(v, "PRAGMA integrity_check")));
        Assert.Equal("synthetisch", herstel.Met(v => JlDatabase.Scalar(v, "SELECT waarde FROM correctie")));
    }
}
