using System;
using System.Collections.Generic;
using System.Linq;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using MediaBrowser.Controller.Library;

namespace Jellyfin.Plugin.JellyLeon.Core;

/// <summary>De mediamappen volgens de officiële bibliotheek-API van de server (alleen lezen).</summary>
internal sealed class BibliotheekMappen : IMediaMappen
{
    private readonly ILibraryManager _bibliotheek;

    public BibliotheekMappen(ILibraryManager bibliotheek)
    {
        _bibliotheek = bibliotheek;
    }

    public IReadOnlyList<string> Paden()
    {
        try
        {
            return _bibliotheek.GetVirtualFolders()
                .SelectMany(m => m.Locations ?? [])
                .Where(p => !string.IsNullOrEmpty(p))
                .Distinct(StringComparer.Ordinal)
                .ToList();
        }
        catch (InvalidOperationException)
        {
            // De bibliotheek is nog niet klaar met opstarten: dan is de stand onbekend, niet "goed".
            return [];
        }
    }
}
