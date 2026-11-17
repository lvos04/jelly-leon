using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
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

    private static readonly DiagnosticDescriptor _databaseToegang = new(
        Regels.BestandSchrijf,
        "Databaseverbindingen alleen via de opslaglaag",
        "'{0}' geeft of gebruikt een databaseverbinding of -bron buiten Core.Storage; gebruik JlDatabase",
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
        ImmutableArray.Create(_serverSchrijf, _bestandSchrijf, _databaseToegang, _serverDatabase, _procesStart, _ongeldigeUitzondering);

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
        context.RegisterOperationAction(toestand.Constante, OperationKind.Literal, OperationKind.FieldReference, OperationKind.LocalReference, OperationKind.Utf8String);
        context.RegisterOperationAction(toestand.Samenstelling, OperationKind.Binary, OperationKind.InterpolatedString);
        context.RegisterSyntaxNodeAction(toestand.Naam, SyntaxKind.IdentifierName);
        context.RegisterOperationAction(
            toestand.Databasetoegang,
            OperationKind.Invocation,
            OperationKind.MethodReference,
            OperationKind.PropertyReference,
            OperationKind.FieldReference,
            OperationKind.EventReference,
            OperationKind.ObjectCreation,
            OperationKind.TypeParameterObjectCreation,
            OperationKind.TypeOf,
            OperationKind.Conversion,
            OperationKind.IsType,
            OperationKind.DeclarationPattern,
            OperationKind.TypePattern,
            OperationKind.RecursivePattern);
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
        private readonly List<INamedTypeSymbol> _databaseTypenExact = new();
        private readonly List<INamedTypeSymbol> _verbindingTypen = new();
        private readonly IAssemblySymbol _eigen;
        private readonly Uitzonderingen _uitzonderingen;

        public Toestand(Compilation compilatie, Uitzonderingen uitzonderingen)
        {
            _uitzonderingen = uitzonderingen;
            _eigen = compilatie.Assembly;
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

            foreach (var naam in Regels.ServerDatabaseTypenExact)
            {
                if (compilatie.GetTypeByMetadataName(naam) is { } type)
                {
                    _databaseTypenExact.Add(type);
                }
            }

            foreach (var naam in Regels.DatabaseVerbindingTypen)
            {
                if (compilatie.GetTypeByMetadataName(naam) is { } type)
                {
                    _verbindingTypen.Add(type);
                }
            }
        }

        public void Methode(OperationAnalysisContext context, IMethodSymbol methode)
        {
            var doel = methode.ReducedFrom ?? methode;
            foreach (var (type, regel) in _typen)
            {
                if (LidVan(doel, type) is not { } lid || !regel.IsVerboden(lid))
                {
                    continue;
                }

                var api = regel.Type + "." + lid;
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
                if (LidVan(verwijzing.Property, type) is not { } lid)
                {
                    continue;
                }

                var api = regel.Type + "." + lid;
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

        /// <summary>
        /// JL0003 op één waarde: een letterlijke tekst, een UTF-8-tekst (<c>"…"u8</c>) of een constante (ook een constante
        /// uit een andere assembly) waarin de naam van de serverdatabase staat.
        /// </summary>
        public void Constante(OperationAnalysisContext context)
        {
            if (Waarde(context.Operation) is { } tekst && ServerDatabaseNaam(tekst) is { } naam)
            {
                context.ReportDiagnostic(Diagnostic.Create(_serverDatabase, context.Operation.Syntax.GetLocation(), naam));
            }
        }

        /// <summary>
        /// JL0003 op een samengestelde tekst (<c>"jellyfin" + ".db"</c>, <c>Naam + ".db"</c> met een constante,
        /// <c>$"{map}/jellyfin.d" + "b"</c>): de bekende stukken die direct op elkaar volgen worden aaneengeschreven; een
        /// onbekend stuk (een variabele) breekt de reeks. Alleen de buitenste samenstelling telt, en alleen een naam die
        /// pas over de stukken heen ontstaat: een stuk dat de naam zelf al bevat, meldt <see cref="Constante"/>.
        /// </summary>
        public void Samenstelling(OperationAnalysisContext context)
        {
            var operatie = context.Operation;
            if (operatie is IBinaryOperation plus && !IsTekstPlus(plus))
            {
                return;
            }

            if (IsDeelVanSamenstelling(operatie))
            {
                return;
            }

            var stukken = new List<string?>();
            Plat(operatie, stukken);
            if (stukken.Any(s => s is not null && ServerDatabaseNaam(s) is not null))
            {
                return;
            }

            foreach (var reeks in Aaneen(stukken))
            {
                if (ServerDatabaseNaam(reeks) is { } naam)
                {
                    context.ReportDiagnostic(Diagnostic.Create(_serverDatabase, operatie.Syntax.GetLocation(), naam));
                    return;
                }
            }
        }

        private static string? ServerDatabaseNaam(string tekst) =>
            Regels.ServerDatabaseNamen.FirstOrDefault(naam => tekst.IndexOf(naam, StringComparison.OrdinalIgnoreCase) >= 0);

        /// <summary>
        /// De bekende tekst van een constante (tekst, teken of <c>null</c> als lege tekst) of van een UTF-8-tekst; anders
        /// null.
        /// </summary>
        private static string? Waarde(IOperation operatie)
        {
            if (operatie is IUtf8StringOperation utf8)
            {
                return utf8.Value;
            }

            if (!operatie.ConstantValue.HasValue)
            {
                return null;
            }

            return operatie.ConstantValue.Value switch
            {
                string tekst => tekst,
                char teken => new string(teken, 1),
                null => string.Empty,
                _ => null,
            };
        }

        /// <summary>
        /// Een optelling van tekst: van gewone tekst, of van UTF-8-tekst (<c>"jellyfin"u8 + ".db"u8</c>, type
        /// <c>ReadOnlySpan&lt;byte&gt;</c>; de compiler voegt die stukken samen).
        /// </summary>
        private static bool IsTekstPlus(IBinaryOperation plus) =>
            plus.OperatorKind == BinaryOperatorKind.Add
            && (plus.Type?.SpecialType == SpecialType.System_String || IsUtf8Samenstelling(plus));

        private static bool IsUtf8Samenstelling(IBinaryOperation plus) =>
            plus.Type is INamedTypeSymbol { Name: "ReadOnlySpan", ContainingNamespace: { Name: "System", ContainingNamespace.IsGlobalNamespace: true }, TypeArguments.Length: 1 } span
            && span.TypeArguments[0].SpecialType == SpecialType.System_Byte
            && plus.LeftOperand is IUtf8StringOperation or IBinaryOperation
            && plus.RightOperand is IUtf8StringOperation or IBinaryOperation;

        private static bool IsDeelVanSamenstelling(IOperation operatie)
        {
            var ouder = operatie.Parent;
            while (ouder is IConversionOperation)
            {
                ouder = ouder.Parent;
            }

            return (ouder is IBinaryOperation plus && IsTekstPlus(plus))
                || ouder is IInterpolationOperation
                || ouder is IInterpolatedStringTextOperation
                || ouder is IArgumentOperation { Parent: IInvocationOperation { Parent: IInterpolatedStringAppendOperation } };
        }

        /// <summary>Schrijft de stukken van een samenstelling op volgorde uit; null is een onbekend stuk.</summary>
        private static void Plat(IOperation operatie, List<string?> stukken)
        {
            switch (operatie)
            {
                case IConversionOperation omzetting:
                    {
                        // Heeft de omzetting zelf een constante waarde, dan telt die: een getal dat een teken wordt
                        // ((char)46, (char)0x2E) is dat teken, een teken dat een getal wordt ((int)'.') is geen tekst meer.
                        // Zonder constante waarde (bijvoorbeeld (object)".db") telt wat omgezet wordt.
                        var binnen = new List<string?>();
                        Plat(omzetting.Operand, binnen);
                        if (!omzetting.ConstantValue.HasValue || (Waarde(omzetting) is { } tekst && !binnen.Contains(null) && string.Concat(binnen) == tekst))
                        {
                            stukken.AddRange(binnen);
                        }
                        else
                        {
                            stukken.Add(Waarde(omzetting));
                        }

                        return;
                    }

                case IBinaryOperation plus when IsTekstPlus(plus):
                    Plat(plus.LeftOperand, stukken);
                    Plat(plus.RightOperand, stukken);
                    return;
                case IInterpolatedStringHandlerCreationOperation maker:
                    Plat(maker.Content, stukken);
                    return;
                case IInterpolatedStringOperation geinterpoleerd:
                    foreach (var deel in geinterpoleerd.Parts)
                    {
                        switch (deel)
                        {
                            case IInterpolatedStringTextOperation tekst:
                                Plat(tekst.Text, stukken);
                                break;
                            case IInterpolationOperation gat:
                                Uitgelijnd(gat.Expression, gat.Alignment, stukken);
                                break;
                            case IInterpolatedStringAppendOperation toevoeging when toevoeging.AppendCall is IInvocationOperation { Arguments.Length: > 0 } aanroep:
                                Uitgelijnd(aanroep.Arguments[0].Value, aanroep.Arguments.Skip(1).FirstOrDefault(a => a.Parameter?.Name == "alignment")?.Value, stukken);
                                break;
                            default:
                                stukken.Add(null);
                                break;
                        }
                    }

                    return;
                default:
                    stukken.Add(Waarde(operatie));
                    return;
            }
        }

        /// <summary>
        /// Een stuk met een uitlijning (<c>{x,n}</c>). Bij een bekende tekst en een constante n is de uitkomst ook bekend:
        /// de tekst, aangevuld met spaties tot |n| tekens (n positief: ervoor, n negatief: erna; een kortere n vult niets
        /// aan). Is de tekst niet helemaal bekend, dan sluit het stuk niet aan op zijn buren.
        /// </summary>
        private static void Uitgelijnd(IOperation waarde, IOperation? uitlijning, List<string?> stukken)
        {
            if (uitlijning is null)
            {
                Plat(waarde, stukken);
                return;
            }

            var binnen = new List<string?>();
            Plat(waarde, binnen);
            if (binnen.Contains(null) || uitlijning.ConstantValue is not { HasValue: true, Value: int breedte })
            {
                stukken.Add(null);
                stukken.AddRange(binnen);
                stukken.Add(null);
                return;
            }

            var tekst = string.Concat(binnen);
            var vulling = new string(' ', Math.Max(0, Math.Abs(breedte) - tekst.Length));
            stukken.Add(breedte >= 0 ? vulling + tekst : tekst + vulling);
        }

        /// <summary>De reeksen van bekende stukken die direct op elkaar volgen, aaneengeschreven.</summary>
        private static IEnumerable<string> Aaneen(IReadOnlyList<string?> stukken)
        {
            var reeks = new System.Text.StringBuilder();
            foreach (var stuk in stukken)
            {
                if (stuk is null)
                {
                    if (reeks.Length > 0)
                    {
                        yield return reeks.ToString();
                        reeks.Clear();
                    }

                    continue;
                }

                reeks.Append(stuk);
            }

            if (reeks.Length > 0)
            {
                yield return reeks.ToString();
            }
        }

        /// <summary>
        /// JL0003 op elke naam die naar een databasetype van de server verwijst, ook als typeargument of elementtype: zo
        /// geeft <c>var f = provider.DbContextFactory</c> (type <c>IDbContextFactory&lt;JellyfinDbContext&gt;</c>) of een
        /// alias ervoor ook JL0003.
        /// </summary>
        public void Naam(SyntaxNodeAnalysisContext context)
        {
            if (_databaseTypen.Count + _databaseTypenExact.Count == 0 || context.SemanticModel.GetSymbolInfo(context.Node, context.CancellationToken).Symbol is not ITypeSymbol type)
            {
                return;
            }

            if (DatabaseType(type) is { } verboden)
            {
                context.ReportDiagnostic(Diagnostic.Create(_serverDatabase, context.Node.GetLocation(), verboden.ToDisplayString()));
            }
        }

        /// <summary>
        /// JL0002 databasetoegang (R-HARDE-EIS-12): buiten Core.Storage is elke operatie verboden die een databaseverbinding
        /// of -bron oplevert of gebruikt. "Databasetype" is een verbinding of bron (<c>DbConnection</c>, <c>IDbConnection</c>,
        /// <c>DbDataSource</c>, <c>DbProviderFactory</c>, <c>DbProviderFactories</c> en alles wat ervan afleidt) en elk type
        /// uit Microsoft.Data.Sqlite, SQLitePCLRaw en Entity Framework Core. Verboden is: een lid van zo'n type aanroepen,
        /// lezen of zetten (ook statisch, zoals <c>SqliteFactory.Instance</c>, en een methodeverwijzing); een aanroep of
        /// extern lid waarvan het resultaat er een is of bevat (<c>Task&lt;DbConnection&gt;</c>, een typeargument, een
        /// <c>out</c>-parameter, de terugkeer van een gedelegeerde); er een aanmaken; <c>typeof</c>; en een omzetting of
        /// patroon naar zo'n type. Wat de naam van de serverdatabase draagt (JL0003, <see cref="DatabaseType"/>) laat deze
        /// regel aan <see cref="Naam"/>. Een verbinding die als parameter binnenkomt (<c>JlDatabase.Met(v =&gt; …)</c>) mag
        /// alleen worden doorgegeven: een parameter, lokale variabele of eigen veld lezen is geen operatie van deze regel.
        /// Per keten één melding: is de ontvanger zelf al een melding, dan niet nog een.
        /// </summary>
        public void Databasetoegang(OperationAnalysisContext context)
        {
            if (Databasetype(context.Operation) is not { } type || Databasetype(Ontvanger(context.Operation)) is not null
                || InNamespace(context.ContainingSymbol, Regels.DatabaseNamespaces) || NoemtServerdatabase(context.Operation))
            {
                return;
            }

            context.ReportDiagnostic(Diagnostic.Create(_databaseToegang, context.Operation.Syntax.GetLocation(), Beschrijf(context.Operation, type)));
        }

        /// <summary>Het databasetype dat <paramref name="operatie"/> oplevert of gebruikt; null als er geen is of als JL0003 erover gaat.</summary>
        private ITypeSymbol? Databasetype(IOperation? operatie)
        {
            var gebruikt = new List<ITypeSymbol?>();
            var resultaat = new List<ITypeSymbol?>();
            void Lid(IMethodSymbol methode)
            {
                gebruikt.Add(methode.ContainingType);
                resultaat.Add(methode.ReturnType);
                resultaat.AddRange(methode.Parameters.Where(p => p.RefKind is RefKind.Out or RefKind.Ref).Select(p => p.Type));
                resultaat.AddRange(methode.TypeArguments);
            }

            switch (operatie)
            {
                case IInvocationOperation aanroep:
                    Lid(aanroep.TargetMethod.ReducedFrom ?? aanroep.TargetMethod);
                    break;
                case IMethodReferenceOperation verwijzing:
                    Lid(verwijzing.Method.ReducedFrom ?? verwijzing.Method);
                    break;
                case IPropertyReferenceOperation eigenschap:
                    gebruikt.Add(eigenschap.Property.ContainingType);
                    resultaat.Add(IsEigen(eigenschap.Property) ? null : eigenschap.Property.Type);
                    break;
                case IFieldReferenceOperation veld:
                    gebruikt.Add(veld.Field.ContainingType);
                    resultaat.Add(IsEigen(veld.Field) ? null : veld.Field.Type);
                    break;
                case IEventReferenceOperation gebeurtenis:
                    gebruikt.Add(gebeurtenis.Event.ContainingType);
                    break;
                case IObjectCreationOperation aanmaak:
                    resultaat.Add(aanmaak.Type);
                    break;
                case ITypeParameterObjectCreationOperation aanmaak:
                    resultaat.Add(aanmaak.Type);
                    break;
                case ITypeOfOperation soort:
                    resultaat.Add(soort.TypeOperand);
                    break;
                case IConversionOperation omzetting when !IsLeeg(omzetting.Operand) && (!omzetting.IsImplicit || Bevat(omzetting.Operand.Type) is null):
                    resultaat.Add(omzetting.Type);
                    break;
                case IIsTypeOperation isType:
                    resultaat.Add(isType.TypeOperand);
                    break;
                case IDeclarationPatternOperation patroon:
                    resultaat.Add(patroon.MatchedType);
                    break;
                case ITypePatternOperation patroon:
                    resultaat.Add(patroon.MatchedType);
                    break;
                case IRecursivePatternOperation patroon:
                    resultaat.Add(patroon.MatchedType);
                    break;
                default:
                    return null;
            }

            if (gebruikt.Concat(resultaat).Any(t => t is not null && DatabaseType(t, metExact: false) is not null))
            {
                return null;
            }

            return gebruikt.FirstOrDefault(IsDatabasetype) ?? resultaat.Select(Bevat).FirstOrDefault(t => t is not null);
        }

        /// <summary>
        /// Waar als de operatie zelf de naam van een databasetype van de server noemt (bijvoorbeeld
        /// <c>GetRequiredService&lt;DbContextOptions&gt;()</c> of <c>typeof(DbContextOptions)</c>): dan meldt <see cref="Naam"/>
        /// al JL0003 en volgt er geen tweede melding.
        /// </summary>
        private bool NoemtServerdatabase(IOperation operatie) =>
            operatie.SemanticModel is { } model
            && operatie.Syntax.DescendantNodesAndSelf().OfType<IdentifierNameSyntax>().Any(n => model.GetSymbolInfo(n).Symbol is ITypeSymbol t && DatabaseType(t) is not null);

        /// <summary>De ontvanger van een lid (ook het eerste argument van een extensiemethode) of wat omgezet wordt.</summary>
        private IOperation? Ontvanger(IOperation operatie)
        {
            var ontvanger = operatie switch
            {
                IInvocationOperation aanroep => aanroep.Instance ?? (aanroep.TargetMethod.IsExtensionMethod && aanroep.Arguments.Length > 0 ? aanroep.Arguments[0].Value : null),
                IMethodReferenceOperation verwijzing => verwijzing.Instance,
                IPropertyReferenceOperation eigenschap => eigenschap.Instance,
                IFieldReferenceOperation veld => veld.Instance,
                IEventReferenceOperation gebeurtenis => gebeurtenis.Instance,
                IConversionOperation omzetting => omzetting.Operand,
                IIsTypeOperation isType => isType.ValueOperand,
                _ => null,
            };
            while (ontvanger is IConversionOperation { IsImplicit: true } stil && Bevat(stil.Operand.Type) is not null)
            {
                ontvanger = stil.Operand;
            }

            return ontvanger;
        }

        private static bool IsLeeg(IOperation operand) =>
            operand is IDefaultValueOperation || (operand.Type is null && operand.ConstantValue is { HasValue: true, Value: null });

        private bool IsEigen(ISymbol lid) => SymbolEqualityComparer.Default.Equals(lid.ContainingAssembly, _eigen);

        /// <summary>Een verbinding of bron, of een type uit een databaseassembly (ook als basistype, interface of beperking).</summary>
        private bool IsDatabasetype(ITypeSymbol? type)
        {
            switch (type)
            {
                case ITypeParameterSymbol parameter:
                    return parameter.ConstraintTypes.Any(IsDatabasetype);
                case INamedTypeSymbol benoemd:
                    for (var t = benoemd; t is not null; t = t.BaseType)
                    {
                        if (IsVerbindingOfAssembly(t))
                        {
                            return true;
                        }
                    }

                    return benoemd.AllInterfaces.Any(IsVerbindingOfAssembly);
                default:
                    return false;
            }
        }

        private bool IsVerbindingOfAssembly(INamedTypeSymbol type) =>
            Regels.IsDatabaseAssembly(type.ContainingAssembly?.Identity.Name)
            || _verbindingTypen.Any(v => SymbolEqualityComparer.Default.Equals(type.OriginalDefinition, v));

        /// <summary>
        /// Het databasetype dat een resultaat is of bevat: het type zelf, een elementtype, een typeargument of de terugkeer van
        /// een gedelegeerde (de parameters van een gedelegeerde niet: <c>Func&lt;SqliteConnection, T&gt;</c> geeft geen
        /// verbinding, die krijgt er een).
        /// </summary>
        private ITypeSymbol? Bevat(ITypeSymbol? type)
        {
            if (type is null)
            {
                return null;
            }

            if (IsDatabasetype(type))
            {
                return type;
            }

            switch (type)
            {
                case IArrayTypeSymbol rij:
                    return Bevat(rij.ElementType);
                case IPointerTypeSymbol wijzer:
                    return Bevat(wijzer.PointedAtType);
                case INamedTypeSymbol { TypeKind: TypeKind.Delegate, DelegateInvokeMethod: { } aanroep }:
                    return Bevat(aanroep.ReturnType);
                case INamedTypeSymbol benoemd:
                    return benoemd.TypeArguments.Select(Bevat).FirstOrDefault(t => t is not null);
                default:
                    return null;
            }
        }

        private static string Beschrijf(IOperation operatie, ITypeSymbol type) => operatie switch
        {
            IInvocationOperation aanroep => Lidnaam(aanroep.TargetMethod.ReducedFrom ?? aanroep.TargetMethod),
            IMethodReferenceOperation verwijzing => Lidnaam(verwijzing.Method.ReducedFrom ?? verwijzing.Method),
            IPropertyReferenceOperation eigenschap => Lidnaam(eigenschap.Property),
            IFieldReferenceOperation veld => Lidnaam(veld.Field),
            IEventReferenceOperation gebeurtenis => Lidnaam(gebeurtenis.Event),
            IObjectCreationOperation or ITypeParameterObjectCreationOperation => "new " + type.ToDisplayString(),
            ITypeOfOperation => "typeof(" + type.ToDisplayString() + ")",
            IConversionOperation => "(" + type.ToDisplayString() + ")",
            _ => "is " + type.ToDisplayString(),
        };

        private static string Lidnaam(ISymbol lid) => lid.ContainingType.OriginalDefinition.ToDisplayString() + "." + lid.Name;

        private static bool InNamespace(ISymbol? plek, ImmutableArray<string> namespaces)
        {
            var ruimte = BuitensteType(plek)?.ContainingNamespace?.ToDisplayString() ?? string.Empty;
            return namespaces.Any(n => ruimte == n || ruimte.StartsWith(n + ".", StringComparison.Ordinal));
        }

        /// <summary>Het databasetype van de server in <paramref name="type"/>: het type zelf, een elementtype of een typeargument.</summary>
        private INamedTypeSymbol? DatabaseType(ITypeSymbol type, bool metExact = true)
        {
            switch (type)
            {
                case IArrayTypeSymbol rij:
                    return DatabaseType(rij.ElementType, metExact);
                case IPointerTypeSymbol wijzer:
                    return DatabaseType(wijzer.PointedAtType, metExact);
                case INamedTypeSymbol benoemd:
                    foreach (var verboden in _databaseTypen)
                    {
                        if (HoortBij(benoemd, verboden))
                        {
                            return verboden;
                        }
                    }

                    foreach (var exact in metExact ? _databaseTypenExact : Enumerable.Empty<INamedTypeSymbol>())
                    {
                        if (SymbolEqualityComparer.Default.Equals(benoemd.OriginalDefinition, exact))
                        {
                            return exact;
                        }
                    }

                    foreach (var argument in benoemd.TypeArguments)
                    {
                        if (DatabaseType(argument, metExact) is { } binnen)
                        {
                            return binnen;
                        }
                    }

                    return benoemd.ContainingType is { } buiten ? DatabaseType(buiten, metExact) : null;
                default:
                    return null;
            }
        }

        /// <summary>
        /// De naam waaronder <paramref name="lid"/> onder de regel van <paramref name="bewaakt"/> valt, of null als het lid
        /// er niet onder valt. Een lid van het bewaakte type, een afgeleid type of (bij een interface) een afgeleide
        /// interface valt er met zijn eigen naam onder. Bij een bewaakte interface valt van een klasse of struct die de
        /// interface implementeert alleen het lid onder de regel dat een lid van die interface implementeert
        /// (<c>FindImplementationForInterfaceMember</c>), met de naam van het interfacelid: de eigen
        /// <c>ExecuteAsync</c> van een taak aanroepen is JL0001 als <c>IScheduledTask.ExecuteAsync</c>, een eigen
        /// hulpmethode of eigenschap van die taak niet.
        /// </summary>
        private static string? LidVan(ISymbol lid, INamedTypeSymbol bewaakt)
        {
            var eigenaar = lid.ContainingType;
            if (eigenaar is null || !HoortBij(eigenaar, bewaakt))
            {
                return null;
            }

            if (bewaakt.TypeKind != TypeKind.Interface || eigenaar.TypeKind == TypeKind.Interface)
            {
                return lid.Name;
            }

            var origineel = lid.OriginalDefinition;
            foreach (var koppelvlak in eigenaar.AllInterfaces)
            {
                if (!HoortBij(koppelvlak, bewaakt))
                {
                    continue;
                }

                foreach (var interfacelid in koppelvlak.GetMembers())
                {
                    if (eigenaar.FindImplementationForInterfaceMember(interfacelid) is { } uitvoering
                        && IsOfOverschrijft(origineel, uitvoering.OriginalDefinition))
                    {
                        return interfacelid.Name;
                    }
                }
            }

            return null;
        }

        /// <summary>
        /// Waar als <paramref name="lid"/> de implementatie zelf is, of (herhaald, via <c>override</c>) een lid dat die
        /// implementatie overschrijft: <c>FindImplementationForInterfaceMember</c> geeft bij een afgeleide klasse het
        /// virtuele lid van de basisklasse, niet de override (R-HARDE-EIS-11). Geldt voor methoden, eigenschappen en events.
        /// </summary>
        private static bool IsOfOverschrijft(ISymbol lid, ISymbol uitvoering)
        {
            for (var kandidaat = lid; kandidaat is not null; kandidaat = Overschreven(kandidaat))
            {
                if (SymbolEqualityComparer.Default.Equals(kandidaat.OriginalDefinition, uitvoering))
                {
                    return true;
                }
            }

            return false;
        }

        private static ISymbol? Overschreven(ISymbol lid) => lid switch
        {
            IMethodSymbol methode => methode.OverriddenMethod,
            IPropertySymbol eigenschap => eigenschap.OverriddenProperty,
            IEventSymbol gebeurtenis => gebeurtenis.OverriddenEvent,
            _ => null,
        };

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
