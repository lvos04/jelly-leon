using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json.Nodes;
using System.Threading;
using Jellyfin.Plugin.JellyLeon.Core.Idempotency;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.JellyLeon.Core.Modules;

/// <summary>Vaste tabel en kolommen uit de migraties van één module, in sleutelvolgorde.</summary>
internal sealed record ModuleTabel(string Naam, params string[] Kolommen);

/// <summary>De beheerexport en het transactioneel wissen van uitsluitend de daarin opgenomen moduletabellen.</summary>
internal sealed class ModuleGegevensbeheer
{
    private readonly JlDatabase _db;
    private readonly SecretStore _geheimen;
    private readonly Lazy<IdempotencyStore> _herhalingen;

    public ModuleGegevensbeheer(JlDatabase db, JlPaths paden, string slug, SecretStore geheimen, ModuleTabel[] tabellen,
        Action<SqliteConnection, DateTimeOffset>? voorExport)
    {
        _db = db;
        Slug = slug;
        _geheimen = geheimen;
        _herhalingen = new Lazy<IdempotencyStore>(
            () => new IdempotencyStore(new JlDatabase(paden, Path.Combine(paden.CacheRoot, slug, "beheerherhaling.db"), [CoreDatabase.IdempotentieTabel])),
            LazyThreadSafetyMode.PublicationOnly);
        Tabellen = [new("instellingen", "id", "bewaar_dagen", "versie"), .. tabellen];
        VoorExport = voorExport;
    }

    public string Slug { get; }

    public IReadOnlyList<ModuleTabel> Tabellen { get; }

    internal Action<SqliteConnection, DateTimeOffset>? VoorExport { get; }

    public string ExportGebruiker(string waarde) => _geheimen.OpaakId("export-" + Slug, waarde);

    // Ook een geweigerd wisverzoek mag geen bestaande verzoeken uit de kerndatabase laten verlopen.
    // De modulecache bewaart per verzoek een ondoorzichtige sleutel zonder account-ID of sessiepseudoniem.
    public IdempotencyStore Herhalingen => _herhalingen.Value;

    public string VerzoekSleutel(string scope, string sleutel) => _geheimen.OpaakId("beheerherhaling-" + Slug, scope + "\n" + sleutel);

    public (Stream Inhoud, string Sha256) MaakExport(TimeProvider klok) => _db.MaakModuleExport(this, klok);

    public JsonObject Wis(string exportSha256, bool dryRun, TimeProvider klok) => _db.WisModule(this, exportSha256, dryRun, klok);
}
