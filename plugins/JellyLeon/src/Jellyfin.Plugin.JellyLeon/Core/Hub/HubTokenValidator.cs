using System;
using System.Buffers.Text;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using Jellyfin.Plugin.JellyLeon.Core.Errors;

namespace Jellyfin.Plugin.JellyLeon.Core.Hub;

/// <summary>
/// Controleert een Hub-token in de vaste volgorde van contract 1.3 §4.7: koppelstatus → soort token → kid en
/// handtekening → claims → token_use → jti. De herhaalcontrole zelf doet <see cref="JtiStore"/>.
/// </summary>
internal static class HubTokenValidator
{
    public const string Audience = "jelly-leon";
    private const int Speling = 30;
    private const int MaxLevensduur = 120;
    private static readonly string[] _gebruikersrollen = ["admin", "operator", "viewer", "kind"];

    public static HubPrincipal Valideer(string? authorization, HubPinState? pin, DateTimeOffset nu)
    {
        if (pin is null)
        {
            throw Fouten.NietGeauthenticeerd("not_linked");
        }

        if (authorization is null || !authorization.StartsWith("Bearer ", StringComparison.Ordinal) || authorization.Length <= 7)
        {
            throw Fouten.NietGeauthenticeerd("invalid_token");
        }

        var token = authorization[7..].Trim();
        if (token.StartsWith("svc_", StringComparison.Ordinal))
        {
            throw Fouten.NietGeauthenticeerd("service_token_not_accepted");
        }

        try
        {
            return ValideerJwt(token, pin, nu);
        }
        catch (InvalidOperationException)
        {
            // System.Text.Json decodeert tekst pas bij het uitlezen van een veld.
            throw Fouten.NietGeauthenticeerd("invalid_token");
        }
    }

    private static HubPrincipal ValideerJwt(string token, HubPinState pin, DateTimeOffset nu)
    {
        var delen = token.Split('.', 3);
        if (delen.Length != 3 || !Json(delen[0], out var kop) || !Json(delen[1], out var claims)
            || delen[2].Length != 86 || !IsBase64Url(delen[2]) || kop.ValueKind != JsonValueKind.Object || claims.ValueKind != JsonValueKind.Object)
        {
            throw Fouten.NietGeauthenticeerd("invalid_token");
        }

        if (Tekst(kop, "alg") != "EdDSA" || Tekst(kop, "typ") != "JWT")
        {
            throw Fouten.NietGeauthenticeerd("invalid_token");
        }

        var sleutel = Tekst(kop, "kid") is { } kid ? pin.Sleutels.Zoek(kid) : null;
        if (sleutel is null)
        {
            throw Fouten.NietGeauthenticeerd("unknown_key");
        }

        var handtekening = Base64Url.DecodeFromChars(delen[2]);
        if (!Ed25519.Verifieer(sleutel.Bytes, Encoding.ASCII.GetBytes(delen[0] + "." + delen[1]), handtekening))
        {
            throw Fouten.NietGeauthenticeerd("invalid_token");
        }

        var seconden = nu.ToUnixTimeSeconds();
        if (Tekst(claims, "iss") != "hub" || Tekst(claims, "aud") != Audience
            || !Getal(claims, "iat", out var iat) || !Getal(claims, "nbf", out var nbf) || !Getal(claims, "exp", out var exp)
            || iat > seconden + Speling || exp < iat || exp > iat + MaxLevensduur || nbf > seconden + Speling || nbf > exp)
        {
            throw Fouten.NietGeauthenticeerd("invalid_token");
        }

        if (exp < seconden - Speling)
        {
            throw Fouten.NietGeauthenticeerd("token_expired");
        }

        var rollen = Rollen(claims);
        var sub = Tekst(claims, "sub");
        var gebruik = Tekst(claims, "token_use");
        bool dienst;
        if (gebruik == "user")
        {
            dienst = false;
            if (rollen is null || rollen.Count == 0 || rollen.Any(r => !_gebruikersrollen.Contains(r)) || !Guid.TryParse(sub, out _))
            {
                throw Fouten.NietGeauthenticeerd("token_use_invalid");
            }
        }
        else if (gebruik == "hub_service")
        {
            dienst = true;
            if (sub != "hub" || rollen is not ["service"] || !string.Equals(Tekst(claims, "service_id"), pin.ServiceId, StringComparison.OrdinalIgnoreCase))
            {
                throw Fouten.NietGeauthenticeerd("token_use_invalid");
            }
        }
        else
        {
            throw Fouten.NietGeauthenticeerd("token_use_invalid");
        }

        var jti = Tekst(claims, "jti");
        if (string.IsNullOrEmpty(jti))
        {
            throw Fouten.NietGeauthenticeerd("jti_missing");
        }

        if (jti.Length != 36 || !Guid.TryParseExact(jti, "D", out var uuid) || uuid.Version != 4
            || char.ToLowerInvariant(jti[19]) is not ('8' or '9' or 'a' or 'b'))
        {
            throw Fouten.NietGeauthenticeerd("invalid_token");
        }

        return new HubPrincipal(sub!, dienst, rollen!, jti, exp);
    }

    private static bool Json(string deel, out JsonElement element)
    {
        element = default;
        if (deel.Length == 0 || deel.Length > 8192 || !IsBase64Url(deel))
        {
            return false;
        }

        try
        {
            using var document = JsonDocument.Parse(Base64Url.DecodeFromChars(deel), new JsonDocumentOptions { AllowDuplicateProperties = false });
            element = document.RootElement.Clone();
            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static bool IsBase64Url(string deel) =>
        deel.All(c => char.IsAsciiLetterOrDigit(c) || c is '-' or '_') && Base64Url.IsValid(deel);

    private static string? Tekst(JsonElement o, string naam) =>
        o.TryGetProperty(naam, out var waarde) && waarde.ValueKind == JsonValueKind.String ? waarde.GetString() : null;

    private static bool Getal(JsonElement o, string naam, out long getal)
    {
        getal = 0;
        return o.TryGetProperty(naam, out var waarde) && waarde.ValueKind == JsonValueKind.Number && waarde.TryGetInt64(out getal);
    }

    private static List<string>? Rollen(JsonElement claims)
    {
        if (!claims.TryGetProperty("roles", out var rollen) || rollen.ValueKind != JsonValueKind.Array)
        {
            return null;
        }

        var lijst = new List<string>();
        foreach (var rol in rollen.EnumerateArray())
        {
            if (rol.ValueKind != JsonValueKind.String)
            {
                return null;
            }

            lijst.Add(rol.GetString()!);
        }

        return lijst;
    }
}
