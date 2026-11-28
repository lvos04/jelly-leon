using System;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
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
        SessieIdentiteit? sessie = null;
        var alleenHerhalen = false;
        if (route.Auth == JlAuth.Hub)
        {
            var hub = HubTokenValidator.Valideer(Kop(verzoek, "Authorization"), _pin.Huidig, nu);
            // Alleen een route met antwoordopslag kan een exacte herhaling afhandelen.
            // Open opslagdiensten pas na de pin- en tokencontrole, ook bij een opslagfout na de start.
            alleenHerhalen = ControleerJti(hub, verzoek.Method, pad, route.Idempotentie == JlIdem.Verplicht ? sleutel : null, nu);
            if (hub.IsKind)
            {
                throw Fouten.Verboden("role_kind");
            }

            wie = new JlPrincipal(hub.Id, true, hub.IsService, hub.Rollen);
        }
        else
        {
            sessie = await _diensten.GetRequiredService<ISessionAuthenticator>().AuthenticeerAsync(verzoek).ConfigureAwait(false);
            sessie.EisToegang(route.Auth);

            var id = sessie.GebruikerId is Guid gebruiker ? "session:" + _diensten.GetRequiredService<PrivacyService>().Pseudoniem(gebruiker) : "session:api-key";
            wie = new JlPrincipal(id, false, false, sessie.IsBeheerder && !sessie.IsKid ? ["admin"] : ["user"]);
        }

        if (route.Module is not null && !_diensten.GetRequiredService<ModuleRegistry>().IsAan(route.Module))
        {
            throw Fouten.NietGevonden();
        }

        if (verzoek.ContentLength > Fouten.MaxBodyBytes)
        {
            throw Fouten.TeGroot();
        }

        // Ook bij GET en bij acties zonder JSON-model telt de grens voor een body zonder opgegeven lengte.
        var bewaar = route.HeeftBody || route.Idempotentie == JlIdem.Verplicht;
        var bytes = verzoek.ContentLength == 0 || (!bewaar && verzoek.ContentLength.HasValue)
            ? []
            : await LeesBodyAsync(verzoek.Body, bewaar, http.RequestAborted).ConfigureAwait(false);

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

        IdempotencyStore? moduleopslag = null;
        string? scope = null;
        JlResult? herhaling = null;
        if (route.Idempotentie == JlIdem.Verplicht)
        {
            scope = wie.Id + "\n" + verzoek.Method + "\n" + pad;
            var voorwaarden = "\n" + ifMatch;
            if (route.WisModule is string slug)
            {
                var module = _diensten.GetRequiredService<ModuleRegistry>().Zoek(slug) as ModuleBasis ?? throw Fouten.NietGevonden();
                var beheer = module.Gegevensbeheer;
                moduleopslag = beheer.Herhalingen;
                sleutel = beheer.VerzoekSleutel(scope, sleutel!);
                scope = slug;
                // Een voorbeeld en de uitvoering met dezelfde body zijn verschillende verzoeken.
                voorwaarden += "\n" + verzoek.QueryString.Value;
            }

            var opslag = moduleopslag ?? _diensten.GetRequiredService<IdempotencyStore>();
            var hash = Convert.ToHexStringLower(SHA256.HashData([.. bytes, .. Encoding.UTF8.GetBytes(voorwaarden)]));
            herhaling = opslag.Begin(scope, sleutel!, hash, nu, alleenHerhalen);
        }

        return new JlContext
        {
            TraceId = traceId,
            Wie = wie,
            Sessie = sessie,
            Route = route,
            Body = body,
            IfMatch = ifMatch,
            ModuleIdempotentie = moduleopslag,
            IdemScope = scope,
            IdemSleutel = sleutel,
            Herhaling = herhaling,
        };
    }

    private bool ControleerJti(HubPrincipal hub, string methode, string pad, string? sleutel, DateTimeOffset nu)
    {
        try
        {
            return _diensten.GetRequiredService<JtiStore>().Controleer(hub, methode, pad, sleutel, nu);
        }
        catch (Exception fout) when (fout is IOException or UnauthorizedAccessException or JlException { Code: "storage_unavailable" })
        {
            // Ook het openen van de database bij het aanmaken van de dienst kan worden geweigerd.
            throw Fouten.ReplayControleOnbeschikbaar();
        }
    }

    /// <summary>Legt het antwoord van een muterende route vast vóór het verzonden wordt; serverfouten geven de sleutel vrij.</summary>
    public void Rond(JlContext context, JlResult antwoord)
    {
        if (context.IdemScope is null || context.IdemSleutel is null || context.Herhaling is not null)
        {
            return;
        }

        var opslag = context.ModuleIdempotentie ?? _diensten.GetRequiredService<IdempotencyStore>();
        if (antwoord.Status >= 500)
        {
            opslag.Annuleer(context.IdemScope, context.IdemSleutel);
        }
        else
        {
            opslag.Voltooi(context.IdemScope, context.IdemSleutel, antwoord);
        }
    }

    private static string? Kop(HttpRequest verzoek, string naam)
    {
        var waarde = verzoek.Headers[naam].ToString();
        return string.IsNullOrWhiteSpace(waarde) ? null : waarde.Trim();
    }

    private static async Task<byte[]> LeesBodyAsync(Stream stroom, bool bewaar, CancellationToken stop)
    {
        if (stroom == Stream.Null)
        {
            return [];
        }

        using var buffer = bewaar ? new MemoryStream() : null;
        var blok = new byte[16384];
        var totaal = 0;
        try
        {
            while (totaal <= Fouten.MaxBodyBytes)
            {
                var ruimte = Math.Min(blok.Length, Fouten.MaxBodyBytes + 1 - totaal);
                var gelezen = await stroom.ReadAsync(blok.AsMemory(0, ruimte), stop).ConfigureAwait(false);
                if (gelezen == 0)
                {
                    return buffer?.ToArray() ?? [];
                }

                totaal += gelezen;
                if (buffer is not null && totaal <= Fouten.MaxBodyBytes)
                {
                    await buffer.WriteAsync(blok.AsMemory(0, gelezen), stop).ConfigureAwait(false);
                }
            }
        }
        catch (BadHttpRequestException fout) when (fout.StatusCode == StatusCodes.Status413PayloadTooLarge)
        {
            // De host kan de routegrens al tijdens het lezen van een chunk afdwingen.
            throw Fouten.TeGroot();
        }

        throw Fouten.TeGroot();
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
