using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using Jellyfin.Plugin.JellyLeon.Configuration;
using Jellyfin.Plugin.JellyLeon.Core;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Model.Serialization;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// Grenzen die de analyzer niet zelf ziet en die bij het draaien vast moeten liggen (S-G1-17 herstelronde 7, ADR-0032):
/// waar de server de pluginconfiguratie schrijft (R-HARDE-EIS-14a) en welke typen in de vrijgestelde namespaces staan
/// (herreview 6, nieuwe grens 1: de vrijstelling hangt af van de namespace in de broncode).
/// </summary>
[Collection(PluginGrensTests.PluginInstantie)]
public class PluginGrensTests
{
    /// <summary>
    /// <c>Plugin.Instance</c> is één gedeelde waarde; tests die hem zetten of via de echte schakelaars lezen, draaien na
    /// elkaar en laten een neutrale plugin met geladen standaardconfiguratie achter.
    /// </summary>
    internal const string PluginInstantie = "Plugin.Instance";

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
    /// Deel 1f (B1 optie A3; R-VEILIG-1 en R-VEILIG-2): vóór elke lezing of opslag van de eigen configuratie toetst de
    /// plugin het bestand en de map opnieuw. Bij een koppeling (bestand of map), een gedeelde map of een map op de
    /// bestandsnaam leest of schrijft de plugin niets: modules uit, ETag en opslaan 503, de server-serializer wordt niet
    /// aangeroepen en het doel van de koppeling blijft byte-gelijk. De serverroute GET/POST /Plugins/{id}/Configuration
    /// gaat hier niet langs (ADR-0032, deel 1f).
    /// </summary>
    /// <param name="geval">De onveilige opzet.</param>
    [Theory]
    [InlineData("bestand-koppeling")]
    [InlineData("map-koppeling")]
    [InlineData("map-gedeeld")]
    [InlineData("bestand-is-map")]
    public void Configuratie_OnveiligBestandOfMapWordtDoorDePluginNietGelezenOfOpgeslagen(string geval)
    {
        if (!OperatingSystem.IsLinux())
        {
            throw new PlatformNotSupportedException("De opslaggrens geldt alleen in de Linux-container.");
        }

        var basis = Directory.CreateTempSubdirectory("jl-pluginconfig-").FullName;
        try
        {
            var kijkgegevens = "SQLite format 3\0synthetische kijkgegevens"u8.ToArray();
            var doel = Path.Combine(basis, "jellyfin.db");
            File.WriteAllBytes(doel, kijkgegevens);
            var map = Path.Combine(Directory.CreateDirectory(Path.Combine(basis, "plugins")).FullName, "configurations");
            var bestand = Path.Combine(map, "Jellyfin.Plugin.JellyLeon.xml");
            if (geval == "map-koppeling")
            {
                var elders = Directory.CreateDirectory(Path.Combine(basis, "elders")).FullName;
                Directory.CreateSymbolicLink(map, elders);
                File.CreateSymbolicLink(Path.Combine(elders, "Jellyfin.Plugin.JellyLeon.xml"), doel);
            }
            else
            {
                Directory.CreateDirectory(map);
                File.SetUnixFileMode(map, geval == "map-gedeeld" ? (UnixFileMode)Convert.ToInt32("777", 8) : (UnixFileMode)Convert.ToInt32("755", 8));
                if (geval == "bestand-is-map")
                {
                    Directory.CreateDirectory(bestand);
                }
                else
                {
                    File.CreateSymbolicLink(bestand, doel);
                }
            }

            var (schakelaars, xml) = MaakSchakelaars(basis, map);
            Assert.False(schakelaars.IsAan("devices"));
            Assert.Equal(503, Assert.Throws<JlException>(() => schakelaars.Etag).Status);
            Assert.Equal("storage_unavailable", Assert.Throws<JlException>(() => schakelaars.Zet("devices", true)).Code);
            Assert.Equal(kijkgegevens, File.ReadAllBytes(doel));
            xml.Verify(x => x.DeserializeFromFile(It.IsAny<Type>(), It.IsAny<string>()), Times.Never);
            xml.Verify(x => x.SerializeToFile(It.IsAny<object>(), It.IsAny<string>()), Times.Never);
        }
        finally
        {
            NeutralePlugin();
            Directory.Delete(basis, true);
        }
    }

    /// <summary>Tegenproef: met een gewone map en zonder (of met een gewoon) bestand leest en bewaart de plugin gewoon.</summary>
    [Fact]
    public void Configuratie_GewoonBestandWordtGelezenEnOpgeslagen()
    {
        var basis = Directory.CreateTempSubdirectory("jl-pluginconfig-").FullName;
        try
        {
            var map = Directory.CreateDirectory(Path.Combine(basis, "plugins", "configurations")).FullName;
            var (schakelaars, xml) = MaakSchakelaars(basis, map);
            Assert.False(schakelaars.IsAan("devices"));
            var etag = schakelaars.Etag;
            schakelaars.Zet("devices", true);
            Assert.True(schakelaars.IsAan("devices"));
            Assert.NotEqual(etag, schakelaars.Etag);
            Assert.True(File.Exists(Path.Combine(map, "Jellyfin.Plugin.JellyLeon.xml")));
            xml.Verify(x => x.SerializeToFile(It.IsAny<object>(), Path.Combine(map, "Jellyfin.Plugin.JellyLeon.xml")), Times.Exactly(2));
        }
        finally
        {
            NeutralePlugin();
            Directory.Delete(basis, true);
        }
    }

    /// <summary>Een plugin met geladen standaardconfiguratie (alle modules uit) als gedeelde <c>Plugin.Instance</c>.</summary>
    private static void NeutralePlugin()
    {
        var basis = Path.Combine(Path.GetTempPath(), "jl-geen-pluginconfig-" + Guid.NewGuid().ToString("N"));
        var paden = new Mock<IApplicationPaths>();
        paden.SetupGet(p => p.PluginConfigurationsPath).Returns(Path.Combine(basis, "configurations"));
        paden.SetupGet(p => p.PluginsPath).Returns(Path.Combine(basis, "plugins"));
        var xml = new Mock<IXmlSerializer>(MockBehavior.Strict);
        xml.Setup(x => x.DeserializeFromFile(typeof(PluginConfiguration), It.IsAny<string>())).Returns(new PluginConfiguration());
        _ = new Plugin(paden.Object, xml.Object).Configuration;
    }

    /// <summary>De echte plugin met de schrijfwijze van de server (FileMode.Create: volgt een koppeling) en de echte schakelaars.</summary>
    private static (PluginModuleSwitches Schakelaars, Mock<IXmlSerializer> Xml) MaakSchakelaars(string basis, string map)
    {
        var paden = new Mock<IApplicationPaths>();
        paden.SetupGet(p => p.PluginConfigurationsPath).Returns(map);
        paden.SetupGet(p => p.PluginsPath).Returns(Path.Combine(basis, "plugins"));
        var xml = new Mock<IXmlSerializer>(MockBehavior.Strict);
        xml.Setup(x => x.DeserializeFromFile(typeof(PluginConfiguration), It.IsAny<string>())).Throws(new IOException("ontbreekt"));
        xml.Setup(x => x.SerializeToFile(It.IsAny<object>(), It.IsAny<string>()))
            .Callback<object, string>((_, pad) =>
            {
                using var stroom = new FileStream(pad, FileMode.Create, FileAccess.Write);
                stroom.Write("<PluginConfiguration />"u8);
            });
        var plugin = new Plugin(paden.Object, xml.Object);
        var opslag = new PluginOpslag(Path.Combine(basis, "data"), Path.Combine(basis, "cache"), NullLogger<PluginOpslag>.Instance);
        Assert.True(opslag.Beschikbaar);
        Assert.Equal(plugin.ConfigurationFilePath, opslag.ConfiguratieBestand);
        return (new PluginModuleSwitches(opslag), xml);
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
