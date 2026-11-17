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

    /// <summary>
    /// Waar: ook de vaste namespaces (Core.Storage, Core.Secrets, Core.Werker) mogen dit niet. Voor de server-ABI die zelf
    /// een bestand schrijft, wist of verplaatst of een proces start (die loopt langs de padgrens van Core.Storage heen) en
    /// voor de omwegen (native code, reflectie, code laden).
    /// </summary>
    public bool Nergens { get; set; }

    /// <summary>Waar: een omweg langs de bouwgrens (native code, reflectie, code laden); eigen melding.</summary>
    public bool Omweg { get; set; }

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
    public static bool IsVoorvoegsel(string voorvoegsel, string lid) =>
        lid.StartsWith(voorvoegsel, StringComparison.Ordinal)
        && (lid.Length == voorvoegsel.Length || !char.IsLower(lid[voorvoegsel.Length]));
}

/// <summary>
/// Eén regel van de witte lijst van de bestandsnamespaces (ADR-0032, kop "Bestanden (JL0002)"): welke leden van een type
/// buiten de opslagnamespaces mogen, en of het type daar aangemaakt mag worden.
/// </summary>
internal sealed class BestandWit
{
    public BestandWit(string type, bool metAfgeleiden, Aanmaken aanmaak, params string[] leden)
    {
        Type = type;
        MetAfgeleiden = metAfgeleiden;
        Aanmaak = aanmaak;
        Leden = leden;
    }

    public enum Aanmaken
    {
        /// <summary>Aanmaken is JL0002.</summary>
        Nee,

        /// <summary>Elke constructor mag.</summary>
        Ja,

        /// <summary>Alleen een constructor zonder tekst (een pad) als parameter: <c>new StreamWriter(stroom)</c> wel, <c>new StreamWriter(pad)</c> niet.</summary>
        ZonderTekst,
    }

    public string Type { get; }

    /// <summary>Waar: de leden gelden ook voor een type dat ervan afleidt (bijvoorbeeld elke stroom).</summary>
    public bool MetAfgeleiden { get; }

    /// <summary>
    /// Of precies dit type aangemaakt mag worden; een type dat ervan afleidt (en zelf niet in een bestandsnamespace ligt)
    /// telt als dit type.
    /// </summary>
    public Aanmaken Aanmaak { get; }

    /// <summary>Toegestane leden: "*" is alle, anders voorvoegsels als heel woord (zoals bij <see cref="TypeRegel"/>).</summary>
    public IReadOnlyList<string> Leden { get; }

    /// <summary>Leden die ondanks "*" verboden blijven.</summary>
    public IReadOnlyList<string> Behalve { get; set; } = Array.Empty<string>();

    /// <summary>Waar: een eigenschap lezen mag (zetten niet).</summary>
    public bool EigenschappenLezen { get; set; }

    public bool StaatToe(string lid) =>
        !Behalve.Contains(lid) && Leden.Any(v => v == "*" || TypeRegel.IsVoorvoegsel(v, lid));
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

    /// <summary>
    /// Wat een metadata- of afbeeldingsleverancier van de server alleen bekijkt. "Get…" hoort er niet bij: GetMetadata,
    /// GetImages en GetImage halen op, schrijven de cache of een afbeelding (AudioDb, Omdb, AudioImageProvider) en FetchAsync
    /// wijzigt het item.
    /// </summary>
    private static readonly string[] _provider = { "Supports", "GetSupported", "Is", "Has", "Can", "To" };

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
        // via ILibraryManager. GetChildren en GetRecursiveChildren zijn ook op Folder zelf verboden: een variabele van
        // het basistype (Folder f = seizoen) kan bij het draaien een Season, UserView of Playlist zijn.
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Entities.Folder", false, false, _itemSchrijf)
        {
            OokVerboden = _mapInhoud.Concat(new[] { "GetChildren", "GetRecursiveChildren" }).ToArray()
        },
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
        // Een item van de server wijzigen via de extensiemethoden (SetImagePath, DeepCopy naar een bestaand item): net als
        // de Set-leden van BaseItem zelf (R-HARDE-EIS-13, gevonden met de padscan van herstelronde 6).
        new TypeRegel(ServerSchrijf, "MediaBrowser.Controller.Entities.BaseItemExtensions", true, false, _lezen),
        // Bestanden (System.IO): alleen de opslagnamespaces; verwijderen elders alleen in één met naam genoemde klasse.
        // Deze vier typen houden hun eigen leesvoorvoegsels (en de witte lijst per klasse); elk ander type uit de
        // bestandsnamespaces valt onder de regel op de namespace met de witte lijst hieronder (BestandWitteLijst).
        new TypeRegel(BestandSchrijf, "System.IO.File", true, true, "Exists", "Read", "OpenRead", "OpenText", "Get"),
        new TypeRegel(BestandSchrijf, "System.IO.Directory", true, true, "Exists", "Get", "Enumerate"),
        new TypeRegel(BestandSchrijf, "System.IO.FileSystemInfo", true, true, "OpenRead", "OpenText", "Get", "Enumerate", "Refresh", "ToString"),
        new TypeRegel(BestandSchrijf, "MediaBrowser.Model.IO.IFileSystem", false, true, "Delete", "Move", "Create", "Swap", "Set"),
        // Bestanden schrijven buiten System.IO (BCL): de schrijvende delen van System.Data, een download naar een bestand en
        // een JIT-profiel met een zelfgekozen naam. Buiten de opslagnamespaces JL0002, zonder uitzondering.
        new TypeRegel(BestandSchrijf, "System.Data.DataSet", false, false, "WriteXml"),
        new TypeRegel(BestandSchrijf, "System.Data.DataTable", false, false, "WriteXml"),
        new TypeRegel(BestandSchrijf, "System.Net.WebClient", false, false, "DownloadFile"),
        new TypeRegel(BestandSchrijf, "System.Runtime.ProfileOptimization", true, false),
        // De server-ABI die zelf een bestand schrijft, wist of verplaatst of een proces start (R-HARDE-EIS-13; ADR-0032,
        // kop "Bestanden (JL0002)"): nergens, ook niet in Core.Storage, want de server doet het langs de padgrens heen.
        new TypeRegel(BestandSchrijf, "MediaBrowser.Common.Plugins.IPluginManager", true, false, _lezen) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Common.Updates.IInstallationManager", true, false, "Get", "Find", "Query", "Is", "Has", "Can", "To", "Filter") { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Common.Configuration.IApplicationPaths", true, false, _lezen) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Model.Serialization.IXmlSerializer", true, false, "Deserialize") { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Model.IO.AsyncFile", true, false, "OpenRead") { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Model.IO.IShortcutHandler", true, false, "Resolve") { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.IO.FileSystemHelper", true, false, "Get", "Resolve") { Nergens = true },
        new TypeRegel(BestandSchrijf, "Jellyfin.Extensions.FileHelper", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.Providers.IDirectoryService", true, false, "Get", "Find", "Query", "Is", "Has", "Can", "To", "Invalidate") { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.Library.IMetadataSaver", true, false, _lezen) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.Providers.IMetadataProvider", true, false, _provider) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.Providers.IImageProvider", true, false, _provider) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.MediaEncoding.ITranscodeManager", true, false, _lezen) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.MediaEncoding.TranscodingJob", true, false, _lezen) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.MediaEncoding.TranscodingSegmentCleaner", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.MediaEncoding.IMediaEncoder", true, false, "Get", "Find", "Query", "Is", "Has", "Can", "To", "Supports", "Escape")
        {
            Nergens = true,
            OokVerboden = new[] { "GetMediaInfo" }
        },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.MediaEncoding.ISubtitleEncoder", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.MediaEncoding.IAttachmentExtractor", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.MediaEncoding.EncodingHelper", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.Drawing.IImageProcessor", true, false, "Get", "Find", "Query", "Is", "Has", "Can", "To", "Supports") { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.Drawing.IImageEncoder", true, false, "Get", "Find", "Query", "Is", "Has", "Can", "To", "Supports") { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.ClientEvent.IClientEventLogger", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "Jellyfin.MediaEncoding.Keyframes.FfProbe.FfProbeKeyframeExtractor", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "Jellyfin.MediaEncoding.Keyframes.FfTool.FfToolKeyframeExtractor", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.LiveTv.IListingsProvider", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.LiveTv.ITunerHost", true, false) { Nergens = true },
        new TypeRegel(BestandSchrijf, "MediaBrowser.Controller.Library.ILiveStream", true, false, _lezen) { Nergens = true },
        // Omwegen langs de bouwgrens (ADR-0032, kop "Dreigingsmodel"): reflectie die een lid aanroept of een type uit een
        // tekst haalt, code laden, een object van een willekeurig type aanmaken en native code. Nergens, zonder uitzondering.
        new TypeRegel(BestandSchrijf, "System.Reflection.MethodBase", false, false, "Invoke", "CreateDelegate") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Reflection.PropertyInfo", false, false, "SetValue", "GetValue") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Reflection.FieldInfo", false, false, "SetValue", "GetValue") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Reflection.EventInfo", false, false, "AddEventHandler", "RemoveEventHandler") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Type", false, false, "InvokeMember", "GetType") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Reflection.Assembly", false, false, "Load", "UnsafeLoadFrom", "ReflectionOnlyLoad", "CreateInstance", "GetType") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Runtime.Loader.AssemblyLoadContext", true, false) { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.AppDomain", false, false, "Load", "ExecuteAssembly", "CreateInstance") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Activator", true, false) { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "Microsoft.Extensions.DependencyInjection.ActivatorUtilities", true, false) { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Delegate", false, false, "DynamicInvoke", "CreateDelegate") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Linq.Expressions.LambdaExpression", false, false, "Compile") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Runtime.InteropServices.NativeLibrary", true, false) { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Runtime.InteropServices.Marshal", true, false) { Nergens = true, Omweg = true },
        new TypeRegel(ProcesStart, "System.Diagnostics.Process", false, false, "Start"),
        new TypeRegel(ProcesStart, "Microsoft.VisualBasic.Interaction", false, false, "Shell"));

    /// <summary>
    /// Typen waarvan het aanmaken al een schrijfactie of een processtart is. Hiervoor bestaat geen uitzondering per
    /// klasse: alleen de vaste namespaces mogen dit, en bij <c>Nergens</c> ook die niet. <c>AlleenMetPad</c>: alleen een
    /// constructor met een tekst (een pad) als eerste parameter. FileStream en StreamWriter vallen onder de regel op de
    /// bestandsnamespaces (zie <see cref="BestandWitteLijst"/>).
    /// </summary>
    public static readonly ImmutableArray<(string RegelId, string Type, bool AlleenMetPad, bool Nergens)> Aanmaak = ImmutableArray.Create(
        (BestandSchrijf, "System.Diagnostics.TextWriterTraceListener", true, false),
        (BestandSchrijf, "System.Resources.ResourceWriter", true, false),
        (BestandSchrijf, "MediaBrowser.Common.Plugins.LocalPlugin", false, true),
        (BestandSchrijf, "MediaBrowser.Controller.Streaming.ProgressiveFileStream", false, true),
        (BestandSchrijf, "MediaBrowser.Controller.MediaEncoding.TranscodingJob", false, true),
        (BestandSchrijf, "MediaBrowser.Controller.MediaEncoding.TranscodingSegmentCleaner", false, true),
        (ProcesStart, "System.Diagnostics.Process", false, false),
        (ProcesStart, "System.Diagnostics.ProcessStartInfo", false, false));

    /// <summary>
    /// Bestanden (JL0002, R-HARDE-EIS-13): buiten de opslagnamespaces is elk gebruik van een type uit deze namespaces
    /// (ook de subnamespaces, zoals System.IO.Compression, System.IO.MemoryMappedFiles, System.IO.Pipes en
    /// System.IO.IsolatedStorage) JL0002, behalve wat op <see cref="BestandWitteLijst"/> staat. Microsoft.VisualBasic.FileIO
    /// is de bestandslaag van Visual Basic (FileSystem.DeleteFile, WriteAllText).
    /// </summary>
    public static readonly ImmutableArray<string> BestandNamespaces = ImmutableArray.Create(
        "System.IO",
        "System.Formats.Tar",
        "Microsoft.VisualBasic.FileIO");

    /// <summary>Losse bestandstypen buiten die namespaces (de bestandsfuncties van Visual Basic: Kill, FileOpen, FileCopy).</summary>
    public static readonly ImmutableArray<string> BestandTypen = ImmutableArray.Create("Microsoft.VisualBasic.FileSystem");

    /// <summary>Namespaces die alleen code maken of laden (omweg): nergens, zonder uitzondering.</summary>
    public static readonly ImmutableArray<string> OmwegNamespaces = ImmutableArray.Create("System.Reflection.Emit");

    /// <summary>
    /// De kleine witte lijst van de bestandsnamespaces: pure padbewerking, lezen, en lezen of schrijven op een stroom of
    /// lezer/schrijver die de code al heeft (zo'n stroom naar een bestand krijgen is zelf JL0002: <c>File.Open…</c>,
    /// <c>new FileStream</c>, <c>new StreamWriter(pad)</c>, <c>AsyncFile.Create</c>). Elk ander lid is JL0002. Altijd
    /// toegestaan: de waarden van een enum (<c>FileMode.Create</c>) en een uitzondering (<c>new IOException</c>, ook vangen).
    /// File, Directory en FileInfo/DirectoryInfo houden hun leesvoorvoegsels uit <see cref="Typen"/>.
    /// </summary>
    public static readonly ImmutableArray<BestandWit> BestandWitteLijst = ImmutableArray.Create(
        // Pure padbewerking; GetTempFileName maakt een leeg bestand aan en hoort er dus niet bij.
        new BestandWit("System.IO.Path", false, BestandWit.Aanmaken.Nee, "*") { Behalve = new[] { "GetTempFileName" } },
        // Bestaande bestanden en mappen bekijken (de methoden bepaalt de regel in Typen): een eigenschap lezen en het object maken.
        new BestandWit("System.IO.FileSystemInfo", true, BestandWit.Aanmaken.Nee) { EigenschappenLezen = true },
        new BestandWit("System.IO.FileInfo", false, BestandWit.Aanmaken.Ja),
        new BestandWit("System.IO.DirectoryInfo", false, BestandWit.Aanmaken.Ja),
        // Lezen en schrijven op een stroom die de code al heeft; zelf maken alleen in het geheugen.
        new BestandWit("System.IO.Stream", true, BestandWit.Aanmaken.Nee, "*"),
        new BestandWit("System.IO.MemoryStream", false, BestandWit.Aanmaken.Ja, "*"),
        new BestandWit("System.IO.BufferedStream", false, BestandWit.Aanmaken.Ja, "*"),
        new BestandWit("System.IO.TextReader", true, BestandWit.Aanmaken.Nee, "*"),
        new BestandWit("System.IO.StreamReader", false, BestandWit.Aanmaken.Ja, "*"),
        new BestandWit("System.IO.StringReader", false, BestandWit.Aanmaken.Ja, "*"),
        new BestandWit("System.IO.TextWriter", true, BestandWit.Aanmaken.Nee, "*"),
        new BestandWit("System.IO.StringWriter", false, BestandWit.Aanmaken.Ja, "*"),
        new BestandWit("System.IO.StreamWriter", false, BestandWit.Aanmaken.ZonderTekst, "*"),
        new BestandWit("System.IO.BinaryReader", true, BestandWit.Aanmaken.Ja, "*"),
        new BestandWit("System.IO.BinaryWriter", true, BestandWit.Aanmaken.Ja, "*"));

    /// <summary>
    /// Het schrijvende deel van System.Xml en System.Xml.Linq: een lid met een van deze namen (als heel woord) op een type
    /// uit die namespaces, met een pad (tekst) of een stroom als parameter, en het aanmaken van een XmlWriter met een pad
    /// of stroom (<c>XmlWriter.Create</c>, <c>new XmlTextWriter(pad, …)</c>). JL0002 buiten de opslagnamespaces.
    /// </summary>
    public static readonly ImmutableArray<string> XmlSchrijfLeden = ImmutableArray.Create("Save", "WriteTo", "WriteContentTo", "Transform", "Serialize");

    public static readonly ImmutableArray<string> XmlNamespaces = ImmutableArray.Create("System.Xml");

    /// <summary>Waar als de typenaam bij de bestandsnamespaces hoort (op naam: de witte lijst van uitzonderingen kent geen symbolen).</summary>
    public static bool IsBestandTypenaam(string type) =>
        BestandTypen.Contains(type) || BestandNamespaces.Any(n => type.StartsWith(n + ".", StringComparison.Ordinal));

    /// <summary>Waar als <paramref name="ruimte"/> een van <paramref name="namespaces"/> is of eronder ligt.</summary>
    public static bool InNamespace(string ruimte, ImmutableArray<string> namespaces) =>
        namespaces.Any(n => ruimte == n || ruimte.StartsWith(n + ".", StringComparison.Ordinal));

    /// <summary>
    /// Databasetoegang (JL0002, R-HARDE-EIS-12): de enige namespace waar een databaseverbinding of -bron mag ontstaan of
    /// gebruikt worden. <c>JlDatabase</c> controleert daar het pad (de padgrens) en zet koppelen uit; buiten deze namespace
    /// mag code een verbinding die <c>JlDatabase.Met</c> geeft alleen doorgeven, niet zelf gebruiken.
    /// </summary>
    public static readonly ImmutableArray<string> DatabaseNamespaces = ImmutableArray.Create(PluginNamespace + ".Core.Storage");

    /// <summary>
    /// Typen die een databaseverbinding of een bron ervan zijn (ook elk type dat ervan afleidt of ze implementeert, zoals
    /// <c>SqliteConnection</c> en <c>SqliteFactory</c>).
    /// </summary>
    public static readonly ImmutableArray<string> DatabaseVerbindingTypen = ImmutableArray.Create(
        "System.Data.Common.DbConnection",
        "System.Data.IDbConnection",
        "System.Data.Common.DbDataSource",
        "System.Data.Common.DbProviderFactory",
        "System.Data.Common.DbProviderFactories");

    /// <summary>
    /// Assemblies die niets anders doen dan een database openen of bedienen: elk type eruit telt als databasetype
    /// (Microsoft.Data.Sqlite, de SQLite-laag SQLitePCLRaw met <c>raw.sqlite3_open</c>, en Entity Framework Core met de
    /// bouwers van een verbinding: <c>DbContextOptions</c>, <c>DbContextOptionsBuilder</c>, <c>RelationalOptionsExtension</c>,
    /// <c>DbContext</c> en <c>Database.GetDbConnection</c>). Een naam telt als hij gelijk is of erop volgt met een punt.
    /// </summary>
    public static readonly ImmutableArray<string> DatabaseAssemblies = ImmutableArray.Create(
        "Microsoft.Data.Sqlite",
        "SQLitePCLRaw",
        "Microsoft.EntityFrameworkCore");

    /// <summary>
    /// Typen van de serverdatabase die alleen precies zo (niet als afgeleid type) JL0003 zijn: de niet-generieke
    /// <c>DbContextOptions</c> staat in de container van de server (<c>AddPooledDbContextFactory&lt;JellyfinDbContext&gt;</c>)
    /// en draagt de verbindingstekst van jellyfin.db. Resolven of injecteren is JL0003.
    /// </summary>
    public static readonly ImmutableArray<string> ServerDatabaseTypenExact = ImmutableArray.Create("Microsoft.EntityFrameworkCore.DbContextOptions");

    /// <summary>Waar als <paramref name="assembly"/> een van de <see cref="DatabaseAssemblies"/> is.</summary>
    public static bool IsDatabaseAssembly(string? assembly) =>
        assembly is not null && DatabaseAssemblies.Any(a => assembly == a || assembly.StartsWith(a + ".", StringComparison.Ordinal));

    /// <summary>
    /// Waar als een typenaam uit de witte lijst bij de databasetoegang hoort (op naam: de witte lijst kent geen symbolen).
    /// Daarvoor bestaat nooit een uitzondering.
    /// </summary>
    public static bool IsDatabaseTypenaam(string type) =>
        DatabaseVerbindingTypen.Contains(type)
        || type.StartsWith("Microsoft.Data.Sqlite.", StringComparison.Ordinal)
        || type.StartsWith("SQLitePCL.", StringComparison.Ordinal)
        || type.StartsWith("Microsoft.EntityFrameworkCore.", StringComparison.Ordinal);

    /// <summary>
    /// De database van de server zelf: nergens, in geen enkele vorm. Elk gebruik van de typenaam is JL0003 (parameter,
    /// veld, <c>GetService&lt;T&gt;</c>, <c>typeof</c>, ook als typeargument zoals <c>IDbContextFactory&lt;JellyfinDbContext&gt;</c>
    /// en via <c>var</c>). Naast de context zelf: <c>IJellyfinDatabaseProvider</c> (een dienst in de container van de
    /// server; <c>DbContextFactory</c> geeft een context, <c>PurgeDatabase</c> en <c>RestoreBackupFast</c> wissen of
    /// overschrijven jellyfin.db; R-HARDE-EIS-10) en de twee typen die een context als argument gebruiken
    /// (<c>IEntityFrameworkCoreLockingBehavior</c>, <c>IItemQueryHelpers</c>).
    /// </summary>
    public static readonly ImmutableArray<string> ServerDatabaseTypen = ImmutableArray.Create(
        "Jellyfin.Database.Implementations.JellyfinDbContext",
        "Jellyfin.Database.Implementations.IJellyfinDatabaseProvider",
        "Jellyfin.Database.Implementations.Locking.IEntityFrameworkCoreLockingBehavior",
        "MediaBrowser.Controller.Persistence.IItemQueryHelpers");

    public static readonly ImmutableArray<string> ServerDatabaseNamen = ImmutableArray.Create("jellyfin.db", "library.db");
}
