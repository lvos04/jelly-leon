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

    private static readonly DiagnosticDescriptor _serverAbi = new(
        Regels.ServerSchrijf,
        "Server-ABI alleen via de witte lijst",
        "'{0}' is een lid van de server-ABI dat in deze klasse niet op de witte lijst staat (ADR-0032, kop \"Server-ABI: witte lijst\": alleen lezende leden die de plugin echt gebruikt, per klasse)",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _serverToewijzing = new(
        Regels.ServerSchrijf,
        "Een eigenschap of veld van een servertype zetten is verboden",
        "'{0}' zet een eigenschap of veld van een servertype; de server kan het object zelf opslaan of erop handelen (zoals SessionInfo.NowPlayingItem of RestoreBackupPath); dat mag nergens",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _serverUitbreiding = new(
        Regels.ServerSchrijf,
        "Uitbreidingspunt van de server buiten de witte lijst",
        "'{0}' implementeert of erft '{1}' uit de server-ABI; de server zoekt zulke typen zelf op en roept ze aan. Alleen de uitbreidingspunten op de witte lijst mogen, elk in zijn eigen namespace (ADR-0032).",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _httpLaag = new(
        Regels.ServerSchrijf,
        "De HTTP-laag van de server alleen via de witte lijst",
        "'{0}' raakt de HTTP-laag van de server (de pijplijn, de instellingen van MVC, autorisatie of authenticatie, de routering of de features, de argumenten van een actie, of het verzoek of de gebruiker wijzigen); zo kan plugincode een verzoek aan de server omzetten. Dat mag alleen in een klasse op de witte lijst van de HTTP-laag (ADR-0032, kop \"HTTP-laag en netwerk\").",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _httpUitbreiding = new(
        Regels.ServerSchrijf,
        "Uitbreidingspunt van de HTTP-laag buiten de witte lijst",
        "'{0}' implementeert of erft '{1}' uit de HTTP-laag van de server (middleware, filter, claimsomzetting, autorisatie, binding of routering); zo kan plugincode een verzoek aan de server omzetten. Alleen een klasse op de witte lijst van de HTTP-laag mag dat (ADR-0032, kop \"HTTP-laag en netwerk\").",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _doorsturen = new(
        Regels.ServerSchrijf,
        "Een antwoord dat de browser doorstuurt is verboden",
        "'{0}' stuurt de browser door (een redirect, de kop Location of een 3xx-status); de browser volgt dat met dezelfde methode en het token van de gebruiker naar elke route van de server (ook 301 en 302 bij DELETE of PUT). Dat mag nergens in plugincode (ADR-0032, kop \"HTTP-laag en netwerk\").",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _hostOptie = new(
        Regels.ServerSchrijf,
        "Instellingen van de host alleen via de witte lijst",
        "'{0}' gebruikt een instelling van de host (een optietype van ASP.NET Core, zoals JsonOptions of MvcOptions, of HostOptions); die geldt voor alle routes en acties van de server, zo kan plugincode de argumenten of het antwoord van een serveractie wijzigen. Dat mag alleen in een klasse op de witte lijst van de instellingen van de host, en die is leeg (ADR-0032, kop \"HTTP-laag en netwerk\").",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _netwerk = new(
        Regels.ServerSchrijf,
        "Netwerkclients alleen in een benoemde transportklasse",
        "'{0}' is een netwerkclient (HTTP, sockets of websockets); daarmee kan plugincode de eigen server aanroepen met het token van een verzoek. Dat mag alleen in een transportklasse die loopback, het eigen serveradres en link-local weigert (ADR-0032, kop \"HTTP-laag en netwerk\"); zo'n klasse is er nu niet.",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _pluginConfig = new(
        Regels.BestandSchrijf,
        "Het pad van de pluginconfiguratie mag niet worden verlegd",
        "'{0}' verlegt of vervangt waar de server de pluginconfiguratie schrijft (ConfigurationFilePath); de server schrijft dan zelf op een gekozen pad. Dat mag nergens in plugincode.",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _bestandSchrijf = new(
        Regels.BestandSchrijf,
        "Bestanden schrijven mag alleen via de opslaglaag",
        "'{0}' schrijft, verwijdert of opent een bestand buiten Core.Storage en Core.Secrets (buiten de opslaglaag mag alleen lezen en padbewerking); gebruik InternalWriteScope of JlDatabase",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _serverBestand = new(
        Regels.BestandSchrijf,
        "Server-API die zelf bestanden schrijft of processen start is verboden",
        "'{0}' laat de server een bestand schrijven, wissen of verplaatsen of een proces starten, langs de padgrens van Core.Storage heen; dat mag nergens in plugincode",
        Categorie,
        DiagnosticSeverity.Error,
        true,
        customTags: WellKnownDiagnosticTags.NotConfigurable);

    private static readonly DiagnosticDescriptor _omweg = new(
        Regels.BestandSchrijf,
        "Omwegen langs de bouwgrens zijn verboden",
        "'{0}' omzeilt de bouwgrens (native code, unsafe, reflectie, dynamic of code laden); dat mag nergens in plugincode",
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
        ImmutableArray.Create(_serverSchrijf, _serverAbi, _serverToewijzing, _serverUitbreiding, _httpLaag, _httpUitbreiding, _doorsturen, _hostOptie, _netwerk, _pluginConfig, _bestandSchrijf, _serverBestand, _omweg, _databaseToegang, _serverDatabase, _procesStart, _ongeldigeUitzondering);

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
        context.RegisterOperationAction(
            toestand.Bestandstoegang,
            OperationKind.Invocation,
            OperationKind.MethodReference,
            OperationKind.PropertyReference,
            OperationKind.FieldReference,
            OperationKind.EventReference,
            OperationKind.ObjectCreation);
        context.RegisterOperationAction(
            toestand.VolledigVerboden,
            OperationKind.Invocation,
            OperationKind.MethodReference,
            OperationKind.PropertyReference,
            OperationKind.FieldReference,
            OperationKind.EventReference,
            OperationKind.ObjectCreation);
        context.RegisterOperationAction(
            toestand.ServerAbi,
            OperationKind.Invocation,
            OperationKind.MethodReference,
            OperationKind.PropertyReference,
            OperationKind.FieldReference,
            OperationKind.EventReference,
            OperationKind.ObjectCreation,
            OperationKind.Binary,
            OperationKind.Unary,
            OperationKind.Conversion,
            OperationKind.CompoundAssignment,
            OperationKind.Increment,
            OperationKind.Decrement);
        context.RegisterSymbolAction(toestand.Uitbreiding, SymbolKind.NamedType);
        context.RegisterOperationAction(
            toestand.HttpLaag,
            OperationKind.Invocation,
            OperationKind.MethodReference,
            OperationKind.PropertyReference,
            OperationKind.FieldReference,
            OperationKind.EventReference,
            OperationKind.ObjectCreation,
            OperationKind.Conversion,
            OperationKind.TypeOf);
        context.RegisterSymbolAction(toestand.HttpUitbreiding, SymbolKind.NamedType);
        context.RegisterSymbolAction(toestand.HostOptieUitbreiding, SymbolKind.NamedType);
        context.RegisterOperationAction(toestand.DoorstuurKop, OperationKind.Literal, OperationKind.Binary, OperationKind.InterpolatedString, OperationKind.NameOf);
        context.RegisterOperationAction(
            toestand.Netwerk,
            OperationKind.Invocation,
            OperationKind.MethodReference,
            OperationKind.PropertyReference,
            OperationKind.FieldReference,
            OperationKind.EventReference,
            OperationKind.ObjectCreation);
        context.RegisterSymbolAction(toestand.PluginConfig, SymbolKind.Method, SymbolKind.Property);
        context.RegisterOperationAction(toestand.XmlSchrijven, OperationKind.Invocation, OperationKind.MethodReference, OperationKind.ObjectCreation);
        context.RegisterOperationAction(toestand.NativeAanroep, OperationKind.Invocation, OperationKind.MethodReference);
        context.RegisterOperationAction(
            toestand.Dynamisch,
            OperationKind.DynamicInvocation,
            OperationKind.DynamicMemberReference,
            OperationKind.DynamicIndexerAccess,
            OperationKind.DynamicObjectCreation);
        context.RegisterSymbolAction(toestand.NativeDeclaratie, SymbolKind.Method);
        context.RegisterSyntaxNodeAction(
            toestand.Onveilig,
            SyntaxKind.UnsafeStatement,
            SyntaxKind.ClassDeclaration,
            SyntaxKind.StructDeclaration,
            SyntaxKind.RecordDeclaration,
            SyntaxKind.RecordStructDeclaration,
            SyntaxKind.InterfaceDeclaration,
            SyntaxKind.MethodDeclaration,
            SyntaxKind.ConstructorDeclaration,
            SyntaxKind.DestructorDeclaration,
            SyntaxKind.OperatorDeclaration,
            SyntaxKind.ConversionOperatorDeclaration,
            SyntaxKind.PropertyDeclaration,
            SyntaxKind.IndexerDeclaration,
            SyntaxKind.EventDeclaration,
            SyntaxKind.FieldDeclaration,
            SyntaxKind.EventFieldDeclaration,
            SyntaxKind.DelegateDeclaration,
            SyntaxKind.LocalFunctionStatement,
            SyntaxKind.UsingDirective);
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

    private static DiagnosticDescriptor Descriptor(TypeRegel regel) =>
        regel.Omweg ? _omweg : regel.Nergens && regel.RegelId == Regels.BestandSchrijf ? _serverBestand : Descriptor(regel.RegelId);

    private sealed class Toestand
    {
        private readonly List<(INamedTypeSymbol Type, TypeRegel Regel)> _typen = new();
        private readonly List<(INamedTypeSymbol Type, string RegelId, bool AlleenMetPad, bool Nergens)> _aanmaak = new();
        private readonly List<(INamedTypeSymbol Type, BestandWit Wit)> _wit = new();
        private readonly INamedTypeSymbol? _uitzondering;
        private readonly INamedTypeSymbol? _stroom;
        private readonly INamedTypeSymbol? _xmlSchrijver;
        private readonly INamedTypeSymbol? _libraryImport;
        private readonly List<INamedTypeSymbol> _databaseTypen = new();
        private readonly List<INamedTypeSymbol> _databaseTypenExact = new();
        private readonly List<INamedTypeSymbol> _verbindingTypen = new();
        private readonly List<INamedTypeSymbol> _volledig = new();
        private readonly List<(INamedTypeSymbol Type, ServerWit Wit)> _serverWit = new();
        private readonly List<(INamedTypeSymbol Type, UitbreidingWit Wit, INamedTypeSymbol? Argument)> _uitbreidingWit = new();
        private readonly List<INamedTypeSymbol> _httpUitbreidingTypen = new();
        private readonly List<INamedTypeSymbol> _httpPijplijn = new();
        private readonly List<INamedTypeSymbol> _httpOpties = new();
        private readonly List<(INamedTypeSymbol Type, string Lid)> _httpVerboden = new();
        private readonly List<INamedTypeSymbol> _httpZet = new();
        private readonly List<(INamedTypeSymbol Type, HttpWit Wit)> _httpWit = new();
        private readonly List<(INamedTypeSymbol Type, HttpWit Wit)> _hostWit = new();
        private readonly List<INamedTypeSymbol> _hostOptieTypen = new();
        private readonly List<(INamedTypeSymbol Type, string Voorvoegsel)> _doorstuurStatus = new();
        private readonly List<(INamedTypeSymbol Type, HttpWit Wit)> _doorstuurWit = new();
        private readonly List<INamedTypeSymbol> _netwerkTypen = new();
        private readonly INamedTypeSymbol? _verzoek;
        private readonly INamedTypeSymbol? _streamOpties;
        private readonly INamedTypeSymbol? _basisPlugin;
        private readonly INamedTypeSymbol? _pluginConfiguratie;
        private readonly IAssemblySymbol _eigen;
        private readonly Uitzonderingen _uitzonderingen;

        public Toestand(Compilation compilatie, Uitzonderingen uitzonderingen)
        {
            _uitzonderingen = uitzonderingen;
            _eigen = compilatie.Assembly;
            _streamOpties = compilatie.GetTypeByMetadataName("System.IO.FileStreamOptions");
            _basisPlugin = compilatie.GetTypeByMetadataName("MediaBrowser.Common.Plugins.BasePlugin`1");
            _pluginConfiguratie = compilatie.GetTypeByMetadataName("MediaBrowser.Common.Plugins.IHasPluginConfiguration");
            _verzoek = compilatie.GetTypeByMetadataName("Microsoft.AspNetCore.Http.HttpRequest");
            Vul(compilatie, Regels.HttpUitbreidingTypen, _httpUitbreidingTypen);
            Vul(compilatie, Regels.HttpPijplijnTypen, _httpPijplijn);
            Vul(compilatie, Regels.HttpOptieTypen, _httpOpties);
            Vul(compilatie, Regels.HttpZetTypen, _httpZet);
            Vul(compilatie, Regels.NetwerkTypen, _netwerkTypen);
            foreach (var (naam, lid) in Regels.HttpVerbodenLeden)
            {
                if (compilatie.GetTypeByMetadataName(naam) is { } type)
                {
                    _httpVerboden.Add((type, lid));
                }
            }

            foreach (var wit in Regels.HttpWitteLijst)
            {
                if (compilatie.GetTypeByMetadataName(wit.Type) is { } type)
                {
                    _httpWit.Add((type, wit));
                }
            }

            foreach (var wit in Regels.HostOptieWitteLijst)
            {
                if (compilatie.GetTypeByMetadataName(wit.Type) is { } type)
                {
                    _hostWit.Add((type, wit));
                }
            }

            Vul(compilatie, Regels.HostOptieTypen, _hostOptieTypen);
            foreach (var (naam, voorvoegsel) in Regels.DoorstuurStatusLeden)
            {
                if (compilatie.GetTypeByMetadataName(naam) is { } type)
                {
                    _doorstuurStatus.Add((type, voorvoegsel));
                }
            }

            foreach (var wit in Regels.DoorstuurWitteLijst)
            {
                if (compilatie.GetTypeByMetadataName(wit.Type) is { } type)
                {
                    _doorstuurWit.Add((type, wit));
                }
            }

            foreach (var naam in Regels.BestandVolledigTypen)
            {
                if (compilatie.GetTypeByMetadataName(naam) is { } type)
                {
                    _volledig.Add(type);
                }
            }

            foreach (var wit in Regels.ServerAbiWitteLijst)
            {
                if (compilatie.GetTypeByMetadataName(wit.Type) is { } type)
                {
                    _serverWit.Add((type, wit));
                }
            }

            foreach (var wit in Regels.UitbreidingWitteLijst)
            {
                if (compilatie.GetTypeByMetadataName(wit.Type) is { } type)
                {
                    var argument = wit.Typeargument is null ? null : compilatie.GetTypeByMetadataName(wit.Typeargument);
                    if (wit.Typeargument is null || argument is not null)
                    {
                        _uitbreidingWit.Add((type, wit, argument));
                    }
                }
            }
            foreach (var regel in Regels.Typen)
            {
                if (compilatie.GetTypeByMetadataName(regel.Type) is { } type)
                {
                    _typen.Add((type, regel));
                }
            }

            foreach (var (regelId, naam, alleenMetPad, nergens) in Regels.Aanmaak)
            {
                if (compilatie.GetTypeByMetadataName(naam) is { } type)
                {
                    _aanmaak.Add((type, regelId, alleenMetPad, nergens));
                }
            }

            foreach (var wit in Regels.BestandWitteLijst)
            {
                if (compilatie.GetTypeByMetadataName(wit.Type) is { } type)
                {
                    _wit.Add((type, wit));
                }
            }

            _uitzondering = compilatie.GetTypeByMetadataName("System.Exception");
            _stroom = compilatie.GetTypeByMetadataName("System.IO.Stream");
            _xmlSchrijver = compilatie.GetTypeByMetadataName("System.Xml.XmlWriter");
            _libraryImport = compilatie.GetTypeByMetadataName("System.Runtime.InteropServices.LibraryImportAttribute");

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
                if (!Toegestaan(context.ContainingSymbol, regel, api)
                    && !(regel.RegelId == Regels.BestandSchrijf && MeldtDatabasetoegang(context, out _)))
                {
                    context.ReportDiagnostic(Diagnostic.Create(Descriptor(regel), context.Operation.Syntax.GetLocation(), api));
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
                if (!Toegestaan(context.ContainingSymbol, regel, api))
                {
                    context.ReportDiagnostic(Diagnostic.Create(Descriptor(regel), verwijzing.Syntax.GetLocation(), api));
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

            foreach (var (type, regelId, alleenMetPad, nergens) in _aanmaak)
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

                if (nergens || !Toegestaan(context.ContainingSymbol, regelId, null))
                {
                    var descriptor = nergens && regelId == Regels.BestandSchrijf ? _serverBestand : Descriptor(regelId);
                    context.ReportDiagnostic(Diagnostic.Create(descriptor, aanmaak.Syntax.GetLocation(), "new " + type.ToDisplayString()));
                }

                return;
            }
        }

        /// <summary>
        /// JL0002 bestanden (R-HARDE-EIS-13): buiten de opslagnamespaces is elk lid van een type uit de bestandsnamespaces
        /// (System.IO met de subnamespaces, System.Formats.Tar, Microsoft.VisualBasic.FileIO) en elk aanmaken ervan verboden,
        /// behalve wat op de witte lijst staat (<see cref="Regels.BestandWitteLijst"/>). Ook een eigen type dat van zo'n type
        /// afleidt telt bij aanmaken als dat type, en een aanroep van de basisconstructor (<c>: base(pad)</c>) ook. File,
        /// Directory en FileSystemInfo houden hun eigen leesvoorvoegsels (<see cref="Methode"/>, <see cref="Eigenschap"/>).
        /// Een type uit System.Reflection.Emit (code maken) is nergens toegestaan.
        /// </summary>
        public void Bestandstoegang(OperationAnalysisContext context)
        {
            ISymbol? lid;
            INamedTypeSymbol? type;
            IMethodSymbol? constructor = null;
            var geschreven = false;
            switch (context.Operation)
            {
                case IInvocationOperation { TargetMethod.MethodKind: MethodKind.Constructor } basis:
                    constructor = basis.TargetMethod;
                    lid = constructor;
                    type = constructor.ContainingType;
                    break;
                case IInvocationOperation aanroep:
                    lid = aanroep.TargetMethod.ReducedFrom ?? aanroep.TargetMethod;
                    type = lid.ContainingType;
                    break;
                case IMethodReferenceOperation verwijzing:
                    lid = verwijzing.Method.ReducedFrom ?? verwijzing.Method;
                    type = lid.ContainingType;
                    break;
                case IPropertyReferenceOperation eigenschap:
                    lid = eigenschap.Property;
                    type = lid.ContainingType;
                    geschreven = eigenschap.Parent switch
                    {
                        IAssignmentOperation toewijzing => ReferenceEquals(toewijzing.Target, eigenschap),
                        IIncrementOrDecrementOperation => true,
                        _ => false,
                    };
                    break;
                case IFieldReferenceOperation veld:
                    lid = veld.Field;
                    type = lid.ContainingType;
                    break;
                case IEventReferenceOperation gebeurtenis:
                    lid = gebeurtenis.Event;
                    type = lid.ContainingType;
                    break;
                case IObjectCreationOperation aanmaak:
                    constructor = aanmaak.Constructor;
                    lid = constructor;
                    type = aanmaak.Type as INamedTypeSymbol;
                    break;
                default:
                    return;
            }

            if (lid is null || type is null)
            {
                return;
            }

            // Bij aanmaken telt het eerste type in de keten dat in een bestandsnamespace ligt (een eigen of upstream-type
            // dat van StreamWriter afleidt, zoals Jellyfin.Extensions.FormattingStreamWriter, telt als StreamWriter).
            var bestand = constructor is null ? (IsType(type, Regels.BestandNamespaces, Regels.BestandTypen) ? type : null) : EersteBestandstype(type);
            if (bestand is null)
            {
                if ((constructor is null ? type : EersteType(type, Regels.OmwegNamespaces)) is { TypeKind: not TypeKind.Enum } omweg && IsType(omweg, Regels.OmwegNamespaces, ImmutableArray<string>.Empty))
                {
                    context.ReportDiagnostic(Diagnostic.Create(_omweg, context.Operation.Syntax.GetLocation(), Naam(omweg, lid, constructor)));
                }

                return;
            }

            if (InNamespace(context.ContainingSymbol, Regels.OpslagNamespaces))
            {
                return;
            }

            // File, Directory, FileInfo/DirectoryInfo: methoden en het zetten van een eigenschap bepaalt hun eigen regel.
            var eigenRegel = _typen.Any(t => t.Regel.RegelId == Regels.BestandSchrijf && HoortBij(bestand, t.Type));
            if (eigenRegel && constructor is null && (lid is IMethodSymbol || geschreven))
            {
                return;
            }

            if (!BestandToegestaan(bestand, lid, constructor, geschreven))
            {
                context.ReportDiagnostic(Diagnostic.Create(_bestandSchrijf, context.Operation.Syntax.GetLocation(), Naam(bestand, lid, constructor)));
            }
        }

        private bool BestandToegestaan(INamedTypeSymbol type, ISymbol lid, IMethodSymbol? constructor, bool geschreven)
        {
            if (type.TypeKind == TypeKind.Enum || (_uitzondering is not null && HoortBij(type, _uitzondering)))
            {
                return true;
            }

            // Een constructor met FileStreamOptions opent een bestand met een zelfgekozen modus en toegang (Truncate, Create,
            // ReadWrite), ook bij een lezer als StreamReader: nooit op de witte lijst (R-HARDE-EIS, herreview 6).
            if (constructor is not null && _streamOpties is not null && constructor.Parameters.Any(p => SymbolEqualityComparer.Default.Equals(p.Type, _streamOpties)))
            {
                return false;
            }

            foreach (var (witType, wit) in _wit)
            {
                if (constructor is not null)
                {
                    if (!SymbolEqualityComparer.Default.Equals(type.OriginalDefinition, witType))
                    {
                        continue;
                    }

                    if (wit.Aanmaak == BestandWit.Aanmaken.Ja
                        || (wit.Aanmaak == BestandWit.Aanmaken.ZonderTekst && !constructor.Parameters.Any(p => p.Type.SpecialType == SpecialType.System_String)))
                    {
                        return true;
                    }

                    continue;
                }

                var past = SymbolEqualityComparer.Default.Equals(type.OriginalDefinition, witType) || (wit.MetAfgeleiden && HoortBij(type, witType));
                if (past && (wit.StaatToe(lid.Name) || (wit.EigenschappenLezen && lid is IPropertySymbol && !geschreven)))
                {
                    return true;
                }
            }

            return false;
        }

        /// <summary>Het type zelf of het eerste basistype dat in de bestandsnamespaces ligt.</summary>
        private static INamedTypeSymbol? EersteBestandstype(INamedTypeSymbol type)
        {
            for (var t = type; t is not null; t = t.BaseType)
            {
                if (IsType(t, Regels.BestandNamespaces, Regels.BestandTypen))
                {
                    return t;
                }
            }

            return null;
        }

        private static INamedTypeSymbol? EersteType(INamedTypeSymbol type, ImmutableArray<string> namespaces)
        {
            for (var t = type; t is not null; t = t.BaseType)
            {
                if (IsType(t, namespaces, ImmutableArray<string>.Empty))
                {
                    return t;
                }
            }

            return null;
        }

        private static bool IsType(INamedTypeSymbol type, ImmutableArray<string> namespaces, ImmutableArray<string> typen) =>
            Regels.InNamespace(type.ContainingNamespace?.ToDisplayString() ?? string.Empty, namespaces)
            || typen.Contains(type.OriginalDefinition.ToDisplayString());

        private static string Naam(INamedTypeSymbol type, ISymbol lid, IMethodSymbol? constructor) =>
            constructor is not null ? "new " + type.OriginalDefinition.ToDisplayString() : type.OriginalDefinition.ToDisplayString() + "." + lid.Name;

        /// <summary>
        /// JL0002 het schrijvende deel van System.Xml en System.Xml.Linq (R-HARDE-EIS-13): <c>Save</c>, <c>WriteTo</c>,
        /// <c>WriteContentTo</c>, <c>Transform</c> en <c>Serialize</c> met een pad of een stroom als parameter, en een
        /// XmlWriter maken met een pad of stroom (<c>XmlWriter.Create(pad)</c>, <c>new XmlTextWriter(pad, …)</c>). Met een
        /// TextWriter of XmlWriter mag het: die naar een bestand krijgen is zelf al JL0002.
        /// </summary>
        public void XmlSchrijven(OperationAnalysisContext context)
        {
            var methode = context.Operation switch
            {
                IInvocationOperation aanroep => aanroep.TargetMethod.ReducedFrom ?? aanroep.TargetMethod,
                IMethodReferenceOperation verwijzing => verwijzing.Method.ReducedFrom ?? verwijzing.Method,
                IObjectCreationOperation aanmaak => aanmaak.Constructor,
                _ => null,
            };
            if (methode?.ContainingType is not { } type || !Regels.InNamespace(type.ContainingNamespace?.ToDisplayString() ?? string.Empty, Regels.XmlNamespaces))
            {
                return;
            }

            var schrijver = _xmlSchrijver is not null && HoortBij(type, _xmlSchrijver);
            var schrijft = methode.MethodKind == MethodKind.Constructor
                ? schrijver
                : Regels.XmlSchrijfLeden.Any(v => TypeRegel.IsVoorvoegsel(v, methode.Name)) || (schrijver && TypeRegel.IsVoorvoegsel("Create", methode.Name));
            if (!schrijft || !methode.Parameters.Any(p => p.Type.SpecialType == SpecialType.System_String || (_stroom is not null && p.Type is INamedTypeSymbol t && HoortBij(t, _stroom)))
                || InNamespace(context.ContainingSymbol, Regels.OpslagNamespaces))
            {
                return;
            }

            context.ReportDiagnostic(Diagnostic.Create(_bestandSchrijf, context.Operation.Syntax.GetLocation(), methode.MethodKind == MethodKind.Constructor ? "new " + type.ToDisplayString() : type.ToDisplayString() + "." + methode.Name));
        }

        /// <summary>
        /// JL0002 (R-HARDE-EIS-15): buiten de opslagnamespaces is elk gebruik van <see cref="Regels.BestandVolledigTypen"/>
        /// verboden, ook lezen en ook van een type dat ervan afleidt: <c>WebClient</c> en <c>WebRequest</c> (met een
        /// file:-adres schrijven ze in elk bestand) en de trace-laag (een listener schrijft in een zelfgekozen bestand).
        /// </summary>
        public void VolledigVerboden(OperationAnalysisContext context)
        {
            var (lid, type, constructor) = LidEnType(context.Operation);
            if (lid is null || type is null || InNamespace(context.ContainingSymbol, Regels.OpslagNamespaces))
            {
                return;
            }

            for (var t = type; t is not null; t = t.BaseType)
            {
                if (_volledig.Any(v => SymbolEqualityComparer.Default.Equals(t.OriginalDefinition, v)))
                {
                    context.ReportDiagnostic(Diagnostic.Create(_bestandSchrijf, context.Operation.Syntax.GetLocation(), Naam(t, lid, constructor)));
                    return;
                }
            }
        }

        /// <summary>Het lid, het type waarop het werkt en (bij aanmaken of een basisconstructor) de constructor.</summary>
        private static (ISymbol? Lid, INamedTypeSymbol? Type, IMethodSymbol? Constructor) LidEnType(IOperation operatie)
        {
            switch (operatie)
            {
                case IInvocationOperation { TargetMethod.MethodKind: MethodKind.Constructor } basis:
                    return (basis.TargetMethod, basis.TargetMethod.ContainingType, basis.TargetMethod);
                case IInvocationOperation aanroep:
                    var methode = aanroep.TargetMethod.ReducedFrom ?? aanroep.TargetMethod;
                    return (methode, methode.ContainingType, null);
                case IMethodReferenceOperation verwijzing:
                    var bedoeld = verwijzing.Method.ReducedFrom ?? verwijzing.Method;
                    return (bedoeld, bedoeld.ContainingType, null);
                case IPropertyReferenceOperation eigenschap:
                    return (eigenschap.Property, eigenschap.Property.ContainingType, null);
                case IFieldReferenceOperation veld:
                    return (veld.Field, veld.Field.ContainingType, null);
                case IEventReferenceOperation gebeurtenis:
                    return (gebeurtenis.Event, gebeurtenis.Event.ContainingType, null);
                case IObjectCreationOperation aanmaak:
                    var gemaakt = aanmaak.Type as INamedTypeSymbol;
                    return ((ISymbol?)aanmaak.Constructor ?? gemaakt, gemaakt, aanmaak.Constructor);
                default:
                    return (null, null, null);
            }
        }

        /// <summary>
        /// JL0001 server-ABI (R-HARDE-EIS-14 en -16, S-G1-17 herstelronde 7): elk gebruik van een lid van een servertype
        /// (MediaBrowser.*, Jellyfin.* behalve de eigen plugin, Emby.*) is verboden, behalve wat in deze klasse op
        /// <see cref="Regels.ServerAbiWitteLijst"/> staat. Een eigenschap of veld van een servertype zetten is altijd verboden,
        /// behalve in de objectinitialisatie van een aanmaak die op de witte lijst staat. Een constante (ook een enumwaarde)
        /// lezen mag. Wat een andere regel al meldt of vrijgeeft (de bewaakte typen, de server-ABI die zelf schrijft,
        /// databasetoegang, bestanden, de naam van de serverdatabase), meldt deze regel niet nog eens.
        /// </summary>
        public void ServerAbi(OperationAnalysisContext context)
        {
            var operatie = context.Operation;
            ISymbol? lid;
            var geschreven = false;
            switch (operatie)
            {
                case IInvocationOperation aanroep:
                    lid = aanroep.TargetMethod.ReducedFrom ?? aanroep.TargetMethod;
                    break;
                case IMethodReferenceOperation verwijzing:
                    lid = verwijzing.Method.ReducedFrom ?? verwijzing.Method;
                    break;
                case IPropertyReferenceOperation eigenschap:
                    lid = eigenschap.Property;
                    geschreven = IsGeschreven(eigenschap);
                    break;
                case IFieldReferenceOperation veld:
                    if (veld.Field.IsConst)
                    {
                        return;
                    }

                    lid = veld.Field;
                    geschreven = IsGeschreven(veld);
                    break;
                case IEventReferenceOperation gebeurtenis:
                    lid = gebeurtenis.Event;
                    break;
                case IObjectCreationOperation aanmaak:
                    lid = (ISymbol?)aanmaak.Constructor ?? aanmaak.Type;
                    break;
                case IBinaryOperation binair:
                    lid = binair.OperatorMethod;
                    break;
                case IUnaryOperation unair:
                    lid = unair.OperatorMethod;
                    break;
                case IConversionOperation omzetting:
                    lid = omzetting.OperatorMethod;
                    break;
                case ICompoundAssignmentOperation samengesteld:
                    lid = samengesteld.OperatorMethod;
                    break;
                case IIncrementOrDecrementOperation ophoging:
                    lid = ophoging.OperatorMethod;
                    break;
                default:
                    return;
            }

            var type = lid as INamedTypeSymbol ?? lid?.ContainingType;
            if (lid is null || type is null || !IsServertype(type) || DoorEenAndereRegel(context, lid, type, geschreven))
            {
                return;
            }

            var naam = type.OriginalDefinition.ToDisplayString() + "." + (lid is INamedTypeSymbol ? ".ctor" : lid.Name);
            var klasse = BuitensteType(context.ContainingSymbol)?.ToDisplayString();
            if (geschreven)
            {
                if (!InitialisatieToegestaan(operatie, klasse))
                {
                    context.ReportDiagnostic(Diagnostic.Create(_serverToewijzing, operatie.Syntax.GetLocation(), naam));
                }

                return;
            }

            var lidnaam = lid is INamedTypeSymbol ? ".ctor" : lid.Name;
            if (!_serverWit.Any(w => w.Wit.Lid == lidnaam && w.Wit.Klasse == klasse && SymbolEqualityComparer.Default.Equals(type.OriginalDefinition, w.Type)))
            {
                context.ReportDiagnostic(Diagnostic.Create(_serverAbi, operatie.Syntax.GetLocation(), naam));
            }
        }

        /// <summary>Waar als het type bij de server-ABI hoort (niet de eigen assembly of de eigen namespace).</summary>
        private bool IsServertype(INamedTypeSymbol type)
        {
            var origineel = type.OriginalDefinition;
            return !SymbolEqualityComparer.Default.Equals(origineel.ContainingAssembly, _eigen)
                && Regels.IsServerAbi(origineel.ContainingNamespace?.ToDisplayString() ?? string.Empty, origineel.ContainingAssembly?.Identity.Name);
        }

        /// <summary>Waar als de operatie een eigenschap of veld schrijft (toewijzing, ++/--, ref/out, deconstructie).</summary>
        private static bool IsGeschreven(IOperation verwijzing)
        {
            var ouder = verwijzing.Parent;
            switch (ouder)
            {
                case IAssignmentOperation toewijzing:
                    return ReferenceEquals(toewijzing.Target, verwijzing);
                case IIncrementOrDecrementOperation:
                    return true;
                case IArgumentOperation argument:
                    return argument.Parameter?.RefKind is RefKind.Ref or RefKind.Out;
            }

            var hier = verwijzing;
            while (ouder is ITupleOperation)
            {
                hier = ouder;
                ouder = ouder.Parent;
            }

            return ouder is IDeconstructionAssignmentOperation deconstructie && ReferenceEquals(deconstructie.Target, hier);
        }

        /// <summary>
        /// Waar als een andere regel deze operatie al meldt of vrijgeeft: een verboden lid van een bewaakt type (ook het zetten
        /// van een eigenschap daarvan), een aanmaak uit <see cref="Regels.Aanmaak"/>, een aanmaak die de bestandsregel meldt,
        /// databasetoegang of een operatie die de naam van een databasetype van de server noemt (JL0003).
        /// </summary>
        private bool DoorEenAndereRegel(OperationAnalysisContext context, ISymbol lid, INamedTypeSymbol type, bool geschreven)
        {
            // Methode() ziet alleen aanroepen en methodegroepen, Eigenschap() alleen het zetten van een eigenschap.
            var methode = context.Operation is IInvocationOperation or IMethodReferenceOperation;
            foreach (var (bewaakt, regel) in _typen)
            {
                if (LidVan(lid, bewaakt) is { } naam && (geschreven ? lid is IPropertySymbol : methode && regel.IsVerboden(naam)))
                {
                    return true;
                }
            }

            if (lid is IMethodSymbol { MethodKind: MethodKind.Constructor } constructor)
            {
                foreach (var (aanmaakType, _, alleenMetPad, _) in _aanmaak)
                {
                    if (HoortBij(type, aanmaakType) && (!alleenMetPad || constructor.Parameters.FirstOrDefault()?.Type.SpecialType == SpecialType.System_String))
                    {
                        return true;
                    }
                }

                if (EersteBestandstype(type) is { } bestand && !InNamespace(context.ContainingSymbol, Regels.OpslagNamespaces)
                    && !BestandToegestaan(bestand, constructor, constructor, false))
                {
                    return true;
                }
            }

            return MeldtDatabasetoegang(context, out _) || NoemtServerdatabase(context.Operation);
        }

        /// <summary>
        /// Waar als een eigenschap wordt gezet in de objectinitialisatie (<c>new T { P = … }</c>) van een aanmaak die in deze
        /// klasse op de witte lijst staat, en de eigenschap bij die aanmaak genoemd is.
        /// </summary>
        private bool InitialisatieToegestaan(IOperation operatie, string? klasse)
        {
            if (operatie is not IPropertyReferenceOperation { Instance: IInstanceReferenceOperation { ReferenceKind: InstanceReferenceKind.ImplicitReceiver } } eigenschap
                || eigenschap.Parent is not ISimpleAssignmentOperation { Parent: IObjectOrCollectionInitializerOperation { Parent: IObjectCreationOperation aanmaak } }
                || aanmaak.Type is not INamedTypeSymbol gemaakt)
            {
                return false;
            }

            return _serverWit.Any(w => w.Wit.Lid == ".ctor" && w.Wit.Klasse == klasse
                && SymbolEqualityComparer.Default.Equals(gemaakt.OriginalDefinition, w.Type)
                && w.Wit.Initialisatie.Contains(eigenschap.Property.Name));
        }

        /// <summary>
        /// JL0001 uitbreidingspunten (R-HARDE-EIS-16): een type van de plugin dat een servertype implementeert of ervan
        /// afleidt, moet daarvoor op <see cref="Regels.UitbreidingWitteLijst"/> staan, in precies zijn namespace. Wat een
        /// toegestaan servertype zelf meebrengt (de interfaces van <c>BasePlugin&lt;T&gt;</c>) mag mee; een servertype dat het
        /// plugintype zelf (opnieuw) noemt, moet er zelf op staan. Ook via een eigen tussentype (een eigen interface of
        /// basisklasse) telt het servertype mee.
        /// </summary>
        public void Uitbreiding(SymbolAnalysisContext context)
        {
            var type = (INamedTypeSymbol)context.Symbol;
            if (type.IsImplicitlyDeclared || type.Locations.FirstOrDefault(l => l.IsInSource) is not { } plek)
            {
                return;
            }

            var ruimte = type.ContainingNamespace?.ToDisplayString() ?? string.Empty;
            var alle = new List<INamedTypeSymbol>();
            for (var t = type.BaseType; t is not null; t = t.BaseType)
            {
                alle.Add(t);
            }

            alle.AddRange(type.AllInterfaces);
            var server = alle.Where(IsServertype).ToList();
            if (server.Count == 0)
            {
                return;
            }

            var toegestaan = new HashSet<INamedTypeSymbol>(SymbolEqualityComparer.Default);
            foreach (var s in server.Where(s => Uitbreidbaar(s, ruimte)))
            {
                toegestaan.Add(s);
                for (var t = s.BaseType; t is not null; t = t.BaseType)
                {
                    toegestaan.Add(t);
                }

                foreach (var i in s.AllInterfaces)
                {
                    toegestaan.Add(i);
                }
            }

            var direct = new List<INamedTypeSymbol>(type.Interfaces);
            if (type.BaseType is { } basis)
            {
                direct.Add(basis);
            }

            var fout = server.Where(s => !toegestaan.Contains(s))
                .Concat(direct.Where(d => IsServertype(d) && !Uitbreidbaar(d, ruimte)))
                .Select(s => s.ToDisplayString())
                .Distinct(StringComparer.Ordinal)
                .OrderBy(s => s, StringComparer.Ordinal)
                .ToList();
            if (fout.Count > 0)
            {
                context.ReportDiagnostic(Diagnostic.Create(_serverUitbreiding, plek, type.ToDisplayString(), string.Join(", ", fout)));
            }
        }

        private bool Uitbreidbaar(INamedTypeSymbol servertype, string ruimte) =>
            _uitbreidingWit.Any(w => w.Wit.Ruimte == ruimte
                && SymbolEqualityComparer.Default.Equals(servertype.OriginalDefinition, w.Type)
                && (w.Argument is null || (servertype.TypeArguments.Length == 1 && SymbolEqualityComparer.Default.Equals(servertype.TypeArguments[0], w.Argument))));

        /// <summary>
        /// JL0002 (R-HARDE-EIS-14a): een override van <c>BasePlugin&lt;T&gt;.ConfigurationFileName</c>,
        /// <c>SaveConfiguration</c> of <c>UpdateConfiguration</c>, of een expliciete implementatie van een lid van
        /// <c>IHasPluginConfiguration</c>, verlegt waar de server de pluginconfiguratie schrijft (al bij het lezen van
        /// <c>Configuration</c>). Nergens toegestaan.
        /// </summary>
        public void PluginConfig(SymbolAnalysisContext context)
        {
            var lid = context.Symbol;
            if (lid.IsImplicitlyDeclared || lid.Locations.FirstOrDefault(l => l.IsInSource) is not { } plek)
            {
                return;
            }

            for (var o = Overschreven(lid); o is not null; o = Overschreven(o))
            {
                if (_basisPlugin is not null && SymbolEqualityComparer.Default.Equals(o.ContainingType?.OriginalDefinition, _basisPlugin) && Regels.PluginConfigLeden.Contains(o.Name))
                {
                    context.ReportDiagnostic(Diagnostic.Create(_pluginConfig, plek, "override " + o.ContainingType!.OriginalDefinition.ToDisplayString() + "." + o.Name));
                    return;
                }
            }

            var expliciet = lid switch
            {
                IMethodSymbol m => m.ExplicitInterfaceImplementations.Cast<ISymbol>(),
                IPropertySymbol p => p.ExplicitInterfaceImplementations.Cast<ISymbol>(),
                _ => Enumerable.Empty<ISymbol>(),
            };
            if (_pluginConfiguratie is not null
                && expliciet.FirstOrDefault(i => SymbolEqualityComparer.Default.Equals(i.ContainingType?.OriginalDefinition, _pluginConfiguratie) && Regels.PluginConfigLeden.Contains(i.Name)) is { } geraakt)
            {
                context.ReportDiagnostic(Diagnostic.Create(_pluginConfig, plek, geraakt.ContainingType.ToDisplayString() + "." + geraakt.Name));
            }
        }

        /// <summary>
        /// JL0001 HTTP-laag (R-HARDE-EIS-17, S-G1-17 herstelronde 8): de pijplijn van de server opbouwen
        /// (<see cref="Regels.HttpPijplijnTypen"/> en hun extensiemethoden), de instellingen van de HTTP-laag
        /// (<see cref="Regels.HttpOptieTypen"/>), elk lid uit <see cref="Regels.HttpLedenNamespaces"/> (behalve een constante),
        /// de losse leden uit <see cref="Regels.HttpVerbodenLeden"/>, een eigenschap van het verzoek of de context zetten
        /// (<see cref="Regels.HttpZetTypen"/>), de verzoekkoppen anders gebruiken dan rechtstreeks lezen, en een waarde uit die
        /// namespaces als ander type doorgeven (een <c>RouteValueDictionary</c> als <c>IDictionary</c>). Behalve wat in deze
        /// klasse op <see cref="Regels.HttpWitteLijst"/> staat. Attributen op eigen code tellen niet: die gelden alleen voor
        /// die code.
        /// </summary>
        public void HttpLaag(OperationAnalysisContext context)
        {
            var operatie = context.Operation;
            if (operatie.Syntax.FirstAncestorOrSelf<AttributeSyntax>() is not null)
            {
                return;
            }

            if (operatie is IConversionOperation omzetting)
            {
                if (omzetting.Operand.Type is INamedTypeSymbol bron && omzetting.Type is { } doel && !omzetting.Conversion.IsIdentity
                    && !SymbolEqualityComparer.Default.Equals(bron, doel) && InHttpLedenNamespace(bron))
                {
                    context.ReportDiagnostic(Diagnostic.Create(_httpLaag, operatie.Syntax.GetLocation(), bron.OriginalDefinition.ToDisplayString() + " als " + doel.ToDisplayString()));
                }

                return;
            }

            var klasse = BuitensteType(context.ContainingSymbol)?.ToDisplayString();
            if (operatie is ITypeOfOperation typeOf)
            {
                // typeof(IConfigureOptions<JsonOptions>): een registratie van een instelling van de host zonder lid of typeargument.
                if (EersteHostOptie(typeOf.TypeOperand) is { } optie && !HostOptieToegestaan(klasse, "typeof", optie))
                {
                    context.ReportDiagnostic(Diagnostic.Create(_hostOptie, operatie.Syntax.GetLocation(), "typeof(" + typeOf.TypeOperand.ToDisplayString() + ")"));
                }

                return;
            }

            var (lid, type, constructor) = LidEnType(operatie);
            if (lid is null || type is null)
            {
                return;
            }

            var lidnaam = constructor is not null ? ".ctor" : lid.Name;
            if (HttpVerboden(operatie, lid, type, constructor) is { } api)
            {
                var declarerend = (constructor is not null ? type : lid.ContainingType)?.OriginalDefinition;
                if (!_httpWit.Any(w => w.Wit.Lid == lidnaam && w.Wit.Klasse == klasse && SymbolEqualityComparer.Default.Equals(declarerend, w.Type)))
                {
                    context.ReportDiagnostic(Diagnostic.Create(_httpLaag, operatie.Syntax.GetLocation(), api));
                }

                return;
            }

            if (Doorsturen(operatie, lid, type, constructor) is { } doorsturen)
            {
                if (!DoorstuurToegestaan(operatie, lid, klasse))
                {
                    context.ReportDiagnostic(Diagnostic.Create(_doorsturen, operatie.Syntax.GetLocation(), doorsturen));
                }

                return;
            }

            if (HostOptie(operatie, lid, type, constructor) is { } hostOptie && !HostOptieToegestaan(klasse, lidnaam, hostOptie))
            {
                context.ReportDiagnostic(Diagnostic.Create(_hostOptie, operatie.Syntax.GetLocation(), Naam(type, lid, constructor)));
            }
        }

        /// <summary>
        /// JL0001 de browser als tussenpersoon (R-HARDE-EIS-18, S-G1-17 herstelronde 9): een lid of aanmaak die een antwoord laat
        /// doorsturen (<see cref="Regels.DoorstuurWoorden"/>, <see cref="Regels.DoorstuurStatusLeden"/>), of een statuscode 3xx als
        /// constante op een eigenschap of parameter uit <see cref="Regels.DoorstuurStatusNamen"/>. Null als dat niet zo is.
        /// </summary>
        private string? Doorsturen(IOperation operatie, ISymbol lid, INamedTypeSymbol type, IMethodSymbol? constructor)
        {
            var declarerend = (constructor is not null ? type : lid.ContainingType ?? type).OriginalDefinition;
            var naam = Naam(type, lid, constructor);
            if (IsDoorstuurType(declarerend))
            {
                var lidnaam = constructor is not null || lid is INamedTypeSymbol ? string.Empty : lid.Name;
                if (Regels.DoorstuurWoorden.Any(w => lidnaam.Contains(w) || declarerend.Name.Contains(w)))
                {
                    return naam;
                }

                if (_doorstuurStatus.Any(s => SymbolEqualityComparer.Default.Equals(declarerend, s.Type) && lidnaam.StartsWith(s.Voorvoegsel, StringComparison.Ordinal)))
                {
                    return naam;
                }

                // Een 3xx-waarde van de statusenum (HttpStatusCode.Found, .SeeOther, .TemporaryRedirect, …; R-HARDE-EIS-20).
                if (lid is IFieldSymbol { HasConstantValue: true } veld && Regels.DoorstuurStatusEnums.Contains(declarerend.ToDisplayString())
                    && veld.ConstantValue is int code && code >= 300 && code <= 399)
                {
                    return naam;
                }

                if (lid is IPropertySymbol eigenschap && Regels.DoorstuurStatusNamen.Contains(eigenschap.Name)
                    && operatie.Parent is IAssignmentOperation toewijzing && ReferenceEquals(toewijzing.Target, operatie) && Is3xx(toewijzing.Value))
                {
                    return naam + " = 3xx";
                }
            }

            var argumenten = operatie switch
            {
                IInvocationOperation aanroep => aanroep.Arguments,
                IObjectCreationOperation aanmaak => aanmaak.Arguments,
                _ => ImmutableArray<IArgumentOperation>.Empty,
            };
            foreach (var argument in argumenten)
            {
                if (argument.Parameter is { } parameter && Regels.DoorstuurStatusNamen.Contains(parameter.Name)
                    && parameter.ContainingSymbol?.ContainingType is { } eigenaar && IsDoorstuurType(eigenaar.OriginalDefinition) && Is3xx(argument.Value))
                {
                    return naam + " (" + parameter.Name + " 3xx)";
                }
            }

            return null;
        }

        /// <summary>
        /// Waar als dit lid in deze klasse op <see cref="Regels.DoorstuurWitteLijst"/> staat én alleen gelezen wordt als argument
        /// van <see cref="Regels.DoorstuurWitAanroepen"/> op de koppen van een antwoord (kijken of weghalen, nooit zetten).
        /// </summary>
        private bool DoorstuurToegestaan(IOperation operatie, ISymbol lid, string? klasse) =>
            operatie is IFieldReferenceOperation or IPropertyReferenceOperation
            && _doorstuurWit.Any(w => w.Wit.Lid == lid.Name && w.Wit.Klasse == klasse && SymbolEqualityComparer.Default.Equals(lid.ContainingType?.OriginalDefinition, w.Type))
            && operatie.Parent is IArgumentOperation { Parent: IInvocationOperation aanroep }
            && Regels.DoorstuurWitAanroepen.Contains(aanroep.TargetMethod.Name)
            && aanroep.Instance is IPropertyReferenceOperation { Property.Name: "Headers" } koppen
            && koppen.Property.ContainingType?.OriginalDefinition.ToDisplayString() == Regels.DoorstuurWitKoppen;

        private static bool IsDoorstuurType(INamedTypeSymbol type) =>
            Regels.InNamespace(type.ContainingNamespace?.ToDisplayString() ?? string.Empty, Regels.DoorstuurNamespaces);

        /// <summary>Waar als de waarde (na omzettingen) een constante statuscode van 300 tot en met 399 is.</summary>
        private static bool Is3xx(IOperation waarde)
        {
            while (waarde is IConversionOperation omzetting && !waarde.ConstantValue.HasValue)
            {
                waarde = omzetting.Operand;
            }

            return waarde.ConstantValue is { HasValue: true, Value: int code } && code >= 300 && code <= 399;
        }

        /// <summary>
        /// JL0001 een kopnaam die het antwoord doorstuurt (<see cref="Regels.DoorstuurKoppen"/>) als constante: een tekst, een
        /// samenstelling van constanten, een constante geïnterpoleerde tekst of <c>nameof</c>. Ook op een eigen antwoordtype.
        /// </summary>
        public void DoorstuurKop(OperationAnalysisContext context)
        {
            var operatie = context.Operation;
            if (operatie.Syntax.FirstAncestorOrSelf<AttributeSyntax>() is not null || (operatie is IBinaryOperation plus && !IsTekstPlus(plus)))
            {
                return;
            }

            if (operatie.ConstantValue is { HasValue: true, Value: string tekst }
                && Regels.DoorstuurKoppen.Any(k => string.Equals(tekst.Trim(), k, StringComparison.OrdinalIgnoreCase)))
            {
                context.ReportDiagnostic(Diagnostic.Create(_doorsturen, operatie.Syntax.GetLocation(), "\"" + tekst + "\" (kopnaam)"));
            }
        }

        /// <summary>
        /// JL0001 de instellingen van de host (R-HARDE-EIS-19, S-G1-17 herstelronde 9): het optietype van de host dat dit lid
        /// raakt (als declarerend type, ook een afgeleid type; als typeargument van het type, de methode of de ontvanger; of als
        /// eerste parameter van een extensiemethode), of null.
        /// </summary>
        private INamedTypeSymbol? HostOptie(IOperation operatie, ISymbol lid, INamedTypeSymbol type, IMethodSymbol? constructor)
        {
            if (EersteHostOptie(constructor is not null ? type : lid.ContainingType ?? type) is { } optie)
            {
                return optie;
            }

            if (lid is IMethodSymbol { IsExtensionMethod: true, Parameters.Length: > 0 } extensie && EersteHostOptie(extensie.Parameters[0].Type) is { } ontvanger)
            {
                return ontvanger;
            }

            var ruw = operatie switch
            {
                IInvocationOperation aanroep => aanroep.TargetMethod,
                IMethodReferenceOperation verwijzing => verwijzing.Method,
                _ => null,
            };
            if (ruw is null)
            {
                return null;
            }

            foreach (var t in ruw.TypeArguments.Cast<ITypeSymbol?>().Append(ruw.ContainingType).Append(ruw.ReceiverType))
            {
                if (EersteHostOptie(t) is { } gevonden)
                {
                    return gevonden;
                }
            }

            return null;
        }

        /// <summary>Het eerste optietype van de host in dit type: het type zelf of een basistype, een typeargument of het omsluitende type.</summary>
        private INamedTypeSymbol? EersteHostOptie(ITypeSymbol? type)
        {
            switch (type)
            {
                case IArrayTypeSymbol rij:
                    return EersteHostOptie(rij.ElementType);
                case INamedTypeSymbol benoemd:
                    for (var t = benoemd; t is not null; t = t.BaseType)
                    {
                        if (IsHostOptieType(t.OriginalDefinition) || IsOpenOptieInfrastructuur(t))
                        {
                            return t.OriginalDefinition;
                        }
                    }

                    foreach (var argument in benoemd.TypeArguments)
                    {
                        if (EersteHostOptie(argument) is { } gevonden)
                        {
                            return gevonden;
                        }
                    }

                    return EersteHostOptie(benoemd.ContainingType);
                default:
                    return null;
            }
        }

        // Een open optiedienst geldt ook voor de host: een IOptionsFactory<T> kan zonder reflectie met new T()
        // de configuratie voor elk hostoptietype vervangen. Gesloten diensten voor eigen opties blijven toegestaan.
        private static bool IsOpenOptieInfrastructuur(INamedTypeSymbol type) =>
            Regels.InNamespace(type.ContainingNamespace?.ToDisplayString() ?? string.Empty, Regels.OptieInfrastructuurNamespaces)
            && (type.IsUnboundGenericType || type.TypeArguments.Any(BevatTypeparameter));

        private static bool BevatTypeparameter(ITypeSymbol type) => type switch
        {
            ITypeParameterSymbol => true,
            IArrayTypeSymbol rij => BevatTypeparameter(rij.ElementType),
            INamedTypeSymbol benoemd => benoemd.IsUnboundGenericType || benoemd.TypeArguments.Any(BevatTypeparameter),
            _ => false,
        };

        private bool IsHostOptieType(INamedTypeSymbol type) =>
            type.TypeKind is TypeKind.Class or TypeKind.Struct or TypeKind.Interface
            && ((type.Name.EndsWith(Regels.HostOptieAchtervoegsel, StringComparison.Ordinal)
                    && Regels.InNamespace(type.ContainingNamespace?.ToDisplayString() ?? string.Empty, Regels.HostOptieNamespaces))
                || _hostOptieTypen.Any(h => SymbolEqualityComparer.Default.Equals(h, type)));

        private bool HostOptieToegestaan(string? klasse, string lid, INamedTypeSymbol optie) =>
            _hostWit.Any(w => w.Wit.Lid == lid && w.Wit.Klasse == klasse && SymbolEqualityComparer.Default.Equals(w.Type, optie));

        /// <summary>
        /// JL0001 een eigen type dat een optietype van de host implementeert of ervan afleidt, ook als typeargument
        /// (<c>IConfigureOptions&lt;JsonOptions&gt;</c>, <c>IPostConfigureOptions&lt;JsonOptions&gt;</c>,
        /// <c>IConfigureNamedOptions&lt;JsonOptions&gt;</c>), behalve wat op <see cref="Regels.HostOptieWitteLijst"/> staat (leeg).
        /// </summary>
        public void HostOptieUitbreiding(SymbolAnalysisContext context)
        {
            var type = (INamedTypeSymbol)context.Symbol;
            if (type.IsImplicitlyDeclared || type.Locations.FirstOrDefault(l => l.IsInSource) is not { } plek)
            {
                return;
            }

            var alle = new List<INamedTypeSymbol>();
            for (var t = type.BaseType; t is not null; t = t.BaseType)
            {
                alle.Add(t);
            }

            alle.AddRange(type.AllInterfaces);
            var klasse = type.ToDisplayString();
            var fout = alle
                .Where(s => EersteHostOptie(s) is { } optie && !HostOptieToegestaan(klasse, HttpWit.Implementeert, optie))
                .Select(s => s.ToDisplayString())
                .Distinct(StringComparer.Ordinal)
                .OrderBy(s => s, StringComparer.Ordinal)
                .ToList();
            if (fout.Count > 0)
            {
                context.ReportDiagnostic(Diagnostic.Create(_hostOptie, plek, klasse + " : " + string.Join(", ", fout)));
            }
        }

        /// <summary>De naam van wat in de HTTP-laag verboden is, of null als deze operatie daar niet onder valt.</summary>
        private string? HttpVerboden(IOperation operatie, ISymbol lid, INamedTypeSymbol type, IMethodSymbol? constructor)
        {
            var naam = Naam(type, lid, constructor);

            // De pijplijn: een lid van IApplicationBuilder of IEndpointRouteBuilder, of een extensiemethode erop.
            if (_httpPijplijn.Any(p => HoortBij(type, p))
                || (lid is IMethodSymbol { IsExtensionMethod: true, Parameters.Length: > 0 } extensie
                    && extensie.Parameters[0].Type is INamedTypeSymbol ontvanger && _httpPijplijn.Any(p => HoortBij(ontvanger, p))))
            {
                return naam;
            }

            // De instellingen die voor alle routes van de server gelden.
            if (_httpOpties.Any(o => HoortBij(type, o)))
            {
                return naam;
            }

            // Authenticatie, autorisatie, routering, features en herschrijfregels: elk lid, behalve een constante.
            if (InHttpLedenNamespace(type) && lid is not IFieldSymbol { IsConst: true })
            {
                return naam;
            }

            if (_httpVerboden.Any(v => v.Lid == lid.Name && HoortBij(type, v.Type)))
            {
                return naam;
            }

            var geschreven = operatie is IPropertyReferenceOperation or IFieldReferenceOperation && IsGeschreven(operatie);
            if (geschreven && _httpZet.Any(z => HoortBij(type, z)))
            {
                return naam;
            }

            // De verzoekkoppen: alleen rechtstreeks lezen (een kop, TryGetValue, ContainsKey); opslaan, doorgeven of wijzigen niet.
            if (operatie is IPropertyReferenceOperation { Property.Name: "Headers" } koppen && _verzoek is not null && HoortBij(type, _verzoek)
                && !AlleenGelezen(koppen))
            {
                return naam + " (anders dan rechtstreeks lezen)";
            }

            return null;
        }

        /// <summary>Waar als de verzoekkoppen hier alleen rechtstreeks gelezen worden.</summary>
        private static bool AlleenGelezen(IPropertyReferenceOperation koppen) => koppen.Parent switch
        {
            IPropertyReferenceOperation kop when ReferenceEquals(kop.Instance, koppen) => !IsGeschreven(kop),
            IInvocationOperation aanroep when ReferenceEquals(aanroep.Instance, koppen) => aanroep.TargetMethod.Name is "TryGetValue" or "ContainsKey",
            _ => false,
        };

        private static bool InHttpLedenNamespace(INamedTypeSymbol type) =>
            type.TypeKind != TypeKind.Enum && Regels.InNamespace(type.OriginalDefinition.ContainingNamespace?.ToDisplayString() ?? string.Empty, Regels.HttpLedenNamespaces);

        /// <summary>
        /// JL0001 uitbreidingspunten van de HTTP-laag (R-HARDE-EIS-17): een type van de plugin dat een type uit
        /// <see cref="Regels.HttpUitbreidingTypen"/> of uit <see cref="Regels.HttpUitbreidingNamespaces"/> implementeert of
        /// ervan afleidt (ook via een eigen tussentype), moet daarvoor op <see cref="Regels.HttpWitteLijst"/> staan, met precies
        /// zijn eigen volledige naam. Wat een toegestaan type zelf meebrengt (<c>IFilterMetadata</c> bij <c>IAsyncActionFilter</c>)
        /// mag mee.
        /// </summary>
        public void HttpUitbreiding(SymbolAnalysisContext context)
        {
            var type = (INamedTypeSymbol)context.Symbol;
            if (type.IsImplicitlyDeclared || type.Locations.FirstOrDefault(l => l.IsInSource) is not { } plek)
            {
                return;
            }

            var alle = new List<INamedTypeSymbol>();
            for (var t = type.BaseType; t is not null; t = t.BaseType)
            {
                alle.Add(t);
            }

            alle.AddRange(type.AllInterfaces);
            var http = alle.Where(IsHttpUitbreiding).ToList();
            if (http.Count == 0)
            {
                return;
            }

            var klasse = type.ToDisplayString();
            var toegestaan = new HashSet<INamedTypeSymbol>(SymbolEqualityComparer.Default);
            foreach (var s in http.Where(s => _httpWit.Any(w => w.Wit.Lid == HttpWit.Implementeert && w.Wit.Klasse == klasse && SymbolEqualityComparer.Default.Equals(s.OriginalDefinition, w.Type))))
            {
                toegestaan.Add(s);
                for (var t = s.BaseType; t is not null; t = t.BaseType)
                {
                    toegestaan.Add(t);
                }

                foreach (var i in s.AllInterfaces)
                {
                    toegestaan.Add(i);
                }
            }

            var fout = http.Where(s => !toegestaan.Contains(s))
                .Select(s => s.ToDisplayString())
                .Distinct(StringComparer.Ordinal)
                .OrderBy(s => s, StringComparer.Ordinal)
                .ToList();
            if (fout.Count > 0)
            {
                context.ReportDiagnostic(Diagnostic.Create(_httpUitbreiding, plek, klasse, string.Join(", ", fout)));
            }
        }

        private bool IsHttpUitbreiding(INamedTypeSymbol type) =>
            _httpUitbreidingTypen.Any(t => SymbolEqualityComparer.Default.Equals(type.OriginalDefinition, t))
            || Regels.InNamespace(type.OriginalDefinition.ContainingNamespace?.ToDisplayString() ?? string.Empty, Regels.HttpUitbreidingNamespaces);

        /// <summary>
        /// JL0001 netwerkclients (R-HARDE-EIS-17, besluit punt 2): elk lid van een type uit <see cref="Regels.NetwerkNamespaces"/>
        /// of <see cref="Regels.NetwerkTypen"/> (ook van een eigen type dat ervan afleidt, en aanmaken), in elke namespace,
        /// behalve in een klasse uit <see cref="Regels.NetwerkKlassen"/> (nu leeg). Een enumwaarde mag. WebClient en WebRequest
        /// buiten de opslaglaag meldt de bestandsregel al (JL0002); daar volgt geen tweede melding.
        /// </summary>
        public void Netwerk(OperationAnalysisContext context)
        {
            var (lid, type, constructor) = LidEnType(context.Operation);
            if (lid is null || type is null || type.TypeKind == TypeKind.Enum)
            {
                return;
            }

            INamedTypeSymbol? netwerk = null;
            for (var t = type; t is not null && netwerk is null; t = t.BaseType)
            {
                if (IsType(t, Regels.NetwerkNamespaces, ImmutableArray<string>.Empty) || _netwerkTypen.Any(n => SymbolEqualityComparer.Default.Equals(t.OriginalDefinition, n)))
                {
                    netwerk = t;
                }
            }

            if (netwerk is null
                || Regels.NetwerkKlassen.Contains(BuitensteType(context.ContainingSymbol)?.ToDisplayString() ?? string.Empty)
                || (_netwerkTypen.Any(n => HoortBij(netwerk, n)) && !InNamespace(context.ContainingSymbol, Regels.OpslagNamespaces)))
            {
                return;
            }

            context.ReportDiagnostic(Diagnostic.Create(_netwerk, context.Operation.Syntax.GetLocation(), Naam(netwerk, lid, constructor)));
        }

        private static void Vul(Compilation compilatie, ImmutableArray<string> namen, List<INamedTypeSymbol> doel)
        {
            foreach (var naam in namen)
            {
                if (compilatie.GetTypeByMetadataName(naam) is { } type)
                {
                    doel.Add(type);
                }
            }
        }

        /// <summary>
        /// JL0002 omweg: een eigen P/Invoke-methode (<c>[DllImport]</c>, <c>[LibraryImport]</c>, <c>extern</c>) aanroepen of
        /// ernaar verwijzen. Nergens toegestaan. (Een functiewijzer kan alleen in een <c>unsafe</c>-context bestaan; die meldt
        /// <see cref="Onveilig"/> al.)
        /// </summary>
        public void NativeAanroep(OperationAnalysisContext context)
        {
            var methode = context.Operation switch
            {
                IInvocationOperation aanroep => aanroep.TargetMethod,
                IMethodReferenceOperation verwijzing => verwijzing.Method,
                _ => null,
            };
            if (methode is not null && SymbolEqualityComparer.Default.Equals(methode.ContainingAssembly, _eigen) && IsNatief(methode))
            {
                context.ReportDiagnostic(Diagnostic.Create(_omweg, context.Operation.Syntax.GetLocation(), methode.ContainingType.ToDisplayString() + "." + methode.Name));
            }
        }

        /// <summary>JL0002 omweg: een P/Invoke-declaratie (<c>[DllImport]</c>, <c>[LibraryImport]</c>, <c>extern</c>) in plugincode.</summary>
        public void NativeDeclaratie(SymbolAnalysisContext context)
        {
            var methode = (IMethodSymbol)context.Symbol;
            if (IsNatief(methode) && methode.Locations.FirstOrDefault(l => l.IsInSource) is { } plek)
            {
                context.ReportDiagnostic(Diagnostic.Create(_omweg, plek, "[DllImport]/extern " + methode.ContainingType.ToDisplayString() + "." + methode.Name));
            }
        }

        private bool IsNatief(IMethodSymbol methode) =>
            methode.IsExtern
            || methode.GetDllImportData() is not null
            || (_libraryImport is not null && methode.GetAttributes().Any(a => SymbolEqualityComparer.Default.Equals(a.AttributeClass, _libraryImport)));

        /// <summary>
        /// JL0002 omweg: <c>dynamic</c> (een lid, aanroep, index of aanmaak die pas bij het draaien wordt gebonden). Eén melding
        /// per plek: het lid dat zelf wordt aangeroepen (<c>x.Delete(pad)</c>) meldt de aanroep.
        /// </summary>
        public void Dynamisch(OperationAnalysisContext context)
        {
            if (context.Operation is IDynamicMemberReferenceOperation && context.Operation.Parent is IDynamicInvocationOperation aanroep && ReferenceEquals(aanroep.Operation, context.Operation))
            {
                return;
            }

            context.ReportDiagnostic(Diagnostic.Create(_omweg, context.Operation.Syntax.GetLocation(), "dynamic"));
        }

        /// <summary>
        /// JL0002 omweg: <c>unsafe</c> (op een type, lid, lokale functie, blok of using-alias). Nergens toegestaan. Pointers,
        /// <c>fixed</c> en functiewijzers (<c>delegate*</c>) kunnen alleen in zo'n context bestaan; de compiler eist dat.
        /// </summary>
        public void Onveilig(SyntaxNodeAnalysisContext context)
        {
            var sleutel = context.Node switch
            {
                UnsafeStatementSyntax blok => blok.UnsafeKeyword,
                MemberDeclarationSyntax lid => lid.Modifiers.FirstOrDefault(m => m.IsKind(SyntaxKind.UnsafeKeyword)),
                LocalFunctionStatementSyntax functie => functie.Modifiers.FirstOrDefault(m => m.IsKind(SyntaxKind.UnsafeKeyword)),
                UsingDirectiveSyntax alias => alias.UnsafeKeyword,
                _ => default,
            };
            if (sleutel.IsKind(SyntaxKind.None))
            {
                return;
            }

            context.ReportDiagnostic(Diagnostic.Create(_omweg, sleutel.GetLocation(), "unsafe"));
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
            if (!MeldtDatabasetoegang(context, out var type))
            {
                return;
            }

            context.ReportDiagnostic(Diagnostic.Create(_databaseToegang, context.Operation.Syntax.GetLocation(), Beschrijf(context.Operation, type)));
        }

        /// <summary>
        /// Waar als <see cref="Databasetoegang"/> deze operatie meldt. Dan geeft een andere JL0002-regel op dezelfde plek
        /// (bijvoorbeeld de omweg <c>Activator.CreateInstance&lt;SqliteConnection&gt;()</c>) geen tweede melding.
        /// </summary>
        private bool MeldtDatabasetoegang(OperationAnalysisContext context, out ITypeSymbol type)
        {
            type = Databasetype(context.Operation)!;
            return type is not null && Databasetype(Ontvanger(context.Operation)) is null
                && !InNamespace(context.ContainingSymbol, Regels.DatabaseNamespaces) && !NoemtServerdatabase(context.Operation);
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

        /// <summary>Een regel met <c>Nergens</c> (server-ABI die zelf schrijft, omwegen) staat ook de vaste namespaces niet toe.</summary>
        private bool Toegestaan(ISymbol? plek, TypeRegel regel, string api) => !regel.Nergens && Toegestaan(plek, regel.RegelId, api);

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
