using System;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.JellyLeon.Configuration;

namespace Jellyfin.Plugin.JellyLeon.Core.Modules;

/// <summary>De schakelaars per module. Standaard staat elke module uit.</summary>
internal interface IModuleSwitches
{
    /// <summary>Gets de ETag van de huidige stand van alle schakelaars.</summary>
    string Etag { get; }

    bool IsAan(string slug);

    void Zet(string slug, bool aan);
}

/// <summary>Schakelaars uit de pluginconfiguratie (alleen aan/uit; nooit een geheim).</summary>
internal sealed class PluginModuleSwitches : IModuleSwitches
{
    private static PluginConfiguration Config => Plugin.Instance?.Configuration ?? new PluginConfiguration();

    public string Etag => BerekenEtag(Config);

    public static string BerekenEtag(PluginConfiguration config)
    {
        var stand = string.Join(';', config.Schakelaars().Select(s => s.Slug + "=" + (s.Schakelaar.Enabled ? "1" : "0")));
        return "\"" + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(stand)).AsSpan(0, 8)) + "\"";
    }

    public bool IsAan(string slug) => Config.Schakelaars().Any(s => s.Slug == slug && s.Schakelaar.Enabled);

    public void Zet(string slug, bool aan)
    {
        var plugin = Plugin.Instance ?? throw new InvalidOperationException("De plugin is nog niet geladen.");
        plugin.Configuration.Schakelaars().First(s => s.Slug == slug).Schakelaar.Enabled = aan;
        plugin.SaveConfiguration();
    }
}
