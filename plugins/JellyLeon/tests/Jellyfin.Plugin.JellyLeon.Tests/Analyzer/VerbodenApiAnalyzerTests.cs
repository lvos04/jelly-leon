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
                _ = voorkeuren.ListItemDisplayPreferences(gebruiker, "web");
                _ = hoofdstukken.GetChapters(item);
                _ = sporen.GetMediaStreamLanguages(MediaBrowser.Model.Entities.MediaStreamType.Audio);
                _ = mensen.GetPeopleNames(new InternalPeopleQuery());
            }
            """);

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

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
    /// eerste vijf gemarkeerde regels geen bevinding.
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
                _ = $"jellyfin{".db",6}";
                _ = $"{"jellyfin",-9}.db";
                _ = sb.Append($"{data}/jellyfin{".db",6}");
                _ = "jellyfin" + (int)'.' + "db";
                _ = System.Text.Encoding.UTF8.GetString("jelly-leon.db"u8);
            }
            """);
        var verwacht = bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0003", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

        Assert.Equal(13, verwacht.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.ServerDatabase, b.Id));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel));
    }

    /// <summary>
    /// R-HARDE-EIS-1 (S-G1-17, herstelronde 2): een servertaak starten of de planning ervan wijzigen kan ook via het
    /// taakobject zelf (<c>ITaskManager.ScheduledTasks</c> of <c>IApplicationHost.GetExports</c>). Dat is net zo goed
    /// JL0001; lezen (naam, staat, standaardplanning) blijft toegestaan. Vóór het herstel gaf deze bron geen bevinding.
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
                await taken.ScheduledTasks[0].ScheduledTask.ExecuteAsync(new Progress<double>(), CancellationToken.None); // JL0001
                taken.ScheduledTasks[0].Triggers = Array.Empty<MediaBrowser.Model.Tasks.TaskTriggerInfo>(); // JL0001
                taken.ScheduledTasks[0].ReloadTriggerEvents(); // JL0001
                await taak.ExecuteAsync(new Progress<double>(), CancellationToken.None); // JL0001
                Func<IProgress<double>, CancellationToken, System.Threading.Tasks.Task> later = taak.ExecuteAsync; // JL0001
                werker.Triggers = werker.Triggers; // JL0001
                foreach (var t in host.GetExports<MediaBrowser.Model.Tasks.IScheduledTask>(false)) { await t.ExecuteAsync(new Progress<double>(), CancellationToken.None); } // JL0001
                _ = later;
                _ = taak.GetDefaultTriggers();
                _ = taak.Name + taak.Key + taak.Category;
                _ = werker.Name + werker.State + werker.Id;
                _ = werker.Triggers.Count;
                _ = taken.ScheduledTasks.Count;
            }
            """);
        var verwacht = bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0001", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

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
    /// zelf. De bibliotheek lezen kan via ILibraryManager.GetItemList. Vóór het herstel gaf deze bron geen bevinding.
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
                var opties = new MediaBrowser.Controller.Dto.DtoOptions();
                _ = await live.GetRecordingsAsync(new MediaBrowser.Model.LiveTv.RecordingQuery(), opties); // JL0001
                _ = await live.GetRecordingFoldersAsync(gebruiker); // JL0001
                _ = weergaven.GetLatestItems(new MediaBrowser.Model.Querying.LatestItemsQuery(), opties); // JL0001
                _ = map.GetItems(new InternalItemsQuery(gebruiker)); // JL0001
                _ = map.GetItemList(new InternalItemsQuery(gebruiker)); // JL0001
                _ = map.GetChildCount(gebruiker); // JL0001
                _ = map.GetRecursiveChildCount(gebruiker); // JL0001
                _ = seizoen.GetEpisodes(); // JL0001
                _ = seizoen.GetChildren(gebruiker, true, null); // JL0001
                _ = weergave.GetChildCount(gebruiker); // JL0001
                _ = serie.GetSeasonEpisodes(seizoen, gebruiker, opties, false); // JL0001
                _ = MediaBrowser.Controller.Playlists.Playlist.GetPlaylistItems(Array.Empty<BaseItem>(), gebruiker, opties); // JL0001
                _ = weergave.GetChildren(gebruiker, true, null); // JL0001
                _ = lijst.GetRecursiveChildren(gebruiker, null, out _); // JL0001
                _ = live.IsEnabledForUser(gebruiker);
                _ = weergaven.GetUserViews(new MediaBrowser.Model.Library.UserViewQuery { User = gebruiker });
                _ = lib.GetItemList(new InternalItemsQuery(gebruiker) { Parent = map });
                _ = map.GetChildren(gebruiker, true);
                _ = serie.GetEpisodes(gebruiker, opties, false);
                _ = seizoen.Name;
            }
            """);
        var verwacht = bron.Split('\n').Select((tekst, index) => (Regel: index + 1, tekst)).Where(r => r.tekst.EndsWith("// JL0001", StringComparison.Ordinal)).Select(r => r.Regel).ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken);

        Assert.Equal(14, verwacht.Count);
        Assert.All(gevonden, b => Assert.Equal(Regels.ServerSchrijf, b.Id));
        Assert.Equal(verwacht, gevonden.Select(b => b.Regel));
        Assert.Contains(gevonden, b => b.Tekst.Contains("ILiveTvManager.GetRecordingsAsync'", StringComparison.Ordinal));
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

    [Fact]
    public async Task Opslagnamespaces_MogenBestandenSchrijven_MaarGeenServerApiOfProces()
    {
        foreach (var ruimte in new[] { "Jellyfin.Plugin.JellyLeon.Core.Storage", "Jellyfin.Plugin.JellyLeon.Core.Secrets" })
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

            Assert.Equal(new[] { Regels.ServerSchrijf, Regels.ProcesStart, Regels.ServerDatabase }, gevonden);
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

    [Fact]
    public async Task LezenMagOveral()
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Quality", "Lezer", """
            public void M(string pad, ILibraryManager lib, IUserDataManager gegevens, IUserManager gebruikers, User gebruiker, BaseItem item)
            {
                _ = lib.GetItemById(Guid.Empty);
                _ = lib.GetVirtualFolders();
                _ = gegevens.GetUserData(gebruiker, item);
                _ = gebruikers.GetUserById(Guid.Empty);
                _ = File.Exists(pad) ? File.ReadAllBytes(pad).Length : 0;
                using var a = File.OpenRead(pad);
                _ = Directory.EnumerateFiles(pad);
                _ = new FileInfo(pad).Length;
                _ = Process.GetCurrentProcess().Id;
            }
            """);

        Assert.Empty(await AnalyzerHarnas.AnalyseerAsync(bron, null, TestContext.Current.CancellationToken));
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
    [InlineData("JL0003 jellyfin.db " + Modules + ".Quality.X", "niet bewaakt")]
    [InlineData("JL0001 MediaBrowser.Controller.Library.IUserDataManager.GetUserData " + Modules + ".Quality.X", "niet bewaakt")]
    [InlineData("JL0002 MediaBrowser.Controller.Library.IUserDataManager.SaveUserData " + Modules + ".Quality.X", "niet bewaakt")]
    [InlineData("JL0001 " + Reset + " Jellyfin.Plugin.JellyLeon.Core.Connector.X", "precies één klasse")]
    [InlineData("JL0001 " + Reset + " " + Modules + ".*", "precies één klasse")]
    [InlineData("JL0001 " + Reset + " Een.Andere.Plugin.X", "precies één klasse")]
    [InlineData("JL0001 " + Reset, "verwacht:")]
    [InlineData("JL0001 " + Reset + " " + SelectionGuard + " extra", "verwacht:")]
    [InlineData("JL0001 " + Reset + " " + SelectionGuard + "\nJL0001 " + Reset + " " + SelectionGuard, "dubbele regel")]
    public async Task OngeldigeUitzonderingsregel_IsEenBouwfoutEnStaatNietsToe(string witteLijst, string reden)
    {
        var bron = AnalyzerHarnas.Klasse(Modules + ".Quality", "X", "public void M() { }");

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(bron, witteLijst, TestContext.Current.CancellationToken);

        var enige = Assert.Single(gevonden);
        Assert.Equal(Regels.OngeldigeUitzondering, enige.Id);
        Assert.Contains(reden, enige.Tekst, StringComparison.Ordinal);
    }

    [Fact]
    public async Task WitteLijstVanDePlugin_IsGeldigEnInGolf1Leeg()
    {
        var tekst = await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, Regels.UitzonderingenBestand), TestContext.Current.CancellationToken);
        var regels = tekst.Split('\n').Select(r => r.Trim()).Where(r => r.Length > 0 && r[0] != '#').ToList();

        var gevonden = await AnalyzerHarnas.AnalyseerAsync(AnalyzerHarnas.Klasse(Modules + ".Quality", "X", "public void M() { }"), tekst, TestContext.Current.CancellationToken);

        Assert.Empty(gevonden);
        // Golf 1 (Devices en Quality) heeft geen enkele uitzondering; de eerste komt met F3 en hoort bij een eigen ADR.
        Assert.Empty(regels);
    }

    [Fact]
    public void Regeltabel_ElkBewaaktTypeBestaatInDezeJellyfinVersie()
    {
        // Een hernoemde of verhuisde interface zou de regel stil uitschakelen: deze test blokkeert dan de upstream-sync.
        var compilatie = AnalyzerHarnas.Compileer("namespace Leeg { public class Niets { } }");
        var namen = Regels.Typen.Select(t => t.Type)
            .Concat(Regels.Aanmaak.Select(a => a.Type))
            .Concat(Regels.ServerDatabaseTypen)
            .Distinct(StringComparer.Ordinal)
            .ToList();

        Assert.True(namen.Count >= 20);
        Assert.All(namen, naam => Assert.True(compilatie.GetTypeByMetadataName(naam) is not null, "onbekend type in de regeltabel: " + naam));
    }

    [Fact]
    public void Regeltabel_ElkLidVanEenBewaaktServertypeIsBeoordeeld()
    {
        // "Lezen" is op naam bepaald. Een nieuwe upstream-methode die Get… heet en toch schrijft, zou er stil doorheen
        // glippen. Daarom ligt de hele ledenlijst van de bewaakte servertypen vast, met het oordeel erbij: komt er bij
        // een upstream-sync een lid bij of verdwijnt er een, dan faalt deze test tot iemand het oordeel heeft bekeken.
        // Bijwerken: draai de tests één keer met JL_SCHRIJF_BEWAAKTE_LEDEN=1 en lees het verschil in de commit.
        var compilatie = AnalyzerHarnas.Compileer("namespace Leeg { public class Niets { } }");
        var regels = Regels.Typen
            .Where(t => !t.Type.StartsWith("System.", StringComparison.Ordinal))
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
