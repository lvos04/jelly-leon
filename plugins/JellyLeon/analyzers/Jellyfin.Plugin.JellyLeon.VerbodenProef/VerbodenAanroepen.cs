// Proefcode voor de analyzer van verboden API's (ADR-0032).
// Elke regel met de markering "VERWACHT: JLxxxx" moet precies die bouwfout geven; geen enkele andere regel mag een
// JL-fout geven. Dit bestand wordt nooit geleverd en nooit uitgevoerd: het bestaat alleen om de build te laten falen.
// Sinds herstelronde 7 (S-G1-17) is de server-ABI een witte lijst per klasse: ook lezen van een servertype is JL0001 buiten
// die lijst, dus de leesregels hieronder staan ook gemarkeerd. Elke regel geeft precies één melding. Sinds herstelronde 8 is
// System.Linq.Expressions een omweg (elk lid), en staan onderaan de HTTP-laag, netwerkclients en de nieuwe omwegen.
using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Database.Implementations;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Database.Implementations.Locking;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller.Collections;
using MediaBrowser.Controller.Configuration;
using MediaBrowser.Controller.Devices;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.MediaSegments;
using MediaBrowser.Controller.Persistence;
using MediaBrowser.Controller.Playlists;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Controller.Session;
using MediaBrowser.Controller.Subtitles;
using MediaBrowser.Model.IO;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.DependencyInjection;

namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
{
    public class VerbodenAanroepen
    {
        public async Task Bibliotheek(ILibraryManager lib, IItemRepository repo, IItemPersistenceService opslag, BaseItem item, CancellationToken stop)
        {
            await lib.UpdateItemAsync(item, item, default, stop); // VERWACHT: JL0001
            lib.DeleteItem(item, null); // VERWACHT: JL0001
            lib.CreateItem(item, null); // VERWACHT: JL0001
            lib.QueueLibraryScan(); // VERWACHT: JL0001
            await lib.RemoveVirtualFolder("x", false); // VERWACHT: JL0001
            opslag.SaveItems(null, stop); // VERWACHT: JL0001
            opslag.UpdateInheritedValues(); // VERWACHT: JL0001
            await item.UpdateToRepositoryAsync(default, stop); // VERWACHT: JL0001
            await item.RefreshMetadata(stop); // VERWACHT: JL0001
            item.AddStudio("x"); // VERWACHT: JL0001
            Func<BaseItem, BaseItem, MediaBrowser.Controller.Library.ItemUpdateType, CancellationToken, Task> omweg = lib.UpdateItemAsync; // VERWACHT: JL0001
            _ = omweg;
            _ = lib.GetItemById(Guid.Empty); // VERWACHT: JL0001
            // Heet "Get…", maar maakt in upstream een item of map aan als die ontbreekt: ook verboden.
            _ = lib.GetOrCreatePerson("x"); // VERWACHT: JL0001
            _ = lib.GetGenre("x"); // VERWACHT: JL0001
            _ = lib.GetStudio("x"); // VERWACHT: JL0001
            _ = lib.GetArtist("x"); // VERWACHT: JL0001
            _ = lib.GetNamedView("x", Jellyfin.Data.Enums.CollectionType.movies, "x"); // VERWACHT: JL0001
            _ = lib.GetUserRootFolder(); // VERWACHT: JL0001
            await item.ReattachUserDataAsync(stop); // VERWACHT: JL0001
            _ = item.OnMetadataChanged(); // VERWACHT: JL0001
            // Een eigenschap van een serverobject zetten is ook schrijven: het item is gedeeld met de cache van de server.
            item.Name = "x"; // VERWACHT: JL0001
            item.IsLocked = true; // VERWACHT: JL0001
            _ = item.Name; // VERWACHT: JL0001
            _ = lib.GetPerson("x"); // VERWACHT: JL0001
            _ = lib.GetGenreId("x"); // VERWACHT: JL0001
            _ = repo.RetrieveItem(Guid.Empty); // VERWACHT: JL0001
            _ = await repo.ItemExistsAsync(Guid.Empty); // VERWACHT: JL0001
        }

        public void Kijkgeschiedenis(IUserDataManager gegevens, User gebruiker, BaseItem item, UserItemData stand)
        {
            gegevens.SaveUserData(gebruiker, item, stand, default, CancellationToken.None); // VERWACHT: JL0001
            gegevens.UpdatePlayState(item, stand, null); // VERWACHT: JL0001
            gegevens.ResetPlaybackStreamSelections(gebruiker, item); // VERWACHT: JL0001
            _ = gegevens.GetUserData(gebruiker, item); // VERWACHT: JL0001
        }

        public async Task Metadata(IProviderManager aanbieders, ISubtitleManager ondertitels, IMediaSegmentManager segmenten, BaseItem item, CancellationToken stop)
        {
            aanbieders.QueueRefresh(Guid.Empty, null, default); // VERWACHT: JL0001
            await aanbieders.RefreshFullItem(item, null, stop); // VERWACHT: JL0001
            await ondertitels.DeleteSubtitles(item, 0); // VERWACHT: JL0001
            await segmenten.DeleteSegmentAsync(Guid.Empty); // VERWACHT: JL0001
            _ = segmenten.HasSegments(Guid.Empty); // VERWACHT: JL0001
            _ = ondertitels.GetSupportedProviders(item); // VERWACHT: JL0001
        }

        public async Task Beheer(IUserManager gebruikers, ISessionManager sessies, IDeviceManager apparaten, IServerConfigurationManager instellingen, IConfigurationManager basis, IPlaylistManager lijsten, ICollectionManager collecties, User gebruiker)
        {
            await gebruikers.UpdateUserAsync(gebruiker); // VERWACHT: JL0001
            await gebruikers.DeleteUserAsync(Guid.Empty); // VERWACHT: JL0001
            await sessies.Logout("x"); // VERWACHT: JL0001
            await sessies.RevokeUserTokens(Guid.Empty, "x"); // VERWACHT: JL0001
            await apparaten.UpdateDeviceOptions("d", "n"); // VERWACHT: JL0001
            instellingen.SaveConfiguration(); // VERWACHT: JL0001
            basis.SaveConfiguration("k", new object()); // VERWACHT: JL0001
            await lijsten.RemovePlaylistsAsync(Guid.Empty); // VERWACHT: JL0001
            await collecties.AddToCollectionAsync(Guid.Empty, Array.Empty<Guid>()); // VERWACHT: JL0001
            _ = await collecties.GetCollectionsFolder(true); // VERWACHT: JL0001
            _ = lijsten.GetPlaylistsFolder(); // VERWACHT: JL0001
            _ = await sessies.GetSessionByAuthenticationToken("t", "d", "e"); // VERWACHT: JL0001
            _ = gebruikers.GetUserById(Guid.Empty); // VERWACHT: JL0001
            _ = apparaten.GetDevice("d"); // VERWACHT: JL0001
            _ = instellingen.GetConfiguration("k"); // VERWACHT: JL0001
            _ = lijsten.GetPlaylists(Guid.Empty); // VERWACHT: JL0001
        }

        // Overige diensten die zelf in jellyfin.db schrijven (R-HARDE-EIS-1, S-G1-17): nergens toegestaan.
        public async Task Serverdatabase(
            MediaBrowser.Controller.IDisplayPreferencesManager voorkeuren,
            IChapterRepository hoofdstukken,
            MediaBrowser.Controller.Chapters.IChapterManager hoofdstukbeheer,
            IMediaStreamRepository sporen,
            IMediaAttachmentRepository bijlagen,
            IPeopleRepository mensen,
            IKeyframeRepository keyframes,
            MediaBrowser.Controller.IO.IKeyframeManager keyframebeheer,
            MediaBrowser.Controller.Trickplay.ITrickplayManager trickplay,
            ILinkedChildrenService koppelingen,
            MediaBrowser.Controller.IO.IExternalDataManager extern_,
            MediaBrowser.Model.Activity.IActivityManager activiteit,
            MediaBrowser.Controller.Security.IAuthenticationManager sleutels,
            Jellyfin.Server.Implementations.SystemBackupService.IBackupService backup,
            BaseItem item,
            CancellationToken stop)
        {
            var p = voorkeuren.GetDisplayPreferences(Guid.Empty, Guid.Empty, "web"); // VERWACHT: JL0001
            _ = voorkeuren.GetItemDisplayPreferences(Guid.Empty, Guid.Empty, "web"); // VERWACHT: JL0001
            voorkeuren.UpdateDisplayPreferences(p); // VERWACHT: JL0001
            voorkeuren.SetCustomItemDisplayPreferences(Guid.Empty, Guid.Empty, "web", null); // VERWACHT: JL0001
            _ = voorkeuren.ListItemDisplayPreferences(Guid.Empty, "web"); // VERWACHT: JL0001
            await hoofdstukken.DeleteChaptersAsync(Guid.Empty, stop); // VERWACHT: JL0001
            hoofdstukken.SaveChapters(Guid.Empty, null); // VERWACHT: JL0001
            _ = hoofdstukken.GetChapters(Guid.Empty); // VERWACHT: JL0001
            await hoofdstukbeheer.DeleteChapterDataAsync(Guid.Empty, stop); // VERWACHT: JL0001
            hoofdstukbeheer.SaveChapters(item, null); // VERWACHT: JL0001
            _ = hoofdstukbeheer.Supports(item); // VERWACHT: JL0001
            sporen.SaveMediaStreams(Guid.Empty, null, stop); // VERWACHT: JL0001
            _ = sporen.GetMediaStreamLanguages(default); // VERWACHT: JL0001
            bijlagen.SaveMediaAttachments(Guid.Empty, null, stop); // VERWACHT: JL0001
            mensen.UpdatePeople(Guid.Empty, null); // VERWACHT: JL0001
            _ = mensen.DeleteOrphanedCredits(); // VERWACHT: JL0001
            _ = mensen.GetPeopleNames(null); // VERWACHT: JL0001
            await keyframes.SaveKeyframeDataAsync(Guid.Empty, null, stop); // VERWACHT: JL0001
            await keyframebeheer.DeleteKeyframeDataAsync(Guid.Empty, stop); // VERWACHT: JL0001
            _ = keyframebeheer.GetKeyframeData(Guid.Empty); // VERWACHT: JL0001
            await trickplay.DeleteTrickplayDataAsync(Guid.Empty, stop); // VERWACHT: JL0001
            await trickplay.SaveTrickplayInfo(null); // VERWACHT: JL0001
            _ = await trickplay.GetTrickplayResolutions(Guid.Empty); // VERWACHT: JL0001
            koppelingen.UpsertLinkedChild(Guid.Empty, Guid.Empty, default); // VERWACHT: JL0001
            _ = koppelingen.RerouteLinkedChildren(Guid.Empty, Guid.Empty); // VERWACHT: JL0001
            _ = koppelingen.GetLinkedChildrenIds(Guid.Empty); // VERWACHT: JL0001
            await extern_.DeleteExternalItemDataAsync(item, stop); // VERWACHT: JL0001
            await activiteit.CreateAsync(null); // VERWACHT: JL0001
            await activiteit.CleanAsync(DateTime.MinValue); // VERWACHT: JL0001
            await sleutels.CreateApiKey("x"); // VERWACHT: JL0001
            await sleutels.DeleteApiKey("x"); // VERWACHT: JL0001
            _ = await sleutels.GetApiKeys(); // VERWACHT: JL0001
            await backup.RestoreBackupAsync("x"); // VERWACHT: JL0001
            backup.ScheduleRestoreAndRestartServer("x"); // VERWACHT: JL0001
            _ = await backup.EnumerateBackups(); // VERWACHT: JL0001
        }

        // Diensten die via een andere server-API schrijven, verversen of een servertaak starten: nergens toegestaan.
        public async Task Omwegen(
            MediaBrowser.Model.Tasks.ITaskManager taken,
            ILibraryMonitor bewaker,
            IMetadataService metadata,
            IMediaSourceManager bronnen,
            MediaBrowser.Controller.Lyrics.ILyricManager songteksten,
            MediaBrowser.Controller.Channels.IChannelManager kanalen,
            MediaBrowser.Controller.LiveTv.ILiveTvManager livetv,
            MediaBrowser.Controller.LiveTv.IGuideManager gids,
            MediaBrowser.Controller.LiveTv.IRecordingsManager opnames,
            MediaBrowser.Controller.LiveTv.IListingsManager aanbieders,
            MediaBrowser.Controller.LiveTv.ITunerHostManager tuners,
            MediaBrowser.Controller.QuickConnect.IQuickConnect snelkoppelen,
            MediaBrowser.Controller.Authentication.IAuthenticationProvider aanmelden,
            MediaBrowser.Controller.Authentication.IPasswordResetProvider herstel,
            MediaBrowser.Controller.Events.IEventManager events,
            BaseItem item,
            User gebruiker,
            MediaBrowser.Controller.Entities.Audio.Audio nummer,
            MediaBrowser.Model.Tasks.IScheduledTask taak,
            IUserViewManager weergaven,
            Folder map,
            MediaBrowser.Controller.Entities.TV.Season seizoen,
            MediaBrowser.Controller.Entities.TV.Series serie,
            UserView weergave,
            Playlist lijst,
            CancellationToken stop)
        {
            taken.QueueScheduledTask(null, null); // VERWACHT: JL0001
            bewaker.ReportFileSystemChanged("x"); // VERWACHT: JL0001
            _ = await metadata.RefreshMetadata(item, null, stop); // VERWACHT: JL0001
            _ = metadata.CanRefresh(item); // VERWACHT: JL0001
            _ = await bronnen.GetPlaybackMediaSources(item, gebruiker, true, false, stop); // VERWACHT: JL0001
            _ = bronnen.GetStaticMediaSources(item, false, null); // VERWACHT: JL0001
            await songteksten.DeleteLyricsAsync(nummer); // VERWACHT: JL0001
            _ = await songteksten.GetLyricsAsync(nummer, stop); // VERWACHT: JL0001
            _ = await kanalen.GetChannelItemsInternal(null, null, stop); // VERWACHT: JL0001
            await kanalen.DeleteItem(item); // VERWACHT: JL0001
            _ = kanalen.GetChannel("x"); // VERWACHT: JL0001
            await livetv.CancelTimer("x"); // VERWACHT: JL0001
            await gids.RefreshGuide(null, stop); // VERWACHT: JL0001
            opnames.CancelRecording("x", null); // VERWACHT: JL0001
            aanbieders.DeleteListingsProvider("x"); // VERWACHT: JL0001
            tuners.DeleteTunerHost("x"); // VERWACHT: JL0001
            _ = await snelkoppelen.AuthorizeRequest(Guid.Empty, "x"); // VERWACHT: JL0001
            await aanmelden.ChangePassword(gebruiker, "x"); // VERWACHT: JL0001
            _ = await herstel.RedeemPasswordResetPin("x"); // VERWACHT: JL0001
            events.Publish(EventArgs.Empty); // VERWACHT: JL0001
            // Een servertaak via het taakobject zelf starten of de planning ervan wijzigen (S-G1-17, herstelronde 2).
            await taak.ExecuteAsync(null, stop); // VERWACHT: JL0001
            var werkers = taken.ScheduledTasks; // VERWACHT: JL0001
            werkers[0].Triggers = null; // VERWACHT: JL0001
            werkers[0].ReloadTriggerEvents(); // VERWACHT: JL0001
            _ = taak.GetDefaultTriggers(); // VERWACHT: JL0001
            _ = werkers[0].Triggers; // VERWACHT: JL0001
            // Leesleden die via IChannelManager kanaalitems aanmaken, verversen of wissen.
            var opties = new MediaBrowser.Controller.Dto.DtoOptions(); // VERWACHT: JL0001
            _ = await livetv.GetRecordingsAsync(null, opties); // VERWACHT: JL0001
            _ = await livetv.GetRecordingFoldersAsync(gebruiker); // VERWACHT: JL0001
            _ = weergaven.GetLatestItems(null, opties); // VERWACHT: JL0001
            _ = map.GetItems(null); // VERWACHT: JL0001
            _ = map.GetItemList(null); // VERWACHT: JL0001
            _ = map.GetChildCount(gebruiker); // VERWACHT: JL0001
            _ = map.GetRecursiveChildCount(gebruiker); // VERWACHT: JL0001
            _ = seizoen.GetEpisodes(); // VERWACHT: JL0001
            _ = seizoen.GetChildren(gebruiker, true, null); // VERWACHT: JL0001
            _ = serie.GetSeasonEpisodes(seizoen, gebruiker, opties, false); // VERWACHT: JL0001
            _ = weergave.GetRecursiveChildren(gebruiker, null, out _); // VERWACHT: JL0001
            _ = lijst.GetChildren(gebruiker, true, null); // VERWACHT: JL0001
            _ = Playlist.GetPlaylistItems(null, gebruiker, opties); // VERWACHT: JL0001
            _ = livetv.IsEnabledForUser(gebruiker); // VERWACHT: JL0001
            _ = map.GetChildren(gebruiker, true); // VERWACHT: JL0001
            _ = serie.GetEpisodes(gebruiker, opties, false); // VERWACHT: JL0001
        }

        public void Bestanden(string pad, IFileSystem bestandssysteem)
        {
            File.WriteAllText(pad, "x"); // VERWACHT: JL0002
            File.Delete(pad); // VERWACHT: JL0002
            File.Move(pad, pad + "2"); // VERWACHT: JL0002
            File.Copy(pad, pad + "2"); // VERWACHT: JL0002
            using var a = File.Create(pad); // VERWACHT: JL0002
            using var b = File.Open(pad, FileMode.Open); // VERWACHT: JL0002
            Directory.CreateDirectory(pad); // VERWACHT: JL0002
            Directory.Delete(pad, true); // VERWACHT: JL0002
            using var c = new FileStream(pad, FileMode.Create); // VERWACHT: JL0002
            using var d = new StreamWriter(pad); // VERWACHT: JL0002
            new FileInfo(pad).Delete(); // VERWACHT: JL0002
            new FileInfo(pad).Attributes = FileAttributes.Normal; // VERWACHT: JL0002
            new DirectoryInfo(pad).Create(); // VERWACHT: JL0002
            bestandssysteem.DeleteFile(pad); // VERWACHT: JL0002
            bestandssysteem.SwapFiles(pad, pad + "2"); // VERWACHT: JL0002
            using var e = new SqliteConnection("Data Source=" + pad); // VERWACHT: JL0002
            Action<string> omweg = File.Delete; // VERWACHT: JL0002
            _ = omweg;
            _ = File.Exists(pad);
            _ = File.ReadAllText(pad);
            using var f = File.OpenRead(pad);
            _ = Directory.GetFiles(pad);
            _ = new FileInfo(pad).Length;
            using var g = new StreamWriter(Stream.Null);
        }

        public void Database(JellyfinDbContext context, string data) // VERWACHT: JL0003
        {
            var nieuw = "/config/data/jellyfin.db"; // VERWACHT: JL0003
            var oud = "Data Source=/config/data/LIBRARY.DB"; // VERWACHT: JL0003
            _ = context;
            _ = nieuw;
            _ = oud;
            _ = "/config/data/jelly-leon/quality/quality.db";
            // Samengesteld, via een constante of geïnterpoleerd (R-HARDE-EIS-2, S-G1-17): ook verboden.
            const string Naam = "library";
            _ = Path.Combine(data, "jellyfin" + ".db"); // VERWACHT: JL0003
            _ = Path.Combine(data, Naam + ".db"); // VERWACHT: JL0003
            _ = $"{data}/jellyfin.d" + "b"; // VERWACHT: JL0003
            _ = $"{data}/{Naam}.db"; // VERWACHT: JL0003
            _ = data + "/jelly" + 'f' + "in.db"; // VERWACHT: JL0003
            _ = "Data Source=" + data + "/jellyfin.db"; // VERWACHT: JL0003
            // Een getal dat een teken wordt, UTF-8-tekst en een uitlijning die niets aanvult (S-G1-17, herstelronde 2).
            _ = "jellyfin" + (char)46 + "db"; // VERWACHT: JL0003
            _ = "jellyfin" + (char)0x2E + "db"; // VERWACHT: JL0003
            _ = System.Text.Encoding.UTF8.GetString("library.db"u8); // VERWACHT: JL0003
            _ = $"jellyfin{".db",0}"; // VERWACHT: JL0003
            _ = $"jellyfin{".db",3}"; // VERWACHT: JL0003
            // Een optelling van UTF-8-teksten is ook een samenstelling (R-HARDE-EIS-8, S-G1-17 herstelronde 3).
            _ = System.Text.Encoding.UTF8.GetString("jellyfin"u8 + ".db"u8); // VERWACHT: JL0003
            _ = System.Text.Encoding.UTF8.GetString("library.d"u8 + "b"u8); // VERWACHT: JL0003
            _ = $"jellyfin{".db",6}";
            _ = "jellyfin" + (int)'.' + "db";
            _ = "jellyfin" + data + ".db";
            _ = $"{data}/jelly-leon/{Naam}-export.json";
        }

        public void Processen()
        {
            using var a = Process.Start("ffmpeg", "-version"); // VERWACHT: JL0004
            var b = new ProcessStartInfo("sh"); // VERWACHT: JL0004
            using var c = new Process(); // VERWACHT: JL0004
            _ = b;
            _ = Process.GetCurrentProcess().Id;
        }
    }

    // De databasedienst van de server (R-HARDE-EIS-10, S-G1-17 herstelronde 4): elk gebruik van de typenaam is JL0003.
    public class DatabaseDienst
    {
        private readonly IJellyfinDatabaseProvider _db; // VERWACHT: JL0003

        public DatabaseDienst(IJellyfinDatabaseProvider db, IServiceProvider diensten) // VERWACHT: JL0003
        {
            _db = db;
            _ = diensten.GetService<IJellyfinDatabaseProvider>(); // VERWACHT: JL0003
            _ = typeof(IJellyfinDatabaseProvider); // VERWACHT: JL0003
            var fabriek = // VERWACHT: JL0003
                _db.DbContextFactory; // VERWACHT: JL0001
            _ = fabriek;
            _ = diensten.GetService<IServiceProvider>();
        }

        public void Slot(IEntityFrameworkCoreLockingBehavior slot) => _ = slot; // VERWACHT: JL0003

        public void Query(IItemQueryHelpers query) => _ = query; // VERWACHT: JL0003
    }
}

// Databasetoegang buiten Core.Storage (R-HARDE-EIS-12, S-G1-17 herstelronde 5): elke weg naar een databaseverbinding of -bron
// is JL0002; de opties van de serverdatabase resolven of injecteren is JL0003. Een gekregen verbinding doorgeven mag.
namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
{
    using System.Data;
    using System.Data.Common;
    using Microsoft.EntityFrameworkCore;
    using Microsoft.EntityFrameworkCore.Diagnostics;
    using Microsoft.EntityFrameworkCore.Infrastructure;

    public class Databasetoegang
    {
        public Databasetoegang(DbContextOptions serveropties) // VERWACHT: JL0003
        {
            _ = serveropties.Extensions; // VERWACHT: JL0002
        }

        public async Task Verbinding(MediaBrowser.Common.Configuration.IApplicationPaths paden, IServiceProvider diensten, SqliteConnection gekregen, DbCommand opdracht, object iets, CancellationToken stop)
        {
            var pad = Path.Combine(paden.DataPath, string.Concat("jellyfin", ".db")); // VERWACHT: JL0001
            using var a = SqliteFactory.Instance.CreateConnection(); // VERWACHT: JL0002
            a.ConnectionString = "Data Source=" + pad; // VERWACHT: JL0002
            a.Open(); // VERWACHT: JL0002
            using var b = SqliteFactory.Instance.CreateDataSource("Data Source=" + pad); // VERWACHT: JL0002
            using var c = b.CreateConnection(); // VERWACHT: JL0002
            await using var d = await b.OpenConnectionAsync(stop); // VERWACHT: JL0002
            var fabriek = DbProviderFactories.GetFactory("Microsoft.Data.Sqlite"); // VERWACHT: JL0002
            _ = diensten.GetService<DbProviderFactory>(); // VERWACHT: JL0002
            _ = diensten.GetService(typeof(SqliteFactory)); // VERWACHT: JL0002
            _ = Activator.CreateInstance<SqliteConnection>(); // VERWACHT: JL0002
            gekregen.BackupDatabase(gekregen, "main", "main"); // VERWACHT: JL0002
            gekregen.ConnectionString = "Data Source=" + pad; // VERWACHT: JL0002
            _ = gekregen.Handle; // VERWACHT: JL0002
            _ = opdracht.Connection; // VERWACHT: JL0002
            _ = (DbConnection)iets; // VERWACHT: JL0002
            _ = iets as IDbConnection; // VERWACHT: JL0002
            _ = iets is SqliteConnection; // VERWACHT: JL0002
            if (iets is DbConnection f) // VERWACHT: JL0002
            {
                _ = f;
            }

            Func<DbConnection> later = SqliteFactory.Instance.CreateConnection; // VERWACHT: JL0002
            _ = SQLitePCL.raw.sqlite3_open(pad, out var g); // VERWACHT: JL0002
            _ = Met(v => v); // VERWACHT: JL0002
            _ = later;
            _ = g;
            _ = fabriek;
            // Toegestaan: een gekregen verbinding doorgeven (zoals JlDatabase.Met die geeft) en een databasetype als parametertype.
            _ = Met(v => Doorgeven(v));
            DbConnection h = gekregen;
            _ = h;
            _ = Doorgeven(gekregen);
        }

        public void Ef(IServiceProvider diensten, IServiceCollection services, DbContextOptions<DbContext> opties)
        {
            _ = diensten.GetRequiredService<DbContextOptions>(); // VERWACHT: JL0003
            _ = diensten.GetService(typeof(DbContextOptions)); // VERWACHT: JL0003
            _ = diensten.GetService<IDbContextOptions>(); // VERWACHT: JL0002
            _ = new DbContextOptionsBuilder(); // VERWACHT: JL0002
            _ = new DbContextOptionsBuilder<DbContext>(opties); // VERWACHT: JL0002
            _ = RelationalOptionsExtension.Extract(opties).ConnectionString; // VERWACHT: JL0002
            _ = opties.FindExtension<RelationalOptionsExtension>(); // VERWACHT: JL0002
            using var ctx = new DbContext(opties); // VERWACHT: JL0002
            _ = ctx.Database.GetDbConnection(); // VERWACHT: JL0002
            services.AddDbContext<DbContext>(o => { }); // VERWACHT: JL0002
            services.AddSingleton<IInterceptor, Onderschepper>(); // VERWACHT: JL0002
        }

        private static int Doorgeven(SqliteConnection verbinding)
        {
            _ = verbinding;
            return 0;
        }

        private static T Met<T>(Func<SqliteConnection, T> werk) => werk(null);
    }

    // Een onderschepper krijgt de verbinding van de server zelf: die gebruiken is JL0002.
    public class Onderschepper : DbConnectionInterceptor
    {
        public override void ConnectionOpened(DbConnection connection, ConnectionEndEventData eventData)
        {
            using var opdracht = connection.CreateCommand(); // VERWACHT: JL0002
            opdracht.CommandText = "DELETE FROM UserData";
            _ = opdracht.ExecuteNonQuery();
        }
    }
}

// Bestanden buiten Core.Storage (R-HARDE-EIS-13, S-G1-17 herstelronde 6): de proef SlippendeRoutes van herreview 5 (jellyfin.db
// als bestand overschrijven of wissen, met een naam die pas bij het draaien ontstaat), de regel op de bestandsnamespaces met
// de witte lijst, de server-ABI die zelf schrijft of een proces start, en de omwegen (native code, reflectie, dynamic).
namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
{
    using System.Data;
    using System.Formats.Tar;
    using System.IO.Compression;
    using System.IO.MemoryMappedFiles;
    using System.Linq.Expressions;
    using System.Reflection;
    using System.Reflection.Emit;
    using System.Runtime.InteropServices;
    using System.Runtime.Loader;
    using System.Text;
    using System.Xml;
    using System.Xml.Linq;
    using Jellyfin.Extensions;
    using MediaBrowser.Common.Plugins;
    using MediaBrowser.Controller.MediaEncoding;
    using MediaBrowser.Controller.Streaming;
    using MediaBrowser.Model.Serialization;

    public class EigenSchrijver : StreamWriter
    {
        public EigenSchrijver(string pad) : base(pad) // VERWACHT: JL0002
        {
        }
    }

    public static class Bestandsroutes
    {
        [DllImport("libc")] private static extern int unlink(string pad); // VERWACHT: JL0002

        private static unsafe int Wijzer(delegate* unmanaged<int> f) => f(); // VERWACHT: JL0002

        public static async Task SlippendeRoutes(IApplicationPaths paden, IPluginManager plugins, IXmlSerializer xml, ITranscodeManager transcode, StreamState staat, string bron)
        {
            var map = paden.DataPath; // VERWACHT: JL0001
            var db = Path.Combine(map, string.Concat("jellyfin", ".db"));
            var manifest = new PluginManifest(); // VERWACHT: JL0001
            var plugin = new LocalPlugin(map, true, manifest); // VERWACHT: JL0002
            _ = plugins.RemovePlugin(plugin); // VERWACHT: JL0002
            xml.SerializeToFile(new object(), db); // VERWACHT: JL0002
            ZipFile.ExtractToDirectory(bron, map, overwriteFiles: true); // VERWACHT: JL0002
            TarFile.ExtractToDirectory(bron, map, overwriteFiles: true); // VERWACHT: JL0002
            using (var w = XmlWriter.Create(db)) // VERWACHT: JL0002
            {
                _ = w;
            }

            new XDocument().Save(db); // VERWACHT: JL0002
            new DataSet().WriteXml(db); // VERWACHT: JL0002
            using var mm = MemoryMappedFile.CreateFromFile(db, FileMode.Open); // VERWACHT: JL0002
            using var zicht = mm.CreateViewAccessor(); // VERWACHT: JL0002
            zicht.Write(0, (byte)0); // VERWACHT: JL0002
            _ = await transcode.StartFfMpeg(staat, db, "-y " + db, Guid.Empty, TranscodingJobType.Progressive, new CancellationTokenSource()); // VERWACHT: JL0002
            _ = unlink(db); // VERWACHT: JL0002
        }

        public static async Task WitteLijst(string pad, Stream stroom, byte[] inhoud, MediaBrowser.Controller.IO.IPathManager paden)
        {
            _ = Path.GetTempFileName(); // VERWACHT: JL0002
            using var a = File.OpenHandle(pad, FileMode.Open, FileAccess.ReadWrite); // VERWACHT: JL0002
            RandomAccess.Write(a, inhoud, 0); // VERWACHT: JL0002
            using var b = new GZipStream(stroom, CompressionLevel.Fastest); // VERWACHT: JL0002
            using var c = new FormattingStreamWriter(pad, System.Globalization.CultureInfo.InvariantCulture); // VERWACHT: JL0002
            Microsoft.VisualBasic.FileIO.FileSystem.DeleteFile(pad); // VERWACHT: JL0002
            using var d = new System.Diagnostics.TextWriterTraceListener(pad); // VERWACHT: JL0002
            new XElement("x").Save(stroom); // VERWACHT: JL0002
            _ = AsyncFile.Create(pad); // VERWACHT: JL0002
            // Toegestaan: padbewerking, lezen, en lezen of schrijven op een stroom die de code al heeft.
            _ = Path.Combine(pad, "x.json");
            _ = File.Exists(pad) ? File.ReadAllText(pad) : string.Empty;
            using var e = new StreamReader(pad);
            _ = await e.ReadToEndAsync();
            using var f = new MemoryStream();
            await f.WriteAsync(inhoud);
            await stroom.WriteAsync(inhoud);
            using var g = new StreamWriter(stroom, Encoding.UTF8, 1024, leaveOpen: true);
            await g.WriteAsync("x");
            _ = new IOException("x");
            var sb = new StringBuilder();
            using (var h = XmlWriter.Create(sb))
            {
                new XDocument(new XElement("x")).Save(h);
            }

            _ = AsyncFile.OpenRead(pad); // VERWACHT: JL0001
            _ = paden.GetAttachmentPath("x", "y"); // VERWACHT: JL0001
        }

        public static void Omwegen(string pad, object iets, MethodInfo methode, Delegate d)
        {
            var bib = NativeLibrary.Load("libc"); // VERWACHT: JL0002
            _ = Marshal.GetDelegateForFunctionPointer<Func<int>>(bib); // VERWACHT: JL0002
            _ = methode.Invoke(null, new object[] { pad }); // VERWACHT: JL0002
            _ = Type.GetType("System.IO.File"); // VERWACHT: JL0002
            _ = Assembly.LoadFrom(pad); // VERWACHT: JL0002
            _ = AssemblyLoadContext.Default.LoadFromAssemblyPath(pad); // VERWACHT: JL0002
            _ = Activator.CreateInstance(typeof(FileStream), pad, FileMode.Create); // VERWACHT: JL0002
            _ = d.DynamicInvoke(pad); // VERWACHT: JL0002
            var getal = Expression.Constant(1); // VERWACHT: JL0002
            var lambda = Expression.Lambda<Func<int>>(getal); // VERWACHT: JL0002
            _ = lambda.Compile(); // VERWACHT: JL0002
            dynamic x = iets;
            x.Delete(pad); // VERWACHT: JL0002
            _ = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("x"), AssemblyBuilderAccess.Run); // VERWACHT: JL0002
            unsafe // VERWACHT: JL0002
            {
                int* p = null;
                _ = p == null;
            }

            // Toegestaan: de reflectie die de plugin gebruikt.
            _ = typeof(Bestandsroutes).Assembly.GetName().Version;
            _ = iets.GetType().Name;
        }
    }
}

// Herstelronde 7 (S-G1-17; R-HARDE-EIS-14, -15 en -16): de server-ABI als witte lijst per klasse, toewijzen aan een servertype,
// uitbreidingspunten per namespace, de configuratieroute van BasePlugin<T>, WebClient/WebRequest/trace en StreamReader met
// FileStreamOptions.
namespace Jellyfin.Plugin.JellyLeon.Configuration
{
    public class PluginConfiguration : MediaBrowser.Model.Plugins.BasePluginConfiguration
    {
    }
}

namespace Jellyfin.Plugin.JellyLeon
{
    using MediaBrowser.Common.Plugins;
    using MediaBrowser.Model.Plugins;
    using MediaBrowser.Model.Serialization;

    // De echte pluginklasse met één verkeerde regel (route -14a); de basisconstructor en de configuratiepagina staan op de
    // witte lijst van deze klasse.
    public class Plugin : BasePlugin<Configuration.PluginConfiguration>, IHasWebPages
    {
        public Plugin(IApplicationPaths paden, IXmlSerializer xml)
            : base(paden, xml)
        {
        }

        public override string Name => "Jelly Leon";

        public override string ConfigurationFileName => "jellyfin.xml"; // VERWACHT: JL0002

        public System.Collections.Generic.IEnumerable<PluginPageInfo> GetPages()
        {
            yield return new PluginPageInfo { Name = "x", DisplayName = "x", EmbeddedResourcePath = "x" };
            yield return new PluginPageInfo { EnableInMainMenu = true }; // VERWACHT: JL0001
        }
    }
}

namespace Jellyfin.Plugin.JellyLeon.Core
{
    // De witte lijst geldt per klasse: in deze klasse mag precies GetVirtualFolders, een ander lid niet.
    public class BibliotheekMappen
    {
        public void M(ILibraryManager lib)
        {
            _ = lib.GetVirtualFolders();
            _ = lib.GetItemById(Guid.Empty); // VERWACHT: JL0001
        }
    }
}

namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
{
    using System.Net;
    using MediaBrowser.Controller;
    using MediaBrowser.Controller.Resolvers;

    public class ServerAbiWitteLijst
    {
        public void Lezen(ILibraryManager lib, SessionInfo s, IServerApplicationHost host, IApplicationPaths paden, Jellyfin.Plugin.JellyLeon.Plugin plugin, string naam)
        {
            _ = lib.GetVirtualFolders(); // VERWACHT: JL0001
            s.NowPlayingItem = null; // VERWACHT: JL0001
            var pad = paden.BackupPath; // VERWACHT: JL0001
            host.RestoreBackupPath = naam; // VERWACHT: JL0001
            _ = host.GetExports<ILibraryPostScanTask>(); // VERWACHT: JL0001
            plugin.SaveConfiguration(); // VERWACHT: JL0001
            // Toegestaan: een constante of enumwaarde en een typenaam.
            _ = Jellyfin.Database.Implementations.Enums.PermissionKind.IsAdministrator;
            _ = typeof(ILibraryManager);
            _ = pad;
        }

#pragma warning disable SYSLIB0014
        public void Schrijvers(Uri doel, string pad, FileStreamOptions opties)
        {
            using var w = new WebClient(); // VERWACHT: JL0002
            var r = WebRequest.Create(doel); // VERWACHT: JL0002
            r.Method = "PUT"; // VERWACHT: JL0002
            Trace.WriteLine("x"); // VERWACHT: JL0002
            var l = new DefaultTraceListener(); // VERWACHT: JL0002
            l.LogFileName = pad; // VERWACHT: JL0002
            using var lezer = new StreamReader(pad, opties); // VERWACHT: JL0002
            using var gewoon = new StreamReader(pad);
        }
#pragma warning restore SYSLIB0014
    }

    // Een uitbreidingspunt buiten de witte lijst: de server zou deze regel zelf bij elke scan gebruiken.
    public class Negeerregel : IResolverIgnoreRule // VERWACHT: JL0001
    {
        public bool ShouldIgnore(FileSystemMetadata fileInfo, BaseItem parent) => true;
    }
}

// Herstelronde 8 (S-G1-17; R-HARDE-EIS-17 en de grenzen 2 en 3 van herreview 7): de HTTP-laag van de server (vormen A, B en
// D), netwerkclients (vorm C: loopback met het token van de client) en de omwegen via reflectie in een bibliotheek,
// DispatchProxy, expressiebomen, Unsafe en modelbinding op een bestaand object.
namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
{
    using System.ComponentModel;
    using System.Linq.Expressions;
    using System.Net.Http;
    using System.Net.Sockets;
    using System.Reflection;
    using System.Runtime.CompilerServices;
    using System.Security.Claims;
    using Microsoft.AspNetCore.Authentication;
    using Microsoft.AspNetCore.Builder;
    using Microsoft.AspNetCore.Hosting;
    using Microsoft.AspNetCore.Http;
    using Microsoft.AspNetCore.Mvc;
    using Microsoft.AspNetCore.Mvc.Filters;
    using Microsoft.AspNetCore.Mvc.Infrastructure;
    using Microsoft.Extensions.Configuration;

    // Vorm A: een middleware vóór routing die een clientverzoek omzet naar een wis-verzoek.
    public sealed class Omzetter : IStartupFilter // VERWACHT: JL0001
    {
        public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => app =>
        {
            app.Use(async (http, volgende) => // VERWACHT: JL0001
            {
                http.Request.Method = "DELETE"; // VERWACHT: JL0001
                http.Request.Path = "/UserPlayedItems/x"; // VERWACHT: JL0001
                await volgende(http);
            });
            next(app);
        };
    }

    // Vorm B: een globaal MVC-filter dat de argumenten van een serveractie wijzigt.
    public sealed class Omleiden : IActionFilter // VERWACHT: JL0001
    {
        public void OnActionExecuting(ActionExecutingContext context) => context.ActionArguments["itemId"] = "x"; // VERWACHT: JL0001

        public void OnActionExecuted(ActionExecutedContext context)
        {
        }
    }

    // Vorm D: een claimsomzetting die de gebruiker verwisselt.
    public sealed class AndereGebruiker : IClaimsTransformation // VERWACHT: JL0001
    {
        public Task<ClaimsPrincipal> TransformAsync(ClaimsPrincipal principal) => Task.FromResult(new ClaimsPrincipal());
    }

    public static class HttpLaag
    {
        public static void Registreer(IServiceCollection diensten, HttpContext http, ClaimsIdentity identiteit, Claim claim)
        {
            diensten.AddTransient<IStartupFilter, Omzetter>();
            // Sinds herstelronde 9 is de registratie met een optietype van de host zelf ook JL0001: twee regels, elk één melding.
            diensten.Configure<MvcOptions>( // VERWACHT: JL0001
                o => o.Filters.Add(new Omleiden())); // VERWACHT: JL0001
            diensten.AddTransient<IClaimsTransformation, AndereGebruiker>();
            http.Request.Headers["Authorization"] = "x"; // VERWACHT: JL0001
            http.User = new ClaimsPrincipal(); // VERWACHT: JL0001
            identiteit.AddClaim(claim); // VERWACHT: JL0001

            // Toegestaan: het verzoek lezen en het antwoord schrijven.
            _ = http.Request.Headers["Authorization"].ToString();
            http.Response.Headers["Cache-Control"] = "no-store";
        }

        // Een actie van de server in het proces uitvoeren, langs authenticatie en autorisatie heen.
        public static void Actie(IActionInvokerFactory invokers, ActionContext context)
        {
            _ = invokers.CreateInvoker(context); // VERWACHT: JL0001
        }

        // Vorm C: loopback naar de eigen server met het token van het binnenkomende verzoek.
        public static async Task Lus()
        {
            using var client = new HttpClient(); // VERWACHT: JL0001
            await client.DeleteAsync("http://127.0.0.1:8096/UserPlayedItems/x"); // VERWACHT: JL0001
            using var tcp = new TcpClient(); // VERWACHT: JL0001
        }
    }

    public class Stomp : DispatchProxy
    {
        protected override object Invoke(MethodInfo targetMethod, object[] args) => null;
    }

    public sealed class Schaduw
    {
        public DateTime LastPlaybackCheckIn;
    }

    public static class Omwegen8
    {
        public static void M(IConfiguration cfg, SessionInfo sessie, MethodInfo methode, object iets, ControllerBase controller)
        {
            cfg.Bind(sessie); // VERWACHT: JL0002
            _ = controller.TryUpdateModelAsync(sessie); // VERWACHT: JL0002
            _ = cfg.Get<SessionInfo>(); // VERWACHT: JL0002
            var eigenschappen = TypeDescriptor.GetProperties(sessie); // VERWACHT: JL0002
            eigenschappen["LastPlaybackCheckIn"].SetValue(sessie, DateTime.MinValue); // VERWACHT: JL0002
            _ = DispatchProxy.Create<IUserDataManager, Stomp>(); // VERWACHT: JL0002
            var doel = Expression.Constant(iets); // VERWACHT: JL0002
            _ = Expression.Call(doel, methode); // VERWACHT: JL0002
            Unsafe.As<Schaduw>(sessie).LastPlaybackCheckIn = DateTime.MinValue; // VERWACHT: JL0002
        }
    }
}

// Herstelronde 9 (S-G1-17; R-HARDE-EIS-18 en -19 van herreview 8): een antwoord dat de browser doorstuurt (een redirect, de
// kop Location of een 3xx-status; de browser volgt die met dezelfde methode en het token van de gebruiker) en de instellingen
// van de host (een optietype van ASP.NET Core of HostOptions: elk lid, als typeargument en als eigen implementatie).
namespace Jellyfin.Plugin.JellyLeon.Modules.Proef
{
    using System.Text.Json;
    using System.Text.Json.Serialization;
    using Microsoft.AspNetCore.Http;
    using Microsoft.AspNetCore.Mvc;
    using Microsoft.Extensions.Hosting;
    using Microsoft.Extensions.Options;

    public sealed class Doorsturen : ControllerBase
    {
        public IActionResult A(string id) => RedirectPreserveMethod("/UserPlayedItems/" + id); // VERWACHT: JL0001
        public IActionResult B() => Redirect("/UserPlayedItems/x"); // VERWACHT: JL0001
        public IActionResult C() => new RedirectResult("/x", false, true); // VERWACHT: JL0001
        public IActionResult D() => StatusCode(307); // VERWACHT: JL0001
        public IActionResult E() => Created("/UserPlayedItems/x", null); // VERWACHT: JL0001

        public void F(HttpContext http)
        {
            http.Response.Redirect("/x", false, true); // VERWACHT: JL0001
            http.Response.Headers.Location = "/UserPlayedItems/x"; // VERWACHT: JL0001
            http.Response.Headers["location"] = "/x"; // VERWACHT: JL0001
            http.Response.StatusCode = 308; // VERWACHT: JL0001

            // Toegestaan: een gewone status en een andere kop.
            http.Response.StatusCode = 404;
            http.Response.Headers["ETag"] = "x";
        }
    }

    public sealed class TicksAlsSeconden : JsonConverter<long>
    {
        public override long Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) => reader.GetInt64() * 10_000_000;

        public override void Write(Utf8JsonWriter writer, long value, JsonSerializerOptions options) => writer.WriteNumberValue(value);
    }

    public sealed class JsonInstellingen : IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions> // VERWACHT: JL0001
    {
        public void PostConfigure(string name, Microsoft.AspNetCore.Mvc.JsonOptions options)
        {
        }
    }

    public static class HostOpties
    {
        public static void Registreer(IServiceCollection diensten, IOptions<HostOptions> host)
        {
            diensten.PostConfigure<Microsoft.AspNetCore.Mvc.JsonOptions>( // VERWACHT: JL0001
                o => o.JsonSerializerOptions.Converters.Add(new TicksAlsSeconden())); // VERWACHT: JL0001
            diensten.Configure<Microsoft.AspNetCore.Http.Json.JsonOptions>(o => { }); // VERWACHT: JL0001
            diensten.Configure<ApiBehaviorOptions>(o => { }); // VERWACHT: JL0001
            var opties = host.Value; // VERWACHT: JL0001
            _ = opties.ShutdownTimeout; // VERWACHT: JL0001
        }
    }
}
