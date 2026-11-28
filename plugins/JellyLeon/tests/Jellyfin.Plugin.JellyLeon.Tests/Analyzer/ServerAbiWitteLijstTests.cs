using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Analyzers;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Analyzer;

/// <summary>
/// S-G1-17 herstelronde 7 (R-HARDE-EIS-14, -15 en -16; besluit regisseur): de server-ABI is omgedraaid naar een witte lijst.
/// Elk gebruik van een lid van een servertype is JL0001, behalve de lezende leden die de plugin echt gebruikt (per klasse);
/// een eigenschap of veld van een servertype zetten is altijd JL0001; een implementatie of afleiding van een servertype
/// is JL0001 buiten de witte lijst van uitbreidingspunten (per namespace); de configuratieroute van BasePlugin&lt;T&gt;
/// verleggen is JL0002 nergens; WebClient, WebRequest en de trace-laag zijn JL0002 buiten de opslaglaag; een constructor met
/// FileStreamOptions is JL0002. ADR-0032, kop "Server-ABI: witte lijst".
/// </summary>
public class ServerAbiWitteLijstTests
{
    private const string Modules = "Jellyfin.Plugin.JellyLeon.Modules";

    /// <summary>
    /// De proef Punt2 van herreview 6, nagebouwd met dezelfde regels. Daar gaven de regels r30, r40-r42, r49-r54, r61-r64,
    /// r70, r72, r85, r86, r92 en r105 GEEN melding; nu moet elk ervan een JL-fout geven (de opmerking achter de regel
    /// noemt de oude regel en de codes die nu verwacht worden). De tegenproeven van toen (r55 en r65) blijven JL0002.
    /// Elke andere melding is ook een fout: de vergelijking is exact per regel en code.
    /// </summary>
    [Fact]
    public async Task Herreview6Punt2_ElkeRegelZonderMeldingGeeftNuEenJLFout()
    {
        const string Bron = """
            using System;
            using System.Diagnostics;
            using System.IO;
            using System.Net;
            using System.Threading;
            using System.Threading.Tasks;
            using MediaBrowser.Common.Configuration;
            using MediaBrowser.Common.Plugins;
            using MediaBrowser.Controller;
            using MediaBrowser.Controller.Entities;
            using MediaBrowser.Controller.Library;
            using MediaBrowser.Controller.Resolvers;
            using MediaBrowser.Controller.Session;
            using MediaBrowser.Model.Dto;
            using MediaBrowser.Model.IO;
            using MediaBrowser.Model.Plugins;
            using MediaBrowser.Model.Serialization;

            namespace Jellyfin.Plugin.JellyLeon.Configuration
            {
                public class PluginConfiguration : BasePluginConfiguration
                {
                }
            }

            namespace Jellyfin.Plugin.JellyLeon
            {
                // De echte pluginklasse met één verkeerde regel op het officiële overridepunt (route -14a).
                public class Plugin : BasePlugin<Configuration.PluginConfiguration>
                {
                    public Plugin(IApplicationPaths paden, IXmlSerializer xml) : base(paden, xml)
                    {
                    }

                    public override string Name => "Jelly Leon";

                    public override Guid Id => Guid.Empty;

                    public override string ConfigurationFileName => Path.Combine(ApplicationPaths.DataPath, string.Concat("jellyfin", ".db")); // r30: JL0002 JL0001
                }
            }

            namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
            {
                public class Punt2
                {
                    public void Configuratie(Jellyfin.Plugin.JellyLeon.Plugin plugin)
                    {
                        _ = plugin.Configuration; // r40: JL0001
                        plugin.SaveConfiguration(); // r41: JL0001
                        plugin.UpdateConfiguration(new Jellyfin.Plugin.JellyLeon.Configuration.PluginConfiguration()); // r42: JL0001
                    }

            #pragma warning disable SYSLIB0014
                    public void WebRoutes(string db)
                    {
                        var doel = new Uri("file://" + db);
                        using var wc = new WebClient(); // JL0002
                        _ = wc.UploadData(doel, new byte[] { 74, 76 }); // r49: JL0002
                        _ = wc.UploadString(doel, "JL"); // r50: JL0002
                        wc.OpenWrite(doel).WriteByte(33); // r51: JL0002
                        var verzoek = WebRequest.Create(doel); // r52: JL0002
                        verzoek.Method = "PUT"; // r53: JL0002
                        verzoek.GetRequestStream().WriteByte(33); // r54: JL0002
                        new WebClient().DownloadFile(doel, db); // r55 (tegenproef): JL0002
                    }
            #pragma warning restore SYSLIB0014

                    public void TraceRoutes(string db)
                    {
                        ((DefaultTraceListener)Trace.Listeners[0]).LogFileName = db; // r61: JL0002
                        Trace.WriteLine("JELLY-LEON-PROEF"); // r62: JL0002
                        var l = new DefaultTraceListener { LogFileName = db }; // r63: JL0002
                        l.WriteLine("JELLY-LEON-PROEF"); // r64: JL0002
                        using var t = new TextWriterTraceListener(db); // r65 (tegenproef): JL0002
                    }

                    public async Task Natraject(IServerApplicationHost host, IProgress<double> voortgang, CancellationToken stop)
                    {
                        foreach (var taak in host.GetExports<ILibraryPostScanTask>()) // r70: JL0001
                        {
                            await taak.Run(voortgang, stop); // r72: JL0001
                        }
                    }

                    public void Sessies(SessionInfo s, BaseItem item)
                    {
                        s.NowPlayingItem = new BaseItemDto { Id = item.Id }; // r85: JL0001
                        s.LastPlaybackCheckIn = DateTime.MinValue; // r86: JL0001
                    }

                    public void Terugzetten(IServerApplicationHost host, IApplicationPaths paden, string naam)
                    {
                        host.RestoreBackupPath = Path.Combine(paden.BackupPath, naam); // r92: JL0001
                    }

                    public void Afbeeldingen(ItemImageInfo beeld, LinkedChild kind, string pad)
                    {
                        beeld.Path = pad; // aanvulling (ItemImageInfo.Path): JL0001
                        kind.Path = pad; // aanvulling (LinkedChild.Path): JL0001
                    }
                }

                public class Negeerregel : IResolverIgnoreRule // r105: JL0001
                {
                    public bool ShouldIgnore(FileSystemMetadata fileInfo, BaseItem parent) => true;
                }
            }
            """;
        var verwacht = Verwacht(Bron);

        var gevonden = (await AnalyzerHarnas.AnalyseerAsync(Bron, null, TestContext.Current.CancellationToken)).Select(b => (b.Regel, b.Id)).ToHashSet();

        // 20 oude GEEN-regels, 2 tegenproeven, de WebClient-aanmaak en de twee aanvullingen.
        Assert.Equal(25, verwacht.Select(v => v.Regel).Distinct().Count());
        Assert.Equal(verwacht, gevonden);
    }

    /// <summary>
    /// Lezen van de server-ABI mag alleen in de klasse die op de witte lijst staat, met precies dat lid. Een constante of
    /// enumwaarde, een typenaam (parameter, typeof, een typeargument) en een lid van System.Object blijven vrij.
    /// </summary>
    [Fact]
    public async Task Lezen_AlleenDeGenoemdeLedenInDeGenoemdeKlasse()
    {
        const string Romp = """
            public System.Collections.Generic.List<string> M(ILibraryManager lib, IServiceProvider diensten, User gebruiker)
            {
                var mappen = lib.GetVirtualFolders(); // WIT
                _ = mappen[0].Locations; // WIT
                _ = lib.GetItemById(Guid.Empty); // JL0001
                _ = mappen[0].Name; // JL0001
                _ = Jellyfin.Database.Implementations.Enums.PermissionKind.IsAdministrator;
                _ = typeof(ILibraryManager).Name;
                _ = diensten.GetService(typeof(ILibraryManager));
                _ = lib.ToString();
                _ = gebruiker.Id; // JL0001
                return new System.Collections.Generic.List<string>();
            }
            """;

        var inDeKlasse = AnalyzerHarnas.Klasse("Jellyfin.Plugin.JellyLeon.Core", "BibliotheekMappen", Romp);
        var elders = AnalyzerHarnas.Klasse("Jellyfin.Plugin.JellyLeon.Core", "AndereMappen", Romp);

        var gevondenIn = (await AnalyzerHarnas.AnalyseerAsync(inDeKlasse, null, TestContext.Current.CancellationToken)).Select(b => (b.Regel, b.Id)).ToHashSet();
        var gevondenElders = (await AnalyzerHarnas.AnalyseerAsync(elders, null, TestContext.Current.CancellationToken)).Select(b => (b.Regel, b.Id)).ToHashSet();

        Assert.Equal(Verwacht(inDeKlasse), gevondenIn);
        var wit = Regels(elders, "// WIT").Select(r => (r, "JL0001"));
        Assert.Equal(Verwacht(elders).Concat(wit).ToHashSet(), gevondenElders);
        Assert.Equal(5, gevondenElders.Count);
    }

    /// <summary>
    /// Een eigenschap of veld van een servertype zetten is altijd JL0001, ook in een klasse met leesrechten op dat lid en
    /// ook in de opslaglaag. Alleen de objectinitialisatie van een aanmaak die in die klasse op de witte lijst staat, mag de
    /// daar genoemde eigenschappen zetten (de configuratiepagina van de plugin).
    /// </summary>
    [Fact]
    public async Task Toewijzing_IsAltijdVerboden_BehalveDeInitialisatieVanEenToegestaneAanmaak()
    {
        const string Romp = """
            public System.Collections.Generic.IEnumerable<MediaBrowser.Model.Plugins.PluginPageInfo> GetPages(MediaBrowser.Controller.Session.SessionInfo s)
            {
                var pagina = new MediaBrowser.Model.Plugins.PluginPageInfo { Name = "x", DisplayName = "x", EmbeddedResourcePath = "x" }; // WIT-INIT
                var anders = new MediaBrowser.Model.Plugins.PluginPageInfo { EnableInMainMenu = true }; // AANMAAK-OK JL0001
                pagina.Name = "y"; // JL0001
                s.NowPlayingItem = null; // JL0001
                s.PlayState.PositionTicks++; // JL0001
                (s.Id, s.DeviceId) = ("a", "b"); // JL0001
                yield return pagina;
                yield return anders;
            }
            """;

        var inPlugin = AnalyzerHarnas.Klasse("Jellyfin.Plugin.JellyLeon", "Plugin", Romp);
        var elders = AnalyzerHarnas.Klasse(Modules + ".Proef", "Plugin", Romp);
        var opslag = AnalyzerHarnas.Klasse("Jellyfin.Plugin.JellyLeon.Core.Storage", "Plugin", Romp);

        var gevondenIn = await AnalyzerHarnas.AnalyseerAsync(inPlugin, null, TestContext.Current.CancellationToken);
        var gevondenElders = await AnalyzerHarnas.AnalyseerAsync(elders, null, TestContext.Current.CancellationToken);
        var gevondenOpslag = await AnalyzerHarnas.AnalyseerAsync(opslag, null, TestContext.Current.CancellationToken);

        // In de pluginklasse: alleen de verboden toewijzingen en de eigenschap buiten de genoemde (EnableInMainMenu).
        Assert.Equal(Verwacht(inPlugin), gevondenIn.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Contains(gevondenIn, b => b.Tekst.Contains("PluginPageInfo.EnableInMainMenu' zet een eigenschap", StringComparison.Ordinal));
        Assert.Contains(gevondenIn, b => b.Tekst.Contains("SessionInfo.NowPlayingItem' zet een eigenschap", StringComparison.Ordinal));
        Assert.Contains(gevondenIn, b => b.Tekst.Contains("PlayerStateInfo.PositionTicks' zet een eigenschap", StringComparison.Ordinal));
        Assert.Contains(gevondenIn, b => b.Tekst.Contains("SessionInfo.DeviceId' zet een eigenschap", StringComparison.Ordinal));
        Assert.Equal(2, gevondenIn.Count(b => Regel(inPlugin, "(s.Id, s.DeviceId)") == b.Regel));

        // In de klasse die NowPlayingItem mag lezen (de planner) blijft zetten verboden.
        var planner = AnalyzerHarnas.Klasse("Jellyfin.Plugin.JellyLeon.Core.Planner", "ServerSessies", """
            public void M(MediaBrowser.Controller.Session.SessionInfo s)
            {
                _ = s.NowPlayingItem;
                s.NowPlayingItem = null; // JL0001
                s.NowPlayingItem ??= null; // JL0001
            }
            """);
        var gevondenPlanner = await AnalyzerHarnas.AnalyseerAsync(planner, null, TestContext.Current.CancellationToken);
        Assert.Equal(Verwacht(planner), gevondenPlanner.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Equal(2, gevondenPlanner.Count);
        Assert.All(gevondenPlanner, b => Assert.Contains("SessionInfo.NowPlayingItem' zet een eigenschap", b.Tekst, StringComparison.Ordinal));

        // Elders (ook in Core.Storage): de aanmaak zelf en elke toewijzing in de initialisatie zijn ook JL0001.
        foreach (var (bron, gevonden) in new[] { (elders, gevondenElders), (opslag, gevondenOpslag) })
        {
            var regels = gevonden.Select(b => (b.Regel, b.Id)).ToHashSet();
            Assert.All(gevonden, b => Assert.Equal(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.ServerSchrijf, b.Id));
            Assert.Equal(Verwacht(bron).Concat(Regels(bron, "// WIT-INIT").Select(r => (r, "JL0001"))).ToHashSet(), regels);
            Assert.Equal(4, gevonden.Count(b => b.Regel == Regel(bron, "// WIT-INIT")));
        }
    }

    /// <summary>
    /// R-HARDE-EIS-16: een type van de plugin dat een servertype implementeert of ervan afleidt, moet op de witte lijst van
    /// uitbreidingspunten staan, in precies zijn namespace. De huidige vijf (BasePlugin&lt;T&gt;, IHasWebPages en
    /// IPluginServiceRegistrator in de wortel, BasePluginConfiguration in Configuration, IEventConsumer&lt;UserDeletedEventArgs&gt;
    /// in Core.Privacy) mogen daar; elders, met een ander typeargument, via een eigen tussentype of opnieuw genoemd niet.
    /// IScheduledTask blijft verboden. De segmentprovider mag uitsluitend in Modules.Segments.
    /// </summary>
    [Fact]
    public async Task Uitbreidingspunten_AlleenDeWitteLijstPerNamespace()
    {
        const string Bron = """
            using System;
            using System.Collections.Generic;
            using System.Threading;
            using System.Threading.Tasks;
            using Jellyfin.Data.Events;
            using Jellyfin.Data.Events.Users;
            using MediaBrowser.Common.Configuration;
            using MediaBrowser.Common.Plugins;
            using MediaBrowser.Controller;
            using MediaBrowser.Controller.Entities;
            using MediaBrowser.Controller.Events;
            using MediaBrowser.Controller.Library;
            using MediaBrowser.Controller.Plugins;
            using MediaBrowser.Controller.Resolvers;
            using MediaBrowser.Model.IO;
            using MediaBrowser.Model.Plugins;
            using MediaBrowser.Model.Serialization;
            using MediaBrowser.Model.Tasks;
            using Microsoft.Extensions.DependencyInjection;

            namespace Jellyfin.Plugin.JellyLeon.Configuration
            {
                public class PluginConfiguration : BasePluginConfiguration
                {
                }
            }

            namespace Jellyfin.Plugin.JellyLeon
            {
                public class Plugin : BasePlugin<Configuration.PluginConfiguration>, IHasWebPages
                {
                    public Plugin(IApplicationPaths paden, IXmlSerializer xml) : base(paden, xml)
                    {
                    }

                    public override string Name => "x";

                    public IEnumerable<PluginPageInfo> GetPages() => Array.Empty<PluginPageInfo>();
                }

                public sealed class PluginServiceRegistrator : IPluginServiceRegistrator
                {
                    public void RegisterServices(IServiceCollection serviceCollection, IServerApplicationHost applicationHost)
                    {
                    }
                }

                public class TweedePlugin : BasePlugin<Configuration.PluginConfiguration>, IHasPluginConfiguration // JL0001
                {
                    public TweedePlugin(IApplicationPaths paden, IXmlSerializer xml) : base(paden, xml) // JL0001
                    {
                    }

                    public override string Name => "x";
                }

                public class Instellingen : BasePluginConfiguration // JL0001
                {
                }
            }

            namespace Jellyfin.Plugin.JellyLeon.Core.Privacy
            {
                public sealed class Verwijderd : IEventConsumer<UserDeletedEventArgs>
                {
                    public Task OnEvent(UserDeletedEventArgs eventArgs) => Task.CompletedTask;
                }

                public sealed class AnderEvent : IEventConsumer<UserCreatedEventArgs> // JL0001
                {
                    public Task OnEvent(UserCreatedEventArgs eventArgs) => Task.CompletedTask;
                }
            }

            namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
            {
                public sealed class Verwijderd : IEventConsumer<UserDeletedEventArgs> // JL0001
                {
                    public Task OnEvent(UserDeletedEventArgs eventArgs) => Task.CompletedTask;
                }

                public class Afgeleid : Jellyfin.Plugin.JellyLeon.Plugin // JL0001
                {
                    public Afgeleid(IApplicationPaths paden, IXmlSerializer xml) : base(paden, xml)
                    {
                    }
                }

                public interface IEigenRegel : IResolverIgnoreRule // JL0001
                {
                }

                public class ViaEigenRegel : IEigenRegel // JL0001
                {
                    public bool ShouldIgnore(FileSystemMetadata fileInfo, BaseItem parent) => false;
                }

                public class Taak : IScheduledTask // JL0001
                {
                    public string Name => "x";

                    public string Key => "x";

                    public string Description => "x";

                    public string Category => "x";

                    public Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken) => Task.CompletedTask;

                    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers() => Array.Empty<TaskTriggerInfo>();
                }

                public class Natraject : ILibraryPostScanTask // JL0001
                {
                    public Task Run(IProgress<double> progress, CancellationToken cancellationToken) => Task.CompletedTask;
                }
            }

            namespace Jellyfin.Plugin.JellyLeon.Modules.Segments.Andere
            {
                public class Segmenten : MediaBrowser.Controller.MediaSegments.IMediaSegmentProvider // JL0001
                {
                    public string Name => "x";

                    public Task<IReadOnlyList<MediaBrowser.Model.MediaSegments.MediaSegmentDto>> GetMediaSegments(MediaBrowser.Model.MediaSegmentGenerationRequest request, CancellationToken cancellationToken) => throw new NotSupportedException();

                    public ValueTask<bool> Supports(BaseItem item) => ValueTask.FromResult(false);

                    public Task CleanupExtractedData(Guid itemId, CancellationToken cancellationToken) => Task.CompletedTask;
                }
            }
            """;

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(Bron, null, TestContext.Current.CancellationToken);

        Assert.Equal(Verwacht(Bron), gevonden.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Equal(11, gevonden.Count);
        Assert.Contains(gevonden, b => b.Tekst.Contains("'MediaBrowser.Common.Plugins.IHasPluginConfiguration'", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("IResolverIgnoreRule", StringComparison.Ordinal) && b.Tekst.Contains("ViaEigenRegel", StringComparison.Ordinal));
    }

    /// <summary>
    /// R-HARDE-EIS-14a: een override van <c>ConfigurationFileName</c>, <c>SaveConfiguration</c> (beide) of
    /// <c>UpdateConfiguration</c>, of een expliciete implementatie van <c>IHasPluginConfiguration</c>, is JL0002, nergens: ook
    /// niet in de echte pluginklasse en niet in Core.Storage. Een override van Name, Id of Description mag.
    /// </summary>
    [Fact]
    public async Task Pluginconfiguratie_DeRouteVerleggenIsNergensToegestaan()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using MediaBrowser.Common.Configuration;
            using MediaBrowser.Common.Plugins;
            using MediaBrowser.Model.Plugins;
            using MediaBrowser.Model.Serialization;

            namespace {{ruimte}}
            {
                public class Plugin : BasePlugin<BasePluginConfiguration>, IHasPluginConfiguration
                {
                    public Plugin(IApplicationPaths paden, IXmlSerializer xml) : base(paden, xml)
                    {
                    }

                    public override string Name => "x";

                    public override string Description => "x";

                    public override string ConfigurationFileName => "x.xml"; // JL0002

                    public override void SaveConfiguration() // JL0002
                    {
                    }

                    public override void SaveConfiguration(BasePluginConfiguration config) // JL0002
                    {
                    }

                    public override void UpdateConfiguration(BasePluginConfiguration configuration) // JL0002
                    {
                    }

                    BasePluginConfiguration IHasPluginConfiguration.Configuration => null; // JL0002
                }
            }
            """;

        foreach (var ruimte in new[] { "Jellyfin.Plugin.JellyLeon", "Jellyfin.Plugin.JellyLeon.Core.Storage", Modules + ".Proef" })
        {
            var bron = Bron(ruimte);
            var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);
            var regel = gevonden
                .Where(b => b.Id == Jellyfin.Plugin.JellyLeon.Analyzers.Regels.BestandSchrijf).Select(b => b.Regel).ToHashSet();

            Assert.Equal(Regels(bron, "// JL0002").ToHashSet(), regel);
            Assert.All(gevonden.Where(b => b.Id == Jellyfin.Plugin.JellyLeon.Analyzers.Regels.BestandSchrijf), b => Assert.Contains("pluginconfiguratie", b.Tekst, StringComparison.Ordinal));

            // BasePluginConfiguration in deze namespace en het opnieuw genoemde IHasPluginConfiguration zijn JL0001
            // (uitbreidingspunten); de basisconstructor staat niet voor deze klasse op de witte lijst.
            Assert.Contains(gevonden, b => b.Id == Jellyfin.Plugin.JellyLeon.Analyzers.Regels.ServerSchrijf && b.Tekst.Contains("IHasPluginConfiguration", StringComparison.Ordinal));
        }
    }

    /// <summary>
    /// R-HARDE-EIS-15: WebClient, WebRequest (ook FileWebRequest) en de trace-laag zijn buiten de opslaglaag helemaal JL0002,
    /// ook lezen; in Core.Storage en Core.Secrets niet (die laag bewaakt zelf de padgrens). Sinds herstelronde 8
    /// (R-HARDE-EIS-17) zijn HttpClient overal en WebClient en WebRequest in de opslaglaag JL0001: een netwerkclient mag alleen
    /// in een benoemde transportklasse (ADR-0032, kop "HTTP-laag en netwerk").
    /// </summary>
    [Fact]
    public async Task WebClientWebRequestEnTrace_BuitenDeOpslaglaagHelemaalJL0002()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using System.Diagnostics;
            using System.Net;
            using System.Net.Http;

            namespace {{ruimte}}
            {
            #pragma warning disable SYSLIB0014
                public class Netwerk
                {
                    public void M(string pad, Uri doel, HttpClient http)
                    {
                        var r = (FileWebRequest)WebRequest.Create(doel); // JL0002 NET
                        _ = r.Method; // JL0002 NET
                        _ = r.ContentLength; // JL0002 NET
                        _ = WebRequest.DefaultWebProxy; // JL0002 NET
                        var w = new WebClient(); // JL0002 NET
                        _ = w.BaseAddress; // JL0002 NET
                        w.UploadFileAsync(doel, pad); // JL0002 NET
                        _ = new TraceSource("x").Listeners.Count; // JL0002
                        Trace.Listeners.Add(new ConsoleTraceListener()); // JL0002
                        Trace.TraceInformation("x"); // JL0002
                        Debug.WriteLine("x"); // JL0002
                        _ = http.GetAsync(doel); // HTTPCLIENT
                    }
                }
            #pragma warning restore SYSLIB0014
            }
            """;

        var buiten = Bron(Modules + ".Proef");
        var gevonden = await AnalyzerHarnas.AnalyseerAsync(buiten, null, TestContext.Current.CancellationToken);

        var httpClient = Regel(buiten, "// HTTPCLIENT");
        Assert.All(gevonden.Where(b => b.Regel != httpClient), b => Assert.Equal(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.BestandSchrijf, b.Id));
        Assert.Equal(Regels(buiten, "// JL0002").Append(httpClient).ToHashSet(), gevonden.Select(b => b.Regel).ToHashSet());
        Assert.Equal(11, Regels(buiten, "// JL0002").Count);
        var client = Assert.Single(gevonden, b => b.Regel == httpClient);
        Assert.Equal(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.ServerSchrijf, client.Id);
        Assert.Contains("is een netwerkclient", client.Tekst, StringComparison.Ordinal);

        // In de opslaglaag geldt de bestandsregel niet; WebClient, WebRequest en HttpClient zijn daar netwerkclients (JL0001).
        foreach (var ruimte in new[] { "Jellyfin.Plugin.JellyLeon.Core.Storage", "Jellyfin.Plugin.JellyLeon.Core.Secrets" })
        {
            var inOpslag = await AnalyzerHarnas.AnalyseerAsync(Bron(ruimte), null, TestContext.Current.CancellationToken);
            Assert.All(inOpslag, b => Assert.Equal(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.ServerSchrijf, b.Id));
            Assert.All(inOpslag, b => Assert.Contains("is een netwerkclient", b.Tekst, StringComparison.Ordinal));
            Assert.Equal(Regels(buiten, " NET").Append(httpClient).ToHashSet(), inOpslag.Select(b => b.Regel).ToHashSet());
        }
    }

    /// <summary>
    /// Herreview 6, proef WitteLijst_StreamReaderMetOpties: StreamReader staat op de witte lijst van aanmaken, maar een
    /// constructor met FileStreamOptions (Mode=Truncate, Access=ReadWrite maakt het bestand leeg) is JL0002, ook als de opties
    /// als parameter binnenkomen (r12 gaf daar GEEN). Zonder opties blijft lezen vrij.
    /// </summary>
    [Fact]
    public async Task StreamReaderMetFileStreamOptions_IsJL0002()
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Proef", "Lezer", """
            public void M(string pad, FileStreamOptions opties)
            {
                using var a = new StreamReader(pad, opties); // JL0002
                using var b = new StreamReader(pad, System.Text.Encoding.UTF8, true, opties); // JL0002
                using var c = new StreamReader(pad);
                using var d = new StreamReader(pad, System.Text.Encoding.UTF8);
            }
            """);

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

        Assert.Equal(Verwacht(bron), gevonden.Select(b => (b.Regel, b.Id)).ToHashSet());
        Assert.Equal(2, gevonden.Count);
    }

    /// <summary>De witte lijsten verwijzen naar typen die in deze Jellyfin-versie bestaan (wacht bij een upstream-sync).</summary>
    [Fact]
    public void WitteLijsten_ElkTypeBestaatInDezeJellyfinVersie()
    {
        var compilatie = AnalyzerHarnas.Compileer("namespace Leeg { public class Niets { } }");
        var namen = Jellyfin.Plugin.JellyLeon.Analyzers.Regels.ServerAbiWitteLijst.Select(w => w.Type)
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.UitbreidingWitteLijst.Select(w => w.Type))
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.UitbreidingWitteLijst.Where(w => w.Typeargument is not null).Select(w => w.Typeargument!))
            .Concat(Jellyfin.Plugin.JellyLeon.Analyzers.Regels.BestandVolledigTypen)
            .Append("MediaBrowser.Common.Plugins.BasePlugin`1")
            .Append("MediaBrowser.Common.Plugins.IHasPluginConfiguration")
            .Append("System.IO.FileStreamOptions")
            .Distinct(StringComparer.Ordinal)
            .ToList();

        Assert.True(namen.Count >= 25, "verdacht weinig typen: " + namen.Count);
        Assert.All(namen, naam => Assert.True(compilatie.GetTypeByMetadataName(naam) is not null, "onbekend type in een witte lijst: " + naam));

        // Elk lid op de witte lijst bestaat ook (een hernoemd lid zou anders stil verdwijnen uit het bewijs).
        foreach (var wit in Jellyfin.Plugin.JellyLeon.Analyzers.Regels.ServerAbiWitteLijst)
        {
            var type = compilatie.GetTypeByMetadataName(wit.Type)!;
            Assert.True(type.GetMembers(wit.Lid).Length > 0, "onbekend lid op de witte lijst: " + wit.Type + "." + wit.Lid);
            Assert.All(wit.Initialisatie, e => Assert.True(type.GetMembers(e).Length > 0, "onbekende eigenschap: " + e));
        }
    }

    /// <summary>
    /// Elk lid en elk uitbreidingspunt op de witte lijst staat met motivatie in ADR-0032 (besluit regisseur: "elk lid met
    /// motivatie in ADR-0032"). De tabel noemt per regel het type (korte naam), het lid en de klasse of namespace.
    /// </summary>
    [Fact]
    public async Task WitteLijsten_ElkeRegelStaatInAdr0032()
    {
        var adr = (await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, "ADR-0032.md"), TestContext.Current.CancellationToken)).Replace("\r\n", "\n", StringComparison.Ordinal);
        var tabel = adr.Split('\n').Where(r => r.StartsWith("| `", StringComparison.Ordinal)).ToList();

        foreach (var wit in Jellyfin.Plugin.JellyLeon.Analyzers.Regels.ServerAbiWitteLijst)
        {
            var kort = wit.Type.Split('.').Last().Split('`')[0];
            var klasse = wit.Klasse.Substring("Jellyfin.Plugin.JellyLeon".Length).TrimStart('.');
            var lid = wit.Lid == ".ctor" ? "new" : wit.Lid;
            Assert.True(
                tabel.Any(r => r.Contains("`" + kort + "`", StringComparison.Ordinal) && r.Contains(lid, StringComparison.Ordinal) && r.Contains("`" + (klasse.Length == 0 ? "Plugin" : klasse) + "`", StringComparison.Ordinal)),
                "ADR-0032 noemt " + kort + "." + wit.Lid + " in " + wit.Klasse + " niet in de tabel van de witte lijst");
        }

        foreach (var wit in Jellyfin.Plugin.JellyLeon.Analyzers.Regels.UitbreidingWitteLijst)
        {
            var kort = wit.Type.Split('.').Last().Split('`')[0];
            Assert.True(
                tabel.Any(r => r.Contains("`" + kort, StringComparison.Ordinal) && r.Contains("`" + wit.Ruimte + "`", StringComparison.Ordinal)),
                "ADR-0032 noemt het uitbreidingspunt " + kort + " in " + wit.Ruimte + " niet");
        }
    }

    [Fact]
    public async Task WatchTogetherGeeftAlleenHetBinnengekomenAfspeelverzoekDoor()
    {
        const string bron = """
            using System;
            using System.Collections.Generic;
            using System.Threading;
            using MediaBrowser.Controller.Session;
            using MediaBrowser.Controller.SyncPlay;
            using MediaBrowser.Controller.SyncPlay.Requests;
            using MediaBrowser.Model.SyncPlay;
            namespace Jellyfin.Plugin.JellyLeon.Modules.WatchTogether;
            public abstract class WatchDecorator(ISyncPlayManager inner) : ISyncPlayManager
            {
                public abstract GroupInfoDto NewGroup(SessionInfo s, NewGroupRequest r, CancellationToken t);
                public abstract void JoinGroup(SessionInfo s, JoinGroupRequest r, CancellationToken t);
                public abstract void LeaveGroup(SessionInfo s, LeaveGroupRequest r, CancellationToken t);
                public abstract GroupInfoDto GetGroup(SessionInfo s, Guid g);
                public abstract List<GroupInfoDto> ListGroups(SessionInfo s, ListGroupsRequest r);
                public abstract bool IsUserActive(Guid u);
                public void HandleRequest(SessionInfo s, IGroupPlaybackRequest r, CancellationToken t)
                {
                    inner.HandleRequest(s, r, t);
                    inner.HandleRequest(s, r, CancellationToken.None); // JL0001
                }
                public void AnderVerzoek(SessionInfo s, IGroupPlaybackRequest r, CancellationToken t)
                {
                    inner.HandleRequest(s, r, t); // JL0001
                }
            }
            """;
        var uitkomst = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);
        Assert.Equal(Verwacht(bron), uitkomst.Select(b => (b.Regel, b.Id)).ToHashSet());
    }

    [Fact]
    public async Task GewoneBouwWeigertDeServerledenVanDeSimilarProef()
    {
        const string bron = """
            using MediaBrowser.Controller.Entities;
            using MediaBrowser.Controller.Library;
            namespace Jellyfin.Plugin.JellyLeon;
            public sealed class SimilarProefRegistrator
            {
                public void Lees(BaseItem bron, ILibraryManager bibliotheek, InternalItemsQuery vraag, IUserDataManager gegevens, UserDataSaveEventArgs gebeurtenis)
                {
                    _ = bron.Genres; // JL0001
                    _ = vraag.Genres; // JL0001
                    _ = bibliotheek.GetItemList(vraag, false); // JL0001
                    gegevens.UserDataSaved += Bewaard; // JL0001
                    _ = gebeurtenis.SaveReason; // JL0001
                }

                private static void Bewaard(object? sender, UserDataSaveEventArgs args) { }
            }
            """;
        var uitkomst = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);
        Assert.Equal(Verwacht(bron), uitkomst.Select(b => (b.Regel, b.Id)).ToHashSet());
    }

    [Fact]
    public async Task AanbevelingsBibliotheekMagKijktoestandAlleenLezen()
    {
        const string bron = """
            using MediaBrowser.Controller.Entities;
            using MediaBrowser.Model.Querying;
            namespace Jellyfin.Plugin.JellyLeon.Modules.Recommendations;
            public sealed class AanbevelingsBibliotheek
            {
                public void Gebruik(UserItemData toestand, NextUpQuery vraag)
                {
                    _ = toestand.Played;
                    toestand.Played = false; // JL0001
                    toestand.IsFavorite = false; // JL0001
                    toestand.PlaybackPositionTicks = 0; // JL0001
                    vraag.User = null!; // JL0001
                }
            }
            """;
        var uitkomst = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);
        Assert.Equal(Verwacht(bron), uitkomst.Select(b => (b.Regel, b.Id)).ToHashSet());
    }

    /// <summary>Verwachte (regel, code)-paren: elke JLxxxx na "//" op een regel.</summary>
    private static HashSet<(int Regel, string Id)> Verwacht(string bron) =>
        bron.Split('\n')
            .Select((tekst, index) => (Regel: index + 1, Opmerking: tekst.Contains("//", StringComparison.Ordinal) ? tekst[tekst.IndexOf("//", StringComparison.Ordinal)..] : string.Empty))
            .SelectMany(r => Regex.Matches(r.Opmerking, @"\bJL\d{4}\b").Select(m => (r.Regel, m.Value)))
            .ToHashSet();

    private static List<int> Regels(string bron, string merk) =>
        bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.Contains(merk, StringComparison.Ordinal)).Select(r => r.Regel).ToList();

    private static int Regel(string bron, string merk) => Regels(bron, merk).Single();
}
