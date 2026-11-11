using System;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>
/// Koppelt een actie aan haar regel in de routetabel en laat de ene pipeline lopen. Elke actie van de plugin draagt
/// dit attribuut (een test bewaakt dat); fouten worden altijd een antwoord uit de foutcatalogus.
/// </summary>
[AttributeUsage(AttributeTargets.Method)]
public sealed class JlRouteAttribute : Attribute, IAsyncActionFilter
{
    /// <summary>Initializes a new instance of the <see cref="JlRouteAttribute"/> class.</summary>
    /// <param name="id">De ID van de route in de routetabel.</param>
    public JlRouteAttribute(string id)
    {
        Id = id;
    }

    /// <summary>Gets de ID van de route in de routetabel.</summary>
    public string Id { get; }

    /// <inheritdoc />
    public async Task OnActionExecutionAsync(ActionExecutingContext context, ActionExecutionDelegate next)
    {
        var http = context.HttpContext;
        var traceId = Guid.NewGuid().ToString();
        var pipeline = http.RequestServices.GetRequiredService<JlPipeline>();
        JlContext jl;
        try
        {
            jl = await pipeline.BereidVoorAsync(http, RouteTable.Zoek(Id), traceId).ConfigureAwait(false);
        }
        catch (JlException fout)
        {
            context.Result = JlResult.Fout(fout, traceId);
            return;
        }

        if (jl.Herhaling is not null)
        {
            context.Result = jl.Herhaling;
            return;
        }

        http.Items[JlContext.Sleutel] = jl;
        var uitgevoerd = await next().ConfigureAwait(false);
        if (uitgevoerd.Exception is JlException actiefout)
        {
            uitgevoerd.ExceptionHandled = true;
            uitgevoerd.Result = JlResult.Fout(actiefout, traceId);
        }
        else if (uitgevoerd.Exception is not null && !uitgevoerd.ExceptionHandled)
        {
            http.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("Jellyfin.Plugin.JellyLeon")
                .LogError("Jelly Leon: onverwachte fout in route {Route} ({Soort}); trace {Trace}.", Id, uitgevoerd.Exception.GetType().Name, traceId);
            uitgevoerd.ExceptionHandled = true;
            uitgevoerd.Result = JlResult.Fout(Fouten.AfhankelijkheidOnbeschikbaar("jelly-leon"), traceId);
        }

        if (uitgevoerd.Result is JlResult antwoord)
        {
            try
            {
                pipeline.Rond(jl, antwoord);
            }
            catch (JlException fout)
            {
                uitgevoerd.Result = JlResult.Fout(fout, traceId);
            }
        }
    }
}
