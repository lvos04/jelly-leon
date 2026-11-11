using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Analyzers;

/// <summary>Eén bewaakt type: welke leden verboden zijn en of er ooit een uitzondering mag bestaan.</summary>
internal sealed class TypeRegel
{
    public TypeRegel(string regelId, string type, bool alleenLezenToegestaan, bool uitzonderingMogelijk, params string[] voorvoegsels)
    {
        RegelId = regelId;
        Type = type;
        AlleenLezenToegestaan = alleenLezenToegestaan;
        UitzonderingMogelijk = uitzonderingMogelijk;
        Voorvoegsels = voorvoegsels;
    }

    public string RegelId { get; }

    public string Type { get; }

    /// <summary>Waar: alles is verboden behalve de voorvoegsels (leesmethoden). Onwaar: alleen de voorvoegsels zijn verboden.</summary>
    public bool AlleenLezenToegestaan { get; }

    public bool UitzonderingMogelijk { get; }

    public IReadOnlyList<string> Voorvoegsels { get; }

    /// <summary>Leden die ondanks een leesvoorvoegsel toch schrijven (bijvoorbeeld "haal op, en maak aan als hij ontbreekt").</summary>
    public IReadOnlyList<string> OokVerboden { get; set; } = Array.Empty<string>();

    public bool IsVerboden(string lid)
    {
        if (OokVerboden.Contains(lid))
        {
            return true;
        }

        var raak = Voorvoegsels.Any(v => lid.StartsWith(v, StringComparison.Ordinal));
        return AlleenLezenToegestaan ? !raak : raak;
    }
}

/// <summary>De tabellen van de analyzer. Wijzigen kan alleen hier, in één bestand, en hoort in ADR-0032.</summary>
internal static class Regels
{
    public const string ServerSchrijf = "JL0001";
    public const string BestandSchrijf = "JL0002";
    public const string ServerDatabase = "JL0003";
    public const string ProcesStart = "JL0004";
    public const string OngeldigeUitzondering = "JL0009";

    public const string PluginNamespace = "Jellyfin.Plugin.JellyLeon";
    public const string UitzonderingenBestand = "JellyLeon.AnalyzerUitzonderingen.txt";

    private static readonly string[] _lezen = { "Get", "Find", "Query", "Is", "Has", "Can", "To" };

    /// <summary>Namespaces die zelf de schrijfgrens bewaken (<c>JlPaths.MagSchrijven</c>) en dus bestanden mogen schrijven.</summary>
    public static readonly ImmutableArray<string> OpslagNamespaces = ImmutableArray.Create(
        PluginNamespace + ".Core.Storage",
        PluginNamespace + ".Core.Secrets");

    /// <summary>De enige namespace die een proces mag starten (de werkerbewaker van B03-018).</summary>
    public static readonly ImmutableArray<string> ProcesNamespaces = ImmutableArray.Create(PluginNamespace + ".Core.Werker");

    public static readonly ImmutableArray<TypeRegel> Typen = ImmutableArray.Create(
        // Bibliotheek en metadata: schrijven kan nergens (HARDE EIS), ook niet met een uitzondering.
        // Let op: "Get…" is geen garantie. Deze leden maken in upstream v12.4 een item of map aan als die ontbreekt
        // (CreateItemByName, GetNamedView, GetUserRootFolder) en staan daarom met naam bij de verboden leden. De
        // ledenlijst in de test (BewaakteLeden.txt) dwingt bij elke upstream-sync een nieuw oordeel af.
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Library.ILibraryManager", true, false, _lezen)
        {
            OokVerboden = new[] { "GetOrCreatePerson", "GetStudio", "GetGenre", "GetMusicGenre", "GetYear", "GetArtist", "GetNamedView", "GetShadowView", "GetUserRootFolder" }
        },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Persistence.IItemRepository", true, false, "Get", "Retrieve", "ItemExists"),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Persistence.IItemPersistenceService", true, false),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Entities.BaseItem", false, false, "Update", "Delete", "Refresh", "Save", "Add", "Remove", "Set", "Swap", "Changed", "Mark", "Validate", "Reattach", "OnMetadata", "BeforeMetadata", "AfterMetadata"),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Playlists.IPlaylistManager", true, false, _lezen) { OokVerboden = new[] { "GetPlaylistsFolder" } },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Collections.ICollectionManager", true, false, _lezen) { OokVerboden = new[] { "GetCollectionsFolder" } },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Library.IUserManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Devices.IDeviceManager", true, false, _lezen),
        // Kijkgeschiedenis, verversen, ondertitels, segmenten, sessies en serverinstellingen: alleen in één met naam
        // genoemde klasse per uitzondering (bijvoorbeeld F3 SelectionGuard), nooit elders.
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Library.IUserDataManager", true, true, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Providers.IProviderManager", true, true, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Subtitles.ISubtitleManager", true, true, "Get", "Search"),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.MediaSegments.IMediaSegmentManager", true, true, _lezen),
        // GetSessionByAuthenticationToken legt sessieactiviteit vast en werkt daarbij de gebruiker bij.
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Session.ISessionManager", true, true, _lezen) { OokVerboden = new[] { "GetSessionByAuthenticationToken" } },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Configuration.IServerConfigurationManager", true, true, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Common.Configuration.IConfigurationManager", true, true, _lezen),
        // Bestanden: alleen de opslagnamespaces; verwijderen elders alleen in één met naam genoemde klasse.
        new TypeRegel(BestandSchrijf, "System.IO.File", true, true, "Exists", "Read", "OpenRead", "OpenText", "Get"),
        new TypeRegel(BestandSchrijf, "System.IO.Directory", true, true, "Exists", "Get", "Enumerate"),
        new TypeRegel(BestandSchrijf, "System.IO.FileSystemInfo", true, true, "OpenRead", "OpenText", "Get", "Enumerate", "Refresh", "ToString"),
        new TypeRegel(BestandSchrijf, "MediaBrowser.Model.IO.IFileSystem", false, true, "Delete", "Move", "Create", "Swap", "Set"),
        new TypeRegel(ProcesStart, "System.Diagnostics.Process", false, false, "Start"));

    /// <summary>
    /// Typen waarvan het aanmaken al een schrijfactie of een processtart is. Hiervoor bestaat geen uitzondering per
    /// klasse: alleen de vaste namespaces mogen dit.
    /// </summary>
    public static readonly ImmutableArray<(string RegelId, string Type, bool AlleenMetPad)> Aanmaak = ImmutableArray.Create(
        (BestandSchrijf, "System.IO.FileStream", false),
        (BestandSchrijf, "System.IO.StreamWriter", true),
        (BestandSchrijf, "Microsoft.Data.Sqlite.SqliteConnection", false),
        (ProcesStart, "System.Diagnostics.Process", false),
        (ProcesStart, "System.Diagnostics.ProcessStartInfo", false));

    /// <summary>De database van de server zelf: nergens, in geen enkele vorm.</summary>
    public static readonly ImmutableArray<string> ServerDatabaseTypen = ImmutableArray.Create(
        "Jellyfin.Database.Implementations.JellyfinDbContext");

    public static readonly ImmutableArray<string> ServerDatabaseNamen = ImmutableArray.Create("jellyfin.db", "library.db");
}
