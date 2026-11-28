using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.JellyLeon.Core.Modules;

/// <summary>
/// Gedeelde basis van een module: het eigen SQLite-bestand onder <c>jelly-leon/&lt;slug&gt;/</c> en de instellingen
/// met ETag. Zo geeft elke module dezelfde fout voor dezelfde situatie (één catalogus, JLT-68).
/// </summary>
internal abstract class ModuleBasis : ModuleOverdracht, IJellyLeonModule
{
    private const string InstellingenTabel =
        "CREATE TABLE instellingen(id INTEGER PRIMARY KEY CHECK(id = 1), bewaar_dagen INTEGER NOT NULL, versie INTEGER NOT NULL);";

    protected ModuleBasis(JlPaths paden, string slug, int standaardBewaarDagen, IEnumerable<string> migraties, SecretStore geheimen,
        ModuleTabel[] tabellen, Action<SqliteConnection, DateTimeOffset>? voorExport = null)
    {
        Slug = slug;
        StandaardBewaarDagen = standaardBewaarDagen;
        Db = new JlDatabase(paden, paden.ModuleDb(slug), [InstellingenTabel, .. migraties]);
        Gegevensbeheer = new ModuleGegevensbeheer(Db, paden, slug, geheimen, tabellen, voorExport);
    }

    public override string Slug { get; }

    public abstract string Naam { get; }

    public abstract IReadOnlyList<string> ItemTypes { get; }

    public abstract IReadOnlyList<string> EventTypes { get; }

    public abstract IReadOnlyList<string> JobTypes { get; }

    public abstract IReadOnlyList<PersoonsgegevenRegel> Persoonsgegevens { get; }

    public ModuleGegevensbeheer Gegevensbeheer { get; }

    protected JlDatabase Db { get; }

    protected int StandaardBewaarDagen { get; }

    public abstract IReadOnlyList<JsonObject> Items(string type, DateTimeOffset nu);

    public abstract int VerwijderGebruiker(Guid gebruiker);

    public abstract int TelGebruiker(Guid gebruiker);

    public void WisSporen() => Db.WisSporen();

    public abstract JsonObject Status(DateTimeOffset nu);

    public void ControleerOpslag() => Db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM instellingen"));

    protected override JsonObject ExportInhoud() => new()
    {
        ["module"] = Slug,
        ["schema_version"] = "1.0",
        ["instellingen"] = LeesInstellingen().Waarde,
    };

    protected override Herstelplan LeesHerstel(BodyLezer lezer)
    {
        if (lezer.Node("instellingen", true) is not JsonObject instellingen)
        {
            throw Fouten.Validatie(("instellingen", "type", "Verwacht de module-instellingen."));
        }

        var velden = new BodyLezer(instellingen);
        var dagen = velden.Geheel("bewaar_dagen", true, 1, 365);
        velden.Klaar();
        lezer.Klaar();
        var verwacht = Db.Bestaat ? LeesInstellingen().Etag : Etag(0);
        return new Herstelplan(new JsonObject { ["instellingen"] = 1 }, () => Db.MetImportkopie(
            v => ControleerVersie(v, verwacht),
            v => ZetBewaarDagen(v, dagen!.Value)));
    }

    public (JsonObject Waarde, string Etag) LeesInstellingen() => Db.Met(v =>
    {
        var rij = JlDatabase.Rijen(v, "SELECT bewaar_dagen, versie FROM instellingen WHERE id = 1").FirstOrDefault();
        var dagen = rij is null ? StandaardBewaarDagen : Convert.ToInt32(rij[0], CultureInfo.InvariantCulture);
        var versie = rij is null ? 0 : Convert.ToInt64(rij[1], CultureInfo.InvariantCulture);
        return (new JsonObject { ["bewaar_dagen"] = dagen }, Etag(versie));
    });

    public (JsonObject Waarde, string Etag) SchrijfInstellingen(int bewaarDagen, string ifMatch) => Db.Transactioneel(v =>
    {
        ControleerVersie(v, ifMatch);
        var versie = ZetBewaarDagen(v, bewaarDagen);
        return (new JsonObject { ["bewaar_dagen"] = bewaarDagen }, Etag(versie));
    });

    private void ControleerVersie(SqliteConnection v, string verwacht)
    {
        var versie = JlDatabase.Getal(v, "SELECT COALESCE((SELECT versie FROM instellingen WHERE id = 1), 0)");
        if (!string.Equals(verwacht, Etag(versie), StringComparison.Ordinal))
        {
            throw Fouten.PreconditieMislukt(Etag(versie));
        }
    }

    private static long ZetBewaarDagen(SqliteConnection v, int bewaarDagen) =>
        JlDatabase.Getal(v, "INSERT INTO instellingen(id, bewaar_dagen, versie) VALUES(1, $d, 1) "
            + "ON CONFLICT(id) DO UPDATE SET bewaar_dagen = $d, versie = instellingen.versie + 1 RETURNING versie",
            ("$d", bewaarDagen));

    protected int BewaarDagen() => LeesInstellingen().Waarde["bewaar_dagen"]!.GetValue<int>();

    private string Etag(long versie) => "\"" + Slug + "-" + versie.ToString(CultureInfo.InvariantCulture) + "\"";
}
