using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Microsoft.Extensions.Hosting;

namespace Jellyfin.Plugin.JellyLeon.Core.Secrets;

/// <summary>
/// Geheimenmap <c>&lt;data&gt;/jelly-leon/secrets</c> (0700, bestanden 0600; plan §10.9). Een gegenereerd geheim wordt
/// bij de eerste start gemaakt en daarna nooit overschreven. Niets hiervan komt in de plugin-XML, een export of het log.
/// Een geweigerde of mislukte bestandsbewerking wordt 503 storage_unavailable, net als bij <see cref="JlDatabase.Met{T}"/>:
/// nooit een ruwe fout in een route, een gebeurtenis van de server of een achtergrondtaak (ADR-0032, deel 1e).
/// </summary>
internal sealed class SecretStore : IHostedService, IHealthBron
{
    private readonly string _map;
    private readonly InternalWriteScope _bestanden;
    private readonly object _slot = new();

    public SecretStore(JlPaths paden)
    {
        _map = paden.SecretsDir;
        _bestanden = new InternalWriteScope(paden);
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        try
        {
            _ = LeesOfMaak("opaque-id.salt", 32);
        }
        catch (JlException)
        {
            // De health-check en de betrokken routes melden de oorzaak. De mediaserver start door.
        }

        return Task.CompletedTask;
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    public IEnumerable<JsonObject> Checks(DateTimeOffset nu)
    {
        lock (_slot)
        {
            try
            {
                _bestanden.ControleerGeheimenmap(_map);
                if (_bestanden.LeesGeheim(Pad("opaque-id.salt"), 32) is { Length: 32 })
                {
                    return [ConnectorService.Check("secrets", "healthy", nu)];
                }
            }
            catch (Exception fout) when (fout is IOException or UnauthorizedAccessException)
            {
                // Geen bestandsnaam, pad of inhoud in de gezondheidsmelding.
            }

            return [ConnectorService.Check("secrets", "degraded", nu, new JsonObject { ["reden"] = "geheim_niet_beschikbaar" })];
        }
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
                _bestanden.ControleerGeheim(pad);
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
                _bestanden.ControleerGeheim(pad);
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
            var bestaand = Lees(naam, Math.Max(4096, lengte));
            if (bestaand is not null)
            {
                return bestaand;
            }

            var pad = Pad(naam);
            var nieuw = RandomNumberGenerator.GetBytes(lengte);
            return Opslag(() =>
            {
                ZorgVoorMap();
                if (_bestanden.MaakGeheimEenmalig(pad, nieuw))
                {
                    return nieuw;
                }

                if (SpinWait.SpinUntil(() => File.Exists(pad), TimeSpan.FromSeconds(1))
                    && Lees(naam, Math.Max(4096, lengte)) is { } gepubliceerd)
                {
                    return gepubliceerd;
                }

                throw Fouten.GeheimOnbeschikbaar();
            });
        }
    }

    /// <summary>Ondoorzichtige, stabiele ID voor de Hub: HMAC over soort en waarde; nooit terug te rekenen.</summary>
    public string OpaakId(string soort, string waarde)
    {
        var zout = LeesOfMaak("opaque-id.salt", 32);
        if (zout.Length != 32)
        {
            throw Fouten.GeheimOnbeschikbaar();
        }

        var mac = HMACSHA256.HashData(zout, Encoding.UTF8.GetBytes(soort + "\n" + waarde));
        return Convert.ToHexStringLower(mac.AsSpan(0, 16));
    }

    public string AccountPseudoniem(Guid gebruiker) => "o_" + OpaakId("user", gebruiker.ToString("N"));

    private string Pad(string naam)
    {
        if (naam.Length == 0 || naam.AsSpan().IndexOfAny('/', '\\') >= 0 || naam.StartsWith('.') ||
            naam.StartsWith("mediaguard", StringComparison.OrdinalIgnoreCase))
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
            throw Fouten.GeheimOnbeschikbaar();
        }
    }

    private void ZorgVoorMap() => _bestanden.MaakGeheimenmap(_map);
}
