using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Modules.Quality;

/// <summary>
/// Module Quality (F4, prototype van golf 1): bewaart bevindingen over mediabestanden (alleen een code en een
/// ondoorzichtige verwijzing) en wie een bevinding heeft onderdrukt. Wijzigt nooit een mediabestand of de bibliotheek.
/// </summary>
internal sealed class QualityModule : ModuleBasis
{
    public const string ModuleSlug = "quality";
    public const string ScanJob = "quality.scan";
    private static readonly string[] _migraties =
    [
        "CREATE TABLE findings(id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT NOT NULL, code TEXT NOT NULL, ernst TEXT NOT NULL, gemaakt INTEGER NOT NULL, UNIQUE(item, code));"
        + "CREATE TABLE suppressions(item TEXT NOT NULL, code TEXT NOT NULL, gebruiker TEXT NOT NULL, gemaakt INTEGER NOT NULL, PRIMARY KEY(item, code));"
        + "CREATE TABLE scans(id INTEGER PRIMARY KEY AUTOINCREMENT, klaar INTEGER NOT NULL, bestanden INTEGER NOT NULL, bevindingen INTEGER NOT NULL);",
    ];

    private static readonly string[] _ernst = ["info", "waarschuwing", "fout"];
    private readonly SecretStore _geheimen;
    private readonly Core.Outbox.Outbox _outbox;

    public QualityModule(JlPaths paden, SecretStore geheimen, Core.Outbox.Outbox outbox)
        : base(paden, ModuleSlug, 90, _migraties)
    {
        _geheimen = geheimen;
        _outbox = outbox;
    }

    public override string Naam => "Kwaliteitscontrole";

    public override IReadOnlyList<string> ItemTypes { get; } = ["quality_summary", "quality_finding"];

    public override IReadOnlyList<string> EventTypes { get; } = ["media.quality_scan.completed"];

    public override IReadOnlyList<string> JobTypes { get; } = [ScanJob];

    public override IReadOnlyList<PersoonsgegevenRegel> Persoonsgegevens { get; } =
    [
        new(ModuleSlug, "suppressions", "account-ID van wie een bevinding heeft onderdrukt", "herleidbaarheid van onderdrukte bevindingen", "tot het account is verwijderd"),
    ];

    /// <summary>De ondoorzichtige verwijzing naar een bibliotheekitem (niet terug te rekenen).</summary>
    public string ItemVerwijzing(Guid item) => "o_" + _geheimen.OpaakId("item", item.ToString("N"));

    /// <summary>Legt een bevinding vast; dezelfde bevinding op hetzelfde item telt één keer.</summary>
    public bool MeldBevinding(Guid item, string code, string ernst, DateTimeOffset nu)
    {
        if (!_ernst.Contains(ernst, StringComparer.Ordinal) || !Core.Outbox.InhoudsBewaker.VeiligeTekst(code))
        {
            throw new ArgumentException("Een bevinding heeft een vaste code en een ernst uit info, waarschuwing of fout.", nameof(code));
        }

        return Db.Met(v => JlDatabase.Voer(
            v,
            "INSERT OR IGNORE INTO findings(item, code, ernst, gemaakt) VALUES($i, $c, $e, $nu)",
            ("$i", ItemVerwijzing(item)),
            ("$c", code),
            ("$e", ernst),
            ("$nu", nu.ToUnixTimeSeconds()))) > 0;
    }

    /// <summary>Onderdrukt een bevinding namens een account.</summary>
    public void Onderdruk(Guid item, string code, Guid gebruiker, DateTimeOffset nu) => Db.Met(v => JlDatabase.Voer(
        v,
        "INSERT OR REPLACE INTO suppressions(item, code, gebruiker, gemaakt) VALUES($i, $c, $g, $nu)",
        ("$i", ItemVerwijzing(item)),
        ("$c", code),
        ("$g", gebruiker.ToString("N")),
        ("$nu", nu.ToUnixTimeSeconds())));

    /// <summary>Sluit een scan af en meldt het resultaat (alleen aantallen) aan de outbox.</summary>
    public long RondScanAf(int bestanden, int bevindingen, DateTimeOffset nu)
    {
        var grens = nu.ToUnixTimeSeconds() - (BewaarDagen() * 86400L);
        var id = Db.Met(v =>
        {
            JlDatabase.Voer(v, "DELETE FROM scans WHERE klaar < $g", ("$g", grens));
            JlDatabase.Voer(v, "INSERT INTO scans(klaar, bestanden, bevindingen) VALUES($nu, $b, $f)", ("$nu", nu.ToUnixTimeSeconds()), ("$b", bestanden), ("$f", bevindingen));
            return JlDatabase.Getal(v, "SELECT last_insert_rowid()");
        });
        _outbox.Meld(ModuleSlug, "media.quality_scan.completed", "quality_scan", "scan-" + id.ToString(CultureInfo.InvariantCulture), new JsonObject { ["bestanden"] = bestanden, ["bevindingen"] = bevindingen });
        return id;
    }

    public override IReadOnlyList<JsonObject> Items(string type, DateTimeOffset nu)
    {
        if (type == "quality_summary")
        {
            return [Samenvatting(nu, "totaal")];
        }

        return Db.Met(v => JlDatabase.Rijen(
                v,
                "SELECT f.id, f.item, f.code, f.ernst, f.gemaakt, EXISTS(SELECT 1 FROM suppressions s WHERE s.item = f.item AND s.code = f.code) FROM findings f ORDER BY f.id")
            .Select(r => new JsonObject
            {
                ["id"] = "f-" + Convert.ToInt64(r[0], CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture),
                ["observed_at"] = Core.Outbox.Outbox.Iso(nu),
                ["item"] = (string)r[1]!,
                ["code"] = (string)r[2]!,
                ["ernst"] = (string)r[3]!,
                ["gevonden_op"] = Core.Outbox.Outbox.Iso(DateTimeOffset.FromUnixTimeSeconds(Convert.ToInt64(r[4], CultureInfo.InvariantCulture))),
                ["onderdrukt"] = Convert.ToInt64(r[5], CultureInfo.InvariantCulture) == 1,
            }).ToList());
    }

    public override JsonObject Status(DateTimeOffset nu)
    {
        var status = Samenvatting(nu, "status");
        status.Remove("id");
        status["module"] = ModuleSlug;
        status["bewaar_dagen"] = BewaarDagen();
        return status;
    }

    public override int VerwijderGebruiker(Guid gebruiker) =>
        Db.Met(v => JlDatabase.Voer(v, "DELETE FROM suppressions WHERE gebruiker = $g", ("$g", gebruiker.ToString("N"))));

    public override int TelGebruiker(Guid gebruiker) =>
        (int)Db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM suppressions WHERE gebruiker = $g", ("$g", gebruiker.ToString("N"))));

    public override JsonObject Exporteer()
    {
        var export = base.Exporteer();
        export["bevindingen"] = Db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM findings"));
        export["onderdrukt"] = Db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM suppressions"));
        return export;
    }

    private JsonObject Samenvatting(DateTimeOffset nu, string id) => Db.Met(v =>
    {
        var perCode = new JsonObject();
        foreach (var rij in JlDatabase.Rijen(v, "SELECT code, COUNT(*) FROM findings GROUP BY code ORDER BY code"))
        {
            perCode[(string)rij[0]!] = Convert.ToInt64(rij[1], CultureInfo.InvariantCulture);
        }

        var laatste = JlDatabase.Scalar(v, "SELECT MAX(klaar) FROM scans");
        return new JsonObject
        {
            ["id"] = id,
            ["observed_at"] = Core.Outbox.Outbox.Iso(nu),
            ["bevindingen"] = JlDatabase.Getal(v, "SELECT COUNT(*) FROM findings"),
            ["onderdrukt"] = JlDatabase.Getal(v, "SELECT COUNT(*) FROM suppressions"),
            ["per_code"] = perCode,
            ["scans"] = JlDatabase.Getal(v, "SELECT COUNT(*) FROM scans"),
            ["laatste_scan"] = laatste is null ? null : Core.Outbox.Outbox.Iso(DateTimeOffset.FromUnixTimeSeconds(Convert.ToInt64(laatste, CultureInfo.InvariantCulture))),
        };
    });
}
