using System;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>
/// Koppelt een actie aan haar regel in de routetabel en laat de ene pipeline lopen. Elke actie van de plugin draagt
/// dit attribuut (een test bewaakt dat); fouten worden altijd een antwoord uit de foutcatalogus. Het zet ook de
/// <see cref="DoorstuurWacht"/> op het verzoek: een antwoord dat de browser zou doorsturen (3xx of Location), van welk type
/// resultaat ook, wordt bij het draaien de vaste fout 503 (R-HARDE-EIS-20).
/// </summary>
[AttributeUsage(AttributeTargets.Method)]
public sealed class JlRouteAttribute : Attribute, IAsyncActionFilter, IAsyncAlwaysRunResultFilter
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
        DoorstuurWacht.Bewaak(http);
        var traceId = Guid.NewGuid().ToString();
        // Controllers laden hun diensten pas in de actie. Deze controle raakt geen opslag, ook geen sleutelpin.
        if (http.RequestServices.GetService<PluginOpslag>() is { Beschikbaar: false } opslag)
        {
            var route = RouteTable.Zoek(Id);
            try
            {
                if (route.Auth == JlAuth.SessieBeheerder)
                {
                    var wie = await http.RequestServices.GetRequiredService<ISessionAuthenticator>().AuthenticeerAsync(http.Request).ConfigureAwait(false);
                    if (wie.IsKid || !wie.IsBeheerder)
                    {
                        throw Fouten.Verboden(wie.IsKid ? "kid_profile" : "admin_required");
                    }
                }

                throw opslag.Fout(route.Auth == JlAuth.Hub, http.RequestServices.GetRequiredService<TimeProvider>().GetUtcNow());
            }
            catch (JlException fout)
            {
                context.Result = JlResult.Fout(fout, traceId);
                return;
            }
        }

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
        if (DoorstuurWacht.IsGeweigerd(http))
        {
            // De actie schreef zelf een doorsturend antwoord en de wacht hield het tegen (503 zonder body, en de schrijfactie
            // gaf daarom een fout): geen tweede antwoord schrijven, het blijft bij de vaste fout.
            uitgevoerd.ExceptionHandled = true;
            uitgevoerd.Result = new EmptyResult();
            try
            {
                // Een serverfout geeft de Idempotency-Key weer vrij.
                pipeline.Rond(jl, JlResult.Fout(Fouten.AfhankelijkheidOnbeschikbaar("jelly-leon"), traceId));
            }
            catch (JlException)
            {
                // Het antwoord ligt al vast (503); een fout bij het vrijgeven verandert dat niet.
            }

            return;
        }

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

    /// <inheritdoc />
    public async Task OnResultExecutionAsync(ResultExecutingContext context, ResultExecutionDelegate next)
    {
        var uitgevoerd = await next().ConfigureAwait(false);
        if (DoorstuurWacht.IsGeweigerd(context.HttpContext))
        {
            // Het resultaat schreef een doorsturend antwoord met body; de wacht hield het tegen (503 zonder body) en de
            // schrijfactie gaf daarom een fout. Die fout hoort bij de weigering.
            uitgevoerd.ExceptionHandled = true;
        }
        else if (await DoorstuurWacht.WeigerAsync(context.HttpContext).ConfigureAwait(false) && uitgevoerd.Exception is not null)
        {
            // Een fout bij een doorsturend antwoord zonder body: het antwoord is nu de vaste fout uit de foutcatalogus.
            uitgevoerd.ExceptionHandled = true;
        }
    }
}
