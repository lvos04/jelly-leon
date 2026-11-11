using System;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Http;

namespace Jellyfin.Plugin.JellyLeon.Core.Modules;

/// <summary>De gedeelde afhandeling van de vaste routes die elke module heeft (status en instellingen).</summary>
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
}
