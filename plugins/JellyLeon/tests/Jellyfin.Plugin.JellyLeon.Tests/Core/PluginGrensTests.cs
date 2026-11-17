using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using Jellyfin.Plugin.JellyLeon.Configuration;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Model.Serialization;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// Grenzen die de analyzer niet zelf ziet en die bij het draaien vast moeten liggen (S-G1-17 herstelronde 7, ADR-0032):
/// waar de server de pluginconfiguratie schrijft (R-HARDE-EIS-14a) en welke typen in de vrijgestelde namespaces staan
/// (herreview 6, nieuwe grens 1: de vrijstelling hangt af van de namespace in de broncode).
/// </summary>
public class PluginGrensTests
{
    /// <summary>
    /// De server schrijft de pluginconfiguratie naar <c>ConfigurationFilePath</c>, ook als hij hem alleen leest en dat
    /// faalt (LoadConfiguration roept dan SaveConfiguration aan). Dat pad moet het vaste bestand in de map van de
    /// pluginconfiguraties zijn: <c>Path.Combine(PluginConfigurationsPath, "Jellyfin.Plugin.JellyLeon.xml")</c>.
    /// </summary>
    [Fact]
    public void Configuratie_WordtAlleenInHetVasteBestandVanDePluginGeschreven()
    {
        var basis = Path.Combine(Path.GetTempPath(), "jl-pluginconfig-" + Guid.NewGuid().ToString("N"));
        var map = Path.Combine(basis, "configurations");
        try
        {
            var paden = new Mock<IApplicationPaths>();
            paden.SetupGet(p => p.PluginConfigurationsPath).Returns(map);
            paden.SetupGet(p => p.PluginsPath).Returns(Path.Combine(basis, "plugins"));
            paden.SetupGet(p => p.DataPath).Returns(Path.Combine(basis, "data"));
            var xml = new Mock<IXmlSerializer>(MockBehavior.Strict);
            xml.Setup(x => x.DeserializeFromFile(typeof(PluginConfiguration), It.IsAny<string>())).Throws(new IOException("ontbreekt"));
            string? geschreven = null;
            xml.Setup(x => x.SerializeToFile(It.IsAny<object>(), It.IsAny<string>())).Callback<object, string>((_, pad) => geschreven = pad);

            var plugin = new Plugin(paden.Object, xml.Object);
            var verwacht = Path.Combine(map, "Jellyfin.Plugin.JellyLeon.xml");

            Assert.Equal(verwacht, plugin.ConfigurationFilePath);
            Assert.Equal("Jellyfin.Plugin.JellyLeon.xml", plugin.ConfigurationFileName);

            // Alleen lezen: de deserialisatie faalt, de server maakt een nieuwe configuratie en slaat die op.
            _ = plugin.Configuration;
            Assert.Equal(verwacht, geschreven);
            xml.Verify(x => x.SerializeToFile(It.IsAny<object>(), It.IsAny<string>()), Times.Once);
        }
        finally
        {
            if (Directory.Exists(basis))
            {
                Directory.Delete(basis, true);
            }
        }
    }

    /// <summary>
    /// De bestandsregel (Core.Storage, Core.Secrets) en de procesregel (Core.Werker) stellen code vrij op grond van de
    /// namespace in de broncode. Een type in zo'n namespace, waar het bestand ook staat, krijgt die vrijstelling. Daarom
    /// liggen de typen in die namespaces hier vast: een nieuw type faalt deze test tot iemand het in een review heeft
    /// bekeken en hier (en in ADR-0032, kop "Grenzen") heeft opgenomen.
    /// </summary>
    [Fact]
    public void VrijgesteldeNamespaces_BevattenPreciesDeOpslaglaagEnDeWerkerinterface()
    {
        var vrijgesteld = Jellyfin.Plugin.JellyLeon.Analyzers.Regels.OpslagNamespaces
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.ProcesNamespaces)
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.DatabaseNamespaces)
            .Distinct(StringComparer.Ordinal)
            .ToList();

        var typen = typeof(Plugin).Assembly.GetTypes()
            .Where(t => t.Namespace is { } ns && vrijgesteld.Any(v => ns == v || ns.StartsWith(v + ".", StringComparison.Ordinal)))
            .Where(t => t.GetCustomAttribute<CompilerGeneratedAttribute>() is null && !t.Name.Contains('<', StringComparison.Ordinal))
            .Select(t => t.FullName!)
            .OrderBy(n => n, StringComparer.Ordinal)
            .ToList();

        Assert.Equal(3, vrijgesteld.Count);
        Assert.Equal(
            new[]
            {
                "Jellyfin.Plugin.JellyLeon.Core.Secrets.SecretStore",
                "Jellyfin.Plugin.JellyLeon.Core.Storage.CoreDatabase",
                "Jellyfin.Plugin.JellyLeon.Core.Storage.InternalWriteScope",
                "Jellyfin.Plugin.JellyLeon.Core.Storage.JlDatabase",
                "Jellyfin.Plugin.JellyLeon.Core.Storage.JlPaths",
                "Jellyfin.Plugin.JellyLeon.Core.Werker.GeenWerker",
                "Jellyfin.Plugin.JellyLeon.Core.Werker.IWerker",
            },
            typen);
    }
}
