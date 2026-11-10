using System;
using System.IO;
using System.Text.Json;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests;

public class ForkInfoTests
{
    private static readonly DateTimeOffset Now = new(2026, 11, 9, 12, 0, 0, TimeSpan.Zero);

    private static ForkVersionInfo Build(string? server, string? product, string builtAgainst = "12.4.0")
        => ForkInfo.Build(server, product, builtAgainst, "12.4.0-jl.0", "v12.4", "83d0d0e", "0.1.0.0", Now);

    [Fact]
    public void Build_SameVersionAndStockIdentity_IsCompatibel()
    {
        var info = Build("12.4.0", "Jellyfin Server");
        Assert.Equal("compatibel", info.Status);
        Assert.Equal("ok", info.ReasonCode);
        Assert.Equal("Jelly Leon", info.DisplayName);
        Assert.Equal("2026-11-09T12:00:00Z", info.ObservedAt);
    }

    [Fact]
    public void Build_FourPartServerVersion_IsTreatedAsEqual()
    {
        Assert.Equal("compatibel", Build("12.4.0.0", "Jellyfin Server").Status);
    }

    [Fact]
    public void Build_OtherServerVersion_IsAbiMismatch()
    {
        var info = Build("12.5.0", "Jellyfin Server");
        Assert.Equal("afwijkend", info.Status);
        Assert.Equal("plugin_abi_mismatch", info.ReasonCode);
        Assert.Contains("12.5.0", info.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Build_RenamedProduct_IsTechnicalIdentityChange()
    {
        var info = Build("12.4.0", "Jelly Leon Server");
        Assert.Equal("afwijkend", info.Status);
        Assert.Equal("technical_identity_changed", info.ReasonCode);
    }

    [Theory]
    [InlineData(null, "Jellyfin Server", "12.4.0")]
    [InlineData("12.4.0", "", "12.4.0")]
    [InlineData("12.4.0", "Jellyfin Server", "unknown")]
    public void Build_MissingData_IsUnknownNeverCompatibel(string? server, string? product, string builtAgainst)
    {
        var info = Build(server, product, builtAgainst);
        Assert.Equal("unknown", info.Status);
        Assert.Equal("version_unknown", info.ReasonCode);
    }

    [Fact]
    public void AssemblyMetadata_ComesFromBaselineJson()
    {
        // Vergelijkt met tools/jelly-leon/baseline.json (meegekopieerd), zodat een upstream-sync geen testwijziging vraagt.
        using var baseline = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "baseline.json")));
        var root = baseline.RootElement;
        Assert.Equal(root.GetProperty("upstream_version").GetString(), ForkInfo.GetMetadata("JellyLeon.JellyfinVersion"));
        Assert.Equal(root.GetProperty("fork_version").GetString(), ForkInfo.GetMetadata("JellyLeon.ForkVersion"));
        Assert.Matches(@"^\d+\.\d+\.\d+-jl\.\d+$", ForkInfo.GetMetadata("JellyLeon.ForkVersion"));
        Assert.Equal(root.GetProperty("upstream_tag").GetString(), ForkInfo.GetMetadata("JellyLeon.UpstreamTag"));
        Assert.Equal(root.GetProperty("upstream_commit").GetString(), ForkInfo.GetMetadata("JellyLeon.UpstreamCommit"));
        Assert.Matches("^[0-9a-f]{40}$", ForkInfo.GetMetadata("JellyLeon.UpstreamCommit"));
        Assert.Equal("unknown", ForkInfo.GetMetadata("JellyLeon.BestaatNiet"));
    }

    [Fact]
    public void Plugin_KeepsUpstreamCompatibleAssemblyName()
    {
        Assert.Equal("Jellyfin.Plugin.JellyLeon", typeof(Plugin).Assembly.GetName().Name);
    }
}
