using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Core.Secrets;

/// <summary>
/// Geheimenmap <c>&lt;data&gt;/jelly-leon/secrets</c> (0700, bestanden 0600; plan §10.9). Een gegenereerd geheim wordt
/// bij de eerste start gemaakt en daarna nooit overschreven. Niets hiervan komt in de plugin-XML, een export of het log.
/// Een geweigerde of mislukte bestandsbewerking wordt 503 storage_unavailable, net als bij <see cref="JlDatabase.Met{T}"/>:
/// nooit een ruwe fout in een route, een gebeurtenis van de server of een achtergrondtaak (ADR-0032, deel 1e).
/// </summary>
internal sealed class SecretStore
{
    private readonly string _map;
    private readonly InternalWriteScope _bestanden;
    private readonly object _slot = new();
    private byte[]? _zout;

    public SecretStore(JlPaths paden)
    {
        _map = paden.SecretsDir;
        _bestanden = new InternalWriteScope(paden);
    }

    public byte[]? Lees(string naam, int maxBytes = int.MaxValue)
    {
        var pad = Pad(naam);
        return Opslag(() => _bestanden.LeesGeheim(pad, maxBytes));
    }

    /// <summary>Schrijft een door de beheerder ingevoerde waarde (atomisch, 0600).</summary>
    public void Schrijf(string naam, byte[] inhoud)
    {
        lock (_slot)
        {
            var pad = Pad(naam);
            Opslag(() =>
            {
                ZorgVoorMap();
                _bestanden.SchrijfAtomisch(pad, inhoud);
                return 0;
            });
        }
    }

    public void Verwijder(string naam)
    {
        lock (_slot)
        {
            var pad = Pad(naam);
            Opslag(() =>
            {
                _bestanden.Verwijder(pad);
                return 0;
            });
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

            var pad = Pad(naam);
            var nieuw = RandomNumberGenerator.GetBytes(lengte);
            return Opslag(() =>
            {
                ZorgVoorMap();
                _bestanden.SchrijfEenmalig(pad, nieuw);
                return nieuw;
            });
        }
    }

    /// <summary>Ondoorzichtige, stabiele ID voor de Hub: HMAC over soort en waarde; nooit terug te rekenen.</summary>
    public string OpaakId(string soort, string waarde)
    {
        _zout ??= LeesOfMaak("opaque-id.salt", 32);
        var mac = HMACSHA256.HashData(_zout, Encoding.UTF8.GetBytes(soort + "\n" + waarde));
        return Convert.ToHexStringLower(mac.AsSpan(0, 16));
    }

    private string Pad(string naam)
    {
        if (naam.Length == 0 || naam.AsSpan().IndexOfAny('/', '\\') >= 0 || naam.StartsWith('.'))
        {
            throw new ArgumentException("Ongeldige naam voor een geheim.", nameof(naam));
        }

        return Path.Combine(_map, naam);
    }

    private static T Opslag<T>(Func<T> werk)
    {
        try
        {
            return werk();
        }
        catch (Exception fout) when (fout is IOException or UnauthorizedAccessException)
        {
            throw Fouten.OpslagOnbeschikbaar();
        }
    }

    private void ZorgVoorMap() => _bestanden.MaakGeheimenmap(_map);
}
