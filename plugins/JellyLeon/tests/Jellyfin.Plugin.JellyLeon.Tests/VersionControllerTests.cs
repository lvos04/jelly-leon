using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Jellyfin.Plugin.JellyLeon.Api;
using MediaBrowser.Controller;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests;

public class VersionControllerTests
{
    private sealed class FixedClock : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => new(2026, 11, 9, 8, 30, 0, TimeSpan.Zero);
    }

    [Fact]
    public void GetVersion_ReportsServerIdentityFromHost()
    {
        var host = new Mock<IServerApplicationHost>();
        host.SetupGet(h => h.ApplicationVersionString).Returns("12.4.0");
        host.SetupGet(h => h.Name).Returns("Jellyfin Server");
        var controller = new JellyLeonVersionController(host.Object, new FixedClock());

        var result = controller.GetVersion();

        var ok = Assert.IsType<OkObjectResult>(result.Result);
        var info = Assert.IsType<ForkVersionInfo>(ok.Value);
        Assert.Equal("compatibel", info.Status);
        Assert.Equal("12.4.0", info.ServerVersion);
        Assert.Equal("2026-11-09T08:30:00Z", info.ObservedAt);
    }

    [Fact]
    public void Controller_RequiresAuthentication()
    {
        var attributes = typeof(JellyLeonVersionController).GetCustomAttributes<AuthorizeAttribute>(true);
        Assert.NotEmpty(attributes);
        var anonymous = typeof(JellyLeonVersionController)
            .GetMethods()
            .Where(m => m.GetCustomAttributes<AllowAnonymousAttribute>(true).Any());
        Assert.Empty(anonymous);
    }

    [Fact]
    public void Routes_MatchPublishedOpenApi()
    {
        var prefix = typeof(JellyLeonVersionController).GetCustomAttribute<RouteAttribute>()!.Template;
        var routes = typeof(JellyLeonVersionController)
            .GetMethods()
            .SelectMany(m => m.GetCustomAttributes<HttpGetAttribute>())
            .Select(a => "/" + prefix + "/" + a.Template)
            .OrderBy(r => r, StringComparer.Ordinal)
            .ToArray();

        var specPath = Path.Combine(AppContext.BaseDirectory, "jelly-leon-plugin.openapi.json");
        using var doc = JsonDocument.Parse(File.ReadAllText(specPath));
        var documented = doc.RootElement.GetProperty("paths").EnumerateObject()
            .Where(p => p.Value.TryGetProperty("get", out _))
            .Select(p => p.Name)
            .OrderBy(r => r, StringComparer.Ordinal)
            .ToArray();

        Assert.Equal(documented, routes);
    }

    [Fact]
    public void Response_UsesSnakeCaseContractFields()
    {
        var info = ForkInfo.Build("12.4.0", "Jellyfin Server", "12.4.0", "12.4.0-jl.0", "v12.4", "abc", "0.1.0.0", DateTimeOffset.UnixEpoch);
        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(info));
        foreach (var name in new[] { "schema_version", "fork_version", "upstream_tag", "upstream_commit", "plugin_built_against", "server_version", "server_product_name", "status", "reason_code", "message", "observed_at" })
        {
            Assert.True(doc.RootElement.TryGetProperty(name, out _), name);
        }
    }
}
