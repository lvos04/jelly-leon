using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Core.Idempotency;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>Eigen opslag van de plugin: idempotency, jti-cache, migratiekopieën, schrijfbereik en de geheimenmap.</summary>
public sealed class OpslagTests : IDisposable
{
    private readonly Harnas _h = new();

    public void Dispose() => _h.Dispose();

    [Fact]
    public void Idempotentie_BezigKlaarHergebruikEnVerloop()
    {
        var opslag = _h.Dienst<IdempotencyStore>();
        var nu = _h.Klok.Nu;
        const string Scope = "session:o_abc\nPUT\n/media/v1/devices/settings";
        Assert.Null(opslag.Begin(Scope, "sleutel-1", "hash-a", nu));
        Assert.Equal("idempotency_in_progress", Assert.Throws<JlException>(() => opslag.Begin(Scope, "sleutel-1", "hash-a", nu)).Code);
        Assert.Equal("idempotency_key_reused", Assert.Throws<JlException>(() => opslag.Begin(Scope, "sleutel-1", "hash-b", nu)).Code);

        var antwoord = JlResult.Ok(new JsonObject { ["bewaar_dagen"] = 7 }, "\"devices-1\"");
        opslag.Voltooi(Scope, "sleutel-1", antwoord);
        var herhaling = opslag.Begin(Scope, "sleutel-1", "hash-a", nu.AddHours(23));
        Assert.NotNull(herhaling);
        Assert.Equal(200, herhaling.Status);
        Assert.Equal(antwoord.Body, herhaling.Body);
        Assert.Equal("true", herhaling.Headers["Idempotent-Replay"]);
        Assert.Equal("\"devices-1\"", herhaling.Headers["ETag"]);
        Assert.Equal("idempotency_key_reused", Assert.Throws<JlException>(() => opslag.Begin(Scope, "sleutel-1", "hash-b", nu.AddHours(23))).Code);

        // Een andere aanvrager of een andere route heeft een eigen sleutelruimte.
        Assert.Null(opslag.Begin("session:o_def\nPUT\n/media/v1/devices/settings", "sleutel-1", "hash-a", nu));

        // Na 24 uur is de sleutel weer vrij.
        Assert.Null(opslag.Begin(Scope, "sleutel-1", "hash-b", nu.AddHours(24).AddSeconds(1)));
    }

    [Fact]
    public void Idempotentie_ServerfoutGeeftDeSleutelVrij()
    {
        var opslag = _h.Dienst<IdempotencyStore>();
        Assert.Null(opslag.Begin("s", "k", "h", _h.Klok.Nu));
        opslag.Annuleer("s", "k");
        Assert.Null(opslag.Begin("s", "k", "h", _h.Klok.Nu));
        opslag.Voltooi("s", "k", JlResult.Ok(new JsonObject()));
        opslag.Annuleer("s", "k");
        Assert.NotNull(opslag.Begin("s", "k", "h", _h.Klok.Nu));
    }

    [Fact]
    public void Jti_HerhalingVanEenMutatieWordtGeweigerd()
    {
        var jti = _h.Dienst<JtiStore>();
        var nu = _h.Klok.Nu;
        HubPrincipal Nieuw() => new("7d0c1a52-3f64-4b7e-8a11-9c2f5e6d7a80", false, ["viewer"], Guid.NewGuid().ToString(), nu.ToUnixTimeSeconds() + 60);
        string? Reden(Action actie) => Assert.Throws<JlException>(actie).Details["reason"]?.GetValue<string>();

        // Lezen mag met hetzelfde token vaker (de Hub pagineert binnen één token).
        var lezer = Nieuw();
        jti.Controleer(lezer, "GET", "/connector/v1/events", null, nu);
        jti.Controleer(lezer, "GET", "/connector/v1/events", null, nu);
        jti.Controleer(lezer, "GET", "/connector/v1/health", null, nu);

        // Een token dat al gebruikt is, mag daarna geen mutatie meer doen.
        Assert.Equal("token_replayed", Reden(() => jti.Controleer(lezer, "POST", "/connector/v1/propose", null, nu)));

        // Een mutatie zonder Idempotency-Key mag precies één keer.
        var zonder = Nieuw();
        jti.Controleer(zonder, "POST", "/connector/v1/propose", null, nu);
        Assert.Equal("token_replayed", Reden(() => jti.Controleer(zonder, "POST", "/connector/v1/propose", null, nu)));

        // Dezelfde mutatie met dezelfde Idempotency-Key is een nieuwe poging, geen replay-aanval.
        var met = Nieuw();
        const string Sleutel = "3b0e1c1c-0a53-4d0e-9d0c-0a4c2a6f1f10";
        jti.Controleer(met, "POST", "/connector/v1/apply", Sleutel, nu);
        jti.Controleer(met, "POST", "/connector/v1/apply", Sleutel, nu);
        Assert.Equal("token_replayed", Reden(() => jti.Controleer(met, "POST", "/connector/v1/apply", "9f0e1c1c-0a53-4d0e-9d0c-0a4c2a6f1f11", nu)));
        Assert.Equal("token_replayed", Reden(() => jti.Controleer(met, "POST", "/connector/v1/rollback", Sleutel, nu)));
        Assert.Equal("token_replayed", Reden(() => jti.Controleer(met, "POST", "/connector/v1/apply", null, nu)));
    }

    [Fact]
    public async Task Jti_OpslagWegFaaltDicht()
    {
        _h.Koppel();
        Assert.Equal(200, (await _h.RoepHub("connector.health", _h.Hub.Token(_h.Klok.Nu))).Status);

        var map = Path.Combine(_h.Map, "data", "jelly-leon", "core");
        Directory.Move(map, map + "-weg");
        try
        {
            var antwoord = await _h.RoepHub("connector.health", _h.Hub.Token(_h.Klok.Nu));
            Assert.Equal(503, antwoord.Status);
            Assert.Equal("replay_check_unavailable", antwoord.Code);
            Assert.Equal("30", antwoord.Kop["Retry-After"]);
        }
        finally
        {
            Directory.Move(map + "-weg", map);
        }

        Assert.Equal(200, (await _h.RoepHub("connector.health", _h.Hub.Token(_h.Klok.Nu))).Status);
    }

    [Fact]
    public void Database_MigratieMaaktEerstEenKopieEnBewaartErDrie()
    {
        var pad = Path.Combine(_h.Map, "data", "jelly-leon", "proef", "proef.db");
        string[] stappen =
        [
            "CREATE TABLE a(x INTEGER);",
            "ALTER TABLE a ADD COLUMN y INTEGER DEFAULT 3;",
            "ALTER TABLE a ADD COLUMN z INTEGER DEFAULT 4;",
            "CREATE TABLE b(x INTEGER);",
            "CREATE TABLE c(x INTEGER);",
            "CREATE TABLE d(x INTEGER);",
        ];
        new JlDatabase(pad, stappen[..1]).Met(v => JlDatabase.Voer(v, "INSERT INTO a VALUES(7)"));
        Assert.Empty(Directory.GetFiles(Path.GetDirectoryName(pad)!, "*.bak"));

        var tweede = new JlDatabase(pad, stappen[..2]);
        Assert.Equal(3, tweede.Met(v => JlDatabase.Getal(v, "SELECT y FROM a WHERE x = 7")));
        var kopie = Assert.Single(Directory.GetFiles(Path.GetDirectoryName(pad)!, "proef.db.v1.*.bak"));

        // De kopie is de database van vóór de migratie: wel de rij, nog niet de nieuwe kolom.
        var oud = new JlDatabase(kopie, stappen[..1]);
        Assert.Equal(7, oud.Met(v => JlDatabase.Getal(v, "SELECT x FROM a")));
        Assert.Equal(1, oud.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM pragma_table_info('a')")));
        foreach (var bijvangst in Directory.GetFiles(Path.GetDirectoryName(pad)!, "*.bak-*"))
        {
            File.Delete(bijvangst);
        }

        for (var i = 3; i <= stappen.Length; i++)
        {
            new JlDatabase(pad, stappen[..i]).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM a"));
        }

        var kopieen = Directory.GetFiles(Path.GetDirectoryName(pad)!, "proef.db.v*.bak").Select(Path.GetFileName).Order(StringComparer.Ordinal).ToList();
        Assert.Equal(3, kopieen.Count);
        Assert.StartsWith("proef.db.v3.", kopieen[0]);
        Assert.StartsWith("proef.db.v4.", kopieen[1]);
        Assert.StartsWith("proef.db.v5.", kopieen[2]);

        // Zonder nieuwe migratie komt er geen kopie bij.
        new JlDatabase(pad, stappen).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM a"));
        Assert.Equal(3, Directory.GetFiles(Path.GetDirectoryName(pad)!, "proef.db.v*.bak").Length);
    }

    [Fact]
    public void Database_KopieVanEenLangOngewijzigdeDatabaseBlijftStaan()
    {
        var pad = Path.Combine(_h.Map, "data", "jelly-leon", "oud", "oud.db");
        new JlDatabase(pad, ["CREATE TABLE a(x INTEGER);"]).Met(v => JlDatabase.Voer(v, "INSERT INTO a VALUES(1)"));
        File.SetLastWriteTimeUtc(pad, DateTime.UtcNow.AddDays(-40));
        new JlDatabase(pad, ["CREATE TABLE a(x INTEGER);", "CREATE TABLE b(x INTEGER);"]).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM b"));
        Assert.Single(Directory.GetFiles(Path.GetDirectoryName(pad)!, "oud.db.v1.*.bak"));

        // Een kopie met een stempel van meer dan dertig dagen geleden wordt bij de volgende migratie opgeruimd.
        var verlopen = pad + ".v0.20200101000000.bak";
        File.WriteAllText(verlopen, "x");
        new JlDatabase(pad, ["CREATE TABLE a(x INTEGER);", "CREATE TABLE b(x INTEGER);", "CREATE TABLE c(x INTEGER);"]).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM c"));
        Assert.False(File.Exists(verlopen));
        Assert.Single(Directory.GetFiles(Path.GetDirectoryName(pad)!, "oud.db.v1.*.bak"));
        Assert.Single(Directory.GetFiles(Path.GetDirectoryName(pad)!, "oud.db.v2.*.bak"));
    }

    [Fact]
    public void Database_OnbereikbareOpslagWordtEenNetteFout()
    {
        var bestand = Path.Combine(_h.Map, "geen-map");
        File.WriteAllText(bestand, "x");
        var db = new JlDatabase(Path.Combine(bestand, "x", "x.db"), ["CREATE TABLE a(x INTEGER);"]);
        var fout = Assert.Throws<JlException>(() => db.Met(v => JlDatabase.Getal(v, "SELECT 1")));
        Assert.Equal(503, fout.Status);
        Assert.Equal("storage_unavailable", fout.Code);
        Assert.Equal(30, fout.RetryAfterSeconds);
    }

    [Fact]
    public void Schrijfbereik_AlleenDeEigenMappen()
    {
        var paden = _h.Dienst<JlPaths>();
        var bereik = _h.Dienst<InternalWriteScope>();
        var binnen = Path.Combine(paden.DataRoot, "quality", "export.json");
        bereik.SchrijfAtomisch(binnen, "{}"u8);
        Assert.Equal("{}", File.ReadAllText(binnen));
        Assert.False(File.Exists(binnen + ".tmp"));
        Assert.True(paden.MagSchrijven(Path.Combine(paden.CacheRoot, "features", "a.bin")));
        bereik.MaakMap(Path.Combine(paden.CacheRoot, "features"));
        bereik.Verwijder(binnen);
        Assert.False(File.Exists(binnen));

        string[] buiten =
        [
            Path.Combine(_h.Map, "media", "film.nfo"),
            Path.Combine(_h.Map, "data", "jellyfin.db"),
            Path.Combine(paden.DataRoot, "..", "library.db"),
            Path.Combine(paden.DataRoot, "quality", "..", "..", "jellyfin.db"),
            paden.DataRoot + "-naast" + Path.DirectorySeparatorChar + "x",
            paden.DataRoot,
            "/media/films/film.mkv",
        ];
        foreach (var pad in buiten)
        {
            Assert.False(paden.MagSchrijven(pad), pad);
            Assert.Throws<UnauthorizedAccessException>(() => bereik.SchrijfAtomisch(pad, "x"u8));
            Assert.Throws<UnauthorizedAccessException>(() => bereik.Verwijder(pad));
        }

        Assert.Throws<UnauthorizedAccessException>(() => bereik.MaakMap(Path.Combine(_h.Map, "media", "nieuw")));
        Assert.False(Directory.Exists(Path.Combine(_h.Map, "media")));
    }

    [Fact]
    public void Geheimen_RechtenNamenEnOndoorzichtigeIds()
    {
        var geheimen = _h.Dienst<SecretStore>();
        var map = _h.Dienst<JlPaths>().SecretsDir;
        geheimen.Schrijf("mediaguard.key", [1, 2, 3]);
        Assert.Equal(new byte[] { 1, 2, 3 }, geheimen.Lees("mediaguard.key"));
        geheimen.Schrijf("mediaguard.key", [4, 5]);
        Assert.Equal(new byte[] { 4, 5 }, geheimen.Lees("mediaguard.key"));
        Assert.False(File.Exists(Path.Combine(map, "mediaguard.key.tmp")));

        var zout = geheimen.LeesOfMaak("proef.salt", 32);
        Assert.Equal(32, zout.Length);
        Assert.Equal(zout, geheimen.LeesOfMaak("proef.salt", 64));

        if (!OperatingSystem.IsWindows())
        {
            Assert.Equal(UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute, File.GetUnixFileMode(map));
            foreach (var bestand in Directory.GetFiles(map))
            {
                Assert.Equal(UnixFileMode.UserRead | UnixFileMode.UserWrite, File.GetUnixFileMode(bestand));
            }
        }

        geheimen.Verwijder("mediaguard.key");
        Assert.Null(geheimen.Lees("mediaguard.key"));
        foreach (var naam in new[] { string.Empty, "../core/core.db", "a/b", "a\\b", ".verborgen" })
        {
            Assert.Throws<ArgumentException>(() => geheimen.Lees(naam));
            Assert.Throws<ArgumentException>(() => geheimen.Schrijf(naam, [1]));
        }

        var id = geheimen.OpaakId("apparaat", "TV Woonkamer");
        Assert.Matches("^[0-9a-f]{32}$", id);
        Assert.Equal(id, geheimen.OpaakId("apparaat", "TV Woonkamer"));
        Assert.NotEqual(id, geheimen.OpaakId("sessie", "TV Woonkamer"));
        Assert.NotEqual(id, geheimen.OpaakId("apparaat", "TV Slaapkamer"));

        // Een andere installatie (ander zout) geeft andere ID's: niet te koppelen tussen servers.
        using var ander = new Harnas();
        Assert.NotEqual(id, ander.Dienst<SecretStore>().OpaakId("apparaat", "TV Woonkamer"));
    }
}
