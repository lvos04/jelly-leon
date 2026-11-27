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
using Microsoft.Extensions.DependencyInjection;

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
    private readonly IServiceProvider _diensten;
    private readonly TimeProvider _klok;

    public JlPipeline(HubPin pin, IServiceProvider diensten, TimeProvider klok)
    {
        _pin = pin;
        _diensten = diensten;
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
            // Alleen een route met antwoordopslag kan een exacte herhaling afhandelen.
            // Open opslagdiensten pas na de pin- en tokencontrole, ook bij een opslagfout na de start.
            _diensten.GetRequiredService<JtiStore>().Controleer(hub, verzoek.Method, pad, route.Idempotentie == JlIdem.Verplicht ? sleutel : null, nu);
            if (hub.IsKind)
            {
                throw Fouten.Verboden("role_kind");
            }

            wie = new JlPrincipal(hub.Id, true, hub.IsService, hub.Rollen);
        }
        else
        {
            var sessie = await _diensten.GetRequiredService<ISessionAuthenticator>().AuthenticeerAsync(verzoek).ConfigureAwait(false);
            sessie.EisBeheerder(route.Auth);

            var id = sessie.GebruikerId is Guid gebruiker ? "session:" + _diensten.GetRequiredService<PrivacyService>().Pseudoniem(gebruiker) : "session:api-key";
            wie = new JlPrincipal(id, false, false, ["admin"]);
        }

        if (route.Module is not null && !_diensten.GetRequiredService<ModuleRegistry>().IsAan(route.Module))
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
            herhaling = _diensten.GetRequiredService<IdempotencyStore>().Begin(scope, sleutel!, hash, nu);
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

        var idempotentie = _diensten.GetRequiredService<IdempotencyStore>();
        if (antwoord.Status >= 500)
        {
            idempotentie.Annuleer(context.IdemScope, context.IdemSleutel);
        }
        else
        {
            idempotentie.Voltooi(context.IdemScope, context.IdemSleutel, antwoord);
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
            if (JsonNode.Parse(bytes, null, new JsonDocumentOptions { MaxDepth = 16, AllowDuplicateProperties = false }) is JsonObject o)
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
