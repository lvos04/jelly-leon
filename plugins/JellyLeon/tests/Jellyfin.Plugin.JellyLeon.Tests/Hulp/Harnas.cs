using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Net;
using MediaBrowser.Controller.Session;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Abstractions;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Moq;
using Org.BouncyCastle.Crypto.Generators;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using Org.BouncyCastle.Security;

namespace Jellyfin.Plugin.JellyLeon.Tests.Hulp;

internal sealed class NepKlok : TimeProvider
{
    public DateTimeOffset Nu { get; set; } = new(2026, 11, 11, 10, 0, 0, TimeSpan.Zero);

    public override DateTimeOffset GetUtcNow() => Nu;
}

internal sealed class NepSchakelaars : IModuleSwitches
{
    private readonly Dictionary<string, bool> _stand = new(StringComparer.Ordinal);

    public string Etag => "\"" + string.Join(';', _stand.OrderBy(s => s.Key, StringComparer.Ordinal).Select(s => s.Key + "=" + s.Value)) + "\"";

    public bool IsAan(string slug) => _stand.GetValueOrDefault(slug);

    public void Zet(string slug, bool aan) => _stand[slug] = aan;
}

internal sealed class NepSessies : ISessionAuthenticator
{
    /// <summary>Gets or sets de identiteit; <c>null</c> betekent: niet aangemeld.</summary>
    public SessieIdentiteit? Wie { get; set; } = new(Guid.Parse("11111111-2222-4333-8444-555555555555"), true, false);

    public Task<SessieIdentiteit> AuthenticeerAsync(HttpRequest verzoek) =>
        Wie is null ? throw Fouten.NietGeauthenticeerd("invalid_token") : Task.FromResult(Wie);
}

internal sealed class NepMedia : IMediaMappen
{
    public List<string> Mappen { get; } = [];

    public IReadOnlyList<string> Paden() => Mappen;
}

/// <summary>Een nagebouwde Hub die tokens tekent met een tweede, onafhankelijke Ed25519-implementatie.</summary>
internal sealed class NepHub
{
    private readonly Ed25519PrivateKeyParameters _jwt;
    private readonly Ed25519PrivateKeyParameters _policy;

    public NepHub()
    {
        _jwt = Nieuw();
        _policy = Nieuw();
    }

    public string ServiceId { get; } = "0b9f6a52-7c1d-4e8a-9b3f-2d5e6f708192";

    public string Kid => KidVan(_jwt);

    public static string B64(byte[] bytes) => Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    public JsonObject Keyset() => new()
    {
        ["jwks"] = new JsonObject { ["keys"] = new JsonArray(Jwk(_jwt)) },
        ["policy_public_key"] = Jwk(_policy),
    };

    public HubKeySet Sleutels() => HubKeySet.Parse(Keyset(), "keyset");

    /// <summary>Een geldig gebruikers-JWT; <paramref name="wijzig"/> mag claims en header aanpassen.</summary>
    public string Token(DateTimeOffset nu, string rol = "viewer", Action<JsonObject, JsonObject>? wijzig = null)
    {
        var header = new JsonObject { ["alg"] = "EdDSA", ["typ"] = "JWT", ["kid"] = Kid };
        var t = nu.ToUnixTimeSeconds();
        var claims = new JsonObject
        {
            ["iss"] = "hub",
            ["aud"] = "jelly-leon",
            ["sub"] = "7d0c1a52-3f64-4b7e-8a11-9c2f5e6d7a80",
            ["token_use"] = "user",
            ["roles"] = new JsonArray(rol),
            ["iat"] = t,
            ["nbf"] = t,
            ["exp"] = t + 60,
            ["jti"] = Guid.NewGuid().ToString(),
        };
        wijzig?.Invoke(header, claims);
        return Teken(header, claims);
    }

    public string DienstToken(DateTimeOffset nu) => Token(nu, "service", (_, c) =>
    {
        c["sub"] = "hub";
        c["token_use"] = "hub_service";
        c["service_id"] = ServiceId;
    });

    public string Teken(JsonObject header, JsonObject claims, Ed25519PrivateKeyParameters? sleutel = null)
    {
        var invoer = B64(Encoding.UTF8.GetBytes(header.ToJsonString())) + "." + B64(Encoding.UTF8.GetBytes(claims.ToJsonString()));
        var signer = new Ed25519Signer();
        signer.Init(true, sleutel ?? _jwt);
        var bytes = Encoding.ASCII.GetBytes(invoer);
        signer.BlockUpdate(bytes, 0, bytes.Length);
        return invoer + "." + B64(signer.GenerateSignature());
    }

    public static Ed25519PrivateKeyParameters Nieuw()
    {
        var generator = new Ed25519KeyPairGenerator();
        generator.Init(new Ed25519KeyGenerationParameters(new SecureRandom()));
        return (Ed25519PrivateKeyParameters)generator.GenerateKeyPair().Private;
    }

    private static string KidVan(Ed25519PrivateKeyParameters sleutel) =>
        Convert.ToHexStringLower(SHA256.HashData(sleutel.GeneratePublicKey().GetEncoded()))[..16];

    private static JsonObject Jwk(Ed25519PrivateKeyParameters sleutel) => new()
    {
        ["kty"] = "OKP",
        ["crv"] = "Ed25519",
        ["x"] = B64(sleutel.GeneratePublicKey().GetEncoded()),
        ["kid"] = KidVan(sleutel),
        ["use"] = "sig",
        ["alg"] = "EdDSA",
    };
}

internal sealed record Antwoord(int Status, JsonNode? Json, IReadOnlyDictionary<string, string> Kop)
{
    public string? Code => Json?["code"]?.GetValue<string>();

    public string? Reden => Json?["details"]?["reason"]?.GetValue<string>();
}

/// <summary>
/// Bouwt de plugin op met de echte registratie (PluginServiceRegistrator) in een tijdelijke map en roept routes aan via
/// het echte filter, de echte pipeline en de echte controller — zonder webserver.
/// </summary>
internal sealed class Harnas : IDisposable
{
    private static readonly Dictionary<string, MethodInfo> _acties = typeof(Plugin).Assembly.GetTypes()
        .Where(t => typeof(ControllerBase).IsAssignableFrom(t))
        .SelectMany(t => t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
        .Where(m => m.GetCustomAttribute<JlRouteAttribute>() is not null)
        .ToDictionary(m => m.GetCustomAttribute<JlRouteAttribute>()!.Id, StringComparer.Ordinal);

    public Harnas()
    {
        Map = Directory.CreateTempSubdirectory("jl-test-").FullName;
        var paden = new Mock<IApplicationPaths>();
        paden.SetupGet(p => p.DataPath).Returns(Path.Combine(Map, "data"));
        paden.SetupGet(p => p.CachePath).Returns(Path.Combine(Map, "cache"));
        var diensten = new ServiceCollection();
        diensten.AddLogging();
        diensten.AddSingleton<TimeProvider>(Klok);
        diensten.AddSingleton(paden.Object);
        diensten.AddSingleton(Mock.Of<ISessionManager>());
        diensten.AddSingleton(Mock.Of<ILibraryManager>());
        diensten.AddSingleton(Mock.Of<IAuthService>());
        new PluginServiceRegistrator().RegisterServices(diensten, Mock.Of<IServerApplicationHost>());
        diensten.AddSingleton<IModuleSwitches>(Schakelaars);
        diensten.AddSingleton<ISessionAuthenticator>(Sessies);
        diensten.AddSingleton<IMediaMappen>(Media);
        Diensten = diensten.BuildServiceProvider();
    }

    public string Map { get; }

    public NepKlok Klok { get; } = new();

    public NepSchakelaars Schakelaars { get; } = new();

    public NepSessies Sessies { get; } = new();

    public NepMedia Media { get; } = new();

    public NepHub Hub { get; } = new();

    public ServiceProvider Diensten { get; }

    public T Dienst<T>()
        where T : notnull => Diensten.GetRequiredService<T>();

    public void Koppel() => Dienst<HubPin>().Zet(Hub.Sleutels(), Hub.ServiceId, Klok.Nu);

    /// <summary>Roept een route uit de routetabel aan. Kopregels als "Naam: waarde".</summary>
    public async Task<Antwoord> Roep(string routeId, string? body = null, string[]? kop = null, Dictionary<string, string>? pad = null, string? query = null, byte[]? ruw = null)
    {
        var spec = RouteTable.Zoek(routeId);
        var actie = _acties[routeId];
        var http = new DefaultHttpContext { RequestServices = Diensten };
        var volledigPad = spec.Pad;
        foreach (var (naam, waarde) in pad ?? [])
        {
            volledigPad = volledigPad.Replace("{" + naam + "}", waarde, StringComparison.Ordinal);
        }

        http.Request.Method = spec.Methode;
        http.Request.Path = volledigPad;
        http.Request.QueryString = new QueryString(query is null ? string.Empty : "?" + query);
        var bytes = ruw ?? (body is null ? null : Encoding.UTF8.GetBytes(body));
        if (bytes is not null)
        {
            http.Request.Body = new MemoryStream(bytes);
            http.Request.ContentLength = bytes.Length;
            http.Request.ContentType = "application/json";
        }

        foreach (var regel in kop ?? [])
        {
            var deel = regel.Split(": ", 2);
            http.Request.Headers[deel[0]] = deel[1];
        }

        var controller = (ControllerBase)ActivatorUtilities.CreateInstance(Diensten, actie.DeclaringType!);
        var actieContext = new ActionContext(http, new RouteData(), new Microsoft.AspNetCore.Mvc.Controllers.ControllerActionDescriptor());
        controller.ControllerContext = new ControllerContext(actieContext);
        var argumenten = actie.GetParameters().Select(p => (object?)(pad ?? [])[p.Name!]).ToArray();
        var voor = new ActionExecutingContext(actieContext, [], new Dictionary<string, object?>(), controller);
        ActionExecutedContext? na = null;
        await actie.GetCustomAttribute<JlRouteAttribute>()!.OnActionExecutionAsync(voor, () =>
        {
            na = new ActionExecutedContext(actieContext, [], controller);
            try
            {
                na.Result = (IActionResult)actie.Invoke(controller, argumenten)!;
            }
            catch (TargetInvocationException fout)
            {
                na.Exception = fout.InnerException;
            }

            return Task.FromResult(na);
        });
        var resultaat = (JlResult)(voor.Result ?? na!.Result)!;
        return new Antwoord(resultaat.Status, string.IsNullOrEmpty(resultaat.Body) ? null : JsonNode.Parse(resultaat.Body), resultaat.Headers);
    }

    public Task<Antwoord> RoepHub(string routeId, string token, string? body = null, string[]? kop = null, string? query = null) =>
        Roep(routeId, body, [.. kop ?? [], "Authorization: Bearer " + token], null, query);

    public void Dispose()
    {
        Diensten.Dispose();
        Directory.Delete(Map, true);
    }
}
