using System;
using System.Collections.Concurrent;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.JellyLeon.Core.Idempotency;

/// <summary>
/// De ene idempotentielaag (contract §5): dezelfde sleutel met hetzelfde verzoek geeft het oorspronkelijke antwoord
/// terug met <c>Idempotent-Replay: true</c>; een ander verzoek 422; een lopend verzoek 409. Bewaartermijn 24 uur.
/// </summary>
internal sealed class IdempotencyStore
{
    private const int BewaarSeconden = 86400;
    private readonly JlDatabase _db;
    private readonly ConcurrentDictionary<(string Scope, string Sleutel), byte> _teAnnuleren = new();

    public IdempotencyStore(CoreDatabase db)
        : this(db.Db)
    {
    }

    internal IdempotencyStore(JlDatabase db)
    {
        _db = db;
    }

    /// <summary>Start een verzoek. Geeft het bewaarde antwoord terug bij een herhaling, anders <c>null</c>.</summary>
    public JlResult? Begin(string scope, string sleutel, string verzoekHash, DateTimeOffset nu, bool alleenHerhalen = false, RouteSpec? route = null, string? oudeSleutel = null)
    {
        var seconden = nu.ToUnixTimeSeconds();
        return _db.Met<JlResult?>(v =>
        {
            JlDatabase.Voer(v, "DELETE FROM idempotentie WHERE gemaakt < $grens", ("$grens", seconden - BewaarSeconden));
            VerwerkAnnuleringen(v);
            var leesScope = route is null ? scope : OpgeslagenScope(v, scope, sleutel, route);
            var leesSleutel = oudeSleutel is null ? sleutel : JlDatabase.Scalar(v,
                "SELECT sleutel FROM idempotentie WHERE scope=$s AND sleutel IN ($k, $oud) ORDER BY sleutel=$k DESC LIMIT 1",
                ("$s", scope), ("$k", sleutel), ("$oud", oudeSleutel)) as string ?? sleutel;
            if (!alleenHerhalen && leesScope == scope && leesSleutel == sleutel && JlDatabase.Voer(
                    v,
                    "INSERT OR IGNORE INTO idempotentie(scope, sleutel, verzoek_hash, staat, gemaakt) VALUES($s, $k, $h, 'bezig', $nu)",
                    ("$s", scope), ("$k", sleutel), ("$h", verzoekHash), ("$nu", seconden)) == 1)
            {
                return null;
            }

            var rijen = JlDatabase.Rijen(v, "SELECT verzoek_hash, staat, status, body, etag FROM idempotentie WHERE scope=$s AND sleutel=$k", ("$s", leesScope), ("$k", leesSleutel));
            if (rijen.Count == 0)
            {
                throw Fouten.NietGeauthenticeerd("token_replayed");
            }

            var rij = rijen[0];
            if (!string.Equals((string)rij[0]!, verzoekHash, StringComparison.Ordinal))
            {
                throw Fouten.SleutelHergebruikt();
            }

            if (!string.Equals((string)rij[1]!, "klaar", StringComparison.Ordinal))
            {
                throw Fouten.SleutelBezig();
            }

            var antwoord = new JlResult(Convert.ToInt32(rij[2], System.Globalization.CultureInfo.InvariantCulture), (string?)rij[3]);
            antwoord.Headers["Idempotent-Replay"] = "true";
            if (rij[4] is string etag)
            {
                antwoord.Headers["ETag"] = etag;
            }

            return antwoord;
        });
    }

    private static string OpgeslagenScope(SqliteConnection verbinding, string scope, string sleutel, RouteSpec route)
    {
        // Alleen de letterlijke routedelen en de afsluitende slash mogen verschillen in rijen van een oudere versie.
        var naAanvrager = scope.IndexOf('\n', StringComparison.Ordinal) + 1;
        var beginPad = scope.IndexOf('\n', naAanvrager) + 1;
        var prefix = scope[..beginPad];
        // Beperk de primaire index tot deze aanvrager en methode. Elk routepad begint met een slash.
        var kandidaten = JlDatabase.Rijen(verbinding,
            """
            SELECT scope FROM idempotentie
            WHERE scope BETWEEN $prefix AND ($prefix || char(0x10ffff)) AND sleutel=$k
                AND scope COLLATE NOCASE IN ($s, $slash)
            ORDER BY scope=$s DESC, gemaakt
            """,
            ("$prefix", prefix), ("$k", sleutel), ("$s", scope), ("$slash", scope + "/"));
        foreach (var rij in kandidaten)
        {
            var eerder = (string)rij[0]!;
            if (eerder.StartsWith(prefix, StringComparison.Ordinal) && route.CanoniekPad(eerder[beginPad..]) == scope[beginPad..])
            {
                return eerder;
            }
        }

        return scope;
    }

    public void Voltooi(string scope, string sleutel, JlResult antwoord)
    {
        antwoord.Headers.TryGetValue("ETag", out var etag);
        try
        {
            _db.Met(v => JlDatabase.Voer(
                v,
                "UPDATE idempotentie SET staat='klaar', status=$st, body=$b, etag=$e WHERE scope=$s AND sleutel=$k",
                ("$st", antwoord.Status),
                ("$b", antwoord.Body),
                ("$e", etag),
                ("$s", scope),
                ("$k", sleutel)));
        }
        catch (JlException)
        {
            Annuleer(scope, sleutel);
            throw;
        }
    }

    /// <summary>Een verzoek dat met een serverfout eindigde mag opnieuw: de sleutel komt weer vrij.</summary>
    public void Annuleer(string scope, string sleutel)
    {
        _teAnnuleren[(scope, sleutel)] = 0;
        try
        {
            _db.Met(VerwerkAnnuleringen);
        }
        catch (JlException)
        {
            // De volgende poging verwerkt de annulering zodra dezelfde opslag weer bereikbaar is.
        }
    }

    private void VerwerkAnnuleringen(SqliteConnection verbinding)
    {
        // Begin en Annuleer lopen hiervoor beide onder het slot van dezelfde JlDatabase.
        foreach (var ((scope, sleutel), _) in _teAnnuleren)
        {
            JlDatabase.Voer(verbinding, "DELETE FROM idempotentie WHERE scope=$s AND sleutel=$k AND staat='bezig'", ("$s", scope), ("$k", sleutel));
            _teAnnuleren.TryRemove((scope, sleutel), out _);
        }
    }
}
