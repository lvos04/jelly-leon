using System;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests;

public class ForkInfoTests
{
    private static readonly DateTimeOffset Now = new(2026, 11, 9, 12, 0, 0, TimeSpan.Zero);

    private static ForkVersionInfo Build(string? server, string? product, string builtAgainst = "10.11.11")
        => ForkInfo.Build(server, product, builtAgainst, "10.11.11-jl.0", "v10.11.11", "1fbd873", "0.1.0.0", Now);

    [Fact]
    public void Build_SameVersionAndStockIdentity_IsCompatibel()
    {
        var info = Build("10.11.11", "Jellyfin Server");
        Assert.Equal("compatibel", info.Status);
        Assert.Equal("ok", info.ReasonCode);
        Assert.Equal("Jelly Leon", info.DisplayName);
        Assert.Equal("2026-11-09T12:00:00Z", info.ObservedAt);
    }

    [Fact]
    public void Build_FourPartServerVersion_IsTreatedAsEqual()
    {
        Assert.Equal("compatibel", Build("10.11.11.0", "Jellyfin Server").Status);
    }

    [Fact]
    public void Build_OtherServerVersion_IsAbiMismatch()
    {
        var info = Build("12.4.0", "Jellyfin Server");
        Assert.Equal("afwijkend", info.Status);
        Assert.Equal("plugin_abi_mismatch", info.ReasonCode);
        Assert.Contains("12.4.0", info.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Build_RenamedProduct_IsTechnicalIdentityChange()
    {
        var info = Build("10.11.11", "Jelly Leon Server");
        Assert.Equal("afwijkend", info.Status);
        Assert.Equal("technical_identity_changed", info.ReasonCode);
    }

    [Theory]
    [InlineData(null, "Jellyfin Server", "10.11.11")]
    [InlineData("10.11.11", "", "10.11.11")]
    [InlineData("10.11.11", "Jellyfin Server", "unknown")]
    public void Build_MissingData_IsUnknownNeverCompatibel(string? server, string? product, string builtAgainst)
    {
        var info = Build(server, product, builtAgainst);
        Assert.Equal("unknown", info.Status);
        Assert.Equal("version_unknown", info.ReasonCode);
    }

    [Fact]
    public void AssemblyMetadata_ComesFromBaselineJson()
    {
        Assert.Equal("10.11.11", ForkInfo.GetMetadata("JellyLeon.JellyfinVersion"));
        Assert.Matches(@"^10\.11\.11-jl\.\d+$", ForkInfo.GetMetadata("JellyLeon.ForkVersion"));
        Assert.Equal("v10.11.11", ForkInfo.GetMetadata("JellyLeon.UpstreamTag"));
        Assert.Matches("^[0-9a-f]{40}$", ForkInfo.GetMetadata("JellyLeon.UpstreamCommit"));
        Assert.Equal("unknown", ForkInfo.GetMetadata("JellyLeon.BestaatNiet"));
    }

    [Fact]
    public void Plugin_KeepsUpstreamCompatibleAssemblyName()
    {
        Assert.Equal("Jellyfin.Plugin.JellyLeon", typeof(Plugin).Assembly.GetName().Name);
    }
}
