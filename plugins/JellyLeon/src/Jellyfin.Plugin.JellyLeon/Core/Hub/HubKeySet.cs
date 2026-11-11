using System;
using System.Buffers.Text;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;

namespace Jellyfin.Plugin.JellyLeon.Core.Hub;

/// <summary>Eén gepinde Ed25519-sleutel van de Hub.</summary>
internal sealed record HubKey(string Kid, string X)
{
    public byte[] Bytes => Base64Url.DecodeFromChars(X);

    /// <summary>JWK-thumbprint volgens RFC 7638 (contract §4.5).</summary>
    public string Thumbprint =>
        Base64Url.EncodeToString(SHA256.HashData(Encoding.UTF8.GetBytes("{\"crv\":\"Ed25519\",\"kty\":\"OKP\",\"x\":\"" + X + "\"}")));
}

/// <summary>
/// De gepinde sleutelset van de Hub (contract 1.3 §4.5): JWT-sleutels en policy-sleutels, met de vingerafdruk die de
/// beheerder bij het pinnen overtikt. De plugin heeft geen hub-link-route; rotatie is opnieuw pinnen.
/// </summary>
internal sealed class HubKeySet
{
    private const string Alfabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

    public HubKeySet(IReadOnlyList<HubKey> jwtSleutels, IReadOnlyList<HubKey> policySleutels)
    {
        JwtSleutels = jwtSleutels;
        PolicySleutels = policySleutels;
        Vingerafdruk = BerekenVingerafdruk(jwtSleutels.Select(k => k.Thumbprint), policySleutels.Select(k => k.Thumbprint));
    }

    public IReadOnlyList<HubKey> JwtSleutels { get; }

    public IReadOnlyList<HubKey> PolicySleutels { get; }

    public string Vingerafdruk { get; }

    public static string BerekenVingerafdruk(IEnumerable<string> jwtThumbprints, IEnumerable<string> policyThumbprints)
    {
        var tekst = "jl-hub-keyset-v1\njwt:" + string.Join(',', jwtThumbprints.Order(StringComparer.Ordinal))
            + "\npolicy:" + string.Join(',', policyThumbprints.Order(StringComparer.Ordinal));
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(tekst));
        var tekens = new StringBuilder(19);
        for (var i = 0; i < 16; i++)
        {
            // 16 tekens × 5 bits = de eerste 80 bits van de hash.
            var bit = i * 5;
            var waarde = ((hash[bit / 8] << 8) | hash[(bit / 8) + 1]) >> (11 - (bit % 8)) & 0x1F;
            if (i > 0 && i % 4 == 0)
            {
                tekens.Append('-');
            }

            tekens.Append(Alfabet[waarde]);
        }

        return tekens.ToString();
    }

    /// <summary>Genormaliseerde vorm voor vergelijken: hoofdletters, alleen letters en cijfers, O→0, I/L→1.</summary>
    public static string Normaliseer(string invoer)
    {
        var tekens = new StringBuilder(16);
        foreach (var teken in invoer.ToUpperInvariant())
        {
            if (char.IsAsciiLetterOrDigit(teken))
            {
                tekens.Append(teken switch { 'O' => '0', 'I' or 'L' => '1', _ => teken });
            }
        }

        return tekens.ToString();
    }

    public bool VingerafdrukKlopt(string getypt) =>
        CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(Normaliseer(getypt)), Encoding.ASCII.GetBytes(Normaliseer(Vingerafdruk)));

    public HubKey? Zoek(string kid) => JwtSleutels.FirstOrDefault(k => string.Equals(k.Kid, kid, StringComparison.Ordinal));

    /// <summary>
    /// Leest het antwoord van <c>GET /api/v1/auth/keyset</c> van de Hub: <c>jwks.keys[]</c> en
    /// <c>policy_public_key</c> (of <c>policy_public_keys[]</c>). Onbekende of ongeldige sleutels geven 422.
    /// </summary>
    public static HubKeySet Parse(JsonNode? keyset, string veld)
    {
        if (keyset is not JsonObject wortel)
        {
            throw Fouten.Validatie((veld, "type", "Verwacht een object met jwks en policy_public_key."));
        }

        var jwt = new List<HubKey>();
        if (wortel["jwks"] is JsonObject jwks && jwks["keys"] is JsonArray sleutels)
        {
            jwt.AddRange(sleutels.Select((s, i) => LeesSleutel(s, $"{veld}.jwks.keys[{i}]")));
        }

        var policy = new List<HubKey>();
        if (wortel["policy_public_key"] is JsonObject enkele)
        {
            policy.Add(LeesSleutel(enkele, veld + ".policy_public_key"));
        }

        if (wortel["policy_public_keys"] is JsonArray meerdere)
        {
            policy.AddRange(meerdere.Select((s, i) => LeesSleutel(s, $"{veld}.policy_public_keys[{i}]")));
        }

        if (jwt.Count is 0 or > 8 || policy.Count is 0 or > 8)
        {
            throw Fouten.Validatie((veld, "sleutelset_onvolledig", "De sleutelset vraagt 1 tot 8 JWT-sleutels en 1 tot 8 policy-sleutels."));
        }

        if (jwt.Select(k => k.Kid).Distinct(StringComparer.Ordinal).Count() != jwt.Count)
        {
            throw Fouten.Validatie((veld + ".jwks.keys", "kid_dubbel", "Elke kid mag één keer voorkomen."));
        }

        return new HubKeySet(jwt, policy);
    }

    public JsonObject NaarJson() => new()
    {
        ["jwks"] = new JsonObject { ["keys"] = new JsonArray(JwtSleutels.Select(SleutelJson).ToArray()) },
        ["policy_public_keys"] = new JsonArray(PolicySleutels.Select(SleutelJson).ToArray()),
    };

    private static JsonNode SleutelJson(HubKey sleutel) =>
        new JsonObject { ["kty"] = "OKP", ["crv"] = "Ed25519", ["x"] = sleutel.X, ["kid"] = sleutel.Kid };

    private static HubKey LeesSleutel(JsonNode? node, string veld)
    {
        if (node is not JsonObject o
            || Tekst(o, "kty") != "OKP" || Tekst(o, "crv") != "Ed25519"
            || Tekst(o, "x") is not { Length: 43 } x || !Base64Url.IsValid(x)
            || Tekst(o, "kid") is not { Length: > 0 and <= 128 } kid)
        {
            throw Fouten.Validatie((veld, "sleutel_ongeldig", "Verwacht een Ed25519-JWK met kty OKP, crv Ed25519, x (32 bytes) en kid."));
        }

        return new HubKey(kid, x);
    }

    private static string? Tekst(JsonObject o, string naam) =>
        o[naam] is JsonValue v && v.TryGetValue<string>(out var tekst) ? tekst : null;
}
