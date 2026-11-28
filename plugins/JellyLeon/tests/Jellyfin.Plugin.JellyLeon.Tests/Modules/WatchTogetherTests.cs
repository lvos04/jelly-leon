using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Data.Events.Users;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Outbox;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Modules.WatchTogether;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Controller.Events;
using MediaBrowser.Controller.Session;
using MediaBrowser.Controller.SyncPlay;
using MediaBrowser.Controller.SyncPlay.Requests;
using MediaBrowser.Model.SyncPlay;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Modules;

public sealed class WatchTogetherTests : IDisposable
{
    private readonly Mock<ISyncPlayManager> _stock = new(MockBehavior.Strict);
    private readonly Mock<ISessionManager> _sessies = new();
    private readonly Dictionary<string, GroupInfoDto> _groepen = [];
    private readonly Harnas _h;
    private readonly SessionInfo _lid;
    private readonly SessionInfo _kijker;

    public WatchTogetherTests()
    {
        _lid = Sessie("Lid");
        _kijker = Sessie("Kijker");
        _sessies.SetupGet(s => s.Sessions).Returns([_lid, _kijker]);
        _stock.Setup(m => m.NewGroup(It.IsAny<SessionInfo>(), It.IsAny<NewGroupRequest>(), It.IsAny<CancellationToken>()))
            .Returns((SessionInfo s, NewGroupRequest r, CancellationToken _) =>
                _groepen[s.Id] = new GroupInfoDto(Guid.NewGuid(), r.GroupName, GroupStateType.Idle, [s.UserName], DateTime.UnixEpoch));
        _stock.Setup(m => m.GetGroup(It.IsAny<SessionInfo>(), It.IsAny<Guid>())).Returns((SessionInfo _, Guid id) =>
            _groepen.Values.FirstOrDefault(g => g.GroupId == id)!);
        _stock.Setup(m => m.ListGroups(It.IsAny<SessionInfo>(), It.IsAny<ListGroupsRequest>())).Returns(() => _groepen.Values.ToList());
        _stock.Setup(m => m.IsUserActive(It.IsAny<Guid>())).Returns((Guid id) => id == _lid.UserId && _groepen.ContainsKey(_lid.Id));
        _stock.Setup(m => m.LeaveGroup(It.IsAny<SessionInfo>(), It.IsAny<LeaveGroupRequest>(), It.IsAny<CancellationToken>()))
            .Callback((SessionInfo s, LeaveGroupRequest _, CancellationToken _) => _groepen.Remove(s.Id));
        _h = new Harnas(extraDiensten: services =>
        {
            services.AddSingleton(_sessies.Object);
            services.AddSingleton<ISyncPlayManager>(sp => new WatchDecorator(_stock.Object, _sessies.Object, sp.GetRequiredService<IModuleSwitches>(),
                sp.GetRequiredService<WatchTogetherModule>, sp.GetRequiredService<TimeProvider>(), NullLogger<WatchDecorator>.Instance));
        });
        _h.Schakelaars.Zet("watch", true);
    }

    public void Dispose() => _h.Dispose();
    private ISyncPlayManager Manager => _h.Dienst<ISyncPlayManager>();
    private WatchTogetherModule Module => _h.Dienst<WatchTogetherModule>();
    private IEnumerable<string?> Redenen => _h.Dienst<Outbox>().Lees(0, 200).Events
        .Where(e => (string?)e["event_type"] == "media.watchgroup.ended").Select(e => (string?)e["payload"]!["detected_by"]);

    private SessionInfo Sessie(string naam) => new(_sessies.Object, NullLogger.Instance) { Id = Guid.NewGuid().ToString("N"), UserId = Guid.NewGuid(), UserName = naam };
    private void MeldAan(SessionInfo s, bool beheer = false, bool recht = true) => _h.Sessies.Wie = new SessieIdentiteit(s.UserId, beheer, false, recht);
    private GroupInfoDto Nieuw() => Manager.NewGroup(_lid, new NewGroupRequest("Proefgroep"), CancellationToken.None);
    private Task<Antwoord> Diagnose(Guid id) => _h.Roep("watch.diagnostics", pad: new() { ["id"] = id.ToString() });

    [Fact]
    public async Task NietLidZietDezelfde404AlsBijEenOnbekendeGroep()
    {
        var groep = Nieuw();
        MeldAan(_kijker);
        var lijst = await _h.Roep("watch.groups");
        Assert.Equal(200, lijst.Status);
        Assert.False((bool)Assert.Single(lijst.Json!["items"]!.AsArray())!["is_member"]!);
        var bekend = await Diagnose(groep.GroupId);
        var onbekend = await Diagnose(Guid.NewGuid());
        Assert.Equal(404, bekend.Status);
        Assert.Equal(onbekend.Status, bekend.Status);
        foreach (var veld in new[] { "code", "message", "details" })
        {
            Assert.Equal(onbekend.Json![veld]!.ToJsonString(), bekend.Json![veld]!.ToJsonString());
        }

        MeldAan(_lid);
        Assert.Equal(200, (await Diagnose(groep.GroupId)).Status);
        MeldAan(_kijker, beheer: true);
        Assert.Equal(200, (await Diagnose(groep.GroupId)).Status);
        MeldAan(_kijker, recht: false);
        Assert.Equal(403, (await _h.Roep("watch.groups")).Status);
        Assert.Equal(403, (await _h.Roep("watch.purge")).Status);
    }

    [Fact]
    public void TweedeNewGroupSessieEindeEnHerstartRuimenElkeGroepOp()
    {
        var eerste = Nieuw();
        var tweede = Nieuw();
        Assert.Equal([tweede.GroupId], Module.Actief());
        Assert.Equal(["reconcile"], Redenen);
        _groepen.Remove(_lid.Id); // De interne LeaveGroup van upstream gaat buiten de decorator om.
        ((WatchDecorator)Manager).ControleerSessies(_lid);
        Assert.Empty(Module.Actief());
        var laatste = Nieuw();
        var herstart = new WatchTogetherModule(_h.Dienst<JlPaths>(), _h.Dienst<SecretStore>(), _h.Dienst<Outbox>(), _h.Schakelaars);
        herstart.Start(_h.Klok.Nu);
        herstart.Start(_h.Klok.Nu);
        Assert.Empty(herstart.Actief());
        Assert.Equal(["reconcile", "session_ended", "startup"], Redenen);
        Assert.NotEqual(eerste.GroupId, laatste.GroupId);
    }

    [Fact]
    public async Task VijftigGesimuleerdeGroepswisselsSessiesEnHerstartsHebbenGeenWeesmetadata()
    {
        var aangesloten = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        EventHandler<SessionEventArgs>? einde = null;
        _sessies.SetupAdd(s => s.SessionEnded += It.IsAny<EventHandler<SessionEventArgs>>())
            .Callback<EventHandler<SessionEventArgs>>(handler => { einde = handler; aangesloten.SetResult(); });
        var bewaking = _h.Dienst<WatchBewaking>();
        await bewaking.StartAsync(TestContext.Current.CancellationToken);
        try
        {
            await aangesloten.Task.WaitAsync(TimeSpan.FromSeconds(10), TestContext.Current.CancellationToken);
            for (var i = 0; i < 50; i++)
            {
                Nieuw();
                var tweede = Nieuw();
                Assert.Equal([tweede.GroupId], Module.Actief());
                _groepen.Remove(_lid.Id);
                einde!(_sessies.Object, new SessionEventArgs { SessionInfo = _lid });
                Assert.Empty(Module.Actief());
                Nieuw();
                _groepen.Clear();
                var herstart = new WatchTogetherModule(_h.Dienst<JlPaths>(), _h.Dienst<SecretStore>(), _h.Dienst<Outbox>(), _h.Schakelaars);
                herstart.Start(_h.Klok.Nu);
                Assert.Empty(herstart.Actief());
            }

            Assert.Equal(Enumerable.Range(0, 50).SelectMany(_ => new[] { "reconcile", "session_ended", "startup" }), Redenen);
        }
        finally
        {
            await bewaking.StopAsync(CancellationToken.None);
        }
    }

    [Fact]
    public void GeweigerdeJoinVerleentGeenLidmaatschapEnEenGemisteSessieWordtHersteld()
    {
        var groep = Nieuw();
        var join = new JoinGroupRequest(groep.GroupId);
        _stock.Setup(m => m.JoinGroup(_kijker, join, CancellationToken.None));
        Manager.JoinGroup(_kijker, join, CancellationToken.None);
        Assert.False(((WatchDecorator)Manager).IsLid(groep.GroupId, _kijker.UserId));
        Assert.Equal([groep.GroupId], Module.Actief());
        _groepen.Remove(_lid.Id);
        ((WatchDecorator)Manager).ControleerSessies(null);
        Assert.Empty(Module.Actief());
        Assert.Equal(["reconcile"], Redenen);
    }

    [Fact]
    public async Task ModuleUitGeeftUpstreamObjectenEnOpentGeenModuledatabase()
    {
        _h.Schakelaars.Zet("watch", false);
        var groep = Nieuw();
        Assert.Same(_groepen[_lid.Id], groep);
        Assert.Same(groep, Assert.Single(Manager.ListGroups(_lid, new ListGroupsRequest())));
        Assert.Same(groep, Manager.GetGroup(_lid, groep.GroupId));
        Assert.True(Manager.IsUserActive(_lid.UserId));
        var join = new JoinGroupRequest(groep.GroupId);
        var speel = Mock.Of<IGroupPlaybackRequest>();
        _stock.Setup(m => m.JoinGroup(_kijker, join, CancellationToken.None));
        _stock.Setup(m => m.HandleRequest(_lid, speel, CancellationToken.None));
        Manager.JoinGroup(_kijker, join, CancellationToken.None);
        Manager.HandleRequest(_lid, speel, CancellationToken.None);
        Manager.LeaveGroup(_lid, new LeaveGroupRequest(), CancellationToken.None);
        _stock.Verify(m => m.HandleRequest(_lid, speel, CancellationToken.None), Times.Once);
        Assert.Empty(_groepen);
        Assert.False(File.Exists(_h.Dienst<JlPaths>().ModuleDb(Module.Slug)));
        Assert.Equal(404, (await _h.Roep("watch.capabilities")).Status);
        _h.Sessies.Wie = null;
        Assert.Equal(401, (await _h.Roep("watch.capabilities")).Status);
    }

    [Theory]
    [InlineData(true, "down")]
    [InlineData(false, "degraded")]
    public async Task InactieveDecoratorGeeftWerkelijkeConnectorstatusEnEenEvent(bool gast, string status)
    {
        using var h = new Harnas(extraDiensten: diensten => diensten.AddSingleton(_stock.Object));
        h.Schakelaars.Zet("watch", true);
        if (gast)
        {
            h.Schakelaars.Gasten.Add(_kijker.UserId);
        }
        h.Gebruikers.Setup(g => g.GetUsers()).Returns([]);
        h.Koppel();
        var health = await h.RoepHub("connector.health", h.Hub.Token(h.Klok.Nu));
        var check = Assert.Single(health.Json!["checks"]!.AsArray(), c => (string?)c!["name"] == "watch_together")!;
        Assert.Equal(status, (string?)check["status"]);
        if (gast)
        {
            Assert.Equal("down", (string?)health.Json["status"]);
        }

        var cap = await h.Roep("watch.capabilities");
        Assert.False((bool)cap.Json!["decorator_active"]!);
        Assert.False((bool)cap.Json["features"]!["privacy"]!);
        Assert.Equal(status, (string?)cap.Json["health"]);
        Assert.Single(h.Dienst<Outbox>().Lees(0, 20).Events, e => (string?)e["event_type"] == "media.watchgroup.degraded");
    }

    [Fact]
    public async Task UserDeletedEnPurgeBewarenKijkgegevensEnMediaGuardVoortgang()
    {
        var bewakers = new[] { ("jellyfin.db", "CREATE TABLE UserData(Played INTEGER, Position INTEGER); INSERT INTO UserData VALUES(1,1900)"),
            ("mediaguard.db", "CREATE TABLE Jobs(Voortgang INTEGER); INSERT INTO Jobs VALUES(62)") };
        var paden = bewakers.Select(x => Path.Combine(_h.Map, x.Item1)).ToArray();
        for (var i = 0; i < paden.Length; i++)
        {
            using var db = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = paden[i], Pooling = false }.ToString());
            await db.OpenAsync(TestContext.Current.CancellationToken);
            JlDatabase.Voer(db, bewakers[i].Item2);
        }

        string[] Hashes() => paden.Select(p => Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(p)))).ToArray();
        var vooraf = Hashes();
        _h.Schakelaars.Gasten.Add(_lid.UserId);
        var groep = Nieuw();
        Assert.Equal(1, Module.TelGebruiker(_lid.UserId));
        await _h.Dienst<IEventConsumer<UserDeletedEventArgs>>().OnEvent(new UserDeletedEventArgs(new User("Lid", "proef", "proef") { Id = _lid.UserId }));
        Assert.Equal(0, Module.TelGebruiker(_lid.UserId));
        Assert.Empty(_h.Schakelaars.Gasten);
        Assert.False(Module.IsEigenaar(groep.GroupId, _lid.UserId));
        var bytes = await File.ReadAllBytesAsync(_h.Dienst<JlPaths>().ModuleDb(Module.Slug), TestContext.Current.CancellationToken);
        Assert.False(bytes.AsSpan().IndexOf(_lid.UserId.ToByteArray()) >= 0);
        foreach (var vorm in new[] { "N", "D" })
        {
            Assert.False(bytes.AsSpan().IndexOf(System.Text.Encoding.UTF8.GetBytes(_lid.UserId.ToString(vorm))) >= 0);
        }

        MeldAan(_kijker, beheer: true);
        const string body = """{"confirm":"WISSEN"}""";
        Assert.Equal(400, (await _h.Roep("watch.purge", body)).Status);
        var kop = new[] { "Idempotency-Key: " + Guid.NewGuid() };
        var wis = await _h.Roep("watch.purge", body, kop);
        Assert.Equal(202, wis.Status);
        Assert.Equal(1, (int)wis.Json!["deleted"]!["wt_group_meta"]!);
        Assert.Null(_h.Dienst<SecretStore>().Lees("wt-hmac.key"));
        var opnieuw = await _h.Roep("watch.purge", body, kop);
        Assert.Equal(wis.Json.ToJsonString(), opnieuw.Json!.ToJsonString());
        Assert.Equal("true", opnieuw.Kop["Idempotent-Replay"]);
        Assert.Equal(vooraf, Hashes());
    }
}
