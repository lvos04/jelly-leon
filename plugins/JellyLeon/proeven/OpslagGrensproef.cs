// Uitsluitend synthetisch testharnas. Dit bestand wordt niet in de plugin gecompileerd.
using System.Diagnostics;
using System.Text.Json;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Microsoft.Data.Sqlite;

var basis = Directory.CreateTempSubdirectory("jl-opslagproef-").FullName;
var resultaten = new List<object>();
try
{
    foreach (var proef in new[] { "hardlink-tijdelijk", "hardlink-database", "padwissel-bestand", "padwissel-database", "botsing-willekeurig-tijdelijk" })
    {
        var map = Path.Combine(basis, proef);
        var paden = new JlPaths(Path.Combine(map, "data"), Path.Combine(map, "cache"));
        Directory.CreateDirectory(paden.DataRoot);
        var buiten = Path.Combine(map, "server");
        Directory.CreateDirectory(buiten);
        var serverDb = Path.Combine(buiten, "synthetisch.db");
        using (var v = new SqliteConnection("Data Source=" + serverDb + ";Pooling=False"))
        {
            v.Open();
            using var q = v.CreateCommand();
            q.CommandText = "CREATE TABLE UserData(UserId TEXT, Played INTEGER, PlaybackPositionTicks INTEGER); INSERT INTO UserData VALUES('synthetisch',1,15000000);";
            q.ExecuteNonQuery();
        }

        var voor = File.ReadAllBytes(serverDb);
        var namen = Directory.GetFileSystemEntries(buiten).Order(StringComparer.Ordinal).ToArray();
        var eigen = Path.Combine(paden.DataRoot, "proef");
        Directory.CreateDirectory(eigen);
        var pad = Path.Combine(eigen, "synthetisch.db");
        string? weigering = null;
        try
        {
            switch (proef)
            {
                case "hardlink-tijdelijk":
                    GrensHaak.Hard(serverDb, pad + ".tmp");
                    new InternalWriteScope(paden).SchrijfAtomisch(pad, "synthetische uitvoer"u8);
                    break;
                case "hardlink-database":
                    GrensHaak.Hard(serverDb, pad);
                    new JlDatabase(paden, pad, ["DELETE FROM UserData;"]).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM UserData"));
                    break;
                case "padwissel-bestand":
                    GrensHaak.Bestand = _ =>
                    {
                        Directory.Move(eigen, eigen + "-voor");
                        Directory.CreateSymbolicLink(eigen, buiten);
                    };
                    new InternalWriteScope(paden).SchrijfAtomisch(pad, "synthetische uitvoer"u8);
                    break;
                case "padwissel-database":
                    var db = new JlDatabase(paden, pad, ["DELETE FROM UserData;"]);
                    GrensHaak.Database = () =>
                    {
                        File.Delete(pad);
                        File.CreateSymbolicLink(pad, serverDb);
                    };
                    db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM UserData"));
                    break;
                case "botsing-willekeurig-tijdelijk":
                    GrensHaak.Bestand = tijdelijk => GrensHaak.Hard(serverDb, tijdelijk);
                    new InternalWriteScope(paden).SchrijfAtomisch(pad, "synthetische uitvoer"u8);
                    break;
            }
        }
        catch (Exception fout)
        {
            weigering = fout.GetType().Name;
        }
        finally
        {
            GrensHaak.Bestand = null;
            GrensHaak.Database = null;
        }

        resultaten.Add(new
        {
            proef,
            bytegelijk = voor.SequenceEqual(File.ReadAllBytes(serverDb)),
            mapgelijk = namen.SequenceEqual(Directory.GetFileSystemEntries(buiten).Order(StringComparer.Ordinal)),
            weigering,
        });
    }

    Console.WriteLine("OPSLAGPROEVEN=" + JsonSerializer.Serialize(resultaten));
    Console.WriteLine("Vijf synthetische opslagregressies uitgevoerd; geen echte diensten benaderd.");
}
finally
{
    Directory.Delete(basis, true);
}

namespace Jellyfin.Plugin.JellyLeon.Core.Storage
{
    internal static class GrensHaak
    {
        public static Action<string>? Bestand;
        public static Action? Database;

        private static void VoorBestand(string pad)
        {
            var actie = Bestand;
            Bestand = null;
            actie?.Invoke(pad);
        }

        public static FileStream OpenBestand(string pad, FileStreamOptions opties)
        {
            VoorBestand(pad);
            return new FileStream(pad, opties);
        }

        public static FileStream OpenBestand(string pad, FileMode modus, FileAccess toegang, FileShare delen)
        {
            VoorBestand(pad);
            return new FileStream(pad, modus, toegang, delen);
        }

        public static SqliteConnection NieuweVerbinding(string verbinding)
        {
            var actie = Database;
            Database = null;
            actie?.Invoke();
            return new SqliteConnection(verbinding);
        }

        public static void Hard(string bron, string doel)
        {
            using var proces = Process.Start(new ProcessStartInfo("ln") { ArgumentList = { "--", bron, doel }, UseShellExecute = false })!;
            proces.WaitForExit();
            if (proces.ExitCode != 0)
            {
                throw new IOException("Harde testkoppeling kon niet worden aangemaakt.");
            }
        }
    }
}

namespace Jellyfin.Plugin.JellyLeon.Core.Errors
{
    internal static class Fouten
    {
        public static IOException OpslagOnbeschikbaar() => new("Synthetische opslag geweigerd.");
    }
}
