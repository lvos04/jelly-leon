using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Plugin.JellyLeon.Configuration;
using Jellyfin.Plugin.JellyLeon.Modules.Recommendations;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Configuration;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Recommendations;

public sealed class SimilarProviderTests
{
    private static Movie Bron() => new() { Id = Guid.NewGuid(), Genres = ["Avontuur"] };

    private static SimilarItemsQuery Vraag() => new() { User = new User("kijker", "lokaal", "lokaal"), Limit = 3 };

    [Fact]
    public void Providercontract_OpDeVastgezetteAbi()
    {
        var type = typeof(SimilarProvider);
        Assert.True(type.IsPublic);
        Assert.True(typeof(ILocalSimilarItemsProvider<Movie>).IsAssignableFrom(type));
        Assert.True(typeof(ILocalSimilarItemsProvider<Series>).IsAssignableFrom(type));
        Assert.False(typeof(IBatchLocalSimilarItemsProvider).IsAssignableFrom(type));
        foreach (var (contract, item) in new[]
        {
            (typeof(ILocalSimilarItemsProvider), typeof(BaseItem)),
            (typeof(ILocalSimilarItemsProvider<Movie>), typeof(Movie)),
            (typeof(ILocalSimilarItemsProvider<Series>), typeof(Series)),
        })
        {
            var method = contract.GetMethod("GetSimilarItemsAsync", [item, typeof(SimilarItemsQuery), typeof(CancellationToken)]);
            Assert.Equal(typeof(Task<IReadOnlyList<BaseItem>>), method?.ReturnType);
        }

        Assert.Equal(["GetSimilarItemsAsync", "Supports"], typeof(ILocalSimilarItemsProvider).GetMethods().Select(m => m.Name).Order());
        var queryType = typeof(SimilarItemsQuery);
        Assert.Equal(["DtoOptions", "ExcludeArtistIds", "ExcludeItemIds", "Limit", "User"], queryType.GetProperties().Select(p => p.Name).Order());
        Assert.Equal(typeof(IReadOnlyList<Guid>), queryType.GetProperty("ExcludeItemIds")!.PropertyType);
        Assert.Equal(typeof(User), queryType.GetProperty("User")!.PropertyType);
        Assert.Equal(typeof(int?), queryType.GetProperty("Limit")!.PropertyType);
        ILocalSimilarItemsProvider provider = new SimilarProvider(() => false, _ => []);
        Assert.Equal("Jelly Leon", provider.Name);
        Assert.Equal(MetadataPluginType.LocalSimilarityProvider, provider.Type);
        Assert.True(provider.Supports(typeof(Movie)));
        Assert.True(provider.Supports(typeof(Series)));
        Assert.False(provider.Supports(typeof(Episode)));
        Assert.Null(provider.CacheDuration);
        Assert.False(new PluginConfiguration().Recommendations.Enabled);
        Assert.True(new PluginConfiguration().Recommendations.Similar.Enabled);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Selectie_VraagtHetJuisteTypeMetGenresGebruikerEnUitsluitingen(bool film)
    {
        BaseItem bron = film ? Bron() : new Series { Id = Guid.NewGuid(), Genres = ["Avontuur"] };
        var vraag = Vraag();
        var eerder = Guid.NewGuid();
        vraag.ExcludeItemIds = [eerder, bron.Id];
        var treffer = Bron();
        InternalItemsQuery? ontvangen = null;
        ILocalSimilarItemsProvider provider = new SimilarProvider(() => true, q =>
        {
            ontvangen = q;
            return [treffer];
        });

        Assert.Same(treffer, Assert.Single(await provider.GetSimilarItemsAsync(bron, vraag, CancellationToken.None)));
        Assert.NotNull(ontvangen);
        Assert.Same(vraag.User, ontvangen.User);
        Assert.Equal(vraag.Limit, ontvangen.Limit);
        Assert.Equal(film ? "Movie" : "Series", Assert.Single(ontvangen.IncludeItemTypes).ToString());
        Assert.Equal(bron.Genres, ontvangen.Genres);
        Assert.Equal([eerder, bron.Id], ontvangen.ExcludeItemIds);
        Assert.False(ontvangen.IsPlayed);
    }

    [Fact]
    public async Task UitGeenGebruikerGeenGenreOfNulLimiet_LeestNiets()
    {
        var aan = false;
        var lezingen = 0;
        var provider = new SimilarProvider(() => aan, _ => { lezingen++; return []; });
        Assert.Empty(await provider.GetSimilarItemsAsync(Bron(), Vraag(), CancellationToken.None));
        aan = true;
        Assert.Empty(await provider.GetSimilarItemsAsync(Bron(), new SimilarItemsQuery(), CancellationToken.None));
        Assert.Empty(await provider.GetSimilarItemsAsync(new Movie(), Vraag(), CancellationToken.None));
        var vraag = Vraag();
        vraag.Limit = 0;
        Assert.Empty(await provider.GetSimilarItemsAsync(Bron(), vraag, CancellationToken.None));
        Assert.Equal(0, lezingen);
    }

    [Fact]
    public async Task Fout_LevertRuimteVoorStockEnBlokkeertDeVolgendeVraagNiet()
    {
        var lezingen = 0;
        var provider = new SimilarProvider(() => true, _ => ++lezingen == 1 ? throw new InvalidOperationException() : [Bron()]);
        Assert.Empty(await provider.GetSimilarItemsAsync(Bron(), Vraag(), CancellationToken.None));
        Assert.Single(await provider.GetSimilarItemsAsync(Bron(), Vraag(), CancellationToken.None));
    }

    [Fact]
    public async Task Tijdslimiet_LaatStockDoorTerwijlDeSynchroneLezingenNogBezetZijn()
    {
        var vrij = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var begonnen = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var lezingen = 0;
        var provider = new SimilarProvider(() => true, _ =>
        {
            if (Interlocked.Increment(ref lezingen) == 2)
            {
                begonnen.SetResult();
            }

            vrij.Task.GetAwaiter().GetResult();
            return [Bron()];
        });

        Assert.Equal(TimeSpan.FromMilliseconds(300), SimilarProvider.Tijdslimiet);
        try
        {
            var twee = Enumerable.Range(0, 2).Select(_ => provider.GetSimilarItemsAsync(Bron(), Vraag(), CancellationToken.None)).ToArray();
            await begonnen.Task.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
            Assert.Empty(await provider.GetSimilarItemsAsync(Bron(), Vraag(), CancellationToken.None));
            Assert.All(await Task.WhenAll(twee).WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken), antwoord => Assert.Empty(antwoord));
            Assert.Equal(2, lezingen);
        }
        finally
        {
            vrij.SetResult();
        }

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => provider.GetSimilarItemsAsync(Bron(), Vraag(), new CancellationToken(true)));
    }
}
