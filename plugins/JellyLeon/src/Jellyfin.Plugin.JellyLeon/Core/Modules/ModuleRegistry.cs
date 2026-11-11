using System;
using System.Collections.Generic;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Core.Modules;

/// <summary>Alle modules van de plugin. Een dubbele slug, itemtype, eventtype of jobtype is een bouwfout.</summary>
internal sealed class ModuleRegistry
{
    private readonly IModuleSwitches _schakelaars;

    public ModuleRegistry(IEnumerable<IJellyLeonModule> modules, IModuleSwitches schakelaars)
    {
        Alle = modules.OrderBy(m => m.Slug, StringComparer.Ordinal).ToList();
        _schakelaars = schakelaars;
        EisUniek(Alle.Select(m => m.Slug), "slug");
        EisUniek(Alle.SelectMany(m => m.ItemTypes), "itemtype");
        EisUniek(Alle.SelectMany(m => m.EventTypes), "eventtype");
        EisUniek(Alle.SelectMany(m => m.JobTypes), "jobtype");
    }

    public IReadOnlyList<IJellyLeonModule> Alle { get; }

    public IEnumerable<IJellyLeonModule> Actief => Alle.Where(m => _schakelaars.IsAan(m.Slug));

    public IJellyLeonModule? Zoek(string slug) => Alle.FirstOrDefault(m => m.Slug == slug);

    public bool IsAan(string slug) => Zoek(slug) is not null && _schakelaars.IsAan(slug);

    private static void EisUniek(IEnumerable<string> waarden, string soort)
    {
        var dubbel = waarden.GroupBy(w => w, StringComparer.Ordinal).FirstOrDefault(g => g.Count() > 1);
        if (dubbel is not null)
        {
            throw new InvalidOperationException($"Dubbel {soort} in de modules: {dubbel.Key}");
        }
    }
}
