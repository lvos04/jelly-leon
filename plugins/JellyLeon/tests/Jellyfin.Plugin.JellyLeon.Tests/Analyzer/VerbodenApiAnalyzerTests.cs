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
