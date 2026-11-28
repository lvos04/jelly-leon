using System;
using System.Collections.Generic;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>Wie een route mag aanroepen.</summary>
internal enum JlAuth
{
    /// <summary>Alleen de Hub, met een gebruikers- of dienst-JWT (contract §4).</summary>
    Hub,

    /// <summary>Een persoonlijke sessie, ook voor een gewone kijker.</summary>
    GebruikersSessie,

    /// <summary>Een beheerder met een gewone serversessie (of een API-sleutel van de server).</summary>
    SessieBeheerder,

    /// <summary>Een beheerder met een eigen gebruikerssessie om een kinderprofiel te beoordelen.</summary>
    PersoonlijkeBeheerder,
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
    string? Vrijstelling = null,
    string? WisModule = null,
    string? ModuleParameter = null)
{
    public bool HeeftBody => VerzoekSchema is not null;

    public string? ActieveModule(string canoniekPad)
    {
        if (ModuleParameter is null)
        {
            return Module;
        }

        var delen = canoniekPad.Split('/');
        var sjabloon = Pad.Split('/');
        var positie = Array.IndexOf(sjabloon, "{" + ModuleParameter + "}");
        return delen.Length == sjabloon.Length && positie >= 0 ? delen[positie] : string.Empty;
    }

    // MVC vergelijkt de vaste delen hoofdletterongevoelig. Parameterwaarden behouden hun eigen identiteit.
    public string CanoniekPad(string pad)
    {
        var zonderSlash = pad.TrimEnd('/');
        if (string.Equals(zonderSlash, Pad, StringComparison.OrdinalIgnoreCase))
        {
            return Pad;
        }

        var delen = zonderSlash.Split('/');
        var sjabloon = Pad.Split('/');
        if (delen.Length != sjabloon.Length)
        {
            return pad;
        }

        for (var i = 0; i < delen.Length; i++)
        {
            if (sjabloon[i].StartsWith('{'))
            {
                continue;
            }

            if (!string.Equals(delen[i], sjabloon[i], StringComparison.OrdinalIgnoreCase))
            {
                return pad;
            }

            delen[i] = sjabloon[i];
        }

        return string.Join('/', delen);
    }
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
        new("hublink.get", "GET", "/media/v1/hub-link", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Geen, "Hub-koppeling: status en vingerafdruk van de gepinde sleutelset", "HubLink"),
        new("hublink.verify", "POST", "/media/v1/hub-link/verify", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Vrijgesteld, "Hub-koppeling: vingerafdruk van een geplakte sleutelset berekenen (wijzigt niets)", "HubLinkVerify", "HubLinkVerifyVerzoek", Vrijstelling: "…/verify zonder neveneffect (contract §5)"),
        new("hublink.put", "PUT", "/media/v1/hub-link", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Verplicht, "Hub-koppeling: sleutelset pinnen na het overtikken van de vingerafdruk", "HubLink", "HubLinkVerzoek"),
        new("hublink.delete", "DELETE", "/media/v1/hub-link", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Verplicht, "Hub-koppeling: pin verwijderen (daarna not_linked)", "HubLink"),
        new("modules.list", "GET", "/media/v1/modules", JlAuth.SessieBeheerder, null, JlIdem.Geen, "Modules: lijst met schakelaars", "Modules"),
        new("modules.export", "GET", "/media/v1/modules/{slug}/export", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Geen, "Downloadt de overdraagbare modulebundel", "ModuleBundel", ModuleParameter: "slug"),
        new("modules.import.preview", "POST", "/media/v1/modules/{slug}/import/preview", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Vrijgesteld, "Toont de aantallen en de inhoudshash vóór herstel", "ModuleImportVoorbeeld", "ModuleBundel", Vrijstelling: "tijdelijk importvoorbeeld zonder wijzigingen aan de herstelgegevens", ModuleParameter: "slug"),
        new("modules.import.apply", "POST", "/media/v1/modules/{slug}/import/apply", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Verplicht, "Herstelt het bevestigde modulevoorbeeld met een voorafgaande databasekopie", "ModuleWisResultaat", "SegmentHash", ModuleParameter: "slug"),
        new("modules.put", "PUT", "/media/v1/modules/{slug}", JlAuth.SessieBeheerder, null, JlIdem.Verplicht, "Modules: één module aan- of uitzetten", "Modules", "ModuleVerzoek", IfMatch: true),
        new("privacy.register", "GET", "/media/v1/privacy/register", JlAuth.SessieBeheerder, null, JlIdem.Geen, "Register van persoonsgegevens per module", "PrivacyRegister"),
        new("privacy.kid.get", "GET", "/media/v1/privacy/kid-profiles/{id}", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Geen, "Voorstel en effectieve kinderstatus van het gekozen account", "Kinderprofiel"),
        new("privacy.kid.confirm", "POST", "/media/v1/privacy/kid-profiles/confirm", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Verplicht, "Bevestig het gekozen account als kind of volwassene", "Kinderprofiel", "KinderprofielBevestiging", IfMatch: true),
        new("planner.status", "GET", "/media/v1/planner", JlAuth.SessieBeheerder, null, JlIdem.Geen, "Planner: mag er batchwerk draaien en waarom niet (aantallen en vaste woorden)", "Planner"),
        new("watch.capabilities", "GET", "/media/v1/watch/capabilities", JlAuth.GebruikersSessie, "watch", JlIdem.Geen, "Beschikbare Watch Together-functies", "WatchCapabilities"),
        new("watch.groups", "GET", "/media/v1/watch/groups", JlAuth.GebruikersSessie, "watch", JlIdem.Geen, "Zichtbare SyncPlay-groepen", "WatchGroepen"),
        new("watch.diagnostics", "GET", "/media/v1/watch/groups/{id}/diagnostics", JlAuth.GebruikersSessie, "watch", JlIdem.Geen, "Diagnose voor een groepslid of beheerder", "WatchDiagnose"),
        new("watch.purge", "POST", "/media/v1/watch/admin/purge", JlAuth.PersoonlijkeBeheerder, "watch", JlIdem.Verplicht, "Eigen Watch Together-gegevens en modulegeheim wissen", "WatchGewist", "WatchWisVerzoek"),
        new("devices.export", "GET", "/media/v1/devices/export", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Geen, "Devices exporteren en de opgeslagen JSON teruglezen", "ModuleExport"),
        new("devices.purge", "POST", "/media/v1/devices/data/purge", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Verplicht, "Devices wissen na verificatie van de actuele export van hoogstens 24 uur oud", "ModuleWisResultaat", "ModuleWisVerzoek", WisModule: "devices"),
        new("devices.status", "GET", "/media/v1/devices/status", JlAuth.SessieBeheerder, "devices", JlIdem.Geen, "Devices: status (aantallen)", "ModuleStatus"),
        new("devices.settings.get", "GET", "/media/v1/devices/settings", JlAuth.SessieBeheerder, "devices", JlIdem.Geen, "Devices: instellingen van de module", "ModuleInstellingen"),
        new("devices.settings.put", "PUT", "/media/v1/devices/settings", JlAuth.SessieBeheerder, "devices", JlIdem.Verplicht, "Devices: instellingen wijzigen", "ModuleInstellingen", "ModuleInstellingenVerzoek", IfMatch: true),
        new("segments.item", "GET", "/media/v1/segments/{itemId}", JlAuth.GebruikersSessie, "segments", JlIdem.Geen, "Leest de gepubliceerde set of de kandidaatset", "SegmentView"),
        new("segments.publication", "PUT", "/media/v1/segments/publication", JlAuth.PersoonlijkeBeheerder, "segments", JlIdem.Verplicht, "Toont of bevestigt een publicatiewijziging", "SegmentPublicatie", "SegmentPublicatieVerzoek"),
        new("segments.status", "GET", "/media/v1/segments/status", JlAuth.PersoonlijkeBeheerder, "segments", JlIdem.Geen, "Leest de module- en mountstatus", "SegmentStatus"),
        new("segments.export", "GET", "/media/v1/segments/export", JlAuth.PersoonlijkeBeheerder, "segments", JlIdem.Geen, "Exporteert de eigen segmentgegevens", "SegmentBundel"),
        new("segments.import.preview", "POST", "/media/v1/segments/import/preview", JlAuth.PersoonlijkeBeheerder, "segments", JlIdem.Vrijgesteld, "Controleert een herstelbundel", "SegmentImportVoorbeeld", "SegmentBundel", Vrijstelling: "tijdelijk importvoorbeeld zonder wijzigingen aan de herstelgegevens"),
        new("segments.import.apply", "POST", "/media/v1/segments/import/apply", JlAuth.PersoonlijkeBeheerder, "segments", JlIdem.Verplicht, "Voegt gecontroleerde gegevens toe", "SegmentImportResultaat", "SegmentHash"),
        new("segments.orphans", "GET", "/media/v1/segments/orphans", JlAuth.PersoonlijkeBeheerder, "segments", JlIdem.Geen, "Telt de wezen", "SegmentWezen"),
        new("segments.orphans.cleanup", "POST", "/media/v1/segments/orphans/cleanup", JlAuth.PersoonlijkeBeheerder, "segments", JlIdem.Verplicht, "Toont of bevestigt opruimen van geëxporteerde wezen", "SegmentOpruiming", "SegmentOpruimVerzoek"),
        new("segments.orphans.unfreeze", "POST", "/media/v1/segments/orphans/unfreeze", JlAuth.PersoonlijkeBeheerder, "segments", JlIdem.Verplicht, "Ontdooit het wezenbeheer met reden", "SegmentOntdooid", "SegmentReden"),
        new("quality.export", "GET", "/media/v1/quality/export", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Geen, "Quality exporteren en de opgeslagen JSON teruglezen", "ModuleExport"),
        new("quality.purge", "POST", "/media/v1/quality/data/purge", JlAuth.PersoonlijkeBeheerder, null, JlIdem.Verplicht, "Quality wissen na verificatie van de actuele export van hoogstens 24 uur oud", "ModuleWisResultaat", "ModuleWisVerzoek", WisModule: "quality"),
        new("quality.status", "GET", "/media/v1/quality/status", JlAuth.SessieBeheerder, "quality", JlIdem.Geen, "Quality: status (aantallen)", "ModuleStatus"),
        new("quality.settings.get", "GET", "/media/v1/quality/settings", JlAuth.SessieBeheerder, "quality", JlIdem.Geen, "Quality: instellingen van de module", "ModuleInstellingen"),
        new("quality.settings.put", "PUT", "/media/v1/quality/settings", JlAuth.SessieBeheerder, "quality", JlIdem.Verplicht, "Quality: instellingen wijzigen", "ModuleInstellingen", "ModuleInstellingenVerzoek", IfMatch: true),
    ];

    public static RouteSpec Zoek(string id) =>
        Alle.FirstOrDefault(r => r.Id == id) ?? throw new InvalidOperationException("Onbekende route-ID: " + id);
}
