using System;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Core.Idempotency;

/// <summary>
/// De ene idempotentielaag (contract §5): dezelfde sleutel met hetzelfde verzoek geeft het oorspronkelijke antwoord
/// terug met <c>Idempotent-Replay: true</c>; een ander verzoek 422; een lopend verzoek 409. Bewaartermijn 24 uur.
/// </summary>
internal sealed class IdempotencyStore
{
    private const int BewaarSeconden = 86400;
    private readonly JlDatabase _db;

    public IdempotencyStore(CoreDatabase db)
    {
        _db = db.Db;
    }

    /// <summary>Start een verzoek. Geeft het bewaarde antwoord terug bij een herhaling, anders <c>null</c>.</summary>
    public JlResult? Begin(string scope, string sleutel, string verzoekHash, DateTimeOffset nu)
    {
        var seconden = nu.ToUnixTimeSeconds();
        return _db.Met<JlResult?>(v =>
        {
            JlDatabase.Voer(v, "DELETE FROM idempotentie WHERE gemaakt < $grens", ("$grens", seconden - BewaarSeconden));
            var toegevoegd = JlDatabase.Voer(
                v,
                "INSERT OR IGNORE INTO idempotentie(scope, sleutel, verzoek_hash, staat, gemaakt) VALUES($s, $k, $h, 'bezig', $nu)",
                ("$s", scope),
                ("$k", sleutel),
                ("$h", verzoekHash),
                ("$nu", seconden));
            if (toegevoegd == 1)
            {
                return null;
            }

            var rij = JlDatabase.Rijen(v, "SELECT verzoek_hash, staat, status, body, etag FROM idempotentie WHERE scope=$s AND sleutel=$k", ("$s", scope), ("$k", sleutel))[0];
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

    public void Voltooi(string scope, string sleutel, JlResult antwoord)
    {
        antwoord.Headers.TryGetValue("ETag", out var etag);
        _db.Met(v => JlDatabase.Voer(
            v,
            "UPDATE idempotentie SET staat='klaar', status=$st, body=$b, etag=$e WHERE scope=$s AND sleutel=$k",
            ("$st", antwoord.Status),
            ("$b", antwoord.Body),
            ("$e", etag),
            ("$s", scope),
            ("$k", sleutel)));
    }

    /// <summary>Een verzoek dat met een serverfout eindigde mag opnieuw: de sleutel komt weer vrij.</summary>
    public void Annuleer(string scope, string sleutel)
    {
        try
        {
            _db.Met(v => JlDatabase.Voer(v, "DELETE FROM idempotentie WHERE scope=$s AND sleutel=$k AND staat='bezig'", ("$s", scope), ("$k", sleutel)));
        }
        catch (JlException)
        {
            // De opslag is weg; de rij verloopt vanzelf.
        }
    }
}
