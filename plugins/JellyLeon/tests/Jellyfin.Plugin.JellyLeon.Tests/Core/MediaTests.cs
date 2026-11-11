using System;
using System.IO;
using Jellyfin.Plugin.JellyLeon.Core.Media;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>Koppelcontrole zonder proefschrijven, de stroomonderbreker bij massale wezen en de stabiele spoorsleutel.</summary>
public sealed class MediaTests
{
    private static readonly string[] _mountinfo =
    [
        "22 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw",
        "30 22 0:25 / /media ro,relatime - zfs pool/media ro,xattr",
        "31 30 0:26 / /media/schrijf rw,relatime - zfs pool/schrijf rw,xattr",
        "32 22 0:27 / /mnt/met\\040spatie rw,relatime shared:1 master:2 - ext4 /dev/sdb1 ro",
        "kapotte regel",
    ];

    [Theory]
    [InlineData("/media/films/film.mkv", "AlleenLezen")]
    [InlineData("/media", "AlleenLezen")]
    [InlineData("/media/schrijf/film.mkv", "Schrijfbaar")]
    [InlineData("/mediaander/film.mkv", "Schrijfbaar")]
    [InlineData("/config/data", "Schrijfbaar")]
    [InlineData("/mnt/met spatie/film.mkv", "AlleenLezen")]
    public void MountCheck_KiestHetLangsteKoppelpunt(string pad, string verwacht)
    {
        Assert.Equal(verwacht, MountCheck.Beoordeel(pad, _mountinfo).ToString());
    }

    [Fact]
    public void MountCheck_ZonderGegevensIsOnbekend()
    {
        Assert.Equal(MountCheck.Uitkomst.Onbekend, MountCheck.Beoordeel("/media", Array.Empty<string>()));
        Assert.Equal(MountCheck.Uitkomst.Onbekend, MountCheck.Beoordeel("/media", new[] { "kapotte regel" }));
        Assert.Equal(MountCheck.Uitkomst.Onbekend, MountCheck.Beoordeel("/media", Path.Combine(Path.GetTempPath(), "bestaat-niet-" + Guid.NewGuid().ToString("N"))));
    }

    [Theory]
    [InlineData(0, 0, false)]
    [InlineData(1000, 50, false)]
    [InlineData(1000, 51, true)]
    [InlineData(100, 5, false)]
    [InlineData(100, 6, true)]
    [InlineData(10, 1, true)]
    [InlineData(100000, 50, false)]
    [InlineData(100000, 51, true)]
    [InlineData(0, 51, true)]
    public void OrphanBreaker_MeerDanVijfProcentOfVijftigItemsBevriest(int totaal, int wezen, bool verwacht)
    {
        Assert.Equal(verwacht, OrphanBreaker.MoetBevriezen(totaal, wezen));
    }

    [Fact]
    public void StreamKey_IsStabielEnZonderLeesbareTitel()
    {
        var sleutel = StreamKey.Ingebed(2, "AAC", "NLD", 6, "Commentaar van de regisseur");
        Assert.Matches("^emb:2:aac:nld:6:[0-9a-f]{12}$", sleutel);
        Assert.Equal(sleutel, StreamKey.Ingebed(2, "aac", "nld", 6, "Commentaar van de regisseur"));
        Assert.NotEqual(sleutel, StreamKey.Ingebed(2, "aac", "nld", 6, "Andere titel"));
        Assert.NotEqual(sleutel, StreamKey.Ingebed(3, "aac", "nld", 6, "Commentaar van de regisseur"));
        Assert.DoesNotContain("Commentaar", sleutel, StringComparison.OrdinalIgnoreCase);
        Assert.Matches("^emb:0:und:und:0:[0-9a-f]{12}$", StreamKey.Ingebed(0, null, string.Empty, null, null));
        Assert.StartsWith("emb:1:a_b:c_d:2:", StreamKey.Ingebed(1, "a:b", "c:d", 2, null));

        var moment = new DateTime(2026, 11, 11, 10, 0, 0, DateTimeKind.Utc);
        var extern1 = StreamKey.Extern("/media/films/film.nl.srt", 1234, moment);
        Assert.Matches("^ext:[0-9a-f]{64}$", extern1);
        Assert.Equal(extern1, StreamKey.Extern("/media/films/film.nl.srt", 1234, moment));
        Assert.NotEqual(extern1, StreamKey.Extern("/media/films/film.nl.srt", 1235, moment));
        Assert.NotEqual(extern1, StreamKey.Extern("/media/films/film.nl.srt", 1234, moment.AddSeconds(1)));
        Assert.NotEqual(extern1, StreamKey.Extern("/media/films/film.en.srt", 1234, moment));
    }
}
