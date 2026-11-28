using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Outbox;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Modules.WatchTogether;

/// <summary>WT-1 bewaart uitsluitend groepsmetadata. De server beheert de groepen en het afspelen.</summary>
internal sealed class WatchTogetherModule : ModuleOverdracht, IJellyLeonModule
{
    public const string ModuleSlug = "watch";
    private const string Zout = "wt-hmac.key";
    private readonly JlDatabase _db;
    private readonly IModuleSwitches _instellingen;
    private readonly SecretStore _geheimen;
    private readonly Outbox _outbox;
    private bool _gestart;

    public WatchTogetherModule(JlPaths paden, SecretStore geheimen, Outbox outbox, IModuleSwitches instellingen)
    {
        _instellingen = instellingen;
        _geheimen = geheimen;
        _outbox = outbox;
        _db = new JlDatabase(paden, paden.ModuleDb(ModuleSlug),
        [
            """
            CREATE TABLE wt_group_meta(
                group_id TEXT PRIMARY KEY, owner TEXT, created_at INTEGER NOT NULL, ended_at INTEGER,
                detected_by TEXT, event_id TEXT UNIQUE, reported INTEGER NOT NULL DEFAULT 0
            );
            """,
            """
            ALTER TABLE wt_group_meta ADD COLUMN visibility TEXT NOT NULL DEFAULT 'open';
            ALTER TABLE wt_group_meta ADD COLUMN laggard_policy TEXT NOT NULL DEFAULT 'wachten';
            """,
        ]);
    }

    public override string Slug => ModuleSlug;
    protected override bool HadVersielozeExport => true;
    public string Naam => "Watch Together";
    public IReadOnlyList<string> ItemTypes => [];
    public IReadOnlyList<string> EventTypes => ["media.watchgroup.ended", "media.watchgroup.degraded"];
    public IReadOnlyList<string> JobTypes => [];
    public IReadOnlyList<PersoonsgegevenRegel> Persoonsgegevens =>
        [
            new(Slug, "wt_group_meta", "HMAC van eigenaar-ID", "Eigenaarschap van een SyncPlay-groep", "Standaard 6 uur na einde", "verwijzing naar de eigenaar wissen"),
            new(Slug, "configuratie", "GuestUserIds", "Gastinstelling voor de zelftest", "Tot verwijdering van instelling of account", "account uit de gastenlijst wissen"),
        ];

    public IReadOnlyList<JsonObject> Items(string type, DateTimeOffset nu) => [];
    protected override Herstelplan LeesHerstel(BodyLezer lezer) => new(new JsonObject(), () =>
    {
        if (_db.Bestaat)
        {
            // Ook bij een lege overdracht wordt de bestaande Watch-database vóór bevestiging veiliggesteld.
            _db.MetImportkopie(_ => { }, _ => 0);
        }
    });

    public void ControleerOpslag() => _db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM wt_group_meta"));
    public void WisSporen()
    {
        if (_db.Bestaat)
        {
            _db.WisSporen();
        }
    }

    // Dezelfde DB-vergrendeling ordent opstarten, gebruikersverwijdering, periodieke controles en purge.
    public void Start(DateTimeOffset nu)
    {
        if (!_db.Bestaat)
        {
            return;
        }

        _db.Met(v =>
        {
            if (!_gestart)
            {
                JlDatabase.Voer(v, "UPDATE wt_group_meta SET ended_at=$t, detected_by='startup', event_id=lower(hex(randomblob(16))) WHERE ended_at IS NULL", ("$t", nu.ToUnixTimeSeconds()));
                _gestart = true;
            }
        });
        VerzendEnRuimOp(nu);
    }

    public void Noteer(Guid groep, Guid? eigenaar, DateTimeOffset nu) => _db.Met(v =>
    {
        JlDatabase.Voer(v, "INSERT OR IGNORE INTO wt_group_meta(group_id, owner, created_at) VALUES($id,$e,$t)",
            ("$id", groep.ToString("N")), ("$e", eigenaar is Guid id ? Pseudoniem(id) : null), ("$t", nu.ToUnixTimeSeconds()));
        _gestart = true;
    });

    public IReadOnlyList<Guid> Actief() => !_db.Bestaat ? [] : _db.Met(v =>
        JlDatabase.Rijen(v, "SELECT group_id FROM wt_group_meta WHERE ended_at IS NULL").Select(r => Guid.Parse((string)r[0]!)).ToList());

    public (string Zichtbaarheid, bool Eigenaar, string Etag) LeesMeta(Guid groep, Guid gebruiker)
    {
        var rij = !_db.Bestaat ? null : _db.Met(v => JlDatabase.Rijen(v,
            "SELECT visibility, laggard_policy, owner FROM wt_group_meta WHERE group_id=$id AND ended_at IS NULL",
            ("$id", groep.ToString("N"))).SingleOrDefault());
        var zichtbaarheid = (string?)rij?[0] ?? "open";
        var beleid = (string?)rij?[1] ?? "wachten";
        var eigenaar = (string?)rij?[2];
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes($"{groep:N}\n{zichtbaarheid}\n{beleid}\n{eigenaar}"));
        var isEigenaar = eigenaar is not null && _geheimen.Lees(Zout) is { } zout && eigenaar == Pseudoniem(gebruiker, zout);
        return (zichtbaarheid, isEigenaar, "\"w/" + Convert.ToHexStringLower(hash) + "\"");
    }

    public void Beeindig(Guid groep, string reden, DateTimeOffset nu) => _db.Met(v =>
        JlDatabase.Voer(v, "UPDATE wt_group_meta SET ended_at=$t, detected_by=$r, event_id=$event WHERE group_id=$id AND ended_at IS NULL",
            ("$t", nu.ToUnixTimeSeconds()), ("$r", reden), ("$event", Guid.NewGuid().ToString("N")), ("$id", groep.ToString("N"))));

    public void VerzendEnRuimOp(DateTimeOffset nu)
    {
        if (!_db.Bestaat)
        {
            return;
        }

        _db.Met(v =>
        {
            foreach (var rij in JlDatabase.Rijen(v, "SELECT group_id, ended_at-created_at, detected_by, event_id FROM wt_group_meta WHERE ended_at IS NOT NULL AND reported=0"))
            {
                var id = (string)rij[0]!;
                _outbox.Meld(Slug, "media.watchgroup.ended", "watch_group", "o_" + _geheimen.OpaakId(Slug, id),
                    new JsonObject { ["duration_s"] = Math.Max(0, (long)rij[1]!), ["detected_by"] = (string)rij[2]! },
                    vasteEventId: Guid.Parse((string)rij[3]!));
                JlDatabase.Voer(v, "UPDATE wt_group_meta SET reported=1 WHERE group_id=$id", ("$id", id));
            }

            JlDatabase.Voer(v, "DELETE FROM wt_group_meta WHERE reported=1 AND ended_at <= $grens", ("$grens", nu.AddHours(-_instellingen.GroepBewaarUren).ToUnixTimeSeconds()));
        });
    }

    public int VerwijderGebruiker(Guid gebruiker)
    {
        _instellingen.VerwijderGast(gebruiker);
        return !_db.Bestaat || _geheimen.Lees(Zout) is null ? 0 : _db.Transactioneel(v =>
        {
            const string Sql = "UPDATE wt_group_meta SET owner=NULL WHERE owner=$g";
            var eigenaar = Pseudoniem(gebruiker);
            _db.OntkoppelInKopieen("wt_group_meta", Sql, eigenaar);
            return JlDatabase.Voer(v, Sql, ("$g", eigenaar));
        });
    }

    public int TelGebruiker(Guid gebruiker) => !_db.Bestaat ? 0 : _db.Met(v =>
        _geheimen.Lees(Zout) is null ? 0 : (int)JlDatabase.Getal(v, "SELECT COUNT(*) FROM wt_group_meta WHERE owner=$e", ("$e", Pseudoniem(gebruiker))));

    public JsonObject Wis() => _db.Met(v =>
    {
        var aantal = JlDatabase.Voer(v, "DELETE FROM wt_group_meta");
        _outbox.VerwijderModule(Slug);
        _geheimen.Verwijder(Zout);
        JlDatabase.Voer(v, "PRAGMA wal_checkpoint(TRUNCATE)");
        return new JsonObject { ["deleted"] = new JsonObject { ["wt_group_meta"] = aantal }, ["secret_removed"] = true };
    });

    private string Pseudoniem(Guid id) => Pseudoniem(id, _geheimen.LeesOfMaak(Zout, 32));

    private static string Pseudoniem(Guid id, byte[] zout) => Convert.ToHexStringLower(HMACSHA256.HashData(zout, id.ToByteArray()));
}
