using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.MediaSegments;
using MediaBrowser.Model.Configuration;
using MediaBrowser.Model.MediaSegments;

namespace Jellyfin.Plugin.JellyLeon.Modules.Segments;

/// <summary>Past uitsluitend de eigen rijen aan. De publieke DTO bevat zelf geen provider-ID.</summary>
internal sealed class SegmentPublicatie(IMediaSegmentManager manager)
{
    internal sealed record Verschil(IReadOnlyList<MediaSegmentDto> Verwijderen, IReadOnlyList<Tijdvak> Maken);

    public async Task<Verschil> Vergelijk(BaseItem item, IReadOnlyList<Tijdvak> gewenst)
    {
        var providers = manager.GetSupportedProviders(item).ToArray();
        if (providers.Count(p => p.Name == SegmentProvider.VasteNaam && p.Id == SegmentProvider.ProviderId) != 1)
        {
            throw Fouten.Conflict("provider_unavailable");
        }

        // Een nieuw, lokaal optiesobject. Upstream filtert hierdoor in de database op precies onze provider-ID.
        var filter = new LibraryOptions
        {
            DisabledMediaSegmentProviders = providers.Where(p => p.Id != SegmentProvider.ProviderId).Select(p => p.Name).ToArray(),
        };
        var eigen = (await manager.GetSegmentsAsync(item, null, filter, filterByProvider: true).ConfigureAwait(false)).ToList();
        var maken = new List<Tijdvak>();
        foreach (var vak in gewenst)
        {
            var index = eigen.FindIndex(r => r.Type == vak.Type && r.StartTicks == vak.Start && r.EndTicks == vak.Einde);
            if (index >= 0)
            {
                eigen.RemoveAt(index);
            }
            else
            {
                maken.Add(vak);
            }
        }

        return new Verschil(eigen, maken);
    }

    public async Task<(int Gemaakt, int Verwijderd)> StemAf(BaseItem item, IReadOnlyList<Tijdvak> gewenst)
    {
        var verschil = await Vergelijk(item, gewenst).ConfigureAwait(false);
        foreach (var rij in verschil.Verwijderen)
        {
            await manager.DeleteSegmentAsync(rij.Id).ConfigureAwait(false);
        }

        foreach (var vak in verschil.Maken)
        {
            await manager.CreateSegmentAsync(SegmentProvider.MaakDto(item.Id, vak), SegmentProvider.ProviderId).ConfigureAwait(false);
        }

        return (verschil.Maken.Count, verschil.Verwijderen.Count);
    }
}
