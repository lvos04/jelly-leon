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

        public void Database(JellyfinDbContext context) // VERWACHT: JL0003
        {
            var nieuw = "/config/data/jellyfin.db"; // VERWACHT: JL0003
            var oud = "Data Source=/config/data/LIBRARY.DB"; // VERWACHT: JL0003
            _ = context;
            _ = nieuw;
            _ = oud;
            _ = "/config/data/jelly-leon/quality/quality.db";
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
