using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

[System.Runtime.Versioning.SupportedOSPlatform("linux")]
public sealed class OpslagGeheimTests : IDisposable
{
    private readonly Harnas _h = new();

    public void Dispose() => _h.Dispose();

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OpstartAls568_OnveiligeRechtenWordenOokNaGebruikGeweigerd(bool mapTeRuim)
    {
        var opslag = _h.Dienst<SecretStore>();
        await opslag.StartAsync(TestContext.Current.CancellationToken);
        var map = _h.Dienst<JlPaths>().SecretsDir;
        var bestand = Path.Combine(map, "opaque-id.salt");
        var origineel = await File.ReadAllBytesAsync(bestand, TestContext.Current.CancellationToken);
        Assert.Equal(32, origineel.Length);
        Assert.Equal("568", JlPaths.OpslagGebruiker());
        Assert.Equal((UnixFileMode)448, File.GetUnixFileMode(map));
        Assert.Equal((UnixFileMode)384, File.GetUnixFileMode(bestand));
        Assert.Equal("healthy", Assert.Single(opslag.Checks(_h.Klok.Nu))["status"]!.GetValue<string>());
        _ = opslag.OpaakId("test", "eerste");
        var doel = mapTeRuim ? map : bestand;
        var modus = mapTeRuim ? (UnixFileMode)493 : (UnixFileMode)420;
        File.SetUnixFileMode(doel, modus);
        Assert.Equal(503, Assert.Throws<JlException>(() => opslag.OpaakId("test", "volgende")).Status);
        Assert.Equal(503, Assert.Throws<JlException>(() => opslag.Schrijf("opaque-id.salt", [1])).Status);
        Assert.Equal(503, Assert.Throws<JlException>(() => opslag.Verwijder("opaque-id.salt")).Status);
        await opslag.StartAsync(TestContext.Current.CancellationToken);
        Assert.Equal(modus, File.GetUnixFileMode(doel));
        Assert.Equal(origineel, await File.ReadAllBytesAsync(bestand, TestContext.Current.CancellationToken));
        var health = Assert.Single(opslag.Checks(_h.Klok.Nu));
        Assert.Equal("degraded", (string?)health["status"]);
        Assert.Equal("geheim_niet_beschikbaar", (string?)health["detail"]!["reden"]);
    }

    [Fact]
    public void VreemdeEigenaarMetModus0600_WeigertLezenVervangenEnWissen()
    {
        var dir = Environment.GetEnvironmentVariable("JL_VREEMD_GEHEIM") ?? throw new InvalidOperationException("Eigenaarfixture ontbreekt.");
        var paden = new JlPaths(dir, Path.Combine(_h.Map, "cache"));
        var opslag = new SecretStore(paden);
        var bestand = Path.Combine(paden.SecretsDir, "vreemd.salt");
        Assert.Equal((UnixFileMode)384, File.GetUnixFileMode(bestand));
        Assert.Throws<UnauthorizedAccessException>(() => File.SetUnixFileMode(bestand, (UnixFileMode)384));
        Assert.Equal(503, Assert.Throws<JlException>(() => opslag.Lees("vreemd.salt")).Status);
        Assert.Equal(503, Assert.Throws<JlException>(() => opslag.Schrijf("vreemd.salt", [1])).Status);
        Assert.Equal(503, Assert.Throws<JlException>(() => opslag.Verwijder("vreemd.salt")).Status);
        Assert.Equal("degraded", (string?)Assert.Single(opslag.Checks(_h.Klok.Nu))["status"]);
        Assert.True(File.Exists(bestand));
    }

    [Fact]
    public async Task GelijktijdigeEersteStart_PubliceertEenVolledigBlijvendGeheim()
    {
        var paden = _h.Dienst<JlPaths>();
        for (var ronde = 0; ronde < 16; ronde++)
        {
            var naam = "testzout-" + ronde.ToString(System.Globalization.CultureInfo.InvariantCulture);
            var taken = Enumerable.Range(0, 4).Select(_ => Task.Run(() => new SecretStore(paden).LeesOfMaak(naam, 32))).ToArray();
            var sleutels = await Task.WhenAll(taken);
            var bewaard = await File.ReadAllBytesAsync(Path.Combine(paden.SecretsDir, naam), TestContext.Current.CancellationToken);
            Assert.Equal(32, bewaard.Length);
            Assert.All(sleutels, s => Assert.True(System.Security.Cryptography.CryptographicOperations.FixedTimeEquals(bewaard, s)));
        }

        Assert.Equal(16, Directory.GetFiles(paden.SecretsDir).Length);
    }
}
