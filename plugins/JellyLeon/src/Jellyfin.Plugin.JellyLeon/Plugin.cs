using System;
using Jellyfin.Plugin.JellyLeon.Configuration;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Serialization;

namespace Jellyfin.Plugin.JellyLeon;

/// <summary>
/// Jelly Leon-basisplugin: levert versie- en compatibiliteitsinformatie van de fork (B03-001).
/// Wijzigt niets aan de technische identiteit van de server (ADR-0003).
/// </summary>
public class Plugin : BasePlugin<PluginConfiguration>
{
    /// <summary>
    /// Vaste plugin-ID (nooit wijzigen: Jellyfin bewaart configuratie per ID).
    /// </summary>
    public static readonly Guid PluginId = new("6a0c5f2e-3b9d-4c71-9e0a-4f1d2b8c7e51");

    /// <summary>
    /// Initializes a new instance of the <see cref="Plugin"/> class.
    /// </summary>
    /// <param name="applicationPaths">Paden van de server.</param>
    /// <param name="xmlSerializer">XML-serializer voor de pluginconfiguratie.</param>
    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
    }

    /// <inheritdoc />
    public override string Name => "Jelly Leon";

    /// <inheritdoc />
    public override Guid Id => PluginId;

    /// <inheritdoc />
    public override string Description =>
        "Jelly Leon-uitbreidingen op Jellyfin (GPL-2.0). Gebaseerd op Jellyfin; de technische identiteit blijft Jellyfin.";
}
