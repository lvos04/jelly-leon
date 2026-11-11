using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Media;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Outbox;
using Jellyfin.Plugin.JellyLeon.Core.Storage;

namespace Jellyfin.Plugin.JellyLeon.Core.Connector;

/// <summary>Bron van extra health-checks (werker, MediaGuard, …).</summary>
internal interface IHealthBron
{
    IEnumerable<JsonObject> Checks(DateTimeOffset nu);
}

/// <summary>De mediamappen van de server (voor de koppelcontrole zonder proefschrijven).</summary>
internal interface IMediaMappen
{
    IReadOnlyList<string> Paden();
}

/// <summary>
/// De ene connector van de plugin (contract 1.3 §6): discover, health, items en events. Items en events bevatten
/// alleen aantallen, codes en ondoorzichtige ID's (plan §10.4); een schending wordt een fout, geen lek.
/// </summary>
internal sealed class ConnectorService
{
    public const int MaxAgeSeconds = 900;
    private static readonly string[] _rangorde = ["healthy", "unknown", "degraded", "down"];
    private readonly ModuleRegistry _modules;
    private readonly Outbox.Outbox _outbox;
    private readonly CoreDatabase _core;
    private readonly JlPaths _paden;
    private readonly IMediaMappen _media;
    private readonly IEnumerable<IHealthBron> _bronnen;

    public ConnectorService(ModuleRegistry modules, Outbox.Outbox outbox, CoreDatabase core, JlPaths paden, IMediaMappen media, IEnumerable<IHealthBron> bronnen)
    {
        _modules = modules;
        _outbox = outbox;
        _core = core;
        _paden = paden;
        _media = media;
        _bronnen = bronnen;
    }

    public static JsonObject Check(string naam, string status, DateTimeOffset gemetenOp, JsonNode? detail = null) => new()
    {
        ["name"] = naam,
        ["status"] = status,
        ["observed_at"] = Outbox.Outbox.Iso(gemetenOp),
        ["detail"] = detail,
    };

    public IEnumerable<string> ItemTypes() => new[] { "backups" }.Concat(_modules.Actief.SelectMany(m => m.ItemTypes));

    public JsonObject Discover(DateTimeOffset nu)
    {
        var maxAge = new JsonObject { ["health"] = MaxAgeSeconds };
        var rechten = new JsonArray("health:read", "events:read");
        foreach (var type in ItemTypes())
        {
            maxAge[type] = MaxAgeSeconds;
            rechten.Add("items:" + type + ":read");
        }

        return new JsonObject
        {
            ["app_id"] = "jelly-leon",
            ["source_version"] = ForkInfo.GetMetadata("JellyLeon.ForkVersion"),
            ["schema_version"] = "1.0",
            ["capabilities"] = new JsonArray("read"),
            ["permissions"] = rechten,
            ["limits"] = new JsonObject
            {
                ["max_page_size"] = 200,
                ["max_body_bytes"] = Fouten.MaxBodyBytes,
                ["event_payload_max_bytes"] = Outbox.Outbox.MaxPayloadBytes,
                ["max_age_s"] = maxAge,
            },
            ["timestamp_utc"] = Outbox.Outbox.Iso(nu),
        };
    }

    public JsonObject Health(DateTimeOffset nu)
    {
        var checks = new List<JsonObject> { DatabaseCheck(nu), JobsCheck(nu), MediaCheck(nu) };
        foreach (var module in _modules.Actief)
        {
            try
            {
                module.ControleerOpslag();
                checks.Add(Check("module." + module.Slug, "healthy", nu));
            }
            catch (JlException)
            {
                checks.Add(Check("module." + module.Slug, "down", nu, new JsonObject { ["reden"] = "opslag_onbeschikbaar" }));
            }
        }

        checks.AddRange(_bronnen.SelectMany(b => b.Checks(nu)));
        if (!checks.Any(c => c["name"]!.GetValue<string>() == "worker"))
        {
            // Vaste check van contract §6. Zonder werkerbewaker is de werker alleen "in orde" als geen actieve module
            // er een nodig heeft; anders is de toestand onbekend (nooit gesimuleerd succes).
            var nodig = _modules.Actief.Any(m => m.JobTypes.Count > 0);
            checks.Add(Check("worker", nodig ? "unknown" : "healthy", nu, new JsonObject { ["nodig"] = nodig, ["reden"] = nodig ? "werker_niet_beschikbaar" : "geen_module_met_jobs" }));
        }

        foreach (var check in checks)
        {
            // §6.2: een meting ouder dan max_age telt als onbekend.
            var gemeten = DateTimeOffset.Parse(check["observed_at"]!.GetValue<string>(), CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal);
            if ((nu - gemeten).TotalSeconds > MaxAgeSeconds)
            {
                check["status"] = "unknown";
                check["detail"] = new JsonObject { ["reden"] = "meting_verouderd" };
            }
        }

        var slechtste = checks.Select(c => c["status"]!.GetValue<string>()).MaxBy(s => Array.IndexOf(_rangorde, s)) ?? "unknown";
        var oorzaak = checks.FirstOrDefault(c => c["status"]!.GetValue<string>() == slechtste && slechtste != "healthy");
        return new JsonObject
        {
            ["status"] = slechtste,
            ["observed_at"] = Outbox.Outbox.Iso(nu),
            ["reason_code"] = oorzaak is null ? "ok" : oorzaak["name"]!.GetValue<string>() + "_" + slechtste,
            ["checks"] = new JsonArray(checks.ToArray<JsonNode>()),
        };
    }

    public JsonObject Items(string? type, string? cursor, string? limiet, DateTimeOffset nu)
    {
        var (start, aantal) = Pagina(cursor, limiet, 50);
        if (type is null || !ItemTypes().Contains(type, StringComparer.Ordinal))
        {
            throw Fouten.Validatie(("type", "onbekend_type", "Dit itemtype biedt Jelly Leon niet aan (zie discover)."));
        }

        var alle = type == "backups" ? Backups(nu) : _modules.Actief.First(m => m.ItemTypes.Contains(type)).Items(type, nu);
        foreach (var item in alle)
        {
            if (InhoudsBewaker.EersteOvertreding(item) is { } pad)
            {
                throw new InvalidOperationException("Connector-item bevat een verboden waarde op " + pad + ".");
            }
        }

        var pagina = alle.Skip((int)start).Take(aantal).ToArray<JsonNode>();
        return new JsonObject
        {
            ["type"] = type,
            ["items"] = new JsonArray(pagina),
            ["observed_at"] = Outbox.Outbox.Iso(nu),
            ["next_cursor"] = start + aantal < alle.Count ? (start + aantal).ToString(CultureInfo.InvariantCulture) : null,
        };
    }

    public JsonObject Events(string? cursor, string? limiet)
    {
        var (na, aantal) = Pagina(cursor, limiet, 100);
        var (events, laatste) = _outbox.Lees(na, aantal);
        return new JsonObject
        {
            ["items"] = new JsonArray(events.ToArray()),
            ["next_cursor"] = events.Count > 0 ? laatste.ToString(CultureInfo.InvariantCulture) : cursor,
        };
    }

    private static (long Start, int Aantal) Pagina(string? cursor, string? limiet, int standaard)
    {
        long start = 0;
        var aantal = standaard;
        if (cursor is not null && (cursor.Length > 18 || !long.TryParse(cursor, NumberStyles.None, CultureInfo.InvariantCulture, out start)))
        {
            throw Fouten.Validatie(("cursor", "cursor_ongeldig", "Gebruik de next_cursor van de vorige pagina."));
        }

        if (limiet is not null && (!int.TryParse(limiet, NumberStyles.None, CultureInfo.InvariantCulture, out aantal) || aantal is < 1 or > 200))
        {
            throw Fouten.Validatie(("limit", "bereik", "Verwacht een geheel getal van 1 tot 200."));
        }

        return (start, aantal);
    }

    private JsonObject DatabaseCheck(DateTimeOffset nu)
    {
        try
        {
            _core.Db.Met(v => JlDatabase.Getal(v, "SELECT COUNT(*) FROM outbox"));
            return Check("database", "healthy", nu);
        }
        catch (JlException)
        {
            return Check("database", "down", nu, new JsonObject { ["reden"] = "opslag_onbeschikbaar" });
        }
    }

    private JsonObject JobsCheck(DateTimeOffset nu)
    {
        try
        {
            return _core.Db.Met(v =>
            {
                var wachtrij = JlDatabase.Getal(v, "SELECT COUNT(*) FROM jobs WHERE staat IN ('wacht', 'gepauzeerd')");
                var bezig = JlDatabase.Getal(v, "SELECT COUNT(*) FROM jobs WHERE staat = 'bezig'");
                var klaar = JlDatabase.Scalar(v, "SELECT MAX(klaar) FROM jobs WHERE staat IN ('klaar', 'mislukt')");
                var detail = new JsonObject
                {
                    ["wachtrij"] = wachtrij,
                    ["bezig"] = bezig,
                    ["laatste_job_klaar"] = klaar is null ? null : Outbox.Outbox.Iso(DateTimeOffset.FromUnixTimeSeconds(Convert.ToInt64(klaar, CultureInfo.InvariantCulture))),
                };
                return Check("jobs", "healthy", nu, detail);
            });
        }
        catch (JlException)
        {
            return Check("jobs", "unknown", nu, new JsonObject { ["reden"] = "niet_te_lezen" });
        }
    }

    private JsonObject MediaCheck(DateTimeOffset nu)
    {
        var uitkomsten = _media.Paden().Select(p => MountCheck.Beoordeel(p)).ToList();
        var detail = new JsonObject
        {
            ["mappen"] = uitkomsten.Count,
            ["alleen_lezen"] = uitkomsten.Count(u => u == MountCheck.Uitkomst.AlleenLezen),
            ["schrijfbaar"] = uitkomsten.Count(u => u == MountCheck.Uitkomst.Schrijfbaar),
        };
        if (uitkomsten.Contains(MountCheck.Uitkomst.Schrijfbaar))
        {
            detail["reden"] = "media_schrijfbaar";
            return Check("media_mount", "degraded", nu, detail);
        }

        var allesGoed = uitkomsten.Count > 0 && uitkomsten.All(u => u == MountCheck.Uitkomst.AlleenLezen);
        return Check("media_mount", allesGoed ? "healthy" : "unknown", nu, detail);
    }

    private List<JsonObject> Backups(DateTimeOffset nu)
    {
        var items = new List<JsonObject>();
        foreach (var naam in new[] { "core" }.Concat(_modules.Actief.Select(m => m.Slug)))
        {
            var map = new DirectoryInfo(_paden.ModuleDir(naam));
            var bestanden = map.Exists ? map.GetFiles() : [];
            var kopieen = bestanden.Where(f => f.Name.EndsWith(".bak", StringComparison.Ordinal)).ToList();
            items.Add(new JsonObject
            {
                ["id"] = naam,
                ["observed_at"] = Outbox.Outbox.Iso(nu),
                ["opslag_bytes"] = bestanden.Sum(f => f.Length),
                ["migratiekopieen"] = kopieen.Count,
                ["laatste_migratiekopie"] = kopieen.Count == 0 ? null : Outbox.Outbox.Iso(kopieen.Max(f => f.LastWriteTimeUtc)),
                ["dekking"] = "onbekend",
            });
        }

        return items;
    }
}
