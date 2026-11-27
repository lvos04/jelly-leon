using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Idempotency;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.JellyLeon.Core.Storage;

/// <summary>Vaste tabel en kolommen uit de migraties van één module, in sleutelvolgorde.</summary>
internal sealed record ModuleTabel(string Naam, params string[] Kolommen);

/// <summary>De beheerexport en het transactioneel wissen van uitsluitend de daarin opgenomen moduletabellen.</summary>
internal sealed class ModuleGegevensbeheer
{
    private static readonly TimeSpan _maxLeeftijd = TimeSpan.FromHours(24);
    private readonly JlDatabase _db;
    private readonly JlPaths _paden;
    private readonly InternalWriteScope _bestanden;
    private readonly string _exportPad;
    private readonly string _slug;
    private readonly SecretStore _geheimen;
    private readonly ModuleTabel[] _tabellen;
    private readonly Lazy<IdempotencyStore> _herhalingen;

    public ModuleGegevensbeheer(JlDatabase db, JlPaths paden, string slug, SecretStore geheimen, ModuleTabel[] tabellen)
    {
        _db = db;
        _paden = paden;
        _bestanden = new InternalWriteScope(paden);
        _exportPad = Path.Combine(paden.ModuleDir(slug), "beheerexport.json");
        _slug = slug;
        _geheimen = geheimen;
        _herhalingen = new Lazy<IdempotencyStore>(() => new IdempotencyStore(
            new JlDatabase(paden, Path.Combine(paden.CacheRoot, slug, "beheerherhaling.db"), [CoreDatabase.IdempotentieTabel])));
        _tabellen = [new("instellingen", "id", "bewaar_dagen", "versie"), .. tabellen];
    }

    // Ook een geweigerd wisverzoek mag geen bestaande verzoeken uit de kerndatabase laten verlopen.
    // De modulecache bewaart per verzoek een ondoorzichtige sleutel zonder account-ID of sessiepseudoniem.
    public IdempotencyStore Herhalingen => _herhalingen.Value;

    public string VerzoekSleutel(string scope, string sleutel) => _geheimen.OpaakId("beheerherhaling-" + _slug, scope + "\n" + sleutel);

    public (Stream Inhoud, string Sha256) MaakExport(TimeProvider klok) => _db.Met(v =>
    {
        using var transactie = v.BeginTransaction(deferred: false);
        using var verwacht = SHA256.Create();
        _bestanden.SchrijfAtomisch(_exportPad, doel =>
        {
            using var inhoud = new CryptoStream(doel, verwacht, CryptoStreamMode.Write, leaveOpen: true);
            SchrijfExport(v, inhoud, klok.GetUtcNow());
        });

        var export = OpenExport() ?? throw Fouten.OpslagOnbeschikbaar();
        try
        {
            var hash = SHA256.HashData(export);
            if (!hash.AsSpan().SequenceEqual(verwacht.Hash))
            {
                throw Fouten.OpslagOnbeschikbaar();
            }

            export.Position = 0;
            transactie.Commit();
            return (export, Convert.ToHexStringLower(hash));
        }
        catch
        {
            export.Dispose();
            throw;
        }
    });

    public JsonObject Wis(string exportSha256, bool dryRun, TimeProvider klok) => _db.Met(v =>
    {
        // Ook een tweede verbinding kan tussen de vergelijking en de laatste DELETE geen rijen wijzigen.
        using var transactie = v.BeginTransaction(deferred: false);
        using var archief = OpenExport();
        if (archief is null || Convert.ToHexStringLower(SHA256.HashData(archief)) != exportSha256
            || !LeesExporttijd(archief, out var gemaakt))
        {
            throw Fouten.Conflict("export_required");
        }

        var leeftijd = klok.GetUtcNow() - gemaakt;
        if (leeftijd < TimeSpan.Zero || leeftijd > _maxLeeftijd)
        {
            throw Fouten.Conflict("export_required");
        }

        using var hash = SHA256.Create();
        using var controle = new CryptoStream(Stream.Null, hash, CryptoStreamMode.Write);
        var aantallen = SchrijfExport(v, controle, gemaakt);
        controle.FlushFinalBlock();
        if (Convert.ToHexStringLower(hash.Hash!) != exportSha256)
        {
            throw Fouten.Conflict("export_changed");
        }

        if (!dryRun)
        {
            var verwachtTotaal = JlDatabase.Getal(v, "SELECT total_changes()");
            foreach (var tabel in _tabellen)
            {
                var verwacht = aantallen[tabel.Naam]!.GetValue<long>();
                JlDatabase.Voer(v, "DELETE FROM main." + tabel.Naam);
                verwachtTotaal += verwacht;
                // changes() telt de eigen DELETE. total_changes() telt ook triggers en cascades.
                if (JlDatabase.Getal(v, "SELECT changes()") != verwacht || JlDatabase.Getal(v, "SELECT total_changes()") != verwachtTotaal)
                {
                    throw Fouten.Conflict("purge_conflict");
                }
            }
        }

        transactie.Commit();
        return new JsonObject { ["counts"] = aantallen, ["applied"] = !dryRun };
    });

    private Stream? OpenExport()
    {
        _paden.EisVeiligBestand(_exportPad);
        FileStream bestand;
        try
        {
            bestand = new FileStream(_exportPad, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete);
        }
        catch (IOException fout) when (fout is FileNotFoundException or DirectoryNotFoundException)
        {
            return null;
        }

        try
        {
            _paden.EisGeopendBestand(bestand, _exportPad);
            return bestand;
        }
        catch
        {
            bestand.Dispose();
            throw;
        }
    }

    private static bool LeesExporttijd(Stream archief, out DateTimeOffset gemaakt)
    {
        gemaakt = default;
        try
        {
            archief.Position = 0;
            Span<byte> begin = stackalloc byte[96];
            var gelezen = archief.ReadAtLeast(begin, begin.Length, throwOnEndOfStream: false);
            var lezer = new Utf8JsonReader(begin[..gelezen], isFinalBlock: false, state: default);
            return lezer.Read() && lezer.TokenType == JsonTokenType.StartObject
                && lezer.Read() && lezer.TokenType == JsonTokenType.PropertyName && lezer.ValueTextEquals("created_at"u8)
                && lezer.Read() && lezer.TokenType == JsonTokenType.String && lezer.TryGetDateTimeOffset(out gemaakt);
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private JsonObject SchrijfExport(SqliteConnection v, Stream doel, DateTimeOffset gemaakt)
    {
        using var json = new Utf8JsonWriter(doel);
        json.WriteStartObject();
        json.WriteString("created_at", gemaakt);
        json.WriteString("module", _slug);
        json.WriteNumber("schema_version", 1);
        json.WriteStartObject("tables");
        var aantallen = new JsonObject();
        foreach (var tabel in _tabellen)
        {
            // De tabelnaam en sorteersleutel komen uitsluitend uit de moduledefinitie.
            using var opdracht = JlDatabase.Opdracht(v, "SELECT * FROM main." + tabel.Naam + " ORDER BY " + string.Join(", ", tabel.Kolommen));
            using var rijen = opdracht.ExecuteReader();
            if (!tabel.Kolommen.SequenceEqual(Enumerable.Range(0, rijen.FieldCount).Select(rijen.GetName), StringComparer.Ordinal))
            {
                throw Fouten.Conflict("export_schema_changed");
            }

            json.WriteStartArray(tabel.Naam);
            long aantal = 0;
            while (rijen.Read())
            {
                json.WriteStartObject();
                for (var i = 0; i < tabel.Kolommen.Length; i++)
                {
                    var kolom = tabel.Kolommen[i];
                    switch (rijen.GetValue(i))
                    {
                        case DBNull:
                            json.WriteNull(kolom);
                            break;
                        case long getal:
                            json.WriteNumber(kolom, getal);
                            break;
                        case string tekst:
                            json.WriteString(kolom, kolom == "gebruiker" ? _geheimen.OpaakId("export-" + _slug, tekst) : tekst);
                            break;
                        default:
                            throw Fouten.Conflict("export_schema_changed");
                    }
                }

                json.WriteEndObject();
                aantal++;
                if (aantal % 256 == 0)
                {
                    json.Flush();
                }
            }

            json.WriteEndArray();
            aantallen[tabel.Naam] = aantal;
        }

        json.WriteEndObject();
        json.WritePropertyName("counts");
        aantallen.WriteTo(json);
        json.WriteEndObject();
        return aantallen;
    }
}
