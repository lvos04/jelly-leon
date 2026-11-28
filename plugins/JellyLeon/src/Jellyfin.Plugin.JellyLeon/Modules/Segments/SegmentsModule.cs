using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Media;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.JellyLeon.Modules.Segments;

/// <summary>Bron van kandidaten, bevestigingen en gewenste publicaties in segments.db. De server bevat alleen de publicatiekopie.</summary>
internal sealed partial class SegmentsModule : ModuleBasis
{
    public const string ModuleSlug = "segments";
    private const string Schema = """
        CREATE TABLE items(id TEXT PRIMARY KEY, library TEXT NOT NULL, series TEXT NOT NULL, inhoud TEXT NOT NULL,
            gepubliceerd TEXT NOT NULL DEFAULT '[]', afstemmen INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX items_scope ON items(library,series);
        CREATE TABLE scope(library TEXT NOT NULL, series TEXT NOT NULL, mode TEXT NOT NULL, PRIMARY KEY(library,series));
        CREATE TABLE beheer(id INTEGER PRIMARY KEY CHECK(id=1), versie INTEGER NOT NULL, bevroren INTEGER);
        INSERT INTO beheer VALUES(1,0,NULL);
        CREATE TABLE exports(id TEXT PRIMARY KEY, library TEXT, gemaakt INTEGER NOT NULL, inhoud_hash TEXT NOT NULL);
        CREATE TABLE audit(id INTEGER PRIMARY KEY, soort TEXT NOT NULL, actor TEXT NOT NULL, reden TEXT NOT NULL, gemaakt INTEGER NOT NULL);
        """;
    // De meetperiode van de wezenbreker loopt per scan of over het laatste uur.
    private const string Weesvenster = "CREATE TABLE weesmoment(item TEXT PRIMARY KEY, tijd INTEGER NOT NULL);";
    private readonly Core.Outbox.Outbox _outbox;
    private readonly JlPaths _paden;
    private readonly InternalWriteScope _bestanden;

    public SegmentsModule(JlPaths paden, SecretStore geheimen, Core.Outbox.Outbox outbox)
        : base(paden, ModuleSlug, 365, [Schema, Weesvenster], geheimen, [])
    {
        _outbox = outbox;
        _paden = paden;
        _bestanden = new InternalWriteScope(paden);
    }

    public override string Naam => "Intro’s en aftiteling";
    public override IReadOnlyList<string> ItemTypes => [];
    public override IReadOnlyList<string> JobTypes => [];
    public override IReadOnlyList<string> EventTypes => ["media.segment_orphans.frozen"];
    public override IReadOnlyList<PersoonsgegevenRegel> Persoonsgegevens => [
        new(ModuleSlug, "audit", "sessiepseudoniem van beheerder", "publicatie en wezenbeheer verantwoorden", "365 dagen")];

    public override IReadOnlyList<JsonObject> Items(string type, DateTimeOffset nu) => [];
    // De audit gebruikt uitsluitend het bestaande sessiepseudoniem. Het formaat draagt geen account-ID.
    public override int VerwijderGebruiker(Guid gebruiker) => 0;
    public override int TelGebruiker(Guid gebruiker) => 0;
    public override JsonObject Status(DateTimeOffset nu) => new() { ["module"] = Slug, ["orphans"] = Wezen(null) };

    internal static string Id(Guid? id) => id?.ToString("N") ?? string.Empty;
    internal static string Schrijf<T>(T data) => JsonSerializer.Serialize(data, SegmentGegevens.Json);
    private static T Lees<T>(object? waarde) => JsonSerializer.Deserialize<T>((string)waarde!, SegmentGegevens.Json)!;
    private static void Verschuif(SqliteConnection v) => JlDatabase.Voer(v, "UPDATE beheer SET versie=versie+1 WHERE id=1");
    internal long Versie => Db.Met(v => JlDatabase.Getal(v, "SELECT versie FROM beheer"));
    internal bool Bevroren => Db.Met(v => JlDatabase.Getal(v, "SELECT bevroren IS NOT NULL FROM beheer")) != 0;
    internal string Modus(Guid bibliotheek, Guid? serie) => Db.Met(v => Modus(v, bibliotheek, serie));

    private static string Modus(SqliteConnection v, Guid bibliotheek, Guid? serie) =>
        (string?)JlDatabase.Scalar(v, "SELECT mode FROM scope WHERE library=$l AND series IN ('',$s) ORDER BY length(series) DESC LIMIT 1",
            ("$l", Id(bibliotheek)), ("$s", Id(serie))) ?? "disabled";

    internal bool BibliotheekAan(Guid bib) => Db.Met(v => JlDatabase.Getal(v,
        "SELECT EXISTS(SELECT 1 FROM scope WHERE library=$l AND mode <> 'disabled')", ("$l", Id(bib)))) != 0;

    internal SegmentItem? Vind(Guid id) => Db.Met(v => Vind(v, id));
    private static SegmentItem? Vind(SqliteConnection v, Guid id) =>
        JlDatabase.Scalar(v, "SELECT inhoud FROM items WHERE id=$id", ("$id", Id(id))) is string s ? Lees<SegmentItem>(s) : null;

    internal IReadOnlyList<SegmentItem> Selectie(Guid? bibliotheek = null, Guid? serie = null) => Db.Met(v => Selectie(v, bibliotheek, serie));
    private static List<SegmentItem> Selectie(SqliteConnection v, Guid? bibliotheek, Guid? serie) =>
        JlDatabase.Rijen(v, "SELECT inhoud FROM items WHERE ($l IS NULL OR library=$l) AND ($s IS NULL OR series=$s) ORDER BY id",
            ("$l", bibliotheek?.ToString("N")), ("$s", serie?.ToString("N"))).Select(r => Lees<SegmentItem>(r[0])).ToList();

    internal Tijdvak[] Gepubliceerd(Guid item) => Db.Met(v =>
        JlDatabase.Scalar(v, "SELECT gepubliceerd FROM items WHERE id=$id", ("$id", Id(item))) is string s ? Lees<Tijdvak[]>(s) : []);

    internal void BewaarAnalyse(SegmentItem item)
    {
        item.Controleer();
        Db.Transactioneel(v =>
        {
            var oud = Vind(v, item.ItemId);
            if (oud is null && item.Herkomst != null && (!item.Serie.HasValue || item.Aflevering.HasValue))
            {
                // Na een container- of padwissel kan het server-ID veranderen. Bij één passend extern aflevering-ID
                // verhuist het mensenwerk naar review. Nieuwe publicatie vraagt heruitlijning of bevestiging.
                var passend = Selectie(v, item.Bibliotheek, item.Serie).Where(i => i.Wees &&
                    i.Serie == item.Serie && i.Seizoen == item.Seizoen && i.Aflevering == item.Aflevering && i.Herkomst == item.Herkomst &&
                    Math.Abs((double)i.Duur - item.Duur) <= i.Duur * .01).Take(2).ToArray();
                if (passend.Length > 0 && JlDatabase.Getal(v, "SELECT bevroren IS NOT NULL FROM beheer") != 0)
                {
                    return;
                }

                if (passend.Length == 1)
                {
                    oud = passend[0] with { ItemId = item.ItemId, Wees = false, Heruitlijnen = true };
                    JlDatabase.Voer(v, "UPDATE items SET id=$nieuw WHERE id=$oud",
                        ("$nieuw", Id(item.ItemId)), ("$oud", Id(passend[0].ItemId)));
                }
            }

            if (oud is { Wees: true } && JlDatabase.Getal(v, "SELECT bevroren IS NOT NULL FROM beheer") != 0)
            {
                return;
            }

            var gewijzigd = oud is not null && (oud.Mtime != item.Mtime || oud.Duur != item.Duur || oud.Heruitlijnen || oud.Wees);
            if (gewijzigd && oud is not null &&
                (oud.Bevestigd || oud.Kandidaten.Any(s => s.Bron is "manual" or "confirmed")))
            {
                // Bewaar ook correcties die door een kortere vervanging nu buiten de nieuwe duur vallen.
                SchrijfItem(v, oud with { Heruitlijnen = true, Wees = false, Mtime = item.Mtime });
                TrekIn(v, oud.ItemId);
            }
            else if (oud is not null && !gewijzigd)
            {
                return;
            }
            else
            {
                SchrijfItem(v, item);
                var modus = Modus(v, item.Bibliotheek, item.Serie);
                var steekproef = modus == "published" && (item.Bevestigd || (item.Serie.HasValue &&
                    Steekproef(Selectie(v, item.Bibliotheek, item.Serie).Where(i => i.Seizoen == item.Seizoen)) >= 3));
                var doel = steekproef ? Doel(item, modus) : [];
                JlDatabase.Voer(v, "UPDATE items SET gepubliceerd=$set, afstemmen=1 WHERE id=$id",
                    ("$set", Schrijf(doel)), ("$id", Id(item.ItemId)));
            }

            Verschuif(v);
        });
    }

    private static void SchrijfItem(SqliteConnection v, SegmentItem item) => JlDatabase.Voer(v,
        "INSERT INTO items(id,library,series,inhoud) VALUES($id,$l,$s,$j) ON CONFLICT(id) DO UPDATE SET library=excluded.library,series=excluded.series,inhoud=excluded.inhoud",
        ("$id", Id(item.ItemId)), ("$l", Id(item.Bibliotheek)), ("$s", Id(item.Serie)), ("$j", Schrijf(item)));

    internal void Verouder(Guid id) => Db.Transactioneel(v =>
    {
        var item = Vind(v, id);
        if (item is null || item.Heruitlijnen)
        {
            return;
        }

        SchrijfItem(v, item with { Heruitlijnen = true });
        TrekIn(v, id);
        Verschuif(v);
    });

    internal bool HeeftDatabase => File.Exists(_paden.ModuleDb(ModuleSlug));

    internal void RuimCache(Guid id)
    {
        // Alleen het afgeleide cachebestand met een door de server geleverd item-ID.
        var cache = Path.Combine(_paden.CacheRoot, ModuleSlug, Id(id) + ".features");
        if (File.Exists(cache))
        {
            _bestanden.Verwijder(cache);
        }
    }

    private static void TrekIn(SqliteConnection v, Guid id) => JlDatabase.Voer(v,
        "UPDATE items SET gepubliceerd='[]', afstemmen=1 WHERE id=$id", ("$id", Id(id)));

    internal void VerwerkWezen(IReadOnlySet<Guid> verdwenen, DateTimeOffset nu)
    {
        var incident = Db.Transactioneel(v =>
        {
            var items = Selectie(v, null, null);
            var nieuw = items.Where(i => !i.Wees && verdwenen.Contains(i.ItemId)).ToArray();
            if (nieuw.Length == 0)
            {
                return false;
            }

            foreach (var item in nieuw)
            {
                JlDatabase.Voer(v, "INSERT OR REPLACE INTO weesmoment VALUES($id,$nu)", ("$id", Id(item.ItemId)), ("$nu", nu.ToUnixTimeSeconds()));
                SchrijfItem(v, item with { Wees = true });
                TrekIn(v, item.ItemId);
            }

            JlDatabase.Voer(v, "DELETE FROM weesmoment WHERE tijd<$grens", ("$grens", nu.AddHours(-1).ToUnixTimeSeconds()));
            var bevries = OrphanBreaker.MoetBevriezen(items.Count, checked((int)JlDatabase.Getal(v, "SELECT COUNT(*) FROM weesmoment"))) &&
                JlDatabase.Voer(v, "UPDATE beheer SET bevroren=$nu WHERE bevroren IS NULL", ("$nu", nu.ToUnixTimeSeconds())) > 0;
            Verschuif(v);
            return bevries;
        });
        if (incident)
        {
            _outbox.Meld(Slug, "media.segment_orphans.frozen", "segment_library", "segments", new JsonObject { ["count"] = verdwenen.Count });
        }
    }

    internal JsonObject Wezen(Guid? bib) => Db.Met(v =>
    {
        var sinds = JlDatabase.Scalar(v, "SELECT bevroren FROM beheer") as long?;
        var aantal = Selectie(v, bib, null).Count(i => i.Wees);
        return new JsonObject { ["count"] = aantal, ["by_reason"] = new JsonObject { ["missing_item"] = aantal },
            ["frozen"] = sinds.HasValue, ["frozen_since"] = sinds.HasValue ? DateTimeOffset.FromUnixTimeSeconds(sinds.Value).ToString("O", CultureInfo.InvariantCulture) : null };
    });
}
