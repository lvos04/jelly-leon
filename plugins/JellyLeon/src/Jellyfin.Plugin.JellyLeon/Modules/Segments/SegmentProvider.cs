using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using MediaBrowser.Common.Extensions;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.MediaSegments;
using MediaBrowser.Model;
using MediaBrowser.Model.MediaSegments;
using Microsoft.Extensions.DependencyInjection;

namespace Jellyfin.Plugin.JellyLeon.Modules.Segments;

/// <summary>De extractietaak leest alleen de al vrijgegeven set. Ook met geweigerde pluginopslag kan de server starten.</summary>
internal sealed class SegmentProvider(IServiceProvider diensten, IModuleSwitches schakelaars) : IMediaSegmentProvider
{
    public const string VasteNaam = "Jelly Leon Segmenten";
    public static readonly string ProviderId = VasteNaam.ToLowerInvariant().GetMD5().ToString("N", CultureInfo.InvariantCulture);

    public string Name => VasteNaam;

    public ValueTask<bool> Supports(BaseItem item)
    {
        if (item is not Video || !schakelaars.IsAan(SegmentsModule.ModuleSlug))
        {
            return ValueTask.FromResult(false);
        }

        var module = diensten.GetRequiredService<SegmentsModule>();
        var serie = SegmentBibliotheek.SerieVan(item);
        return ValueTask.FromResult(diensten.GetRequiredService<ILibraryManager>().GetCollectionFolders(item)
            .Any(map => module.Modus(map.Id, serie) != "disabled"));
    }

    public Task<IReadOnlyList<MediaSegmentDto>> GetMediaSegments(MediaSegmentGenerationRequest request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        IReadOnlyList<MediaSegmentDto> resultaat = schakelaars.IsAan(SegmentsModule.ModuleSlug)
            ? diensten.GetRequiredService<SegmentsModule>().Gepubliceerd(request.ItemId).Select(s => MaakDto(request.ItemId, s)).ToArray()
            : [];
        return Task.FromResult(resultaat);
    }

    public Task CleanupExtractedData(Guid itemId, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        // Ook een uitgeschakelde module bewaart menselijke correcties. Open geen nieuwe DB bij een stock-refresh.
        if (diensten.GetRequiredService<Core.PluginOpslag>().Beschikbaar)
        {
            diensten.GetRequiredService<SegmentsModule>().RuimCache(itemId);
        }

        return Task.CompletedTask;
    }

    internal static MediaSegmentDto MaakDto(Guid item, Tijdvak vak) => new()
    {
        Id = Guid.NewGuid(), ItemId = item, Type = vak.Type, StartTicks = vak.Start, EndTicks = vak.Einde,
    };
}
