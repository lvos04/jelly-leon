using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.JellyLeon.Configuration;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

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
    private readonly PluginOpslag _opslag;

    public PluginModuleSwitches(PluginOpslag opslag)
    {
        _opslag = opslag;
    }

    /// <summary>
    /// De configuratie, of null als het bestand of zijn map onveilig is (deel 1f, B1 optie A3: vóór elke lezing opnieuw
    /// getoetst; de server leest dat bestand en schrijft er bij een mislukte lezing een nieuw in, ook door een koppeling).
    /// Een fout bij het lezen of het opslaan door de server geeft ook null: nooit een ruwe fout in een gebeurtenis.
    /// </summary>
    private PluginConfiguration? Config
    {
        get
        {
            var plugin = Plugin.Instance;
            if (plugin is null)
            {
                return new PluginConfiguration();
            }

            try
            {
                JlPaths.EisVeiligConfiguratiebestand(_opslag.ConfiguratieBestand);
                return plugin.Configuration;
            }
            catch (Exception fout) when (fout is IOException or UnauthorizedAccessException or PlatformNotSupportedException)
            {
                return null;
            }
        }
    }

    public string Etag => _opslag.Beschikbaar ? BerekenEtag(Config ?? throw Fouten.OpslagOnbeschikbaar()) : "\"storage-disabled\"";

    public static string BerekenEtag(PluginConfiguration config)
    {
        var stand = string.Join(';', config.Schakelaars().Select(s => s.Slug + "=" + (s.Schakelaar.Enabled ? "1" : "0")));
        return "\"" + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(stand)).AsSpan(0, 8)) + "\"";
    }

    public bool IsAan(string slug) => _opslag.Beschikbaar && Config is { } config && config.Schakelaars().Any(s => s.Slug == slug && s.Schakelaar.Enabled);

    public void Zet(string slug, bool aan)
    {
        _ = _opslag.Paden;
        var plugin = Plugin.Instance ?? throw new InvalidOperationException("De plugin is nog niet geladen.");
        var config = Config ?? throw Fouten.OpslagOnbeschikbaar();
        config.Schakelaars().First(s => s.Slug == slug).Schakelaar.Enabled = aan;
        try
        {
            JlPaths.EisVeiligConfiguratiebestand(_opslag.ConfiguratieBestand);
            plugin.SaveConfiguration();
        }
        catch (Exception fout) when (fout is IOException or UnauthorizedAccessException or PlatformNotSupportedException)
        {
            throw Fouten.OpslagOnbeschikbaar();
        }
    }
}
