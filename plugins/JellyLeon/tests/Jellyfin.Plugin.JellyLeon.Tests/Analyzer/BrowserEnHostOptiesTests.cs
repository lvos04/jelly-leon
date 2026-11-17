using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Analyzer;

/// <summary>
/// S-G1-17 herstelronde 9 (herreview 8; besluit regisseur, optie A). R-HARDE-EIS-18: een eigen actie kon de browser van de
/// beheerder doorsturen (een redirect, een Location-kop of een 3xx-status) en de browser volgde dat met dezelfde methode en het
/// token van de gebruiker naar elke route van de server. R-HARDE-EIS-19: een optietype van de host (zoals
/// <c>Microsoft.AspNetCore.Mvc.JsonOptions</c>) gaf geen JL-fout, en <c>PostConfigure&lt;JsonOptions&gt;</c> met een eigen
/// converter wijzigde het argument van elke serveractie. Beide zijn nu JL0001 (ADR-0032, kop "HTTP-laag en netwerk").
/// </summary>
public class BrowserEnHostOptiesTests
{
    /// <summary>
    /// R-HARDE-EIS-18 punt 3: elke redirect (ook <c>Redirect</c> zonder "PreserveMethod": een browser volgt 301 en 302 bij DELETE
    /// met dezelfde methode), elke Location-kop (eigenschap, <c>HeaderNames</c>, als tekst, ook op een eigen woordenboek en
    /// samengesteld), de antwoorden die een Location-kop zetten (Created, Accepted) en een constante 3xx-status. In elke
    /// namespace, ook in de opslaglaag en in Core.Http. Een gewone status, een andere kop en Ok/NoContent mogen.
    /// </summary>
    [Fact]
    public async Task Doorsturen_RedirectsLocationEn3xxZijnOveralJL0001()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using System.Collections.Generic;
            using Microsoft.AspNetCore.Http;
            using Microsoft.AspNetCore.Mvc;
            using Microsoft.Net.Http.Headers;

            namespace {{ruimte}}
            {
                public sealed class Acties : ControllerBase
                {
                    public IActionResult A(string id) => RedirectPreserveMethod("/UserPlayedItems/" + id); // JL0001
                    public IActionResult B() => RedirectPermanentPreserveMethod("/x"); // JL0001
                    public IActionResult C() => LocalRedirectPreserveMethod("/x"); // JL0001
                    public IActionResult D() => LocalRedirectPermanentPreserveMethod("/x"); // JL0001
                    public IActionResult E() => RedirectToActionPreserveMethod("x"); // JL0001
                    public IActionResult F() => RedirectToRoutePreserveMethod("x"); // JL0001
                    public IActionResult G() => RedirectToPagePreserveMethod("x"); // JL0001
                    public IActionResult H() => Redirect("/UserPlayedItems/x"); // JL0001
                    public IActionResult I() => LocalRedirect("/x"); // JL0001
                    public IActionResult J() => new RedirectResult("/x", false, true); // JL0001
                    public IActionResult K() => new RedirectResult("/x") { PreserveMethod = true }; // JL0001
                    public IActionResult L() => Created("/UserPlayedItems/x", null); // JL0001
                    public IActionResult M() => AcceptedAtAction("x"); // JL0001
                    public IActionResult N() => StatusCode(307); // JL0001
                    public IActionResult O() => new StatusCodeResult(308); // JL0001
                    public IActionResult P() => new ObjectResult(null) { StatusCode = 302 }; // JL0001
                    public IResult Q() => Results.Redirect("/x", false, true); // JL0001
                    public IResult R() => TypedResults.LocalRedirect("/x"); // JL0001

                    public void S(HttpContext http)
                    {
                        http.Response.Redirect("/x", false, true); // JL0001
                        http.Response.Headers.Location = "/UserPlayedItems/x"; // JL0001
                        http.Response.Headers["Location"] = "/x"; // JL0001
                        http.Response.Headers["location"] = "/x"; // JL0001
                        http.Response.Headers.Append("Location", "/x"); // JL0001
                        http.Response.Headers[HeaderNames.Location] = "/x"; // JL0001
                        http.Response.StatusCode = 307; // JL0001
                        http.Response.StatusCode = StatusCodes.Status308PermanentRedirect; // JL0001
                        http.Response.StatusCode = StatusCodes.Status301MovedPermanently; // JL0001
                        http.Response.StatusCode = (int)System.Net.HttpStatusCode.Redirect; // JL0001
                        const string Kop = "Loc" + "ation"; // JL0001
                        var eigen = new Dictionary<string, string>();
                        eigen[nameof(Location)] = "/x"; // JL0001
                        _ = Kop;

                        // Toegestaan: een gewone status, een andere kop en de gewone antwoorden.
                        http.Response.StatusCode = 200;
                        http.Response.StatusCode = StatusCodes.Status404NotFound;
                        http.Response.Headers["ETag"] = "x";
                        _ = Ok();
                        _ = NoContent();
                        _ = StatusCode(404);
                        _ = new ObjectResult(null) { StatusCode = 404 };
                    }

                    public string Location { get; set; }
                }
            }
            """;

        foreach (var ruimte in new[] { "Jellyfin.Plugin.JellyLeon.Modules.Proef", "Jellyfin.Plugin.JellyLeon.Core.Http", "Jellyfin.Plugin.JellyLeon.Core.Storage" })
        {
            var bron = Bron(ruimte);
            var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

            Assert.Equal(Verwacht(bron), gevonden.Select(b => (b.Regel, b.Id)).ToHashSet());
            Assert.Equal(30, Verwacht(bron).Count);
            Assert.All(gevonden, b => Assert.Contains("stuurt de browser door", b.Tekst, StringComparison.Ordinal));
        }
    }

    /// <summary>
    /// R-HARDE-EIS-20 (herreview 9, herstelronde 10): de vorm van de herreview (de status uit een variabele met een waarde uit
    /// System.Net, en de kopnaam via <c>HttpResponseHeader.Location.ToString()</c>) en de varianten met System.Net zijn nu
    /// JL0001: de kop Location uit System.Net en elke 3xx-waarde van <c>HttpStatusCode</c>, ook als de naam geen van de woorden
    /// bevat (<c>Found</c>, <c>SeeOther</c>). Een status uit een variabele zonder zo'n waarde ziet de analyzer niet; die weigert de
    /// wacht bij het draaien (<c>DoorstuurWachtTests</c>). De witte lijst van punt 8 geldt alleen in <c>Core.Http.DoorstuurWacht</c>
    /// en alleen voor <c>HeaderNames.Location</c> als argument van <c>ContainsKey</c> of <c>Remove</c> op de antwoordkoppen: zetten,
    /// toevoegen, teruggeven, een ander woordenboek, de tekst "Location" en een 3xx blijven daar JL0001, en elders is ook kijken
    /// en weghalen JL0001.
    /// </summary>
    [Fact]
    public async Task Doorsturen_SystemNetIsJL0001_EnAlleenDeWachtMagLocationZienEnWeghalen()
    {
        const string Bron = """
            using System.Collections.Generic;
            using System.Net;
            using Microsoft.AspNetCore.Http;
            using Microsoft.AspNetCore.Mvc;
            using Microsoft.Net.Http.Headers;

            namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
            {
                public sealed class Verplaats : ControllerBase
                {
                    public IActionResult A(string id, bool verplaatst)
                    {
                        var status = verplaatst ? HttpStatusCode.TemporaryRedirect : HttpStatusCode.OK; // JL0001
                        Response.Headers[HttpResponseHeader.Location.ToString()] = "/UserPlayedItems/" + id; // JL0001
                        return StatusCode((int)status);
                    }

                    public void B(HttpContext http)
                    {
                        http.Response.StatusCode = (int)HttpStatusCode.Found; // JL0001
                        _ = HttpStatusCode.SeeOther; // JL0001
                        _ = HttpStatusCode.MultipleChoices; // JL0001
                        _ = HttpStatusCode.PermanentRedirect; // JL0001
                        var kop = new WebHeaderCollection { [HttpResponseHeader.Location] = "/x" }; // JL0001
                        http.Response.Headers.Append(HttpResponseHeader.Location.ToString(), "/x"); // JL0001
                        http.Response.Headers.Remove(HeaderNames.Location); // JL0001
                        _ = http.Response.Headers.ContainsKey(HeaderNames.Location); // JL0001
                        _ = kop;

                        // Toegestaan: een gewone status uit System.Net en een andere kop. Een status uit een variabele ziet de
                        // analyzer niet; die weigert de wacht bij het draaien.
                        http.Response.StatusCode = (int)HttpStatusCode.NotFound;
                        _ = HttpStatusCode.OK;
                        http.Response.Headers[HttpResponseHeader.ETag.ToString()] = "x";
                        var code = 300 + http.Request.Path.Value!.Length;
                        http.Response.StatusCode = code;
                    }
                }
            }

            namespace Jellyfin.Plugin.JellyLeon.Core.Http
            {
                internal static class DoorstuurWacht
                {
                    public static bool Kijk(HttpResponse a) => a.Headers.ContainsKey(HeaderNames.Location);

                    public static bool Weg(HttpResponse a) => a.Headers.Remove(HeaderNames.Location);

                    public static void Zet(HttpResponse a) => a.Headers[HeaderNames.Location] = "/x"; // JL0001

                    public static void Voeg(HttpResponse a) => a.Headers.Append(HeaderNames.Location, "/x"); // JL0001

                    public static string Naam() => HeaderNames.Location; // JL0001

                    public static bool Elders(Dictionary<string, string> d) => d.Remove(HeaderNames.Location); // JL0001

                    public static bool Tekst(HttpResponse a) => a.Headers.Remove("Location"); // JL0001

                    public static void Status(HttpResponse a) => a.StatusCode = 307; // JL0001

                    public static bool Verzoek(HttpRequest v) => v.Headers.ContainsKey(HeaderNames.Location); // JL0001
                }
            }

            namespace Jellyfin.Plugin.JellyLeon.Core.Http.Elders
            {
                internal static class DoorstuurWacht
                {
                    public static bool Weg(HttpResponse a) => a.Headers.Remove(HeaderNames.Location); // JL0001
                }
            }
            """;

        var stop = TestContext.Current.CancellationToken;
        Assert.Empty(AnalyzerHarnas.Compileer(Bron).GetDiagnostics(stop).Where(d => d.Severity == Microsoft.CodeAnalysis.DiagnosticSeverity.Error));
        var gevonden = await AnalyzerHarnas.AnalyseerAsync(Bron, null, stop);

        Assert.Equal(Verwacht(Bron), gevonden.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Equal(18, Verwacht(Bron).Count);
        Assert.All(gevonden, b => Assert.Contains("stuurt de browser door", b.Tekst, StringComparison.Ordinal));
    }

    /// <summary>
    /// R-HARDE-EIS-19: elk lid van een optietype van de host (ook lezen en aanmaken), elke registratie met zo'n type als
    /// typeargument (ook binden vanuit de configuratie, dat raakt geen lid), <c>IOptions&lt;T&gt;.Value</c>, <c>typeof</c>, en elk
    /// eigen type dat zo'n type implementeert of ervan afleidt (ook als typeargument van IConfigureOptions,
    /// IPostConfigureOptions en IConfigureNamedOptions). In elke namespace. Eigen opties en een eigen JsonSerializerOptions
    /// mogen.
    /// </summary>
    [Fact]
    public async Task HostOpties_ElkLidTypeargumentEnImplementatieIsJL0001()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using System.Text.Json;
            using System.Text.Json.Serialization;
            using Microsoft.AspNetCore.Mvc;
            using Microsoft.AspNetCore.Server.Kestrel.Core;
            using Microsoft.Extensions.Configuration;
            using Microsoft.Extensions.DependencyInjection;
            using Microsoft.Extensions.Hosting;
            using Microsoft.Extensions.Options;

            namespace {{ruimte}}
            {
                public sealed class TicksAlsSeconden : JsonConverter<long>
                {
                    public override long Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) => reader.GetInt64() * 10_000_000;

                    public override void Write(Utf8JsonWriter writer, long value, JsonSerializerOptions options) => writer.WriteNumberValue(value);
                }

                public sealed class EigenOpties
                {
                    public bool Aan { get; set; }
                }

                public sealed class JsonInstellingen : IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions> // JL0001
                {
                    public void PostConfigure(string name, Microsoft.AspNetCore.Mvc.JsonOptions options)
                    {
                    }
                }

                public sealed class Benoemd : IConfigureNamedOptions<Microsoft.AspNetCore.Http.Json.JsonOptions> // JL0001
                {
                    public void Configure(Microsoft.AspNetCore.Http.Json.JsonOptions options)
                    {
                    }

                    public void Configure(string name, Microsoft.AspNetCore.Http.Json.JsonOptions options)
                    {
                    }
                }

                public sealed class Afsluiten : IConfigureOptions<HostOptions> // JL0001
                {
                    public void Configure(HostOptions options)
                    {
                    }
                }

                public sealed class EigenJson : Microsoft.AspNetCore.Mvc.JsonOptions // JL0001
                {
                }

                public static class Registratie
                {
                    public static void Registreer(IServiceCollection d, IConfiguration cfg, IOptions<HostOptions> host, IOptions<Microsoft.AspNetCore.Mvc.JsonOptions> mvcJson)
                    {
                        d.PostConfigure<Microsoft.AspNetCore.Mvc.JsonOptions>(o => o.JsonSerializerOptions.Converters.Add(new TicksAlsSeconden())); // JL0001
                        d.Configure<Microsoft.AspNetCore.Http.Json.JsonOptions>(o => { }); // JL0001
                        d.Configure<ApiBehaviorOptions>(cfg); // JL0001
                        d.AddOptions<Microsoft.AspNetCore.Builder.ForwardedHeadersOptions>().Bind(cfg); // JL0001
                        d.AddSingleton<IConfigureOptions<KestrelServerOptions>>(new ConfigureOptions<KestrelServerOptions>(o => { })); // JL0001
                        d.Configure<MvcOptions>(o => { }); // JL0001
                        d.ConfigureOptions<JsonInstellingen>();
                        _ = host.Value.ShutdownTimeout; // JL0001
                        _ = mvcJson.Value; // JL0001
                        _ = new Microsoft.AspNetCore.Mvc.JsonOptions(); // JL0001
                        _ = typeof(IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>); // JL0001

                        // Toegestaan: eigen opties en een eigen JsonSerializerOptions.
                        d.Configure<EigenOpties>(o => o.Aan = true);
                        _ = new JsonSerializerOptions { WriteIndented = true };
                        _ = typeof(EigenOpties);
                    }
                }
            }
            """;

        foreach (var ruimte in new[] { "Jellyfin.Plugin.JellyLeon.Modules.Proef", "Jellyfin.Plugin.JellyLeon.Core.Http", "Jellyfin.Plugin.JellyLeon.Core.Storage" })
        {
            var bron = Bron(ruimte);
            var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

            Assert.Equal(Verwacht(bron), gevonden.Select(b => (b.Regel, b.Id)).ToHashSet());
            Assert.Equal(14, Verwacht(bron).Count);
            Assert.All(gevonden, b => Assert.Contains("gebruikt een instelling van de host", b.Tekst, StringComparison.Ordinal));
        }
    }

    /// <summary>
    /// De witte lijst van de instellingen van de host is leeg (de plugin gebruikt geen optietype van de host); de genoemde
    /// typen en leden bestaan in deze SDK (anders zou een regel stil uitvallen).
    /// </summary>
    [Fact]
    public void Tabellen_WitteLijstLeegEnElkTypeBestaat()
    {
        Assert.Empty(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HostOptieWitteLijst);

        var compilatie = AnalyzerHarnas.Compileer("namespace Leeg { public class Niets { } }");
        foreach (var naam in Jellyfin.Plugin.JellyLeon.Analyzers.Regels.HostOptieTypen
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.DoorstuurStatusLeden.Select(s => s.Type))
            .Concat(new[]
            {
                "Microsoft.AspNetCore.Mvc.JsonOptions",
                "Microsoft.AspNetCore.Http.Json.JsonOptions",
                "Microsoft.AspNetCore.Mvc.ApiBehaviorOptions",
                "Microsoft.AspNetCore.Builder.ForwardedHeadersOptions",
                "Microsoft.AspNetCore.Server.Kestrel.Core.KestrelServerOptions",
                "Microsoft.Net.Http.Headers.HeaderNames",
            }))
        {
            Assert.True(compilatie.GetTypeByMetadataName(naam) is not null, "onbekend type: " + naam);
        }

        foreach (var (type, voorvoegsel) in Jellyfin.Plugin.JellyLeon.Analyzers.Regels.DoorstuurStatusLeden)
        {
            Assert.Contains(compilatie.GetTypeByMetadataName(type)!.GetMembers(), l => l.Name.StartsWith(voorvoegsel, StringComparison.Ordinal));
        }
    }

    /// <summary>
    /// ADR-0032 noemt de browser als tussenpersoon onder "Dreigingsmodel" en "Grenzen" (met de webplugins van jelly-leon-web),
    /// de twee nieuwe regels onder "HTTP-laag en netwerk", en grens 5 (een eigen route boven een serverroute, gedekt door
    /// RoutetabelTests).
    /// </summary>
    [Fact]
    public async Task Adr0032_NoemtDeBrowserAlsTussenpersoonDeNieuweRegelsEnGrens5()
    {
        var adr = (await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, "ADR-0032.md"), TestContext.Current.CancellationToken)).Replace("\r\n", "\n", StringComparison.Ordinal);

        string Deel(string kop)
        {
            var begin = adr.IndexOf(kop + "\n", StringComparison.Ordinal);
            Assert.True(begin >= 0, "kop ontbreekt: " + kop);
            var niveau = kop.TakeWhile(c => c == '#').Count();
            var rest = adr[(begin + kop.Length)..];
            var einde = Regex.Match(rest, "\n#{1," + niveau + "} ");
            return einde.Success ? rest[..einde.Index] : rest;
        }

        var dreiging = Deel("#### Dreigingsmodel");
        var grenzen = Deel("## Grenzen (eerlijk)");
        var http = Deel("#### HTTP-laag en netwerk (JL0001)");

        Assert.Contains("browser als tussenpersoon", dreiging, StringComparison.Ordinal);
        Assert.Contains("browser als tussenpersoon", grenzen, StringComparison.Ordinal);
        Assert.Contains("jelly-leon-web", grenzen, StringComparison.Ordinal);
        Assert.Contains("BrowserTussenpersoonTests", dreiging, StringComparison.Ordinal);
        Assert.Contains("RoutetabelTests", grenzen, StringComparison.Ordinal);
        Assert.Contains("eigen route boven een serverroute", grenzen, StringComparison.Ordinal);
        Assert.Contains("stuurt de browser door", http, StringComparison.Ordinal);
        Assert.Contains("instellingen van de host", http, StringComparison.Ordinal);
        Assert.Contains("PostConfigure<JsonOptions>", http, StringComparison.Ordinal);

        // Herstelronde 10 (R-HARDE-EIS-20): de oude zin gold alleen voor JlResult en een constante status; nu dekt de wacht
        // tegen doorsturen de 3xx en de kop Location bij het draaien. Plus de twee grenzen uit herreview 9.
        Assert.DoesNotContain("zonder 3xx volgt de browser geen omleiding", adr, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("DoorstuurWacht", http, StringComparison.Ordinal);
        Assert.Contains("System.Net", http, StringComparison.Ordinal);
        Assert.Contains("DoorstuurWacht", dreiging, StringComparison.Ordinal);
        Assert.Contains("wacht tegen doorsturen", grenzen, StringComparison.Ordinal);
        Assert.Contains("JellyLeonVersionController.GetVersion", grenzen, StringComparison.Ordinal);
        Assert.Contains("open generieke registratie", grenzen, StringComparison.Ordinal);
        Assert.Contains("typeof(IPostConfigureOptions<>)", grenzen, StringComparison.Ordinal);
        Assert.Contains("S-G1-16", grenzen, StringComparison.Ordinal);
        Assert.Contains("fetch.call(…)", grenzen, StringComparison.Ordinal);
        Assert.Contains("S-G1-12", grenzen, StringComparison.Ordinal);
    }

    /// <summary>Verwachte (regel, code)-paren: elke JLxxxx na "//" op een regel.</summary>
    private static HashSet<(int Regel, string Id)> Verwacht(string bron) =>
        bron.Split('\n')
            .Select((tekst, index) => (Regel: index + 1, Opmerking: tekst.Contains("//", StringComparison.Ordinal) ? tekst[tekst.IndexOf("//", StringComparison.Ordinal)..] : string.Empty))
            .SelectMany(r => Regex.Matches(r.Opmerking, @"\bJL\d{4}\b").Select(m => (r.Regel, m.Value)))
            .ToHashSet();
}
