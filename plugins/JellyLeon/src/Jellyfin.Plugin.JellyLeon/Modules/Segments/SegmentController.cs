using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Database.Implementations.Enums;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;

namespace Jellyfin.Plugin.JellyLeon.Modules.Segments;

/// <summary>Segmenten lezen, publiceren, exporteren en beheren via de gemeenschappelijke verzoekfilters.</summary>
[Route("media/v1/segments")]
public sealed class SegmentController(IServiceProvider diensten) : ControllerBase
{
    private SegmentsModule Module => diensten.GetRequiredService<SegmentsModule>();
    private SegmentDienst Dienst => diensten.GetRequiredService<SegmentDienst>();
    private SegmentBibliotheek Bron => diensten.GetRequiredService<SegmentBibliotheek>();
    private JlContext Context => JlContext.Van(HttpContext);
    private DateTimeOffset Nu => diensten.GetRequiredService<TimeProvider>().GetUtcNow();

    /// <summary>Leest na de item-ACL de gepubliceerde set of de kandidaatset.</summary>
    /// <param name="itemId">Het item in de bibliotheek.</param>
    /// <returns>De set en haar ETag.</returns>
    [HttpGet("{itemId}")]
    [JlRoute("segments.item")]
    public IActionResult Item([FromRoute] string itemId)
    {
        if (!Guid.TryParse(itemId, out var id) || Context.Sessie?.GebruikerId is not Guid gebruiker)
        {
            throw Fouten.NietGevonden();
        }

        var video = Bron.Zichtbaar(id, gebruiker);
        var view = Request.Query["view"].FirstOrDefault() ?? "published";
        if (view is not ("candidate" or "published"))
        {
            throw Fouten.Validatie(("view", "invalid_view", "Gebruik published of candidate."));
        }

        if (view == "candidate" && (Context.Sessie.IsKid || !(Context.Sessie.IsBeheerder || diensten.GetRequiredService<IModuleSwitches>().IsSegmentEditor(gebruiker))))
        {
            throw Fouten.Verboden(Context.Sessie.IsKid ? "kid_profile" : "not_editor");
        }

        var item = Module.Vind(id);
        var vrij = Module.Gepubliceerd(id);
        var kandidaat = view == "candidate";
        var modus = item is not null ? Module.Modus(item.Bibliotheek, item.Serie) : Bron.Bibliotheken(video)
            .Select(b => Module.Modus(b, SegmentBibliotheek.SerieVan(video))).FirstOrDefault(m => m != "disabled") ?? "disabled";
        var duur = SegmentBibliotheek.DuurVanItem(video);
        var actueel = item is not null && !item.Wees && !item.Heruitlijnen && Bron.Past(video, item);
        var vakken = kandidaat && item is not null ? item.Kandidaten : actueel ? vrij : [];
        var antwoord = new JsonObject
        {
            ["item_id"] = id, ["media_source_id"] = id, ["duration_s"] = (decimal)duur / TimeSpan.TicksPerSecond,
            ["view"] = view, ["publication"] = modus, ["analysis_state"] = item is null ? "pending" : actueel ? "ok" : "realign_needed",
            ["segments"] = new JsonArray(vakken.Select(s => (JsonNode)Toon(id, s, actueel && vrij.Contains(s))).ToArray()),
            ["protected"] = new JsonArray(),
        };
        if (kandidaat)
        {
            antwoord["recurring_unclassified"] = new JsonArray();
            antwoord["evidence"] = new JsonObject { ["chapters"] = new JsonArray(vakken.Where(v => v.Bron == "chapter").Select(v => (JsonNode?)v.Start).ToArray()) };
        }

        var etag = "\"" + SegmentGegevens.Hash(antwoord.ToJsonString()) + "\"";
        antwoord["etag"] = etag;
        return JlResult.Ok(antwoord, etag);
    }

    /// <summary>Toont of bevestigt een gerichte wijziging van publicatiestand.</summary>
    /// <returns>De aantallen en, bij een voorbeeld, de bevestigingshash.</returns>
    [HttpPut("publication")]
    [JlRoute("segments.publication")]
    public async Task<IActionResult> Publicatie()
    {
        var lezer = new BodyLezer(Context.Body);
        var bib = LeesId(lezer, "library_id", true);
        var serie = LeesId(lezer, "series_id", false);
        var modus = lezer.Tekst("mode", true, 12);
        if (modus is not ("disabled" or "shadow" or "published"))
        {
            lezer.Fout("mode", "invalid_mode", "Gebruik disabled, shadow of published.");
        }

        var reden = lezer.Tekst("override_reason", false, 500)?.Trim();
        var voorbeeld = lezer.Bool("dry_run", true);
        var hash = lezer.Tekst("preview_hash", voorbeeld == false, 64);
        lezer.Klaar();
        return JlResult.Ok(await Dienst.Publiceer(bib!.Value, serie, modus!, reden, voorbeeld!.Value, hash, Context.Wie.Id, HttpContext.RequestAborted).ConfigureAwait(false));
    }

    /// <summary>Geeft de publicatiestanden, mountcontrole en wezenstatus.</summary>
    /// <returns>De actuele status.</returns>
    [HttpGet("status")]
    [JlRoute("segments.status")]
    public IActionResult Status() => JlResult.Ok(Dienst.Status());

    /// <summary>Maakt een getypeerde export zonder accountgegevens.</summary>
    /// <returns>Een herstelbundel.</returns>
    [HttpGet("export")]
    [JlRoute("segments.export")]
    public IActionResult Export() => JlResult.Ok(Module.Exporteer(BibliotheekFilter(), Nu));

    /// <summary>Controleert de inhoud en onthoudt een voorbeeld gedurende vijftien minuten.</summary>
    /// <returns>De hash, aantallen en conflicterende items.</returns>
    [HttpPost("import/preview")]
    [JlRoute("segments.import.preview")]
    public IActionResult ImportVoorbeeld() => JlResult.Ok(Module.OnthoudImport(Context.Body!, Context.Wie.Id, Nu));

    /// <summary>Past de vooraf gecontroleerde import als één transactie toe.</summary>
    /// <returns>Het aantal toegevoegde items.</returns>
    [HttpPost("import/apply")]
    [JlRoute("segments.import.apply")]
    public IActionResult Import()
    {
        var lezer = new BodyLezer(Context.Body);
        var hash = lezer.Tekst("preview_hash", true, 64);
        lezer.Klaar();
        return JlResult.Ok(Module.PasImportToe(hash!, Context.Wie.Id, Nu));
    }

    /// <summary>Telt de wezen binnen de gekozen bibliotheek.</summary>
    /// <returns>Aantallen en de stand van de stroomonderbreker.</returns>
    [HttpGet("orphans")]
    [JlRoute("segments.orphans")]
    public IActionResult Wezen() => JlResult.Ok(Module.Wezen(BibliotheekFilter()));

    /// <summary>Toont of bevestigt het opruimen van geëxporteerde wezen.</summary>
    /// <returns>Het aantal betrokken items.</returns>
    [HttpPost("orphans/cleanup")]
    [JlRoute("segments.orphans.cleanup")]
    public IActionResult Opruimen()
    {
        var lezer = new BodyLezer(Context.Body);
        var id = LeesId(lezer, "export_id", true);
        var voorbeeld = lezer.Bool("dry_run", true);
        var hash = lezer.Tekst("preview_hash", voorbeeld == false, 64);
        lezer.Klaar();
        return JlResult.Ok(Module.RuimWezen(id!.Value, voorbeeld!.Value, hash, Context.Wie.Id, Nu));
    }

    /// <summary>Legt de beheerdersreden vast en geeft het wezenbeheer vrij.</summary>
    /// <returns>De nieuwe stand.</returns>
    [HttpPost("orphans/unfreeze")]
    [JlRoute("segments.orphans.unfreeze")]
    public IActionResult Ontdooi()
    {
        var lezer = new BodyLezer(Context.Body);
        var reden = lezer.Tekst("reason", true, 500);
        if (string.IsNullOrWhiteSpace(reden))
        {
            lezer.Fout("reason", "required", "Geef een reden op.");
        }

        lezer.Klaar();
        Module.Ontdooi(reden!, Context.Wie.Id, Nu);
        return JlResult.Ok(new JsonObject { ["frozen"] = false });
    }

    private static Guid? LeesId(BodyLezer lezer, string veld, bool verplicht)
    {
        var tekst = lezer.Tekst(veld, verplicht, 36);
        if (tekst == null)
        {
            return null;
        }

        if (Guid.TryParse(tekst, out var id) && id != Guid.Empty)
        {
            return id;
        }

        lezer.Fout(veld, "uuid", "Verwacht een niet-lege UUID.");
        return null;
    }

    private Guid? BibliotheekFilter()
    {
        if (!Request.Query.TryGetValue("library_id", out var waarde))
        {
            return null;
        }

        return Guid.TryParse(waarde.ToString(), out var id) && id != Guid.Empty ? id :
            throw Fouten.Validatie(("library_id", "uuid", "Verwacht een bibliotheek-ID."));
    }

    private static JsonObject Toon(Guid id, Tijdvak s, bool gepubliceerd)
    {
        var type = s.Type == MediaSegmentType.Outro ? "credits" : s.Type.ToString().ToLowerInvariant();
        var sleutel = FormattableString.Invariant($"{id:N}/{type}/{s.Start}/{s.Einde}");
        return new JsonObject { ["id"] = Guid.ParseExact(SegmentGegevens.Hash(sleutel)[..32], "N"),
            ["type"] = type, ["jellyfin_type"] = s.Type.ToString(), ["start_ticks"] = s.Start, ["end_ticks"] = s.Einde,
            ["start_s"] = (decimal)s.Start / TimeSpan.TicksPerSecond, ["end_s"] = (decimal)s.Einde / TimeSpan.TicksPerSecond,
            ["source"] = s.Bron, ["confidence"] = s.Zekerheid, ["status"] = gepubliceerd ? "published" : s.Publiceerbaar ? "shadow" : "review" };
    }
}
