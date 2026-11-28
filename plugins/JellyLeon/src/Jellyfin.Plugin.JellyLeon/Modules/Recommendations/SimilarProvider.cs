using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Jellyfin.Plugin.JellyLeon.Modules.Recommendations;

internal delegate IReadOnlyList<BaseItem> LeesSimilarMetadata(BaseItem bron, SimilarItemsQuery vraag, CancellationToken stop);

/// <summary>Klassieke aanbevelingen voor Meer zoals dit. De host ontdekt deze publieke provider in de plugin-DLL.</summary>
public sealed class SimilarProvider : ILocalSimilarItemsProvider<Movie>, ILocalSimilarItemsProvider<Series>
{
    internal static readonly TimeSpan Tijdslimiet = TimeSpan.FromMilliseconds(300);
    private readonly Func<bool> _aan;
    private readonly LeesSimilarMetadata _lees;
    private int _bezet;

    /// <summary>Bindt de provider aan de moduleschakelaar en de gebruikersgebonden bibliotheekquery.</summary>
    /// <param name="diensten">De gedeelde diensten van de plugin.</param>
    public SimilarProvider(IServiceProvider diensten)
        : this(diensten.GetRequiredService<PluginModuleSwitches>().SimilarAan, diensten.GetRequiredService<LeesSimilarMetadata>())
    {
    }

    internal SimilarProvider(Func<bool> aan, LeesSimilarMetadata lees)
    {
        _aan = aan;
        _lees = lees;
    }

    /// <inheritdoc />
    public string Name => "Jelly Leon";

    /// <inheritdoc />
    public MetadataPluginType Type => MetadataPluginType.LocalSimilarityProvider;

    bool ILocalSimilarItemsProvider.Supports(Type itemType) =>
        typeof(Movie).IsAssignableFrom(itemType) || typeof(Series).IsAssignableFrom(itemType);

    Task<IReadOnlyList<BaseItem>> ILocalSimilarItemsProvider.GetSimilarItemsAsync(
        BaseItem item, SimilarItemsQuery query, CancellationToken cancellationToken) => item switch
        {
            Movie film => GetSimilarItemsAsync(film, query, cancellationToken),
            Series serie => GetSimilarItemsAsync(serie, query, cancellationToken),
            _ => Task.FromResult<IReadOnlyList<BaseItem>>([]),
        };

    /// <inheritdoc />
    public Task<IReadOnlyList<BaseItem>> GetSimilarItemsAsync(Movie item, SimilarItemsQuery query, CancellationToken cancellationToken) =>
        Zoek(item, query, cancellationToken);

    /// <inheritdoc />
    public Task<IReadOnlyList<BaseItem>> GetSimilarItemsAsync(Series item, SimilarItemsQuery query, CancellationToken cancellationToken) =>
        Zoek(item, query, cancellationToken);

    private async Task<IReadOnlyList<BaseItem>> Zoek(BaseItem item, SimilarItemsQuery query, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        if (query.User is null || query.Limit is <= 0 || item.Id == Guid.Empty)
        {
            return [];
        }

        // De lees-API van 12.4 is synchroon. Ook na een time-out blijven hooguit twee lezingen actief.
        if (Interlocked.Increment(ref _bezet) > 2)
        {
            Interlocked.Decrement(ref _bezet);
            return [];
        }

        using var termijn = CancellationTokenSource.CreateLinkedTokenSource(token);
        termijn.CancelAfter(Tijdslimiet);
        var stop = termijn.Token;
        var lezing = Task.Run<IReadOnlyList<BaseItem>>(() =>
        {
            try
            {
                if (stop.IsCancellationRequested || !_aan())
                {
                    return [];
                }

                return _lees(item, query, stop);
            }
            catch (Exception)
            {
                // Een providerfout laat de host bij de volgende provider doorgaan. Ook late fouten worden afgehandeld.
                return [];
            }
            finally
            {
                Interlocked.Decrement(ref _bezet);
            }
        }, CancellationToken.None);

        try
        {
            var items = await lezing.WaitAsync(stop).ConfigureAwait(false);
            token.ThrowIfCancellationRequested();
            return stop.IsCancellationRequested ? [] : items;
        }
        catch (OperationCanceledException) when (!token.IsCancellationRequested)
        {
            return [];
        }
    }
}
