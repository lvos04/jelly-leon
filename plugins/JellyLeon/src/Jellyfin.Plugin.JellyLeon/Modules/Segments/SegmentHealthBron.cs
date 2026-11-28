using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Microsoft.Extensions.DependencyInjection;

namespace Jellyfin.Plugin.JellyLeon.Modules.Segments;

internal sealed class SegmentHealthBron(IServiceProvider diensten, IModuleSwitches schakelaars) : IHealthBron
{
    public IEnumerable<JsonObject> Checks(DateTimeOffset nu)
    {
        if (schakelaars.IsAan(SegmentsModule.ModuleSlug))
        {
            var status = diensten.GetRequiredService<SegmentDienst>().Status();
            yield return ConnectorService.Check("segments", status["health"]!.GetValue<string>(), nu,
                new JsonObject { ["reason"] = status["reason"]!.DeepClone() });
        }
    }
}
