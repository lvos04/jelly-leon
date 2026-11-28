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
        new JlDatabase(_h.Dienst<JlPaths>(), pad, stappen[..1]).Met(v => JlDatabase.Voer(v, "INSERT INTO a VALUES(7)"));
        Assert.Empty(Directory.GetFiles(Path.GetDirectoryName(pad)!, "*.bak"));

        var tweede = new JlDatabase(_h.Dienst<JlPaths>(), pad, stappen[..2]);
        Assert.Equal(3, tweede.Met(v => JlDatabase.Getal(v, "SELECT y FROM a WHERE x = 7")));
        var kopie = Assert.Single(Directory.GetFiles(Path.GetDirectoryName(pad)!, "proef.db.v1.*.bak"));

        // De kopie is de database van vóór de migratie: wel de rij, nog niet de nieuwe kolom.
        var oud = new JlDatabase(_h.Dienst<JlPaths>(), kopie, stappen[..1]);
        Assert.Equal(7, oud.Met(v => JlDatabase.Getal(v, "SELECT x FROM a")));
        Assert.Equal(1, oud.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM pragma_table_info('a')")));
        foreach (var bijvangst in Directory.GetFiles(Path.GetDirectoryName(pad)!, "*.bak-*"))
        {
            File.Delete(bijvangst);
        }

        for (var i = 3; i <= stappen.Length; i++)
        {
            new JlDatabase(_h.Dienst<JlPaths>(), pad, stappen[..i]).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM a"));
        }

        var kopieen = Directory.GetFiles(Path.GetDirectoryName(pad)!, "proef.db.v*.bak").Select(Path.GetFileName).Order(StringComparer.Ordinal).ToList();
        Assert.Equal(3, kopieen.Count);
        Assert.StartsWith("proef.db.v3.", kopieen[0]);
        Assert.StartsWith("proef.db.v4.", kopieen[1]);
        Assert.StartsWith("proef.db.v5.", kopieen[2]);

        // Zonder nieuwe migratie komt er geen kopie bij.
        new JlDatabase(_h.Dienst<JlPaths>(), pad, stappen).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM a"));
        Assert.Equal(3, Directory.GetFiles(Path.GetDirectoryName(pad)!, "proef.db.v*.bak").Length);
    }

    [Fact]
    public void Database_KopieVanEenLangOngewijzigdeDatabaseBlijftStaan()
    {
        var pad = Path.Combine(_h.Map, "data", "jelly-leon", "oud", "oud.db");
        new JlDatabase(_h.Dienst<JlPaths>(), pad, ["CREATE TABLE a(x INTEGER);"]).Met(v => JlDatabase.Voer(v, "INSERT INTO a VALUES(1)"));
        File.SetLastWriteTimeUtc(pad, DateTime.UtcNow.AddDays(-40));
        new JlDatabase(_h.Dienst<JlPaths>(), pad, ["CREATE TABLE a(x INTEGER);", "CREATE TABLE b(x INTEGER);"]).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM b"));
        Assert.Single(Directory.GetFiles(Path.GetDirectoryName(pad)!, "oud.db.v1.*.bak"));

        // Een kopie met een stempel van meer dan dertig dagen geleden wordt bij de volgende migratie opgeruimd.
        var verlopen = pad + ".v0.20200101000000.bak";
        File.WriteAllText(verlopen, "x");
        new JlDatabase(_h.Dienst<JlPaths>(), pad, ["CREATE TABLE a(x INTEGER);", "CREATE TABLE b(x INTEGER);", "CREATE TABLE c(x INTEGER);"]).Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM c"));
        Assert.False(File.Exists(verlopen));
        Assert.Single(Directory.GetFiles(Path.GetDirectoryName(pad)!, "oud.db.v1.*.bak"));
        Assert.Single(Directory.GetFiles(Path.GetDirectoryName(pad)!, "oud.db.v2.*.bak"));
    }

    [Fact]
    public void Database_OnbereikbareOpslagWordtEenNetteFout()
    {
        var paden = _h.Dienst<JlPaths>();
        Directory.CreateDirectory(paden.DataRoot);
        var bestand = Path.Combine(paden.DataRoot, "geen-map");
        File.WriteAllText(bestand, "x");
        var db = new JlDatabase(paden, Path.Combine(bestand, "x", "x.db"), ["CREATE TABLE a(x INTEGER);"]);
        var fout = Assert.Throws<JlException>(() => db.Met(v => JlDatabase.Getal(v, "SELECT 1")));
        Assert.Equal(503, fout.Status);
        Assert.Equal("storage_unavailable", fout.Code);
        Assert.Equal(30, fout.RetryAfterSeconds);
    }

    /// <summary>
    /// HARDE EIS (R-HARDE-EIS-2, S-G1-17): JlDatabase opent nooit een bestand buiten de eigen mappen, ook niet de
    /// database van de server. De weigering komt vóór het openen: jellyfin.db blijft byte-gelijk en er ontstaat geen
    /// -wal, -shm of nieuw bestand.
    /// </summary>
    [Fact]
    public void Database_BuitenDeEigenMappenWordtGeweigerdZonderTeOpenen()
    {
        var paden = _h.Dienst<JlPaths>();
        var data = Path.GetDirectoryName(paden.DataRoot)!;
        Directory.CreateDirectory(data);
        var serverDb = Path.Combine(data, "jellyfin" + ".db");
        using (var verbinding = new Microsoft.Data.Sqlite.SqliteConnection("Data Source=" + serverDb + ";Pooling=False"))
        {
            verbinding.Open();
            using var opdracht = verbinding.CreateCommand();
            opdracht.CommandText = "CREATE TABLE UserData(UserId TEXT, Played INTEGER, PlaybackPositionTicks INTEGER); INSERT INTO UserData VALUES('u1', 1, 15000000);";
            opdracht.ExecuteNonQuery();
        }

        var voor = File.ReadAllBytes(serverDb);
        var bestandenVoor = Directory.GetFileSystemEntries(_h.Map, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal).ToList();
        string[] buiten =
        [
            serverDb,
            Path.Combine(data, "library" + ".db"),
            Path.Combine(paden.DataRoot, "..", "jellyfin" + ".db"),
            Path.Combine(paden.DataRoot, "core", "..", "..", "jellyfin" + ".db"),
            paden.DataRoot + "-naast" + Path.DirectorySeparatorChar + "x.db",
            Path.Combine(_h.Map, "media", "x.db"),
        ];

        foreach (var pad in buiten)
        {
            Assert.False(paden.MagSchrijven(pad), pad);
            Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(paden, pad, ["CREATE TABLE jl_proef(a INTEGER);"]));
        }

        Assert.Equal(voor, File.ReadAllBytes(serverDb));
        Assert.Equal(bestandenVoor, Directory.GetFileSystemEntries(_h.Map, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal).ToList());

        // Tegenproef: binnen de eigen map werkt dezelfde aanroep wel.
        var eigen = new JlDatabase(paden, Path.Combine(paden.DataRoot, "proef", "proef.db"), ["CREATE TABLE jl_proef(a INTEGER);"]);
        Assert.Equal(0, eigen.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM jl_proef")));
    }

    /// <summary>
    /// HARDE EIS (R-HARDE-EIS-5, S-G1-17 herstelronde 2): de padgrens volgt symbolische koppelingen zoals het
    /// besturingssysteem dat doet (bestand, elke bovenliggende map, ook een relatieve koppeling of een keten). Een
    /// koppeling binnen de eigen map naar jellyfin.db, naar de servermap of naar het WAL-bestand van de server wordt
    /// geweigerd vóór het openen; jellyfin.db blijft byte-gelijk en naast jellyfin.db ontstaat niets. Ook een koppeling binnen de eigen map wordt sinds deel 1b geweigerd.
    /// </summary>
    [Fact]
    public void Database_SymbolischeKoppelingNaarBuitenWordtGeweigerdZonderTeOpenen()
    {
        var paden = _h.Dienst<JlPaths>();
        var data = Path.GetDirectoryName(paden.DataRoot)!;
        var serverDb = MaakServerDb(data);
        var voor = File.ReadAllBytes(serverDb);
        Directory.CreateDirectory(Path.Combine(paden.DataRoot, "proef"));
        Directory.CreateDirectory(paden.CacheRoot);
        File.CreateSymbolicLink(Path.Combine(paden.DataRoot, "proef", "link.db"), serverDb);
        File.CreateSymbolicLink(Path.Combine(paden.DataRoot, "proef", "relatief.db"), Path.Combine("..", "..", "jellyfin" + ".db"));
        File.CreateSymbolicLink(Path.Combine(paden.DataRoot, "proef", "keten.db"), Path.Combine(paden.DataRoot, "proef", "link.db"));
        Directory.CreateSymbolicLink(Path.Combine(paden.DataRoot, "maplink"), data);
        Directory.CreateSymbolicLink(Path.Combine(paden.CacheRoot, "naar-data"), data);
        File.CreateSymbolicLink(Path.Combine(paden.DataRoot, "proef", "eigen.db-wal"), serverDb + "-wal");
        var servermapVoor = Directory.GetFileSystemEntries(data).Order(StringComparer.Ordinal).ToList();

        string[] buiten =
        [
            Path.Combine(paden.DataRoot, "proef", "link.db"),
            Path.Combine(paden.DataRoot, "proef", "relatief.db"),
            Path.Combine(paden.DataRoot, "proef", "keten.db"),
            Path.Combine(paden.DataRoot, "maplink", "jellyfin" + ".db"),
            Path.Combine(paden.DataRoot, "maplink", "nieuw", "x.db"),
            Path.Combine(paden.DataRoot, "maplink", "jelly-leon", "..", "jellyfin" + ".db"),
            Path.Combine(paden.CacheRoot, "naar-data", "jellyfin" + ".db"),
            Path.Combine(paden.DataRoot, "proef", "eigen.db"),
        ];

        foreach (var pad in buiten)
        {
            Assert.False(paden.MagSchrijven(pad) && paden.MagSchrijven(pad + "-wal"), pad);
            Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(paden, pad, ["CREATE TABLE jl_proef(a INTEGER);"]));
        }

        Assert.Equal(voor, File.ReadAllBytes(serverDb));
        Assert.Equal(servermapVoor, Directory.GetFileSystemEntries(data).Order(StringComparer.Ordinal).ToList());
        Assert.False(Directory.Exists(Path.Combine(data, "nieuw")));

        // Aangescherpt in deel 1b: ook een koppeling binnen de eigen map wordt geweigerd.
        Directory.CreateDirectory(Path.Combine(paden.DataRoot, "echt"));
        Directory.CreateSymbolicLink(Path.Combine(paden.DataRoot, "binnen"), Path.Combine(paden.DataRoot, "echt"));
        Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(paden, Path.Combine(paden.DataRoot, "binnen", "x.db"), ["CREATE TABLE jl_proef(a INTEGER);"]));
        Assert.False(File.Exists(Path.Combine(paden.DataRoot, "echt", "x.db")));
    }

    /// <summary>
    /// R-HARDE-EIS-5: is de eigen map zelf een koppeling (bijvoorbeeld &lt;data&gt;/jelly-leon -&gt; &lt;data&gt;), dan is niets
    /// eronder een eigen plek. Sinds deel 1b worden ook koppelingen boven de eigen map geweigerd.
    /// </summary>
    [Fact]
    public void Database_EigenMapEnDatamapAlsKoppelingWordenGeweigerd()
    {
        var paden = _h.Dienst<JlPaths>();
        var data = Path.GetDirectoryName(paden.DataRoot)!;
        var serverDb = MaakServerDb(data);
        var voor = File.ReadAllBytes(serverDb);

        var gekoppeld = Path.Combine(_h.Map, "gekoppeld");
        Directory.CreateDirectory(gekoppeld);
        File.Copy(serverDb, Path.Combine(gekoppeld, "jellyfin" + ".db"));
        var lus = new JlPaths(gekoppeld, Path.Combine(_h.Map, "cache"));
        Directory.CreateSymbolicLink(Path.Combine(gekoppeld, "jelly-leon"), gekoppeld);
        foreach (var pad in new[] { Path.Combine(lus.DataRoot, "jellyfin" + ".db"), lus.CoreDb, lus.ModuleDb("quality") })
        {
            Assert.False(lus.MagSchrijven(pad), pad);
            Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(lus, pad, ["CREATE TABLE jl_proef(a INTEGER);"]));
        }

        var configLink = Path.Combine(_h.Map, "config-link");
        var viaLink = new JlPaths(configLink, Path.Combine(_h.Map, "cache"));
        Directory.CreateSymbolicLink(configLink, data);
        Assert.True(viaLink.MagSchrijven(viaLink.CoreDb));
        Assert.False(viaLink.MagSchrijven(Path.Combine(configLink, "jellyfin" + ".db")));
        Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(viaLink, Path.Combine(configLink, "jellyfin" + ".db"), ["CREATE TABLE jl_proef(a INTEGER);"]));
        Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(viaLink, viaLink.CoreDb, ["CREATE TABLE jl_proef(a INTEGER);"]));
        var eigen = new JlDatabase(paden, paden.CoreDb, ["CREATE TABLE jl_proef(a INTEGER);"]);
        Assert.Equal(0, eigen.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM jl_proef")));
        Assert.True(File.Exists(Path.Combine(paden.DataRoot, "core", "core.db")));
        Assert.Equal(voor, File.ReadAllBytes(serverDb));
    }

    /// <summary>
    /// R-HARDE-EIS-5 en het vervolgpunt InternalWriteScope: dezelfde padgrens geldt voor bestanden. Een koppeling naar
    /// buiten als doel, als tijdelijk bestand (<c>&lt;doel&gt;.tmp</c>) of als bovenliggende map wordt geweigerd voordat er iets
    /// geschreven, verwijderd of aangemaakt is.
    /// </summary>
    [Fact]
    public void Schrijfbereik_SymbolischeKoppelingNaarBuitenWordtGeweigerd()
    {
        var paden = _h.Dienst<JlPaths>();
        var bereik = _h.Dienst<InternalWriteScope>();
        var data = Path.GetDirectoryName(paden.DataRoot)!;
        var serverDb = MaakServerDb(data);
        var voor = File.ReadAllBytes(serverDb);
        var quality = Path.Combine(paden.DataRoot, "quality");
        Directory.CreateDirectory(quality);
        File.CreateSymbolicLink(Path.Combine(quality, "export.json"), serverDb);
        File.CreateSymbolicLink(Path.Combine(quality, "b.json.tmp"), serverDb);
        Directory.CreateSymbolicLink(Path.Combine(paden.DataRoot, "maplink"), data);

        Assert.Throws<UnauthorizedAccessException>(() => bereik.SchrijfAtomisch(Path.Combine(quality, "export.json"), "{}"u8));
        Assert.Throws<UnauthorizedAccessException>(() => bereik.SchrijfAtomisch(Path.Combine(quality, "b.json"), "{}"u8));
        Assert.Throws<UnauthorizedAccessException>(() => bereik.SchrijfAtomisch(Path.Combine(paden.DataRoot, "maplink", "c.json"), "{}"u8));
        Assert.Throws<UnauthorizedAccessException>(() => bereik.Verwijder(Path.Combine(paden.DataRoot, "maplink", "jellyfin" + ".db")));
        Assert.Throws<UnauthorizedAccessException>(() => bereik.MaakMap(Path.Combine(paden.DataRoot, "maplink", "nieuw")));

        Assert.Equal(voor, File.ReadAllBytes(serverDb));
        Assert.False(File.Exists(Path.Combine(quality, "b.json")));
        Assert.False(File.Exists(Path.Combine(data, "c.json")));
        Assert.False(Directory.Exists(Path.Combine(data, "nieuw")));

        // Tegenproef: binnen de eigen map gaat het wel.
        bereik.SchrijfAtomisch(Path.Combine(quality, "d.json"), "{}"u8);
        Assert.Equal("{}", File.ReadAllText(Path.Combine(quality, "d.json")));
    }

    /// <summary>
    /// R-HARDE-EIS-5: de padgrens geldt bij elke opening, niet alleen bij het aanmaken. Wordt het eigen bestand later
    /// vervangen door een koppeling naar jellyfin.db, dan geeft de volgende opening 503 storage_unavailable en blijft
    /// jellyfin.db byte-gelijk.
    /// </summary>
    [Fact]
    public void Database_KoppelingNaHetAanmakenWordtBijHetOpenenGeweigerd()
    {
        var paden = _h.Dienst<JlPaths>();
        var data = Path.GetDirectoryName(paden.DataRoot)!;
        var serverDb = MaakServerDb(data);
        var voor = File.ReadAllBytes(serverDb);
        var pad = Path.Combine(paden.DataRoot, "proef", "later.db");
        var db = new JlDatabase(paden, pad, ["CREATE TABLE jl_proef(a INTEGER);"]);
        Assert.Equal(0, db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM jl_proef")));

        foreach (var bestand in Directory.GetFiles(Path.GetDirectoryName(pad)!))
        {
            File.Delete(bestand);
        }

        File.CreateSymbolicLink(pad, serverDb);
        var fout = Assert.Throws<JlException>(() => db.Met(v => JlDatabase.Voer(v, "DELETE FROM UserData")));
        Assert.Equal(503, fout.Status);
        Assert.Equal("storage_unavailable", fout.Code);
        Assert.Equal(voor, File.ReadAllBytes(serverDb));
    }

    /// <summary>
    /// R-HARDE-EIS-5 vervolg (S-G1-17 herstelronde 3): SQLite zet <c>-wal</c>, <c>-shm</c> en <c>-journal</c> naast het
    /// echte bestand. Is het opgegeven pad zelf een koppeling binnen de eigen map (a.db -&gt; b.db), dan controleert
    /// JlDatabase de naastbestanden ook naast b.db: een koppeling b.db-wal (of -shm, -journal) naar de naastbestanden
    /// van jellyfin.db weigert de constructor. Vóór het herstel keek de controle alleen naar a.db-wal enz. en liet hij
    /// dit toe (proef H8 van de herreview).
    /// </summary>
    [Fact]
    public void Database_NaastbestandenNaastHetEchtePadWordenGecontroleerd()
    {
        var paden = _h.Dienst<JlPaths>();
        var data = Path.GetDirectoryName(paden.DataRoot)!;
        var serverDb = MaakServerDb(data);
        var voor = File.ReadAllBytes(serverDb);
        var proef = Path.Combine(paden.DataRoot, "proef");
        Directory.CreateDirectory(proef);
        var servermapVoor = Directory.GetFileSystemEntries(data).Order(StringComparer.Ordinal).ToList();

        foreach (var achtervoegsel in new[] { "-wal", "-shm", "-journal" })
        {
            var naam = "n" + achtervoegsel.TrimStart('-');
            var echt = Path.Combine(proef, naam + "-b.db");
            var koppeling = Path.Combine(proef, naam + "-a.db");
            File.WriteAllBytes(echt, []);
            File.CreateSymbolicLink(koppeling, echt);
            File.CreateSymbolicLink(echt + achtervoegsel, serverDb + achtervoegsel);

            Assert.True(paden.MagSchrijven(koppeling) && paden.MagSchrijven(koppeling + achtervoegsel), koppeling);
            Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(paden, koppeling, ["CREATE TABLE jl_proef(a INTEGER);"]));
        }

        Assert.Equal(voor, File.ReadAllBytes(serverDb));
        Assert.Equal(servermapVoor, Directory.GetFileSystemEntries(data).Order(StringComparer.Ordinal).ToList());

        // Aangescherpt in deel 1b: ook zonder koppelingen ernaast blijft de gekoppelde database verboden.
        var goedEcht = Path.Combine(proef, "goed-b.db");
        var goed = Path.Combine(proef, "goed-a.db");
        File.CreateSymbolicLink(goed, goedEcht);
        Assert.Throws<UnauthorizedAccessException>(() => new JlDatabase(paden, goed, ["CREATE TABLE jl_proef(a INTEGER);"]));
        var db = new JlDatabase(paden, goedEcht, ["CREATE TABLE jl_proef(a INTEGER);"]);
        Assert.Equal(0, db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM jl_proef")));
        Assert.True(File.Exists(goedEcht));
    }

    /// <summary>
    /// R-HARDE-EIS-12 (S-G1-17, herstelronde 5): de verbinding die <see cref="JlDatabase.Met{T}"/> aan Core of een module
    /// geeft, bereikt met SQL geen ander databasebestand. <c>ATTACH</c> en <c>VACUUM INTO</c> (dat intern ook een database
    /// koppelt) worden geweigerd, ook met een pad dat pas bij het draaien ontstaat; <c>load_extension</c> staat uit.
    /// jellyfin.db blijft byte-gelijk en naast de serverdatabase ontstaat geen bestand. Vóór het herstel koppelde de
    /// eerste opdracht jellyfin.db gewoon (en kon een module daarna <c>DELETE FROM s.UserData</c> doen).
    /// </summary>
    [Fact]
    public void Database_EigenVerbindingKoppeltGeenAnderDatabasebestand()
    {
        var paden = _h.Dienst<JlPaths>();
        var data = Path.GetDirectoryName(paden.DataRoot)!;
        var serverDb = MaakServerDb(data);
        var voor = File.ReadAllBytes(serverDb);
        var db = new JlDatabase(paden, Path.Combine(paden.DataRoot, "proef", "proef.db"), ["CREATE TABLE jl_proef(a INTEGER);"]);
        Assert.Equal(0, db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM jl_proef")));
        var servermapVoor = Directory.GetFileSystemEntries(data).Order(StringComparer.Ordinal).ToList();
        var nieuw = Path.Combine(data, string.Concat("kopie", ".db"));
        var eigenKopie = Path.Combine(paden.DataRoot, "proef", "kopie.db");

        foreach (var (sql, pad) in new[]
        {
            ("ATTACH DATABASE $p AS s", serverDb),
            ("ATTACH DATABASE $p AS s", nieuw),
            ("ATTACH DATABASE $p AS s", eigenKopie),
            ("VACUUM INTO $p", nieuw),
            ("SELECT load_extension($p)", Path.Combine(data, "x.so")),
        })
        {
            var fout = Assert.Throws<JlException>(() => db.Met(v => JlDatabase.Voer(v, sql, ("$p", pad))));
            Assert.Equal("storage_unavailable", fout.Code);
        }

        Assert.Equal(voor, File.ReadAllBytes(serverDb));
        Assert.Equal(servermapVoor, Directory.GetFileSystemEntries(data).Order(StringComparer.Ordinal).ToList());
        Assert.False(File.Exists(eigenKopie));

        // Tegenproef: dezelfde verbinding werkt gewoon op het eigen bestand.
        db.Met(v => JlDatabase.Voer(v, "INSERT INTO jl_proef VALUES(1)"));
        Assert.Equal(1, db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM jl_proef")));
    }

    /// <summary>
    /// Bewaakt een aanname uit ADR-0032 (proef H8r van de herreview): SQLite opent zelf geen <c>-wal</c>, <c>-shm</c> of
    /// <c>-journal</c> dat een symbolische koppeling is (fout 14, SQLITE_CANTOPEN), ook buiten JlDatabase. Verandert dat
    /// bij een upgrade van SQLite, dan faalt deze test en hoort de padgrens opnieuw beoordeeld te worden. Per opdracht,
    /// niet in één batch: een batch verbergt de fout van een latere opdracht.
    /// </summary>
    [Fact]
    public void Sqlite_OpentGeenKoppelingAlsNaastbestand()
    {
        var map = Path.Combine(_h.Map, "sqlite-proef");
        var buiten = Path.Combine(_h.Map, "buiten");
        Directory.CreateDirectory(map);
        Directory.CreateDirectory(buiten);

        foreach (var (achtervoegsel, wal) in new[] { ("-journal", false), ("-wal", true), ("-shm", true) })
        {
            var db = Path.Combine(map, "b" + achtervoegsel + ".db");
            using (var verbinding = new Microsoft.Data.Sqlite.SqliteConnection("Data Source=" + db + ";Pooling=False"))
            {
                verbinding.Open();
                using var modus = verbinding.CreateCommand();
                modus.CommandText = wal ? "PRAGMA journal_mode=WAL;" : "PRAGMA journal_mode=DELETE;";
                modus.ExecuteNonQuery();
                using var tabel = verbinding.CreateCommand();
                tabel.CommandText = "CREATE TABLE t(a INTEGER);";
                tabel.ExecuteNonQuery();
            }

            Assert.False(File.Exists(db + achtervoegsel), db + achtervoegsel);
            var doel = Path.Combine(buiten, "doel" + achtervoegsel);
            File.CreateSymbolicLink(db + achtervoegsel, doel);

            var fout = Assert.Throws<Microsoft.Data.Sqlite.SqliteException>(() =>
            {
                using var verbinding = new Microsoft.Data.Sqlite.SqliteConnection("Data Source=" + db + ";Pooling=False");
                verbinding.Open();
                using var invoegen = verbinding.CreateCommand();
                invoegen.CommandText = "INSERT INTO t VALUES(1);";
                invoegen.ExecuteNonQuery();
            });

            Assert.Equal(14, fout.SqliteErrorCode);
            Assert.False(File.Exists(doel), doel);
        }
    }

    private static string MaakServerDb(string data)
    {
        Directory.CreateDirectory(data);
        var serverDb = Path.Combine(data, "jellyfin" + ".db");
        using var verbinding = new Microsoft.Data.Sqlite.SqliteConnection("Data Source=" + serverDb + ";Pooling=False");
        verbinding.Open();
        using var opdracht = verbinding.CreateCommand();
        opdracht.CommandText = "CREATE TABLE UserData(UserId TEXT, Played INTEGER, PlaybackPositionTicks INTEGER); INSERT INTO UserData VALUES('u1', 1, 15000000);";
        opdracht.ExecuteNonQuery();
        return serverDb;
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
        geheimen.Schrijf("testkoppeling.bin", [1, 2, 3]);
        Assert.Equal(new byte[] { 1, 2, 3 }, geheimen.Lees("testkoppeling.bin"));
        geheimen.Schrijf("testkoppeling.bin", [4, 5]);
        Assert.Equal(new byte[] { 4, 5 }, geheimen.Lees("testkoppeling.bin"));
        Assert.False(File.Exists(Path.Combine(map, "testkoppeling.bin.tmp")));

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

        geheimen.Verwijder("testkoppeling.bin");
        Assert.Null(geheimen.Lees("testkoppeling.bin"));
        foreach (var naam in new[] { string.Empty, "../core/core.db", "mediaguard.key", "a/b", "a\\b", ".verborgen" })
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

    /// <summary>
    /// Deel 1f (BN-1, R-HARDE-EIS-1): een eigen tmpfs van de container wordt herkend uit de mounttabel, niet uit de naam:
    /// alleen het koppelpunt zelf, van een heel tmpfs-bestandssysteem (wortel "/"); bij gestapelde mounts telt de laatste.
    /// </summary>
    [Fact]
    public void TmpfsCache_AlleenEenEigenKoppelpuntVanEenHeleTmpfsTelt()
    {
        const string Wortel = "21 1 0:20 / / rw,relatime - overlay overlay rw";
        static string Tmpfs(string wortel, string punt) => $"900 21 0:99 {wortel} {punt} rw,nosuid,nodev,noexec,relatime - tmpfs tmpfs rw,size=512000k";

        Assert.True(JlPaths.IsEigenTmpfs("/cache", [Wortel, Tmpfs("/", "/cache")]));
        Assert.True(JlPaths.IsEigenTmpfs("/cache/", [Wortel, Tmpfs("/", "/cache")]));
        Assert.True(JlPaths.IsEigenTmpfs("/mijn cache", [Wortel, Tmpfs("/", "/mijn\\040cache")]));
        Assert.True(JlPaths.IsEigenTmpfs("/cache", [Wortel, "800 21 0:50 /ds /cache rw - zfs pool/ds rw", Tmpfs("/", "/cache")]));
        Assert.False(JlPaths.IsEigenTmpfs("/cache", [Wortel]));
        Assert.False(JlPaths.IsEigenTmpfs("/cache", [Wortel, Tmpfs("/gedeeld", "/cache")]));
        Assert.False(JlPaths.IsEigenTmpfs("/cache", [Wortel, Tmpfs("/", "/")]));
        Assert.False(JlPaths.IsEigenTmpfs("/cache/sub", [Wortel, Tmpfs("/", "/cache")]));
        Assert.False(JlPaths.IsEigenTmpfs("/cache", [Wortel, Tmpfs("/", "/cache"), "800 21 0:50 /ds /cache rw - zfs pool/ds rw"]));
        Assert.False(JlPaths.IsEigenTmpfs("/cache", [Wortel, "800 21 0:50 / /cache rw - zfs pool/ds rw"]));
    }

    /// <summary>
    /// Deel 1f (BN-1, R-HARDE-EIS-1): een eigen tmpfs als cachemap wordt aanvaard met de modus (1777) en eigenaar (root of een
    /// andere gebruiker) die Docker of TrueNAS geeft; zonder tmpfs, als map ín een tmpfs, of als datamap blijft het streng.
    /// De mounttabel is hier synthetisch (een tmpfs koppelen vraagt root); de echte tabel wordt wel gelezen en ontleed.
    /// </summary>
    [Fact]
    public void TmpfsCache_EigenTmpfsAlsCacheWordtAanvaardAlsDatamapNiet()
    {
        if (!OperatingSystem.IsLinux())
        {
            throw new PlatformNotSupportedException("De opslaggrens geldt alleen in de Linux-container.");
        }

        Assert.True(JlPaths.IsEigenTmpfs("/dev/shm", File.ReadLines("/proc/self/mountinfo")), "verwacht /dev/shm als eigen tmpfs in de echte mounttabel");
        var data = Path.Combine(_h.Map, "data");
        var cache = Directory.CreateDirectory(Path.Combine(_h.Map, "tmpfs-cache")).FullName;
        File.SetUnixFileMode(cache, (UnixFileMode)Convert.ToInt32("1777", 8));
        var vreemd = Environment.GetEnvironmentVariable("JL_VREEMDE_OPSLAG") ?? throw new InvalidOperationException("JL_VREEMDE_OPSLAG ontbreekt; maak eerst de tijdelijke eigenaarfixture.");
        static string[] Tmpfs(string punt) => [$"900 21 0:99 / {punt} rw,nosuid,nodev,noexec,relatime - tmpfs tmpfs rw,size=512000k"];

        Assert.Contains("voor groep of anderen", Assert.Throws<UnauthorizedAccessException>(() => new JlPaths(data, cache, [])).Message, StringComparison.Ordinal);
        Assert.Contains("niet van de eigen gebruiker", Assert.Throws<UnauthorizedAccessException>(() => new JlPaths(data, vreemd, [])).Message, StringComparison.Ordinal);
        foreach (var map in new[] { cache, vreemd })
        {
            var paden = new JlPaths(data, map, Tmpfs(map));
            Assert.Equal(map, paden.EigenTmpfs);
            paden.EisVeiligBestand(Path.Combine(paden.CacheRoot, "run", "werker.sock"));
        }

        Assert.Throws<UnauthorizedAccessException>(() => new JlPaths(cache, Path.Combine(_h.Map, "cache"), Tmpfs(cache)));
        Assert.Throws<UnauthorizedAccessException>(() => new JlPaths(data, cache, Tmpfs(_h.Map)));
        Assert.Null(_h.Dienst<JlPaths>().EigenTmpfs);
    }
}
