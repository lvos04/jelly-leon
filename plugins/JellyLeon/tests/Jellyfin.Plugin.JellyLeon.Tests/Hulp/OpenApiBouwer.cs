using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;

namespace Jellyfin.Plugin.JellyLeon.Tests.Hulp;

/// <summary>
/// Bouwt docs/openapi/jelly-leon-plugin.openapi.json uit de routetabel en de schema's hieronder (contract §5). De
/// drifttest vergelijkt het resultaat met het bestand in de repo; de schematest houdt echte antwoorden ertegen.
/// </summary>
internal static partial class OpenApiBouwer
{
    private const string Vast = """
    {
      "openapi": "3.0.3",
      "info": {
        "title": "Jelly Leon-plugin (Jellyfin.Plugin.JellyLeon)",
        "version": "0.2.0",
        "description": "Fork-eigen routes van de ene Jelly Leon-plugin (ADR-0016). Draait binnen de Jellyfin-server (zelfde poort). /connector/v1/** is alleen voor de Hub (gepinde sleutelset, contract 1.3 §4 en §6); /media/v1/** gebruikt de gewone serveraanmelding. Dit bestand wordt gegenereerd uit de routetabel van de plugin; de upstream-API staat ongewijzigd in jelly-leon.openapi.json. Routes van latere modules (zoeken, scènes, ondertitels, …) bestaan nog niet."
      },
      "paths": {
        "/media/v1/version": {
          "get": {
            "operationId": "JellyLeonGetVersion",
            "summary": "Forkversie, upstream-basis en compatibiliteit plugin ↔ server",
            "security": [{ "CustomAuthentication": [] }],
            "responses": {
              "200": {
                "description": "Versie-informatie; status is compatibel, afwijkend of unknown (nooit gesimuleerd groen).",
                "content": { "application/json": { "schema": { "$ref": "#/components/schemas/ForkVersionInfo" } } }
              },
              "401": { "description": "Niet aangemeld (geen geldige Jellyfin-sessie of API-sleutel)." }
            }
          }
        }
      },
      "components": {
        "securitySchemes": {
          "CustomAuthentication": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Jellyfin-authenticatie: Authorization: MediaBrowser Token=\"<token>\" (sessie of API-sleutel). Beheerroutes vragen een beheerder; een kinderprofiel krijgt 403."
          },
          "HubJwt": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Hub-JWT (EdDSA, aud jelly-leon) ondertekend met de gepinde sleutelset: gebruikers-JWT of dienst-JWT. Zonder pin 401 not_linked; rol kind 403."
          }
        },
        "schemas": {
          "ForkVersionInfo": {
            "type": "object",
            "required": ["schema_version", "fork_version", "upstream_tag", "upstream_commit", "plugin_built_against", "plugin_version", "server_version", "server_product_name", "display_name", "status", "reason_code", "message", "observed_at"],
            "properties": {
              "schema_version": { "type": "string", "example": "1.0" },
              "fork_version": { "type": "string", "description": "<upstream>-jl.<N> (ADR-0005)", "example": "10.11.11-jl.0" },
              "upstream_tag": { "type": "string", "example": "v10.11.11" },
              "upstream_commit": { "type": "string" },
              "plugin_built_against": { "type": "string", "description": "Jellyfin-versie waartegen de plugin is gebouwd" },
              "plugin_version": { "type": "string" },
              "server_version": { "type": "string", "description": "Versie die de server aan clients meldt (technische identiteit)" },
              "server_product_name": { "type": "string", "description": "Hoort 'Jellyfin Server' te zijn (ADR-0003)" },
              "display_name": { "type": "string", "example": "Jelly Leon" },
              "status": { "type": "string", "enum": ["compatibel", "afwijkend", "unknown"] },
              "reason_code": { "type": "string", "enum": ["ok", "plugin_abi_mismatch", "technical_identity_changed", "version_unknown"] },
              "message": { "type": "string", "description": "Nederlandse uitleg" },
              "observed_at": { "type": "string", "format": "date-time" }
            }
          }
        }
      }
    }
    """;

    private const string Schemas = """
    {
      "Fout": {
        "type": "object", "additionalProperties": false, "required": ["code", "message", "details", "trace_id"],
        "properties": {
          "code": { "type": "string", "enum": [] },
          "message": { "type": "string", "description": "Nederlandse uitleg" },
          "details": { "type": "object" },
          "trace_id": { "type": "string", "format": "uuid" }
        }
      },
      "Discover": {
        "type": "object", "additionalProperties": false,
        "required": ["app_id", "source_version", "schema_version", "capabilities", "permissions", "limits", "timestamp_utc"],
        "properties": {
          "app_id": { "type": "string", "enum": ["jelly-leon"] },
          "source_version": { "type": "string" },
          "schema_version": { "type": "string", "enum": ["1.0"] },
          "capabilities": { "type": "array", "items": { "type": "string", "enum": ["read"] } },
          "permissions": { "type": "array", "items": { "type": "string" } },
          "limits": {
            "type": "object", "additionalProperties": false, "required": ["max_page_size", "max_body_bytes", "event_payload_max_bytes", "max_age_s"],
            "properties": {
              "max_page_size": { "type": "integer" },
              "max_body_bytes": { "type": "integer" },
              "event_payload_max_bytes": { "type": "integer" },
              "max_age_s": { "type": "object", "additionalProperties": { "type": "integer" } }
            }
          },
          "timestamp_utc": { "type": "string", "format": "date-time" }
        }
      },
      "HealthCheck": {
        "type": "object", "additionalProperties": false, "required": ["name", "status", "observed_at", "detail"],
        "properties": {
          "name": { "type": "string", "pattern": "^[a-z0-9_.-]{1,64}$" },
          "status": { "type": "string", "enum": ["healthy", "unknown", "degraded", "down"] },
          "observed_at": { "type": "string", "format": "date-time" },
          "detail": { "type": "object", "nullable": true }
        }
      },
      "Health": {
        "type": "object", "additionalProperties": false, "required": ["status", "observed_at", "reason_code", "checks"],
        "properties": {
          "status": { "type": "string", "enum": ["healthy", "unknown", "degraded", "down"], "description": "De slechtste check (healthy < unknown < degraded < down)" },
          "observed_at": { "type": "string", "format": "date-time" },
          "reason_code": { "type": "string" },
          "checks": { "type": "array", "items": { "$ref": "#/components/schemas/HealthCheck" } }
        }
      },
      "Item": {
        "type": "object", "required": ["id", "observed_at"], "description": "Alleen aantallen, codes, tijdstippen en ondoorzichtige ID's",
        "properties": { "id": { "type": "string" }, "observed_at": { "type": "string", "format": "date-time" } }
      },
      "ItemsPagina": {
        "type": "object", "additionalProperties": false, "required": ["type", "items", "observed_at", "next_cursor"],
        "properties": {
          "type": { "type": "string" },
          "items": { "type": "array", "items": { "$ref": "#/components/schemas/Item" } },
          "observed_at": { "type": "string", "format": "date-time" },
          "next_cursor": { "type": "string", "nullable": true }
        }
      },
      "Event": {
        "type": "object", "additionalProperties": false,
        "required": ["schema_version", "event_id", "source_app", "source_event_id", "event_type", "entity", "timestamp_utc", "trace_id", "correlation_id", "actor", "classification", "payload", "payload_ref"],
        "properties": {
          "schema_version": { "type": "string", "enum": ["1.0"] },
          "event_id": { "type": "string", "format": "uuid" },
          "source_app": { "type": "string", "enum": ["jelly-leon"] },
          "source_event_id": { "type": "string" },
          "event_type": { "type": "string", "pattern": "^[a-z0-9_]+\\.[a-z0-9_]+\\.[a-z0-9_]+$" },
          "entity": {
            "type": "object", "additionalProperties": false, "required": ["type", "id"],
            "properties": { "type": { "type": "string" }, "id": { "type": "string" } }
          },
          "timestamp_utc": { "type": "string", "format": "date-time" },
          "trace_id": { "type": "string", "format": "uuid" },
          "correlation_id": { "type": "string", "nullable": true },
          "actor": {
            "type": "object", "additionalProperties": false, "required": ["type", "id"],
            "properties": { "type": { "type": "string", "enum": ["system", "user", "ai", "flow"] }, "id": { "type": "string" } }
          },
          "classification": { "type": "string", "enum": ["internal"] },
          "payload": { "type": "object" },
          "payload_ref": { "type": "string", "nullable": true }
        }
      },
      "EventsPagina": {
        "type": "object", "additionalProperties": false, "required": ["items", "next_cursor"],
        "properties": {
          "items": { "type": "array", "items": { "$ref": "#/components/schemas/Event" } },
          "next_cursor": { "type": "string", "nullable": true }
        }
      },
      "HubLink": {
        "type": "object", "additionalProperties": false,
        "required": ["status", "fingerprint", "service_id", "gepind_op", "jwt_sleutels", "policy_sleutels", "audience"],
        "properties": {
          "status": { "type": "string", "enum": ["not_linked", "linked"] },
          "fingerprint": { "type": "string", "nullable": true, "description": "Vingerafdruk van de gepinde sleutelset (contract §4.5)" },
          "service_id": { "type": "string", "nullable": true },
          "gepind_op": { "type": "string", "format": "date-time", "nullable": true },
          "jwt_sleutels": { "type": "integer" },
          "policy_sleutels": { "type": "integer" },
          "audience": { "type": "string", "enum": ["jelly-leon"] }
        }
      },
      "HubLinkVerifyVerzoek": {
        "type": "object", "additionalProperties": false, "required": ["keyset"],
        "properties": { "keyset": { "type": "object", "description": "De sleutelset zoals de Hub die toont (jwks en policy_public_key)" } }
      },
      "HubLinkVerify": {
        "type": "object", "additionalProperties": false, "required": ["fingerprint", "jwt_sleutels", "policy_sleutels"],
        "properties": { "fingerprint": { "type": "string" }, "jwt_sleutels": { "type": "integer" }, "policy_sleutels": { "type": "integer" } }
      },
      "HubLinkVerzoek": {
        "type": "object", "additionalProperties": false, "required": ["keyset", "fingerprint", "service_id"],
        "properties": {
          "keyset": { "type": "object" },
          "fingerprint": { "type": "string", "maxLength": 64, "description": "Door de beheerder overgetikt uit de Hub" },
          "service_id": { "type": "string", "format": "uuid" }
        }
      },
      "Module": {
        "type": "object", "additionalProperties": false, "required": ["slug", "naam", "enabled", "item_types", "event_types", "job_types"],
        "properties": {
          "slug": { "type": "string" },
          "naam": { "type": "string" },
          "enabled": { "type": "boolean" },
          "item_types": { "type": "array", "items": { "type": "string" } },
          "event_types": { "type": "array", "items": { "type": "string" } },
          "job_types": { "type": "array", "items": { "type": "string" } }
        }
      },
      "Modules": {
        "type": "object", "additionalProperties": false, "required": ["items"],
        "properties": { "items": { "type": "array", "items": { "$ref": "#/components/schemas/Module" } } }
      },
      "ModuleVerzoek": {
        "type": "object", "additionalProperties": false, "required": ["enabled"],
        "properties": { "enabled": { "type": "boolean" } }
      },
      "PrivacyRegel": {
        "type": "object", "additionalProperties": false, "required": ["module", "tabel", "gegeven", "doel", "bewaartermijn"],
        "properties": {
          "module": { "type": "string" }, "tabel": { "type": "string" }, "gegeven": { "type": "string" },
          "doel": { "type": "string" }, "bewaartermijn": { "type": "string" }
        }
      },
      "PrivacyRegister": {
        "type": "object", "additionalProperties": false, "required": ["items"],
        "properties": { "items": { "type": "array", "items": { "$ref": "#/components/schemas/PrivacyRegel" } } }
      },
      "ModuleStatus": {
        "type": "object", "required": ["module", "bewaar_dagen", "observed_at"], "description": "Aantallen van de module; geen titels, namen of paden",
        "properties": {
          "module": { "type": "string" },
          "bewaar_dagen": { "type": "integer" },
          "observed_at": { "type": "string", "format": "date-time" }
        }
      },
      "ModuleInstellingen": {
        "type": "object", "additionalProperties": false, "required": ["bewaar_dagen"],
        "properties": { "bewaar_dagen": { "type": "integer", "minimum": 1, "maximum": 365 } }
      },
      "ModuleInstellingenVerzoek": {
        "type": "object", "additionalProperties": false, "required": ["bewaar_dagen"],
        "properties": { "bewaar_dagen": { "type": "integer", "minimum": 1, "maximum": 365 } }
      }
    }
    """;

    private static readonly JsonSerializerOptions _opmaak = new() { WriteIndented = true, Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    private static readonly Dictionary<int, string> _uitleg = new()
    {
        [400] = "Idempotency-Key ontbreekt of is geen UUID.",
        [401] = "Niet aangemeld, niet gekoppeld (not_linked) of een ongeldig token; zie details.reason.",
        [403] = "Niet toegestaan voor dit account (kinderprofiel, rol kind of geen beheerder).",
        [404] = "Niet gevonden, of de module staat uit.",
        [409] = "Een verzoek met dezelfde Idempotency-Key wordt nog verwerkt.",
        [412] = "If-Match klopt niet meer; details.huidige_etag geeft de huidige ETag.",
        [413] = "Het verzoek is groter dan 1 MiB.",
        [422] = "Ongeldige invoer (details.fouten) of een hergebruikte Idempotency-Key.",
        [428] = "If-Match ontbreekt.",
        [501] = "Niet beschikbaar in deze versie (capability_unavailable).",
        [503] = "Eigen opslag of herhaalcontrole tijdelijk niet beschikbaar; zie Retry-After.",
    };

    /// <summary>Het volledige OpenAPI-document, deterministisch opgebouwd.</summary>
    public static JsonObject Bouw()
    {
        var document = JsonNode.Parse(Vast)!.AsObject();
        var schemas = document["components"]!["schemas"]!.AsObject();
        foreach (var (naam, schema) in JsonNode.Parse(Schemas)!.AsObject())
        {
            schemas[naam] = schema!.DeepClone();
        }

        schemas["Fout"]!["properties"]!["code"]!["enum"] = new JsonArray(
            Fouten.Catalogus.Keys.OrderBy(k => k, StringComparer.Ordinal).Select(k => (JsonNode)k).ToArray());

        var paden = document["paths"]!.AsObject();
        foreach (var route in RouteTable.Alle)
        {
            if (paden[route.Pad] is not JsonObject pad)
            {
                pad = new JsonObject();
                paden[route.Pad] = pad;
            }

            pad[route.Methode.ToLowerInvariant()] = Operatie(route);
        }

        return document;
    }

    public static string Tekst() => Bouw().ToJsonString(_opmaak) + "\n";

    /// <summary>De statuscodes die een route volgens de pipeline kan geven.</summary>
    public static IReadOnlyList<int> Statussen(RouteSpec route)
    {
        var codes = new SortedSet<int> { 401, 403, 503 };
        var heeftPadParameter = route.Pad.Contains('{', StringComparison.Ordinal);
        if (route.AntwoordSchema == "Fout")
        {
            codes.Add(501);
        }
        else
        {
            codes.Add(200);
        }

        if (route.Module is not null || heeftPadParameter)
        {
            codes.Add(404);
        }

        if (route.Methode != "GET")
        {
            codes.Add(413);
        }

        if (route.Idempotentie == JlIdem.Verplicht)
        {
            codes.UnionWith([400, 409, 422]);
        }

        if (route.HeeftBody || route.Id is "connector.items" or "connector.events")
        {
            codes.Add(422);
        }

        if (route.IfMatch)
        {
            codes.UnionWith([412, 428]);
        }

        return [.. codes];
    }

    private static JsonObject Operatie(RouteSpec route)
    {
        var parameters = new JsonArray();
        foreach (Match m in PadParameter().Matches(route.Pad))
        {
            parameters.Add(Parameter(m.Groups[1].Value, "path", true, "string", null));
        }

        if (route.Id == "connector.items")
        {
            parameters.Add(Parameter("type", "query", true, "string", "Een itemtype uit discover (permissions items:<type>:read)"));
        }

        if (route.Id is "connector.items" or "connector.events")
        {
            parameters.Add(Parameter("cursor", "query", false, "string", "De next_cursor van de vorige pagina"));
            parameters.Add(Parameter("limit", "query", false, "integer", "1 tot 200"));
        }

        if (route.Idempotentie == JlIdem.Verplicht)
        {
            parameters.Add(Parameter("Idempotency-Key", "header", true, "string", "UUID; dezelfde sleutel met hetzelfde verzoek geeft het oorspronkelijke antwoord met Idempotent-Replay: true"));
        }

        if (route.IfMatch)
        {
            parameters.Add(Parameter("If-Match", "header", true, "string", "De ETag van de laatste GET"));
        }

        var antwoorden = new JsonObject();
        foreach (var status in Statussen(route))
        {
            var schema = status == 200 ? route.AntwoordSchema : "Fout";
            antwoorden[status.ToString(System.Globalization.CultureInfo.InvariantCulture)] = new JsonObject
            {
                ["description"] = status == 200 ? route.Samenvatting : _uitleg[status],
                ["content"] = new JsonObject
                {
                    ["application/json"] = new JsonObject { ["schema"] = new JsonObject { ["$ref"] = "#/components/schemas/" + schema } },
                },
            };
        }

        var operatie = new JsonObject
        {
            ["operationId"] = "Jl" + string.Concat(route.Id.Split('.').Select(d => char.ToUpperInvariant(d[0]) + d[1..])),
            ["summary"] = route.Samenvatting,
            ["tags"] = new JsonArray(route.Module ?? (route.Auth == JlAuth.Hub ? "connector" : "beheer")),
            ["security"] = new JsonArray(new JsonObject { [route.Auth == JlAuth.Hub ? "HubJwt" : "CustomAuthentication"] = new JsonArray() }),
        };
        if (route.Vrijstelling is not null)
        {
            operatie["description"] = "Geen Idempotency-Key: " + route.Vrijstelling + ".";
        }

        if (parameters.Count > 0)
        {
            operatie["parameters"] = parameters;
        }

        if (route.VerzoekSchema is not null)
        {
            operatie["requestBody"] = new JsonObject
            {
                ["required"] = true,
                ["content"] = new JsonObject
                {
                    ["application/json"] = new JsonObject { ["schema"] = new JsonObject { ["$ref"] = "#/components/schemas/" + route.VerzoekSchema } },
                },
            };
        }

        operatie["responses"] = antwoorden;
        return operatie;
    }

    private static JsonObject Parameter(string naam, string plek, bool verplicht, string type, string? uitleg)
    {
        var parameter = new JsonObject
        {
            ["name"] = naam,
            ["in"] = plek,
            ["required"] = verplicht,
            ["schema"] = new JsonObject { ["type"] = type },
        };
        if (uitleg is not null)
        {
            parameter["description"] = uitleg;
        }

        return parameter;
    }

    [GeneratedRegex(@"\{([a-z_]+)\}")]
    private static partial Regex PadParameter();
}

/// <summary>Kleine schemacontrole voor de deelverzameling van OpenAPI 3.0 die het document gebruikt.</summary>
internal static class SchemaControle
{
    /// <summary>Geeft de afwijkingen van <paramref name="waarde"/> ten opzichte van het schema; leeg is in orde.</summary>
    public static List<string> Afwijkingen(JsonObject document, string schemaNaam, JsonNode? waarde)
    {
        var fouten = new List<string>();
        Controleer(document, document["components"]!["schemas"]![schemaNaam]!.AsObject(), waarde, schemaNaam, fouten);
        return fouten;
    }

    private static void Controleer(JsonObject document, JsonObject schema, JsonNode? waarde, string pad, List<string> fouten)
    {
        if (schema["$ref"] is JsonNode verwijzing)
        {
            var naam = verwijzing.GetValue<string>().Split('/')[^1];
            schema = document["components"]!["schemas"]![naam]!.AsObject();
        }

        if (waarde is null)
        {
            if (schema["nullable"]?.GetValue<bool>() != true)
            {
                fouten.Add(pad + ": null is niet toegestaan");
            }

            return;
        }

        var type = schema["type"]?.GetValue<string>();
        var soort = waarde.GetValueKind();
        var klopt = type switch
        {
            "object" => soort == JsonValueKind.Object,
            "array" => soort == JsonValueKind.Array,
            "string" => soort == JsonValueKind.String,
            "boolean" => soort is JsonValueKind.True or JsonValueKind.False,
            "integer" => soort == JsonValueKind.Number && waarde.AsValue().TryGetValue<long>(out _),
            _ => true,
        };
        if (!klopt)
        {
            fouten.Add($"{pad}: verwacht {type}, kreeg {soort}");
            return;
        }

        if (schema["enum"] is JsonArray toegestaan && !toegestaan.Any(e => e!.GetValue<string>() == waarde.GetValue<string>()))
        {
            fouten.Add($"{pad}: '{waarde.GetValue<string>()}' staat niet in de enum");
        }

        if (schema["pattern"] is JsonNode patroon && !Regex.IsMatch(waarde.GetValue<string>(), patroon.GetValue<string>()))
        {
            fouten.Add($"{pad}: past niet op het patroon");
        }

        if (schema["format"]?.GetValue<string>() == "date-time" && !DateTimeOffset.TryParse(waarde.GetValue<string>(), out _))
        {
            fouten.Add($"{pad}: geen tijdstip");
        }

        if (schema["format"]?.GetValue<string>() == "uuid" && !Guid.TryParse(waarde.GetValue<string>(), out _))
        {
            fouten.Add($"{pad}: geen UUID");
        }

        if (waarde is JsonArray lijst && schema["items"] is JsonObject itemSchema)
        {
            for (var i = 0; i < lijst.Count; i++)
            {
                Controleer(document, itemSchema, lijst[i], $"{pad}[{i}]", fouten);
            }
        }

        if (waarde is JsonObject o)
        {
            var eigenschappen = schema["properties"] as JsonObject ?? [];
            foreach (var verplicht in schema["required"] as JsonArray ?? [])
            {
                if (!o.ContainsKey(verplicht!.GetValue<string>()))
                {
                    fouten.Add($"{pad}: mist {verplicht}");
                }
            }

            foreach (var (naam, kind) in o)
            {
                if (eigenschappen[naam] is JsonObject kindSchema)
                {
                    Controleer(document, kindSchema, kind, pad + "." + naam, fouten);
                }
                else if (schema["additionalProperties"] is JsonObject vrijSchema)
                {
                    Controleer(document, vrijSchema, kind, pad + "." + naam, fouten);
                }
                else if (schema["additionalProperties"] is JsonValue vrij && !vrij.GetValue<bool>())
                {
                    fouten.Add($"{pad}: onbekend veld {naam}");
                }
            }
        }
    }
}
