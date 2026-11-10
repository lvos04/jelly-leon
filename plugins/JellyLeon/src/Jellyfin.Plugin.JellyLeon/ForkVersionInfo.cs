using System.Text.Json.Serialization;

namespace Jellyfin.Plugin.JellyLeon;

/// <summary>
/// Antwoord van <c>GET /media/v1/version</c>: welke forkversie draait er en past de plugin bij de server.
/// Veldnamen in snake_case volgens het platformcontract (§5).
/// </summary>
public sealed record ForkVersionInfo
{
    /// <summary>Gets the schema version of this response.</summary>
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; init; } = "1.0";

    /// <summary>Gets the fork version (bv. 12.4.0-jl.1).</summary>
    [JsonPropertyName("fork_version")]
    public required string ForkVersion { get; init; }

    /// <summary>Gets the upstream tag of the fork baseline.</summary>
    [JsonPropertyName("upstream_tag")]
    public required string UpstreamTag { get; init; }

    /// <summary>Gets the upstream commit of the fork baseline.</summary>
    [JsonPropertyName("upstream_commit")]
    public required string UpstreamCommit { get; init; }

    /// <summary>Gets the Jellyfin version the plugin was compiled against.</summary>
    [JsonPropertyName("plugin_built_against")]
    public required string PluginBuiltAgainst { get; init; }

    /// <summary>Gets the plugin assembly version.</summary>
    [JsonPropertyName("plugin_version")]
    public required string PluginVersion { get; init; }

    /// <summary>Gets the version the running server reports to clients (technical identity).</summary>
    [JsonPropertyName("server_version")]
    public required string ServerVersion { get; init; }

    /// <summary>Gets the product name the running server reports to clients (technical identity).</summary>
    [JsonPropertyName("server_product_name")]
    public required string ServerProductName { get; init; }

    /// <summary>Gets the visible product name.</summary>
    [JsonPropertyName("display_name")]
    public string DisplayName { get; init; } = "Jelly Leon";

    /// <summary>Gets the compatibility status: <c>compatibel</c>, <c>afwijkend</c> or <c>unknown</c>.</summary>
    [JsonPropertyName("status")]
    public required string Status { get; init; }

    /// <summary>Gets a machine readable reason code (snake_case).</summary>
    [JsonPropertyName("reason_code")]
    public required string ReasonCode { get; init; }

    /// <summary>Gets a Dutch explanation for the UI.</summary>
    [JsonPropertyName("message")]
    public required string Message { get; init; }

    /// <summary>Gets the observation time (ISO-8601 UTC).</summary>
    [JsonPropertyName("observed_at")]
    public required string ObservedAt { get; init; }
}
