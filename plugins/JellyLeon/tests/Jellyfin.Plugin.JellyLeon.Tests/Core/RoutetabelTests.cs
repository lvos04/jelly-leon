using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Api;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Routing;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// Statische bewaking van de routes (contract 1.3 §5 en ADR-0016): elke route precies één keer, elke actie via de ene
/// pipeline, en geen muterende route zonder Idempotency-Key buiten de vrijstellingslijst.
/// </summary>
public sealed class RoutetabelTests
{
    /// <summary>De vrijstellingslijst van contract §5; elke andere muterende route vraagt een Idempotency-Key.</summary>
    private static readonly string[] _vrijgesteld = ["connector.propose", "connector.apply", "connector.rollback", "hublink.verify"];

    private static IEnumerable<(Type Controller, MethodInfo Actie)> Acties() =>
        typeof(Plugin).Assembly.GetTypes()
            .Where(t => typeof(ControllerBase).IsAssignableFrom(t) && t != typeof(JellyLeonVersionController))
            .SelectMany(t => t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly).Select(m => (t, m)))
            .Where(p => !p.m.IsSpecialName);

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
        Assert.Equal(RouteTable.Alle.Count, RouteTable.Alle.Select(r => r.Methode + " " + r.Pad).Distinct(StringComparer.Ordinal).Count());
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

    [Fact]
    public void Versieroute_BlijftOngewijzigdAchterDeServeraanmelding()
    {
        Assert.NotNull(typeof(JellyLeonVersionController).GetCustomAttribute<AuthorizeAttribute>());
    }
}
