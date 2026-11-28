using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.JellyLeon.Core.Storage;

// De gecontroleerde moduleverbinding bezit de bestandshandles, rijlezer en transactie.
internal sealed partial class JlDatabase
{
    private static readonly TimeSpan _maxExportleeftijd = TimeSpan.FromHours(24);

    // De laatste beheerexport is een lokale kopie voor de wisbevestiging. Ook na het verlopen van de
    // bronrij kan die kopie het exportpseudoniem nog bevatten. Dezelfde schrijftransactie ordent export en wissen.
    public int VerwijderModuleGebruiker(ModuleGegevensbeheer module, Guid gebruiker, string sql) => Transactioneel(v =>
    {
        var pad = ModuleExportPad(module);
        var account = gebruiker.ToString("N");
        var aantal = Voer(v, sql, ("$g", account));
        using var export = OpenExport(pad);
        if (export is not null && BevatExportPseudoniem(export, module.ExportGebruiker(account)))
        {
            _bestanden.Verwijder(pad);
        }

        return aantal;
    });

    private static bool BevatExportPseudoniem(Stream export, string pseudoniem)
    {
        var naald = Encoding.ASCII.GetBytes(pseudoniem);
        Span<byte> blok = stackalloc byte[8192];
        var rest = 0;
        int gelezen;
        while ((gelezen = export.Read(blok[rest..])) > 0)
        {
            var inhoud = blok[..(rest + gelezen)];
            if (inhoud.IndexOf(naald) >= 0)
            {
                return true;
            }

            rest = Math.Min(inhoud.Length, naald.Length - 1);
            inhoud[^rest..].CopyTo(blok);
        }

        return false;
    }

    public (Stream Inhoud, string Sha256) MaakModuleExport(ModuleGegevensbeheer module, TimeProvider klok) => Met(v =>
    {
        var exportPad = ModuleExportPad(module);
        using var transactie = v.BeginTransaction(deferred: false);
        var nu = klok.GetUtcNow();
        module.VoorExport?.Invoke(v, nu);
        using var verwacht = SHA256.Create();
        _bestanden.SchrijfAtomisch(exportPad, doel =>
        {
            using var inhoud = new CryptoStream(doel, verwacht, CryptoStreamMode.Write, leaveOpen: true);
            SchrijfExport(module, v, inhoud, nu);
        });

        var export = OpenExport(exportPad) ?? throw Fouten.OpslagOnbeschikbaar();
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

    public JsonObject WisModule(ModuleGegevensbeheer module, string exportSha256, bool dryRun, TimeProvider klok) => Met(v =>
    {
        // Ook een tweede verbinding kan tussen de vergelijking en de laatste DELETE geen rijen wijzigen.
        var exportPad = ModuleExportPad(module);
        using var transactie = v.BeginTransaction(deferred: false);
        using var archief = OpenExport(exportPad);
        if (archief is null || Convert.ToHexStringLower(SHA256.HashData(archief)) != exportSha256
            || !LeesExporttijd(archief, out var gemaakt))
        {
            throw Fouten.Conflict("export_required");
        }

        var leeftijd = klok.GetUtcNow() - gemaakt;
        if (leeftijd < TimeSpan.Zero || leeftijd > _maxExportleeftijd)
        {
            throw Fouten.Conflict("export_required");
        }

        using var hash = SHA256.Create();
        using var controle = new CryptoStream(Stream.Null, hash, CryptoStreamMode.Write);
        var aantallen = SchrijfExport(module, v, controle, gemaakt);
        controle.FlushFinalBlock();
        if (Convert.ToHexStringLower(hash.Hash!) != exportSha256)
        {
            throw Fouten.Conflict("export_changed");
        }

        if (!dryRun)
        {
            var verwachtTotaal = Getal(v, "SELECT total_changes()");
            foreach (var tabel in module.Tabellen)
            {
                var verwacht = aantallen[tabel.Naam]!.GetValue<long>();
                Voer(v, "DELETE FROM main." + tabel.Naam);
                verwachtTotaal += verwacht;
                // changes() telt de eigen DELETE. total_changes() telt ook triggers en cascades.
                if (Getal(v, "SELECT changes()") != verwacht || Getal(v, "SELECT total_changes()") != verwachtTotaal)
                {
                    throw Fouten.Conflict("purge_conflict");
                }
            }
        }

        transactie.Commit();
        return new JsonObject { ["counts"] = aantallen, ["applied"] = !dryRun };
    });

    private string ModuleExportPad(ModuleGegevensbeheer module)
    {
        if (!string.Equals(Pad, _paden.ModuleDb(module.Slug), StringComparison.Ordinal))
        {
            throw Fouten.OpslagOnbeschikbaar();
        }

        return Path.Combine(_paden.ModuleDir(module.Slug), "beheerexport.json");
    }

    private Stream? OpenExport(string exportPad)
    {
        _paden.EisVeiligBestand(exportPad);
        FileStream bestand;
        try
        {
            bestand = new FileStream(exportPad, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete);
        }
        catch (IOException fout) when (fout is FileNotFoundException or DirectoryNotFoundException)
        {
            return null;
        }

        try
        {
            _paden.EisGeopendBestand(bestand, exportPad);
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

    private static JsonObject SchrijfExport(ModuleGegevensbeheer module, SqliteConnection v, Stream doel, DateTimeOffset gemaakt)
    {
        using var json = new Utf8JsonWriter(doel);
        json.WriteStartObject();
        json.WriteString("created_at", gemaakt);
        json.WriteString("module", module.Slug);
        json.WriteNumber("schema_version", 1);
        json.WriteStartObject("tables");
        var aantallen = new JsonObject();
        foreach (var tabel in module.Tabellen)
        {
            // De tabelnaam en sorteersleutel komen uitsluitend uit de moduledefinitie.
            using var opdracht = Opdracht(v, "SELECT * FROM main." + tabel.Naam + " ORDER BY " + string.Join(", ", tabel.Kolommen));
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
                            json.WriteString(kolom, kolom == "gebruiker" ? module.ExportGebruiker(tekst) : tekst);
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
