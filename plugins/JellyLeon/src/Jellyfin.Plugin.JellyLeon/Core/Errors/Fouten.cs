using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Jellyfin.Plugin.JellyLeon.Core.Errors;

/// <summary>
/// De ene foutcatalogus van de plugin (contract 1.3 §5, ADR-0030). Elke module gebruikt uitsluitend deze fabrieken,
/// zodat dezelfde situatie in elke module dezelfde status en code geeft.
/// </summary>
internal static class Fouten
{
    /// <summary>Bovengrens van een verzoekbody: 1 MiB, per route en na authenticatie (contract §2.3 regel 9).</summary>
    public const int MaxBodyBytes = 1048576;

    /// <summary>Alle codes die de plugin kan teruggeven, met hun vaste status (bron voor OpenAPI en contracttest).</summary>
    public static readonly IReadOnlyDictionary<string, int> Catalogus = new Dictionary<string, int>
    {
        ["idempotency_key_required"] = 400,
        ["idempotency_key_invalid"] = 400,
        ["unauthorized"] = 401,
        ["forbidden"] = 403,
        ["not_found"] = 404,
        ["idempotency_in_progress"] = 409,
        ["conflict"] = 409,
        ["precondition_failed"] = 412,
        ["payload_too_large"] = 413,
        ["validation_error"] = 422,
        ["idempotency_key_reused"] = 422,
        ["precondition_required"] = 428,
        ["rate_limited"] = 429,
        ["capability_unavailable"] = 501,
        ["storage_unavailable"] = 503,
        ["replay_check_unavailable"] = 503,
        ["dependency_unavailable"] = 503,
    };

    public static JlException NietGeauthenticeerd(string reason) =>
        new(401, "unauthorized", MeldingVoor(reason), new JsonObject { ["reason"] = reason });

    public static JlException Verboden(string reason) =>
        new(403, "forbidden", "Deze actie is voor dit account niet toegestaan.", new JsonObject { ["reason"] = reason });

    public static JlException NietGevonden() => new(404, "not_found", "Niet gevonden.");

    public static JlException SleutelVerplicht() =>
        new(400, "idempotency_key_required", "Deze wijziging vraagt de header Idempotency-Key (een UUID).");

    public static JlException SleutelOngeldig() =>
        new(400, "idempotency_key_invalid", "De header Idempotency-Key moet een UUID zijn.");

    public static JlException SleutelBezig() =>
        new(409, "idempotency_in_progress", "Een verzoek met deze Idempotency-Key wordt nog verwerkt.");

    public static JlException SleutelHergebruikt() =>
        new(422, "idempotency_key_reused", "Deze Idempotency-Key is al gebruikt voor een ander verzoek.");

    public static JlException Conflict(string reason) =>
        new(409, "conflict", "De wijziging botst met de huidige toestand.", new JsonObject { ["reason"] = reason });

    public static JlException PreconditieMislukt(string huidigeEtag) =>
        new(412, "precondition_failed", "Het object is intussen gewijzigd; haal het opnieuw op.", new JsonObject { ["huidige_etag"] = huidigeEtag });

    public static JlException PreconditieVerplicht() =>
        new(428, "precondition_required", "Deze wijziging vraagt de header If-Match met de ETag van het object.");

    public static JlException TeGroot() =>
        new(413, "payload_too_large", "Het verzoek is groter dan 1 MiB.", new JsonObject { ["max_bytes"] = MaxBodyBytes });

    public static JlException Validatie(params (string Veld, string Code, string Melding)[] fouten)
    {
        var lijst = new JsonArray();
        foreach (var (veld, code, melding) in fouten)
        {
            lijst.Add(new JsonObject { ["veld"] = veld, ["code"] = code, ["melding"] = melding });
        }

        return new JlException(422, "validation_error", "De invoer is ongeldig.", new JsonObject { ["fouten"] = lijst });
    }

    public static JlException NietBeschikbaar(string wat) =>
        new(501, "capability_unavailable", $"'{wat}' biedt Jelly Leon niet aan.", new JsonObject { ["capability"] = wat });

    public static JlException OpslagOnbeschikbaar() =>
        new(503, "storage_unavailable", "De eigen opslag van Jelly Leon is tijdelijk niet beschikbaar.", null, 30);

    public static JlException ReplayControleOnbeschikbaar() =>
        new(503, "replay_check_unavailable", "De herhaalcontrole van tokens is tijdelijk niet beschikbaar.", null, 30);

    public static JlException AfhankelijkheidOnbeschikbaar(string wat) =>
        new(503, "dependency_unavailable", $"'{wat}' is tijdelijk niet beschikbaar.", new JsonObject { ["dependency"] = wat }, 60);

    private static string MeldingVoor(string reason) => reason switch
    {
        "not_linked" => "Jelly Leon is nog niet aan de Hub gekoppeld.",
        "token_expired" => "Het token is verlopen.",
        "token_replayed" => "Dit token is al voor een wijziging gebruikt.",
        "unknown_key" => "Het token is ondertekend met een onbekende sleutel.",
        "service_token_not_accepted" => "Een service-token wordt hier niet aanvaard.",
        "token_use_invalid" => "Het soort token past niet bij dit verzoek.",
        "jti_missing" => "Het token mist een jti.",
        _ => "Aanmelden is vereist of het token is ongeldig.",
    };
}
