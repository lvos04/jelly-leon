using System;
using System.Text.Json.Nodes;

namespace Jellyfin.Plugin.JellyLeon.Core.Errors;

/// <summary>Fout uit de ene foutcatalogus (contract 1.3 §5): status, code, Nederlandse melding en details.</summary>
internal sealed class JlException : Exception
{
    public JlException(int status, string code, string message, JsonObject? details = null, int? retryAfterSeconds = null)
        : base(message)
    {
        Status = status;
        Code = code;
        Details = details ?? new JsonObject();
        RetryAfterSeconds = retryAfterSeconds;
    }

    public int Status { get; }

    public string Code { get; }

    public JsonObject Details { get; }

    public int? RetryAfterSeconds { get; }
}
