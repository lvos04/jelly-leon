using System.IO;

namespace Jellyfin.Plugin.JellyLeon.Core.Storage;

/// <summary>
/// De enige schrijfplekken van de pluginlaag (plan §10.9): <c>&lt;data&gt;/jelly-leon/**</c> en
/// <c>&lt;cache&gt;/jelly-leon/**</c>. Nooit een mediamap, nooit de database van de server.
/// </summary>
internal sealed class JlPaths
{
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
    public string RunDir => Directory.Exists("/run/jelly-leon") ? "/run/jelly-leon" : Path.Combine(CacheRoot, "run");

    public string ModuleDir(string slug) => Path.Combine(DataRoot, slug);

    public string ModuleDb(string slug) => Path.Combine(ModuleDir(slug), slug + ".db");

    /// <summary>Is <paramref name="pad"/> een toegestane schrijfplek van de pluginlaag?</summary>
    public bool MagSchrijven(string pad)
    {
        var vol = Path.GetFullPath(pad);
        return Binnen(vol, DataRoot) || Binnen(vol, CacheRoot) || Binnen(vol, "/run/jelly-leon");
    }

    private static bool Binnen(string pad, string wortel)
    {
        var w = Path.GetFullPath(wortel).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return pad.StartsWith(w, System.StringComparison.Ordinal);
    }
}
