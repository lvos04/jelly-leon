using System;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Core.Hub;

/// <summary>
/// Blijvende herhaalcache op <c>(iss, jti)</c> tot <c>exp</c> + 30 s (contract §4.6). Een mutatie met een al
/// gebruikte jti geeft 401 token_replayed, behalve de exacte herhaling (zelfde jti, methode, pad en
/// Idempotency-Key): die beantwoordt de idempotentielaag. Is de controle niet mogelijk, dan 503.
/// </summary>
internal sealed class JtiStore
{
    private readonly JlDatabase _db;

    public JtiStore(CoreDatabase db)
    {
        _db = db.Db;
    }

    public void Controleer(HubPrincipal wie, string methode, string pad, string? idempotencyKey, DateTimeOffset nu)
    {
        var mutatie = methode is not ("GET" or "HEAD");
        var seconden = nu.ToUnixTimeSeconds();
        bool herhaald;
        try
        {
            herhaald = _db.Met(v =>
            {
                JlDatabase.Voer(v, "DELETE FROM hub_jti WHERE exp + 30 < $nu", ("$nu", seconden));
                var toegevoegd = JlDatabase.Voer(
                    v,
                    "INSERT OR IGNORE INTO hub_jti(iss, jti, exp, methode, pad, idem) VALUES('hub', $jti, $exp, $m, $p, $i)",
                    ("$jti", wie.Jti),
                    ("$exp", wie.Exp),
                    ("$m", methode),
                    ("$p", pad),
                    ("$i", idempotencyKey));
                if (toegevoegd == 1 || !mutatie)
                {
                    return false;
                }

                var zelfde = JlDatabase.Getal(
                    v,
                    "SELECT COUNT(*) FROM hub_jti WHERE iss='hub' AND jti=$jti AND methode=$m AND pad=$p AND idem IS NOT NULL AND idem=$i",
                    ("$jti", wie.Jti),
                    ("$m", methode),
                    ("$p", pad),
                    ("$i", idempotencyKey));
                return zelfde == 0;
            });
        }
        catch (JlException)
        {
            throw Fouten.ReplayControleOnbeschikbaar();
        }

        if (herhaald)
        {
            throw Fouten.NietGeauthenticeerd("token_replayed");
        }
    }
}
