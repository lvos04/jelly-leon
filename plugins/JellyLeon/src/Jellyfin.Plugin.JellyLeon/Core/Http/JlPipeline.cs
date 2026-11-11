using System;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Core.Idempotency;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using Microsoft.AspNetCore.Http;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>
/// De ene verzoekpipeline van de plugin, in de vaste volgorde van contract 1.3 §4.7 en §5 (ADR-0030):
/// authenticatie (koppelstatus → soort token → sleutel → claims → token_use → jti) → rol (403) → module aan (404) →
/// 1 MiB per route (413) → Idempotency-Key (400) → body (422) → If-Match (428) → idempotentielaag (409/422/herhaling).
/// Zonder geldige authenticatie is het antwoord altijd 401.
/// </summary>
internal sealed class JlPipeline
{
    private readonly HubPin _pin;
    private readonly JtiStore _jti;
    private readonly IdempotencyStore _idempotentie;
    private readonly ISessionAuthenticator _sessies;
    private readonly ModuleRegistry _modules;
    private readonly PrivacyService _privacy;
    private readonly TimeProvider _klok;

    public JlPipeline(HubPin pin, JtiStore jti, IdempotencyStore idempotentie, ISessionAuthenticator sessies, ModuleRegistry modules, PrivacyService privacy, TimeProvider klok)
    {
        _pin = pin;
        _jti = jti;
        _idempotentie = idempotentie;
        _sessies = sessies;
        _modules = modules;
        _privacy = privacy;
        _klok = klok;
    }

    public async Task<JlContext> BereidVoorAsync(HttpContext http, RouteSpec route, string traceId)
    {
        var verzoek = http.Request;
        var nu = _klok.GetUtcNow();
        var pad = verzoek.Path.Value ?? string.Empty;
        var sleutel = Kop(verzoek, "Idempotency-Key");

        JlPrincipal wie;
        if (route.Auth == JlAuth.Hub)
        {
            var hub = HubTokenValidator.Valideer(Kop(verzoek, "Authorization"), _pin.Huidig, nu);
            _jti.Controleer(hub, verzoek.Method, pad, sleutel, nu);
            if (hub.IsKind)
            {
                throw Fouten.Verboden("role_kind");
            }

            wie = new JlPrincipal(hub.Id, true, hub.IsService, hub.Rollen);
        }
        else
        {
            var sessie = await _sessies.AuthenticeerAsync(verzoek).ConfigureAwait(false);
            if (sessie.IsKid)
            {
                throw Fouten.Verboden("kid_profile");
            }

            if (!sessie.IsBeheerder)
            {
                throw Fouten.Verboden("admin_required");
            }

            var id = sessie.GebruikerId is Guid gebruiker ? "session:" + _privacy.Pseudoniem(gebruiker) : "session:api-key";
            wie = new JlPrincipal(id, false, false, ["admin"]);
        }

        if (route.Module is not null && !_modules.IsAan(route.Module))
        {
            throw Fouten.NietGevonden();
        }

        if (verzoek.ContentLength > Fouten.MaxBodyBytes)
        {
            throw Fouten.TeGroot();
        }

        var bytes = route.HeeftBody ? await LeesBodyAsync(verzoek.Body).ConfigureAwait(false) : [];

        if (route.Idempotentie == JlIdem.Verplicht)
        {
            if (sleutel is null)
            {
                throw Fouten.SleutelVerplicht();
            }

            if (sleutel.Length != 36 || !Guid.TryParseExact(sleutel, "D", out _))
            {
                throw Fouten.SleutelOngeldig();
            }
        }

        JsonObject? body = null;
        if (route.HeeftBody)
        {
            body = LeesJson(bytes);
        }

        var ifMatch = Kop(verzoek, "If-Match");
        if (route.IfMatch && ifMatch is null)
        {
            throw Fouten.PreconditieVerplicht();
        }

        string? scope = null;
        JlResult? herhaling = null;
        if (route.Idempotentie == JlIdem.Verplicht)
        {
            scope = wie.Id + "\n" + verzoek.Method + "\n" + pad;
            var hash = Convert.ToHexStringLower(SHA256.HashData([.. bytes, .. Encoding.UTF8.GetBytes("\n" + ifMatch)]));
            herhaling = _idempotentie.Begin(scope, sleutel!, hash, nu);
        }

        return new JlContext
        {
            TraceId = traceId,
            Wie = wie,
            Route = route,
            Body = body,
            IfMatch = ifMatch,
            IdemScope = scope,
            IdemSleutel = sleutel,
            Herhaling = herhaling,
        };
    }

    /// <summary>Legt het antwoord van een muterende route vast vóór het verzonden wordt; serverfouten geven de sleutel vrij.</summary>
    public void Rond(JlContext context, JlResult antwoord)
    {
        if (context.IdemScope is null || context.IdemSleutel is null || context.Herhaling is not null)
        {
            return;
        }

        if (antwoord.Status >= 500)
        {
            _idempotentie.Annuleer(context.IdemScope, context.IdemSleutel);
        }
        else
        {
            _idempotentie.Voltooi(context.IdemScope, context.IdemSleutel, antwoord);
        }
    }

    private static string? Kop(HttpRequest verzoek, string naam)
    {
        var waarde = verzoek.Headers[naam].ToString();
        return string.IsNullOrWhiteSpace(waarde) ? null : waarde.Trim();
    }

    private static async Task<byte[]> LeesBodyAsync(Stream stroom)
    {
        using var buffer = new MemoryStream();
        var blok = new byte[16384];
        int gelezen;
        while ((gelezen = await stroom.ReadAsync(blok).ConfigureAwait(false)) > 0)
        {
            if (buffer.Length + gelezen > Fouten.MaxBodyBytes)
            {
                throw Fouten.TeGroot();
            }

            await buffer.WriteAsync(blok.AsMemory(0, gelezen)).ConfigureAwait(false);
        }

        return buffer.ToArray();
    }

    private static JsonObject LeesJson(byte[] bytes)
    {
        try
        {
            if (JsonNode.Parse(bytes, null, new JsonDocumentOptions { MaxDepth = 16 }) is JsonObject o)
            {
                return o;
            }
        }
        catch (JsonException)
        {
            // Valt door naar de validatiefout hieronder.
        }

        throw Fouten.Validatie(("$", "json_ongeldig", "De body moet één JSON-object zijn."));
    }
}
