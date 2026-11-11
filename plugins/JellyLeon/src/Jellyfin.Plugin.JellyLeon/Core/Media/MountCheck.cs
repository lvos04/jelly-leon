using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Core.Media;

/// <summary>
/// Controleert zonder proefschrijven of een mediamap alleen-lezen is gekoppeld (plan §10.9): de opties van de
/// dichtstbijzijnde koppeling in <c>/proc/self/mountinfo</c>. Onbekend is nooit "in orde".
/// </summary>
internal static class MountCheck
{
    public enum Uitkomst
    {
        /// <summary>De koppeling is alleen-lezen.</summary>
        AlleenLezen,

        /// <summary>De koppeling is schrijfbaar: geen batchmodule.</summary>
        Schrijfbaar,

        /// <summary>Niet vast te stellen.</summary>
        Onbekend,
    }

    public static Uitkomst Beoordeel(string pad, string mountinfoPad = "/proc/self/mountinfo")
    {
        try
        {
            return File.Exists(mountinfoPad) ? Beoordeel(pad, File.ReadAllLines(mountinfoPad)) : Uitkomst.Onbekend;
        }
        catch (IOException)
        {
            return Uitkomst.Onbekend;
        }
        catch (UnauthorizedAccessException)
        {
            return Uitkomst.Onbekend;
        }
    }

    public static Uitkomst Beoordeel(string pad, IEnumerable<string> mountinfo)
    {
        var doel = Path.GetFullPath(pad).TrimEnd('/') + "/";
        string? besteOpties = null;
        var besteLengte = -1;
        foreach (var regel in mountinfo)
        {
            // Velden: id ouder major:minor wortel koppelpunt opties [optioneel...] - fstype bron superopties
            var velden = regel.Split(' ');
            var streep = Array.IndexOf(velden, "-");
            if (velden.Length < 7 || streep < 6 || streep + 3 >= velden.Length)
            {
                continue;
            }

            var punt = velden[4].Replace("\\040", " ", StringComparison.Ordinal).TrimEnd('/') + "/";
            if (doel.StartsWith(punt, StringComparison.Ordinal) && punt.Length >= besteLengte)
            {
                besteLengte = punt.Length;
                besteOpties = velden[5] + "," + velden[streep + 3];
            }
        }

        if (besteOpties is null)
        {
            return Uitkomst.Onbekend;
        }

        return besteOpties.Split(',').Contains("ro") ? Uitkomst.AlleenLezen : Uitkomst.Schrijfbaar;
    }
}
