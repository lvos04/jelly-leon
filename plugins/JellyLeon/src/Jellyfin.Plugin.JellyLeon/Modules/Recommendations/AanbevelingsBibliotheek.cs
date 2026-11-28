using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using Jellyfin.Data.Enums;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Plugin.JellyLeon.Configuration;
using Jellyfin.Plugin.JellyLeon.Modules.Recommendations.Engine;
using MediaBrowser.Controller.Dto;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.TV;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.Querying;

namespace Jellyfin.Plugin.JellyLeon.Modules.Recommendations;

internal sealed class AanbevelingsBibliotheek(ILibraryManager bibliotheek, IUserDataManager gebruikersdata,
    ITVSeriesManager series, TimeProvider klok, Func<AnimeOptions> leesAnime)
{
    public IReadOnlyList<BaseItem> Similar(BaseItem bron, SimilarItemsQuery vraag, CancellationToken stop)
    {
        if (vraag.User is not { } gebruiker) { return []; }
        var opname = Lees(gebruiker, stop);
        var bronId = bron.Id.ToString("N");
        if (!opname.Items.ContainsKey(bronId)) { return []; }
        var profiel = opname.Profiel with { NietInteressant = vraag.ExcludeItemIds.Select(id => id.ToString("N")).ToHashSet() };
        var soort = bron is Series ? "Series" : "Movie";
        var rij = new KlassiekeEngine(klok).Rangschik(opname.Titels.Where(t => t.Soort == soort), profiel,
            Math.Min(vraag.Limit ?? 20, opname.Titels.Count), bronId, stop: stop);
        return rij.Select(r => opname.Items[r.Item]).ToArray();
    }

    public IReadOnlyList<Aanbeveling> VoorGebruiker(User gebruiker, CancellationToken stop)
    {
        var opname = Lees(gebruiker, stop);
        return new KlassiekeEngine(klok).Rangschik(opname.Titels, opname.Profiel, stop: stop);
    }

    private (List<Titel> Titels, Dictionary<string, BaseItem> Items, Kijkprofiel Profiel) Lees(User gebruiker, CancellationToken stop)
    {
        var items = new Dictionary<string, BaseItem>(StringComparer.Ordinal);
        var titels = new List<Titel>();
        var tvMappen = new List<BaseItem>();
        var anime = leesAnime();
        var animeItems = new HashSet<Guid>();
        var verzamelingen = new Dictionary<Guid, List<string>>();
        foreach (var map in bibliotheek.GetVirtualFolders(false))
        {
            stop.ThrowIfCancellationRequested();
            if (map.CollectionType is not (CollectionTypeOptions.movies or CollectionTypeOptions.tvshows or CollectionTypeOptions.boxsets)
                || !Guid.TryParse(map.ItemId, out var id)
                || bibliotheek.GetItemById<CollectionFolder>(id, gebruiker) is not { } zichtbaar)
            {
                continue;
            }

            if (map.CollectionType == CollectionTypeOptions.tvshows) { tvMappen.Add(zichtbaar); }
            var selectie = new InternalItemsQuery(gebruiker)
            {
                ParentId = id, Recursive = true,
                IncludeItemTypes = map.CollectionType == CollectionTypeOptions.boxsets ? [BaseItemKind.BoxSet]
                    : [BaseItemKind.Movie, BaseItemKind.Series, BaseItemKind.BoxSet],
                EnableTotalRecordCount = false, DtoOptions = new DtoOptions(true) { EnableImages = false },
            };
            foreach (var item in bibliotheek.GetItemList(selectie, false))
            {
                stop.ThrowIfCancellationRequested();
                if (item is BoxSet groep)
                {
                    foreach (var lid in groep.GetLinkedChildren(gebruiker))
                    {
                        if (!verzamelingen.TryGetValue(lid.Id, out var lijst)) { verzamelingen[lid.Id] = lijst = []; }
                        lijst.Add(groep.Id.ToString("N"));
                    }
                }
                else if (item is Movie or Series && map.CollectionType != CollectionTypeOptions.boxsets)
                {
                    items.TryAdd(item.Id.ToString("N"), item);
                    if (anime.LibraryIds?.Contains(id) == true) { animeItems.Add(item.Id); }
                }
            }
        }

        stop.ThrowIfCancellationRequested();
        var betrokkenen = bibliotheek.GetPeopleByItems(items.Values.Select(item => item.Id).ToArray());
        foreach (var (sleutel, item) in items)
        {
            stop.ThrowIfCancellationRequested();
            var personen = betrokkenen.GetValueOrDefault(item.Id) ?? [];
            IEnumerable<string> groepen = verzamelingen.GetValueOrDefault(item.Id) ?? [];
            if (item is Movie { CollectionName.Length: > 0 } film) { groepen = groepen.Append(film.CollectionName); }
            titels.Add(new(sleutel, item is Series ? "Series" : "Movie")
            {
                Genres = item.Genres, Tags = item.Tags, Studios = item.Studios,
                Regisseurs = personen.Where(p => p.IsType(PersonKind.Director)).Select(p => p.Name).ToArray(),
                Schrijvers = personen.Where(p => p.IsType(PersonKind.Writer)).Select(p => p.Name).ToArray(),
                Acteurs = personen.Where(p => p.IsType(PersonKind.Actor)).OrderBy(p => p.SortOrder ?? int.MaxValue)
                    .ThenBy(p => p.Name, StringComparer.Ordinal).Take(5).Select(p => p.Name).ToArray(),
                Collecties = groepen.Distinct(StringComparer.Ordinal).ToArray(),
                Serie = item is Series ? sleutel : null, Jaar = item.ProductionYear,
                Keur = item.OfficialRating, Waardering = item.CommunityRating, Landen = item.ProductionLocations,
                Toegevoegd = DateTime.SpecifyKind(item.DateCreated, DateTimeKind.Utc),
                AnimeBibliotheek = animeItems.Contains(item.Id),
                AnimeGenres = anime.GenreNames ?? ["Anime"],
            });
        }

        stop.ThrowIfCancellationRequested();
        var toestanden = gebruikersdata.GetUserDataBatch(items.Values.ToArray(), gebruiker);
        var eigen = new List<Kijktoestand>();
        foreach (var item in items.Values)
        {
            stop.ThrowIfCancellationRequested();
            var data = toestanden.GetValueOrDefault(item.Id);
            var voltooid = item is Series && gebruikersdata.GetUserDataDto(item, gebruiker)?.Played == true;
            if (data is null && !voltooid) { continue; }
            var toestand = new Kijktoestand(item.Id.ToString("N"),
                data?.LastPlayedDate is { } tijd ? DateTime.SpecifyKind(tijd, DateTimeKind.Utc) : null,
                voltooid || data?.Played == true, data?.IsFavorite == true, data?.Rating, data?.Likes,
                item.RunTimeTicks is > 0 ? (double)(data?.PlaybackPositionTicks ?? 0) / item.RunTimeTicks.Value : 0);
            if (toestand.Bekeken || toestand.Favoriet || toestand.Rating.HasValue || toestand.Fractie > 0) { eigen.Add(toestand); }
        }

        var volgende = tvMappen.Count == 0 ? [] : series.GetNextUp(new NextUpQuery { User = gebruiker }, [.. tvMappen], new DtoOptions())
            .Items.OfType<Episode>().Select(a => a.SeriesId.ToString("N")).ToHashSet();
        var profiel = new Kijkprofiel(gebruiker.Id.ToString("N"), items.Keys.ToHashSet(), [.. eigen]) { Volgende = volgende };
        return (titels, items, profiel);
    }
}
