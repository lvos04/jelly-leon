using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// S-G1-17 herstelronde 9, R-HARDE-EIS-18 (besluit regisseur, optie A): de browser als tussenpersoon. Plugincode die in de
/// browser van de beheerder draait (de ingebedde webbronnen, zoals de configuratiepagina) gebruikt het token van de beheerder.
/// Zo'n bron mag alleen de eigen paden van de plugin vragen, via één functie <c>vraag()</c> die elk ander pad weigert vóór
/// <c>ApiClient.fetch</c>; geen andere netwerk-, script- of navigatieweg. Daarnaast weigert een pluginantwoord (<see cref="JlResult"/>)
/// een 3xx-status: een browser volgt die met dezelfde methode en hetzelfde token (ADR-0032, kop "Dreigingsmodel").
/// </summary>
public class BrowserTussenpersoonTests
{
    /// <summary>Wegen naar een andere route, een script of een andere pagina. Elk ervan is in een ingebedde webbron verboden.</summary>
    private static readonly (string Naam, Regex Patroon)[] _verboden =
    {
        ("XMLHttpRequest", new Regex(@"\b(XMLHttpRequest|ActiveXObject)\b")),
        ("jQuery/$.ajax", new Regex(@"\bjQuery\b|\$\s*\.\s*(ajax|get|post|getJSON|getScript|load)\b")),
        ("locatiewissel", new Regex(@"\blocation\b|\bhistory\s*\.|\bopen\s*\(|\bnavigate\b|\.submit\s*\(|\bsendBeacon\b")),
        ("andere verbinding", new Regex(@"\b(WebSocket|EventSource|Worker|serviceWorker|RTCPeerConnection)\b")),
        ("code laden", new Regex(@"\bimport\s*\(|\bimportScripts\b|\beval\b|\bFunction\s*\(|\bset(Timeout|Interval)\s*\(\s*['""`]")),
        ("andere API-client", new Regex(@"\b(ServerConnections|ConnectionManager|Dashboard|appRouter|globalThis|localStorage|sessionStorage)\b|\bdocument\s*\.\s*cookie\b|\bpostMessage\b")),
        ("globaal object via index", new Regex(@"\b(window|self|globalThis|top|parent|frames)\s*\[")),
        ("ander lid van window", new Regex(@"\bwindow\s*\.(?!crypto\.getRandomValues\()")),
        ("HTML invoegen", new Regex(@"\b(innerHTML|outerHTML|insertAdjacentHTML)\b|\bdocument\s*\.\s*write")),
        ("element met een adres", new Regex(@"createElement\s*\(\s*['""](script|iframe|frame|form|a|link|base|img|object|embed|meta)['""]")),
        ("adres zetten", new Regex(@"\.(src|href|action|formAction)\s*=|setAttribute\s*\(\s*['""](src|href|action|formaction|on[a-z]+)['""]")),
        ("<script src>", new Regex(@"<script\b[^>]*\bsrc\s*=", RegexOptions.IgnoreCase)),
        ("HTML-element met een adres", new Regex(@"<(iframe|frame|form|object|embed|link|base|a|img|video|audio|source)\b|<meta\b[^>]*http-equiv", RegexOptions.IgnoreCase)),
        ("inline gebeurtenis", new Regex(@"<[^>]*\son[a-z]+\s*=", RegexOptions.IgnoreCase)),
    };

    /// <summary>
    /// Punt 2 van het voorstel: elke ingebedde bron van de plugin (alle manifestbronnen van de assembly, dus ook een bron die er
    /// later bij komt) is een webbron die alleen <c>vraag(…)</c> gebruikt met een letterlijk eigen pad als begin; geen ander lid van
    /// ApiClient dan fetch en getUrl (elk precies één keer, in vraag), geen fetch(, XMLHttpRequest, $.ajax, &lt;script src&gt; of
    /// locatiewissel.
    /// </summary>
    [Fact]
    public void ElkeIngebeddeWebbron_VraagtAlleenEigenPaden()
    {
        var assembly = typeof(Plugin).Assembly;
        var namen = assembly.GetManifestResourceNames();
        Assert.NotEmpty(namen);
        Assert.Contains("Jellyfin.Plugin.JellyLeon.Configuration.configPage.html", namen);

        foreach (var naam in namen)
        {
            Assert.True(
                naam.EndsWith(".html", StringComparison.Ordinal) || naam.EndsWith(".js", StringComparison.Ordinal),
                "Onbekende soort ingebedde bron (alleen .html en .js zijn beoordeeld): " + naam);
            using var stroom = assembly.GetManifestResourceStream(naam)!;
            using var lezer = new StreamReader(stroom);
            var fouten = Beoordeel(lezer.ReadToEnd());
            Assert.True(fouten.Count == 0, naam + ":\n" + string.Join("\n", fouten));
        }
    }

    /// <summary>
    /// Punt 1 van het voorstel: vraag() is fail-closed. De eerste opdracht van vraag() weigert elk pad buiten media/v1/ en
    /// connector/v1/ (en elke andere methode) vóór ApiClient.fetch. Het patroon wordt hier met de ECMAScript-regels van .NET
    /// beproefd; <c>tools/jelly-leon/tests/test_config_pagina.py</c> voert dezelfde code echt uit in Node.
    /// </summary>
    [Fact]
    public void Configuratiepagina_VraagWeigertElkAnderPadVoorApiClientFetch()
    {
        var pagina = Webbron("Jellyfin.Plugin.JellyLeon.Configuration.configPage.html");
        var patroon = new Regex("^" + Regex.Escape("            var EIGEN_PAD = /") + "(?<p>.+)/;$", RegexOptions.Multiline).Match(pagina);
        Assert.True(patroon.Success, "EIGEN_PAD ontbreekt");
        var eigenPad = new Regex(patroon.Groups["p"].Value, RegexOptions.ECMAScript);

        foreach (var goed in new[] { "media/v1/hub-link", "media/v1/hub-link/verify", "media/v1/modules", "media/v1/modules/devices", "connector/v1/propose" })
        {
            Assert.True(eigenPad.IsMatch(goed), "eigen pad geweigerd: " + goed);
        }

        foreach (var fout in new[]
        {
            "UserPlayedItems/bibliotheek-A", "Items", "/media/v1/hub-link", "media/v1/", "media/v1", "media/v10/x", "mediax/v1/x",
            "media/v1/../UserPlayedItems/x", "media/v1/./x", "media/v1/%2e%2e/UserPlayedItems/x", "media/v1/x/..%2fUserPlayedItems",
            "media/v1\\..\\UserPlayedItems", "media/v1/x?userId=y", "media/v1/x#y", "media/v1/x/", "media/v1//x", "MEDIA/v1/x",
            "http://elders/media/v1/x", "//elders/media/v1/x", "media/v1/x y", string.Empty,
        })
        {
            Assert.False(eigenPad.IsMatch(fout), "vreemd pad toegestaan: " + fout);
        }

        Assert.Contains("            var METHODEN = ['GET', 'POST', 'PUT', 'DELETE'];\n", pagina, StringComparison.Ordinal);
        var begin = pagina.IndexOf("            function vraag(methode, pad, body, ifMatch) {\n", StringComparison.Ordinal);
        Assert.True(begin >= 0, "vraag() ontbreekt");
        var romp = pagina[begin..];
        var eersteOpdracht = romp.Split('\n')[1];
        Assert.Equal(
            "                if (typeof pad !== 'string' || !EIGEN_PAD.test(pad) || METHODEN.indexOf(methode) < 0) { throw new Error('Geweigerd: geen eigen pad van Jelly Leon.'); }",
            eersteOpdracht);
        Assert.Equal(2, Regex.Count(pagina, @"\bEIGEN_PAD\b"));
        Assert.Equal(2, Regex.Count(pagina, @"\bMETHODEN\b"));
    }

    /// <summary>
    /// Een pluginantwoord met een 3xx-status wordt geweigerd vóór er iets geschreven is (een browser volgt 301, 302, 307 en 308
    /// bij DELETE met dezelfde methode en hetzelfde token). Een gewoon antwoord gaat door.
    /// </summary>
    [Theory]
    [InlineData(301)]
    [InlineData(302)]
    [InlineData(303)]
    [InlineData(307)]
    [InlineData(308)]
    public async Task JlResult_WeigertEen3xxStatus(int status)
    {
        var http = new DefaultHttpContext();
        http.Response.Body = new MemoryStream();
        var context = new ActionContext(http, new RouteData(), new Microsoft.AspNetCore.Mvc.Abstractions.ActionDescriptor());

        await Assert.ThrowsAsync<InvalidOperationException>(() => new JlResult(status, "{}").ExecuteResultAsync(context));
        Assert.Equal(200, http.Response.StatusCode);
        Assert.Equal(0, http.Response.Body.Length);
        Assert.Empty(http.Response.Headers);

        var gewoon = new DefaultHttpContext();
        gewoon.Response.Body = new MemoryStream();
        await new JlResult(204, (string?)null).ExecuteResultAsync(new ActionContext(gewoon, new RouteData(), new Microsoft.AspNetCore.Mvc.Abstractions.ActionDescriptor()));
        Assert.Equal(204, gewoon.Response.StatusCode);
    }

    /// <summary>De afwijkingen van één webbron; leeg = in orde.</summary>
    internal static List<string> Beoordeel(string bron)
    {
        var fouten = new List<string>();
        foreach (var (naam, patroon) in _verboden)
        {
            foreach (Match raak in patroon.Matches(bron))
            {
                fouten.Add(naam + ": '" + raak.Value + "' op regel " + Regelnummer(bron, raak.Index));
            }
        }

        // fetch alleen als ApiClient.fetch; ApiClient alleen met fetch en getUrl, elk precies één keer, in vraag().
        foreach (Match raak in Regex.Matches(bron, @"\bfetch\s*\("))
        {
            if (raak.Index < "ApiClient.".Length || bron.Substring(raak.Index - "ApiClient.".Length, "ApiClient.".Length) != "ApiClient.")
            {
                fouten.Add("fetch buiten ApiClient.fetch op regel " + Regelnummer(bron, raak.Index));
            }
        }

        foreach (Match raak in Regex.Matches(bron, @"\bApiClient\b(?!\.(fetch|getUrl)\()"))
        {
            fouten.Add("ander gebruik van ApiClient op regel " + Regelnummer(bron, raak.Index));
        }

        var vraag = bron.IndexOf("function vraag(", StringComparison.Ordinal);
        var naVraag = vraag < 0 ? -1 : bron.IndexOf("\n            function ", vraag, StringComparison.Ordinal);
        foreach (var lid in new[] { "ApiClient.fetch(", "ApiClient.getUrl(" })
        {
            var plekken = Regex.Matches(bron, Regex.Escape(lid)).Select(m => m.Index).ToList();
            if (plekken.Count > 0 && (plekken.Count != 1 || vraag < 0 || plekken[0] < vraag || (naVraag >= 0 && plekken[0] > naVraag)))
            {
                fouten.Add(lid + " hoort precies één keer in vraag() te staan (gevonden: " + plekken.Count + ")");
            }
        }

        // Elke aanroep van vraag(): een vaste methode en een pad dat letterlijk met een eigen pad begint.
        foreach (Match raak in Regex.Matches(bron, @"\bvraag\s*\("))
        {
            var ervoor = bron[..raak.Index].TrimEnd();
            if (ervoor.EndsWith("function", StringComparison.Ordinal))
            {
                continue;
            }

            if (!Regex.IsMatch(bron[raak.Index..], @"^vraag\(\s*'(GET|POST|PUT|DELETE)'\s*,\s*'(media|connector)/v1/[a-z0-9-]+(/[a-z0-9-]*)*'"))
            {
                fouten.Add("vraag() zonder letterlijk eigen pad op regel " + Regelnummer(bron, raak.Index));
            }
        }

        return fouten;
    }

    private static int Regelnummer(string bron, int index) => bron[..index].Count(c => c == '\n') + 1;

    private static string Webbron(string naam)
    {
        using var stroom = typeof(Plugin).Assembly.GetManifestResourceStream(naam)!;
        using var lezer = new StreamReader(stroom);
        return lezer.ReadToEnd().Replace("\r\n", "\n", StringComparison.Ordinal);
    }
}
