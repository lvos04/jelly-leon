using System;
using System.Collections.Generic;
using System.Linq;
using Jellyfin.Data.Enums;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Media;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Persistence;

namespace Jellyfin.Plugin.JellyLeon.Modules.Segments;

/// <summary>Leest IDs, mediaduur en hoofdstukken via de publieke server-ABI. Opent geen mediabestand.</summary>
internal sealed class SegmentBibliotheek(ILibraryManager bibliotheek, IUserManager gebruikers, IChapterRepository hoofdstukken)
{
    public void Volg(EventHandler<ItemChangeEventArgs> signaal)
    {
        bibliotheek.ItemAdded += signaal;
        bibliotheek.ItemRemoved += signaal;
        bibliotheek.ItemUpdated += signaal;
    }

    public void LaatLos(EventHandler<ItemChangeEventArgs> signaal)
    {
        bibliotheek.ItemAdded -= signaal;
        bibliotheek.ItemRemoved -= signaal;
        bibliotheek.ItemUpdated -= signaal;
    }

    internal static Guid? SerieVan(BaseItem item) => item is Episode ep && ep.SeriesId != Guid.Empty ? ep.SeriesId : null;

    internal static long DuurVanItem(BaseItem item) => item.RunTimeTicks ?? 0;

    public Video? Video(Guid id) => bibliotheek.GetItemById<Video>(id);

    public Video Zichtbaar(Guid id, Guid gebruiker)
    {
        var account = gebruiker == Guid.Empty ? null : gebruikers.GetUserById(gebruiker);
        if (account is null)
        {
            throw Fouten.NietGevonden();
        }

        return bibliotheek.GetItemById<Video>(id, account) ?? throw Fouten.NietGevonden();
    }

    public IReadOnlyList<Guid> Bibliotheken(BaseItem item) => bibliotheek.GetCollectionFolders(item).Select(f => f.Id).ToList();

    public bool Past(Video video, SegmentItem item) => Bibliotheken(video).Contains(item.Bibliotheek) &&
        SerieVan(video) == item.Serie && video.RunTimeTicks == item.Duur && video.DateModified.Ticks == item.Mtime;

    public static bool TeLezen(Video video, Guid bib, SegmentsModule module)
    {
        if (module.Modus(bib, SerieVan(video)) == "disabled")
        {
            return false;
        }

        var oud = module.Vind(video.Id);
        return oud is null || oud.Wees || oud.Mtime != video.DateModified.Ticks || (!oud.Heruitlijnen && oud.Duur != DuurVanItem(video)) || (oud.Heruitlijnen && !oud.Bevestigd &&
            !oud.Kandidaten.Any(k => k.Bron is "manual" or "confirmed"));
    }

    public string[] Mappen(Guid bib) => bibliotheek.GetVirtualFolders().Where(f => Guid.TryParse(f.ItemId, out var id) && id == bib)
        .SelectMany(f => f.Locations).Distinct(StringComparer.Ordinal).ToArray();

    public static MountCheck.Uitkomst Mount(IReadOnlyList<string> paden)
    {
        var uitkomsten = paden.Select(p => MountCheck.Beoordeel(p)).ToArray();
        return uitkomsten.Contains(MountCheck.Uitkomst.Schrijfbaar) ? MountCheck.Uitkomst.Schrijfbaar :
            uitkomsten.Length > 0 && uitkomsten.All(u => u == MountCheck.Uitkomst.AlleenLezen) ? MountCheck.Uitkomst.AlleenLezen : MountCheck.Uitkomst.Onbekend;
    }

    public IEnumerable<Video> Videos(Guid bib)
    {
        for (var begin = 0; ; begin += 128)
        {
            var pagina = bibliotheek.GetItemList(new InternalItemsQuery
            {
                ParentId = bib, Recursive = true, MediaTypes = [MediaType.Video], StartIndex = begin, Limit = 128,
            });
            foreach (var item in pagina.OfType<Video>())
            {
                yield return item;
            }

            if (pagina.Count < 128)
            {
                yield break;
            }
        }
    }

    public SegmentItem? Lees(Video video, Guid bib)
    {
        var duur = video.RunTimeTicks ?? 0;
        if (duur <= 0)
        {
            return null;
        }

        var vakken = SegmentGegevens.UitHoofdstukken(hoofdstukken.GetChapters(video.Id).Select(h => (h.StartPositionTicks, h.Name)), duur);
        var externeIds = video.ProviderIds.OrderBy(p => p.Key, StringComparer.Ordinal).Select(p => p.Key + "=" + p.Value).ToArray();
        var herkomst = externeIds.Length == 0 ? null : SegmentGegevens.Hash(SegmentsModule.Schrijf(externeIds));
        return new SegmentItem(video.Id, bib, SerieVan(video), video.ParentIndexNumber, video.IndexNumber, duur,
            video.DateModified.Ticks, herkomst, vakken);
    }
}
