using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>
/// Antwoord van een pluginroute: eigen JSON-serialisatie, los van de formatters van de host, zodat fork en stock
/// byte-gelijk antwoorden (ADR-0029).
/// </summary>
internal sealed class JlResult : IActionResult
{
    private static readonly JsonSerializerOptions _json = new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    public JlResult(int status, JsonNode? body)
    {
        Status = status;
        Body = body?.ToJsonString(_json);
    }

    public JlResult(int status, string? rawBody)
    {
        Status = status;
        Body = rawBody;
    }

    public int Status { get; }

    public string? Body { get; }

    public Dictionary<string, string> Headers { get; } = new(StringComparer.OrdinalIgnoreCase);

    public static JlResult Ok(JsonNode body, string? etag = null)
    {
        var result = new JlResult(200, body);
        if (etag is not null)
        {
            result.Headers["ETag"] = etag;
        }

        return result;
    }

    public static JlResult Fout(JlException fout, string traceId)
    {
        var body = new JsonObject
        {
            ["code"] = fout.Code,
            ["message"] = fout.Message,
            ["details"] = fout.Details.DeepClone(),
            ["trace_id"] = traceId,
        };
        var result = new JlResult(fout.Status, body);
        if (fout.RetryAfterSeconds is int seconden)
        {
            result.Headers["Retry-After"] = seconden.ToString(System.Globalization.CultureInfo.InvariantCulture);
        }

        return result;
    }

    public async Task ExecuteResultAsync(ActionContext context)
    {
        var response = context.HttpContext.Response;
        response.StatusCode = Status;
        foreach (var (naam, waarde) in Headers)
        {
            response.Headers[naam] = waarde;
        }

        response.Headers["Cache-Control"] = "no-store";
        if (Body is null)
        {
            return;
        }

        var bytes = Encoding.UTF8.GetBytes(Body);
        response.ContentType = "application/json; charset=utf-8";
        response.ContentLength = bytes.Length;
        await response.Body.WriteAsync(bytes).ConfigureAwait(false);
    }
}
