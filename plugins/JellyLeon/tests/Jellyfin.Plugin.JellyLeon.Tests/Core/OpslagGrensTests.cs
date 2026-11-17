using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Runtime.Versioning;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Microsoft.Data.Sqlite;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>Synthetische regressies voor opslagrechten en koppelingen (S-G1-16 deel 1b).</summary>
[SupportedOSPlatform("linux")]
public sealed class OpslagGrensTests : IDisposable
{
    private readonly string _map = Directory.CreateTempSubdirectory("jl-opslaggrens-").FullName;

    public void Dispose() => Directory.Delete(_map, true);

    [Fact]
    public void Tijdelijk_VasteHardeKoppelingRaaktHetBuitenbestandNiet()
    {
        var paden = Paden();
        Directory.CreateDirectory(paden.DataRoot);
        var buiten = Path.Combine(_map, "buiten.db");
        File.WriteAllBytes(buiten, "synthetische kijkgegevens"u8.ToArray());
        var voor = File.ReadAllBytes(buiten);
        var pad = Path.Combine(paden.DataRoot, "uitvoer.json");
        Hard(buiten, pad + ".tmp");
        new InternalWriteScope(paden).SchrijfAtomisch(pad, "nieuwe uitvoer"u8);
        Assert.Equal(voor, File.ReadAllBytes(buiten));
        Assert.Equal("nieuwe uitvoer", File.ReadAllText(pad));
    }

    [Theory]
    [InlineData(UnixFileMode.GroupWrite)]
    [InlineData(UnixFileMode.OtherWrite)]
    public void Start_GedeeldeGegevensmapWordtGeweigerd(UnixFileMode extra)
    {
        var data = Path.Combine(_map, "data");
        Directory.CreateDirectory(data);
        File.SetUnixFileMode(data, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute | extra);
        Assert.Throws<UnauthorizedAccessException>(() => new JlPaths(data, Path.Combine(_map, "cache")));
        Assert.False(Directory.Exists(Path.Combine(data, "jelly-leon")));
    }

    [Theory]
    [InlineData("/")]
    [InlineData("/tmp")]
    [InlineData("/run")]
    public void Start_SysteemouderIsGeenEigenGegevensmap(string data)
    {
        Assert.Throws<UnauthorizedAccessException>(() => new JlPaths(data, Path.Combine(_map, "cache")));
    }

    [Fact]
    public void Start_VreemdeEigenaarWordtGeweigerd()
    {
        // Rootmap uit de SDK-image, veilig leesbaar, maar geen eigendom van de testgebruiker.
        Assert.Throws<UnauthorizedAccessException>(() => new JlPaths("/usr/share", Path.Combine(_map, "cache")));
    }

    [Fact]
    public void Start_VervangbareBovenliggendeMapWordtGeweigerd()
    {
        var ouder = Path.Combine(_map, "gedeeld");
        var data = Path.Combine(ouder, "data");
        Directory.CreateDirectory(data);
        File.SetUnixFileMode(ouder, (UnixFileMode)511);
        Assert.Throws<UnauthorizedAccessException>(() => new JlPaths(data, Path.Combine(_map, "cache")));
    }

    [Fact]
    public void Start_EigenWortelAlsKoppelingWordtGeweigerd()
    {
        var data = Path.Combine(_map, "data");
        Directory.CreateDirectory(data);
        Directory.CreateSymbolicLink(Path.Combine(data, "jelly-leon"), _map);
        Assert.Throws<UnauthorizedAccessException>(() => new JlPaths(data, Path.Combine(_map, "cache")));
    }

    [Theory]
    [InlineData("")]
    [InlineData("-wal")]
    [InlineData("-shm")]
    [InlineData("-journal")]
    public void Database_ElkeKoppelingWordtGeweigerdOokBinnenEigenMap(string suffix)
    {
        var paden = Paden();
        Directory.CreateDirectory(paden.DataRoot);
        var pad = Path.Combine(paden.DataRoot, "eigen.db");
        var ander = Path.Combine(paden.DataRoot, "ander");
        File.WriteAllBytes(ander, []);
        File.CreateSymbolicLink(pad + suffix, ander);
        Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(paden, pad, []));
    }

    [Theory]
    [InlineData("")]
    [InlineData("-wal")]
    [InlineData("-shm")]
    [InlineData("-journal")]
    public void Database_BeschrijfbaarBestandVoorAnderenWordtGeweigerd(string suffix)
    {
        var paden = Paden();
        Directory.CreateDirectory(paden.DataRoot);
        var pad = Path.Combine(paden.DataRoot, "eigen.db");
        File.WriteAllBytes(pad + suffix, []);
        File.SetUnixFileMode(pad + suffix, (UnixFileMode)438);
        Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(paden, pad, []));
    }

    [Fact]
    public void Bewerkingen_HercontrolerenMaprechtenEnMakenPriveAan()
    {
        var paden = Paden();
        var scope = new InternalWriteScope(paden);
        var map = Path.Combine(paden.DataRoot, "nieuw");
        scope.MaakMap(map);
        var pad = Path.Combine(map, "uitvoer");
        scope.SchrijfAtomisch(pad, "proef"u8);
        Assert.Equal((UnixFileMode)448, File.GetUnixFileMode(map));
        Assert.Equal((UnixFileMode)384, File.GetUnixFileMode(pad));
        File.SetUnixFileMode(map, (UnixFileMode)511);
        Assert.Throws<UnauthorizedAccessException>(() => scope.SchrijfAtomisch(pad, "anders"u8));
        Assert.Throws<UnauthorizedAccessException>(() => scope.Verwijder(pad));
        Assert.Throws<UnauthorizedAccessException>(() => scope.MaakMap(Path.Combine(map, "sub")));
        Assert.Equal("proef", File.ReadAllText(pad));
    }

    [Fact]
    public void Geheimen_TijdelijkeHardeKoppelingRaaktHetBuitenbestandNiet()
    {
        var paden = Paden();
        var geheimen = new SecretStore(paden);
        geheimen.Schrijf("synthetisch", [1, 2, 3]);
        var buiten = Path.Combine(_map, "buiten");
        File.WriteAllBytes(buiten, [7, 8, 9]);
        Hard(buiten, Path.Combine(paden.SecretsDir, "synthetisch.tmp"));
        geheimen.Schrijf("synthetisch", [4, 5, 6]);
        Assert.Equal(new byte[] { 7, 8, 9 }, File.ReadAllBytes(buiten));
    }

    [Fact]
    public void Herstel_ZipKoppelingskenmerkMaaktGeenHardeOfSymbolischeKoppeling()
    {
        // De ingebouwde BackupService herstelt met ZipArchiveEntry.ExtractToFile. Bewaak juist die aanname.
        var paden = Paden();
        Directory.CreateDirectory(paden.DataRoot);
        var buiten = Path.Combine(_map, "synthetisch.db");
        using (var verbinding = new SqliteConnection("Data Source=" + buiten + ";Pooling=False"))
        {
            verbinding.Open();
            JlDatabase.Voer(verbinding, "CREATE TABLE UserData(x INTEGER); INSERT INTO UserData VALUES(7);");
        }

        var voor = File.ReadAllBytes(buiten);
        using var inhoud = new MemoryStream();
        using (var zip = new ZipArchive(inhoud, ZipArchiveMode.Create, leaveOpen: true))
        {
            var entry = zip.CreateEntry("synthetisch.db");
            // Unix-symlinktype in de archiefmetadata: de extractor mag daarvan geen bestandskoppeling maken.
            entry.ExternalAttributes = unchecked((int)0xa1800000);
            using var uitvoer = entry.Open();
            uitvoer.Write(voor);
        }

        inhoud.Position = 0;
        var pad = Path.Combine(paden.DataRoot, "herstel.db");
        using (var zip = new ZipArchive(inhoud, ZipArchiveMode.Read))
        {
            zip.Entries[0].ExtractToFile(pad, overwrite: true);
        }

        Assert.Null(new FileInfo(pad).LinkTarget);
        new JlDatabase(paden, pad, ["DELETE FROM UserData;"]).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM UserData"));
        Assert.Equal(voor, File.ReadAllBytes(buiten));
    }

    private JlPaths Paden() => new(Path.Combine(_map, "data"), Path.Combine(_map, "cache"));

    private static void Hard(string bron, string doel)
    {
        using var proces = Process.Start(new ProcessStartInfo("ln") { ArgumentList = { "--", bron, doel }, UseShellExecute = false });
        Assert.NotNull(proces);
        proces.WaitForExit();
        Assert.Equal(0, proces.ExitCode);
    }
}
