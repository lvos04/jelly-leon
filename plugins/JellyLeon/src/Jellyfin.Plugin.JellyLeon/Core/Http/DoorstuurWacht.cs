using System;
using System.Globalization;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Net.Http.Headers;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>
/// Fail-closed bij het draaien (R-HARDE-EIS-20, S-G1-17 herstelronde 10, ADR-0032): een antwoord op een pluginpad stuurt de
/// browser nooit door. Een browser volgt een 3xx met de kop Location met dezelfde methode en hetzelfde token naar elke route van
/// de server (bijvoorbeeld <c>DELETE /UserPlayedItems/&lt;bibliotheek&gt;</c>). De analyzer ziet alleen een constante status en
/// een kopnaam als constante; een status uit een variabele of een kopnaam die pas bij het draaien ontstaat, ziet hij niet. Deze
/// wacht kijkt daarom naar het antwoord zelf, vlak voordat de koppen vertrekken (<c>Response.OnStarting</c>), ongeacht het type
/// resultaat: een status van 300 tot en met 399 of een kop Location wordt de vaste fout 503 <c>dependency_unavailable</c>, zonder
/// Location en zonder de body van de actie (als JSON uit de foutcatalogus als de actie zelf nog niets schreef, anders zonder body). <see cref="JlRouteAttribute"/> zet de wacht op elke eigen actie,
/// <see cref="JlStartupFilterSpike"/> (als die aan staat) op elk pluginpad.
/// </summary>
internal static class DoorstuurWacht
{
    /// <summary>Sleutel in <c>HttpContext.Items</c> van de wacht van dit verzoek.</summary>
    internal const string Sleutel = "JellyLeon.DoorstuurWacht";

    /// <summary>Zet de wacht op dit verzoek (één keer per verzoek, ook als de spike en het attribuut allebei lopen).</summary>
    public static void Bewaak(HttpContext http)
    {
        if (http.Items.ContainsKey(Sleutel))
        {
            return;
        }

        http.Items[Sleutel] = new Stand();
        http.Response.OnStarting(
            static staat =>
            {
                Controleer((HttpContext)staat);
                return Task.CompletedTask;
            },
            http);
    }

    /// <summary>Waar als de wacht van dit verzoek een antwoord heeft tegengehouden.</summary>
    public static bool IsGeweigerd(HttpContext http) => http.Items.TryGetValue(Sleutel, out var stand) && stand is Stand { Geweigerd: true };

    /// <summary>Waar als dit antwoord de browser zou doorsturen: een status van 300 tot en met 399, of een kop Location.</summary>
    public static bool StuurtDoor(HttpResponse antwoord) =>
        antwoord.StatusCode is >= 300 and <= 399 || antwoord.Headers.ContainsKey(HeaderNames.Location);

    /// <summary>
    /// Na afloop van een actie of middleware: is het antwoord nog niet begonnen en stuurt het door, dan schrijft dit de vaste fout
    /// uit de foutcatalogus (503 <c>dependency_unavailable</c> als JSON). Waar als dat gebeurde. Heeft de wacht het antwoord al in
    /// <c>OnStarting</c> tegengehouden (de actie schreef een body), dan schrijft dit niets meer: het antwoord blijft 503 zonder
    /// body, want Kestrel telt de geweigerde bytes van de actie al mee en neemt geen tweede body aan.
    /// </summary>
    public static async Task<bool> WeigerAsync(HttpContext http)
    {
        var antwoord = http.Response;
        if (antwoord.HasStarted || IsGeweigerd(http) || !StuurtDoor(antwoord))
        {
            return false;
        }

        Meld(http, antwoord.StatusCode);
        antwoord.Clear();
        await JlResult.Fout(Fout(), Guid.NewGuid().ToString()).ExecuteResultAsync(new ActionContext { HttpContext = http }).ConfigureAwait(false);
        return true;
    }

    private static JlException Fout() => Fouten.AfhankelijkheidOnbeschikbaar("jelly-leon");

    /// <summary>
    /// De controle in <c>Response.OnStarting</c>: de koppen zijn nog niet verstuurd. Stuurt het antwoord door, dan wordt het de
    /// vaste fout: status 503, geen kop Location, <c>Cache-Control: no-store</c> en Content-Length 0, zodat de body die de actie
    /// daarna schrijft niet meegaat (Kestrel weigert die schrijfactie met een <see cref="InvalidOperationException"/> voordat de
    /// koppen vertrekken; het attribuut en de spike vangen die op).
    /// </summary>
    private static void Controleer(HttpContext http)
    {
        var antwoord = http.Response;
        if (!StuurtDoor(antwoord))
        {
            return;
        }

        if (http.Items.TryGetValue(Sleutel, out var stand) && stand is Stand wacht)
        {
            wacht.Geweigerd = true;
        }

        Meld(http, antwoord.StatusCode);
        antwoord.Headers.Remove(HeaderNames.Location);
        antwoord.StatusCode = Fout().Status;
        antwoord.ContentLength = 0;
        antwoord.Headers["Cache-Control"] = "no-store";
    }

    private static void Meld(HttpContext http, int status) =>
        http.RequestServices?.GetService<ILoggerFactory>()?.CreateLogger("Jellyfin.Plugin.JellyLeon")
            .LogError("Jelly Leon: een antwoord op een pluginpad zou de browser doorsturen (status {Status}); geweigerd met 503.", status.ToString(CultureInfo.InvariantCulture));

    private sealed class Stand
    {
        public bool Geweigerd { get; set; }
    }
}
