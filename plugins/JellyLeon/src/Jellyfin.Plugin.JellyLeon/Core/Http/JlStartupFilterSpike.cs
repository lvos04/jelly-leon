using System;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>
/// Spike (B03-017, ADR-0033): een laag vóór routing en authenticatie die een verzoek van meer dan 1 MiB aan een
/// pluginroute met 413 weigert. Alleen actief met de omgevingsvariabele <c>JELLYLEON_SPIKE_STARTUPFILTER=1</c>;
/// standaard uit. De controle per route in <see cref="JlPipeline"/> blijft altijd staan, met of zonder deze laag.
/// Verzoeken buiten <c>/media/v1</c> en <c>/connector/v1</c> gaan ongewijzigd door. Op een pluginpad staat ook de
/// <see cref="DoorstuurWacht"/> (geen 3xx en geen Location, R-HARDE-EIS-20).
/// </summary>
internal sealed class JlStartupFilterSpike : IStartupFilter
{
    /// <summary>Naam van de omgevingsvariabele die de spike aanzet.</summary>
    public const string Schakelaar = "JELLYLEON_SPIKE_STARTUPFILTER";

    private static readonly PathString[] _voorvoegsels = ["/media/v1", "/connector/v1"];

    /// <summary>Alleen de exacte waarde "1" zet de spike aan; elke andere waarde (ook leeg) laat hem uit.</summary>
    public static bool IsAan(Func<string, string?> omgeving) => omgeving(Schakelaar) == "1";

    /// <inheritdoc />
    public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => app =>
    {
        app.Use(VoorAuthAsync);
        next(app);
    };

    /// <summary>
    /// De middleware zelf: 413 bij een te grote Content-Length op een pluginroute, anders ongewijzigd door. Op een pluginpad
    /// staat daarbij de <see cref="DoorstuurWacht"/> (R-HARDE-EIS-20): een antwoord met 3xx of Location wordt de vaste fout
    /// 503, ook als het niet uit een eigen actie komt. Verzoeken buiten de pluginpaden raakt de wacht niet.
    /// </summary>
    internal static async Task VoorAuthAsync(HttpContext http, RequestDelegate volgende)
    {
        if (!IsPluginPad(http.Request.Path))
        {
            await volgende(http).ConfigureAwait(false);
            return;
        }

        if (http.Request.ContentLength > Fouten.MaxBodyBytes)
        {
            var antwoord = JlResult.Fout(Fouten.TeGroot(), Guid.NewGuid().ToString());
            await antwoord.ExecuteResultAsync(new ActionContext { HttpContext = http }).ConfigureAwait(false);
            return;
        }

        DoorstuurWacht.Bewaak(http);
        try
        {
            await volgende(http).ConfigureAwait(false);
        }
        catch (InvalidOperationException) when (DoorstuurWacht.IsGeweigerd(http))
        {
            // De schrijfactie die de wacht tegenhield (503 met Content-Length 0): het blijft bij de vaste fout.
        }

        await DoorstuurWacht.WeigerAsync(http).ConfigureAwait(false);
    }

    private static bool IsPluginPad(PathString pad)
    {
        foreach (var voorvoegsel in _voorvoegsels)
        {
            if (pad.StartsWithSegments(voorvoegsel, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }
}
