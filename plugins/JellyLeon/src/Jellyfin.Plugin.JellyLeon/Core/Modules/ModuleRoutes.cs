using System;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Core.Modules;

/// <summary>De gedeelde afhandeling van de vaste routes die elke module heeft (status, instellingen, export en wissen).</summary>
internal static class ModuleRoutes
{
    public static JlResult Status(ModuleBasis module, DateTimeOffset nu) => JlResult.Ok(module.Status(nu));

    public static JlResult LeesInstellingen(ModuleBasis module)
    {
        var (waarde, etag) = module.LeesInstellingen();
        return JlResult.Ok(waarde, etag);
    }

    public static JlResult SchrijfInstellingen(ModuleBasis module, JlContext context)
    {
        var lezer = new BodyLezer(context.Body);
        var dagen = lezer.Geheel("bewaar_dagen", true, 1, 365);
        lezer.Klaar();
        var (waarde, etag) = module.SchrijfInstellingen(dagen!.Value, context.IfMatch!);
        return JlResult.Ok((JsonNode)waarde, etag);
    }

    public static JlResult Export(ModuleBasis module, HttpContext http, TimeProvider klok)
    {
        var (bestand, sha256) = module.Gegevensbeheer.MaakExport(klok);
        return JlResult.Download(http.Response, bestand, sha256);
    }

    public static JlResult Wis(ModuleBasis module, HttpContext http, TimeProvider klok)
    {
        var lezer = new BodyLezer(JlContext.Van(http).Body);
        var sha256 = lezer.Tekst("export_sha256", true, 64);
        if (sha256 is not null && (sha256.Length != 64 || !sha256.All(char.IsAsciiHexDigitLower)))
        {
            lezer.Fout("export_sha256", "sha256", "Verwacht 64 hexadecimale tekens in kleine letters.");
        }

        var dryRun = true;
        if (http.Request.Query.TryGetValue("dry_run", out var waarde) && !bool.TryParse(waarde.ToString(), out dryRun))
        {
            lezer.Fout("dry_run", "boolean", "Verwacht true of false.");
        }

        lezer.Klaar();
        var resultaat = module.Gegevensbeheer.Wis(sha256!, dryRun, klok);
        if (!dryRun)
        {
            http.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("Jellyfin.Plugin.JellyLeon")
                .LogInformation("Jelly Leon: beheerder heeft de gegevens van module {Module} gewist.", module.Slug);
        }

        return JlResult.Ok(resultaat);
    }
}
