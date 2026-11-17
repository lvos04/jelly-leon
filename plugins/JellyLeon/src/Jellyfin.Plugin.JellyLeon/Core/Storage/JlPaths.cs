using System;
using System.IO;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Core.Storage;

/// <summary>
/// De enige schrijfplekken van de pluginlaag (plan §10.9): <c>&lt;data&gt;/jelly-leon/**</c> en
/// <c>&lt;cache&gt;/jelly-leon/**</c>. Nooit een mediamap, nooit de database van de server.
/// </summary>
internal sealed class JlPaths
{
    /// <summary>Zoveel symbolische koppelingen volgt het pad hooguit (zoals de kernel); daarboven is het geen eigen plek.</summary>
    private const int MaxKoppelingen = 40;

    private const string RunWortel = "/run/jelly-leon";

    public JlPaths(string dataPath, string cachePath)
    {
        DataRoot = Path.Combine(dataPath, "jelly-leon");
        CacheRoot = Path.Combine(cachePath, "jelly-leon");
    }

    public string DataRoot { get; }

    public string CacheRoot { get; }

    public string SecretsDir => Path.Combine(DataRoot, "secrets");

    public string CoreDb => Path.Combine(DataRoot, "core", "core.db");

    /// <summary>Map van de unix-socket van de analysewerker: /run/jelly-leon als die bestaat, anders onder de cache.</summary>
    public string RunDir => Directory.Exists(RunWortel) ? RunWortel : Path.Combine(CacheRoot, "run");

    public string ModuleDir(string slug) => Path.Combine(DataRoot, slug);

    public string ModuleDb(string slug) => Path.Combine(ModuleDir(slug), slug + ".db");

    /// <summary>
    /// Is <paramref name="pad"/> een toegestane schrijfplek van de pluginlaag? Twee eisen (HARDE EIS, ADR-0032): het pad
    /// zoals het er staat ligt in een eigen map, en het echte pad ook. Het echte pad volgt elke symbolische koppeling
    /// zoals het besturingssysteem dat doet: het bestand zelf en elke bovenliggende map, relatief of in een keten, en
    /// <c>..</c> na het volgen. Een eigen map die zelf een koppeling is, telt niet als eigen plek.
    /// </summary>
    public bool MagSchrijven(string pad)
    {
        var wortels = new[] { DataRoot, CacheRoot, RunWortel };
        var vol = Path.GetFullPath(pad);
        if (!wortels.Any(w => Binnen(vol, w)))
        {
            return false;
        }

        // Niet de tekstueel opgeschoonde vorm volgen: na een koppeling betekent ".." de ouder van het doel.
        var echt = EchtPad(Path.IsPathRooted(pad) ? pad : Path.Combine(Directory.GetCurrentDirectory(), pad));
        return echt is not null && wortels.Any(w => EchteWortel(w) is { } e && Binnen(echt, e));
    }

    /// <summary>
    /// Het echte pad: elke bestaande symbolische koppeling in <paramref name="pad"/> (absoluut) is vervangen door haar
    /// doel, <c>.</c> is weggelaten en <c>..</c> gaat naar de ouder van het echte pad tot dan toe. Wat (nog) niet bestaat,
    /// blijft zoals het er staat. Null bij meer dan <see cref="MaxKoppelingen"/> koppelingen (een lus).
    /// </summary>
    internal static string? EchtPad(string pad)
    {
        var stappen = 0;
        return Volg(pad, ref stappen);
    }

    private static string? Volg(string pad, ref int stappen)
    {
        var wortel = Path.GetPathRoot(pad);
        if (string.IsNullOrEmpty(wortel))
        {
            return null;
        }

        var huidig = wortel;
        foreach (var deel in pad[wortel.Length..].Split([Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar], StringSplitOptions.RemoveEmptyEntries))
        {
            if (deel == ".")
            {
                continue;
            }

            if (deel == "..")
            {
                huidig = Path.GetDirectoryName(huidig) ?? wortel;
                continue;
            }

            var volgende = Path.Combine(huidig, deel);
            var doel = new FileInfo(volgende).LinkTarget;
            if (doel is null)
            {
                huidig = volgende;
                continue;
            }

            if (++stappen > MaxKoppelingen)
            {
                return null;
            }

            // Een relatief doel geldt vanaf de map waarin de koppeling staat.
            var opgelost = Volg(Path.IsPathRooted(doel) ? doel : Path.Combine(huidig, doel), ref stappen);
            if (opgelost is null)
            {
                return null;
            }

            huidig = opgelost;
        }

        return huidig;
    }

    /// <summary>Het echte pad van een eigen map; null als de eigen map zelf een koppeling is of niet te volgen is.</summary>
    private static string? EchteWortel(string wortel)
    {
        var vol = Path.GetFullPath(wortel).TrimEnd(Path.DirectorySeparatorChar);
        if (new FileInfo(vol).LinkTarget is not null)
        {
            return null;
        }

        var ouder = Path.GetDirectoryName(vol);
        if (ouder is null)
        {
            return vol;
        }

        var echteOuder = EchtPad(ouder);
        return echteOuder is null ? null : Path.Combine(echteOuder, Path.GetFileName(vol));
    }

    private static bool Binnen(string pad, string wortel)
    {
        var w = Path.GetFullPath(wortel).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return pad.StartsWith(w, StringComparison.Ordinal);
    }
}
