using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;

namespace Jellyfin.Plugin.JellyLeon.Core.Planner;

/// <summary>
/// Stroomonderbreker voor leesfouten (plan §10.7, besluit Q8): drie verschillende bestanden met een leesfout binnen een
/// uur zetten al het batchwerk stil. Hij gaat niet vanzelf weer dicht; alleen een beheerder herstelt hem.
/// </summary>
internal sealed class LeesfoutBreker
{
    /// <summary>Aantal verschillende bestanden dat de onderbreker opent.</summary>
    public const int Drempel = 3;

    /// <summary>Venster in minuten waarin de fouten moeten vallen.</summary>
    public const int VensterMinuten = 60;

    private readonly object _slot = new();
    private readonly Dictionary<string, DateTimeOffset> _fouten = new(StringComparer.Ordinal);
    private readonly Outbox.Outbox? _outbox;
    private DateTimeOffset? _openSinds;
    private DateTimeOffset? _eersteFout;
    private int _bestanden;

    public LeesfoutBreker(Outbox.Outbox? outbox = null)
    {
        _outbox = outbox;
    }

    /// <summary>Gets a value indicating whether de onderbreker open staat (dan draait er geen batch).</summary>
    public bool Open
    {
        get
        {
            lock (_slot)
            {
                return _openSinds is not null;
            }
        }
    }

    /// <summary>
    /// Meldt één leesfout. <paramref name="bestandSleutel"/> is een ondoorzichtige sleutel (vingerafdruk), nooit een pad
    /// of titel. Geeft <c>true</c> als deze melding de onderbreker opent.
    /// </summary>
    public bool Meld(string bestandSleutel, DateTimeOffset nu)
    {
        JsonObject? payload = null;
        lock (_slot)
        {
            if (_openSinds is not null)
            {
                return false;
            }

            var grens = nu - TimeSpan.FromMinutes(VensterMinuten);
            foreach (var oud in _fouten.Where(f => f.Value < grens).Select(f => f.Key).ToList())
            {
                _fouten.Remove(oud);
            }

            _fouten[bestandSleutel] = nu;
            if (_fouten.Count < Drempel)
            {
                return false;
            }

            _openSinds = nu;
            _eersteFout = _fouten.Values.Min();
            _bestanden = _fouten.Count;
            payload = new JsonObject
            {
                ["files"] = _bestanden,
                ["breaker"] = true,
                ["first_at"] = Outbox.Outbox.Iso(_eersteFout.Value),
            };
        }

        // Buiten het slot: de outbox heeft een eigen slot. Lukt het melden niet, dan blijft de onderbreker toch open.
        try
        {
            _outbox?.Meld("core", "media.storage.read_failed", "storage", "media", payload);
        }
        catch (JlException)
        {
            // Opslag niet beschikbaar: de health-check "database" meldt dat al.
        }

        return true;
    }

    /// <summary>Handmatig herstel door een beheerder; de telling begint opnieuw.</summary>
    public void Herstel()
    {
        lock (_slot)
        {
            _openSinds = null;
            _eersteFout = null;
            _bestanden = 0;
            _fouten.Clear();
        }
    }

    public JsonObject Status()
    {
        lock (_slot)
        {
            return new JsonObject
            {
                ["open"] = _openSinds is not null,
                ["open_sinds"] = _openSinds is DateTimeOffset open ? Outbox.Outbox.Iso(open) : null,
                ["bestanden"] = _openSinds is null ? _fouten.Count : _bestanden,
                ["drempel"] = Drempel,
                ["venster_minuten"] = VensterMinuten,
            };
        }
    }
}
