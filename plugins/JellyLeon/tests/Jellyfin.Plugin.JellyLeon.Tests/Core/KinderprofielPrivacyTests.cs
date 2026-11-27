using System;
using System.IO;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Data;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Database.Implementations.Enums;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Controller.Net;
using Microsoft.AspNetCore.Http;
using Microsoft.Data.Sqlite;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

public sealed class KinderprofielPrivacyTests : IDisposable
{
    private readonly Harnas _h = new(gebruikServerauth: true);
    private readonly User _beheerder = new("beheer", "proef", "proef");
    private readonly User _profiel = new("profiel", "proef", "proef") { MaxParentalRatingScore = 10 };
    private readonly AuthorizationInfo _sessie = new() { IsAuthenticated = true };

    public KinderprofielPrivacyTests()
    {
        _beheerder.SetPermission(PermissionKind.IsAdministrator, true);
        _sessie.User = _beheerder;
        _h.Authenticatie.Setup(a => a.Authenticate(It.IsAny<HttpRequest>())).ReturnsAsync(_sessie);
        _h.Gebruikers.Setup(g => g.GetUserById(_profiel.Id)).Returns(_profiel);
        _h.Gebruikers.Setup(g => g.GetUserById(_beheerder.Id)).Returns(_beheerder);
    }

    public void Dispose() => _h.Dispose();

    [Theory]
    [InlineData(false, false, "admin_required")]
    [InlineData(true, false, "kid_profile")]
    [InlineData(true, true, "kid_profile")]
    public async Task AlleenBeheerderMagBevestigen_KindKanZichzelfNietOntkinderen(bool eigenProfiel, bool beheerrecht, string reden)
    {
        var voorstel = await Lees(_profiel);
        Status(voorstel, "voorgesteld", true);
        var actor = eigenProfiel ? _profiel : new User("lezer", "proef", "proef");
        actor.SetPermission(PermissionKind.IsAdministrator, beheerrecht);
        _sessie.User = actor;

        var geweigerd = await Bevestig(_profiel, false, voorstel.Kop["ETag"]);
        Assert.Equal((403, "forbidden", reden), (geweigerd.Status, geweigerd.Code, geweigerd.Reden));
        Assert.Equal(403, (await Lees(_profiel)).Status);
        _sessie.User = _beheerder;
        Status(await Lees(_profiel), "voorgesteld", true);
    }

    [Fact]
    public async Task ApiSleutelEnAnoniemeSessieKunnenGeenProfielBevestigen()
    {
        var voorstel = await Lees(_profiel);
        _sessie.User = null;
        _sessie.IsApiKey = true;
        Assert.Equal(403, (await Lees(_profiel)).Status);
        Assert.Equal(403, (await Bevestig(_profiel, false, voorstel.Kop["ETag"])).Status);
        _sessie.IsApiKey = false;
        _sessie.IsAuthenticated = false;
        Assert.Equal(401, (await Bevestig(_profiel, false, voorstel.Kop["ETag"])).Status);
        _sessie.IsAuthenticated = true;
        _sessie.User = _beheerder;
        Status(await Lees(_profiel), "voorgesteld", true);
    }

    [Fact]
    public async Task SessieSteltVoor_BeheerkeuzeGeldtVoorElkeVolgendeSessie()
    {
        _profiel.SetPermission(PermissionKind.IsAdministrator, true);
        _sessie.User = _profiel;
        Assert.Equal("kid_profile", (await _h.Roep("modules.list")).Reden);
        _profiel.MaxParentalRatingScore = null;
        Assert.Equal("kid_profile", (await _h.Roep("modules.list")).Reden);

        _sessie.User = _beheerder;
        var voorstel = await Lees(_profiel);
        Status(voorstel, "voorgesteld", true);
        var sleutel = Guid.NewGuid();
        var volwassen = await Bevestig(_profiel, false, voorstel.Kop["ETag"], sleutel);
        Status(volwassen, "bevestigd_volwassene", false);
        Assert.Equal("true", (await Bevestig(_profiel, false, voorstel.Kop["ETag"], sleutel)).Kop["Idempotent-Replay"]);
        Assert.Equal(412, (await Bevestig(_profiel, true, voorstel.Kop["ETag"])).Status);

        _profiel.SetPreference(PreferenceKind.BlockedTags, ["eng"]);
        _sessie.User = _profiel;
        Assert.Equal(200, (await _h.Roep("modules.list")).Status);
        Assert.True(_h.Dienst<KidPolicy>().IsKid(_profiel, hubRolKind: true));
        _profiel.SetPermission(PermissionKind.IsAdministrator, false);
        Assert.Equal("admin_required", (await _h.Roep("modules.list")).Reden);

        _sessie.User = _beheerder;
        Status(await Bevestig(_profiel, true, volwassen.Kop["ETag"]), "bevestigd_kind", true);
        _profiel.SetPreference(PreferenceKind.BlockedTags, []);
        _sessie.User = _profiel;
        Assert.Equal("kid_profile", (await _h.Roep("privacy.register")).Reden);

        var paden = _h.Dienst<JlPaths>();
        var kern = new CoreDatabase(paden);
        var privacy = new PrivacyService(_h.Dienst<ModuleRegistry>(), kern, new SecretStore(paden));
        var naHerstart = new KidPolicy(kern, privacy, _h.Gebruikers.Object);
        Assert.True(naHerstart.IsKid(_profiel));
        Assert.False(naHerstart.IsKid(_beheerder));
    }

    [Fact]
    public async Task SignaalUitDeSessieBlijftGeldenBijEenGelijktijdigeProfielwijziging()
    {
        _profiel.SetPermission(PermissionKind.IsAdministrator, true);
        var zonderFilter = new User("profiel", "proef", "proef") { Id = _profiel.Id };
        zonderFilter.SetPermission(PermissionKind.IsAdministrator, true);
        _h.Gebruikers.Setup(g => g.GetUserById(_profiel.Id)).Returns(zonderFilter);

        _sessie.User = _profiel;
        Assert.Equal("kid_profile", (await _h.Roep("modules.list")).Reden);
        _sessie.User = zonderFilter;
        Assert.Equal("kid_profile", (await _h.Roep("modules.list")).Reden);
        _sessie.User = _beheerder;
        Status(await Lees(zonderFilter), "voorgesteld", true);
    }

    [Fact]
    public async Task AlleenBekendVoorstelEnGeldigeBeheerinvoerWijzigenDeStatus()
    {
        var onbekend = Guid.NewGuid();
        _h.Gebruikers.Setup(g => g.GetUserById(onbekend)).Returns((User?)null);
        Assert.Equal(404, (await _h.Roep("privacy.kid.get", pad: new() { ["id"] = onbekend.ToString() })).Status);
        Status(await Lees(_beheerder), "geen_voorstel", false);
        Assert.Equal(404, (await Bevestig(_beheerder, false, "\"geen_voorstel\"")).Status);

        var voorstel = await Lees(_profiel);
        var body = new JsonObject { ["user_id"] = _profiel.Id.ToString("N"), ["is_kid"] = false };
        var etag = "If-Match: " + voorstel.Kop["ETag"];
        Assert.Equal(400, (await _h.Roep("privacy.kid.confirm", body.ToJsonString(), [etag])).Status);
        Assert.Equal(428, (await _h.Roep("privacy.kid.confirm", body.ToJsonString(), ["Idempotency-Key: " + Guid.NewGuid()])).Status);
        body.Remove("is_kid");
        Assert.Equal(422, (await _h.Roep("privacy.kid.confirm", body.ToJsonString(), [etag, "Idempotency-Key: " + Guid.NewGuid()])).Status);
        // De server heeft het account intussen verwijderd, terwijl de plugin de verwijdergebeurtenis nog verwerkt.
        _h.Gebruikers.Setup(g => g.GetUserById(_profiel.Id)).Returns((User?)null);
        Assert.Equal(404, (await Bevestig(_profiel, false, voorstel.Kop["ETag"])).Status);
        _h.Gebruikers.Setup(g => g.GetUserById(_profiel.Id)).Returns(_profiel);
        Status(await Lees(_profiel), "voorgesteld", true);
    }

    [Fact]
    public async Task VoorstelEnBevestiging_BewarenBestaandeRijenEnBeideVoortgangsbestanden()
    {
        var paden = _h.Dienst<JlPaths>();
        // Vul eerst de bestaande kern, zonder een profielopslag aan te maken.
        var oud = _h.Dienst<CoreDatabase>().Db;
        oud.Met(v => JlDatabase.Voer(v, "INSERT INTO jobs(id,soort,module,payload,staat,gemaakt) VALUES(7,'proef','core','bestaande taak','wacht',1)"));
        var kernversie = oud.Met(v => JlDatabase.Getal(v, "PRAGMA user_version"));
        Assert.True(kernversie > 0);

        Assert.False(File.Exists(paden.KinderprofielenDb));
        var kijk = Path.Combine(_h.Map, "data", "jellyfin.db");
        var voortgang = Path.Combine(_h.Map, "mediaguard-proef.db");
        using (var server = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = kijk, Pooling = false }.ToString()))
        using (var guard = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = voortgang, Pooling = false }.ToString()))
        {
            server.Open();
            guard.Open();
            JlDatabase.Voer(server, "CREATE TABLE UserData(Played INTEGER, PlaybackPositionTicks INTEGER); INSERT INTO UserData VALUES(1,15000000)");
            JlDatabase.Voer(guard, "CREATE TABLE voortgang(positie INTEGER); INSERT INTO voortgang VALUES(37)");
            var kijkVoor = File.ReadAllBytes(kijk);
            var guardVoor = File.ReadAllBytes(voortgang);
            var kijkpositie = JlDatabase.Getal(server, "SELECT PlaybackPositionTicks FROM UserData WHERE Played=1");
            var guardpositie = JlDatabase.Getal(guard, "SELECT positie FROM voortgang");
            Assert.Equal(15000000L, kijkpositie);
            Assert.Equal(37L, guardpositie);

            var voorstel = await Lees(_profiel);
            Status(voorstel, "voorgesteld", true);
            Status(await Bevestig(_profiel, false, voorstel.Kop["ETag"]), "bevestigd_volwassene", false);

            Assert.Equal(kijkpositie, JlDatabase.Getal(server, "SELECT PlaybackPositionTicks FROM UserData WHERE Played=1"));
            Assert.Equal(guardpositie, JlDatabase.Getal(guard, "SELECT positie FROM voortgang"));
            Assert.Equal(kijkVoor, File.ReadAllBytes(kijk));
            Assert.Equal(guardVoor, File.ReadAllBytes(voortgang));
        }

        var nieuweKern = _h.Dienst<CoreDatabase>().Db;
        Assert.Equal("bestaande taak", nieuweKern.Met(v => JlDatabase.Scalar(v, "SELECT payload FROM jobs WHERE id=7")));
        Assert.True(File.Exists(paden.KinderprofielenDb));
        Assert.Equal(kernversie, nieuweKern.Met(v => JlDatabase.Getal(v, "PRAGMA user_version")));
    }

    private static void Status(Antwoord antwoord, string verwacht, bool kind)
    {
        Assert.Equal(200, antwoord.Status);
        Assert.Empty(SchemaControle.Afwijkingen(OpenApiBouwer.Bouw(), "Kinderprofiel", antwoord.Json));
        Assert.Equal(verwacht, (string?)antwoord.Json!["status"]);
        Assert.Equal(kind, (bool?)antwoord.Json["is_kid"]);
    }

    private Task<Antwoord> Lees(User gebruiker) =>
        _h.Roep("privacy.kid.get", pad: new() { ["id"] = gebruiker.Id.ToString("N") });

    private Task<Antwoord> Bevestig(User gebruiker, bool kind, string etag, Guid? sleutel = null)
    {
        var body = new JsonObject { ["user_id"] = gebruiker.Id.ToString(), ["is_kid"] = kind };
        return _h.Roep("privacy.kid.confirm", body.ToJsonString(), ["Idempotency-Key: " + (sleutel ?? Guid.NewGuid()), "If-Match: " + etag]);
    }
}
