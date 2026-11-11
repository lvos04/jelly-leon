using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Core.Secrets;

/// <summary>
/// Geheimenmap <c>&lt;data&gt;/jelly-leon/secrets</c> (0700, bestanden 0600; plan §10.9). Een gegenereerd geheim wordt
/// bij de eerste start gemaakt en daarna nooit overschreven. Niets hiervan komt in de plugin-XML, een export of het log.
/// </summary>
internal sealed class SecretStore
{
    private const UnixFileMode MapModus = UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode BestandModus = UnixFileMode.UserRead | UnixFileMode.UserWrite;
    private readonly string _map;
    private readonly object _slot = new();
    private byte[]? _zout;

    public SecretStore(JlPaths paden)
    {
        _map = paden.SecretsDir;
    }

    public byte[]? Lees(string naam)
    {
        var pad = Pad(naam);
        return File.Exists(pad) ? File.ReadAllBytes(pad) : null;
    }

    /// <summary>Schrijft een door de beheerder ingevoerde waarde (atomisch, 0600).</summary>
    public void Schrijf(string naam, byte[] inhoud)
    {
        lock (_slot)
        {
            ZorgVoorMap();
            var pad = Pad(naam);
            var tijdelijk = pad + ".tmp";
            SchrijfNieuw(tijdelijk, inhoud, FileMode.Create);
            File.Move(tijdelijk, pad, overwrite: true);
        }
    }

    public void Verwijder(string naam)
    {
        lock (_slot)
        {
            File.Delete(Pad(naam));
        }
    }

    /// <summary>Leest een gegenereerd geheim of maakt het één keer aan; een bestaand bestand wordt nooit overschreven.</summary>
    public byte[] LeesOfMaak(string naam, int lengte)
    {
        lock (_slot)
        {
            var bestaand = Lees(naam);
            if (bestaand is not null)
            {
                return bestaand;
            }

            ZorgVoorMap();
            var nieuw = RandomNumberGenerator.GetBytes(lengte);
            SchrijfNieuw(Pad(naam), nieuw, FileMode.CreateNew);
            return nieuw;
        }
    }

    /// <summary>Ondoorzichtige, stabiele ID voor de Hub: HMAC over soort en waarde; nooit terug te rekenen.</summary>
    public string OpaakId(string soort, string waarde)
    {
        _zout ??= LeesOfMaak("opaque-id.salt", 32);
        var mac = HMACSHA256.HashData(_zout, Encoding.UTF8.GetBytes(soort + "\n" + waarde));
        return Convert.ToHexStringLower(mac.AsSpan(0, 16));
    }

    private static void SchrijfNieuw(string pad, byte[] inhoud, FileMode modus)
    {
        var opties = new FileStreamOptions { Mode = modus, Access = FileAccess.Write, Share = FileShare.None };
        if (!OperatingSystem.IsWindows())
        {
            opties.UnixCreateMode = BestandModus;
        }

        using var stroom = new FileStream(pad, opties);
        stroom.Write(inhoud);
        stroom.Flush(true);
    }

    private string Pad(string naam)
    {
        if (naam.Length == 0 || naam.AsSpan().IndexOfAny('/', '\\') >= 0 || naam.StartsWith('.'))
        {
            throw new ArgumentException("Ongeldige naam voor een geheim.", nameof(naam));
        }

        return Path.Combine(_map, naam);
    }

    private void ZorgVoorMap()
    {
        if (Directory.Exists(_map))
        {
            return;
        }

        if (OperatingSystem.IsWindows())
        {
            Directory.CreateDirectory(_map);
        }
        else
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_map)!);
            Directory.CreateDirectory(_map, MapModus);
        }
    }
}
