using System;
using System.Collections.Generic;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>Wie een route mag aanroepen.</summary>
internal enum JlAuth
{
    /// <summary>Alleen de Hub, met een gebruikers- of dienst-JWT (contract §4).</summary>
    Hub,

    /// <summary>Een beheerder met een gewone serversessie (of een API-sleutel van de server).</summary>
    SessieBeheerder,
}

/// <summary>Of een route een Idempotency-Key vraagt.</summary>
internal enum JlIdem
{
    /// <summary>Leesroute.</summary>
    Geen,

    /// <summary>Muterende route: Idempotency-Key verplicht.</summary>
    Verplicht,

    /// <summary>Muterende methode zonder neveneffect; staat met reden in de vrijstellingslijst.</summary>
    Vrijgesteld,
}

/// <summary>Eén route van de plugin: de enige bron voor pipeline, discover, OpenAPI en de statische tests.</summary>
internal sealed record RouteSpec(
    string Id,
    string Methode,
    string Pad,
    JlAuth Auth,
    string? Module,
    JlIdem Idempotentie,
    string Samenvatting,
    string AntwoordSchema,
    string? VerzoekSchema = null,
    bool IfMatch = false,
    string? Vrijstelling = null)
{
    public bool HeeftBody => VerzoekSchema is not null;
}

/// <summary>De routetabel van de ene plugin (ADR-0016): elke route precies één keer.</summary>
internal static class RouteTable
{
    public static readonly IReadOnlyList<RouteSpec> Alle =
    [
        new("connector.discover", "GET", "/connector/v1/discover", JlAuth.Hub, null, JlIdem.Geen, "Connector: wat Jelly Leon aanbiedt", "Discover"),
        new("connector.health", "GET", "/connector/v1/health", JlAuth.Hub, null, JlIdem.Geen, "Connector: gezondheid (totaal = slechtste check)", "Health"),
        new("connector.items", "GET", "/connector/v1/items", JlAuth.Hub, null, JlIdem.Geen, "Connector: items van één type (alleen aantallen en ondoorzichtige ID's)", "ItemsPagina"),
        new("connector.events", "GET", "/connector/v1/events", JlAuth.Hub, null, JlIdem.Geen, "Connector: outbox van Jelly Leon (cursor)", "EventsPagina"),
        new("connector.evidence", "GET", "/connector/v1/evidence/{id}", JlAuth.Hub, null, JlIdem.Geen, "Connector: bewijs (nog niet beschikbaar, 501)", "Fout"),
        new("connector.propose", "POST", "/connector/v1/propose", JlAuth.Hub, null, JlIdem.Vrijgesteld, "Connector: niet beschikbaar (501)", "Fout", Vrijstelling: "geeft altijd 501 capability_unavailable (contract §5)"),
        new("connector.apply", "POST", "/connector/v1/apply", JlAuth.Hub, null, JlIdem.Vrijgesteld, "Connector: niet beschikbaar (501)", "Fout", Vrijstelling: "geeft altijd 501 capability_unavailable (contract §5)"),
        new("connector.rollback", "POST", "/connector/v1/rollback", JlAuth.Hub, null, JlIdem.Vrijgesteld, "Connector: niet beschikbaar (501)", "Fout", Vrijstelling: "geeft altijd 501 capability_unavailable (contract §5)"),
        new("hublink.get", "GET", "/media/v1/hub-link", JlAuth.SessieBeheerder, null, JlIdem.Geen, "Hub-koppeling: status en vingerafdruk van de gepinde sleutelset", "HubLink"),
        new("hublink.verify", "POST", "/media/v1/hub-link/verify", JlAuth.SessieBeheerder, null, JlIdem.Vrijgesteld, "Hub-koppeling: vingerafdruk van een geplakte sleutelset berekenen (wijzigt niets)", "HubLinkVerify", "HubLinkVerifyVerzoek", Vrijstelling: "…/verify zonder neveneffect (contract §5)"),
        new("hublink.put", "PUT", "/media/v1/hub-link", JlAuth.SessieBeheerder, null, JlIdem.Verplicht, "Hub-koppeling: sleutelset pinnen na het overtikken van de vingerafdruk", "HubLink", "HubLinkVerzoek"),
        new("hublink.delete", "DELETE", "/media/v1/hub-link", JlAuth.SessieBeheerder, null, JlIdem.Verplicht, "Hub-koppeling: pin verwijderen (daarna not_linked)", "HubLink"),
        new("modules.list", "GET", "/media/v1/modules", JlAuth.SessieBeheerder, null, JlIdem.Geen, "Modules: lijst met schakelaars", "Modules"),
        new("modules.put", "PUT", "/media/v1/modules/{slug}", JlAuth.SessieBeheerder, null, JlIdem.Verplicht, "Modules: één module aan- of uitzetten", "Modules", "ModuleVerzoek", IfMatch: true),
        new("privacy.register", "GET", "/media/v1/privacy/register", JlAuth.SessieBeheerder, null, JlIdem.Geen, "Register van persoonsgegevens per module", "PrivacyRegister"),
        new("devices.status", "GET", "/media/v1/devices/status", JlAuth.SessieBeheerder, "devices", JlIdem.Geen, "Devices: status (aantallen)", "ModuleStatus"),
        new("devices.settings.get", "GET", "/media/v1/devices/settings", JlAuth.SessieBeheerder, "devices", JlIdem.Geen, "Devices: instellingen van de module", "ModuleInstellingen"),
        new("devices.settings.put", "PUT", "/media/v1/devices/settings", JlAuth.SessieBeheerder, "devices", JlIdem.Verplicht, "Devices: instellingen wijzigen", "ModuleInstellingen", "ModuleInstellingenVerzoek", IfMatch: true),
        new("quality.status", "GET", "/media/v1/quality/status", JlAuth.SessieBeheerder, "quality", JlIdem.Geen, "Quality: status (aantallen)", "ModuleStatus"),
        new("quality.settings.get", "GET", "/media/v1/quality/settings", JlAuth.SessieBeheerder, "quality", JlIdem.Geen, "Quality: instellingen van de module", "ModuleInstellingen"),
        new("quality.settings.put", "PUT", "/media/v1/quality/settings", JlAuth.SessieBeheerder, "quality", JlIdem.Verplicht, "Quality: instellingen wijzigen", "ModuleInstellingen", "ModuleInstellingenVerzoek", IfMatch: true),
    ];

    public static RouteSpec Zoek(string id) =>
        Alle.FirstOrDefault(r => r.Id == id) ?? throw new InvalidOperationException("Onbekende route-ID: " + id);
}
