using System;
using System.IO;
using System.Reflection;
using System.Threading;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Modules.WatchTogether;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Controller;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Session;
using MediaBrowser.Controller.SyncPlay;
using MediaBrowser.Controller.SyncPlay.Requests;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Modules;

public sealed class WatchSamenstellingProef
{
    [Fact]
    public void DeEchteManagerBlijftEenSingletonEnEindigtDeVorigeGroep()
    {
        using var h = new Harnas();
        h.Schakelaars.Zet("watch", true);
        var diensten = new ServiceCollection();
        diensten.AddLogging();
        var gebruikers = new Mock<IUserManager>();
        var sessies = new Mock<ISessionManager>();
        var testgebruiker = new User("proef", "proef", "proef");
        var sessie = new SessionInfo(sessies.Object, NullLogger.Instance) { Id = Guid.NewGuid().ToString("N"), UserId = testgebruiker.Id, UserName = testgebruiker.Username };
        gebruikers.Setup(g => g.GetUserById(testgebruiker.Id)).Returns(testgebruiker);
        sessies.SetupGet(s => s.Sessions).Returns([sessie]);
        diensten.AddSingleton(gebruikers.Object);
        diensten.AddSingleton(sessies.Object);
        diensten.AddSingleton(Mock.Of<ILibraryManager>());
        var assembly = Assembly.LoadFrom(Path.Combine(AppContext.BaseDirectory, "Emby.Server.Implementations.dll"));
        var type = assembly.GetType("Emby.Server.Implementations.SyncPlay.SyncPlayManager", true)!;
        diensten.AddSingleton(typeof(ISyncPlayManager), type);
        new PluginServiceRegistrator().RegisterServices(diensten, Mock.Of<IServerApplicationHost>());
        diensten.AddSingleton<IModuleSwitches>(h.Schakelaars);
        var module = h.Dienst<WatchTogetherModule>();
        diensten.AddSingleton(module);
        using var provider = diensten.BuildServiceProvider();
        var manager = provider.GetRequiredService<ISyncPlayManager>();
        Assert.IsType<WatchDecorator>(manager);
        var upstream = provider.GetRequiredKeyedService<ISyncPlayManager>(typeof(WatchDecorator));
        Assert.Equal(type, upstream.GetType());
        Assert.Same(upstream, provider.GetRequiredKeyedService<ISyncPlayManager>(typeof(WatchDecorator)));
        var eerst = manager.NewGroup(sessie, new NewGroupRequest("Eerste"), CancellationToken.None);
        var tweede = manager.NewGroup(sessie, new NewGroupRequest("Tweede"), CancellationToken.None);
        Assert.Null(upstream.GetGroup(sessie, eerst.GroupId));
        Assert.Equal(tweede.GroupId, Assert.Single(manager.ListGroups(sessie, new ListGroupsRequest())).GroupId);
        Assert.Equal([tweede.GroupId], module.Actief());
        manager.LeaveGroup(sessie, new LeaveGroupRequest(), CancellationToken.None);
        Assert.Empty(module.Actief());
        Assert.False(manager.IsUserActive(testgebruiker.Id));
    }
}
