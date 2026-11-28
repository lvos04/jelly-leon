using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.JellyLeon.Modules.Segments;

internal sealed partial class SegmentsModule
{
    internal sealed record Bundel(int SchemaVersion, Guid ExportId, SegmentItem[] Items);
    internal sealed record ImportVoorbeeld(string Actor, long Versie, DateTimeOffset Vervalt, SegmentItem[] Inhoud);
    private readonly Dictionary<string, ImportVoorbeeld> _voorbeelden = new(StringComparer.Ordinal);
    private readonly object _voorbeeldSlot = new();

    internal List<Guid> Bibliotheken() => Db.Met(v => JlDatabase.Rijen(v, "SELECT DISTINCT library FROM scope ORDER BY library")
        .Select(r => Guid.Parse((string)r[0]!)).ToList());

    internal List<Guid> TeSynchroniseren() => Db.Met(v => JlDatabase.Rijen(v, "SELECT id FROM items WHERE afstemmen=1 ORDER BY id")
        .Select(r => Guid.Parse((string)r[0]!)).ToList());

    internal void Afgestemd(Guid id, Tijdvak[] set) => Db.Met(v => JlDatabase.Voer(v,
        "UPDATE items SET afstemmen=0 WHERE id=$id AND gepubliceerd=$set", ("$id", Id(id)), ("$set", Schrijf(set))));

    internal static int Steekproef(IEnumerable<SegmentItem> items)
    {
        // Verschillende afleveringen per serie/seizoen. Alternatieve bestandsversies tellen één keer.
        var groepen = items.Where(i => !i.Wees && !i.Heruitlijnen).GroupBy(i => (i.Serie, i.Seizoen));
        return groepen.Select(g => g.Key.Serie.HasValue
            ? g.Where(i => i.Bevestigd && i.Aflevering.HasValue).Select(i => i.Aflevering).Distinct().Count()
            : (g.All(i => i.Bevestigd) ? 3 : 0)).DefaultIfEmpty(0).Min();
    }

    internal static Tijdvak[] Doel(SegmentItem item, string modus) => modus == "published" && !item.Heruitlijnen && !item.Wees
        ? item.Kandidaten.Where(v => v.Publiceerbaar).ToArray() : [];

    internal void LegPublicatieVast(Guid bibliotheek, Guid? serie, string modus, long versie, string? reden, string actor, DateTimeOffset nu)
    {
        Db.Transactioneel(v =>
        {
            if (versie != JlDatabase.Getal(v, "SELECT versie FROM beheer"))
            {
                throw Fouten.Conflict("preview_changed");
            }

            var items = Selectie(v, bibliotheek, serie);
            if (modus == "published" && string.IsNullOrWhiteSpace(reden) && Steekproef(items) < 3)
            {
                throw Fouten.Conflict("qc_sample_incomplete");
            }

            // Een nieuwe stand voor de hele bibliotheek vervangt ook eerder ingestelde uitzonderingen per serie.
            if (!serie.HasValue)
            {
                JlDatabase.Voer(v, "DELETE FROM scope WHERE library=$l", ("$l", Id(bibliotheek)));
            }

            JlDatabase.Voer(v, "INSERT INTO scope(library,series,mode) VALUES($l,$s,$m) ON CONFLICT(library,series) DO UPDATE SET mode=excluded.mode",
                ("$l", Id(bibliotheek)), ("$s", Id(serie)), ("$m", modus));
            foreach (var item in items)
            {
                JlDatabase.Voer(v, "UPDATE items SET gepubliceerd=$j, afstemmen=1 WHERE id=$id",
                    ("$j", Schrijf(Doel(item, modus))), ("$id", Id(item.ItemId)));
            }

            if (reden != null)
            {
                Audit(v, "publicatie", actor, reden, nu);
            }

            Verschuif(v);
        });
    }

    internal void AllesIntrekken() => Db.Transactioneel(v =>
    {
        var aantal = JlDatabase.Voer(v, "UPDATE scope SET mode='shadow' WHERE mode='published'");
        aantal += JlDatabase.Voer(v, "UPDATE items SET gepubliceerd='[]', afstemmen=1 WHERE gepubliceerd<>'[]'");
        if (aantal > 0)
        {
            Verschuif(v);
        }
    });

    private static void Audit(SqliteConnection v, string soort, string actor, string reden, DateTimeOffset nu)
    {
        JlDatabase.Voer(v, "DELETE FROM audit WHERE gemaakt<$grens", ("$grens", nu.AddDays(-365).ToUnixTimeSeconds()));
        JlDatabase.Voer(v, "INSERT INTO audit(soort,actor,reden,gemaakt) VALUES($s,$a,$r,$t)",
            ("$s", soort), ("$a", actor), ("$r", reden), ("$t", nu.ToUnixTimeSeconds()));
    }

    internal JsonObject Exporteer(Guid? bib, DateTimeOffset nu) => Db.Transactioneel(v =>
    {
        var items = Selectie(v, bib, null).ToArray();
        var bundel = new Bundel(1, Guid.NewGuid(), items);
        JlDatabase.Voer(v, "DELETE FROM exports WHERE gemaakt<$t", ("$t", nu.AddHours(-24).ToUnixTimeSeconds()));
        JlDatabase.Voer(v, "INSERT INTO exports VALUES($id,$l,$t,$hash)", ("$id", Id(bundel.ExportId)),
            ("$l", bib?.ToString("N")), ("$t", nu.ToUnixTimeSeconds()), ("$hash", SegmentGegevens.Hash(Schrijf(items))));
        return JsonSerializer.SerializeToNode(bundel, SegmentGegevens.Json)!.AsObject();
    });

    internal JsonObject OnthoudImport(JsonObject body, string actor, DateTimeOffset nu)
    {
        Bundel? bundel;
        try
        {
            bundel = body.Deserialize<Bundel>(SegmentGegevens.Json);
        }
        catch (JsonException)
        {
            throw Fouten.Validatie(("bundle", "invalid_bundle", "De bundel voldoet niet aan het exportschema."));
        }

        if (bundel?.SchemaVersion != 1 || bundel.ExportId == Guid.Empty || bundel.Items is null || bundel.Items.Any(i => i is null) ||
            bundel.Items.Select(i => i.ItemId).Distinct().Count() != bundel.Items.Length)
        {
            throw Fouten.Validatie(("bundle", "invalid_bundle", "Controleer versie, export-ID en unieke item-ID’s."));
        }

        foreach (var item in bundel.Items)
        {
            item.Controleer();
        }

        var (versie, conflicten) = Db.Met(v => (JlDatabase.Getal(v, "SELECT versie FROM beheer"),
            bundel.Items.Where(i => Vind(v, i.ItemId) is { } oud && Schrijf(oud) != Schrijf(i)).Select(i => i.ItemId).ToArray()));
        var vervalt = nu.AddMinutes(15);
        var hash = SegmentGegevens.Hash(Schrijf(new { actor, versie, bundel }));
        lock (_voorbeeldSlot)
        {
            foreach (var sleutel in _voorbeelden.Where(p => p.Value.Vervalt <= nu).Select(p => p.Key).ToArray())
            {
                _voorbeelden.Remove(sleutel);
            }

            if (_voorbeelden.Count >= 8 && !_voorbeelden.ContainsKey(hash))
            {
                throw Fouten.TeVeelVerzoeken(60);
            }

            _voorbeelden[hash] = new ImportVoorbeeld(actor, versie, vervalt, bundel.Items);
        }

        return new JsonObject { ["preview_hash"] = hash, ["counts"] = new JsonObject { ["items"] = bundel.Items.Length },
            ["conflicts"] = JsonSerializer.SerializeToNode(conflicten), ["expires_at"] = vervalt.ToString("O", CultureInfo.InvariantCulture) };
    }

    internal JsonObject PasImportToe(string hash, string actor, DateTimeOffset nu)
    {
        lock (_voorbeeldSlot)
        {
            if (!_voorbeelden.TryGetValue(hash, out var preview) || preview.Actor != actor || preview.Vervalt <= nu)
            {
                throw Fouten.Conflict("import_conflict");
            }

            var aantal = Db.Transactioneel(v =>
            {
                if (JlDatabase.Getal(v, "SELECT versie FROM beheer") != preview.Versie)
                {
                    throw Fouten.Conflict("import_conflict");
                }

                var nieuw = 0;
                foreach (var item in preview.Inhoud)
                {
                    var oud = Vind(v, item.ItemId);
                    if (oud is not null && Schrijf(oud) != Schrijf(item))
                    {
                        throw Fouten.Conflict("import_conflict");
                    }

                    if (oud is null)
                    {
                        SchrijfItem(v, item);
                        nieuw++;
                    }
                }

                if (nieuw > 0)
                {
                    Verschuif(v);
                }

                return nieuw;
            });
            _voorbeelden.Remove(hash);
            return new JsonObject { ["applied"] = new JsonObject { ["items"] = aantal } };
        }
    }

    internal JsonObject RuimWezen(Guid exportId, bool voorbeeld, string? hash, string actor, DateTimeOffset nu) => Db.Transactioneel(v =>
    {
        if (JlDatabase.Getal(v, "SELECT bevroren IS NOT NULL FROM beheer") != 0)
        {
            throw Fouten.Conflict("orphans_frozen");
        }

        var export = JlDatabase.Rijen(v, "SELECT library,inhoud_hash FROM exports WHERE id=$id AND gemaakt BETWEEN $van AND $tot",
            ("$id", Id(exportId)), ("$van", nu.AddHours(-24).ToUnixTimeSeconds()), ("$tot", nu.ToUnixTimeSeconds())).SingleOrDefault();
        if (export is null)
        {
            throw Fouten.Conflict("export_required");
        }

        var items = Selectie(v, export[0] is string id ? Guid.Parse(id) : null, null);
        if ((string)export[1]! != SegmentGegevens.Hash(Schrijf(items)))
        {
            throw Fouten.Conflict("export_required");
        }

        var wezen = items.Where(i => i.Wees).Select(i => i.ItemId).ToArray();
        var actueel = SegmentGegevens.Hash(Schrijf(new { exportId, actor, versie = JlDatabase.Getal(v, "SELECT versie FROM beheer"), wezen }));
        if (voorbeeld)
        {
            return new JsonObject { ["would_delete"] = wezen.Length, ["preview_hash"] = actueel };
        }

        if (hash != actueel)
        {
            throw Fouten.Conflict("preview_changed");
        }

        foreach (var wees in wezen)
        {
            JlDatabase.Voer(v, "DELETE FROM items WHERE id=$id", ("$id", Id(wees)));
        }

        Audit(v, "opruimen", actor, Id(exportId), nu);
        Verschuif(v);
        return new JsonObject { ["deleted"] = wezen.Length };
    });

    internal void Ontdooi(string reden, string actor, DateTimeOffset nu) => Db.Transactioneel(v =>
    {
        JlDatabase.Voer(v, "UPDATE beheer SET bevroren=NULL");
        JlDatabase.Voer(v, "DELETE FROM weesmoment");
        Audit(v, "ontdooien", actor, reden, nu);
        Verschuif(v);
    });
}
