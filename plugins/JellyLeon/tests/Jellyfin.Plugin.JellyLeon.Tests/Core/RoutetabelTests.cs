using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Api;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.ApplicationParts;
using Microsoft.AspNetCore.Mvc.Controllers;
using Microsoft.AspNetCore.Mvc.Routing;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// Statische bewaking van de routes (contract 1.3 §5 en ADR-0016): elke route precies één keer, elke actie via de ene
/// pipeline, en geen muterende route zonder Idempotency-Key buiten de vrijstellingslijst.
/// </summary>
public sealed class RoutetabelTests
{
    /// <summary>De vrijstellingslijst van contract §5; elke andere muterende route vraagt een Idempotency-Key.</summary>
    private static readonly string[] _vrijgesteld = ["connector.propose", "connector.apply", "connector.rollback", "hublink.verify", "segments.import.preview", "modules.import.preview"];

    private static IEnumerable<(Type Controller, MethodInfo Actie)> Acties() =>
        typeof(Plugin).Assembly.GetTypes()
            .Where(t => typeof(ControllerBase).IsAssignableFrom(t) && t != typeof(JellyLeonVersionController))
            .SelectMany(t => t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly).Select(m => (t, m)))
            .Where(p => !p.m.IsSpecialName);

    [Fact]
    public async Task Connectorroutes_StaanElkEenKeerInDeMvcEndpoints()
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.Services.AddControllers().AddApplicationPart(typeof(Plugin).Assembly);
        await using var app = builder.Build();
        app.MapControllers();

        var routes = ((IEndpointRouteBuilder)app).DataSources
            .SelectMany(bron => bron.Endpoints)
            .OfType<RouteEndpoint>()
            .Select(endpoint => (Pad: "/" + endpoint.RoutePattern.RawText?.TrimStart('/'), Endpoint: endpoint))
            .Where(route => route.Pad.StartsWith("/connector/v1/", StringComparison.OrdinalIgnoreCase))
            .SelectMany(route => route.Endpoint.Metadata.GetRequiredMetadata<HttpMethodMetadata>().HttpMethods
                .Select(methode => (Methode: methode, route.Pad)))
            .ToArray();
        var verwacht = RouteTable.Alle.Where(r => r.Auth == JlAuth.Hub).Select(r => (r.Methode, r.Pad));
        Assert.NotEmpty(routes);
        Assert.Empty(RouteSleutel.Dubbel(routes));
        Assert.Equal(verwacht.OrderBy(r => r.Pad, StringComparer.Ordinal).ThenBy(r => r.Methode, StringComparer.Ordinal),
            routes.OrderBy(r => r.Pad, StringComparer.Ordinal).ThenBy(r => r.Methode, StringComparer.Ordinal));
    }

    [Fact]
    public void ElkeActie_LooptViaDePipelineEnKomtOvereenMetDeTabel()
    {
        var gezien = new List<string>();
        foreach (var (controller, actie) in Acties())
        {
            var jl = actie.GetCustomAttribute<JlRouteAttribute>();
            Assert.True(jl is not null, $"{controller.Name}.{actie.Name} mist [JlRoute]: de actie zou buiten de pipeline lopen.");
            var spec = RouteTable.Zoek(jl.Id);
            var http = Assert.Single(actie.GetCustomAttributes<HttpMethodAttribute>());
            var basis = controller.GetCustomAttribute<RouteAttribute>()!.Template;
            var pad = "/" + basis + (string.IsNullOrEmpty(http.Template) ? string.Empty : "/" + http.Template);
            Assert.Equal(spec.Methode, Assert.Single(http.HttpMethods));
            Assert.Equal(spec.Pad, pad);
            gezien.Add(jl.Id);

            // Zonder [ApiController] en [Authorize]: de pipeline bepaalt zelf de volgorde 401 → 403 → 404 → 413 → 400 → 422.
            Assert.Null(controller.GetCustomAttribute<ApiControllerAttribute>());
            Assert.Null(controller.GetCustomAttribute<AuthorizeAttribute>());
            Assert.Null(actie.GetCustomAttribute<AuthorizeAttribute>());
        }

        Assert.Equal(RouteTable.Alle.Select(r => r.Id).OrderBy(i => i, StringComparer.Ordinal), gezien.OrderBy(i => i, StringComparer.Ordinal));
    }

    [Fact]
    public void ElkeRoute_BestaatPreciesEenKeer()
    {
        Assert.Equal(RouteTable.Alle.Count, RouteTable.Alle.Select(r => r.Id).Distinct(StringComparer.Ordinal).Count());

        // Zoals de server routes vergelijkt: hoofdletterongevoelig, padparameters zonder naam (R-TECH-5, S-G1-17).
        Assert.Empty(RouteSleutel.Dubbel(RouteTable.Alle.Select(r => (r.Methode, r.Pad))));
        Assert.All(RouteTable.Alle, r => Assert.True(r.Pad.StartsWith("/connector/v1/", StringComparison.Ordinal) || r.Pad.StartsWith("/media/v1/", StringComparison.Ordinal)));

        // De connector hoort bij Core en bestaat dus één keer, ook met meerdere modules.
        Assert.All(RouteTable.Alle.Where(r => r.Pad.StartsWith("/connector/v1/", StringComparison.Ordinal)), r =>
        {
            Assert.Null(r.Module);
            Assert.Equal(JlAuth.Hub, r.Auth);
        });

        // Moduleroutes liggen onder de eigen naam van de module.
        Assert.All(RouteTable.Alle.Where(r => r.Module is not null), r => Assert.StartsWith("/media/v1/" + r.Module + "/", r.Pad, StringComparison.Ordinal));
    }

    /// <summary>De uniekheidscontrole vangt een route die alleen in hoofdletters, parameternaam of slot-slash verschilt.</summary>
    [Fact]
    public void Uniekheidscontrole_VangtVariantenDieDeServerAlsDezelfdeRouteZiet()
    {
        Assert.Equal(new[] { "GET /MEDIA/V1/HUB-LINK" }, RouteSleutel.Dubbel([("GET", "/media/v1/hub-link"), ("GET", "/media/v1/Hub-link")]));
        Assert.Single(RouteSleutel.Dubbel([("get", "/media/v1/hub-link"), ("GET", "/media/v1/hub-link")]));
        Assert.Single(RouteSleutel.Dubbel([("PUT", "/media/v1/modules/{id}"), ("PUT", "/media/v1/modules/{naam}")]));
        Assert.Single(RouteSleutel.Dubbel([("DELETE", "/media/v1/hub-link"), ("DELETE", "/media/v1/hub-link/")]));

        // Wat de server wel als twee routes ziet, blijft twee.
        Assert.Empty(RouteSleutel.Dubbel([("GET", "/media/v1/hub-link"), ("PUT", "/media/v1/hub-link")]));
        Assert.Empty(RouteSleutel.Dubbel([("GET", "/media/v1/modules/{id}"), ("GET", "/media/v1/modules/{id}/status")]));
    }

    [Fact]
    public void MuterendeRoute_VraagtIdempotencyKeyOfStaatOpDeVrijstellingslijst()
    {
        foreach (var route in RouteTable.Alle)
        {
            var muterend = route.Methode is "POST" or "PUT" or "PATCH" or "DELETE";
            if (!muterend)
            {
                Assert.Equal(JlIdem.Geen, route.Idempotentie);
                continue;
            }

            if (_vrijgesteld.Contains(route.Id))
            {
                Assert.Equal(JlIdem.Vrijgesteld, route.Idempotentie);
                Assert.False(string.IsNullOrWhiteSpace(route.Vrijstelling), route.Id + " mist de reden van de vrijstelling.");
            }
            else
            {
                Assert.True(route.Idempotentie == JlIdem.Verplicht, route.Id + " is muterend en vraagt geen Idempotency-Key.");
            }
        }

        Assert.All(_vrijgesteld, id => Assert.Equal(JlIdem.Vrijgesteld, RouteTable.Zoek(id).Idempotentie));
    }

    [Fact]
    public async Task VrijgesteldeConnectorroutes_GevenAltijd501()
    {
        using var h = new Harnas();
        h.Koppel();
        foreach (var id in new[] { "connector.propose", "connector.apply", "connector.rollback", "connector.evidence" })
        {
            var antwoord = await h.RoepHub(id, h.Hub.Token(h.Klok.Nu, "admin"));
            Assert.Equal((501, "capability_unavailable"), (antwoord.Status, antwoord.Code));
        }
    }

    /// <summary>
    /// R-HARDE-EIS-20 (S-G1-17 herstelronde 10): de wacht tegen doorsturen (<c>DoorstuurWacht</c>) staat op elke actie met
    /// [JlRoute]. Daarom: elke controller die MVC in de plugin vindt (ook een POCO-controller zonder <c>ControllerBase</c>) is een
    /// <c>ControllerBase</c> die <see cref="ElkeActie_LooptViaDePipelineEnKomtOvereenMetDeTabel"/> nagaat, en de enige eigen actie
    /// zonder [JlRoute] is <c>JellyLeonVersionController.GetVersion</c> (een vast 200-antwoord met JSON). Een nieuwe actie daar
    /// zou buiten de wacht vallen; deze test faalt dan.
    /// </summary>
    [Fact]
    public void ElkeController_LooptViaDeWacht_BehalveDeEneVersieactie()
    {
        var onderdelen = new ApplicationPartManager();
        onderdelen.ApplicationParts.Add(new AssemblyPart(typeof(Plugin).Assembly));
        onderdelen.FeatureProviders.Add(new ControllerFeatureProvider());
        var gevonden = new ControllerFeature();
        onderdelen.PopulateFeature(gevonden);

        Assert.NotEmpty(gevonden.Controllers);
        Assert.All(gevonden.Controllers, c => Assert.True(typeof(ControllerBase).IsAssignableFrom(c), c.FullName + " is geen ControllerBase"));
        var versie = typeof(JellyLeonVersionController).GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
            .Where(m => !m.IsSpecialName)
            .ToList();
        var enige = Assert.Single(versie);
        Assert.Equal(nameof(JellyLeonVersionController.GetVersion), enige.Name);
        Assert.Equal(typeof(ActionResult<ForkVersionInfo>), enige.ReturnType);
        Assert.Equal(
            gevonden.Controllers.Select(c => c.AsType()).Where(c => c != typeof(JellyLeonVersionController)).OrderBy(c => c.FullName, StringComparer.Ordinal),
            Acties().Select(a => a.Controller).Distinct().OrderBy(c => c.FullName, StringComparer.Ordinal));
    }

    [Fact]
    public void Versieroute_BlijftOngewijzigdAchterDeServeraanmelding()
    {
        Assert.NotNull(typeof(JellyLeonVersionController).GetCustomAttribute<AuthorizeAttribute>());
    }
}
