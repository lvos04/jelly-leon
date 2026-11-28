using System;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Analyzers;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Microsoft.CodeAnalysis;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Analyzer;

/// <summary>
/// B03-017 / ADR-0032: de analyzer maakt van elke verboden aanroep een bouwfout. De proefbron is dezelfde die
/// <c>tools/jelly-leon/analyzer_proef.py</c> echt laat bouwen ("een testassembly met elke verboden aanroep moet de
/// build laten falen").
/// </summary>
public class VerbodenApiAnalyzerTests
{
    private const string Modules = "Jellyfin.Plugin.JellyLeon.Modules";
    private const string SelectionGuard = Modules + ".Subtitles.Publication.SelectionGuard";
    private const string Reset = "MediaBrowser.Controller.Library.IUserDataManager.ResetPlaybackStreamSelections";

    [Fact]
    public async Task Proefbron_ElkeGemarkeerdeRegelGeeftPreciesDieBouwfout()
    {
        var bron = await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, "VerbodenAanroepen.cs.txt"), TestContext.Current.CancellationToken);
        var verwacht = bron.Split('\n')
            .Select((tekst, index) => (Regel: index + 1, Raak: Regex.Match(tekst, @"// VERWACHT: (JL\d{4})")))
            .Where(r => r.Raak.Success)
            .Select(r => (r.Regel, Id: r.Raak.Groups[1].Value))
            .ToList();

        var gevonden = (await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken)).Select(b => (b.Regel, b.Id)).ToList();

        Assert.Equal(verwacht, gevonden);
        foreach (var id in new[] { Regels.ServerSchrijf, Regels.BestandSchrijf, Regels.ServerDatabase, Regels.ProcesStart })
        {
            Assert.Contains(verwacht, v => v.Id == id);
        }

        Assert.True(verwacht.Count >= 50, "de proefbron hoort elke verboden aanroep te bevatten");
    }

    /// <summary>
    /// R-HARDE-EIS-1 (S-G1-17): officiële server-API's die zelf in jellyfin.db schrijven (voorkeuren, hoofdstukken,
    /// sporen, personen) zijn verboden, ook een Get die de rij aanmaakt als die ontbreekt. Vóór het herstel gaf deze
    /// bron geen enkele bevinding.
    /// </summary>
    [Fact]
    public async Task VoorkeurenHoofdstukkenSporenEnPersonen_ElkeSchrijvendeAanroepIsJL0001()
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Proef", "Schrijver", """
            public async System.Threading.Tasks.Task M(
                MediaBrowser.Controller.IDisplayPreferencesManager voorkeuren,
                MediaBrowser.Controller.Persistence.IChapterRepository hoofdstukken,
                MediaBrowser.Controller.Chapters.IChapterManager hoofdstukbeheer,
                MediaBrowser.Controller.Persistence.IMediaStreamRepository sporen,
                MediaBrowser.Controller.Persistence.IPeopleRepository mensen,
                Guid gebruiker, Guid item)
            {
                var p = voorkeuren.GetDisplayPreferences(gebruiker, item, "web");
                voorkeuren.UpdateDisplayPreferences(p);
                await hoofdstukken.DeleteChaptersAsync(item, CancellationToken.None);
                await hoofdstukbeheer.DeleteChapterDataAsync(item, CancellationToken.None);
                sporen.SaveMediaStreams(item, Array.Empty<MediaBrowser.Model.Entities.MediaStream>(), CancellationToken.None);
                mensen.UpdatePeople(item, Array.Empty<MediaBrowser.Controller.Entities.PersonInfo>());
                _ = mensen.DeleteOrphanedCredits();
                /*WL*/ _ = voorkeuren.ListItemDisplayPreferences(gebruiker, "web");
                /*WL*/ _ = hoofdstukken.GetChapters(item);
                /*WL*/ _ = sporen.GetMediaStreamLanguages(MediaBrowser.Model.Entities.MediaStreamType.Audio);
                /*WL*/ _ = mensen.GetPeopleNames(new InternalPeopleQuery());
            }
            """);

        var alles = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);
        var gevonden = alles.Where(b => !AnalyzerHarnas.IsWitteLijst(b)).ToList();

        // Sinds herstelronde 7 geven de leesregels ook JL0001: lezen van de server-ABI buiten de witte lijst (/*WL*/).
        Assert.Equal(4, AnalyzerHarnas.WlRegels(bron).Count);
        Assert.Equal(AnalyzerHarnas.WlRegels(bron), AnalyzerHarnas.WlGevonden(alles));
        Assert.Equal(7, gevonden.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.ServerSchrijf, b.Id));
        Assert.Equal(7, gevonden.Select(b => b.Regel).Distinct().Count());
        foreach (var api in new[] { "GetDisplayPreferences", "UpdateDisplayPreferences", "DeleteChaptersAsync", "DeleteChapterDataAsync", "SaveMediaStreams", "UpdatePeople", "DeleteOrphanedCredits" })
        {
            Assert.Contains(gevonden, b => b.Tekst.Contains("." + api + "'", StringComparison.Ordinal));
        }
    }

    /// <summary>
    /// R-HARDE-EIS-2 (S-G1-17): JL0003 ziet de naam van de serverdatabase ook als die uit stukken bestaat; precies één
    /// bevinding per uitdrukking, en geen bevinding als een onbekend stuk de naam onderbreekt.
    /// </summary>
    [Fact]
    public async Task SamengesteldeNaamVanDeServerdatabase_IsJL0003()
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Proef", "Schrijver", """
            public void M(string data)
            {
                _ = Path.Combine(data, "jellyfin" + ".db"); // JL0003
                const string Naam = "library";
                _ = Path.Combine(data, Naam + ".db"); // JL0003
                _ = $"{data}/jellyfin.d" + "b"; // JL0003
                _ = $"{data}/{Naam}.DB"; // JL0003
                _ = "Data Source=" + data + "/jellyfin.db"; // JL0003
                _ = ("jelly" + "fin") + (data + "x") + ".db";
                _ = "jellyfin" + data + ".db";
                _ = $"{data}/jelly-leon/{Naam}-export.json";
                _ = Naam + "/" + ".db";
            }
            """);
        var verwacht = bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0003", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

        Assert.Equal(5, verwacht.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.ServerDatabase, b.Id));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel));
    }

    /// <summary>
    /// R-HARDE-EIS-6 (S-G1-17, herstelronde 2): JL0003 leest ook de constante waarde van een omzetting (<c>(char)46</c>,
    /// <c>(char)0x2E</c>), een UTF-8-tekst (<c>"…"u8</c>) en een uitlijning in <c>$"…"</c>: een uitlijning die niet
    /// langer is dan het stuk vult niets aan, een langere vult met spaties aan de goede kant. Vóór het herstel gaven de
    /// eerste vijf gemarkeerde regels geen bevinding. R-HARDE-EIS-8 (herstelronde 3): een optelling van UTF-8-teksten
    /// (<c>"jellyfin"u8 + ".db"u8</c>) is ook een samenstelling; vóór dat herstel gaven die drie regels geen bevinding.
    /// </summary>
    [Fact]
    public async Task ConstanteTekensUtf8EnUitlijning_IsJL0003()
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Proef", "Schrijver", """
            public void M(string data, System.Text.StringBuilder sb)
            {
                const int Breed = 0;
                _ = "jellyfin" + (char)46 + "db"; // JL0003
                _ = "jellyfin" + (char)0x2E + "db"; // JL0003
                _ = System.Text.Encoding.UTF8.GetString("jellyfin.db"u8); // JL0003
                _ = $"jellyfin{".db",0}"; // JL0003
                _ = $"jellyfin{".db",3}"; // JL0003
                _ = $"jellyfin{".db",-6}"; // JL0003
                _ = $"{"jellyfin",9}.db"; // JL0003
                _ = $"{"jellyfin",-8}.db"; // JL0003
                _ = $"jellyfin{".db",Breed}"; // JL0003
                _ = $"jellyfin{(char)46}db"; // JL0003
                _ = $"jellyfin{'.',1}db"; // JL0003
                _ = sb.Append($"{data}/jellyfin{".db",3}"); // JL0003
                _ = (string)("jelly" + "fin.db") + data; // JL0003
                _ = System.Text.Encoding.UTF8.GetString("jellyfin"u8 + ".db"u8); // JL0003
                _ = System.Text.Encoding.UTF8.GetString("jellyfin.d"u8 + "b"u8); // JL0003
                _ = System.Text.Encoding.UTF8.GetString("jelly"u8 + "fin"u8 + ".db"u8); // JL0003
                _ = System.Text.Encoding.UTF8.GetString("jelly-leon"u8 + ".db"u8);
                _ = $"jellyfin{".db",6}";
                _ = $"{"jellyfin",-9}.db";
                _ = sb.Append($"{data}/jellyfin{".db",6}");
                _ = "jellyfin" + (int)'.' + "db";
                _ = System.Text.Encoding.UTF8.GetString("jelly-leon.db"u8);
            }
            """);
        var verwacht = bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0003", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

        Assert.Equal(16, verwacht.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.ServerDatabase, b.Id));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel));
    }

    /// <summary>
    /// R-HARDE-EIS-1 (S-G1-17, herstelronde 2): een servertaak starten of de planning ervan wijzigen kan ook via het
    /// taakobject zelf (<c>ITaskManager.ScheduledTasks</c> of <c>IApplicationHost.GetExports</c>). Dat is net zo goed
    /// JL0001. Lezen (naam, staat, standaardplanning) gaf geen melding; sinds herstelronde 7 is het JL0001 buiten de witte
    /// lijst van de server-ABI (/*WL*/). Vóór het herstel gaf deze bron geen bevinding.
    /// </summary>
    [Fact]
    public async Task ServertaakViaHetTaakobject_IsJL0001()
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Proef", "Schrijver", """
            public async System.Threading.Tasks.Task M(
                MediaBrowser.Model.Tasks.ITaskManager taken,
                MediaBrowser.Model.Tasks.IScheduledTask taak,
                MediaBrowser.Model.Tasks.IScheduledTaskWorker werker,
                MediaBrowser.Common.IApplicationHost host)
            {
                /*WL*/ await taken.ScheduledTasks[0].ScheduledTask.ExecuteAsync(new Progress<double>(), CancellationToken.None); // JL0001
                /*WL*/ taken.ScheduledTasks[0].Triggers = Array.Empty<MediaBrowser.Model.Tasks.TaskTriggerInfo>(); // JL0001
                /*WL*/ taken.ScheduledTasks[0].ReloadTriggerEvents(); // JL0001
                await taak.ExecuteAsync(new Progress<double>(), CancellationToken.None); // JL0001
                Func<IProgress<double>, CancellationToken, System.Threading.Tasks.Task> later = taak.ExecuteAsync; // JL0001
                /*WL*/ werker.Triggers = werker.Triggers; // JL0001
                /*WL*/ foreach (var t in host.GetExports<MediaBrowser.Model.Tasks.IScheduledTask>(false)) { await t.ExecuteAsync(new Progress<double>(), CancellationToken.None); } // JL0001
                _ = later;
                /*WL*/ _ = taak.GetDefaultTriggers();
                /*WL*/ _ = taak.Name + taak.Key + taak.Category;
                /*WL*/ _ = werker.Name + werker.State + werker.Id;
                /*WL*/ _ = werker.Triggers.Count;
                /*WL*/ _ = taken.ScheduledTasks.Count;
            }
            """);
        var verwacht = bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0001", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var alles = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);
        var gevonden = alles.Where(b => !AnalyzerHarnas.IsWitteLijst(b)).ToList();

        // Sinds herstelronde 7: lezen van de server-ABI (ScheduledTasks, GetExports, naam en staat) is JL0001 buiten de witte lijst.
        Assert.Equal(10, AnalyzerHarnas.WlRegels(bron).Count);
        Assert.Equal(AnalyzerHarnas.WlRegels(bron), AnalyzerHarnas.WlGevonden(alles));
        Assert.Equal(7, verwacht.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.ServerSchrijf, b.Id));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel));
        Assert.Contains(gevonden, b => b.Tekst.Contains("IScheduledTask.ExecuteAsync'", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("IScheduledTaskWorker.Triggers'", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("IScheduledTaskWorker.ReloadTriggerEvents'", StringComparison.Ordinal));
    }

    /// <summary>
    /// R-HARDE-EIS-7 (S-G1-17, herstelronde 2): leden die via IChannelManager kanaalitems aanmaken, verversen of wissen
    /// (en daarbij de UserData van verdwenen kanaalitems verplaatsen) zijn JL0001, net als die leden van IChannelManager
    /// zelf. De bibliotheek lezen kan via ILibraryManager.GetItemList, sinds herstelronde 7 alleen in een klasse waarvoor dat
    /// lid op de witte lijst van de server-ABI staat (hier niet: /*WL*/). Vóór het herstel gaf deze bron geen bevinding.
    /// Herstelronde 3 (basistype-grens): GetChildren en GetRecursiveChildren zijn ook op Folder verboden, zodat een
    /// variabele van het basistype (<c>Folder f1 = seizoen</c>) de regel niet omzeilt; vóór dat herstel gaven die vijf
    /// regels geen bevinding.
    /// </summary>
    [Fact]
    public async Task KanaalitemsVerversenOfWissenViaEenLeeslid_IsJL0001()
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Proef", "Lezer", """
            public async System.Threading.Tasks.Task M(
                MediaBrowser.Controller.LiveTv.ILiveTvManager live,
                IUserViewManager weergaven,
                ILibraryManager lib,
                Folder map,
                UserView weergave,
                MediaBrowser.Controller.Playlists.Playlist lijst,
                MediaBrowser.Controller.Entities.TV.Season seizoen,
                MediaBrowser.Controller.Entities.TV.Series serie,
                User gebruiker)
            {
                /*WL*/ var opties = new MediaBrowser.Controller.Dto.DtoOptions();
                /*WL*/ _ = await live.GetRecordingsAsync(new MediaBrowser.Model.LiveTv.RecordingQuery(), opties); // JL0001
                _ = await live.GetRecordingFoldersAsync(gebruiker); // JL0001
                /*WL*/ _ = weergaven.GetLatestItems(new MediaBrowser.Model.Querying.LatestItemsQuery(), opties); // JL0001
                /*WL*/ _ = map.GetItems(new InternalItemsQuery(gebruiker)); // JL0001
                /*WL*/ _ = map.GetItemList(new InternalItemsQuery(gebruiker)); // JL0001
                _ = map.GetChildCount(gebruiker); // JL0001
                _ = map.GetRecursiveChildCount(gebruiker); // JL0001
                _ = seizoen.GetEpisodes(); // JL0001
                _ = seizoen.GetChildren(gebruiker, true, null); // JL0001
                _ = weergave.GetChildCount(gebruiker); // JL0001
                _ = serie.GetSeasonEpisodes(seizoen, gebruiker, opties, false); // JL0001
                _ = MediaBrowser.Controller.Playlists.Playlist.GetPlaylistItems(Array.Empty<BaseItem>(), gebruiker, opties); // JL0001
                _ = weergave.GetChildren(gebruiker, true, null); // JL0001
                _ = lijst.GetRecursiveChildren(gebruiker, null, out _); // JL0001
                _ = map.GetChildren(gebruiker, true); // JL0001
                _ = map.GetRecursiveChildren(gebruiker, null, out _); // JL0001
                Folder f1 = seizoen; _ = f1.GetChildren(gebruiker, true); // JL0001
                Folder f2 = weergave; _ = f2.GetRecursiveChildren(gebruiker, null, out _); // JL0001
                Folder f3 = lijst; _ = f3.GetRecursiveChildren(); // JL0001
                /*WL*/ _ = live.IsEnabledForUser(gebruiker);
                /*WL*/ _ = weergaven.GetUserViews(new MediaBrowser.Model.Library.UserViewQuery { User = gebruiker });
                /*WL*/ _ = lib.GetItemList(new InternalItemsQuery(gebruiker) { Parent = map });
                /*WL*/ _ = lib.GetItemsResult(new InternalItemsQuery(gebruiker) { Parent = map });
                /*WL*/ _ = serie.GetEpisodes(gebruiker, opties, false);
                /*WL*/ _ = seizoen.Name;
            }
            """);
        var verwacht = bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0001", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var alles = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);
        var gevonden = alles.Where(b => !AnalyzerHarnas.IsWitteLijst(b)).ToList();

        // Sinds herstelronde 7: ook de leesregels en het aanmaken van servertypen (DtoOptions, de query's) zijn JL0001 buiten de
        // witte lijst; ILibraryManager.GetItemList staat voor deze klasse niet op de lijst.
        Assert.Equal(11, AnalyzerHarnas.WlRegels(bron).Count);
        Assert.Equal(AnalyzerHarnas.WlRegels(bron), AnalyzerHarnas.WlGevonden(alles));
        Assert.Equal(19, verwacht.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.ServerSchrijf, b.Id));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel));
        Assert.Contains(gevonden, b => b.Tekst.Contains("ILiveTvManager.GetRecordingsAsync'", StringComparison.Ordinal));
    }

    /// <summary>
    /// R-HARDE-EIS-9 (S-G1-17, herstelronde 3; besluit van de regisseur): bij een bewaakte interface tellen van een eigen
    /// klasse die de interface implementeert alleen de leden die een lid van die interface implementeren. Een eigen
    /// servertaak mag dus eigen hulpmethoden en eigenschappen hebben (de vorm van proef H11); de eigen ExecuteAsync
    /// aanroepen, ook via een verwijzing of via de interface, en de planning van een eigen werker wijzigen blijft JL0001,
    /// met de naam van het interfacelid in de melding. Vóór het herstel gaven de drie regels in ExecuteAsync JL0001 met
    /// een misleidende naam (<c>IScheduledTask.VerwerkAsync</c>), net als de eigen eigenschap van de werker.
    /// R-HARDE-EIS-11 (herstelronde 4): ook een override van de implementatie telt (<c>Overschreven.Start</c>, en bij de
    /// werker een overschreven <c>Triggers</c> en <c>ReloadTriggerEvents</c>); vóór dat herstel gaven die drie regels geen bevinding.
    /// </summary>
    [Fact]
    public async Task EigenServertaak_AlleenDeLedenVanDeInterfaceTellen()
    {
        const string Bron = """
            using System;
            using System.Collections.Generic;
            using System.Threading;
            using System.Threading.Tasks;
            using Jellyfin.Data.Events;
            using MediaBrowser.Model.Tasks;

            namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
            {
                /*WL*/ public class Taak : IScheduledTask
                {
                    public string Name => Naam();
                    public string Key => "JellyLeonProef";
                    public string Description => "Proef";
                    public string Category => "Jelly Leon";
                    public int Teller { get; set; }

                    public virtual async Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
                    {
                        await VerwerkAsync(cancellationToken);
                        Teller = 1;
                        _ = Naam();
                        progress.Report(100);
                        _ = GetDefaultTriggers();
                        Teller++;
                    }

                    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers() => Array.Empty<TaskTriggerInfo>();

                    private static string Naam() => "Proef";

                    private Task VerwerkAsync(CancellationToken stop) => Task.CompletedTask;

                    public async Task Opnieuw()
                    {
                        await ExecuteAsync(new Progress<double>(), CancellationToken.None); // JL0001 ExecuteAsync
                        Func<IProgress<double>, CancellationToken, Task> later = ExecuteAsync; // JL0001 ExecuteAsync
                        await ((IScheduledTask)this).ExecuteAsync(new Progress<double>(), CancellationToken.None); // JL0001 ExecuteAsync
                        _ = later;
                    }
                }

                /*WL*/ public sealed class AfgeleideTaak : Taak
                {
                    public Task Start() => ExecuteAsync(new Progress<double>(), CancellationToken.None); // JL0001 ExecuteAsync
                }

                /*WL*/ public sealed class Overschreven : Taak
                {
                    public override Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken) => base.ExecuteAsync(progress, cancellationToken); // JL0001 ExecuteAsync

                    public Task Start() => ExecuteAsync(null!, default); // JL0001 ExecuteAsync
                }

                /*WL*/ public sealed class Uitdrukkelijk : IScheduledTask
                {
                    public string Name => "U";
                    public string Key => "U";
                    public string Description => "U";
                    public string Category => "U";

                    Task IScheduledTask.ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken) => Hulp();

                    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers() => Array.Empty<TaskTriggerInfo>();

                    public Task Hulp() => Task.CompletedTask;

                    public Task Start() => ((IScheduledTask)this).ExecuteAsync(new Progress<double>(), CancellationToken.None); // JL0001 ExecuteAsync
                }

                /*WL*/ public class Werker : IScheduledTaskWorker
                {
                    public event EventHandler<GenericEventArgs<double>> TaskProgress { add { } remove { } }
                    public IScheduledTask ScheduledTask => new Taak();
                    /*WL*/ public TaskResult LastExecutionResult => new TaskResult();
                    public string Name => "W";
                    public string Description => "W";
                    public string Category => "W";
                    public TaskState State => TaskState.Idle;
                    public double? CurrentProgress => null;
                    public virtual IReadOnlyList<TaskTriggerInfo> Triggers { get => Array.Empty<TaskTriggerInfo>(); set { } }
                    public string Id => "W";
                    public int Stand { get; set; }
                    public virtual void ReloadTriggerEvents() { }
                    public void Eigen() { }
                    public void Dispose() { }
                }

                /*WL*/ public sealed class OverschrevenWerker : Werker
                {
                    public override IReadOnlyList<TaskTriggerInfo> Triggers { get => Array.Empty<TaskTriggerInfo>(); set { } }
                    public override void ReloadTriggerEvents() { }
                }

                public static class Gebruiker
                {
                    public static void M(Werker werker, Uitdrukkelijk taak, OverschrevenWerker ander)
                    {
                        werker.Triggers = werker.Triggers; // JL0001 Triggers
                        werker.ReloadTriggerEvents(); // JL0001 ReloadTriggerEvents
                        ander.Triggers = ander.Triggers; // JL0001 Triggers
                        ander.ReloadTriggerEvents(); // JL0001 ReloadTriggerEvents
                        werker.Stand = 2;
                        werker.Eigen();
                        _ = werker.Name + werker.State + werker.Id;
                        _ = taak.Hulp();
                        _ = taak.GetDefaultTriggers();
                    }
                }
            }
            """;
        var verwacht = Bron.Split('\n')
            .Select((tekst, index) => (Regel: index + 1, Raak: Regex.Match(tekst, @"// JL0001 (\w+)$")))
            .Where(r => r.Raak.Success)
            .Select(r => (r.Regel, Lid: r.Raak.Groups[1].Value))
            .ToList();

        var alles = await AnalyzerHarnas.AnalyseerAsync(Bron, null, TestContext.Current.CancellationToken);
        var gevonden = alles.Where(b => !AnalyzerHarnas.IsWitteLijst(b)).ToList();

        // Sinds herstelronde 7 (R-HARDE-EIS-16): IScheduledTask en IScheduledTaskWorker staan (nog) niet op de witte lijst van
        // uitbreidingspunten, dus elke klasse die ze implementeert of ervan afleidt is JL0001; ook new TaskResult (servertype).
        Assert.Equal(7, AnalyzerHarnas.WlRegels(Bron).Count);
        Assert.Equal(AnalyzerHarnas.WlRegels(Bron), AnalyzerHarnas.WlGevonden(alles));
        Assert.Equal(11, verwacht.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.ServerSchrijf, b.Id));
        Assert.Equal(verwacht.Select(v => v.Regel), gevonden.Select(b => b.Regel));
        foreach (var (v, b) in verwacht.Zip(gevonden))
        {
            var type = v.Lid == "ExecuteAsync" ? "IScheduledTask" : "IScheduledTaskWorker";
            Assert.Contains("'MediaBrowser.Model.Tasks." + type + "." + v.Lid + "'", b.Tekst, StringComparison.Ordinal);
        }
    }

    /// <summary>
    /// R-HARDE-EIS-10 (S-G1-17, herstelronde 4; de vorm van proef H12): de dienst <c>IJellyfinDatabaseProvider</c> zit in
    /// de container van de server en geeft via <c>DbContextFactory</c> een <c>JellyfinDbContext</c>; <c>PurgeDatabase</c>
    /// en <c>RestoreBackupFast</c> wissen of overschrijven jellyfin.db. Elk gebruik van die typenaam is JL0003, ook als
    /// typeargument, via <c>var</c> of een alias, en ook van de twee typen die een context gebruiken
    /// (<c>IEntityFrameworkCoreLockingBehavior</c>, <c>IItemQueryHelpers</c>). De grens ligt bij de naam: zonder het veld
    /// en de constructorparameter kan de klasse de dienst niet krijgen; de regels in de romp die de naam niet noemen,
    /// geven daarom zelf geen tweede melding. Vóór het herstel gaven alleen de regels met <c>JellyfinDbContext</c> (de
    /// tegenproeven) een bevinding. Sinds herstelronde 5 (R-HARDE-EIS-12) geven de drie regels die met de context een
    /// Entity Framework-lid gebruiken (<c>Database</c>, <c>ExecuteDeleteAsync</c>, <c>SaveChanges</c>) daarnaast JL0002:
    /// dat is databasetoegang buiten Core.Storage. De regels met alleen leden van de dienst zelf (<c>PurgeDatabase</c>,
    /// <c>RestoreBackupFast</c>) gaven geen tweede melding; sinds herstelronde 7 geven ze JL0001 (witte lijst van de server-ABI).
    /// </summary>
    [Fact]
    public async Task DatabasedienstVanDeServer_ElkGebruikVanDeTypenaamIsJL0003()
    {
        const string Bron = """
            using System;
            using System.Collections.Generic;
            using System.Threading;
            using System.Threading.Tasks;
            using Jellyfin.Database.Implementations;
            using Jellyfin.Database.Implementations.Locking;
            using MediaBrowser.Controller.Persistence;
            using MediaBrowser.Model.Tasks;
            using Microsoft.EntityFrameworkCore;
            using Microsoft.Extensions.DependencyInjection;
            using Fabriek = Microsoft.EntityFrameworkCore.IDbContextFactory<Jellyfin.Database.Implementations.JellyfinDbContext>; // JL0003
            using Provider = Jellyfin.Database.Implementations.IJellyfinDatabaseProvider; // JL0003

            namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
            {
                /*WL*/ public class DbTaak : IScheduledTask
                {
                    private readonly IJellyfinDatabaseProvider _db; // JL0003

                    public DbTaak(IJellyfinDatabaseProvider db) // JL0003
                    {
                        _db = db;
                    }

                    public string Name => "Db";
                    public string Key => "Db";
                    public string Description => "Db";
                    public string Category => "Db";

                    public async Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
                    {
                        /*WL*/ _db.DbContextFactory!.CreateDbContext().Database.ExecuteSqlRaw("DELETE FROM UserData"); // JL0002
                        /*WL*/ await _db.DbContextFactory!.CreateDbContext().UserData.ExecuteDeleteAsync(cancellationToken); // JL0002
                        /*WL*/ DbContext c = _db.DbContextFactory!.CreateDbContext();
                        c.SaveChanges(); // JL0002
                        /*WL*/ await _db.PurgeDatabase(_db.DbContextFactory!.CreateDbContext(), null);
                        /*WL*/ await _db.RestoreBackupFast("sleutel", cancellationToken);
                        /*WL*/ await _db.RunScheduledOptimisation(cancellationToken);
                        /*WL*/ await _db.RefreshStatistics(cancellationToken);
                        /*WL*/ var v = _db.DbContextFactory!.CreateDbContext(); // JL0003
                        JellyfinDbContext n = v; // JL0003
                        /*WL*/ var f = _db.DbContextFactory; // JL0003
                        _ = n;
                        _ = f;
                    }

                    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers() => Array.Empty<TaskTriggerInfo>();
                }

                public static class Omwegen
                {
                    public static void Diensten(IServiceProvider diensten)
                    {
                        _ = diensten.GetService<IJellyfinDatabaseProvider>(); // JL0003
                        _ = diensten.GetRequiredService<IDbContextFactory<JellyfinDbContext>>(); // JL0003
                        _ = typeof(IJellyfinDatabaseProvider); // JL0003
                        var rij = new IJellyfinDatabaseProvider[0]; // JL0003
                        _ = rij;
                        _ = diensten.GetService<IServiceProvider>();
                    }

                    public static void Via(Fabriek fabriek, Provider provider) // JL0003
                    {
                        _ = fabriek;
                        _ = provider;
                    }

                    public static void Slot(IEntityFrameworkCoreLockingBehavior slot) => _ = slot; // JL0003

                    public static void Query(IItemQueryHelpers query) => _ = query; // JL0003
                }
            }
            """;
        var verwacht = Bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0003", StringComparison.Ordinal)).Select(r => r.Regel).ToList();
        var verwachtEf = Bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0002", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var alles = await AnalyzerHarnas.AnalyseerAsync(Bron, null, TestContext.Current.CancellationToken);
        var gevonden = alles.Where(b => b.Id == Regels.ServerDatabase).ToList();

        // Sinds herstelronde 7 geeft elk lid van de dienst (en de taak zelf, IScheduledTask) daarnaast JL0001: de server-ABI is
        // een witte lijst, en IJellyfinDatabaseProvider staat daar nergens op.
        Assert.Equal(10, AnalyzerHarnas.WlRegels(Bron).Count);
        Assert.Equal(AnalyzerHarnas.WlRegels(Bron), AnalyzerHarnas.WlGevonden(alles));
        Assert.Equal(14, verwacht.Count);
        Assert.Equal(3, verwachtEf.Count);
        Assert.All(alles.Where(b => !AnalyzerHarnas.IsWitteLijst(b)), b => Assert.Contains(b.Id, new[] { Regels.ServerDatabase, Regels.BestandSchrijf }));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel).Distinct());
        Assert.Equal(verwachtEf, alles.Where(b => b.Id == Regels.BestandSchrijf).Select(b => b.Regel));
        Assert.Contains(gevonden, b => b.Tekst.Contains("'Jellyfin.Database.Implementations.IJellyfinDatabaseProvider'", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("'Jellyfin.Database.Implementations.Locking.IEntityFrameworkCoreLockingBehavior'", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("'MediaBrowser.Controller.Persistence.IItemQueryHelpers'", StringComparison.Ordinal));
    }

    /// <summary>
    /// R-HARDE-EIS-12 (S-G1-17, herstelronde 5; de vormen van proef H15 en H16): buiten Core.Storage een verbinding met een
    /// SQLite-bestand krijgen via <c>SqliteFactory.Instance</c> (de verbinding of een <c>DbDataSource</c>) met een pad dat pas
    /// bij het draaien ontstaat, is JL0002; de niet-generieke <c>DbContextOptions</c> van de server resolven is JL0003 en de
    /// verbindingstekst eruit halen (<c>RelationalOptionsExtension.Extract</c>) is JL0002. Vóór het herstel gaf alleen de
    /// tegenproef <c>new SqliteConnection</c> een melding. Een type uit een tekst halen (<c>Type.GetType("…")</c>) is sinds
    /// herstelronde 6 zelf JL0002 (omweg, R-HARDE-EIS-13); daarmee is zonder reflectie of dynamic geen verbinding te gebruiken.
    /// </summary>
    [Fact]
    public async Task DatabaseverbindingBuitenDeOpslag_ProevenH15EnH16_IsJL0002OfJL0003()
    {
        const string Bron = """
            using System;
            using System.IO;
            using MediaBrowser.Common.Configuration;
            using Microsoft.Data.Sqlite;
            using Microsoft.EntityFrameworkCore;
            using Microsoft.EntityFrameworkCore.Infrastructure;
            using Microsoft.Extensions.DependencyInjection;

            namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
            {
                public class H15
                {
                    public void Sqlitefabriek(IApplicationPaths paden)
                    {
                        /*WL*/ var pad = Path.Combine(paden.DataPath, string.Concat("jellyfin", ".db"));
                        using var c = SqliteFactory.Instance.CreateConnection(); c.ConnectionString = "Data Source=" + pad; c.Open(); // JL0002
                        using var cmd = c.CreateCommand(); cmd.CommandText = "DELETE FROM UserData"; cmd.ExecuteNonQuery(); // JL0002
                        using var bron = SqliteFactory.Instance.CreateDataSource("Data Source=" + pad); // JL0002
                        using var tegen = new SqliteConnection("Data Source=" + pad); // JL0002
                    }

                    public string? Opties(IServiceProvider sp)
                    {
                        var opties = sp.GetRequiredService<DbContextOptions>(); // JL0003
                        _ = sp.GetService(Type.GetType("Microsoft.EntityFrameworkCore.DbContextOptions, Microsoft.EntityFrameworkCore")!); // JL0002
                        return RelationalOptionsExtension.Extract(opties).ConnectionString; // JL0002
                    }
                }

                public static class H16
                {
                    public static int Wis(string data)
                    {
                        using var c = SqliteFactory.Instance.CreateConnection(); // JL0002
                        c.ConnectionString = "Data Source=" + Path.Combine(data, string.Concat("jellyfin", ".db")); // JL0002
                        c.Open(); // JL0002
                        using var cmd = c.CreateCommand(); // JL0002
                        cmd.CommandText = "DELETE FROM UserData";
                        return cmd.ExecuteNonQuery();
                    }
                }
            }
            """;
        var verwacht = Bron.Split('\n').Select((tekst, index) => (Regel: index + 1, Raak: Regex.Match(tekst, @"// (JL\d{4})$")))
            .Where(r => r.Raak.Success).Select(r => (r.Regel, Id: r.Raak.Groups[1].Value)).ToList();

        var alles = await AnalyzerHarnas.AnalyseerAsync(Bron, null, TestContext.Current.CancellationToken);
        var gevonden = alles.Where(b => !AnalyzerHarnas.IsWitteLijst(b)).ToList();

        // Sinds herstelronde 7: IApplicationPaths.DataPath staat voor deze klasse niet op de witte lijst (JL0001).
        Assert.Equal(AnalyzerHarnas.WlRegels(Bron), AnalyzerHarnas.WlGevonden(alles));
        Assert.Single(AnalyzerHarnas.WlRegels(Bron));
        Assert.Equal(11, verwacht.Count);
        Assert.Equal(verwacht, gevonden.Select(b => (b.Regel, b.Id)).Distinct());
        Assert.Contains(gevonden, b => b.Tekst.Contains("'Microsoft.Data.Sqlite.SqliteFactory.Instance'", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("'Microsoft.EntityFrameworkCore.DbContextOptions'", StringComparison.Ordinal));
        Assert.Contains(gevonden, b => b.Tekst.Contains("'Microsoft.EntityFrameworkCore.Infrastructure.RelationalOptionsExtension.Extract'", StringComparison.Ordinal));
    }

    /// <summary>
    /// R-HARDE-EIS-12 (S-G1-17, herstelronde 5): de regel is generiek. Elke gevonden weg naar een verbinding of bron (uit de
    /// zoektocht over de compile-assets van de plugin en de plugin-ABI, ADR-0032 kop "Databasetoegang") is buiten Core.Storage
    /// JL0002: Microsoft.Data.Sqlite, System.Data.Common (fabrieken, bronnen, <c>BackupDatabase</c>, <c>ConnectionString</c>, <c>DbCommand.Connection</c>,
    /// omzettingen en patronen), SQLitePCL (<c>raw.sqlite3_open</c>, <c>Handle</c>), Entity Framework Core (bouwers, opties, context,
    /// <c>GetDbConnection</c>, registratie in de container en een onderschepper die de verbinding van de server krijgt) en een
    /// verbinding uit een eigen terugroep halen. In Core.Storage geeft dezelfde bron geen databasemelding, en een gekregen
    /// verbinding doorgeven of een databasetype als parametertype blijft overal toegestaan. Alleen <c>Activator.CreateInstance</c>
    /// is sinds herstelronde 6 ook in Core.Storage JL0002, als omweg (R-HARDE-EIS-13); buiten Core.Storage blijft het één melding.
    /// </summary>
    [Fact]
    public async Task Databasetoegang_ElkeWegIsBuitenCoreStorageJL0002()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using System.Data;
            using System.Data.Common;
            using System.IO;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Data.Sqlite;
            using Microsoft.EntityFrameworkCore;
            using Microsoft.EntityFrameworkCore.Diagnostics;
            using Microsoft.EntityFrameworkCore.Infrastructure;
            using Microsoft.Extensions.DependencyInjection;

            namespace {{ruimte}}
            {
                public class Toegang
                {
                    public async Task Verbinding(string pad, IServiceProvider diensten, SqliteConnection gekregen, DbCommand opdracht, object iets, CancellationToken stop)
                    {
                        using var a = SqliteFactory.Instance.CreateConnection(); // JL0002
                        a.ConnectionString = "Data Source=" + pad; // JL0002
                        a.Open(); // JL0002
                        using var b = SqliteFactory.Instance.CreateDataSource("Data Source=" + pad); // JL0002
                        using var c = b.CreateConnection(); // JL0002
                        await using var d = await b.OpenConnectionAsync(stop); // JL0002
                        var fabriek = DbProviderFactories.GetFactory("Microsoft.Data.Sqlite"); // JL0002
                        _ = diensten.GetService<DbProviderFactory>(); // JL0002
                        _ = diensten.GetService(typeof(SqliteFactory)); // JL0002
                        _ = Activator.CreateInstance<SqliteConnection>(); // JL0002
                        gekregen.BackupDatabase(gekregen, "main", "main"); // JL0002
                        gekregen.ConnectionString = "Data Source=" + pad; // JL0002
                        _ = gekregen.Handle; // JL0002
                        _ = opdracht.Connection; // JL0002
                        _ = (DbConnection)iets; // JL0002
                        _ = iets as IDbConnection; // JL0002
                        _ = iets is SqliteConnection; // JL0002
                        if (iets is DbConnection f) // JL0002
                        {
                            _ = f;
                        }

                        Func<DbConnection> later = SqliteFactory.Instance.CreateConnection; // JL0002
                        _ = SQLitePCL.raw.sqlite3_open(pad, out var g); // JL0002
                        _ = Met(v => v); // JL0002
                        _ = later;
                        _ = g;
                        _ = fabriek;
                        _ = Met(v => Doorgeven(v));
                        DbConnection h = gekregen;
                        _ = h;
                        _ = Doorgeven(gekregen);
                    }

                    public void Ef(IServiceCollection services, DbContextOptions<DbContext> opties)
                    {
                        _ = new DbContextOptionsBuilder(); // JL0002
                        _ = new DbContextOptionsBuilder<DbContext>(opties); // JL0002
                        _ = opties.FindExtension<RelationalOptionsExtension>(); // JL0002
                        using var ctx = new DbContext(opties); // JL0002
                        _ = ctx.Database.GetDbConnection(); // JL0002
                        services.AddDbContext<DbContext>(o => { }); // JL0002
                        services.AddSingleton<IInterceptor, Onderschepper>(); // JL0002
                    }

                    private static int Doorgeven(SqliteConnection verbinding)
                    {
                        _ = verbinding;
                        return 0;
                    }

                    private static T Met<T>(Func<SqliteConnection, T> werk) => werk(null!);
                }

                public class Onderschepper : DbConnectionInterceptor
                {
                    public override void ConnectionOpened(DbConnection connection, ConnectionEndEventData eventData)
                    {
                        using var opdracht = connection.CreateCommand(); // JL0002
                        opdracht.CommandText = "DELETE FROM UserData";
                        _ = opdracht.ExecuteNonQuery();
                    }
                }
            }
            """;
        var buiten = Bron(Modules + ".Proef");
        var verwacht = buiten.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0002", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(buiten, null, TestContext.Current.CancellationToken);
        var inOpslag = await AnalyzerHarnas.AnalyseerAsync(Bron("Jellyfin.Plugin.JellyLeon.Core.Storage.Proef"), null, TestContext.Current.CancellationToken);
        var inGeheimen = await AnalyzerHarnas.AnalyseerAsync(Bron("Jellyfin.Plugin.JellyLeon.Core.Secrets"), null, TestContext.Current.CancellationToken);

        Assert.Equal(29, verwacht.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.BestandSchrijf, b.Id));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel));
        var omweg = Assert.Single(inOpslag);
        Assert.Equal(Regels.BestandSchrijf, omweg.Id);
        Assert.Contains("'System.Activator.CreateInstance' omzeilt de bouwgrens", omweg.Tekst, StringComparison.Ordinal);
        Assert.Contains(omweg.Regel, verwacht);
        Assert.Equal(verwacht, inGeheimen.Select(b => b.Regel));
    }

    /// <summary>
    /// R-HARDE-EIS-13 (S-G1-17 herstelronde 6), de proef SlippendeRoutes van herreview 5: tien routes waarlangs plugincode
    /// buiten de opslagnamespaces jellyfin.db als bestand kon overschrijven of wissen (de naam ontstaat met
    /// <c>string.Concat</c>, dus JL0003 ziet hem niet). Elke route is nu JL0002: de BCL-routes via de regel op de
    /// namespaces System.IO, System.IO.Compression, System.IO.MemoryMappedFiles en System.Formats.Tar en de schrijvende delen
    /// van System.Xml en System.Data, de server-ABI (IPluginManager, LocalPlugin, IXmlSerializer, ITranscodeManager) en
    /// P/Invoke. Tegenproef: File.Delete en new FileStream geven op dezelfde plek JL0002. In Core.Storage mogen de
    /// BCL-routes (die laag bewaakt de padgrens zelf), maar de server-ABI en P/Invoke nergens.
    /// </summary>
    [Fact]
    public async Task SlippendeBestandsroutes_ProefHerreview5_ElkeRegelIsJL0002()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using System.Data;
            using System.Formats.Tar;
            using System.IO;
            using System.IO.Compression;
            using System.IO.MemoryMappedFiles;
            using System.Runtime.InteropServices;
            using System.Threading;
            using System.Threading.Tasks;
            using System.Xml;
            using System.Xml.Linq;
            using MediaBrowser.Common.Configuration;
            using MediaBrowser.Common.Plugins;
            using MediaBrowser.Controller.MediaEncoding;
            using MediaBrowser.Controller.Streaming;
            using MediaBrowser.Model.Serialization;

            namespace {{ruimte}}
            {
                public class Routes
                {
                    [DllImport("libc")] private static extern int unlink(string pad); // BCL-NEE JL0002

                    public async Task Slip(IApplicationPaths paden, IPluginManager plugins, IXmlSerializer xml, ITranscodeManager transcode, StreamState staat, string bron)
                    {
                        /*WL*/ var db = Path.Combine(paden.DataPath, string.Concat("jellyfin", ".db"));
                        /*WL*/ _ = plugins.RemovePlugin(new LocalPlugin(paden.DataPath, true, new PluginManifest())); // BCL-NEE JL0002
                        xml.SerializeToFile(new object(), db); // BCL-NEE JL0002
                        /*WL*/ ZipFile.ExtractToDirectory(bron, paden.DataPath, overwriteFiles: true); // BCL JL0002
                        /*WL*/ TarFile.ExtractToDirectory(bron, paden.DataPath, overwriteFiles: true); // BCL JL0002
                        using (var w = XmlWriter.Create(db)) { } // BCL JL0002
                        new XDocument().Save(db); // BCL JL0002
                        new DataSet().WriteXml(db); // BCL JL0002
                        using var mm = MemoryMappedFile.CreateFromFile(db, FileMode.Open); // BCL JL0002
                        mm.CreateViewAccessor().Write(0, (byte)0); // BCL JL0002
                        _ = await transcode.StartFfMpeg(staat, db, "-y " + db, Guid.Empty, TranscodingJobType.Progressive, new CancellationTokenSource()); // BCL-NEE JL0002
                        _ = unlink(db); // BCL-NEE JL0002
                    }

                    public void Tegenproef(string db)
                    {
                        File.Delete(db); // BCL JL0002
                        using var a = new FileStream(db, FileMode.Create); // BCL JL0002
                    }
                }
            }
            """;
        static int[] Gemarkeerd(string bron, string merk) => bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst))
            .Where(r => r.tekst.Contains(merk, StringComparison.Ordinal)).Select(r => r.Regel).ToArray();

        var buiten = Bron(Modules + ".Proef");
        var verwacht = Gemarkeerd(buiten, " JL0002");
        var nergens = Gemarkeerd(buiten, "// BCL-NEE JL0002");

        var alles = await AnalyzerHarnas.AnalyseerAsync(buiten, null, TestContext.Current.CancellationToken);
        var allesInOpslag = await AnalyzerHarnas.AnalyseerAsync(Bron("Jellyfin.Plugin.JellyLeon.Core.Storage"), null, TestContext.Current.CancellationToken);
        var gevonden = alles.Where(b => !AnalyzerHarnas.IsWitteLijst(b)).ToList();
        var inOpslag = allesInOpslag.Where(b => !AnalyzerHarnas.IsWitteLijst(b)).ToList();

        // Sinds herstelronde 7, ook in Core.Storage: DataPath en new PluginManifest staan voor deze klasse niet op de witte
        // lijst van de server-ABI (JL0001).
        Assert.Equal(4, AnalyzerHarnas.WlRegels(buiten).Count);
        Assert.Equal(AnalyzerHarnas.WlRegels(buiten), AnalyzerHarnas.WlGevonden(alles));
        Assert.Equal(AnalyzerHarnas.WlRegels(buiten), AnalyzerHarnas.WlGevonden(allesInOpslag));
        Assert.Equal(14, verwacht.Length);
        Assert.Equal(5, nergens.Length);
        Assert.All(gevonden, b => Assert.Equal(Regels.BestandSchrijf, b.Id));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel).Distinct());
        Assert.All(inOpslag, b => Assert.Equal(Regels.BestandSchrijf, b.Id));
        Assert.Equal(nergens, inOpslag.Select(b => b.Regel).Distinct());
    }

    /// <summary>
    /// R-HARDE-EIS-13 (S-G1-17 herstelronde 6): de regel op de bestandsnamespaces. Buiten de opslagnamespaces is elk gebruik
    /// van een type uit System.IO (met de subnamespaces), System.Formats.Tar en de bestandslaag van Visual Basic JL0002,
    /// behalve de kleine witte lijst (padbewerking, lezen, en een stroom of lezer/schrijver die de code al heeft). Ook een
    /// eigen of upstream-type dat van StreamWriter afleidt en een pad meekrijgt, en de schrijvende delen van System.Xml,
    /// System.Data en een paar BCL-schrijvers buiten System.IO. Tegenproef: de toegestane regels geven niets, en in
    /// Core.Storage geeft dezelfde bron niets (die laag bewaakt de padgrens zelf).
    /// </summary>
    [Fact]
    public async Task Bestandsnamespaces_ElkGebruikBuitenDeWitteLijstIsJL0002()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using System.Data;
            using System.Diagnostics;
            using System.IO;
            using System.IO.Compression;
            using System.IO.IsolatedStorage;
            using System.IO.Pipes;
            using System.Net;
            using System.Resources;
            using System.Runtime;
            using System.Text;
            using System.Threading.Tasks;
            using System.Xml;
            using System.Xml.Linq;
            using System.Xml.Serialization;
            using System.Xml.Xsl;
            using Jellyfin.Extensions;

            namespace {{ruimte}}
            {
                public class EigenSchrijver : StreamWriter
                {
                    public EigenSchrijver(string pad) : base(pad) // JL0002
                    {
                    }
                }

                public class EigenStroom : MemoryStream
                {
                }

                public class Bestanden
                {
                    public async Task M(string pad, Stream stroom, byte[] inhoud)
                    {
                        _ = Path.GetTempFileName(); // JL0002
                        using var a = File.OpenHandle(pad, FileMode.Open, FileAccess.ReadWrite); // JL0002
                        RandomAccess.Write(a, inhoud, 0); // JL0002
                        using var b = new FileSystemWatcher(pad); // JL0002
                        using var c = IsolatedStorageFile.GetUserStoreForApplication(); // JL0002
                        using var d = new NamedPipeServerStream(pad); // JL0002
                        using var e = new GZipStream(stroom, CompressionLevel.Fastest); // JL0002
                        using var f = new FormattingStreamWriter(pad, System.Globalization.CultureInfo.InvariantCulture); // JL0002
                        using var g = new EigenSchrijver(pad); // JL0002
                        _ = new FileStreamOptions(); // JL0002
                        Microsoft.VisualBasic.FileIO.FileSystem.DeleteFile(pad); // JL0002
                        Microsoft.VisualBasic.FileSystem.Kill(pad); // JL0002
                        new WebClient().DownloadFile("http://127.0.0.1/x", pad); // JL0002
                        using var h = new TextWriterTraceListener(pad); // JL0002
                        using var i = new ResourceWriter(pad); // JL0002
                        ProfileOptimization.StartProfile(pad); // JL0002
                        using var j = new XmlTextWriter(pad, Encoding.UTF8); // JL0002
                        new XmlDocument().Save(stroom); // JL0002
                        new XElement("x").Save(pad); // JL0002
                        new XslCompiledTransform().Transform(pad, pad); // JL0002
                        new XmlSerializer(typeof(string)).Serialize(stroom, "x"); // JL0002
                        new DataTable().WriteXml(pad); // JL0002
                        new DataSet().WriteXmlSchema(stroom); // JL0002
                        _ = Path.Combine(pad, "x.json");
                        _ = File.Exists(pad) ? File.ReadAllText(pad) : string.Empty;
                        using var k = new StreamReader(pad);
                        _ = await k.ReadToEndAsync();
                        _ = new FileInfo(pad).Length;
                        _ = Directory.Exists(pad);
                        using var l = new MemoryStream();
                        await l.WriteAsync(inhoud);
                        await stroom.WriteAsync(inhoud);
                        await stroom.CopyToAsync(l);
                        using var m = new StreamWriter(stroom, Encoding.UTF8, 1024, leaveOpen: true);
                        await m.WriteAsync("x");
                        using var n = new BinaryWriter(l);
                        n.Write(1);
                        using var o = new EigenStroom();
                        _ = FileMode.Create;
                        _ = new IOException("x");
                        var sb = new StringBuilder();
                        using (var p = XmlWriter.Create(sb)) { new XDocument(new XElement("x")).Save(p); }
                        _ = XDocument.Parse("<x/>").ToString();
                        _ = Stream.Null;
                    }
                }
            }
            """;
        var buiten = Bron(Modules + ".Proef");
        var verwacht = buiten.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0002", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(buiten, null, TestContext.Current.CancellationToken);
        var inOpslag = await AnalyzerHarnas.AnalyseerAsync(Bron("Jellyfin.Plugin.JellyLeon.Core.Storage"), null, TestContext.Current.CancellationToken);

        Assert.Equal(24, verwacht.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.BestandSchrijf, b.Id));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel).Distinct());

        // In Core.Storage geldt de bestandsregel niet, de witte lijst van de server-ABI wel (herstelronde 7):
        // FormattingStreamWriter komt uit Jellyfin.Extensions en staat voor deze klasse niet op de lijst. WebClient is daar
        // sinds herstelronde 8 een netwerkclient (JL0001, nergens buiten een transportklasse; ADR-0032, "HTTP-laag en netwerk").
        var serverAbi = Assert.Single(inOpslag, AnalyzerHarnas.IsWitteLijst);
        Assert.Contains("'Jellyfin.Extensions.FormattingStreamWriter..ctor'", serverAbi.Tekst, StringComparison.Ordinal);
        var webClient = buiten.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Single(r => r.tekst.Contains("new WebClient()", StringComparison.Ordinal)).Regel;
        Assert.Equal(2, inOpslag.Count(b => b.Regel == webClient && b.Id == Regels.ServerSchrijf && b.Tekst.Contains("is een netwerkclient", StringComparison.Ordinal)));
        Assert.Equal(3, inOpslag.Count);
    }

    /// <summary>
    /// R-HARDE-EIS-13 (S-G1-17 herstelronde 6): de server-ABI die zelf een bestand schrijft, wist of verplaatst of een proces
    /// start, gevonden met de padscan van de plugin-ABI en de bronscan van de server (ADR-0032, kop "Bestanden (JL0002)").
    /// Nergens toegestaan: ook niet in Core.Storage, want de server doet het langs de padgrens heen. De leesleden ernaast
    /// gaven geen melding; sinds herstelronde 7 zijn ze JL0001 (witte lijst van de server-ABI, gemarkeerd met /*WL*/).
    /// <c>BaseItemExtensions.SetImagePath</c> wijzigt een item en is JL0001.
    /// </summary>
    [Fact]
    public async Task ServerAbiDieZelfSchrijftOfStart_IsNergensToegestaan()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using System.IO;
            using System.Threading;
            using System.Threading.Tasks;
            using Jellyfin.Extensions;
            using Jellyfin.MediaEncoding.Keyframes.FfProbe;
            using MediaBrowser.Common.Configuration;
            using MediaBrowser.Common.Plugins;
            using MediaBrowser.Common.Updates;
            using MediaBrowser.Controller.ClientEvent;
            using MediaBrowser.Controller.Drawing;
            using MediaBrowser.Controller.Entities;
            using MediaBrowser.Controller.Entities.Movies;
            using MediaBrowser.Controller.IO;
            using MediaBrowser.Controller.Library;
            using MediaBrowser.Controller.LiveTv;
            using MediaBrowser.Controller.MediaEncoding;
            using MediaBrowser.Controller.Providers;
            using MediaBrowser.Controller.Streaming;
            using MediaBrowser.Model.Drawing;
            using MediaBrowser.Model.Entities;
            using MediaBrowser.Model.IO;
            using MediaBrowser.Model.Serialization;
            using Microsoft.Extensions.Logging.Abstractions;

            namespace {{ruimte}}
            {
                public class ServerAbi
                {
                    public async Task M(string pad, IPluginManager plugins, IInstallationManager installatie, IApplicationPaths paden, IXmlSerializer xml,
                        IShortcutHandler snelkoppeling, IFileSystem bestandssysteem, IDirectoryService mappen, IMetadataSaver opslaan,
                        IRemoteMetadataProvider<Movie, MovieInfo> leverancier, IDynamicImageProvider afbeeldingen, ITranscodeManager transcode,
                        IMediaEncoder encoder, ISubtitleEncoder ondertitels, IAttachmentExtractor bijlagen, EncodingHelper hulp, EncodingJobInfo taak,
                        IImageProcessor beelden, IImageEncoder beeldencoder, IClientEventLogger log, IListingsProvider gids, ITunerHost tuner,
                        ILiveStream live, BaseItem item, Stream stroom, CancellationToken stop)
                    {
                        /*WL*/ _ = plugins.RemovePlugin(plugins.GetPlugin(Guid.Empty)!); // JL0002
                        /*WL*/ _ = plugins.SaveManifest(new PluginManifest(), pad); // JL0002
                        /*WL*/ _ = plugins.Plugins;
                        /*WL*/ installatie.UninstallPlugin(new LocalPlugin(pad, true, new PluginManifest())); // JL0002
                        paden.CreateAndCheckMarker(pad, "x"); // JL0002
                        /*WL*/ _ = paden.DataPath;
                        xml.SerializeToFile(new object(), pad); // JL0002
                        /*WL*/ _ = xml.DeserializeFromFile(typeof(object), pad);
                        using var a = AsyncFile.Create(pad); // JL0002
                        using var b = AsyncFile.OpenWrite(pad); // JL0002
                        /*WL*/ using var c = AsyncFile.OpenRead(pad);
                        snelkoppeling.Create(pad, pad); // JL0002
                        /*WL*/ _ = snelkoppeling.Resolve(pad);
                        FileSystemHelper.DeleteFile(bestandssysteem, pad, NullLogger.Instance); // JL0002
                        /*WL*/ _ = FileSystemHelper.ResolveLinkTarget(pad);
                        FileHelper.CreateEmpty(pad); // JL0002
                        mappen.Move(pad, pad); // JL0002
                        /*WL*/ _ = mappen.GetFiles(pad);
                        await opslaan.SaveAsync(item, stop); // JL0002
                        /*WL*/ _ = await leverancier.GetMetadata(new MovieInfo(), stop); // JL0002
                        _ = await afbeeldingen.GetImage(item, ImageType.Primary, stop); // JL0002
                        /*WL*/ _ = afbeeldingen.Supports(item);
                        await transcode.KillTranscodingJobs("x", null, _ => true); // JL0002
                        /*WL*/ var job = transcode.GetTranscodingJob("x");
                        job!.Path = pad; // JL0002
                        _ = new TranscodingJob(NullLogger<TranscodingJob>.Instance); // JL0002
                        using var d = new ProgressiveFileStream(pad, job, transcode); // JL0002
                        await encoder.ConvertImage(pad, pad); // JL0002
                        _ = await encoder.GetMediaInfo(null!, stop); // JL0002
                        /*WL*/ _ = encoder.SupportsEncoder("x");
                        _ = await ondertitels.GetSubtitles(item, "x", 0, "srt", 0, 0, false, stop); // JL0002
                        await bijlagen.ExtractAllAttachments(pad, null!, stop); // JL0002
                        _ = hulp.GetInputArgument(taak, null!, "ts"); // JL0002
                        beelden.CreateImageCollage(null!, null); // JL0002
                        /*WL*/ _ = beelden.GetImageDimensions(pad);
                        _ = beeldencoder.EncodeImage(pad, DateTime.UtcNow, pad, false, null, 90, null!, ImageFormat.Jpg); // JL0002
                        _ = await log.WriteDocumentAsync("x", "1", stroom); // JL0002
                        _ = FfProbeKeyframeExtractor.GetKeyframeData(pad, pad); // JL0002
                        _ = await gids.GetChannels(null!, stop); // JL0002
                        _ = await tuner.GetChannels(false, stop); // JL0002
                        await live.Open(stop); // JL0002
                        /*WL*/ _ = live.GetStream();
                        item.SetImagePath(ImageType.Primary, pad); // JL0001
                        /*WL*/ _ = item.GetImagePath(ImageType.Primary);
                    }
                }
            }
            """;
        static (int Regel, string Id)[] Verwacht(string bron) => bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst))
            .Where(r => r.tekst.EndsWith("// JL0002", StringComparison.Ordinal) || r.tekst.EndsWith("// JL0001", StringComparison.Ordinal))
            .Select(r => (r.Regel, r.tekst[^6..])).ToArray();

        var buiten = Bron(Modules + ".Proef");
        var opslag = Bron("Jellyfin.Plugin.JellyLeon.Core.Storage");

        var alles = await AnalyzerHarnas.AnalyseerAsync(buiten, null, TestContext.Current.CancellationToken);
        var allesInOpslag = await AnalyzerHarnas.AnalyseerAsync(opslag, null, TestContext.Current.CancellationToken);
        var gevonden = alles.Where(b => !AnalyzerHarnas.IsWitteLijst(b)).ToList();
        var inOpslag = allesInOpslag.Where(b => !AnalyzerHarnas.IsWitteLijst(b)).ToList();

        // Sinds herstelronde 7 zijn ook de leesleden ernaast JL0001, overal: de server-ABI is een witte lijst per klasse en
        // geen van deze leden staat er voor deze klasse op (ook het aanmaken van PluginManifest en MovieInfo niet).
        Assert.Equal(17, AnalyzerHarnas.WlRegels(buiten).Count);
        Assert.Equal(AnalyzerHarnas.WlRegels(buiten), AnalyzerHarnas.WlGevonden(alles));
        Assert.Equal(AnalyzerHarnas.WlRegels(opslag), AnalyzerHarnas.WlGevonden(allesInOpslag));
        Assert.Equal(31, Verwacht(buiten).Length);
        Assert.Equal(Verwacht(buiten), gevonden.Select(b => (b.Regel, b.Id)).Distinct());
        Assert.Equal(Verwacht(opslag), inOpslag.Select(b => (b.Regel, b.Id)).Distinct());
    }

    /// <summary>
    /// R-HARDE-EIS-13 (S-G1-17 herstelronde 6), dreigingsmodel van ADR-0032: de omwegen langs de bouwgrens zijn nergens
    /// toegestaan (JL0002): P/Invoke (<c>[DllImport]</c>, <c>[LibraryImport]</c>, <c>extern</c>, ook de aanroep),
    /// <c>unsafe</c> en functiewijzers, <c>NativeLibrary</c> en <c>Marshal</c>, reflectie die een lid aanroept of een type
    /// uit een tekst haalt, code laden, een object van een willekeurig type maken, <c>dynamic</c> en System.Reflection.Emit.
    /// De reflectie die de plugin gebruikt (versie en kenmerken van de eigen assembly, de naam van een type) blijft toegestaan.
    /// </summary>
    [Fact]
    public async Task Omwegen_NativeCodeReflectieEnDynamic_ZijnNergensToegestaan()
    {
        static string Bron(string ruimte) => $$"""
            using System;
            using System.Linq.Expressions;
            using System.Reflection;
            using System.Reflection.Emit;
            using System.Runtime.InteropServices;
            using System.Runtime.Loader;
            using Microsoft.Extensions.DependencyInjection;

            namespace {{ruimte}}
            {
                public static partial class Native
                {
                    [DllImport("libc")] private static extern int unlink(string pad); // JL0002
                    [LibraryImport("libc", StringMarshalling = StringMarshalling.Utf8)] private static partial int rmdir(string pad); private static partial int rmdir(string pad) => 0; // JL0002
                    private static unsafe int Wijzer(delegate* unmanaged<int> f) => f(); // JL0002

                    public static void M(string pad, object iets, Type type, MethodInfo methode, PropertyInfo eigenschap, FieldInfo veld, Delegate d, IServiceProvider diensten)
                    {
                        _ = unlink(pad); // JL0002
                        Func<string, int> f = rmdir; // JL0002
                        var bib = NativeLibrary.Load("libc"); // JL0002
                        _ = Marshal.GetDelegateForFunctionPointer<Func<int>>(bib); // JL0002
                        _ = methode.Invoke(null, new object[] { pad }); // JL0002
                        _ = typeof(System.IO.FileStream).GetConstructors()[0].Invoke(new object[] { pad }); // JL0002
                        eigenschap.SetValue(iets, pad); // JL0002
                        _ = veld.GetValue(iets); // JL0002
                        _ = Type.GetType("System.IO.File"); // JL0002
                        _ = type.InvokeMember("Delete", BindingFlags.InvokeMethod, null, null, new object[] { pad }); // JL0002
                        _ = Assembly.LoadFrom(pad); // JL0002
                        _ = AssemblyLoadContext.Default.LoadFromAssemblyPath(pad); // JL0002
                        _ = Activator.CreateInstance(typeof(System.IO.FileStream), pad, System.IO.FileMode.Create); // JL0002
                        _ = ActivatorUtilities.CreateInstance(diensten, typeof(object)); // JL0002
                        _ = d.DynamicInvoke(pad); // JL0002
                        _ = methode.CreateDelegate<Action<string>>(); // JL0002
                        _ = Expression.Lambda<Func<int>>(Expression.Constant(1)).Compile(); // JL0002
                        dynamic x = iets;
                        x.Delete(pad); // JL0002
                        _ = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("x"), AssemblyBuilderAccess.Run); // JL0002
                        unsafe { int* p = null; _ = p == null; } // JL0002
                        _ = typeof(Native).Assembly.GetName().Version;
                        _ = typeof(Native).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>();
                        _ = iets.GetType().Name;
                        _ = typeof(Native).Namespace;
                        _ = diensten.GetService(typeof(object));
                        Action a = () => { };
                        a.Invoke();
                    }
                }
            }
            """;
        var buiten = Bron(Modules + ".Proef");
        var verwacht = buiten.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0002", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(buiten, null, TestContext.Current.CancellationToken);
        var inOpslag = await AnalyzerHarnas.AnalyseerAsync(Bron("Jellyfin.Plugin.JellyLeon.Core.Storage"), null, TestContext.Current.CancellationToken);

        Assert.Equal(23, verwacht.Count);
        Assert.All(gevonden.Concat(inOpslag), b => Assert.Equal(Regels.BestandSchrijf, b.Id));
        Assert.All(gevonden, b => Assert.Contains("omzeilt de bouwgrens", b.Tekst, StringComparison.Ordinal));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel).Distinct());
        Assert.Equal(verwacht, inOpslag.Select(b => b.Regel).Distinct());
    }

    /// <summary>Een leesvoorvoegsel geldt alleen als heel woord: <c>CancelTimer</c> begint met "Can" maar leest niet.</summary>
    [Fact]
    public void Leesvoorvoegsel_GeldtAlleenOpEenWoordgrens()
    {
        var regel = new TypeRegel(Regels.ServerSchrijf, "X", true, false, "Get", "Can", "To", "Is", "Supports");

        foreach (var lid in new[] { "Cancel", "CancelTimer", "CancelIfRunningAndQueue", "Toggle", "Issue", "Getaway", "Supportsx" })
        {
            Assert.True(regel.IsVerboden(lid), lid);
        }

        foreach (var lid in new[] { "GetItem", "Get", "CanRefresh", "ToString", "IsEnabled", "Supports", "Get2" })
        {
            Assert.False(regel.IsVerboden(lid), lid);
        }
    }

    /// <summary>
    /// Core.Storage en Core.Secrets mogen bestanden schrijven; een databaseverbinding maken mag sinds herstelronde 5
    /// (R-HARDE-EIS-12) alleen Core.Storage: in Core.Secrets is <c>new SqliteConnection</c> JL0002.
    /// </summary>
    [Fact]
    public async Task Opslagnamespaces_MogenBestandenSchrijven_MaarGeenServerApiOfProces()
    {
        foreach (var (ruimte, verwacht) in new[]
        {
            ("Jellyfin.Plugin.JellyLeon.Core.Storage", new[] { Regels.ServerSchrijf, Regels.ProcesStart, Regels.ServerDatabase }),
            ("Jellyfin.Plugin.JellyLeon.Core.Secrets", new[] { Regels.BestandSchrijf, Regels.ServerSchrijf, Regels.ProcesStart, Regels.ServerDatabase }),
        })
        {
            var bron = AnalyzerHarnas.Klasse(ruimte, "Proefopslag", """
                public void M(string pad, ILibraryManager lib, BaseItem item)
                {
                    File.WriteAllText(pad, "x");
                    File.Delete(pad);
                    Directory.CreateDirectory(pad);
                    using var a = new FileStream(pad, FileMode.Create);
                    using var b = new SqliteConnection("Data Source=" + pad);
                    lib.DeleteItem(item, null!);
                    using var c = Process.Start("ffmpeg", "-version");
                    var d = "jellyfin.db";
                }
                """);

            var gevonden = (await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken)).Select(b => b.Id).ToList();

            Assert.Equal(verwacht, gevonden);
        }
    }

    [Fact]
    public async Task Werkernamespace_MagProcessenStarten_MaarGeenBestandenSchrijven()
    {
        var bron = AnalyzerHarnas.Klasse("Jellyfin.Plugin.JellyLeon.Core.Werker", "Proefbewaker", """
            public void M(string pad)
            {
                using var a = Process.Start(new ProcessStartInfo("python3"));
                File.WriteAllText(pad, "x");
            }
            """);

        var gevonden = (await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken)).Select(b => b.Id).ToList();

        Assert.Equal(new[] { Regels.BestandSchrijf }, gevonden);
    }

    /// <summary>
    /// Bestanden lezen en processen bekijken mag overal. Lezen van de server-ABI mag sinds herstelronde 7 (besluit regisseur,
    /// R-HARDE-EIS-14) alleen nog via de witte lijst per klasse (ADR-0032, kop "Server-ABI: witte lijst"): in een moduleklasse
    /// zonder regel op die lijst is elk leeslid van de server JL0001, ook GetVirtualFolders (dat staat alleen voor
    /// Core.BibliotheekMappen op de lijst).
    /// </summary>
    [Fact]
    public async Task LezenVanBestandenMagOveral_LezenVanDeServerAlleenViaDeWitteLijst()
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Quality", "Lezer", """
            public void M(string pad, ILibraryManager lib, IUserDataManager gegevens, IUserManager gebruikers, User gebruiker, BaseItem item)
            {
                /*WL*/ _ = lib.GetItemById(Guid.Empty);
                /*WL*/ _ = lib.GetVirtualFolders();
                /*WL*/ _ = gegevens.GetUserData(gebruiker, item);
                /*WL*/ _ = gebruikers.GetUserById(Guid.Empty);
                _ = File.Exists(pad) ? File.ReadAllBytes(pad).Length : 0;
                using var a = File.OpenRead(pad);
                _ = Directory.EnumerateFiles(pad);
                _ = new FileInfo(pad).Length;
                _ = Process.GetCurrentProcess().Id;
            }
            """);

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

        Assert.All(gevonden, b => Assert.True(AnalyzerHarnas.IsWitteLijst(b), b.Tekst));
        Assert.Equal(4, AnalyzerHarnas.WlRegels(bron).Count);
        Assert.Equal(AnalyzerHarnas.WlRegels(bron), AnalyzerHarnas.WlGevonden(gevonden));
    }

    [Fact]
    public async Task Uitzondering_GeldtVoorPreciesEenApiInPreciesEenKlasse()
    {
        const string Romp = """
            public void Toegestaan(IUserDataManager gegevens, User gebruiker, BaseItem item)
            {
                gegevens.ResetPlaybackStreamSelections(gebruiker, item);
                Action later = () => gegevens.ResetPlaybackStreamSelections(gebruiker, item);
                later();
            }

            public void NietGenoemd(IUserDataManager gegevens, User gebruiker, BaseItem item)
            {
                gegevens.UpdatePlayState(item, null!, null);
            }

            private sealed class Genest
            {
                public void M(IUserDataManager gegevens, User gebruiker, BaseItem item) => gegevens.ResetPlaybackStreamSelections(gebruiker, item);
            }
            """;
        var witteLijst = "# F3\n" + Regels.ServerSchrijf + " " + Reset + " " + SelectionGuard + "\n";

        var inDeKlasse = await AnalyzerHarnas.AnalyseerAsync(AnalyzerHarnas.Klasse(Modules + ".Subtitles.Publication", "SelectionGuard", Romp), witteLijst, TestContext.Current.CancellationToken);
        var inEenAndereKlasse = await AnalyzerHarnas.AnalyseerAsync(AnalyzerHarnas.Klasse(Modules + ".Subtitles.Publication", "Anders", Romp), witteLijst, TestContext.Current.CancellationToken);
        var zonderLijst = await AnalyzerHarnas.AnalyseerAsync(AnalyzerHarnas.Klasse(Modules + ".Subtitles.Publication", "SelectionGuard", Romp), null, TestContext.Current.CancellationToken);

        // In de genoemde klasse (ook in een lambda en een geneste klasse) mag alleen de genoemde API.
        var enige = Assert.Single(inDeKlasse);
        Assert.Equal(Regels.ServerSchrijf, enige.Id);
        Assert.Contains("UpdatePlayState", enige.Tekst, StringComparison.Ordinal);
        Assert.Equal(4, inEenAndereKlasse.Count);
        Assert.Equal(4, zonderLijst.Count);
        Assert.All(inEenAndereKlasse.Concat(zonderLijst), b => Assert.Equal(Regels.ServerSchrijf, b.Id));
    }

    [Fact]
    public async Task Uitzondering_BestandVerwijderenInEenGenoemdeKlasse()
    {
        const string Romp = """
            public void M(string pad)
            {
                File.Delete(pad);
                File.WriteAllText(pad, "x");
                using var a = new FileStream(pad, FileMode.Create);
            }
            """;
        var witteLijst = Regels.BestandSchrijf + " System.IO.File.Delete " + Modules + ".Subtitles.Publication.Depublisher";

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(AnalyzerHarnas.Klasse(Modules + ".Subtitles.Publication", "Depublisher", Romp), witteLijst, TestContext.Current.CancellationToken);

        // Alleen File.Delete is vrijgegeven; schrijven en een FileStream openen blijven verboden.
        Assert.Equal(2, gevonden.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.BestandSchrijf, b.Id));
        Assert.DoesNotContain(gevonden, b => b.Tekst.Contains("File.Delete", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData("JL0001 MediaBrowser.Controller.Library.ILibraryManager.UpdateItemAsync " + Modules + ".Subtitles.X", "nergens toegestaan")]
    [InlineData("JL0001 MediaBrowser.Controller.Persistence.IItemPersistenceService.SaveItems " + Modules + ".Subtitles.X", "nergens toegestaan")]
    [InlineData("JL0001 MediaBrowser.Controller.Library.IUserManager.DeleteUserAsync " + Modules + ".Devices.X", "nergens toegestaan")]
    [InlineData("JL0001 MediaBrowser.Controller.IDisplayPreferencesManager.UpdateDisplayPreferences " + Modules + ".Subtitles.X", "nergens toegestaan")]
    [InlineData("JL0001 MediaBrowser.Model.Tasks.ITaskManager.QueueScheduledTask " + Modules + ".Subtitles.X", "nergens toegestaan")]
    [InlineData("JL0001 MediaBrowser.Controller.Library.IMediaSourceManager.GetPlaybackMediaSources " + Modules + ".Quality.X", "nergens toegestaan")]
    [InlineData("JL0004 System.Diagnostics.Process.Start " + Modules + ".Quality.X", "nergens toegestaan")]
    [InlineData("JL0002 Microsoft.Data.Sqlite.SqliteFactory.CreateConnection " + Modules + ".Quality.X", "nergens toegestaan")]
    [InlineData("JL0002 System.Data.Common.DbProviderFactories.GetFactory " + Modules + ".Quality.X", "nergens toegestaan")]
    [InlineData("JL0002 System.IO.Compression.ZipFile.ExtractToDirectory " + Modules + ".Quality.X", "nergens toegestaan")]
    [InlineData("JL0002 System.IO.Path.GetTempFileName " + Modules + ".Quality.X", "nergens toegestaan")]
    [InlineData("JL0002 MediaBrowser.Common.Plugins.IPluginManager.RemovePlugin " + Modules + ".Quality.X", "nergens toegestaan")]
    [InlineData("JL0002 MediaBrowser.Controller.MediaEncoding.ITranscodeManager.StartFfMpeg " + Modules + ".Quality.X", "nergens toegestaan")]
    [InlineData("JL0002 System.Reflection.MethodBase.Invoke " + Modules + ".Quality.X", "nergens toegestaan")]
    [InlineData("JL0003 jellyfin.db " + Modules + ".Quality.X", "niet bewaakt")]
    [InlineData("JL0001 MediaBrowser.Controller.Library.IUserDataManager.GetUserData " + Modules + ".Quality.X", "niet bewaakt")]
    [InlineData("JL0002 MediaBrowser.Controller.Library.IUserDataManager.SaveUserData " + Modules + ".Quality.X", "niet bewaakt")]
    [InlineData("JL0001 " + Reset + " Jellyfin.Plugin.JellyLeon.Core.Connector.X", "precies één klasse")]
    [InlineData("JL0001 " + Reset + " " + Modules + ".*", "precies één klasse")]
    [InlineData("JL0001 " + Reset + " Een.Andere.Plugin.X", "precies één klasse")]
    [InlineData("JL0001 " + Reset, "verwacht:")]
    [InlineData("JL0001 " + Reset + " " + SelectionGuard + " extra", "verwacht:")]
    [InlineData("JL0001 " + Reset + " " + SelectionGuard + "\nJL0001 " + Reset + " " + SelectionGuard, "dubbele regel")]
    [InlineData("JL0001 MediaBrowser.Controller.MediaSegments.IMediaSegmentManager.RunSegmentPluginProviders Jellyfin.Plugin.JellyLeon.Modules.Segments.SegmentPublicatie", "alleen gerichte publicatie")]
    [InlineData("JL0001 MediaBrowser.Controller.MediaSegments.IMediaSegmentManager.DeleteSegmentsAsync Jellyfin.Plugin.JellyLeon.Modules.Segments.SegmentPublicatie", "alleen gerichte publicatie")]
    public async Task OngeldigeUitzonderingsregel_IsEenBouwfoutEnStaatNietsToe(string witteLijst, string reden)
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Quality", "X", "public void M() { }");

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, witteLijst, TestContext.Current.CancellationToken);

        var enige = Assert.Single(gevonden);
        Assert.Equal(Regels.OngeldigeUitzondering, enige.Id);
        Assert.Contains(reden, enige.Tekst, StringComparison.Ordinal);
    }

    [Fact]
    public async Task WitteLijstVanDePlugin_BevatUitsluitendGerichteSegmentpublicatie()
    {
        var tekst = await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, Regels.UitzonderingenBestand), TestContext.Current.CancellationToken);
        var regels = tekst.Split('\n').Select(r => r.Trim()).Where(r => r.Length > 0 && r[0] != '#').ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(AnalyzerHarnas.Klasse(Modules + ".Quality", "X", "public void M() { }"), tekst, TestContext.Current.CancellationToken);

        Assert.Empty(gevonden);
        const string manager = "JL0001 MediaBrowser.Controller.MediaSegments.IMediaSegmentManager.";
        const string klasse = " Jellyfin.Plugin.JellyLeon.Modules.Segments.SegmentPublicatie";
        Assert.Equal([manager + "CreateSegmentAsync" + klasse, manager + "DeleteSegmentAsync" + klasse], regels);
    }

    [Fact]
    public void Regeltabel_ElkBewaaktTypeBestaatInDezeJellyfinVersie()
    {
        // Een hernoemde of verhuisde interface zou de regel stil uitschakelen: deze test blokkeert dan de upstream-sync.
        var compilatie = AnalyzerHarnas.Compileer("namespace Leeg { public class Niets { } }");
        var namen = Regels.Typen.Select(t => t.Type)
            .Concat(Regels.Aanmaak.Select(a => a.Type))
            .Concat(Regels.ServerDatabaseTypen)
            .Concat(Regels.ServerDatabaseTypenExact)
            .Concat(Regels.DatabaseVerbindingTypen)
            .Concat(Regels.BestandWitteLijst.Select(w => w.Type))
            .Concat(Regels.BestandTypen)
            .Distinct(StringComparer.Ordinal)
            .ToList();

        Assert.True(namen.Count >= 20);
        Assert.All(namen, naam => Assert.True(compilatie.GetTypeByMetadataName(naam) is not null, "onbekend type in de regeltabel: " + naam));

        // De databaseassemblies (JL0002, databasetoegang) moeten er ook zijn, anders telt de regel stil niets.
        var assemblies = compilatie.References.Select(r => (compilatie.GetAssemblyOrModuleSymbol(r) as IAssemblySymbol)?.Identity.Name).ToList();
        Assert.All(Regels.DatabaseAssemblies, a => Assert.Contains(assemblies, n => Regels.IsDatabaseAssembly(n) && (n == a || n!.StartsWith(a + ".", StringComparison.Ordinal))));
    }

    [Fact]
    public void Regeltabel_ElkLidVanEenBewaaktServertypeIsBeoordeeld()
    {
        // "Lezen" is op naam bepaald. Een nieuwe upstream-methode die Get… heet en toch schrijft, zou er stil doorheen
        // glippen. Daarom ligt de hele ledenlijst van de bewaakte servertypen vast, met het oordeel erbij: komt er bij
        // een upstream-sync een lid bij of verdwijnt er een, dan faalt deze test tot iemand het oordeel heeft bekeken.
        // Bijwerken: draai de tests één keer met JL_SCHRIJF_BEWAAKTE_LEDEN=1 en lees het verschil in de commit.
        var compilatie = AnalyzerHarnas.Compileer("namespace Leeg { public class Niets { } }");
        // Alleen de servertypen (de BCL-, Microsoft- en reflectieregels volgen de SDK, niet de upstream-sync).
        var regels = Regels.Typen
            .Where(t => t.Type.StartsWith("MediaBrowser.", StringComparison.Ordinal) || t.Type.StartsWith("Jellyfin.", StringComparison.Ordinal))
            .SelectMany(t => compilatie.GetTypeByMetadataName(t.Type)!.GetMembers()
                .OfType<IMethodSymbol>()
                .Where(m => m.MethodKind == MethodKind.Ordinary && m.DeclaredAccessibility == Accessibility.Public)
                .Select(m => m.Name)
                .Distinct(StringComparer.Ordinal)
                .Select(lid => t.Type + "." + lid + " " + (t.IsVerboden(lid) ? "verboden" : "lezen")))
            .OrderBy(r => r, StringComparer.Ordinal)
            .ToList();
        var verwacht = string.Join("\n", regels) + "\n";

        if (Environment.GetEnvironmentVariable("JL_SCHRIJF_BEWAAKTE_LEDEN") == "1")
        {
            File.WriteAllText(LedenBestand(), verwacht);
        }

        var vastgelegd = File.ReadAllText(
            Environment.GetEnvironmentVariable("JL_SCHRIJF_BEWAAKTE_LEDEN") == "1" ? LedenBestand() : Path.Combine(AppContext.BaseDirectory, "BewaakteLeden.txt"));

        Assert.True(regels.Count >= 150, "de ledenlijst is verdacht kort: " + regels.Count);
        Assert.True(
            string.Equals(verwacht, vastgelegd.Replace("\r\n", "\n", StringComparison.Ordinal), StringComparison.Ordinal),
            "De ledenlijst van de bewaakte servertypen is gewijzigd (upstream-sync?). Beoordeel elk nieuw lid: schrijft het, zet het dan in de regeltabel. "
            + "Draai daarna de tests één keer met JL_SCHRIJF_BEWAAKTE_LEDEN=1 en commit Analyzer/BewaakteLeden.txt.");
    }

    private static string LedenBestand([CallerFilePath] string hier = "") =>
        Path.Combine(Path.GetDirectoryName(hier)!, "BewaakteLeden.txt");
}
