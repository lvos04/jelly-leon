// Proefcode voor de analyzer van verboden API's (ADR-0032).
// Elke regel met de markering "VERWACHT: JLxxxx" moet precies die bouwfout geven; geen enkele andere regel mag een
// JL-fout geven. Dit bestand wordt nooit geleverd en nooit uitgevoerd: het bestaat alleen om de build te laten falen.
using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Database.Implementations;
using Jellyfin.Database.Implementations.Entities;
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
            _ = lib.GetItemById(Guid.Empty);
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
            _ = item.Name;
            _ = lib.GetPerson("x");
            _ = lib.GetGenreId("x");
            _ = repo.RetrieveItem(Guid.Empty);
            _ = await repo.ItemExistsAsync(Guid.Empty);
        }

        public void Kijkgeschiedenis(IUserDataManager gegevens, User gebruiker, BaseItem item, UserItemData stand)
        {
            gegevens.SaveUserData(gebruiker, item, stand, default, CancellationToken.None); // VERWACHT: JL0001
            gegevens.UpdatePlayState(item, stand, null); // VERWACHT: JL0001
            gegevens.ResetPlaybackStreamSelections(gebruiker, item); // VERWACHT: JL0001
            _ = gegevens.GetUserData(gebruiker, item);
        }

        public async Task Metadata(IProviderManager aanbieders, ISubtitleManager ondertitels, IMediaSegmentManager segmenten, BaseItem item, CancellationToken stop)
        {
            aanbieders.QueueRefresh(Guid.Empty, null, default); // VERWACHT: JL0001
            await aanbieders.RefreshFullItem(item, null, stop); // VERWACHT: JL0001
            await ondertitels.DeleteSubtitles(item, 0); // VERWACHT: JL0001
            await segmenten.DeleteSegmentAsync(Guid.Empty); // VERWACHT: JL0001
            _ = segmenten.HasSegments(Guid.Empty);
            _ = ondertitels.GetSupportedProviders(item);
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
            _ = gebruikers.GetUserById(Guid.Empty);
            _ = apparaten.GetDevice("d");
            _ = instellingen.GetConfiguration("k");
            _ = lijsten.GetPlaylists(Guid.Empty);
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
            _ = voorkeuren.ListItemDisplayPreferences(Guid.Empty, "web");
            await hoofdstukken.DeleteChaptersAsync(Guid.Empty, stop); // VERWACHT: JL0001
            hoofdstukken.SaveChapters(Guid.Empty, null); // VERWACHT: JL0001
            _ = hoofdstukken.GetChapters(Guid.Empty);
            await hoofdstukbeheer.DeleteChapterDataAsync(Guid.Empty, stop); // VERWACHT: JL0001
            hoofdstukbeheer.SaveChapters(item, null); // VERWACHT: JL0001
            _ = hoofdstukbeheer.Supports(item);
            sporen.SaveMediaStreams(Guid.Empty, null, stop); // VERWACHT: JL0001
            _ = sporen.GetMediaStreamLanguages(default);
            bijlagen.SaveMediaAttachments(Guid.Empty, null, stop); // VERWACHT: JL0001
            mensen.UpdatePeople(Guid.Empty, null); // VERWACHT: JL0001
            _ = mensen.DeleteOrphanedCredits(); // VERWACHT: JL0001
            _ = mensen.GetPeopleNames(null);
            await keyframes.SaveKeyframeDataAsync(Guid.Empty, null, stop); // VERWACHT: JL0001
            await keyframebeheer.DeleteKeyframeDataAsync(Guid.Empty, stop); // VERWACHT: JL0001
            _ = keyframebeheer.GetKeyframeData(Guid.Empty);
            await trickplay.DeleteTrickplayDataAsync(Guid.Empty, stop); // VERWACHT: JL0001
            await trickplay.SaveTrickplayInfo(null); // VERWACHT: JL0001
            _ = await trickplay.GetTrickplayResolutions(Guid.Empty);
            koppelingen.UpsertLinkedChild(Guid.Empty, Guid.Empty, default); // VERWACHT: JL0001
            _ = koppelingen.RerouteLinkedChildren(Guid.Empty, Guid.Empty); // VERWACHT: JL0001
            _ = koppelingen.GetLinkedChildrenIds(Guid.Empty);
            await extern_.DeleteExternalItemDataAsync(item, stop); // VERWACHT: JL0001
            await activiteit.CreateAsync(null); // VERWACHT: JL0001
            await activiteit.CleanAsync(DateTime.MinValue); // VERWACHT: JL0001
            await sleutels.CreateApiKey("x"); // VERWACHT: JL0001
            await sleutels.DeleteApiKey("x"); // VERWACHT: JL0001
            _ = await sleutels.GetApiKeys();
            await backup.RestoreBackupAsync("x"); // VERWACHT: JL0001
            backup.ScheduleRestoreAndRestartServer("x"); // VERWACHT: JL0001
            _ = await backup.EnumerateBackups();
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
            _ = metadata.CanRefresh(item);
            _ = await bronnen.GetPlaybackMediaSources(item, gebruiker, true, false, stop); // VERWACHT: JL0001
            _ = bronnen.GetStaticMediaSources(item, false, null);
            await songteksten.DeleteLyricsAsync(nummer); // VERWACHT: JL0001
            _ = await songteksten.GetLyricsAsync(nummer, stop);
            _ = await kanalen.GetChannelItemsInternal(null, null, stop); // VERWACHT: JL0001
            await kanalen.DeleteItem(item); // VERWACHT: JL0001
            _ = kanalen.GetChannel("x");
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
            taken.ScheduledTasks[0].Triggers = null; // VERWACHT: JL0001
            taken.ScheduledTasks[0].ReloadTriggerEvents(); // VERWACHT: JL0001
            _ = taak.GetDefaultTriggers();
            _ = taken.ScheduledTasks[0].Triggers;
            // Leesleden die via IChannelManager kanaalitems aanmaken, verversen of wissen.
            var opties = new MediaBrowser.Controller.Dto.DtoOptions();
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
            _ = livetv.IsEnabledForUser(gebruiker);
            _ = map.GetChildren(gebruiker, true); // VERWACHT: JL0001
            _ = serie.GetEpisodes(gebruiker, opties, false);
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
}
