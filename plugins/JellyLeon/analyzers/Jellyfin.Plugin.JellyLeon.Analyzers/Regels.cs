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

/// <summary>
/// Eén regel van de witte lijst van de server-ABI (ADR-0032, kop "Server-ABI: witte lijst"): één lezend lid van een
/// servertype in precies één klasse van de plugin (de buitenste klasse, met volledige naam). Een eigenschap of veld van
/// een servertype zetten staat nooit op deze lijst; alleen bij een aanmaak (lid ".ctor") mogen de genoemde eigenschappen
/// in de objectinitialisatie van precies dat nieuwe object.
/// </summary>
internal sealed class ServerWit
{
    public ServerWit(string type, string lid, string klasse, params string[] initialisatie)
    {
        Type = type;
        Lid = lid;
        Klasse = klasse;
        Initialisatie = initialisatie;
    }

    /// <summary>Metadatanaam van het servertype dat het lid declareert (bij een generiek type met `1).</summary>
    public string Type { get; }

    /// <summary>Naam van het lid (alle overloads); ".ctor" is aanmaken.</summary>
    public string Lid { get; }

    /// <summary>Volledige naam van de buitenste klasse van de plugin waarin het gebruik mag.</summary>
    public string Klasse { get; }

    /// <summary>Alleen bij ".ctor": eigenschappen die in de objectinitialisatie van het nieuwe object gezet mogen worden.</summary>
    public IReadOnlyList<string> Initialisatie { get; }
}

/// <summary>
/// Eén regel van de witte lijst van uitbreidingspunten (ADR-0032, kop "Server-ABI: witte lijst"): een servertype dat een
/// type van de plugin mag implementeren of ervan afleiden, alleen in precies deze namespace (niet eronder).
/// </summary>
internal sealed class UitbreidingWit
{
    public UitbreidingWit(string type, string ruimte, string? typeargument = null)
    {
        Type = type;
        Ruimte = ruimte;
        Typeargument = typeargument;
    }

    /// <summary>Metadatanaam van het servertype (bij een generiek type met `1).</summary>
    public string Type { get; }

    /// <summary>De namespace van het plugintype (exact).</summary>
    public string Ruimte { get; }

    /// <summary>Optioneel: het enige toegestane typeargument (metadatanaam), bijvoorbeeld bij IEventConsumer&lt;T&gt;.</summary>
    public string? Typeargument { get; }
}

/// <summary>
/// Eén regel van de witte lijst van de HTTP-laag (ADR-0032, kop "HTTP-laag en netwerk"): één lid van de HTTP-laag
/// (<see cref="Lid"/> is een naam) of één uitbreidingspunt van de HTTP-laag (<see cref="Lid"/> is <see cref="Implementeert"/>)
/// in precies één klasse van de plugin (bij een lid de buitenste klasse, bij een uitbreidingspunt het type zelf, met
/// volledige naam). Alleen voor de eigen pluginpaden of de eigen acties; de motivatie staat in ADR-0032.
/// </summary>
internal sealed class HttpWit
{
    /// <summary>Waarde van <see cref="Lid"/> voor een uitbreidingspunt: het type implementeert of erft <see cref="Type"/>.</summary>
    public const string Implementeert = ":";

    public HttpWit(string type, string lid, string klasse)
    {
        Type = type;
        Lid = lid;
        Klasse = klasse;
    }

    /// <summary>Metadatanaam van het type dat het lid declareert, of van het uitbreidingspunt.</summary>
    public string Type { get; }

    /// <summary>Naam van het lid (alle overloads), of <see cref="Implementeert"/>.</summary>
    public string Lid { get; }

    /// <summary>Volledige naam van de klasse van de plugin.</summary>
    public string Klasse { get; }
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
        new TypeRegel(BestandSchrijf, "System.Runtime.InteropServices.NativeLibrary", true, false) { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Runtime.InteropServices.Marshal", true, false) { Nergens = true, Omweg = true },
        // Herstelronde 8 (herreview 7, grenzen 2 en 3): reflectie in een Microsoft- of BCL-bibliotheek die een eigenschap van
        // een willekeurig object zet (ConfigurationBinder.Bind/Get, PropertyDescriptor.SetValue via TypeDescriptor), een
        // implementatie van een willekeurige interface maakt zonder eigen klasse (DispatchProxy.Create) en het beheerde
        // equivalent van unsafe (Unsafe.As op een object). System.Linq.Expressions staat bij OmwegNamespaces.
        new TypeRegel(BestandSchrijf, "Microsoft.Extensions.Configuration.ConfigurationBinder", false, false) { Nergens = true, Omweg = true, OokVerboden = new[] { "Bind", "Get" } },
        new TypeRegel(BestandSchrijf, "System.ComponentModel.TypeDescriptor", true, false) { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.ComponentModel.PropertyDescriptor", false, false, "SetValue", "GetValue", "ResetValue") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.ComponentModel.EventDescriptor", false, false, "AddEventHandler", "RemoveEventHandler") { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Reflection.DispatchProxy", true, false) { Nergens = true, Omweg = true },
        new TypeRegel(BestandSchrijf, "System.Runtime.CompilerServices.Unsafe", true, false) { Nergens = true, Omweg = true },
        // Modelbinding op een bestaand object (zoals ConfigurationBinder.Bind): de waarden uit een verzoek in een levend object zetten.
        new TypeRegel(BestandSchrijf, "Microsoft.AspNetCore.Mvc.ControllerBase", false, false) { Nergens = true, Omweg = true, OokVerboden = new[] { "TryUpdateModelAsync" } },
        new TypeRegel(BestandSchrijf, "Microsoft.AspNetCore.Mvc.ModelBinding.ModelBindingHelper", true, false) { Nergens = true, Omweg = true },
        new TypeRegel(ProcesStart, "System.Diagnostics.Process", false, false, "Start"),
        new TypeRegel(ProcesStart, "Microsoft.VisualBasic.Interaction", false, false, "Shell"));

    /// <summary>
    /// Typen waarvan het aanmaken al een schrijfactie of een processtart is. Hiervoor bestaat geen uitzondering per
    /// klasse: alleen de vaste namespaces mogen dit, en bij <c>Nergens</c> ook die niet. <c>AlleenMetPad</c>: alleen een
    /// constructor met een tekst (een pad) als eerste parameter. FileStream en StreamWriter vallen onder de regel op de
    /// bestandsnamespaces (zie <see cref="BestandWitteLijst"/>).
    /// </summary>
    public static readonly ImmutableArray<(string RegelId, string Type, bool AlleenMetPad, bool Nergens)> Aanmaak = ImmutableArray.Create(
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

    /// <summary>
    /// Namespaces die alleen code maken of laden (omweg): nergens, zonder uitzondering. System.Linq.Expressions (sinds
    /// herstelronde 8): een boom met een aanroep, aanmaak of toewijzing opbouwen en compileren of laten uitvoeren
    /// (<c>Expression.Call</c>, <c>Compile</c>, een <c>IQueryable</c>-provider) roept een lid aan buiten de analyzer om.
    /// Een lambda die de compiler naar een expressieboom omzet, ziet de analyzer gewoon (de leden in de lambda tellen).
    /// </summary>
    public static readonly ImmutableArray<string> OmwegNamespaces = ImmutableArray.Create("System.Reflection.Emit", "System.Linq.Expressions");

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

    /// <summary>
    /// BCL-typen die buiten de opslagnamespaces helemaal JL0002 zijn: elk lid (ook lezen), elk event en het aanmaken, ook van
    /// een type dat ervan afleidt (R-HARDE-EIS-15, S-G1-17 herstelronde 7). <c>WebClient</c> en <c>WebRequest</c> (met
    /// <c>FileWebRequest</c>) schrijven met een file:-adres in elk bestand (UploadData, OpenWrite, PUT met GetRequestStream).
    /// De trace-laag schrijft via een listener in een zelfgekozen bestand (<c>DefaultTraceListener.LogFileName</c>):
    /// listeners aanmaken of instellen, de lijsten met listeners en het schrijven via Trace, TraceSource en Debug mogen
    /// alleen in de opslaglaag. Geen uitzondering per klasse.
    /// </summary>
    public static readonly ImmutableArray<string> BestandVolledigTypen = ImmutableArray.Create(
        "System.Net.WebClient",
        "System.Net.WebRequest",
        "System.Diagnostics.TraceListener",
        "System.Diagnostics.TraceListenerCollection",
        "System.Diagnostics.Trace",
        "System.Diagnostics.TraceSource",
        "System.Diagnostics.Debug");

    /// <summary>
    /// De server-ABI (R-HARDE-EIS-14/-16, S-G1-17 herstelronde 7): elk type uit deze namespaces of uit een assembly met zo'n
    /// naam, behalve de eigen plugin (<see cref="PluginNamespace"/>). Elk gebruik van een lid ervan (aanroepen, als
    /// methodegroep nemen, een eigenschap of veld lezen of zetten, een event, aanmaken, een operator) is JL0001, behalve
    /// wat op <see cref="ServerAbiWitteLijst"/> staat; een implementatie of afleiding is JL0001, behalve wat op
    /// <see cref="UitbreidingWitteLijst"/> staat. Een constante (ook een enumwaarde) lezen mag altijd: de compiler zet de
    /// waarde in de plugin, er draait geen servercode.
    /// </summary>
    public static readonly ImmutableArray<string> ServerAbiNamespaces = ImmutableArray.Create("MediaBrowser", "Jellyfin", "Emby");

    /// <summary>
    /// De witte lijst van de server-ABI: alleen lezende leden die de plugin op 2026-11-17 echt gebruikt (vastgesteld met de
    /// bouw van de plugin zonder deze lijst), elk in precies één klasse. De motivatie per lid staat in ADR-0032, kop
    /// "Server-ABI: witte lijst"; een test eist dat elk lid daar genoemd wordt. Eén uitzondering op "alleen lezen", met
    /// reden in de ADR: <c>BasePlugin&lt;T&gt;.SaveConfiguration</c> in <c>PluginModuleSwitches</c> (de officiële route voor de
    /// eigen schakelaars; het pad ligt vast, zie <see cref="PluginConfigLeden"/>).
    /// </summary>
    public static readonly ImmutableArray<ServerWit> ServerAbiWitteLijst = ImmutableArray.Create(
        new ServerWit("MediaBrowser.Controller.Library.SimilarItemsQuery", "User", PluginNamespace + ".Modules.Recommendations.SimilarProvider"),
        new ServerWit("MediaBrowser.Controller.Library.SimilarItemsQuery", "Limit", PluginNamespace + ".Modules.Recommendations.SimilarProvider"),
        new ServerWit("MediaBrowser.Controller.Library.SimilarItemsQuery", "DtoOptions", PluginNamespace + ".Modules.Recommendations.SimilarProvider"),
        new ServerWit("MediaBrowser.Controller.Library.SimilarItemsQuery", "ExcludeItemIds", PluginNamespace + ".Modules.Recommendations.SimilarProvider"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "Genres", PluginNamespace + ".Modules.Recommendations.SimilarProvider"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "Id", PluginNamespace + ".Modules.Recommendations.SimilarProvider"),
        new ServerWit("MediaBrowser.Controller.Dto.DtoOptions", ".ctor", PluginNamespace + ".Modules.Recommendations.SimilarProvider"),
        new ServerWit("MediaBrowser.Controller.Entities.InternalItemsQuery", ".ctor", PluginNamespace + ".Modules.Recommendations.SimilarProvider", "IncludeItemTypes", "Genres", "ExcludeItemIds", "IsPlayed", "Limit", "DtoOptions", "OrderBy", "EnableTotalRecordCount"),
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "GetItemList", PluginNamespace + ".PluginServiceRegistrator"),
        // F6-S1: alleen deze serverleden in hun benoemde adapter.
        new ServerWit("MediaBrowser.Common.Extensions.BaseExtensions", "GetMD5", PluginNamespace + ".Modules.Segments.SegmentProvider"),
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "GetCollectionFolders", PluginNamespace + ".Modules.Segments.SegmentProvider"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "Id", PluginNamespace + ".Modules.Segments.SegmentProvider"),
        new ServerWit("MediaBrowser.Model.MediaSegmentGenerationRequest", "ItemId", PluginNamespace + ".Modules.Segments.SegmentProvider"),
        new ServerWit("MediaBrowser.Model.MediaSegments.MediaSegmentDto", ".ctor", PluginNamespace + ".Modules.Segments.SegmentProvider", "Id", "ItemId", "Type", "StartTicks", "EndTicks"),
        new ServerWit("MediaBrowser.Controller.MediaSegments.IMediaSegmentManager", "GetSupportedProviders", PluginNamespace + ".Modules.Segments.SegmentPublicatie"),
        new ServerWit("MediaBrowser.Controller.MediaSegments.IMediaSegmentManager", "GetSegmentsAsync", PluginNamespace + ".Modules.Segments.SegmentPublicatie"),
        new ServerWit("MediaBrowser.Model.Configuration.LibraryOptions", ".ctor", PluginNamespace + ".Modules.Segments.SegmentPublicatie", "DisabledMediaSegmentProviders"),
        new ServerWit("MediaBrowser.Model.MediaSegments.MediaSegmentDto", "Type", PluginNamespace + ".Modules.Segments.SegmentPublicatie"),
        new ServerWit("MediaBrowser.Model.MediaSegments.MediaSegmentDto", "StartTicks", PluginNamespace + ".Modules.Segments.SegmentPublicatie"),
        new ServerWit("MediaBrowser.Model.MediaSegments.MediaSegmentDto", "EndTicks", PluginNamespace + ".Modules.Segments.SegmentPublicatie"),
        new ServerWit("MediaBrowser.Model.MediaSegments.MediaSegmentDto", "Id", PluginNamespace + ".Modules.Segments.SegmentPublicatie"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "Id", PluginNamespace + ".Modules.Segments.SegmentPublicatie"),
        new ServerWit("MediaBrowser.Controller.Library.IUserManager", "GetUserById", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Entities.TV.Episode", "SeriesId", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "GetItemById", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "GetCollectionFolders", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "GetVirtualFolders", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "GetItemList", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "ItemAdded", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "ItemUpdated", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "ItemRemoved", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "Id", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "RunTimeTicks", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "ParentIndexNumber", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "IndexNumber", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "DateModified", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Entities.BaseItem", "ProviderIds", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Model.Entities.VirtualFolderInfo", "ItemId", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Model.Entities.VirtualFolderInfo", "Locations", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.Entities.InternalItemsQuery", ".ctor", PluginNamespace + ".Modules.Segments.SegmentBibliotheek", "ParentId", "Recursive", "MediaTypes", "StartIndex", "Limit"),
        new ServerWit("MediaBrowser.Controller.Persistence.IChapterRepository", "GetChapters", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Model.Entities.ChapterInfo", "StartPositionTicks", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Model.Entities.ChapterInfo", "Name", PluginNamespace + ".Modules.Segments.SegmentBibliotheek"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "NewGroup", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "JoinGroup", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "LeaveGroup", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "GetGroup", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "ListGroups", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "HandleRequest", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "IsUserActive", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.Session.ISessionManager", "Sessions", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "Id", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "UserId", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "UserName", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Model.SyncPlay.GroupInfoDto", "GroupId", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Model.SyncPlay.GroupInfoDto", "Participants", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.Requests.JoinGroupRequest", "GroupId", PluginNamespace + ".Modules.WatchTogether.WatchDecorator"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "GetGroup", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "ListGroups", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", "IsUserActive", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Controller.Session.ISessionManager", "Sessions", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", ".ctor", PluginNamespace + ".Modules.WatchTogether.WatchController", "UserId", "UserName"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "UserId", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "UserName", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Controller.SyncPlay.Requests.ListGroupsRequest", ".ctor", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Model.SyncPlay.GroupInfoDto", "GroupId", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Model.SyncPlay.GroupInfoDto", "GroupName", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Model.SyncPlay.GroupInfoDto", "Participants", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Model.SyncPlay.GroupInfoDto", "State", PluginNamespace + ".Modules.WatchTogether.WatchController"),
        new ServerWit("MediaBrowser.Controller.Library.IUserManager", "GetUsers", PluginNamespace + ".Modules.WatchTogether.WatchBewaking"),
        new ServerWit("MediaBrowser.Controller.Session.ISessionManager", "SessionEnded", PluginNamespace + ".Modules.WatchTogether.WatchBewaking"),
        new ServerWit("MediaBrowser.Controller.Session.SessionEventArgs", "SessionInfo", PluginNamespace + ".Modules.WatchTogether.WatchBewaking"),
        new ServerWit("Jellyfin.Database.Implementations.Entities.User", "Username", PluginNamespace + ".Core.Http.JellyfinSessionAuthenticator"),
        new ServerWit("Jellyfin.Database.Implementations.Entities.User", "SyncPlayAccess", PluginNamespace + ".Core.Http.JellyfinSessionAuthenticator"),
        // De pluginklasse: de basisconstructor en de configuratiepagina (een nieuw object, alleen in zijn initialisatie gevuld).
        new ServerWit("MediaBrowser.Common.Plugins.BasePlugin`1", ".ctor", PluginNamespace + ".Plugin"),
        new ServerWit("MediaBrowser.Model.Plugins.PluginPageInfo", ".ctor", PluginNamespace + ".Plugin", "Name", "DisplayName", "EmbeddedResourcePath"),
        // De eigen schrijfmappen afleiden uit de paden van de server.
        new ServerWit("MediaBrowser.Common.Configuration.IApplicationPaths", "DataPath", PluginNamespace + ".PluginServiceRegistrator"),
        new ServerWit("MediaBrowser.Common.Configuration.IApplicationPaths", "CachePath", PluginNamespace + ".PluginServiceRegistrator"),
        // Versie en naam van de server tonen (B03-001).
        new ServerWit("MediaBrowser.Common.IApplicationHost", "ApplicationVersionString", PluginNamespace + ".Api.JellyLeonVersionController"),
        new ServerWit("MediaBrowser.Common.IApplicationHost", "Name", PluginNamespace + ".Api.JellyLeonVersionController"),
        // De mediamappen van de bibliotheek (alleen-lezencontrole van de mount).
        new ServerWit("MediaBrowser.Controller.Library.ILibraryManager", "GetVirtualFolders", PluginNamespace + ".Core.BibliotheekMappen"),
        new ServerWit("MediaBrowser.Model.Entities.VirtualFolderInfo", "Locations", PluginNamespace + ".Core.BibliotheekMappen"),
        // De sessiecontrole van de pluginroutes.
        new ServerWit("MediaBrowser.Controller.Net.IAuthService", "Authenticate", PluginNamespace + ".Core.Http.JellyfinSessionAuthenticator"),
        new ServerWit("MediaBrowser.Controller.Net.AuthorizationInfo", "IsApiKey", PluginNamespace + ".Core.Http.JellyfinSessionAuthenticator"),
        new ServerWit("MediaBrowser.Controller.Net.AuthorizationInfo", "IsAuthenticated", PluginNamespace + ".Core.Http.JellyfinSessionAuthenticator"),
        new ServerWit("MediaBrowser.Controller.Net.AuthorizationInfo", "User", PluginNamespace + ".Core.Http.JellyfinSessionAuthenticator"),
        new ServerWit("Jellyfin.Database.Implementations.Entities.User", "Id", PluginNamespace + ".Core.Http.JellyfinSessionAuthenticator"),
        new ServerWit("Jellyfin.Data.UserEntityExtensions", "HasPermission", PluginNamespace + ".Core.Http.JellyfinSessionAuthenticator"),
        // Kind-signalen van een gebruiker (alleen tellen en kijken of er een grens is).
        new ServerWit("Jellyfin.Database.Implementations.Entities.User", "MaxParentalRatingScore", PluginNamespace + ".Core.Privacy.KidPolicy"),
        new ServerWit("Jellyfin.Database.Implementations.Entities.User", "Id", PluginNamespace + ".Core.Privacy.KidPolicy"),
        new ServerWit("MediaBrowser.Controller.Library.IUserManager", "GetUserById", PluginNamespace + ".Core.Privacy.KidPolicy"),
        new ServerWit("Jellyfin.Database.Implementations.Entities.User", "AccessSchedules", PluginNamespace + ".Core.Privacy.KidPolicy"),
        new ServerWit("Jellyfin.Data.UserEntityExtensions", "GetPreference", PluginNamespace + ".Core.Privacy.KidPolicy"),
        // Een verwijderde gebruiker: alleen het ID, om de eigen gegevens te wissen.
        new ServerWit("Jellyfin.Data.Events.GenericEventArgs`1", "Argument", PluginNamespace + ".Core.Privacy.UserDeletedConsumer"),
        new ServerWit("Jellyfin.Database.Implementations.Entities.User", "Id", PluginNamespace + ".Core.Privacy.UserDeletedConsumer"),
        // De eigen moduleschakelaars (de officiële route; het pad ligt vast, zie PluginConfigLeden). De enige schrijvende regel.
        new ServerWit("MediaBrowser.Common.Plugins.BasePlugin`1", "Configuration", PluginNamespace + ".Core.Modules.PluginModuleSwitches"),
        new ServerWit("MediaBrowser.Common.Plugins.BasePlugin`1", "SaveConfiguration", PluginNamespace + ".Core.Modules.PluginModuleSwitches"),
        // De planner telt de kijksessies (pauze bij afspelen).
        new ServerWit("MediaBrowser.Controller.Session.ISessionManager", "PlaybackStart", PluginNamespace + ".Core.Planner.ServerSessies"),
        new ServerWit("MediaBrowser.Controller.Session.ISessionManager", "PlaybackStopped", PluginNamespace + ".Core.Planner.ServerSessies"),
        new ServerWit("MediaBrowser.Controller.Session.ISessionManager", "Sessions", PluginNamespace + ".Core.Planner.ServerSessies"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "NowPlayingItem", PluginNamespace + ".Core.Planner.ServerSessies"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "TranscodingInfo", PluginNamespace + ".Core.Planner.ServerSessies"),
        new ServerWit("MediaBrowser.Model.Session.TranscodingInfo", "IsVideoDirect", PluginNamespace + ".Core.Planner.ServerSessies"),
        new ServerWit("MediaBrowser.Model.Session.TranscodingInfo", "HardwareAccelerationType", PluginNamespace + ".Core.Planner.ServerSessies"),
        // Module Devices: welke apparaten hoe afspelen (eigen tabel, geen kijkgegevens van de server).
        new ServerWit("MediaBrowser.Controller.Session.ISessionManager", "PlaybackStart", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Controller.Session.ISessionManager", "PlaybackStopped", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Controller.Library.PlaybackProgressEventArgs", "Users", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Controller.Library.PlaybackProgressEventArgs", "Session", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Controller.Library.PlaybackProgressEventArgs", "DeviceId", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Controller.Library.PlaybackProgressEventArgs", "MediaSourceId", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Controller.Library.PlaybackProgressEventArgs", "PlaySessionId", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "Id", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "PlayState", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Controller.Session.SessionInfo", "TranscodingInfo", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Model.Session.TranscodingInfo", "IsVideoDirect", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Model.Session.TranscodingInfo", "HardwareAccelerationType", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("MediaBrowser.Model.Session.PlayerStateInfo", "PlayMethod", PluginNamespace + ".Modules.Devices.DevicesListener"),
        new ServerWit("Jellyfin.Database.Implementations.Entities.User", "Id", PluginNamespace + ".Modules.Devices.DevicesListener"));

    /// <summary>
    /// De witte lijst van uitbreidingspunten: welke servertypen een type van de plugin mag implementeren of ervan afleiden,
    /// per namespace (exact). De server zoekt zulke typen zelf in de pluginassembly (GetExports) of krijgt ze via de
    /// registratie, en roept ze aan zonder dat plugincode iets aanroept (bijvoorbeeld een IResolverIgnoreRule die de
    /// bibliotheekscan items laat wissen). Elke andere implementatie of afleiding is JL0001. Later bewust uit te breiden,
    /// elk met een eigen ADR: IScheduledTask (planner) en IMediaSegmentProvider (alleen in Modules.Segments, B03-07x).
    /// Microsoft-typen (IHostedService, IStartupFilter) zijn geen server-ABI en vallen niet onder deze regel.
    /// </summary>
    public static readonly ImmutableArray<UitbreidingWit> UitbreidingWitteLijst = ImmutableArray.Create(
        new UitbreidingWit("MediaBrowser.Controller.Library.ILocalSimilarItemsProvider`1", PluginNamespace + ".Modules.Recommendations", "MediaBrowser.Controller.Entities.Movies.Movie"),
        new UitbreidingWit("MediaBrowser.Controller.Library.ILocalSimilarItemsProvider`1", PluginNamespace + ".Modules.Recommendations", "MediaBrowser.Controller.Entities.TV.Series"),
        new UitbreidingWit("MediaBrowser.Controller.MediaSegments.IMediaSegmentProvider", PluginNamespace + ".Modules.Segments"),
        new UitbreidingWit("MediaBrowser.Controller.SyncPlay.ISyncPlayManager", PluginNamespace + ".Modules.WatchTogether"),
        new UitbreidingWit("MediaBrowser.Common.Plugins.BasePlugin`1", PluginNamespace),
        new UitbreidingWit("MediaBrowser.Model.Plugins.IHasWebPages", PluginNamespace),
        new UitbreidingWit("MediaBrowser.Controller.Plugins.IPluginServiceRegistrator", PluginNamespace),
        new UitbreidingWit("MediaBrowser.Model.Plugins.BasePluginConfiguration", PluginNamespace + ".Configuration"),
        new UitbreidingWit("MediaBrowser.Controller.Events.IEventConsumer`1", PluginNamespace + ".Core.Privacy", "Jellyfin.Data.Events.Users.UserDeletedEventArgs"));

    /// <summary>
    /// De leden van <c>BasePlugin&lt;T&gt;</c> die bepalen waar de server de pluginconfiguratie schrijft
    /// (R-HARDE-EIS-14a): <c>ConfigurationFilePath = Path.Combine(PluginConfigurationsPath, ConfigurationFileName)</c>, en
    /// al <c>Configuration</c> lezen laat de server bij een leesfout <c>SaveConfiguration</c> doen. Een override (of een
    /// expliciete implementatie van het interfacelid) is JL0002, nergens.
    /// </summary>
    public static readonly ImmutableArray<string> PluginConfigLeden = ImmutableArray.Create("ConfigurationFileName", "SaveConfiguration", "UpdateConfiguration", "Configuration");

    /// <summary>
    /// De HTTP-laag van de server (R-HARDE-EIS-17, S-G1-17 herstelronde 8): uitbreidingspunten waarmee plugincode een
    /// verzoek aan de server kan omzetten, de gebruiker kan verwisselen of de argumenten van een serveractie kan wijzigen. Een
    /// type van de plugin dat een van deze typen (of een type uit <see cref="HttpUitbreidingNamespaces"/>) implementeert of
    /// ervan afleidt, is JL0001, behalve wat op <see cref="HttpWitteLijst"/> staat.
    /// </summary>
    public static readonly ImmutableArray<string> HttpUitbreidingTypen = ImmutableArray.Create(
        "Microsoft.AspNetCore.Hosting.IStartupFilter",
        "Microsoft.AspNetCore.Hosting.IHostingStartup",
        "Microsoft.AspNetCore.Http.IMiddleware",
        "Microsoft.AspNetCore.Http.IMiddlewareFactory",
        "Microsoft.AspNetCore.Http.IHttpContextFactory",
        "Microsoft.AspNetCore.Http.IHttpContextAccessor",
        "Microsoft.AspNetCore.Http.IEndpointFilter",
        "Microsoft.AspNetCore.Http.Endpoint");

    /// <summary>
    /// Namespaces van de HTTP-laag waarvan elk type een uitbreidingspunt is: authenticatie (ook <c>IClaimsTransformation</c>),
    /// autorisatie (<c>IAuthorizationHandler</c>, <c>IAuthorizationPolicyProvider</c>), MVC-filters, conventies, modelbinding
    /// (een waardebron of binder voor de argumenten van een serveractie), formatters, routering en de features van een verzoek.
    /// </summary>
    public static readonly ImmutableArray<string> HttpUitbreidingNamespaces = ImmutableArray.Create(
        "Microsoft.AspNetCore.Authentication",
        "Microsoft.AspNetCore.Authorization",
        "Microsoft.AspNetCore.Mvc.Filters",
        "Microsoft.AspNetCore.Mvc.ApplicationModels",
        "Microsoft.AspNetCore.Mvc.ApplicationParts",
        "Microsoft.AspNetCore.Mvc.ModelBinding",
        "Microsoft.AspNetCore.Mvc.Formatters",
        "Microsoft.AspNetCore.Mvc.Routing",
        "Microsoft.AspNetCore.Mvc.Abstractions",
        "Microsoft.AspNetCore.Mvc.Infrastructure",
        "Microsoft.AspNetCore.Mvc.Controllers",
        "Microsoft.AspNetCore.Routing",
        "Microsoft.AspNetCore.Http.Features",
        "Microsoft.AspNetCore.Rewrite");

    /// <summary>
    /// De pijplijn van de server opbouwen: elk lid van deze typen en elke extensiemethode die erop werkt (<c>Use</c>,
    /// <c>UseMiddleware</c>, <c>Map</c>, <c>MapWhen</c>, <c>UseWhen</c>, <c>Run</c>, <c>UseRouting</c>, <c>MapGet</c>, …) is
    /// JL0001, behalve wat op <see cref="HttpWitteLijst"/> staat.
    /// </summary>
    public static readonly ImmutableArray<string> HttpPijplijnTypen = ImmutableArray.Create(
        "Microsoft.AspNetCore.Builder.IApplicationBuilder",
        "Microsoft.AspNetCore.Routing.IEndpointRouteBuilder");

    /// <summary>
    /// De instellingen van de HTTP-laag die voor alle routes van de server gelden: elk lid is JL0001 (een filter, conventie,
    /// waardebron, binder of formatter toevoegen; een policy of schema toevoegen, vervangen of als standaard zetten; de
    /// onderdelen met controllers wijzigen). Plugincode komt hier via <c>Configure&lt;T&gt;</c>, <c>AddMvc</c>,
    /// <c>AddAuthorization</c> of <c>AddAuthentication</c>; het lid telt, en sinds herstelronde 9 ook <c>Configure&lt;T&gt;</c>
    /// met een optietype van de host als typeargument (zie <see cref="HostOptieNamespaces"/>).
    /// </summary>
    public static readonly ImmutableArray<string> HttpOptieTypen = ImmutableArray.Create(
        "Microsoft.AspNetCore.Mvc.MvcOptions",
        "Microsoft.AspNetCore.Mvc.ApplicationParts.ApplicationPartManager",
        "Microsoft.AspNetCore.Authorization.AuthorizationOptions",
        "Microsoft.AspNetCore.Authorization.AuthorizationBuilder",
        "Microsoft.AspNetCore.Authentication.AuthenticationOptions",
        "Microsoft.AspNetCore.Authentication.AuthenticationBuilder");

    /// <summary>
    /// Namespaces van de HTTP-laag waarvan elk lid JL0001 is (lezen ook): authenticatie, autorisatie, routering (met
    /// <c>RouteValueDictionary</c>, de routewaarden van een verzoek, en de endpoints van de server), de features van een
    /// verzoek (<c>IHttpRequestFeature.Path</c> zetten zou langs <c>HttpRequest</c> heen gaan), herschrijfregels, en de
    /// acties van MVC zelf (<c>IActionDescriptorCollectionProvider</c> en <c>IActionInvokerFactory</c> voeren een actie van de
    /// server uit in het proces, langs authenticatie en autorisatie heen).
    /// </summary>
    public static readonly ImmutableArray<string> HttpLedenNamespaces = ImmutableArray.Create(
        "Microsoft.AspNetCore.Authentication",
        "Microsoft.AspNetCore.Authorization",
        "Microsoft.AspNetCore.Routing",
        "Microsoft.AspNetCore.Http.Features",
        "Microsoft.AspNetCore.Rewrite",
        "Microsoft.AspNetCore.Mvc.ApplicationModels",
        "Microsoft.AspNetCore.Mvc.ApplicationParts",
        "Microsoft.AspNetCore.Mvc.Infrastructure",
        "Microsoft.AspNetCore.Mvc.Abstractions",
        "Microsoft.AspNetCore.Mvc.Controllers");

    /// <summary>
    /// Losse leden van de HTTP-laag die JL0001 zijn (type, lid): de argumenten van een actie (ook lezen: het is een
    /// gewone, wijzigbare lijst), een endpoint van de server rechtstreeks uitvoeren (langs authenticatie en autorisatie
    /// heen), het endpoint van een verzoek zetten, de getypeerde verzoekkoppen (met setters) en de claims of identiteiten van
    /// een gebruiker wijzigen.
    /// </summary>
    public static readonly ImmutableArray<(string Type, string Lid)> HttpVerbodenLeden = ImmutableArray.Create(
        ("Microsoft.AspNetCore.Mvc.Filters.ActionExecutingContext", "ActionArguments"),
        ("Microsoft.AspNetCore.Http.Endpoint", "RequestDelegate"),
        ("Microsoft.AspNetCore.Http.EndpointHttpContextExtensions", "SetEndpoint"),
        ("Microsoft.AspNetCore.Http.HeaderDictionaryTypeExtensions", "GetTypedHeaders"),
        ("System.Security.Claims.ClaimsPrincipal", "AddIdentity"),
        ("System.Security.Claims.ClaimsPrincipal", "AddIdentities"),
        ("System.Security.Claims.ClaimsIdentity", "AddClaim"),
        ("System.Security.Claims.ClaimsIdentity", "AddClaims"),
        ("System.Security.Claims.ClaimsIdentity", "RemoveClaim"),
        ("System.Security.Claims.ClaimsIdentity", "TryRemoveClaim"));

    /// <summary>
    /// Typen waarvan het zetten van een eigenschap JL0001 is: het verzoek (<c>Path</c>, <c>PathBase</c>, <c>Method</c>,
    /// <c>QueryString</c>, <c>Query</c>, <c>Body</c>, <c>RouteValues</c>, …), de context (<c>User</c>,
    /// <c>RequestServices</c>, <c>Items</c>, …) en de toegang tot de context van het lopende verzoek.
    /// </summary>
    public static readonly ImmutableArray<string> HttpZetTypen = ImmutableArray.Create(
        "Microsoft.AspNetCore.Http.HttpRequest",
        "Microsoft.AspNetCore.Http.HttpContext",
        "Microsoft.AspNetCore.Http.IHttpContextAccessor");

    /// <summary>
    /// De witte lijst van de HTTP-laag, per klasse: alleen voor de eigen pluginpaden of de eigen acties. De motivatie staat in
    /// ADR-0032 (kop "HTTP-laag en netwerk"); een test eist dat elke regel daar genoemd wordt.
    /// </summary>
    public static readonly ImmutableArray<HttpWit> HttpWitteLijst = ImmutableArray.Create(
        // De spike van ADR-0033: een laag vóór routing en authenticatie die alleen /media/v1 en /connector/v1 boven 1 MiB weigert.
        new HttpWit("Microsoft.AspNetCore.Hosting.IStartupFilter", HttpWit.Implementeert, PluginNamespace + ".Core.Http.JlStartupFilterSpike"),
        new HttpWit("Microsoft.AspNetCore.Builder.UseExtensions", "Use", PluginNamespace + ".Core.Http.JlStartupFilterSpike"),
        // Het attribuut op de eigen acties dat de ene pipeline laat lopen (nooit een globaal filter: MvcOptions is JL0001).
        new HttpWit("Microsoft.AspNetCore.Mvc.Filters.IAsyncActionFilter", HttpWit.Implementeert, PluginNamespace + ".Core.Http.JlRouteAttribute"),
        // Hetzelfde attribuut ook als resultaatfilter, alleen op de eigen acties: na het resultaat schrijft de wacht tegen
        // doorsturen (DoorstuurWacht, R-HARDE-EIS-20) de vaste fout als het antwoord een 3xx of Location had.
        new HttpWit("Microsoft.AspNetCore.Mvc.Filters.IAsyncAlwaysRunResultFilter", HttpWit.Implementeert, PluginNamespace + ".Core.Http.JlRouteAttribute"));

    /// <summary>
    /// De browser als tussenpersoon (R-HARDE-EIS-18, S-G1-17 herstelronde 9): een antwoord dat de browser doorstuurt. Elk lid
    /// van een type uit <see cref="DoorstuurNamespaces"/> waarvan de naam van het lid of van het type een van deze woorden
    /// bevat, is JL0001, ook een constante en ook aanmaken: een redirect (<c>Redirect</c>, <c>RedirectPreserveMethod</c>,
    /// <c>LocalRedirect…</c>, <c>RedirectTo…</c>, <c>HttpResponse.Redirect</c>, <c>Results.Redirect</c>, <c>RedirectResult</c>,
    /// <c>StatusCodes.Status307TemporaryRedirect</c>), de kop Location (<c>IHeaderDictionary.Location</c>,
    /// <c>HeaderNames.Location</c>) en de antwoorden die een Location-kop zetten (<c>Created…</c>, <c>Accepted…</c>). Een
    /// browser volgt 301, 302, 307 en 308 bij DELETE en PUT met dezelfde methode en hetzelfde Authorization-token (gemeten met
    /// Chrome), dus niet alleen de varianten "PreserveMethod".
    /// </summary>
    public static readonly ImmutableArray<string> DoorstuurWoorden = ImmutableArray.Create("Redirect", "Location", "Created", "Accepted");

    /// <summary>
    /// De namespaces waarvoor <see cref="DoorstuurWoorden"/> en <see cref="DoorstuurStatusLeden"/> gelden (met alles eronder).
    /// Sinds herstelronde 10 (R-HARDE-EIS-20) ook System.Net: <c>HttpResponseHeader.Location</c> is het BCL-equivalent van
    /// <c>HeaderNames.Location</c>, en <c>HttpStatusCode.TemporaryRedirect</c> en elke andere 3xx-waarde uit
    /// <see cref="DoorstuurStatusEnums"/> is JL0001 (ook <c>Found</c>, <c>SeeOther</c> en <c>MultipleChoices</c>, waarvan de naam
    /// geen van de woorden bevat).
    /// </summary>
    public static readonly ImmutableArray<string> DoorstuurNamespaces = ImmutableArray.Create("Microsoft.AspNetCore", "Microsoft.Net.Http.Headers", "System.Net");

    /// <summary>De statusenums waarvan elke waarde van 300 tot en met 399 JL0001 is, ook als de naam geen van de woorden bevat.</summary>
    public static readonly ImmutableArray<string> DoorstuurStatusEnums = ImmutableArray.Create("System.Net.HttpStatusCode");

    /// <summary>
    /// De witte lijst van punt 8 (R-HARDE-EIS-20, herstelronde 10): een lid dat anders "stuurt de browser door" geeft, in precies
    /// één klasse, en alleen als argument van een aanroep uit <see cref="DoorstuurWitAanroepen"/> op de antwoordkoppen
    /// (<see cref="DoorstuurWitKoppen"/>). Zo kan de wacht tegen doorsturen de kop Location zien en weghalen, maar nergens zetten.
    /// </summary>
    public static readonly ImmutableArray<HttpWit> DoorstuurWitteLijst = ImmutableArray.Create(
        new HttpWit("Microsoft.Net.Http.Headers.HeaderNames", "Location", PluginNamespace + ".Core.Http.DoorstuurWacht"));

    /// <summary>De aanroepen waarin een lid van <see cref="DoorstuurWitteLijst"/> als argument mag staan: kijken en weghalen.</summary>
    public static readonly ImmutableArray<string> DoorstuurWitAanroepen = ImmutableArray.Create("ContainsKey", "Remove");

    /// <summary>
    /// Het type waarvan de eigenschap <c>Headers</c> de ontvanger moet zijn van een aanroep uit <see cref="DoorstuurWitAanroepen"/>:
    /// de koppen van het antwoord (<c>antwoord.Headers.Remove(HeaderNames.Location)</c>), niet die van het verzoek of een ander
    /// woordenboek.
    /// </summary>
    public const string DoorstuurWitKoppen = "Microsoft.AspNetCore.Http.HttpResponse";

    /// <summary>De statuscodes 3xx als constante (<c>StatusCodes.Status301MovedPermanently</c>, …): het voorvoegsel van het lid.</summary>
    public static readonly ImmutableArray<(string Type, string Voorvoegsel)> DoorstuurStatusLeden = ImmutableArray.Create(("Microsoft.AspNetCore.Http.StatusCodes", "Status3"));

    /// <summary>
    /// Een kopnaam die een antwoord doorstuurt: deze tekst als constante (hoofdletters tellen niet, ook samengesteld uit
    /// constanten) is overal JL0001. Zo kan ook een eigen antwoordtype (<c>JlResult.Headers</c>) geen Location-kop krijgen.
    /// </summary>
    public static readonly ImmutableArray<string> DoorstuurKoppen = ImmutableArray.Create("Location");

    /// <summary>
    /// Een statuscode 300 tot en met 399 als constante, gezet op een eigenschap met deze naam of meegegeven aan een parameter met
    /// deze naam, van een type uit <see cref="DoorstuurNamespaces"/> (<c>HttpResponse.StatusCode = 307</c>,
    /// <c>StatusCode(308)</c>, <c>new StatusCodeResult(307)</c>, <c>new ObjectResult(x) { StatusCode = 307 }</c>), is JL0001.
    /// </summary>
    public static readonly ImmutableArray<string> DoorstuurStatusNamen = ImmutableArray.Create("StatusCode", "statusCode");

    /// <summary>
    /// De instellingen van de host (R-HARDE-EIS-19, S-G1-17 herstelronde 9): elk type uit deze namespaces (met alles eronder)
    /// waarvan de naam op <see cref="HostOptieAchtervoegsel"/> eindigt, plus <see cref="HostOptieTypen"/>. Ze gelden voor alle
    /// routes en acties van de server: <c>Mvc.JsonOptions</c> (de JSON-invoer van elke serveractie), <c>Http.Json.JsonOptions</c>,
    /// <c>ApiBehaviorOptions</c>, <c>ForwardedHeadersOptions</c>, <c>KestrelServerOptions</c>, <c>MvcOptions</c>, … Elk lid
    /// (ook lezen, ook aanmaken), elke aanroep of elk type met zo'n type als typeargument (<c>Configure&lt;JsonOptions&gt;</c>,
    /// <c>PostConfigure&lt;JsonOptions&gt;</c>, <c>AddOptions&lt;T&gt;().Bind</c>, <c>IOptions&lt;JsonOptions&gt;.Value</c>,
    /// <c>typeof(IConfigureOptions&lt;JsonOptions&gt;)</c>) en elk eigen type dat zo'n type implementeert of ervan afleidt, ook
    /// als typeargument (<c>IConfigureOptions&lt;T&gt;</c>, <c>IPostConfigureOptions&lt;T&gt;</c>,
    /// <c>IConfigureNamedOptions&lt;T&gt;</c>), is JL0001, behalve wat op <see cref="HostOptieWitteLijst"/> staat.
    /// </summary>
    public static readonly ImmutableArray<string> HostOptieNamespaces = ImmutableArray.Create("Microsoft.AspNetCore");

    /// <summary>Open generieke optiediensten kunnen ook de hostconfiguratie vervangen (S-G1-16).</summary>
    public static readonly ImmutableArray<string> OptieInfrastructuurNamespaces = ImmutableArray.Create("Microsoft.Extensions.Options");

    public const string HostOptieAchtervoegsel = "Options";

    /// <summary>Instellingen van de host buiten <see cref="HostOptieNamespaces"/> (metadatanaam).</summary>
    public static readonly ImmutableArray<string> HostOptieTypen = ImmutableArray.Create("Microsoft.Extensions.Hosting.HostOptions");

    /// <summary>
    /// De witte lijst van de instellingen van de host, per klasse (zoals <see cref="HttpWitteLijst"/>; bij "implementeert" is
    /// <see cref="HttpWit.Type"/> het optietype). Leeg: de plugin gebruikt geen optietype van de host. Een regel komt er alleen
    /// op met een eigen ADR.
    /// </summary>
    public static readonly ImmutableArray<HttpWit> HostOptieWitteLijst = ImmutableArray<HttpWit>.Empty;

    /// <summary>
    /// Netwerkclients (R-HARDE-EIS-17, besluit punt 2): elk lid van een type uit deze namespaces (ook aanmaken, ook een eigen
    /// type dat ervan afleidt, zoals een <c>DelegatingHandler</c>) is JL0001, in elke namespace, behalve in een klasse uit
    /// <see cref="NetwerkKlassen"/>. Zo kan plugincode de eigen server niet via loopback aanroepen met het token van een
    /// binnenkomend verzoek. <c>IHttpClientFactory</c> ligt ook in System.Net.Http.
    /// </summary>
    public static readonly ImmutableArray<string> NetwerkNamespaces = ImmutableArray.Create(
        "System.Net.Http",
        "System.Net.Sockets",
        "System.Net.WebSockets",
        "System.Net.Quic");

    /// <summary>
    /// Netwerkclients buiten die namespaces (met elk afgeleid type): buiten de opslaglaag al JL0002 (bestanden, zie
    /// <see cref="BestandVolledigTypen"/>), in de opslaglaag JL0001 als netwerkclient.
    /// </summary>
    public static readonly ImmutableArray<string> NetwerkTypen = ImmutableArray.Create("System.Net.WebClient", "System.Net.WebRequest");

    /// <summary>
    /// De transportklassen die een netwerkclient mogen gebruiken (volledige naam). Leeg: de plugin heeft er nu geen nodig.
    /// Een klasse komt er alleen op met een eigen ADR, en moet bij het draaien loopback, het eigen serveradres en link-local
    /// weigeren (ook na het oplossen van de naam en na een omleiding), met een test daarop (ADR-0032, kop "HTTP-laag en netwerk").
    /// </summary>
    public static readonly ImmutableArray<string> NetwerkKlassen = ImmutableArray<string>.Empty;

    /// <summary>Waar als de namespace of de assembly bij de server-ABI hoort (niet de eigen plugin).</summary>
    public static bool IsServerAbi(string ruimte, string? assembly) =>
        !InNamespace(ruimte, ImmutableArray.Create(PluginNamespace))
        && (InNamespace(ruimte, ServerAbiNamespaces)
            || (assembly is not null && !assembly.StartsWith(PluginNamespace, StringComparison.Ordinal) && ServerAbiNamespaces.Any(n => assembly == n || assembly.StartsWith(n + ".", StringComparison.Ordinal))));
}
