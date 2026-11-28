using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Data.Events.Users;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Outbox;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Modules.Devices;
using Jellyfin.Plugin.JellyLeon.Modules.Quality;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Events;
using MediaBrowser.Controller.Session;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>Voor- en nametingen via de geregistreerde gebeurtenis en de gewone beheer- en connectorroutes.</summary>
public sealed partial class PrivacyTests
{
    private Task Verwijder(User account) =>
        _h.Dienst<IEventConsumer<UserDeletedEventArgs>>().OnEvent(new UserDeletedEventArgs(account));

    [Fact]
    public async Task OnderdrukkingVanEenBevindingBlijftWerkenNaUserDeleted()
    {
        var weg = new User("proef", "test", "test");
        var ander = Guid.NewGuid();
        var module = _h.Dienst<QualityModule>();
        var item = Guid.NewGuid();
        const string code = "audio_clipping";
        module.MeldBevinding(item, code, "waarschuwing", _h.Klok.Nu);
        module.Onderdruk(item, code, weg.Id, _h.Klok.Nu);
        module.Onderdruk(Guid.NewGuid(), code, ander, _h.Klok.Nu);
        bool Onderdrukt() => module.Items("quality_finding", _h.Klok.Nu).Single()["onderdrukt"]!.GetValue<bool>();
        Assert.True(Onderdrukt());
        Assert.Equal(1, module.TelGebruiker(weg.Id));
        await Verwijder(weg);
        Assert.Equal(0, module.TelGebruiker(weg.Id));
        Assert.Equal(1, module.TelGebruiker(ander));
        Assert.True(Onderdrukt(), "Dezelfde bevinding was vóór UserDeleted onderdrukt en is daarna opnieuw zichtbaar.");
    }

    [Fact]
    public async Task OutboxKanNaUserDeletedGeenActorMeerAanHetAccountKoppelen()
    {
        var account = new User("proef", "test", "test");
        var privacy = _h.Dienst<PrivacyService>();
        var bus = _h.Dienst<Outbox>();
        var weg = privacy.Pseudoniem(account.Id);
        var ander = privacy.Pseudoniem(Guid.NewGuid());
        foreach (var actor in new[] { weg, ander })
        {
            bus.Meld("quality", "media.quality_scan.completed", "quality_scan", "scan-1", new JsonObject(), "user", actor);
        }

        var voor = bus.Lees(0, 20);
        Assert.Equal(2, voor.Events.Count);
        Assert.Equal(weg, (string?)voor.Events[0]["actor"]!["id"]);
        Assert.Equal(ander, (string?)voor.Events[1]["actor"]!["id"]);
        await Verwijder(account);
        var na = bus.Lees(0, 20);
        Assert.Equal(voor.Laatste, na.Laatste);
        Assert.Equal(2, na.Events.Count);
        Assert.DoesNotContain(weg, na.Events[0].ToJsonString(), StringComparison.Ordinal);
        voor.Events[0]["actor"]!["id"] = "verwijderd";
        Assert.True(JsonNode.DeepEquals(voor.Events[0], na.Events[0]));
        Assert.True(JsonNode.DeepEquals(voor.Events[1], na.Events[1]));
    }

    [Fact]
    public async Task VerwijderenRuimtDeJuisteIdempotentieOpEnBehoudtDeHerhaalbeveiliging()
    {
        var account = new User("proef", "test", "test");
        var ander = Guid.NewGuid();
        _h.Schakelaars.Zet("devices", true);
        async Task Wijzig(Guid beheerder, int dagen)
        {
            _h.Sessies.Wie = new SessieIdentiteit(beheerder, true, false);
            var etag = (await _h.Roep("devices.settings.get")).Kop["ETag"];
            var inhoud = new JsonObject { ["bewaar_dagen"] = dagen };
            var antwoord = await _h.Roep("devices.settings.put", inhoud.ToJsonString(),
                ["Idempotency-Key: " + Guid.NewGuid(), "If-Match: " + etag]);
            Assert.Equal(200, antwoord.Status);
        }

        await Wijzig(account.Id, 14);
        await Wijzig(ander, 21);
        var db = _h.Dienst<CoreDatabase>().Db;
        long Idempotentie(Guid gebruiker) => db.Met(v => JlDatabase.Getal(v,
            "SELECT count(*) FROM idempotentie WHERE instr(scope,$p)>0",
            ("$p", _h.Dienst<PrivacyService>().Pseudoniem(gebruiker))));
        Assert.Equal(1, Idempotentie(account.Id));
        Assert.Equal(1, Idempotentie(ander));

        _h.Koppel();
        var tokenId = Guid.NewGuid().ToString("D");
        var token = _h.Hub.Token(_h.Klok.Nu, "admin", (_, claims) =>
        {
            claims["sub"] = account.Id.ToString("D");
            claims["jti"] = tokenId;
        });
        Assert.Equal(501, (await _h.RoepHub("connector.propose", token)).Status);
        long Jti() => db.Met(v => JlDatabase.Getal(v, "SELECT count(*) FROM hub_jti WHERE jti=$jti", ("$jti", tokenId)));
        Assert.Equal(1, Jti());
        await Verwijder(account);
        Assert.Equal(0, Idempotentie(account.Id));
        Assert.Equal(1, Idempotentie(ander));
        Assert.Equal(1, Jti());
        var herhaling = await _h.RoepHub("connector.propose", token);
        Assert.Equal((401, "token_replayed"), (herhaling.Status, herhaling.Reden));
    }

    [Fact]
    public async Task SegmentauditKoppeltNaUserDeletedDeBeheeractieLosVanHetAccount()
    {
        var account = new User("proef", "test", "test");
        _h.Schakelaars.Zet("segments", true);
        async Task Ontdooi(Guid beheerder)
        {
            _h.Sessies.Wie = new SessieIdentiteit(beheerder, true, false);
            var antwoord = await _h.Roep("segments.orphans.unfreeze", """{"reason":"handmatige controle"}""",
                ["Idempotency-Key: " + Guid.NewGuid()]);
            Assert.Equal(200, antwoord.Status);
        }

        var ander = Guid.NewGuid();
        await Ontdooi(account.Id);
        await Ontdooi(ander);
        var privacy = _h.Dienst<PrivacyService>();
        var pad = _h.Dienst<JlPaths>().ModuleDb("segments");
        string[] Audit()
        {
            using var v = OpenTestDb(pad, SqliteOpenMode.ReadOnly);
            return JlDatabase.Rijen(v, "SELECT actor FROM audit WHERE soort='ontdooien' AND reden='handmatige controle' ORDER BY id")
                .Select(r => (string)r[0]!).ToArray();
        }

        var blijft = "session:" + privacy.Pseudoniem(ander);
        Assert.Equal(["session:" + privacy.Pseudoniem(account.Id), blijft], Audit());
        await Verwijder(account);
        Assert.Equal(["verwijderd", blijft], Audit());
    }

    [Fact]
    public async Task VerwijderenWistAlleenDeSegmentrolVanHetBedoeldeAccount()
    {
        var account = new User("redacteur", "test", "test");
        var ander = Guid.NewGuid();
        _h.Schakelaars.Editors.UnionWith([account.Id, ander]);
        Assert.True(_h.Schakelaars.IsSegmentEditor(account.Id));
        await Verwijder(account);
        Assert.False(_h.Schakelaars.IsSegmentEditor(account.Id));
        Assert.True(_h.Schakelaars.IsSegmentEditor(ander));
    }

    [Fact]
    public async Task RegisterVermeldtHoeDeOnderdrukkingsregelBijVerwijderenWordtBehandeld()
    {
        var antwoord = await _h.Roep("privacy.register");
        Assert.Equal(200, antwoord.Status);
        var regel = antwoord.Json!["items"]!.AsArray().Single(r => (string?)r!["tabel"] == "suppressions");
        Assert.True(regel!.ToJsonString().Contains("pseudonimis", StringComparison.OrdinalIgnoreCase),
            "De registerrij voor suppressions noemt geen pseudonimisering van de auteur.");
    }

    [Fact]
    public async Task UserDeletedBehoudtDeGevuldeKijkgeschiedenisEnVoortgang()
    {
        var account = new User("proef", "test", "test");
        var ander = Guid.NewGuid();
        var module = _h.Dienst<DevicesModule>();
        module.RegistreerStart([account.Id, ander], "test", "sessie", "direct_play", false, _h.Klok.Nu);
        Assert.Equal(1, module.TelGebruiker(account.Id));
        var kijkpad = Path.Combine(_h.Map, "data", "jellyfin.db");
        var voortgangspad = Path.Combine(_h.Map, "mediaguard-proef.db");
        using var kijk = OpenTestDb(kijkpad);
        using var guard = OpenTestDb(voortgangspad);
        JlDatabase.Voer(kijk, "CREATE TABLE UserData(gebruiker TEXT PRIMARY KEY, gezien INTEGER, hervat INTEGER, favoriet INTEGER, beoordeling INTEGER, spoor INTEGER)");
        JlDatabase.Voer(kijk, "INSERT INTO UserData VALUES ($weg,1,15000000,1,4,2), ($ander,0,25000000,0,3,1)",
            ("$weg", account.Id.ToString("N")), ("$ander", ander.ToString("N")));
        JlDatabase.Voer(guard, "CREATE TABLE voortgang(gebruiker TEXT, taak INTEGER PRIMARY KEY, positie INTEGER)");
        JlDatabase.Voer(guard, "INSERT INTO voortgang VALUES ($weg,1,37), ($ander,2,82)",
            ("$weg", account.Id.ToString("N")), ("$ander", ander.ToString("N")));
        Assert.Equal(2, JlDatabase.Getal(kijk, "SELECT COUNT(*) FROM UserData"));
        Assert.Equal(2, JlDatabase.Getal(guard, "SELECT COUNT(*) FROM voortgang"));
        var stop = TestContext.Current.CancellationToken;
        var kijkVoor = await File.ReadAllBytesAsync(kijkpad, stop);
        var guardVoor = await File.ReadAllBytesAsync(voortgangspad, stop);
        await Verwijder(account);
        Assert.Equal(0, module.TelGebruiker(account.Id));
        Assert.Equal(1, module.TelGebruiker(ander));
        Assert.Equal(kijkVoor, await File.ReadAllBytesAsync(kijkpad, stop));
        Assert.Equal(guardVoor, await File.ReadAllBytesAsync(voortgangspad, stop));
        Assert.Equal(25000000, JlDatabase.Getal(kijk, "SELECT hervat FROM UserData WHERE gebruiker=$g", ("$g", ander.ToString("N"))));
        Assert.Equal(82, JlDatabase.Getal(guard, "SELECT positie FROM voortgang WHERE gebruiker=$g", ("$g", ander.ToString("N"))));
    }

    [Fact]
    public async Task NieuweDevicesExportVerliestAlleenHetVerwijderdeAccount()
    {
        var module = _h.Dienst<DevicesModule>();
        var account = new User("proef", "test", "test");
        var ander = Guid.NewGuid();
        module.RegistreerStart([account.Id, ander], "test", "sessie", "direct_play", false, _h.Klok.Nu);
        var weg = module.Gegevensbeheer.ExportGebruiker(account.Id.ToString("N"));
        var blijft = module.Gegevensbeheer.ExportGebruiker(ander.ToString("N"));
        var voor = await _h.Roep("devices.export");
        Assert.Equal(200, voor.Status);
        var rijen = voor.Json!["tables"]!["playback_sessions"]!.AsArray();
        Assert.Equal(2, rijen.Count);
        Assert.Contains(rijen, r => (string?)r!["gebruiker"] == weg);
        Assert.Contains(rijen, r => (string?)r!["gebruiker"] == blijft);
        await Verwijder(account);
        var na = await _h.Roep("devices.export");
        Assert.Equal(200, na.Status);
        var rij = Assert.Single(na.Json!["tables"]!["playback_sessions"]!.AsArray());
        Assert.True((string?)rij!["gebruiker"] == blijft);
        foreach (var naald in new[] { weg, account.Id.ToString("D"), account.Id.ToString("N") })
        {
            Assert.False(na.Json.ToJsonString().Contains(naald, StringComparison.OrdinalIgnoreCase));
        }
    }

    [Theory]
    [InlineData("devices")]
    [InlineData("quality")]
    public async Task AlleenEenOpgeslagenExportMetDeVerwijderdeAuteurVervalt(string slug)
    {
        var weg = new User("proef", "test", "test");
        var ander = Guid.NewGuid();
        var module = (ModuleBasis)_h.Dienst<ModuleRegistry>().Zoek(slug)!;
        var pad = Path.Combine(_h.Dienst<JlPaths>().ModuleDir(slug), "beheerexport.json");
        var kenmerk = module.Gegevensbeheer.ExportGebruiker(weg.Id.ToString("N"));
        if (module is DevicesModule d)
        {
            d.RegistreerStart([weg.Id, ander], "test", "oud", "direct_play", false, _h.Klok.Nu);
        }
        else
        {
            ((QualityModule)module).Onderdruk(Guid.NewGuid(), "audio_clipping", weg.Id, _h.Klok.Nu);
            ((QualityModule)module).Onderdruk(Guid.NewGuid(), "audio_clipping", ander, _h.Klok.Nu);
        }

        Assert.Equal(200, (await _h.Roep(slug + ".export")).Status);
        var voor = await File.ReadAllTextAsync(pad, TestContext.Current.CancellationToken);
        Assert.Contains(kenmerk, voor, StringComparison.Ordinal);
        await Verwijder(new User("zonder-rijen", "test", "test"));
        Assert.Equal(voor, await File.ReadAllTextAsync(pad, TestContext.Current.CancellationToken));
        if (module is DevicesModule devices)
        {
            _h.Klok.Nu = _h.Klok.Nu.AddDays(31);
            devices.RegistreerStart([ander], "test", "recent", "direct_play", false, _h.Klok.Nu);
            Assert.Equal(0, devices.TelGebruiker(weg.Id));
        }

        await Verwijder(weg);
        Assert.False(File.Exists(pad));
        Assert.Equal(200, (await _h.Roep(slug + ".export")).Status);
        Assert.DoesNotContain(kenmerk, await File.ReadAllTextAsync(pad, TestContext.Current.CancellationToken), StringComparison.Ordinal);
        Assert.Equal(1, module.TelGebruiker(ander));
    }

    [Fact]
    public async Task DevicesExportBevatNaVerstrijkenVanDeTermijnGeenOudeSessie()
    {
        var module = _h.Dienst<DevicesModule>();
        var account = Guid.NewGuid();
        var ander = Guid.NewGuid();
        var begin = _h.Klok.Nu;
        module.SchrijfInstellingen(7, module.LeesInstellingen().Etag);
        module.RegistreerStart([account], "test", "eerste", "direct_play", false, begin);
        module.RegistreerStop("eerste", begin);
        module.RegistreerStart([ander], "test", "tweede", "direct_play", false, begin.AddDays(1));
        _h.Klok.Nu = begin.AddDays(7);
        Assert.Equal(2, (await _h.Roep("devices.export")).Json!["tables"]!["playback_sessions"]!.AsArray().Count);
        _h.Klok.Nu = _h.Klok.Nu.AddSeconds(1);
        var export = await _h.Roep("devices.export");
        Assert.Equal(200, export.Status);
        var behouden = Assert.Single(export.Json!["tables"]!["playback_sessions"]!.AsArray());
        Assert.Equal(module.Gegevensbeheer.ExportGebruiker(ander.ToString("N")), (string?)behouden!["gebruiker"]);
        Assert.Equal(0, module.TelGebruiker(account));
        Assert.Equal(1, module.TelGebruiker(ander));
    }

    [Fact]
    public async Task BewaartermijnVerstrijktOokZonderActiviteitBijUitgeschakeldeModule()
    {
        var module = _h.Dienst<DevicesModule>();
        var klok = new Mock<TimeProvider>();
        var timer = new Mock<ITimer>();
        TimerCallback? tik = null;
        klok.Setup(k => k.GetUtcNow()).Returns(() => _h.Klok.Nu);
        klok.Setup(k => k.CreateTimer(It.IsAny<TimerCallback>(), null, TimeSpan.Zero, TimeSpan.FromHours(1)))
            .Callback<TimerCallback, object?, TimeSpan, TimeSpan>((callback, _, _, _) => tik = callback)
            .Returns(timer.Object);
        var dienst = new DevicesListener(_h.Dienst<ISessionManager>(), module, _h.Dienst<ModuleRegistry>(), klok.Object, NullLogger<DevicesListener>.Instance);
        var account = Guid.NewGuid();
        module.RegistreerStart([account], "test", "eerste", "direct_play", false, _h.Klok.Nu);
        await dienst.StartAsync(TestContext.Current.CancellationToken);
        try
        {
            Assert.Equal(1, module.TelGebruiker(account));
            _h.Klok.Nu = _h.Klok.Nu.AddDays(31);
            Assert.NotNull(tik);
            tik(null);
            Assert.Equal(0, module.TelGebruiker(account));
        }
        finally
        {
            await dienst.StopAsync(TestContext.Current.CancellationToken);
        }

        timer.Verify(t => t.DisposeAsync(), Times.Once);
    }

    [Fact]
    public async Task RegistertestWeigertEenGevuldeTabelMetUserIdZonderRegisterregel()
    {
        await PrivacyRegister_NoemtElkeTabelMetDoelEnBewaartermijn();
        using (var v = OpenTestDb(_h.Dienst<JlPaths>().ModuleDb("devices")))
        {
            JlDatabase.Voer(v, "CREATE TABLE controletabel(user_id TEXT NOT NULL)");
            Assert.Equal(1, JlDatabase.Voer(v, "INSERT INTO controletabel VALUES ($id)", ("$id", Guid.NewGuid().ToString("D"))));
        }

        var fout = await Assert.ThrowsAsync<Xunit.Sdk.ContainsException>(PrivacyRegister_NoemtElkeTabelMetDoelEnBewaartermijn);
        Assert.Contains("controletabel", fout.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void RuweScannerVindtSchrijfwijzenEnZijbestanden(bool inCache)
    {
        var paden = _h.Dienst<JlPaths>();
        var map = Path.Combine(inCache ? paden.CacheRoot : paden.DataRoot, "featurecache");
        Directory.CreateDirectory(map);
        var id = Guid.Parse("abcdef01-abcd-4bcd-abcd-abcdef012345");
        string[] namen = ["normaal.db", "proef.db-wal", "proef.db-shm", "compact", "binair-le", "binair-be"];
        byte[][] vormen = [
            Encoding.ASCII.GetBytes(id.ToString("D")), Encoding.ASCII.GetBytes(id.ToString("D").ToUpperInvariant()),
            Encoding.ASCII.GetBytes(id.ToString("N").ToUpperInvariant()), Encoding.ASCII.GetBytes(id.ToString("N")),
            id.ToByteArray(), id.ToByteArray(bigEndian: true)];
        for (var i = 0; i < namen.Length; i++)
        {
            File.WriteAllBytes(Path.Combine(map, namen[i]), vormen[i]);
        }

        Assert.Equal(namen.Order(), RuweVindplaatsen(id).Order());
        Assert.Empty(RuweVindplaatsen(Guid.NewGuid()));
    }

    [Fact]
    public async Task HubKindKrijgtOpElkeConnectorrouteDezelfdeWeigering()
    {
        _h.Koppel();
        Assert.Equal(200, (await _h.RoepHub("connector.discover", _h.Hub.Token(_h.Klok.Nu))).Status);
        var routes = RouteTable.Alle.Where(r => r.Pad.StartsWith("/connector/v1/", StringComparison.Ordinal)).ToArray();
        Assert.NotEmpty(routes);
        foreach (var route in routes)
        {
            foreach (var metKijkersrol in new[] { false, true })
            {
                var token = _h.Hub.Token(_h.Klok.Nu, "kind", (_, claims) =>
                {
                    if (metKijkersrol)
                    {
                        claims["roles"] = new JsonArray("viewer", "kind");
                    }
                });
                var antwoord = await _h.RoepHub(route.Id, token);
                Assert.Equal((403, "forbidden", "role_kind"), (antwoord.Status, antwoord.Code, antwoord.Reden));
            }
        }
    }

    [Fact]
    public async Task VerborgenEnOntbrekendItemGevenEenKindHetzelfdeAntwoordZonderTitelOfEvent()
    {
        _h.Schakelaars.Zet("segments", true);
        var film = new Movie { Id = Guid.NewGuid(), Name = "Synthetische verborgen filmtitel" };
        var kind = new User("kind", "test", "test") { MaxParentalRatingScore = 1 };
        var kijker = new User("kijker", "test", "test");
        foreach (var account in new[] { kind, kijker })
        {
            _h.Gebruikers.Setup(g => g.GetUserById(account.Id)).Returns(account);
        }

        _h.Bibliotheek.Setup(b => b.GetItemById<Video>(film.Id, kijker)).Returns(film);
        _h.Bibliotheek.Setup(b => b.GetCollectionFolders(film)).Returns([new Folder { Id = Guid.NewGuid() }]);
        Task<Antwoord> Vraag(Guid id) => _h.Roep("segments.item", pad: new Dictionary<string, string> { ["itemId"] = id.ToString() });
        var beleid = _h.Dienst<KidPolicy>();
        _h.Sessies.Wie = new SessieIdentiteit(kijker.Id, false, beleid.IsKid(kijker));
        Assert.Equal(200, (await Vraag(film.Id)).Status);

        var bus = _h.Dienst<Outbox>();
        bus.Meld("quality", "media.quality_scan.completed", "quality_scan", "scan-1", new JsonObject());
        var voor = bus.Lees(0, 20);
        Assert.NotEmpty(voor.Events);
        Assert.True(beleid.IsKid(kind));
        _h.Sessies.Wie = new SessieIdentiteit(kind.Id, false, beleid.IsKid(kind));
        var verborgen = await Vraag(film.Id);
        var ontbreekt = await Vraag(Guid.NewGuid());
        Assert.Equal(404, verborgen.Status);
        Assert.Equal(404, ontbreekt.Status);
        foreach (var antwoord in new[] { verborgen, ontbreekt })
        {
            Assert.DoesNotContain(film.Name, antwoord.Json!.ToJsonString(), StringComparison.Ordinal);
            Assert.True(antwoord.Json.AsObject().Remove("trace_id"));
        }

        Assert.True(JsonNode.DeepEquals(verborgen.Json, ontbreekt.Json));
        var na = bus.Lees(0, 20);
        Assert.Equal(voor.Laatste, na.Laatste);
        Assert.All(na.Events, e => Assert.DoesNotContain(film.Name, e.ToJsonString(), StringComparison.Ordinal));
    }
}
