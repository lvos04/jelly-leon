using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Analyzers;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Text;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Hulp;

/// <summary>Compileert proefcode tegen dezelfde Jellyfin-assemblies als de plugin en draait de echte analyzer erop.</summary>
internal static class AnalyzerHarnas
{
    private static readonly Lazy<ImmutableArray<MetadataReference>> _referenties = new(() =>
        ((string)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES")!)
            .Split(Path.PathSeparator)
            .Where(p => p.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
            .Select(p => (MetadataReference)MetadataReference.CreateFromFile(p))
            .ToImmutableArray());

    public static CSharpCompilation Compileer(string bron)
    {
        var compilatie = CSharpCompilation.Create(
            "JellyLeonAnalyzerProef",
            new[] { CSharpSyntaxTree.ParseText(bron, new CSharpParseOptions(LanguageVersion.Latest), "Proef.cs") },
            _referenties.Value,
            new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

        // Een proef die niet compileert bewijst niets: dan vindt de analyzer vanzelf niets.
        var fouten = compilatie.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).Select(d => d.ToString()).ToList();
        Assert.True(fouten.Count == 0, "De proefcode compileert niet:\n" + string.Join("\n", fouten));
        return compilatie;
    }

    /// <summary>Geeft per bevinding het regelnummer (1-gebaseerd; 0 = zonder plek) en de regel-id.</summary>
    public static async Task<IReadOnlyList<(int Regel, string Id, string Tekst)>> AnalyseerAsync(string bron, string? uitzonderingen, CancellationToken stop)
    {
        var bestanden = uitzonderingen is null
            ? ImmutableArray<AdditionalText>.Empty
            : ImmutableArray.Create<AdditionalText>(new Tekstbestand("/proef/" + Regels.UitzonderingenBestand, uitzonderingen));
        var metAnalyzer = Compileer(bron).WithAnalyzers(
            ImmutableArray.Create<DiagnosticAnalyzer>(new VerbodenApiAnalyzer()),
            new AnalyzerOptions(bestanden));
        var bevindingen = await metAnalyzer.GetAnalyzerDiagnosticsAsync(stop);
        return bevindingen
            .Select(d => (d.Location == Location.None ? 0 : d.Location.GetLineSpan().StartLinePosition.Line + 1, d.Id, d.GetMessage(System.Globalization.CultureInfo.InvariantCulture)))
            .OrderBy(b => b.Item1).ThenBy(b => b.Id, StringComparer.Ordinal)
            .ToList();
    }

    /// <summary>Proefcode in één klasse; <paramref name="ruimte"/> bepaalt welke regels gelden.</summary>
    public static string Klasse(string ruimte, string klasse, string romp) => $$"""
        using System;
        using System.Diagnostics;
        using System.IO;
        using System.Threading;
        using Jellyfin.Database.Implementations.Entities;
        using MediaBrowser.Controller.Entities;
        using MediaBrowser.Controller.Library;
        using MediaBrowser.Controller.Providers;
        using Microsoft.Data.Sqlite;

        namespace {{ruimte}}
        {
            public class {{klasse}}
            {
                {{romp}}
            }
        }
        """;

    private sealed class Tekstbestand(string pad, string inhoud) : AdditionalText
    {
        public override string Path { get; } = pad;

        public override SourceText GetText(CancellationToken cancellationToken = default) => SourceText.From(inhoud);
    }
}
