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
/// Alleen een bestand binnen de eigen mappen (<see cref="JlPaths.MagSchrijven"/>, ook na het volgen van symbolische
/// koppelingen): elk ander pad, zoals de database van de server, weigert de constructor voordat er iets geopend of
/// aangemaakt is, en elke opening controleert het opnieuw (HARDE EIS, ADR-0032). Dat geldt ook voor de bestanden die
/// SQLite ernaast schrijft (<c>-wal</c>, <c>-shm</c>, <c>-journal</c>). Een verbinding van dit type kan geen tweede database
/// koppelen (<c>ATTACH</c>, <c>VACUUM INTO</c>); buiten Core.Storage is elke andere weg naar een databaseverbinding een
/// bouwfout (JL0002, ADR-0032).
/// </summary>
internal sealed class JlDatabase
{
    private const int MaxKopieen = 3;
    private static readonly TimeSpan _bewaartermijn = TimeSpan.FromDays(30);
    private static readonly string[] _naastBestanden = ["", "-wal", "-shm", "-journal"];
    private readonly JlPaths _paden;
    private readonly InternalWriteScope _bestanden;
    private readonly string _connectionString;
    private readonly IReadOnlyList<string> _migraties;
    private readonly object _slot = new();
    private bool _klaar;

    public JlDatabase(JlPaths paden, string pad, IReadOnlyList<string> migraties)
    {
        ArgumentNullException.ThrowIfNull(paden);
        EisEigenPlek(paden, pad);
        _paden = paden;
        _bestanden = new InternalWriteScope(paden);
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

    /// <summary>
    /// De eenmalige opslagbeslissing bij de serverstart (ADR-0032, deel 1e): dezelfde eisen als de constructor en elke
    /// opening, plus de eigendomsproef op het bestaande bestand en elk bestaand naastbestand. Opent en maakt niets.
    /// </summary>
    internal static void EisVeiligBijStart(JlPaths paden, string pad)
    {
        EisEigenPlek(paden, pad);
        foreach (var suffix in _naastBestanden)
        {
            JlPaths.EisEigenBestand(pad + suffix);
        }
    }

    /// <summary>
    /// Het bestand en wat SQLite ernaast schrijft, liggen (ook na het volgen van koppelingen) in een eigen map. SQLite zet
    /// <c>-wal</c>, <c>-shm</c> en <c>-journal</c> naast het echte bestand: is <paramref name="pad"/> zelf een koppeling
    /// (a.db -&gt; b.db), dan naast b.db. Daarom telt elk naastbestand naast de opgegeven naam én naast het echte pad.
    /// </summary>
    private static void EisEigenPlek(JlPaths paden, string pad)
    {
        foreach (var suffix in _naastBestanden)
        {
            paden.EisVeiligBestand(pad + suffix);
        }

        var echt = JlPaths.EchtPad(Path.IsPathRooted(pad) ? pad : Path.Combine(Directory.GetCurrentDirectory(), pad));
        if (echt is null || _naastBestanden.Any(achtervoegsel => !paden.MagSchrijven(pad + achtervoegsel) || !paden.EchtInEigenMap(echt + achtervoegsel)))
        {
            throw new UnauthorizedAccessException("Een database buiten de eigen mappen van Jelly Leon openen is niet toegestaan.");
        }
    }

    private SqliteConnection Open()
    {
        // Bij elke opening opnieuw: een koppeling kan na het aanmaken van dit object zijn ontstaan.
        EisEigenPlek(_paden, Pad);
        if (!_klaar)
        {
            _bestanden.MaakMap(Path.GetDirectoryName(Pad)!);
            if (!File.Exists(Pad))
            {
                // Exclusieve aanmaak weigert een inmiddels verschenen bestand of koppeling; nieuwe DB is 0600.
                _bestanden.SchrijfEenmalig(Pad, []);
            }
        }

        var verbinding = new SqliteConnection(_connectionString);
        verbinding.Open();
        try
        {
            // Microsoft.Data.Sqlite biedt geen NOFOLLOW-optie of beheerde bestandsidentiteit. Daarom opnieuw
            // controleren vóór de eerste PRAGMA of migratie; dit sluit de gereproduceerde padwissel vóór openen.
            EisEigenPlek(_paden, Pad);
            EisEigenPlek(_paden, verbinding.DataSource);
            SluitKoppelenUit(verbinding);
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

    /// <summary>
    /// De verbinding gaat via <see cref="Met{T}"/> naar Core en de modules. Met SQL mag die geen ander databasebestand bereiken
    /// (R-HARDE-EIS-12, ADR-0032): <c>ATTACH</c> koppelt elk pad, ook een pad dat pas bij het draaien ontstaat, en
    /// <c>VACUUM INTO</c> koppelt intern ook. Daarom mag deze verbinding geen enkele database koppelen
    /// (<c>SQLITE_LIMIT_ATTACHED</c> = 0); daarna wordt de grens teruggelezen. Gaat dat mis, dan gaat de verbinding dicht
    /// (503 storage_unavailable), nooit open met koppelen aan. De limiet geldt per verbinding en is alleen via SQLitePCL te
    /// wijzigen, en dat is buiten Core.Storage een bouwfout (JL0002).
    /// </summary>
    private static void SluitKoppelenUit(SqliteConnection verbinding)
    {
        _ = SQLitePCL.raw.sqlite3_limit(verbinding.Handle, SQLitePCL.raw.SQLITE_LIMIT_ATTACHED, 0);
        if (SQLitePCL.raw.sqlite3_limit(verbinding.Handle, SQLitePCL.raw.SQLITE_LIMIT_ATTACHED, -1) != 0)
        {
            throw new IOException("Koppelen van een tweede database is niet uit te zetten; verbinding gesloten.");
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
        _bestanden.KopieerNieuw(Pad, kopie);

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
                _bestanden.Verwijder(bestand.FullName);
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
