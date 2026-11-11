using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.JellyLeon.Core.Storage;

/// <summary>
/// Eigen SQLite-bestand van Core of van één module (ADR-0016). Migraties via <c>user_version</c>; vóór elke
/// migratie van een bestaand bestand een kopie na <c>PRAGMA integrity_check</c> (hooguit 3 kopieën, 30 dagen).
/// </summary>
internal sealed class JlDatabase
{
    private const int MaxKopieen = 3;
    private static readonly TimeSpan _bewaartermijn = TimeSpan.FromDays(30);
    private readonly string _connectionString;
    private readonly IReadOnlyList<string> _migraties;
    private readonly object _slot = new();
    private bool _klaar;

    public JlDatabase(string pad, IReadOnlyList<string> migraties)
    {
        Pad = pad;
        _migraties = migraties;
        _connectionString = new SqliteConnectionStringBuilder { DataSource = pad, Pooling = false }.ToString();
    }

    public string Pad { get; }

    /// <summary>Voert <paramref name="werk"/> uit op een open verbinding; opslagfouten worden 503 storage_unavailable.</summary>
    public T Met<T>(Func<SqliteConnection, T> werk)
    {
        try
        {
            lock (_slot)
            {
                using var verbinding = Open();
                return werk(verbinding);
            }
        }
        catch (SqliteException)
        {
            throw Fouten.OpslagOnbeschikbaar();
        }
        catch (IOException)
        {
            throw Fouten.OpslagOnbeschikbaar();
        }
        catch (UnauthorizedAccessException)
        {
            throw Fouten.OpslagOnbeschikbaar();
        }
    }

    /// <summary>
    /// Schrijft het WAL-bestand weg en kort het in tot nul bytes. Na een verwijdering staan oude paginabeelden (met de
    /// verwijderde inhoud) anders nog in het WAL tot de volgende controle van SQLite.
    /// </summary>
    public void WisSporen() => Met(v => Voer(v, "PRAGMA wal_checkpoint(TRUNCATE);"));

    public void Met(Action<SqliteConnection> werk) => Met(v =>
    {
        werk(v);
        return 0;
    });

    public static int Voer(SqliteConnection verbinding, string sql, params (string Naam, object? Waarde)[] parameters)
    {
        using var opdracht = Opdracht(verbinding, sql, parameters);
        return opdracht.ExecuteNonQuery();
    }

    public static object? Scalar(SqliteConnection verbinding, string sql, params (string Naam, object? Waarde)[] parameters)
    {
        using var opdracht = Opdracht(verbinding, sql, parameters);
        var waarde = opdracht.ExecuteScalar();
        return waarde is DBNull ? null : waarde;
    }

    public static long Getal(SqliteConnection verbinding, string sql, params (string Naam, object? Waarde)[] parameters) =>
        Convert.ToInt64(Scalar(verbinding, sql, parameters) ?? 0L, CultureInfo.InvariantCulture);

    public static List<object?[]> Rijen(SqliteConnection verbinding, string sql, params (string Naam, object? Waarde)[] parameters)
    {
        using var opdracht = Opdracht(verbinding, sql, parameters);
        using var lezer = opdracht.ExecuteReader();
        var rijen = new List<object?[]>();
        while (lezer.Read())
        {
            var rij = new object?[lezer.FieldCount];
            for (var i = 0; i < rij.Length; i++)
            {
                rij[i] = lezer.IsDBNull(i) ? null : lezer.GetValue(i);
            }

            rijen.Add(rij);
        }

        return rijen;
    }

    private static SqliteCommand Opdracht(SqliteConnection verbinding, string sql, (string Naam, object? Waarde)[] parameters)
    {
        var opdracht = verbinding.CreateCommand();
#pragma warning disable CA2100 // SQL-tekst komt uitsluitend uit vaste tekst in de plugin; waarden gaan altijd als parameter.
        opdracht.CommandText = sql;
#pragma warning restore CA2100
        foreach (var (naam, waarde) in parameters)
        {
            opdracht.Parameters.AddWithValue(naam, waarde ?? DBNull.Value);
        }

        return opdracht;
    }

    private SqliteConnection Open()
    {
        if (!_klaar)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Pad)!);
        }

        var verbinding = new SqliteConnection(_connectionString);
        verbinding.Open();
        try
        {
            Voer(verbinding, "PRAGMA busy_timeout=5000;");

            // Verwijderde rijen worden met nullen overschreven: anders blijft de inhoud (bijvoorbeeld een account-ID na
            // UserDeleted) in vrije pagina's van het bestand leesbaar. Geldt per verbinding.
            Voer(verbinding, "PRAGMA secure_delete=ON;");
            if (!_klaar)
            {
                Voer(verbinding, "PRAGMA journal_mode=WAL;");
                Migreer(verbinding);
                _klaar = true;
            }

            return verbinding;
        }
        catch
        {
            verbinding.Dispose();
            throw;
        }
    }

    private void Migreer(SqliteConnection verbinding)
    {
        var versie = (int)Getal(verbinding, "PRAGMA user_version;");
        if (versie >= _migraties.Count)
        {
            return;
        }

        if (versie > 0)
        {
            MaakKopie(verbinding, versie);
        }

        for (var i = versie; i < _migraties.Count; i++)
        {
            using var transactie = verbinding.BeginTransaction();
            Voer(verbinding, _migraties[i]);
            Voer(verbinding, "PRAGMA user_version=" + (i + 1).ToString(CultureInfo.InvariantCulture) + ";");
            transactie.Commit();
        }
    }

    private void MaakKopie(SqliteConnection verbinding, int versie)
    {
        var uitkomst = Convert.ToString(Scalar(verbinding, "PRAGMA integrity_check;"), CultureInfo.InvariantCulture);
        if (!string.Equals(uitkomst, "ok", StringComparison.Ordinal))
        {
            throw new IOException("integrity_check van " + Path.GetFileName(Pad) + " is niet 'ok'; migratie gestopt.");
        }

        Voer(verbinding, "PRAGMA wal_checkpoint(TRUNCATE);");
        var stempel = DateTime.UtcNow.ToString("yyyyMMddHHmmss", CultureInfo.InvariantCulture);
        var kopie = Pad + ".v" + versie.ToString(CultureInfo.InvariantCulture) + "." + stempel + ".bak";
        File.Copy(Pad, kopie, overwrite: false);

        // Opruimen op de stempel in de naam (niet op de bestandstijd: een kopie erft de tijd van het origineel).
        // De kopie van zojuist blijft altijd staan.
        var nu = DateTime.UtcNow;
        var kopieen = new DirectoryInfo(Path.GetDirectoryName(Pad)!)
            .GetFiles(Path.GetFileName(Pad) + ".v*.bak")
            .Select(f => (Bestand: f, Sleutel: Sorteersleutel(f.Name)))
            .OrderByDescending(k => k.Sleutel, StringComparer.Ordinal)
            .ToList();
        for (var i = 0; i < kopieen.Count; i++)
        {
            var (bestand, sleutel) = kopieen[i];
            if (string.Equals(bestand.FullName, kopie, StringComparison.Ordinal))
            {
                continue;
            }

            var teOud = DateTime.TryParseExact(sleutel[..14], "yyyyMMddHHmmss", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var gemaakt)
                && nu - gemaakt > _bewaartermijn;
            if (i >= MaxKopieen || teOud)
            {
                bestand.Delete();
            }
        }
    }

    /// <summary>Sorteersleutel van een kopie <c>&lt;db&gt;.v&lt;versie&gt;.&lt;stempel&gt;.bak</c>: stempel, dan versie (numeriek).</summary>
    private static string Sorteersleutel(string naam)
    {
        var delen = naam.Split('.');
        var stempel = delen.Length >= 3 ? delen[^2] : string.Empty;
        var versie = delen.Length >= 3 ? delen[^3].TrimStart('v') : string.Empty;
        return stempel.PadLeft(14, '0')[..14] + "." + versie.PadLeft(10, '0');
    }
}
