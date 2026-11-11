using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Core.Modules;

/// <summary>
/// Gedeelde basis van een module: het eigen SQLite-bestand onder <c>jelly-leon/&lt;slug&gt;/</c> en de instellingen
/// met ETag. Zo geeft elke module dezelfde fout voor dezelfde situatie (één catalogus, JLT-68).
/// </summary>
internal abstract class ModuleBasis : IJellyLeonModule
{
    private const string InstellingenTabel =
        "CREATE TABLE instellingen(id INTEGER PRIMARY KEY CHECK(id = 1), bewaar_dagen INTEGER NOT NULL, versie INTEGER NOT NULL);";

    protected ModuleBasis(JlPaths paden, string slug, int standaardBewaarDagen, IEnumerable<string> migraties)
    {
        Slug = slug;
        StandaardBewaarDagen = standaardBewaarDagen;
        Db = new JlDatabase(paden.ModuleDb(slug), [InstellingenTabel, .. migraties]);
    }

    public string Slug { get; }

    public abstract string Naam { get; }

    public abstract IReadOnlyList<string> ItemTypes { get; }

    public abstract IReadOnlyList<string> EventTypes { get; }

    public abstract IReadOnlyList<string> JobTypes { get; }

    public abstract IReadOnlyList<PersoonsgegevenRegel> Persoonsgegevens { get; }

    protected JlDatabase Db { get; }

    protected int StandaardBewaarDagen { get; }

    public abstract IReadOnlyList<JsonObject> Items(string type, DateTimeOffset nu);

    public abstract int VerwijderGebruiker(Guid gebruiker);

    public abstract int TelGebruiker(Guid gebruiker);

    public abstract JsonObject Status(DateTimeOffset nu);

    public void ControleerOpslag() => Db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM instellingen"));

    public virtual JsonObject Exporteer() => new()
    {
        ["module"] = Slug,
        ["schema_version"] = "1.0",
        ["instellingen"] = LeesInstellingen().Waarde,
    };

    public (JsonObject Waarde, string Etag) LeesInstellingen() => Db.Met(v =>
    {
        var rij = JlDatabase.Rijen(v, "SELECT bewaar_dagen, versie FROM instellingen WHERE id = 1").FirstOrDefault();
        var dagen = rij is null ? StandaardBewaarDagen : Convert.ToInt32(rij[0], CultureInfo.InvariantCulture);
        var versie = rij is null ? 0 : Convert.ToInt64(rij[1], CultureInfo.InvariantCulture);
        return (new JsonObject { ["bewaar_dagen"] = dagen }, Etag(versie));
    });

    public (JsonObject Waarde, string Etag) SchrijfInstellingen(int bewaarDagen, string ifMatch) => Db.Met(v =>
    {
        var versie = JlDatabase.Getal(v, "SELECT COALESCE((SELECT versie FROM instellingen WHERE id = 1), 0)");
        if (!string.Equals(ifMatch, Etag(versie), StringComparison.Ordinal))
        {
            throw Fouten.PreconditieMislukt(Etag(versie));
        }

        JlDatabase.Voer(
            v,
            "INSERT INTO instellingen(id, bewaar_dagen, versie) VALUES(1, $d, $v) ON CONFLICT(id) DO UPDATE SET bewaar_dagen = $d, versie = $v",
            ("$d", bewaarDagen),
            ("$v", versie + 1));
        return (new JsonObject { ["bewaar_dagen"] = bewaarDagen }, Etag(versie + 1));
    });

    protected int BewaarDagen() => LeesInstellingen().Waarde["bewaar_dagen"]!.GetValue<int>();

    private string Etag(long versie) => "\"" + Slug + "-" + versie.ToString(CultureInfo.InvariantCulture) + "\"";
}
