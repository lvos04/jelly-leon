using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Data.Enums;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Plugin.JellyLeon.Configuration;
using Jellyfin.Plugin.JellyLeon.Modules.Recommendations;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.TV;
using MediaBrowser.Model.Configuration;
using MediaBrowser.Model.Entities;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Recommendations;

public sealed class AanbevelingsBibliotheekTests
{
    [Fact]
    public async Task AlleenDeGekozenProviderLeestNaDeModulekeuze()
    {
        var film = new Movie { Id = Guid.NewGuid() };
        var serie = new Series { Id = Guid.NewGuid() };
        var type = new TypeOptions { Type = "Movie" };
        var opties = new LibraryOptions { TypeOptions = [type] };
        var bibliotheek = new Mock<ILibraryManager>(MockBehavior.Strict);
        bibliotheek.Setup(b => b.GetLibraryOptions(It.IsAny<BaseItem>())).Returns(opties);
        var adapter = new AanbevelingsBibliotheek(bibliotheek.Object, Mock.Of<IUserDataManager>(), Mock.Of<ITVSeriesManager>(),
            TimeProvider.System, () => new AnimeOptions());
        var lezingen = 0;
        var provider = new SimilarProvider(() => true, adapter.SimilarIngesteld, (_, _, _) => { lezingen++; return [film]; });
        var vraag = new SimilarItemsQuery { User = new User("test", "lokaal", "lokaal"), Limit = 1 };
        Assert.Empty(await provider.GetSimilarItemsAsync(film, vraag, CancellationToken.None));
        type.SimilarItemProviders = ["JELLY LEON"];
        Assert.Single(await provider.GetSimilarItemsAsync(film, vraag, CancellationToken.None));
        type.SimilarItemProviderOrder = ["Local Genre/Tag"];
        Assert.Empty(await provider.GetSimilarItemsAsync(film, vraag, CancellationToken.None));
        type.SimilarItemProviderOrder = ["Jelly Leon", "Local Genre/Tag"];
        Assert.Single(await provider.GetSimilarItemsAsync(film, vraag, CancellationToken.None));
        Assert.Empty(await provider.GetSimilarItemsAsync(serie, vraag, CancellationToken.None));
        Assert.Equal(2, lezingen);
    }

    [Fact]
    public void Bibliotheek_LeestAlleenHuidigeToestandVanDeVragerEnBewaartDeKijkgegevens()
    {
        var gebruiker = new User("test", "lokaal", "lokaal") { Id = Guid.NewGuid() };
        var map = new CollectionFolder { Id = Guid.NewGuid() };
        var geweigerd = Guid.NewGuid();
        Movie Film() => new() { Id = Guid.NewGuid(), Genres = ["Drama"], RunTimeTicks = 1000 };
        var bron = Film();
        var keuze = Film();
        var uitgesloten = Film();
        var onzichtbaar = Film();
        BaseItem[] toegestaan = [bron, keuze, uitgesloten];
        var eigenData = new UserItemData { Key = "bron", Played = true, IsFavorite = true, Rating = 8, PlaybackPositionTicks = 174,
            AudioStreamIndex = 2, SubtitleStreamIndex = 1, LastPlayedDate = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc) };
        var bibliotheek = new Mock<ILibraryManager>(MockBehavior.Strict);
        var gegevens = new Mock<IUserDataManager>(MockBehavior.Strict);
        var tv = new Mock<ITVSeriesManager>(MockBehavior.Strict);
        bibliotheek.Setup(b => b.GetVirtualFolders(false)).Returns([
            new() { ItemId = map.Id.ToString(), CollectionType = CollectionTypeOptions.movies },
            new() { ItemId = geweigerd.ToString(), CollectionType = CollectionTypeOptions.movies },
            new() { ItemId = Guid.NewGuid().ToString(), CollectionType = CollectionTypeOptions.homevideos },
        ]);
        bibliotheek.Setup(b => b.GetItemById<CollectionFolder>(map.Id, gebruiker)).Returns(map);
        bibliotheek.Setup(b => b.GetItemById<CollectionFolder>(geweigerd, gebruiker)).Returns((CollectionFolder?)null);
        bibliotheek.Setup(b => b.GetItemList(It.Is<InternalItemsQuery>(q => q.User == gebruiker && q.ParentId == map.Id
            && q.Recursive && q.IncludeItemTypes.Contains(BaseItemKind.Movie) && q.IncludeItemTypes.Contains(BaseItemKind.Series)), false))
            .Returns(toegestaan);
        bibliotheek.Setup(b => b.GetPeopleByItems(It.Is<IReadOnlyList<Guid>>(ids => ids.SequenceEqual(toegestaan.Select(i => i.Id)))))
            .Returns(new Dictionary<Guid, IReadOnlyList<PersonInfo>>());

        gegevens.Setup(g => g.GetUserDataBatch(It.Is<IReadOnlyList<BaseItem>>(rij => rij.SequenceEqual(toegestaan)), gebruiker))
            .Returns(new Dictionary<Guid, UserItemData> { [bron.Id] = eigenData });
        var adapter = new AanbevelingsBibliotheek(bibliotheek.Object, gegevens.Object, tv.Object, TimeProvider.System,
            () => new AnimeOptions());
        var vraag = new SimilarItemsQuery { User = gebruiker, Limit = 8, ExcludeItemIds = [uitgesloten.Id] };
        Assert.Equal([keuze.Id], adapter.Similar(bron, vraag, CancellationToken.None).Select(t => t.Id));
        Assert.Empty(adapter.Similar(onzichtbaar, vraag, CancellationToken.None));
        var home = adapter.VoorGebruiker(gebruiker, CancellationToken.None);
        Assert.Equal(new[] { keuze.Id, uitgesloten.Id }.Order(), home.Select(r => Guid.Parse(r.Item)).Order());
        Assert.True(eigenData.Played && eigenData.IsFavorite);
        Assert.Equal((8.0, 174L, 2, 1), (eigenData.Rating, eigenData.PlaybackPositionTicks, eigenData.AudioStreamIndex, eigenData.SubtitleStreamIndex));
        gegevens.VerifyAll();
        gegevens.VerifyNoOtherCalls();
    }
}
