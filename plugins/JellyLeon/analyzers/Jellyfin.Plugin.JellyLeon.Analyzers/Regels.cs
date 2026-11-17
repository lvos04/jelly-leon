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

        var raak = Voorvoegsels.Any(v => IsVoorvoegsel(v, lid));
        return AlleenLezenToegestaan ? !raak : raak;
    }

    /// <summary>
    /// Een voorvoegsel telt alleen als heel woord: "Can" past op <c>CanRefresh</c>, niet op <c>CancelTimer</c>; "To" niet
    /// op <c>Toggle</c>; "Is" niet op <c>Issue</c>.
    /// </summary>
    private static bool IsVoorvoegsel(string voorvoegsel, string lid) =>
        lid.StartsWith(voorvoegsel, StringComparison.Ordinal)
        && (lid.Length == voorvoegsel.Length || !char.IsLower(lid[voorvoegsel.Length]));
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

    /// <summary>De wijzigende methoden van een item van de server (<c>BaseItem</c> en elke afgeleide).</summary>
    private static readonly string[] _itemSchrijf = { "Update", "Delete", "Refresh", "Save", "Add", "Remove", "Set", "Swap", "Changed", "Mark", "Validate", "Reattach", "OnMetadata", "BeforeMetadata", "AfterMetadata" };

    /// <summary>Leesleden van een map die bij inhoud van een kanaal de kanaalitems laten verversen of wissen.</summary>
    private static readonly string[] _mapInhoud = { "GetItems", "GetItemList", "GetChildCount", "GetRecursiveChildCount" };

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
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Entities.BaseItem", false, false, _itemSchrijf),
        // Inhoud lezen via het item zelf: bij een map, seizoen of afspeellijst met inhoud van een kanaal laat de server
        // dan via IChannelManager de kanaalitems aanmaken, verversen en de verdwenen items wissen (in v12.4 roepen
        // Folder.GetItemsInternal, Season.GetItemsInternal, Series.GetSeasonEpisodes, UserViewBuilder en
        // Playlist.GetPlaylistItems GetChannelItemsInternal aan). Op naam, dus ook in elke override; een afgeleid type
        // erft de verboden leden van zijn basistype, zodat BewaakteLeden.txt het echte oordeel toont. Lees de bibliotheek
        // via ILibraryManager.
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Entities.Folder", false, false, _itemSchrijf) { OokVerboden = _mapInhoud },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Entities.TV.Season", false, false, _itemSchrijf) { OokVerboden = _mapInhoud.Concat(new[] { "GetEpisodes", "GetChildren" }).ToArray() },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Entities.TV.Series", false, false, _itemSchrijf) { OokVerboden = _mapInhoud.Concat(new[] { "GetSeasonEpisodes" }).ToArray() },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Entities.UserView", false, false, _itemSchrijf) { OokVerboden = _mapInhoud.Concat(new[] { "GetChildren", "GetRecursiveChildren" }).ToArray() },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Playlists.Playlist", false, false, _itemSchrijf)
        {
            OokVerboden = _mapInhoud.Concat(new[] { "GetChildren", "GetRecursiveChildren", "GetPlaylistItems" }).ToArray()
        },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Playlists.IPlaylistManager", true, false, _lezen) { OokVerboden = new[] { "GetPlaylistsFolder" } },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Collections.ICollectionManager", true, false, _lezen) { OokVerboden = new[] { "GetCollectionsFolder" } },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Library.IUserManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Devices.IDeviceManager", true, false, _lezen),
        // Alle overige diensten van de plugin-ABI die in v12.4 zelf in jellyfin.db schrijven (gevonden op SaveChanges,
        // ExecuteDelete en ExecuteUpdate in de serverbron; ADR-0032, kop "Wat JL0001 bewaakt"): voorkeuren,
        // hoofdstukken, sporen, bijlagen, personen, keyframes, trickplay, gekoppelde items, het activiteitenlog,
        // API-sleutels en het terugzetten van een back-up. Nergens schrijven, ook niet met een uitzondering.
        // GetDisplayPreferences en GetItemDisplayPreferences maken de rij aan als die ontbreekt.
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.IDisplayPreferencesManager", true, false, "Get", "Find", "Query", "Is", "Has", "Can", "To", "List")
        {
            OokVerboden = new[] { "GetDisplayPreferences", "GetItemDisplayPreferences" }
        },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Persistence.IChapterRepository", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Chapters.IChapterManager", true, false, "Get", "Find", "Query", "Is", "Has", "Can", "To", "Supports"),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Persistence.IMediaStreamRepository", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Persistence.IMediaAttachmentRepository", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Persistence.IPeopleRepository", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Persistence.IKeyframeRepository", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.IO.IKeyframeManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Trickplay.ITrickplayManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Persistence.ILinkedChildrenService", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.IO.IExternalDataManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Model.Activity.IActivityManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Security.IAuthenticationManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "Jellyfin.Server.Implementations.SystemBackupService.IBackupService", true, false, "Get", "Find", "Query", "Is", "Has", "Can", "To", "Enumerate"),
        // Diensten die via een andere server-API de bibliotheek, metadata, gebruikers of instellingen wijzigen: een
        // servertaak of een verversing starten (ook de taak die kijkgegevens van "ontbrekende" items opruimt),
        // songteksten naast de media schrijven, kanaal- en gids-items aanmaken of wissen, opnames wissen,
        // tv-instellingen opslaan, een aanmelding goedkeuren, een wachtwoord wijzigen of een serverevent publiceren.
        // GetPlaybackMediaSources ververst met allowMediaProbe de metadata van het item; de Get-leden van
        // IChannelManager maken kanaalitems aan of wissen ze, en ILiveTvManager.GetRecordingsAsync en
        // GetRecordingFoldersAsync en IUserViewManager.GetLatestItems doen dat via IChannelManager.
        // Een servertaak kan ook via het taakobject zelf starten (ITaskManager.ScheduledTasks of
        // IApplicationHost.GetExports): IScheduledTask.ExecuteAsync, en IScheduledTaskWorker wijzigt de planning
        // (Triggers zetten, ReloadTriggerEvents).
        new TypeRegel(ServerSchrijf, "MediaBrowser.Model.Tasks.ITaskManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Model.Tasks.IScheduledTask", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Model.Tasks.IScheduledTaskWorker", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Library.IUserViewManager", true, false, _lezen) { OokVerboden = new[] { "GetLatestItems" } },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Library.ILibraryMonitor", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Providers.IMetadataService", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Library.IMediaSourceManager", true, false, _lezen) { OokVerboden = new[] { "GetPlaybackMediaSources" } },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Lyrics.ILyricManager", true, false, "Get", "Find", "Query", "Is", "Has", "Can", "To", "Search"),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Channels.IChannelManager", true, false, _lezen)
        {
            OokVerboden = new[] { "GetChannelsInternalAsync", "GetChannelsAsync", "GetLatestChannelItems", "GetLatestChannelItemsInternal", "GetChannelItems", "GetChannelItemsInternal" }
        },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.LiveTv.ILiveTvManager", true, false, _lezen)
        {
            OokVerboden = new[] { "GetRecordingsAsync", "GetRecordingFoldersAsync" }
        },
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.LiveTv.IGuideManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.LiveTv.IRecordingsManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.LiveTv.IListingsManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.LiveTv.ITunerHostManager", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.QuickConnect.IQuickConnect", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Authentication.IAuthenticationProvider", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Authentication.IPasswordResetProvider", true, false, _lezen),
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Events.IEventManager", true, false, _lezen),
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
