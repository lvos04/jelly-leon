using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Media;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.MediaGuard;
using Jellyfin.Plugin.JellyLeon.Core.Planner;
using MediaBrowser.Controller.MediaSegments;
using MediaBrowser.Controller.Library;
using System.Threading.Channels;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Modules.Segments;

/// <summary>Serialiseert publicatie en herstel over de eigen SQLite en de publieke segmentmanager.</summary>
internal sealed class SegmentDienst(IServiceProvider diensten, SegmentsModule module, IModuleSwitches schakelaars, TimeProvider klok, ILogger<SegmentDienst> log)
    : BackgroundService
{
    private bool _volgt;
    private readonly SemaphoreSlim _slot = new(1, 1);
    private readonly Channel<bool> _wakker = Channel.CreateBounded<bool>(1);
    private SegmentBibliotheek Bron => diensten.GetRequiredService<SegmentBibliotheek>();
    private SegmentPublicatie Publicatie => diensten.GetRequiredService<SegmentPublicatie>();

    public async Task<JsonObject> Publiceer(Guid bib, Guid? serie, string modus, string? reden, bool voorbeeld, string? hash, string actor, CancellationToken stop)
    {
        await _slot.WaitAsync(stop).ConfigureAwait(false);
        try
        {
            if (!schakelaars.IsAan(SegmentsModule.ModuleSlug))
            {
                throw Fouten.NietGevonden();
            }

            if (Bron.Mappen(bib).Length == 0)
            {
                throw Fouten.NietGevonden();
            }

            var versie = module.Versie;
            var items = module.Selectie(bib, serie);
            var bevestigd = SegmentsModule.Steekproef(items);
            var maken = 0;
            var wissen = 0;
            var wijzigingen = new List<object>();
            foreach (var item in items)
            {
                stop.ThrowIfCancellationRequested();
                var video = Bron.Video(item.ItemId);
                if (video is null)
                {
                    continue;
                }

                var doel = SegmentsModule.Doel(item, modus);
                if (doel.Length > 0 && !Bron.Past(video, item))
                {
                    throw Fouten.Conflict("realign_needed");
                }

                var verschil = await Publicatie.Vergelijk(video, doel).ConfigureAwait(false);
                maken += verschil.Maken.Count;
                wissen += verschil.Verwijderen.Count;
                wijzigingen.Add(new { item.ItemId, verschil.Maken, wissen = verschil.Verwijderen.Select(SegmentPublicatie.RijId).Order().ToArray() });
            }

            var actueel = SegmentGegevens.Hash(SegmentsModule.Schrijf(new { bib, serie, modus, reden, actor, versie, wijzigingen }));
            if (voorbeeld)
            {
                return new JsonObject { ["mode"] = modus, ["qc"] = new JsonObject { ["required"] = 3, ["confirmed"] = bevestigd },
                    ["would_create"] = maken, ["would_delete"] = wissen, ["preview_hash"] = actueel };
            }

            if (actueel != hash)
            {
                throw Fouten.Conflict("preview_changed");
            }

            module.LegPublicatieVast(bib, serie, modus, versie, reden, actor, klok.GetUtcNow());
            var aantallen = await Synchroniseer(stop).ConfigureAwait(false);
            _wakker.Writer.TryWrite(true);
            return new JsonObject { ["mode"] = modus, ["created"] = aantallen.Gemaakt, ["deleted"] = aantallen.Verwijderd };
        }
        finally
        {
            _slot.Release();
        }
    }

    public async Task Uitzetten(CancellationToken stop)
    {
        await _slot.WaitAsync(stop).ConfigureAwait(false);
        try
        {
            if (module.HeeftDatabase)
            {
                module.AllesIntrekken();
                await Synchroniseer(stop).ConfigureAwait(false);
            }

            schakelaars.Zet(SegmentsModule.ModuleSlug, false);
        }
        finally
        {
            _slot.Release();
        }
    }

    private async Task<(int Gemaakt, int Verwijderd)> Synchroniseer(CancellationToken stop)
    {
        var gemaakt = 0;
        var verwijderd = 0;
        foreach (var id in module.TeSynchroniseren())
        {
            stop.ThrowIfCancellationRequested();
            var doel = module.Gepubliceerd(id);
            if (Bron.Video(id) is { } video)
            {
                if (doel.Length > 0 && (module.Vind(id) is not { } item || !Bron.Past(video, item)))
                {
                    module.Verouder(id);
                    doel = [];
                }

                var verschil = await Publicatie.StemAf(video, doel).ConfigureAwait(false);
                gemaakt += verschil.Gemaakt;
                verwijderd += verschil.Verwijderd;
            }
            else if (doel.Length > 0)
            {
                module.Verouder(id);
                doel = [];
            }

            module.Afgestemd(id, doel);
        }

        return (gemaakt, verwijderd);
    }

    internal async Task Controleer(CancellationToken stop)
    {
        await _slot.WaitAsync(stop).ConfigureAwait(false);
        try
        {
            if (!schakelaars.IsAan(SegmentsModule.ModuleSlug))
            {
                if (_volgt)
                {
                    Bron.LaatLos(Gewijzigd);
                    _volgt = false;
                }

                if (module.HeeftDatabase)
                {
                    module.AllesIntrekken();
                    await Synchroniseer(stop).ConfigureAwait(false);
                }

                return;
            }

            if (!_volgt)
            {
                Bron.Volg(Gewijzigd);
                _volgt = true;
            }

            var verdwenen = new HashSet<Guid>();
            foreach (var oud in module.Selectie())
            {
                stop.ThrowIfCancellationRequested();
                if (Bron.Video(oud.ItemId) is null)
                {
                    verdwenen.Add(oud.ItemId);
                }
            }

            module.VerwerkWezen(verdwenen, klok.GetUtcNow());
            foreach (var bib in module.Bibliotheken().Where(module.BibliotheekAan))
            {
                var mappen = Bron.Mappen(bib);
                if (SegmentBibliotheek.Mount(mappen) != MountCheck.Uitkomst.AlleenLezen)
                {
                    continue;
                }

                foreach (var video in Bron.Videos(bib))
                {
                    stop.ThrowIfCancellationRequested();
                    if (SegmentBibliotheek.TeLezen(video, bib, module) && Bron.Lees(video, bib) is { } item)
                    {
                        module.BewaarAnalyse(item);
                    }
                }
            }

            await Synchroniseer(stop).ConfigureAwait(false);
        }
        finally
        {
            _slot.Release();
        }
    }

    internal JsonObject Status()
    {
        var mount = MountCheck.Uitkomst.Onbekend;
        var libs = new JsonArray();
        var standen = new List<MountCheck.Uitkomst>();
        foreach (var bib in module.Bibliotheken())
        {
            var beoordeeld = SegmentBibliotheek.Mount(Bron.Mappen(bib));
            if (module.BibliotheekAan(bib))
            {
                standen.Add(beoordeeld);
            }

            libs.Add(new JsonObject { ["id"] = bib, ["publication"] = module.Modus(bib, null), ["mount"] = beoordeeld.ToString() });
        }

        if (standen.Count > 0)
        {
            mount = standen.Contains(MountCheck.Uitkomst.Schrijfbaar) ? MountCheck.Uitkomst.Schrijfbaar :
                standen.All(v => v == MountCheck.Uitkomst.AlleenLezen) ? MountCheck.Uitkomst.AlleenLezen : MountCheck.Uitkomst.Onbekend;
        }

        return new JsonObject
        {
            ["provider"] = new JsonObject { ["name"] = SegmentProvider.VasteNaam, ["registered"] = diensten.GetServices<IMediaSegmentProvider>().OfType<SegmentProvider>().Count() == 1 },
            ["libraries"] = libs, ["mount"] = new JsonObject { ["read_only"] = mount == MountCheck.Uitkomst.AlleenLezen },
            ["health"] = mount == MountCheck.Uitkomst.Schrijfbaar ? "down" : module.Bevroren ? "degraded" :
                mount == MountCheck.Uitkomst.AlleenLezen ? "healthy" : "unknown",
            ["reason"] = mount == MountCheck.Uitkomst.Schrijfbaar ? "media_mount_writable" : module.Bevroren ? "orphans_frozen" :
                mount == MountCheck.Uitkomst.Onbekend ? "media_mount_unknown" : "ok",
            ["orphans"] = module.Wezen(null),
            ["budget"] = diensten.GetRequiredService<BatchPlanner>().Status(),
            ["mediaguard"] = new JsonObject { ["state"] = diensten.GetRequiredService<MediaGuardClient>().Beeld.Status switch
                {
                    MgStatus.Ok => "ok", MgStatus.Geweigerd => "wrong_role", MgStatus.Onbereikbaar => "unreachable", _ => "unknown",
                } },
            ["local_ai"] = new JsonObject { ["stt"] = "off", ["embedding"] = "off" },
        };
    }

    private void Gewijzigd(object? afzender, ItemChangeEventArgs gegevens) => _wakker.Writer.TryWrite(true);

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        await base.StopAsync(cancellationToken).ConfigureAwait(false);
        if (_volgt)
        {
            Bron.LaatLos(Gewijzigd);
            _volgt = false;
        }
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await Controleer(stoppingToken).ConfigureAwait(false);
            }
            catch (Exception fout) when (!stoppingToken.IsCancellationRequested)
            {
                log.LogWarning("Segmentcontrole wordt herhaald ({Soort}).", fout.GetType().Name);
            }

            using var uur = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
            uur.CancelAfter(TimeSpan.FromHours(1));
            try
            {
                await _wakker.Reader.ReadAsync(uur.Token).ConfigureAwait(false);
                // Bundel een bibliotheekscan tot één herlezing.
                await Task.Delay(TimeSpan.FromSeconds(2), klok, stoppingToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (!stoppingToken.IsCancellationRequested)
            {
                // De periodieke mountcontrole is aan de beurt.
            }
        }
    }

    public override void Dispose()
    {
        base.Dispose();
        _slot.Dispose();
        _wakker.Writer.TryComplete();
    }
}
