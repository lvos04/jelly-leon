using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Modules.Devices;
using Jellyfin.Plugin.JellyLeon.Modules.Quality;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Microsoft.Data.Sqlite;
using Xunit;
using JlOutbox = Jellyfin.Plugin.JellyLeon.Core.Outbox.Outbox;

namespace Jellyfin.Plugin.JellyLeon.Tests.Modules;

/// <summary>JLT-61(c) met het echte routefilter en gevulde, afzonderlijke SQLite-testbestanden.</summary>
public sealed class ModuleGegevensbeheerTests : IDisposable
{
    private readonly Harnas _h = new();
    private readonly Guid _gebruiker = Guid.NewGuid();
    private readonly Guid _item = Guid.NewGuid();

    public ModuleGegevensbeheerTests()
    {
        var devices = _h.Dienst<DevicesModule>();
        devices.SchrijfInstellingen(7, devices.LeesInstellingen().Etag);
        devices.RegistreerStart([_gebruiker, Guid.NewGuid()], "proef-tv", "proefsessie", "transcode", false, _h.Klok.Nu);
        var quality = _h.Dienst<QualityModule>();
        quality.SchrijfInstellingen(14, quality.LeesInstellingen().Etag);
        quality.MeldBevinding(_item, "proef", "info", _h.Klok.Nu);
        quality.Onderdruk(_item, "proef", _gebruiker, _h.Klok.Nu);
        quality.RondScanAf(3, 1, _h.Klok.Nu);
    }

    public void Dispose() => _h.Dispose();

    [Theory]
    [InlineData("devices", "quality")]
    [InlineData("quality", "devices")]
    public async Task VoorbeeldEnWissen_BewarenAndereTabellenKijkgegevensEnVoortgang(string slug, string ander)
    {
        var paden = _h.Dienst<JlPaths>();
        var server = Path.Combine(_h.Map, "data", "jellyfin.db");
        var voortgang = Path.Combine(_h.Map, "mediaguard.db");
        using (var v = Open(server))
        {
            JlDatabase.Voer(v, """
                CREATE TABLE Users(Id INTEGER PRIMARY KEY);
                INSERT INTO Users VALUES(1), (2);
                CREATE TABLE UserData(UserId INTEGER, Played INTEGER, PlayCount INTEGER, PlaybackPositionTicks INTEGER,
                                      IsFavorite INTEGER, Rating REAL, AudioStreamIndex INTEGER, SubtitleStreamIndex INTEGER);
                INSERT INTO UserData VALUES(1, 0, 1, 15000000, 1, 8, 2, 4), (2, 1, 3, 0, 0, 7, 1, 3);
                """);
        }

        using (var v = Open(voortgang))
        {
            JlDatabase.Voer(v, "CREATE TABLE voortgang(taak INTEGER, stap INTEGER); INSERT INTO voortgang VALUES(4, 19)");
        }

        using (var v = Open(paden.ModuleDb(slug)))
        {
            JlDatabase.Voer(v, "CREATE TABLE ander_onderdeel(waarde TEXT); INSERT INTO ander_onderdeel VALUES('behouden')");
        }

        var kern = _h.Dienst<CoreDatabase>();
        kern.Db.Met(v => JlDatabase.Voer(v, """
            INSERT INTO idempotentie(scope, sleutel, verzoek_hash, staat, gemaakt) VALUES('andere-route', 'proef', 'proef', 'klaar', 0)
            """));
        kern.Kinderprofielen.Met(v => JlDatabase.Voer(v, "INSERT INTO kinderprofielen VALUES('proefaccount', 'bevestigd_kind')"));
        var overigeBestanden = new[] { server, voortgang, paden.ModuleDb(ander), paden.CoreDb, paden.KinderprofielenDb };
        var vooraf = overigeBestanden.Select(BestandHash).ToArray();
        var outbox = _h.Dienst<JlOutbox>();
        var events = outbox.Lees(0, 100).Events.Select(e => e.ToJsonString()).ToArray();
        Assert.NotEmpty(events);
        Assert.False(_h.Schakelaars.IsAan(slug));

        var (export, sha256) = await Exporteer(slug);
        Assert.DoesNotContain(_gebruiker.ToString("N"), export.ToJsonString(), StringComparison.Ordinal);
        var tabellen = slug == "devices" ? new[] { "instellingen", "playback_sessions" } : ["instellingen", "findings", "suppressions", "scans"];
        Assert.Equal(tabellen, export["tables"]!.AsObject().Select(t => t.Key));
        Assert.Equal(1, (int)export["counts"]!["instellingen"]!);
        var personen = export["tables"]![slug == "devices" ? "playback_sessions" : "suppressions"]!.AsArray();
        Assert.All(personen, rij => Assert.Matches("^[0-9a-f]{32}$", (string)rij!["gebruiker"]!));
        Assert.Equal(slug == "devices" ? 2 : 1, personen.Count);
        foreach (var tabel in tabellen)
        {
            Assert.True((long)export["counts"]![tabel]! > 0);
            Assert.Equal((long)export["counts"]![tabel]!, export["tables"]![tabel]!.AsArray().Count);
        }

        var doelVooraf = BestandHash(paden.ModuleDb(slug));
        var sleutel = Guid.NewGuid().ToString();
        var voorbeeld = await Wis(slug, sha256, sleutel, query: null);
        Assert.Equal(200, voorbeeld.Status);
        Assert.False((bool)voorbeeld.Json!["applied"]!);
        Assert.True(JsonNode.DeepEquals(export["counts"], voorbeeld.Json["counts"]));
        Assert.Equal("idempotency_key_reused", (await Wis(slug, sha256, sleutel)).Code);
        Assert.Equal(doelVooraf, BestandHash(paden.ModuleDb(slug)));

        sleutel = Guid.NewGuid().ToString();
        var gewist = await Wis(slug, sha256, sleutel);
        Assert.Equal(200, gewist.Status);
        Assert.True((bool)gewist.Json!["applied"]!);
        Assert.Empty(SchemaControle.Afwijkingen(OpenApiBouwer.Bouw(), "ModuleWisResultaat", gewist.Json));
        Assert.True(JsonNode.DeepEquals(export["counts"], gewist.Json["counts"]));
        using (var v = Open(paden.ModuleDb(slug)))
        {
            foreach (var tabel in tabellen)
            {
                Assert.Equal(0, JlDatabase.Getal(v, "SELECT COUNT(*) FROM " + tabel));
            }

            Assert.Equal("behouden", JlDatabase.Scalar(v, "SELECT waarde FROM ander_onderdeel"));
        }

        Assert.Equal(vooraf, overigeBestanden.Select(BestandHash));
        Assert.Equal(events, outbox.Lees(0, 100).Events.Select(e => e.ToJsonString()));
        Assert.Equal(sha256, BestandHash(ExportPad(slug)));
        var module = _h.Dienst<ModuleRegistry>().Zoek(slug)!;
        Assert.Equal(0, module.TelGebruiker(_gebruiker));

        var instellingen = slug == "devices" ? _h.Dienst<DevicesModule>().LeesInstellingen() : _h.Dienst<QualityModule>().LeesInstellingen();
        Assert.Equal(slug == "devices" ? 30 : 90, (int)instellingen.Waarde["bewaar_dagen"]!);
        // Een vertraagde herhaling mag de later opnieuw ingestelde bewaartermijn niet wissen.
        if (slug == "devices")
        {
            _h.Dienst<DevicesModule>().SchrijfInstellingen(17, instellingen.Etag);
        }
        else
        {
            _h.Dienst<QualityModule>().SchrijfInstellingen(17, instellingen.Etag);
        }

        var herhaling = await Wis(slug, sha256, sleutel);
        Assert.Equal("true", herhaling.Kop["Idempotent-Replay"]);
        using var naHerhaling = Open(paden.ModuleDb(slug));
        Assert.Equal(17, JlDatabase.Getal(naHerhaling, "SELECT bewaar_dagen FROM instellingen"));
    }

    [Theory]
    [InlineData("devices")]
    [InlineData("quality")]
    public async Task AlleenPersoonlijkeBeheerder_MagExporterenEnWissen(string slug)
    {
        _h.Schakelaars.Zet(slug, true);
        var (_, sha256) = await Exporteer(slug);
        var vooraf = BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug));
        foreach (var identiteit in new[] { new SessieIdentiteit(_gebruiker, false, false), new(null, true, false), new(_gebruiker, true, true) })
        {
            _h.Sessies.Wie = identiteit;
            Assert.Equal(403, (await _h.Roep(slug + ".export")).Status);
            Assert.Equal(403, (await Wis(slug, sha256)).Status);
        }

        _h.Sessies.Wie = null;
        Assert.Equal(401, (await Wis(slug, sha256)).Status);
        Assert.Equal(vooraf, BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug)));
    }

    [Theory]
    [InlineData("devices", "quality")]
    [InlineData("quality", "devices")]
    public async Task OntbrekendeVerwisseldeOfBeschadigdeExport_WeigertZonderWijziging(string slug, string ander)
    {
        var vooraf = BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug));
        var (_, verkeerdeHash) = await Exporteer(ander);
        var zonder = await Wis(slug, verkeerdeHash);
        Assert.Equal((409, "export_required"), (zonder.Status, zonder.Reden));
        var (_, sha256) = await Exporteer(slug);
        Assert.Equal("export_required", (await Wis(slug, verkeerdeHash)).Reden);
        File.Copy(ExportPad(ander), ExportPad(slug), overwrite: true);
        Assert.Equal("export_changed", (await Wis(slug, verkeerdeHash)).Reden);
        File.WriteAllText(ExportPad(slug), "{}");
        Assert.Equal("export_required", (await Wis(slug, sha256)).Reden);
        Assert.Equal("export_required", (await Wis(slug, BestandHash(ExportPad(slug)))).Reden);
        File.Delete(ExportPad(slug));
        Assert.Equal("export_required", (await Wis(slug, sha256)).Reden);
        Assert.Equal(vooraf, BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug)));
    }

    [Theory]
    [InlineData("devices")]
    [InlineData("quality")]
    public async Task AlleenExportVanHoogstens24Uur_GeldtOpDeServerklok(string slug)
    {
        var (_, sha256) = await Exporteer(slug);
        var gemaakt = _h.Klok.Nu;
        var vooraf = BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug));
        _h.Klok.Nu = gemaakt.AddTicks(-1);
        Assert.Equal("export_required", (await Wis(slug, sha256)).Reden);
        _h.Klok.Nu = gemaakt.AddHours(24).AddTicks(1);
        Assert.Equal("export_required", (await Wis(slug, sha256)).Reden);
        Assert.Equal(vooraf, BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug)));
        _h.Klok.Nu = gemaakt.AddHours(24);
        Assert.Equal(200, (await Wis(slug, sha256)).Status);
    }

    [Theory]
    [InlineData("devices")]
    [InlineData("quality")]
    public async Task GewijzigdeRijBijGelijkeTellingen_VraagtNieuweExport(string slug)
    {
        var (export, sha256) = await Exporteer(slug);
        if (slug == "devices")
        {
            _h.Dienst<DevicesModule>().RegistreerStop("proefsessie", _h.Klok.Nu.AddMinutes(1));
        }
        else
        {
            _h.Dienst<QualityModule>().Onderdruk(_item, "proef", Guid.NewGuid(), _h.Klok.Nu);
        }

        var voorWeigering = BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug));
        var geweigerd = await Wis(slug, sha256);
        Assert.Equal((409, "export_changed"), (geweigerd.Status, geweigerd.Reden));
        Assert.Equal(voorWeigering, BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug)));
        var (nieuw, nieuweHash) = await Exporteer(slug);
        Assert.True(JsonNode.DeepEquals(export["counts"], nieuw["counts"]));
        Assert.NotEqual(sha256, nieuweHash);
        Assert.Equal(200, (await Wis(slug, nieuweHash)).Status);
    }

    [Theory]
    [InlineData("devices")]
    [InlineData("quality")]
    public async Task OngeldigeAanvragenSelecterenGeenTabelEnWissenNiets(string slug)
    {
        var (_, sha256) = await Exporteer(slug);
        var vooraf = BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug));
        var body = new JsonObject { ["export_sha256"] = sha256 };
        Assert.Equal(400, (await _h.Roep(slug + ".purge", body.ToJsonString(), query: "dry_run=false")).Status);
        Assert.Equal(422, (await Wis(slug, "ongeldige-vingerafdruk")).Status);
        Assert.Equal(422, (await Wis(slug, sha256, query: "dry_run=onbekend")).Status);
        body["table"] = "ander_onderdeel";
        Assert.Equal(422, (await _h.Roep(slug + ".purge", body.ToJsonString(), ["Idempotency-Key: " + Guid.NewGuid()], query: "dry_run=false")).Status);
        Assert.Equal(vooraf, BestandHash(_h.Dienst<JlPaths>().ModuleDb(slug)));
    }

    [Fact]
    public async Task FoutInLaatsteTabel_DraaitOokDeEersteTabellenTerug()
    {
        const string Slug = "quality";
        var (export, sha256) = await Exporteer(Slug);
        using (var v = Open(_h.Dienst<JlPaths>().ModuleDb(Slug)))
        {
            JlDatabase.Voer(v, "CREATE TRIGGER proeffout BEFORE DELETE ON scans BEGIN SELECT RAISE(ABORT, 'proeffout'); END");
        }

        Assert.Equal(503, (await Wis(Slug, sha256)).Status);
        var (na, _) = await Exporteer(Slug);
        Assert.True(JsonNode.DeepEquals(export, na));
    }

    [Fact]
    public async Task IndirecteWijzigingVanEenAndereTabel_DraaitDeHeleActieTerug()
    {
        const string Slug = "quality";
        var (export, sha256) = await Exporteer(Slug);
        var pad = _h.Dienst<JlPaths>().ModuleDb(Slug);
        using (var v = Open(pad))
        {
            JlDatabase.Voer(v, """
                CREATE TABLE ander_onderdeel(waarde INTEGER);
                INSERT INTO ander_onderdeel VALUES(4);
                CREATE TRIGGER proeftelling AFTER DELETE ON findings BEGIN UPDATE ander_onderdeel SET waarde = waarde + 1; END;
                """);
        }

        var geweigerd = await Wis(Slug, sha256);
        Assert.Equal((409, "purge_conflict"), (geweigerd.Status, geweigerd.Reden));
        var (na, _) = await Exporteer(Slug);
        Assert.True(JsonNode.DeepEquals(export, na));
        using var controle = Open(pad);
        Assert.Equal(4, JlDatabase.Getal(controle, "SELECT waarde FROM ander_onderdeel"));
    }

    private string ExportPad(string slug) => Path.Combine(_h.Dienst<JlPaths>().ModuleDir(slug), "beheerexport.json");

    private static string BestandHash(string pad) => Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(pad)));

    private static SqliteConnection Open(string pad)
    {
        var v = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = pad, Pooling = false }.ToString());
        v.Open();
        return v;
    }

    private async Task<(JsonNode Export, string Sha256)> Exporteer(string slug)
    {
        var antwoord = await _h.Roep(slug + ".export");
        Assert.Equal(200, antwoord.Status);
        var sha256 = BestandHash(ExportPad(slug));
        Assert.Equal("\"" + sha256 + "\"", antwoord.Kop["ETag"]);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(File.ReadAllBytes(ExportPad(slug))), antwoord.Json));
        Assert.Empty(SchemaControle.Afwijkingen(OpenApiBouwer.Bouw(), "ModuleExport", antwoord.Json));
        return (antwoord.Json!, sha256);
    }

    private Task<Antwoord> Wis(string slug, string sha256, string? sleutel = null, string? query = "dry_run=false") =>
        _h.Roep(slug + ".purge", new JsonObject { ["export_sha256"] = sha256 }.ToJsonString(),
            ["Idempotency-Key: " + (sleutel ?? Guid.NewGuid().ToString())], query: query);
}
