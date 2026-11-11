using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Modules.Devices;

/// <summary>
/// Module Devices (F5, prototype van golf 1): houdt per afspeelsessie bij hoe er is afgespeeld (direct of
/// omgezet). Leest alleen de officiële sessiegebeurtenissen van de server en schrijft uitsluitend in het eigen
/// SQLite-bestand; nooit in de bibliotheek, de kijkgeschiedenis of de gebruikersgegevens.
/// </summary>
internal sealed class DevicesModule : ModuleBasis
{
    public const string ModuleSlug = "devices";
    private static readonly string[] _migraties =
    [
        "CREATE TABLE playback_sessions(sessie TEXT NOT NULL, gebruiker TEXT NOT NULL, apparaat TEXT NOT NULL, methode TEXT NOT NULL, "
        + "hardware INTEGER NOT NULL, gestart INTEGER NOT NULL, gestopt INTEGER, PRIMARY KEY(sessie, gebruiker));"
        + "CREATE INDEX playback_sessions_gestart ON playback_sessions(gestart);",
    ];

    private readonly SecretStore _geheimen;
    private readonly Core.Outbox.Outbox _outbox;

    public DevicesModule(JlPaths paden, SecretStore geheimen, Core.Outbox.Outbox outbox)
        : base(paden, ModuleSlug, 30, _migraties)
    {
        _geheimen = geheimen;
        _outbox = outbox;
    }

    public override string Naam => "Apparaten en afspelen";

    public override IReadOnlyList<string> ItemTypes { get; } = ["playback_stats", "device"];

    public override IReadOnlyList<string> EventTypes { get; } = ["media.transcode.started", "media.transcode.stopped"];

    public override IReadOnlyList<string> JobTypes { get; } = [];

    public override IReadOnlyList<PersoonsgegevenRegel> Persoonsgegevens { get; } =
    [
        new(ModuleSlug, "playback_sessions", "account-ID, pseudoniem van apparaat en sessie, afspeelmethode, begin en eind", "afspeelstatistiek en diagnose per apparaat", "instelbaar, standaard 30 dagen"),
    ];

    /// <summary>Legt het begin van een afspeelsessie vast. Methode: direct_play, direct_stream of transcode.</summary>
    public void RegistreerStart(IEnumerable<Guid> gebruikers, string apparaatId, string sessieId, string methode, bool hardware, DateTimeOffset nu)
    {
        var sessie = "o_" + _geheimen.OpaakId("sessie", sessieId);
        var apparaat = "o_" + _geheimen.OpaakId("apparaat", apparaatId);
        var grens = nu.ToUnixTimeSeconds() - (BewaarDagen() * 86400L);
        var nieuw = Db.Met(v =>
        {
            JlDatabase.Voer(v, "DELETE FROM playback_sessions WHERE gestart < $g", ("$g", grens));
            var rijen = 0;
            foreach (var gebruiker in gebruikers)
            {
                rijen += JlDatabase.Voer(
                    v,
                    "INSERT OR IGNORE INTO playback_sessions(sessie, gebruiker, apparaat, methode, hardware, gestart) VALUES($s, $g, $a, $m, $h, $nu)",
                    ("$s", sessie),
                    ("$g", gebruiker.ToString("N")),
                    ("$a", apparaat),
                    ("$m", methode),
                    ("$h", hardware ? 1 : 0),
                    ("$nu", nu.ToUnixTimeSeconds()));
            }

            return rijen;
        });
        if (nieuw > 0 && methode == "transcode")
        {
            _outbox.Meld(ModuleSlug, "media.transcode.started", "playback_session", sessie, new JsonObject { ["hardware"] = hardware });
        }
    }

    /// <summary>Legt het einde van een afspeelsessie vast.</summary>
    public void RegistreerStop(string sessieId, DateTimeOffset nu)
    {
        var sessie = "o_" + _geheimen.OpaakId("sessie", sessieId);
        var open = Db.Met(v =>
        {
            var rij = JlDatabase.Rijen(v, "SELECT methode, hardware, gestart FROM playback_sessions WHERE sessie = $s AND gestopt IS NULL LIMIT 1", ("$s", sessie)).FirstOrDefault();
            JlDatabase.Voer(v, "UPDATE playback_sessions SET gestopt = $nu WHERE sessie = $s AND gestopt IS NULL", ("$nu", nu.ToUnixTimeSeconds()), ("$s", sessie));
            return rij;
        });
        if (open is not null && (string)open[0]! == "transcode")
        {
            var duur = Math.Max(0, nu.ToUnixTimeSeconds() - Convert.ToInt64(open[2], CultureInfo.InvariantCulture));
            _outbox.Meld(ModuleSlug, "media.transcode.stopped", "playback_session", sessie, new JsonObject { ["hardware"] = Convert.ToInt64(open[1], CultureInfo.InvariantCulture) == 1, ["duur_s"] = duur });
        }
    }

    public override IReadOnlyList<JsonObject> Items(string type, DateTimeOffset nu)
    {
        var sinds = nu.ToUnixTimeSeconds() - 86400;
        if (type == "playback_stats")
        {
            return [Db.Met(v => Telling(v, "laatste_24u", sinds, nu))];
        }

        return Db.Met(v => JlDatabase.Rijen(v, "SELECT apparaat, COUNT(DISTINCT sessie), MAX(gestart) FROM playback_sessions GROUP BY apparaat ORDER BY apparaat")
            .Select(r => new JsonObject
            {
                ["id"] = (string)r[0]!,
                ["observed_at"] = Core.Outbox.Outbox.Iso(nu),
                ["sessies"] = Convert.ToInt64(r[1], CultureInfo.InvariantCulture),
                ["laatst_gezien"] = Core.Outbox.Outbox.Iso(DateTimeOffset.FromUnixTimeSeconds(Convert.ToInt64(r[2], CultureInfo.InvariantCulture))),
            }).ToList());
    }

    public override JsonObject Status(DateTimeOffset nu)
    {
        var telling = Db.Met(v => Telling(v, "alles", 0, nu));
        telling.Remove("id");
        telling["module"] = ModuleSlug;
        telling["bewaar_dagen"] = BewaarDagen();
        return telling;
    }

    public override int VerwijderGebruiker(Guid gebruiker) =>
        Db.Met(v => JlDatabase.Voer(v, "DELETE FROM playback_sessions WHERE gebruiker = $g", ("$g", gebruiker.ToString("N"))));

    public override int TelGebruiker(Guid gebruiker) =>
        (int)Db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM playback_sessions WHERE gebruiker = $g", ("$g", gebruiker.ToString("N"))));

    public override JsonObject Exporteer()
    {
        var export = base.Exporteer();
        export["sessies"] = Db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(DISTINCT sessie) FROM playback_sessions"));
        return export;
    }

    private static JsonObject Telling(Microsoft.Data.Sqlite.SqliteConnection v, string id, long sinds, DateTimeOffset nu)
    {
        long Tel(string waar) => JlDatabase.Getal(v, "SELECT COUNT(DISTINCT sessie) FROM playback_sessions WHERE gestart >= $s AND " + waar, ("$s", sinds));
        return new JsonObject
        {
            ["id"] = id,
            ["observed_at"] = Core.Outbox.Outbox.Iso(nu),
            ["sessies"] = Tel("1 = 1"),
            ["actief"] = Tel("gestopt IS NULL"),
            ["direct_play"] = Tel("methode = 'direct_play'"),
            ["direct_stream"] = Tel("methode = 'direct_stream'"),
            ["transcodes"] = Tel("methode = 'transcode'"),
            ["hardware_transcodes"] = Tel("methode = 'transcode' AND hardware = 1"),
        };
    }
}
