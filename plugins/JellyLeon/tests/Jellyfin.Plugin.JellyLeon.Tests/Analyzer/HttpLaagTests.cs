using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Analyzers;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Analyzer;

/// <summary>
/// S-G1-17 herstelronde 8 (R-HARDE-EIS-17; besluit regisseur): de HTTP-laag van de server en netwerkclients. Via de HTTP-laag
/// kon plugincode, zonder één lid van de server-ABI, de server via zijn eigen REST-API kijkgegevens laten wissen (een
/// omgezet verzoek, een globaal filter, een claimsomzetting, of loopback met het token van de client). Nu is dat JL0001,
/// behalve in een klasse op de witte lijst van de HTTP-laag (alleen voor de eigen pluginpaden); een netwerkclient mag alleen
/// in een benoemde transportklasse (de lijst is leeg). Daarnaast zijn de omwegen uit grens 2 en 3 van herreview 7 JL0002.
/// ADR-0032, kop "HTTP-laag en netwerk".
/// </summary>
public class HttpLaagTests
{
    private const string Modules = "Jellyfin.Plugin.JellyLeon.Modules";

    private const string Usings = """
        using System;
        using System.Collections.Generic;
        using System.Linq;
        using System.Net;
        using System.Net.Http;
        using System.Net.Sockets;
        using System.Net.WebSockets;
        using System.Security.Claims;
        using System.Threading.Tasks;
        using Microsoft.AspNetCore.Authentication;
        using Microsoft.AspNetCore.Authorization;
        using Microsoft.AspNetCore.Builder;
        using Microsoft.AspNetCore.Hosting;
        using Microsoft.AspNetCore.Http;
        using Microsoft.AspNetCore.Http.Features;
        using Microsoft.AspNetCore.Mvc;
        using Microsoft.AspNetCore.Mvc.Filters;
        using Microsoft.AspNetCore.Mvc.Infrastructure;
        using Microsoft.AspNetCore.Mvc.ModelBinding;
        using Microsoft.AspNetCore.Routing;
        using Microsoft.Extensions.DependencyInjection;
        """;

    /// <summary>
    /// Herreview 7, punt 3: de vormen A tot en met D gaven op 8bf8b2cb4 geen melding en de echte pluginbouw slaagde. Elke
    /// regel met een markering moet nu precies die codes geven; elke andere melding is ook een fout.
    /// A: een IStartupFilter met een middleware die GET /Items?ParentId=… omzet naar DELETE /UserPlayedItems/….
    /// B: een globaal MVC-filter dat de argumenten van een serveractie wijzigt.
    /// C: HttpClient naar de eigen server via loopback, met het token van het binnenkomende verzoek.
    /// D: een claimsomzetting die de gebruiker verwisselt.
    /// </summary>
    [Fact]
    public async Task Herreview7Punt3_VormenAtotD_GevenNuEenJLFout()
    {
        var bron = Usings + "\n" + """
            namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
            {
                public static class Registratie
                {
                    public static void Registreer(IServiceCollection diensten)
                    {
                        diensten.AddTransient<IStartupFilter, Omzetter>();
                        diensten.Configure<MvcOptions>(o => o.Filters.Add(new Omleiden())); // B: JL0001
                        diensten.AddTransient<IClaimsTransformation, AndereGebruiker>();
                    }
                }

                public sealed class Omzetter : IStartupFilter // A: JL0001
                {
                    public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => app =>
                    {
                        app.Use(async (http, volgende) => // A: JL0001
                        {
                            if (http.Request.Path.StartsWithSegments("/Items") && http.Request.Query.ContainsKey("ParentId"))
                            {
                                http.Request.Method = "DELETE"; // A: JL0001
                                http.Request.Path = "/UserPlayedItems/" + http.Request.Query["ParentId"]; // A: JL0001
                            }

                            await volgende(http);
                        });
                        next(app);
                    };
                }

                public sealed class Omleiden : IActionFilter // B: JL0001
                {
                    public void OnActionExecuting(ActionExecutingContext context)
                    {
                        context.ActionArguments["itemId"] = "bibliotheek-B"; // B: JL0001
                    }

                    public void OnActionExecuted(ActionExecutedContext context)
                    {
                    }
                }

                public static class Lus
                {
                    public static async Task Roep(HttpContext http, string bibliotheek)
                    {
                        using var client = new HttpClient(); // C: JL0001
                        var adres = $"http://127.0.0.1:{http.Connection.LocalPort}/UserPlayedItems/{bibliotheek}";
                        using var verzoek = new HttpRequestMessage(HttpMethod.Delete, adres); // C: JL0001
                        verzoek.Headers.TryAddWithoutValidation("Authorization", http.Request.Headers.Authorization.ToString()); // C: JL0001
                        await client.SendAsync(verzoek); // C: JL0001
                    }
                }

                public sealed class AndereGebruiker : IClaimsTransformation // D: JL0001
                {
                    public Task<ClaimsPrincipal> TransformAsync(ClaimsPrincipal principal)
                    {
                        var identiteit = new ClaimsIdentity(principal.Claims.Where(c => c.Type != "Jellyfin-UserId"), "x");
                        return Task.FromResult(new ClaimsPrincipal(new[] { identiteit, new ClaimsIdentity(new[] { new Claim("Jellyfin-UserId", Guid.Empty.ToString()) }, "x") }));
                    }
                }
            }
            """;

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

        Assert.Equal(Verwacht(bron), gevonden.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Equal(12, Verwacht(bron).Count);
        Assert.Contains(gevonden, b => b.Tekst.Contains("'Microsoft.AspNetCore.Http.HttpRequest.Method' raakt de HTTP-laag", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("'Microsoft.AspNetCore.Mvc.MvcOptions.Filters' raakt de HTTP-laag", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("ActionExecutingContext.ActionArguments", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("'Microsoft.AspNetCore.Authentication.IClaimsTransformation'", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("'System.Net.Http.HttpClient.SendAsync' is een netwerkclient", StringComparison.Ordinal));
    }

    /// <summary>
    /// Varianten binnen dezelfde categorie: elk ander uitbreidingspunt van de HTTP-laag, een policy of schema van de server
    /// vervangen, een verzoek via de features omzetten, de verzoekkoppen, de routewaarden of de gebruiker wijzigen, een
    /// endpoint van de server rechtstreeks uitvoeren, en elke netwerkclient (sockets, websockets, IHttpClientFactory, een eigen
    /// handler), en een actie van de server in het proces uitvoeren (IActionInvokerFactory). De toegestane tegenvormen (lezen
    /// van het verzoek, het antwoord en Items schrijven, een enumwaarde) geven niets. In Core.Storage gelden dezelfde regels,
    /// ook voor WebClient en WebRequest (daar als netwerkclient).
    /// </summary>
    [Fact]
    public async Task Varianten_ElkeWegLangsDeHttpLaagOfHetNetwerkIsJL0001()
    {
        static string Bron(string ruimte) => Usings + "\n" + $$"""
            namespace {{ruimte}}
            {
            #pragma warning disable SYSLIB0014
                public sealed class Tussenlaag : IMiddleware // JL0001
                {
                    public Task InvokeAsync(HttpContext context, RequestDelegate next) => next(context);
                }

                public sealed class Beleid : IAuthorizationHandler // JL0001
                {
                    public Task HandleAsync(AuthorizationHandlerContext context) => Task.CompletedTask;
                }

                public sealed class Beleidsbron : IAuthorizationPolicyProvider // JL0001
                {
                    public Task<AuthorizationPolicy> GetPolicyAsync(string policyName) => Task.FromResult<AuthorizationPolicy>(null);

                    public Task<AuthorizationPolicy> GetDefaultPolicyAsync() => Task.FromResult<AuthorizationPolicy>(null);

                    public Task<AuthorizationPolicy> GetFallbackPolicyAsync() => Task.FromResult<AuthorizationPolicy>(null);
                }

                public sealed class Waardebron : IValueProviderFactory // JL0001
                {
                    public Task CreateValueProviderAsync(ValueProviderFactoryContext context) => Task.CompletedTask;
                }

                public interface IEigenFilter : IAsyncResourceFilter // JL0001
                {
                }

                public sealed class ViaEigenFilter : IEigenFilter // JL0001
                {
                    public Task OnResourceExecutionAsync(ResourceExecutingContext context, ResourceExecutionDelegate next) => next();
                }

                public sealed class EigenHandler : DelegatingHandler
                {
                }

                public static class Wegen
                {
                    public static void Registreer(IServiceCollection diensten, IApplicationBuilder app)
                    {
                        app.UseMiddleware<Tussenlaag>(); // JL0001
                        app.Map("/Items", tak => { }); // JL0001
                        diensten.AddAuthorization(o => o.AddPolicy("RequiresElevation", b => { })); // JL0001
                        diensten.Configure<AuthenticationOptions>(o => o.DefaultScheme = "x"); // JL0001
                        diensten.Configure<MvcOptions>(o => o.ValueProviderFactories.Insert(0, new Waardebron())); // JL0001
                        diensten.Configure<MvcOptions>(o => o.Conventions.Clear()); // JL0001
                    }

                    public static void Actie(IActionDescriptorCollectionProvider acties, IActionInvokerFactory invokers, ActionContext context)
                    {
                        _ = acties.ActionDescriptors.Items[0]; // JL0001
                        _ = invokers.CreateInvoker(context); // JL0001
                        _ = context.ActionDescriptor.DisplayName; // JL0001
                    }

                    public static void Verzoek(HttpContext http, Endpoint endpoint, ClaimsIdentity identiteit, Claim claim)
                    {
                        http.Features.Get<IHttpRequestFeature>().Path = "/UserPlayedItems/x"; // JL0001
                        http.Request.PathBase = "/x"; // JL0001
                        http.Request.QueryString = new QueryString("?userId=x"); // JL0001
                        http.Request.Body = System.IO.Stream.Null; // JL0001
                        http.Request.Headers["Authorization"] = "x"; // JL0001
                        http.Request.Headers.Authorization = "x"; // JL0001
                        http.Request.Headers.Append("Authorization", "x"); // JL0001
                        var koppen = http.Request.Headers; // JL0001
                        http.Request.RouteValues["itemId"] = "x"; // JL0001
                        IDictionary<string, object> waarden = http.Request.RouteValues; // JL0001
                        http.User = new ClaimsPrincipal(); // JL0001
                        identiteit.RemoveClaim(claim); // JL0001
                        identiteit.AddClaim(claim); // JL0001
                        _ = endpoint.RequestDelegate; // JL0001
                        // Toegestaan: het verzoek lezen, het antwoord en Items schrijven.
                        _ = http.Request.Path;
                        _ = http.Request.Method;
                        _ = http.Request.Query["x"];
                        _ = http.Request.Headers["X-Test"].ToString();
                        _ = http.Request.Headers.TryGetValue("X-Test", out _);
                        _ = http.Request.Headers.ContainsKey("X-Test");
                        _ = http.Request.Headers.Authorization;
                        http.Response.Headers["X-Test"] = "y";
                        http.Response.StatusCode = 200;
                        http.Items["x"] = 1;
                        _ = HttpCompletionOption.ResponseHeadersRead;
                    }

                    public static void Netwerk(IHttpClientFactory fabriek, Uri doel)
                    {
                        _ = fabriek.CreateClient("x"); // JL0001
                        using var tcp = new TcpClient("127.0.0.1", 8096); // JL0001
                        using var socket = new Socket(SocketType.Stream, ProtocolType.Tcp); // JL0001
                        using var ws = new ClientWebSocket(); // JL0001
                        using var handler = new EigenHandler(); // JL0001
                        using var w = new WebClient(); // NET
                        _ = WebRequest.Create(doel); // NET
                    }
                }
            #pragma warning restore SYSLIB0014
            }
            """;

        var buiten = Bron(Modules + ".Proef");
        var opslag = Bron("Jellyfin.Plugin.JellyLeon.Core.Storage");

        var gevondenBuiten = await AnalyzerHarnas.AnalyseerAsync(buiten, null, TestContext.Current.CancellationToken);
        var gevondenOpslag = await AnalyzerHarnas.AnalyseerAsync(opslag, null, TestContext.Current.CancellationToken);

        // Buiten de opslaglaag meldt de bestandsregel WebClient en WebRequest al (JL0002); geen tweede melding.
        var net = Regels(buiten, "// NET");
        Assert.Equal(Verwacht(buiten).Concat(net.Select(r => (r, "JL0002"))).ToHashSet(), gevondenBuiten.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Equal(Verwacht(opslag).Concat(net.Select(r => (r, "JL0001"))).ToHashSet(), gevondenOpslag.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Equal(34, Verwacht(buiten).Count);
        Assert.All(gevondenOpslag.Where(b => net.Contains(b.Regel)), b => Assert.Contains("is een netwerkclient", b.Tekst, StringComparison.Ordinal));
        Assert.Contains(gevondenBuiten, b => b.Tekst.Contains("'Microsoft.AspNetCore.Http.HttpRequest.Headers (anders dan rechtstreeks lezen)'", StringComparison.Ordinal));
        Assert.Contains(gevondenBuiten, b => b.Tekst.Contains("'Microsoft.AspNetCore.Routing.RouteValueDictionary als ", StringComparison.Ordinal));
    }

    /// <summary>
    /// De witte lijst van de HTTP-laag geldt per klasse en per lid of uitbreidingspunt: de spike (JlStartupFilterSpike) mag een
    /// IStartupFilter zijn en Use aanroepen, JlRouteAttribute mag IAsyncActionFilter zijn. Dezelfde code in een andere klasse,
    /// een ander lid in de genoemde klasse (Map, UseMiddleware), een ander uitbreidingspunt (IActionFilter) en een geneste klasse
    /// zijn JL0001.
    /// </summary>
    [Fact]
    public async Task WitteLijst_GeldtPerKlasseEnPerLid()
    {
        static string Bron(string spike, string attribuut) => Usings + "\n" + $$"""
            namespace Jellyfin.Plugin.JellyLeon.Core.Http
            {
                public sealed class {{spike}} : IStartupFilter // ANDERE-KLASSE
                {
                    public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => app =>
                    {
                        app.Use(VoorAuthAsync); // ANDERE-KLASSE
                        app.Map("/x", tak => { }); // JL0001
                        next(app);
                    };

                    private static Task VoorAuthAsync(HttpContext http, RequestDelegate volgende) => volgende(http);

                    public sealed class Genest : IMiddleware // JL0001
                    {
                        public Task InvokeAsync(HttpContext context, RequestDelegate next) => next(context);
                    }
                }

                [AttributeUsage(AttributeTargets.Method)]
                public sealed class {{attribuut}} : Attribute, IAsyncActionFilter // ANDERE-KLASSE
                {
                    public Task OnActionExecutionAsync(ActionExecutingContext context, ActionExecutionDelegate next) => next();
                }

                [AttributeUsage(AttributeTargets.Method)]
                public sealed class TweedeFilter : Attribute, IActionFilter // JL0001
                {
                    public void OnActionExecuting(ActionExecutingContext context)
                    {
                    }

                    public void OnActionExecuted(ActionExecutedContext context)
                    {
                    }
                }
            }
            """;

        var opDeLijst = Bron("JlStartupFilterSpike", "JlRouteAttribute");
        var elders = Bron("AnderFilter", "AnderAttribuut");

        var gevondenOp = await AnalyzerHarnas.AnalyseerAsync(opDeLijst, null, TestContext.Current.CancellationToken);
        var gevondenElders = await AnalyzerHarnas.AnalyseerAsync(elders, null, TestContext.Current.CancellationToken);

        Assert.Equal(Verwacht(opDeLijst), gevondenOp.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Equal(3, gevondenOp.Count);
        Assert.Equal(Verwacht(elders).Concat(Regels(elders, "// ANDERE-KLASSE").Select(r => (r, "JL0001"))).ToHashSet(), gevondenElders.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Equal(6, gevondenElders.Count);
    }

    /// <summary>
    /// Besluit punt 2: de lijst met transportklassen is leeg (de plugin heeft er nu geen nodig). Een netwerkclient is dus in
    /// elke namespace JL0001, ook in Core.MediaGuard (waar de toekomstige vervoerder komt), Core.Storage en Core.Secrets. Een
    /// klasse komt pas op de lijst met een eigen ADR en een test dat zij loopback, het eigen serveradres en link-local weigert.
    /// </summary>
    [Fact]
    public async Task Netwerk_TransportlijstIsLeegEnElkeClientIsOveralJL0001()
    {
        Assert.Empty(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.NetwerkKlassen);

        foreach (var ruimte in new[] { Modules + ".Proef", "Jellyfin.Plugin.JellyLeon.Core.MediaGuard", "Jellyfin.Plugin.JellyLeon.Core.Storage", "Jellyfin.Plugin.JellyLeon.Core.Secrets", "Jellyfin.Plugin.JellyLeon.Core.Werker" })
        {
            var bron = AnalyzerHarnas.Klasse(ruimte, "MediaGuardVervoerder", """
                public async System.Threading.Tasks.Task M(System.Net.Http.HttpClient http, System.Uri doel)
                {
                    _ = await http.GetAsync(doel); // JL0001
                    using var handler = new System.Net.Http.SocketsHttpHandler(); // JL0001
                    using var invoker = new System.Net.Http.HttpMessageInvoker(handler); // JL0001
                    _ = System.Net.Http.HttpMethod.Get; // JL0001
                }
                """);

            var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

            Assert.Equal(Verwacht(bron), gevonden.Select(b => (b.Regel, b.Id)).ToHashSet());
            Assert.Equal(4, gevonden.Count);
            Assert.All(gevonden, b => Assert.Contains("is een netwerkclient", b.Tekst, StringComparison.Ordinal));
        }
    }

    /// <summary>
    /// Herreview 7, grenzen 2 en 3 (besluit: dichten als omweg, JL0002, nergens): reflectie in een Microsoft- of BCL-bibliotheek
    /// die een eigenschap van een levend serverobject zet (ConfigurationBinder.Bind/Get, TypeDescriptor en
    /// PropertyDescriptor.SetValue), DispatchProxy.Create (een implementatie van een serverinterface zonder eigen klasse),
    /// System.Linq.Expressions (een aanroep opbouwen en compileren of laten uitvoeren), Unsafe.As en modelbinding op een bestaand
    /// object (ControllerBase.TryUpdateModelAsync). Ook in Core.Storage.
    /// </summary>
    [Fact]
    public async Task Omwegen_ReflectieInBibliotheken_DispatchProxyEnExpressies_ZijnNergensToegestaan()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using System.ComponentModel;
            using System.Linq;
            using System.Linq.Expressions;
            using System.Reflection;
            using System.Runtime.CompilerServices;
            using MediaBrowser.Controller.Library;
            using MediaBrowser.Controller.Session;
            using Microsoft.AspNetCore.Mvc;
            using Microsoft.Extensions.Configuration;
            using Microsoft.Extensions.DependencyInjection;

            namespace {{ruimte}}
            {
                public class Leeg : DispatchProxy
                {
                    protected override object Invoke(MethodInfo targetMethod, object[] args) => null;
                }

                public sealed class Schaduw
                {
                    public DateTime LastPlaybackCheckIn;
                }

                public static class Omwegen
                {
                    public static void M(IConfiguration cfg, SessionInfo sessie, IServiceCollection diensten, MethodInfo methode, object iets, ControllerBase controller)
                    {
                        cfg.Bind(sessie); // JL0002
                        _ = controller.TryUpdateModelAsync(sessie); // JL0002
                        ConfigurationBinder.Bind(cfg, "x", sessie); // JL0002
                        _ = cfg.Get<SessionInfo>(); // JL0002
                        var eigenschappen = TypeDescriptor.GetProperties(sessie); // JL0002
                        eigenschappen["LastPlaybackCheckIn"].SetValue(sessie, DateTime.MinValue); // JL0002
                        _ = eigenschappen["LastPlaybackCheckIn"].GetValue(sessie); // JL0002
                        var stomp = DispatchProxy.Create<IUserDataManager, Leeg>(); // JL0002
                        diensten.AddSingleton(stomp);
                        var aanroep = Expression.Call(Expression.Constant(iets), methode); // JL0002
                        var lambda = Expression.Lambda<Action>(aanroep); // JL0002
                        lambda.Compile()(); // JL0002
                        _ = new[] { 1 }.AsQueryable().Provider.Execute(aanroep); // uitvoeren via een provider: het opbouwen van de boom is al een omweg
                        Unsafe.As<Schaduw>(sessie).LastPlaybackCheckIn = DateTime.MinValue; // JL0002
                        // Toegestaan: een expressie die de compiler maakt (de leden erin tellen gewoon) en een enumwaarde.
                        Expression<Func<int>> getal = () => 1;
                        _ = ExpressionType.Call;
                        _ = getal;
                    }
                }
            }
            """;

        foreach (var ruimte in new[] { Modules + ".Proef", "Jellyfin.Plugin.JellyLeon.Core.Storage" })
        {
            var bron = Bron(ruimte);
            var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);
            var omweg = gevonden.Where(b => b.Tekst.Contains("omzeilt de bouwgrens", StringComparison.Ordinal)).ToList();

            Assert.Equal(Verwacht(bron), omweg.Select(b => (b.Regel, b.Id)).ToHashSet());
            Assert.Equal(12, Verwacht(bron).Count);

            // Daarnaast alleen de witte lijst van de server-ABI (IUserDataManager als typeargument is een typenaam: vrij).
            Assert.All(gevonden.Except(omweg), b => Assert.True(AnalyzerHarnas.IsWitteLijst(b), b.Tekst));
        }
    }

    /// <summary>De typen in de tabellen van de HTTP-laag, het netwerk en de witte lijst bestaan in deze SDK (wacht bij een update).</summary>
    [Fact]
    public void Tabellen_ElkTypeEnLidBestaat()
    {
        var compilatie = AnalyzerHarnas.Compileer("namespace Leeg { public class Niets { } }");
        var typen = Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpUitbreidingTypen
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpPijplijnTypen)
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpOptieTypen)
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpZetTypen)
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.NetwerkTypen)
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpVerbodenLeden.Select(v => v.Type))
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpWitteLijst.Select(w => w.Type))
            .Append("Microsoft.AspNetCore.Http.HttpRequest")
            .Distinct(StringComparer.Ordinal)
            .ToList();

        Assert.True(typen.Count >= 20, "verdacht weinig typen: " + typen.Count);
        Assert.All(typen, naam => Assert.True(compilatie.GetTypeByMetadataName(naam) is not null, "onbekend type: " + naam));
        Assert.All(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpVerbodenLeden, v => Assert.True(compilatie.GetTypeByMetadataName(v.Type)!.GetMembers(v.Lid).Length > 0, "onbekend lid: " + v.Type + "." + v.Lid));
        Assert.All(
            Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpWitteLijst.Where(w => w.Lid != HttpWit.Implementeert),
            w => Assert.True(compilatie.GetTypeByMetadataName(w.Type)!.GetMembers(w.Lid).Length > 0, "onbekend lid: " + w.Type + "." + w.Lid));

        // Elke namespace bevat typen in deze SDK (een verhuisde namespace zou de regel stil uitzetten).
        var namespaces = Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpUitbreidingNamespaces
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpLedenNamespaces)
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.NetwerkNamespaces)
            .Distinct(StringComparer.Ordinal);
        var bekend = compilatie.References
            .Select(r => compilatie.GetAssemblyOrModuleSymbol(r) as Microsoft.CodeAnalysis.IAssemblySymbol)
            .Where(a => a is not null)
            .SelectMany(a => Alle(a!.GlobalNamespace))
            .ToHashSet(StringComparer.Ordinal);
        Assert.All(namespaces, n => Assert.Contains(n, bekend));
    }

    /// <summary>Elke regel van de witte lijst van de HTTP-laag staat met motivatie in ADR-0032 (kop "HTTP-laag en netwerk").</summary>
    [Fact]
    public async Task WitteLijst_ElkeRegelStaatInAdr0032()
    {
        var adr = (await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, "ADR-0032.md"), TestContext.Current.CancellationToken)).Replace("\r\n", "\n", StringComparison.Ordinal);
        var tabel = adr.Split('\n').Where(r => r.StartsWith("| `", StringComparison.Ordinal)).ToList();

        Assert.Contains("#### HTTP-laag en netwerk", adr, StringComparison.Ordinal);
        foreach (var wit in Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HttpWitteLijst)
        {
            var kort = wit.Type.Split('.').Last();
            var klasse = wit.Klasse.Substring("Jellyfin.Plugin.JellyLeon.".Length);
            var lid = wit.Lid == HttpWit.Implementeert ? "implementeert" : wit.Lid;
            Assert.True(
                tabel.Any(r => r.Contains("`" + kort + "`", StringComparison.Ordinal) && r.Contains(lid, StringComparison.Ordinal) && r.Contains("`" + klasse + "`", StringComparison.Ordinal)),
                "ADR-0032 noemt " + kort + " " + lid + " in " + wit.Klasse + " niet in de tabel van de HTTP-laag");
        }
    }

    private static IEnumerable<string> Alle(Microsoft.CodeAnalysis.INamespaceSymbol ruimte)
    {
        foreach (var kind in ruimte.GetNamespaceMembers())
        {
            if (kind.GetTypeMembers().Length > 0)
            {
                yield return kind.ToDisplayString();
            }

            foreach (var dieper in Alle(kind))
            {
                yield return dieper;
            }
        }
    }

    /// <summary>Verwachte (regel, code)-paren: elke JLxxxx na "//" op een regel.</summary>
    private static HashSet<(int Regel, string Id)> Verwacht(string bron) =>
        bron.Split('\n')
            .Select((tekst, index) => (Regel: index + 1, Opmerking: tekst.Contains("//", StringComparison.Ordinal) ? tekst[tekst.IndexOf("//", StringComparison.Ordinal)..] : string.Empty))
            .SelectMany(r => Regex.Matches(r.Opmerking, @"\bJL\d{4}\b").Select(m => (r.Regel, m.Value)))
            .ToHashSet();

    private static List<int> Regels(string bron, string merk) =>
        bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.Contains(merk, StringComparison.Ordinal)).Select(r => r.Regel).ToList();
}
