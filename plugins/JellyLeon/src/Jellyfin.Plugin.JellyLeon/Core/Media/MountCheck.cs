using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

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

    public static Uitkomst BeoordeelBibliotheek(string pad)
    {
        try
        {
            var echt = Path.IsPathFullyQualified(pad) && Directory.Exists(pad) ? JlPaths.EchtPad(pad) : null;
            return echt is null ? Uitkomst.Onbekend : LeesMountinfo(echt, "/proc/self/mountinfo", inclusiefKinderen: true);
        }
        catch (Exception fout) when (fout is IOException or UnauthorizedAccessException)
        {
            return Uitkomst.Onbekend;
        }
    }

    public static Uitkomst Beoordeel(string pad, string mountinfoPad = "/proc/self/mountinfo") =>
        LeesMountinfo(pad, mountinfoPad, inclusiefKinderen: false);

    private static Uitkomst LeesMountinfo(string pad, string mountinfoPad, bool inclusiefKinderen)
    {
        try
        {
            return File.Exists(mountinfoPad) ? Beoordeel(pad, File.ReadAllLines(mountinfoPad), inclusiefKinderen) : Uitkomst.Onbekend;
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

    public static Uitkomst Beoordeel(string pad, IEnumerable<string> mountinfo, bool inclusiefKinderen = false)
    {
        if (string.IsNullOrWhiteSpace(pad) || !Path.IsPathFullyQualified(pad) || pad.Contains('\0', StringComparison.Ordinal))
        {
            return Uitkomst.Onbekend;
        }

        var doel = Path.GetFullPath(pad).TrimEnd('/') + "/";
        var uitkomst = Uitkomst.Onbekend;
        var kinderen = Uitkomst.AlleenLezen;
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

            var punt = velden[4].Replace("\\040", " ", StringComparison.Ordinal)
                .Replace("\\011", "\t", StringComparison.Ordinal).Replace("\\012", "\n", StringComparison.Ordinal)
                .Replace("\\134", "\\", StringComparison.Ordinal).TrimEnd('/') + "/";
            var opties = velden[5].Split(',');
            var superopties = velden[streep + 3].Split(',');
            var stand = opties.Contains("ro") || superopties.Contains("ro") ? Uitkomst.AlleenLezen :
                opties.Contains("rw") && superopties.Contains("rw") ? Uitkomst.Schrijfbaar : Uitkomst.Onbekend;
            if (doel.StartsWith(punt, StringComparison.Ordinal) && punt.Length >= besteLengte)
            {
                besteLengte = punt.Length;
                uitkomst = stand;
            }
            else if (inclusiefKinderen && punt.StartsWith(doel, StringComparison.Ordinal) && stand != Uitkomst.AlleenLezen)
            {
                kinderen = kinderen == Uitkomst.Schrijfbaar ? kinderen : stand;
            }
        }

        if (uitkomst == Uitkomst.Schrijfbaar || kinderen == Uitkomst.Schrijfbaar)
        {
            return Uitkomst.Schrijfbaar;
        }

        return uitkomst == Uitkomst.AlleenLezen && kinderen == Uitkomst.AlleenLezen ? Uitkomst.AlleenLezen : Uitkomst.Onbekend;
    }
}
