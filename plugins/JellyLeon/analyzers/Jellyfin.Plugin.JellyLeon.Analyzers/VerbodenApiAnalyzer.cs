using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Operations;

namespace Jellyfin.Plugin.JellyLeon.Analyzers;

/// <summary>
/// Bewaakt de HARDE EIS bij het bouwen: plugincode schrijft niet in de bibliotheek, de metadata, de kijkgeschiedenis of
/// de gebruikersgegevens van de server, opent de database van de server niet, schrijft geen bestanden buiten de
/// opslagnamespaces en start geen processen buiten de werkerbewaker. Uitzonderingen bestaan alleen per API en per
/// met naam genoemde klasse (bestand <c>JellyLeon.AnalyzerUitzonderingen.txt</c>); elke overtreding is een bouwfout.
/// </summary>
[DiagnosticAnalyzer(LanguageNames.CSharp)]
public sealed class VerbodenApiAnalyzer : DiagnosticAnalyzer
{
    private const string Categorie = "JellyLeon.Gegevensbescherming";

    private static readonly DiagnosticDescriptor _serverSchrijf = new(
        Regels.ServerSchrijf,
        "Schrijvende server-API is verboden",
        "'{0}' wijzigt gegevens van de server (bibliotheek, metadata, kijkgeschiedenis, gebruikers, sessies of instellingen); dat mag hier niet",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _bestandSchrijf = new(
        Regels.BestandSchrijf,
        "Bestanden schrijven mag alleen via de opslaglaag",
        "'{0}' schrijft of verwijdert een bestand buiten Core.Storage en Core.Secrets; gebruik InternalWriteScope of JlDatabase",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _serverDatabase = new(
        Regels.ServerDatabase,
        "De database van de server is verboden terrein",
        "'{0}' raakt de database van de server zelf; plugincode gebruikt alleen de officiële API en de eigen databases",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _procesStart = new(
        Regels.ProcesStart,
        "Processen starten mag alleen in de werkerbewaker",
        "'{0}' start een proces buiten Core.Werker; hulpprogramma's draaien alleen onder de werkerbewaker, nooit via een shell",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _ongeldigeUitzondering = new(
        Regels.OngeldigeUitzondering,
        "Ongeldige uitzonderingsregel voor de analyzer",
        "Uitzonderingsregel '{0}' is ongeldig: {1}",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: new[] { WellKnownDiagnosticTags.NotConfigurable, WellKnownDiagnosticTags.CompilationEnd });

    /// <inheritdoc />
    public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics { get; } =
        ImmutableArray.Create(_serverSchrijf, _bestandSchrijf, _serverDatabase, _procesStart, _ongeldigeUitzondering);

    /// <inheritdoc />
    public override void Initialize(AnalysisContext context)
    {
        // Ook gegenereerde code telt mee: een generator mag de grens evenmin omzeilen.
        context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.Analyze | GeneratedCodeAnalysisFlags.ReportDiagnostics);
        context.EnableConcurrentExecution();
        context.RegisterCompilationStartAction(Start);
    }

    private static void Start(CompilationStartAnalysisContext context)
    {
        var uitzonderingen = Uitzonderingen.Lees(context.Options.AdditionalFiles, context.CancellationToken);
        var toestand = new Toestand(context.Compilation, uitzonderingen);

        context.RegisterOperationAction(c => toestand.Methode(c, ((IInvocationOperation)c.Operation).TargetMethod), OperationKind.Invocation);
        context.RegisterOperationAction(c => toestand.Methode(c, ((IMethodReferenceOperation)c.Operation).Method), OperationKind.MethodReference);
        context.RegisterOperationAction(toestand.Eigenschap, OperationKind.PropertyReference);
        context.RegisterOperationAction(toestand.Aanmaak, OperationKind.ObjectCreation);
        context.RegisterOperationAction(toestand.Letterlijk, OperationKind.Literal);
        context.RegisterSyntaxNodeAction(toestand.Naam, SyntaxKind.IdentifierName);
        context.RegisterCompilationEndAction(c =>
        {
            foreach (var (regel, reden) in uitzonderingen.Fouten)
            {
                c.ReportDiagnostic(Diagnostic.Create(_ongeldigeUitzondering, Location.None, regel, reden));
            }
        });
    }

    private static DiagnosticDescriptor Descriptor(string id) => id switch
    {
        Regels.ServerSchrijf => _serverSchrijf,
        Regels.BestandSchrijf => _bestandSchrijf,
        Regels.ProcesStart => _procesStart,
        _ => _serverDatabase,
    };

    private sealed class Toestand
    {
        private readonly List<(INamedTypeSymbol Type, TypeRegel Regel)> _typen = new();
        private readonly List<(INamedTypeSymbol Type, string RegelId, bool AlleenMetPad)> _aanmaak = new();
        private readonly List<INamedTypeSymbol> _databaseTypen = new();
        private readonly Uitzonderingen _uitzonderingen;

        public Toestand(Compilation compilatie, Uitzonderingen uitzonderingen)
        {
            _uitzonderingen = uitzonderingen;
            foreach (var regel in Regels.Typen)
            {
                if (compilatie.GetTypeByMetadataName(regel.Type) is { } type)
                {
                    _typen.Add((type, regel));
                }
            }

            foreach (var (regelId, naam, alleenMetPad) in Regels.Aanmaak)
            {
                if (compilatie.GetTypeByMetadataName(naam) is { } type)
                {
                    _aanmaak.Add((type, regelId, alleenMetPad));
                }
            }

            foreach (var naam in Regels.ServerDatabaseTypen)
            {
                if (compilatie.GetTypeByMetadataName(naam) is { } type)
                {
                    _databaseTypen.Add(type);
                }
            }
        }

        public void Methode(OperationAnalysisContext context, IMethodSymbol methode)
        {
            var doel = methode.ReducedFrom ?? methode;
            foreach (var (type, regel) in _typen)
            {
                if (!regel.IsVerboden(doel.Name) || !HoortBij(doel.ContainingType, type))
                {
                    continue;
                }

                var api = regel.Type + "." + doel.Name;
                if (!Toegestaan(context.ContainingSymbol, regel.RegelId, api))
                {
                    context.ReportDiagnostic(Diagnostic.Create(Descriptor(regel.RegelId), context.Operation.Syntax.GetLocation(), api));
                }

                return;
            }
        }

        /// <summary>Een eigenschap van een bewaakt type zetten (bijvoorbeeld <c>FileInfo.Attributes</c>) is ook schrijven.</summary>
        public void Eigenschap(OperationAnalysisContext context)
        {
            var verwijzing = (IPropertyReferenceOperation)context.Operation;
            var geschreven = verwijzing.Parent switch
            {
                IAssignmentOperation toewijzing => ReferenceEquals(toewijzing.Target, verwijzing),
                IIncrementOrDecrementOperation => true,
                _ => false,
            };
            if (!geschreven)
            {
                return;
            }

            foreach (var (type, regel) in _typen)
            {
                if (!HoortBij(verwijzing.Property.ContainingType, type))
                {
                    continue;
                }

                var api = regel.Type + "." + verwijzing.Property.Name;
                if (!Toegestaan(context.ContainingSymbol, regel.RegelId, api))
                {
                    context.ReportDiagnostic(Diagnostic.Create(Descriptor(regel.RegelId), verwijzing.Syntax.GetLocation(), api));
                }

                return;
            }
        }

        public void Aanmaak(OperationAnalysisContext context)
        {
            var aanmaak = (IObjectCreationOperation)context.Operation;
            if (aanmaak.Type is not INamedTypeSymbol gemaakt)
            {
                return;
            }

            foreach (var (type, regelId, alleenMetPad) in _aanmaak)
            {
                if (!HoortBij(gemaakt, type))
                {
                    continue;
                }

                var eerste = aanmaak.Constructor?.Parameters.FirstOrDefault()?.Type.SpecialType;
                if (alleenMetPad && eerste != SpecialType.System_String)
                {
                    return;
                }

                if (!Toegestaan(context.ContainingSymbol, regelId, null))
                {
                    context.ReportDiagnostic(Diagnostic.Create(Descriptor(regelId), aanmaak.Syntax.GetLocation(), "new " + type.ToDisplayString()));
                }

                return;
            }
        }

        public void Letterlijk(OperationAnalysisContext context)
        {
            if (context.Operation.ConstantValue is { HasValue: true, Value: string tekst })
            {
                foreach (var naam in Regels.ServerDatabaseNamen)
                {
                    if (tekst.IndexOf(naam, StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        context.ReportDiagnostic(Diagnostic.Create(_serverDatabase, context.Operation.Syntax.GetLocation(), naam));
                        return;
                    }
                }
            }
        }

        public void Naam(SyntaxNodeAnalysisContext context)
        {
            if (_databaseTypen.Count == 0 || context.SemanticModel.GetSymbolInfo(context.Node, context.CancellationToken).Symbol is not INamedTypeSymbol type)
            {
                return;
            }

            foreach (var verboden in _databaseTypen)
            {
                if (HoortBij(type, verboden))
                {
                    context.ReportDiagnostic(Diagnostic.Create(_serverDatabase, context.Node.GetLocation(), verboden.ToDisplayString()));
                    return;
                }
            }
        }

        private static bool HoortBij(INamedTypeSymbol? kandidaat, INamedTypeSymbol bewaakt)
        {
            for (var t = kandidaat; t is not null; t = t.BaseType)
            {
                if (SymbolEqualityComparer.Default.Equals(t.OriginalDefinition, bewaakt))
                {
                    return true;
                }
            }

            return kandidaat is not null && kandidaat.AllInterfaces.Any(i => SymbolEqualityComparer.Default.Equals(i.OriginalDefinition, bewaakt));
        }

        private bool Toegestaan(ISymbol? plek, string regelId, string? api)
        {
            var klasse = BuitensteType(plek);
            var ruimte = klasse?.ContainingNamespace?.ToDisplayString() ?? string.Empty;
            var vast = regelId switch
            {
                Regels.BestandSchrijf => Regels.OpslagNamespaces,
                Regels.ProcesStart => Regels.ProcesNamespaces,
                _ => ImmutableArray<string>.Empty,
            };
            if (vast.Any(n => ruimte == n || ruimte.StartsWith(n + ".", StringComparison.Ordinal)))
            {
                return true;
            }

            return api is not null && klasse is not null && _uitzonderingen.Bevat(regelId, api, klasse.ToDisplayString());
        }

        private static INamedTypeSymbol? BuitensteType(ISymbol? plek)
        {
            var type = plek as INamedTypeSymbol ?? plek?.ContainingType;
            while (type?.ContainingType is not null)
            {
                type = type.ContainingType;
            }

            return type;
        }
    }
}
