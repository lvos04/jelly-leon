using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Modules.Devices;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Microsoft.Data.Sqlite;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

public sealed class OpslagImportTests : IDisposable
{
    private readonly Harnas _h = new();
    private static readonly Dictionary<string, string> _devices = new() { ["slug"] = "devices" };

    public void Dispose() => _h.Dispose();

    [Fact]
    public async Task HerstelBewaartermijn_BewaartKijkgegevensVoortgangEnLeesbareVoorkopie()
    {
        _h.Schakelaars.Zet("devices", true);
        var devices = _h.Dienst<DevicesModule>();
        var kijker = Guid.NewGuid();
        devices.RegistreerStart([kijker], "proef-tv", "proef", "direct_play", false, _h.Klok.Nu);
        var server = Path.Combine(_h.Map, "data", "jellyfin.db");
        var guard = Path.Combine(_h.Map, "mediaguard.db");
        using (var v = Open(server))
        {
            JlDatabase.Voer(v, "CREATE TABLE UserData(gezien, hervat, favoriet, beoordeling, audio, ondertitel); INSERT INTO UserData VALUES(1,950,1,8,2,3)");
        }
        using (var v = Open(guard))
        {
            JlDatabase.Voer(v, "CREATE TABLE voortgang(taak, stap); INSERT INTO voortgang VALUES(3,17)");
        }

        var kijkstand = Hash(server);
        var voortgang = Hash(guard);
        var bundel = (await _h.Roep("modules.export", pad: _devices)).Json!.AsObject();
        var hash = bundel["preview_hash"]!.GetValue<string>();
        Assert.DoesNotContain(kijker.ToString("N"), bundel.ToJsonString(), StringComparison.OrdinalIgnoreCase);
        Assert.Equal(1, bundel["sessies"]!.GetValue<int>());
        devices.SchrijfInstellingen(12, devices.LeesInstellingen().Etag);
        var voorbeeld = await _h.Roep("modules.import.preview", bundel.ToJsonString(), pad: _devices);
        Assert.Equal(200, voorbeeld.Status);
        Assert.Equal(hash, voorbeeld.Json!["preview_hash"]!.GetValue<string>());
        Assert.Equal(1, voorbeeld.Json["counts"]!["instellingen"]!.GetValue<int>());
        Assert.Equal(12, devices.LeesInstellingen().Waarde["bewaar_dagen"]!.GetValue<int>());
        Assert.Empty(Kopieen());
        var sleutel = Guid.NewGuid().ToString();
        var antwoord = await PasToe(hash, sleutel);
        Assert.Equal(200, antwoord.Status);
        Assert.True(antwoord.Json!["applied"]!.GetValue<bool>());
        Assert.Equal(30, devices.LeesInstellingen().Waarde["bewaar_dagen"]!.GetValue<int>());
        Assert.Equal(1, devices.TelGebruiker(kijker));
        Assert.Equal(200, (await PasToe(hash, sleutel)).Status);
        Assert.Equal(409, (await PasToe(hash)).Status);
        var kopie = Assert.Single(Kopieen());
        if (OperatingSystem.IsLinux())
        {
            Assert.Equal(UnixFileMode.UserRead | UnixFileMode.UserWrite, File.GetUnixFileMode(kopie));
        }
        using var backup = Open(kopie, SqliteOpenMode.ReadOnly);
        Assert.Equal("ok", JlDatabase.Scalar(backup, "PRAGMA integrity_check"));
        Assert.Equal(12, JlDatabase.Getal(backup, "SELECT bewaar_dagen FROM instellingen"));
        Assert.Equal(1, JlDatabase.Getal(backup, "SELECT COUNT(*) FROM playback_sessions"));
        Assert.Equal(kijkstand, Hash(server));
        Assert.Equal(voortgang, Hash(guard));
    }

    [Fact]
    public async Task OudeBundelBrengtGegevensVanVerwijderdeKijkerNietTerug()
    {
        var devices = _h.Dienst<DevicesModule>();
        _h.Schakelaars.Zet("devices", true);
        var weg = Guid.NewGuid();
        var ander = Guid.NewGuid();
        devices.RegistreerStart([weg], "proef-tv", "eerste", "direct_play", false, _h.Klok.Nu);
        devices.RegistreerStart([ander], "proef-tv", "tweede", "direct_play", false, _h.Klok.Nu);
        var oud = devices.Exporteer();
        Assert.Equal(200, (await _h.Roep("modules.import.preview", oud.ToJsonString(), pad: _devices)).Status);
        Assert.Equal(200, (await PasToe((string)oud["preview_hash"]!)).Status);
        var kopie = Assert.Single(Kopieen());
        using (var v = Open(kopie))
        {
            Assert.Equal(2, JlDatabase.Getal(v, "SELECT COUNT(*) FROM playback_sessions"));
        }

        _h.Dienst<PrivacyService>().VerwijderGebruiker(weg);
        using (var v = Open(kopie))
        {
            Assert.Equal(1, JlDatabase.Getal(v, "SELECT COUNT(*) FROM playback_sessions"));
            Assert.Equal(ander.ToString("N"), JlDatabase.Scalar(v, "SELECT gebruiker FROM playback_sessions"));
        }
        Assert.DoesNotContain(weg.ToString("N"), System.Text.Encoding.Latin1.GetString(await File.ReadAllBytesAsync(kopie, TestContext.Current.CancellationToken)));
        var nieuw = devices.Exporteer();
        Assert.Equal(1, nieuw["sessies"]!.GetValue<long>());
        Assert.DoesNotContain(weg.ToString("N"), nieuw.ToJsonString(), StringComparison.OrdinalIgnoreCase);
        var voorbeeld = await _h.Roep("modules.import.preview", oud.ToJsonString(), pad: _devices);
        Assert.Equal(200, voorbeeld.Status);
        Assert.Equal(200, (await PasToe((string)voorbeeld.Json!["preview_hash"]!)).Status);
        Assert.Equal(0, devices.TelGebruiker(weg));
        Assert.Equal(1, devices.TelGebruiker(ander));
    }

    [Fact]
    public async Task SymbolischeKoppelingAlsExportdoel_WordtGeweigerdEnBehoudtHetDoel()
    {
        _h.Schakelaars.Zet("devices", true);
        Assert.Equal(200, (await _h.Roep("devices.export")).Status);
        var doel = Path.Combine(_h.Dienst<JlPaths>().ModuleDir("devices"), "beheerexport.json");
        var server = Path.Combine(_h.Map, "buiten-export.json");
        await File.WriteAllTextAsync(server, "synthetische inhoud", TestContext.Current.CancellationToken);
        var vooraf = Hash(server);
        File.Delete(doel);
        File.CreateSymbolicLink(doel, server);
        Assert.Equal(503, (await _h.Roep("devices.export")).Status);
        Assert.Equal(vooraf, Hash(server));
        Assert.NotNull(new FileInfo(doel).LinkTarget);
    }

    [Fact]
    public async Task AndereHashNieuwSchemaVerlopenOfVerwisseldeBeheerder_WijzigenNiets()
    {
        _h.Schakelaars.Zet("devices", true);
        var bundel = (await _h.Roep("modules.export", pad: _devices)).Json!.AsObject();
        var origineel = bundel.ToJsonString();
        var hash = bundel["preview_hash"]!.GetValue<string>();
        var db = _h.Dienst<JlPaths>().ModuleDb("devices");
        var vooraf = Hash(db);
        Assert.Equal(409, (await PasToe(hash)).Status);
        bundel["schema_version"] = "2.0";
        Assert.Equal(422, (await _h.Roep("modules.import.preview", bundel.ToJsonString(), pad: _devices)).Status);
        bundel["schema_version"] = "1.0";
        bundel["instellingen"]!["bewaar_dagen"] = 1;
        Assert.Equal(409, (await _h.Roep("modules.import.preview", bundel.ToJsonString(), pad: _devices)).Status);
        Assert.Equal(200, (await _h.Roep("modules.import.preview", origineel, pad: _devices)).Status);
        Assert.Equal(409, (await PasToe(new string('a', 64))).Status);
        var beheerder = _h.Sessies.Wie;
        _h.Sessies.Wie = new SessieIdentiteit(Guid.NewGuid(), true, false);
        Assert.Equal(409, (await PasToe(hash)).Status);
        _h.Sessies.Wie = beheerder;
        _h.Klok.Nu = _h.Klok.Nu.AddMinutes(15);
        Assert.Equal(409, (await PasToe(hash)).Status);
        Assert.Equal(vooraf, Hash(db));
        Assert.Empty(Kopieen());
    }

    [Fact]
    public async Task OudFormaatEnGewijzigdeDoelversie_BeschermenTussenliggendeWijziging()
    {
        _h.Schakelaars.Zet("devices", true);
        var oud = """{"sessies":2,"instellingen":{"bewaar_dagen":21},"schema_version":"1.0","module":"devices"}""";
        var voorbeeld = await _h.Roep("modules.import.preview", oud, pad: _devices);
        Assert.Equal(200, voorbeeld.Status);
        var hash = voorbeeld.Json!["preview_hash"]!.GetValue<string>();
        var devices = _h.Dienst<DevicesModule>();
        devices.SchrijfInstellingen(8, devices.LeesInstellingen().Etag);
        Assert.Equal(412, (await PasToe(hash)).Status);
        Assert.Equal(8, devices.LeesInstellingen().Waarde["bewaar_dagen"]!.GetValue<int>());
        Assert.Empty(Kopieen());
        _h.Schakelaars.Zet("quality", true);
        Assert.Equal(422, (await _h.Roep("modules.import.preview", oud, pad: new() { ["slug"] = "quality" })).Status);
    }

    [Theory]
    [InlineData("devices")]
    [InlineData("quality")]
    [InlineData("segments")]
    [InlineData("watch")]
    [InlineData("recommendations")]
    public async Task Modulebundel_IsPersoonlijkBeheerEnVolgtDeSchakelaar(string slug)
    {
        var pad = new Dictionary<string, string> { ["slug"] = slug };
        Assert.Equal(404, (await _h.Roep("modules.export", pad: pad)).Status);
        _h.Schakelaars.Zet(slug, true);
        var antwoord = await _h.Roep("modules.export", pad: pad);
        Assert.Equal(200, antwoord.Status);
        var inhoud = antwoord.Json!.ToJsonString();
        Assert.Matches("^[0-9a-f]{64}$", antwoord.Json["preview_hash"]!.GetValue<string>());
        Assert.Equal(200, (await _h.Roep("modules.import.preview", inhoud, pad: pad)).Status);
        _h.Sessies.Wie = new(Guid.NewGuid(), true, true);
        Assert.Equal(403, (await _h.Roep("modules.export", pad: pad)).Status);
        Assert.Equal(403, (await _h.Roep("modules.import.preview", inhoud, pad: pad)).Status);
    }

    private Task<Antwoord> PasToe(string hash, string? sleutel = null) =>
        _h.Roep("modules.import.apply", new JsonObject { ["preview_hash"] = hash }.ToJsonString(),
            ["Idempotency-Key: " + (sleutel ?? Guid.NewGuid().ToString())], _devices);

    private string[] Kopieen() => Directory.GetFiles(_h.Dienst<JlPaths>().ModuleDir("devices"), "*.bak");

    private static byte[] Hash(string pad) => SHA256.HashData(File.ReadAllBytes(pad));

    private static SqliteConnection Open(string pad, SqliteOpenMode modus = SqliteOpenMode.ReadWriteCreate)
    {
        var verbinding = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = pad, Mode = modus, Pooling = false }.ToString());
        verbinding.Open();
        return verbinding;
    }
}
