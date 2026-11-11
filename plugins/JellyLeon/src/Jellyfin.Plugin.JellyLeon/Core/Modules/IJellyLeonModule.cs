using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Jellyfin.Plugin.JellyLeon.Core.Modules;

/// <summary>Eén regel van het register van persoonsgegevens (plan §10.9).</summary>
internal sealed record PersoonsgegevenRegel(string Module, string Tabel, string Gegeven, string Doel, string Bewaartermijn);

/// <summary>
/// Een module van de ene plugin (ADR-0016): eigen schakelaar, eigen SQLite-bestand, eigen routes, itemtypes, events
/// en jobtypes. Staat de module uit, dan bestaan die delen voor de buitenwereld niet.
/// </summary>
internal interface IJellyLeonModule
{
    /// <summary>Gets de vaste korte naam (kleine letters), ook de mapnaam onder <c>jelly-leon/</c>.</summary>
    string Slug { get; }

    string Naam { get; }

    IReadOnlyList<string> ItemTypes { get; }

    IReadOnlyList<string> EventTypes { get; }

    IReadOnlyList<string> JobTypes { get; }

    IReadOnlyList<PersoonsgegevenRegel> Persoonsgegevens { get; }

    /// <summary>Connector-items van één type: alleen aantallen en ondoorzichtige ID's, elk met <c>observed_at</c>.</summary>
    IReadOnlyList<JsonObject> Items(string type, DateTimeOffset nu);

    /// <summary>Verwijdert alles van één gebruiker uit de eigen opslag; geeft het aantal verwijderde rijen.</summary>
    int VerwijderGebruiker(Guid gebruiker);

    /// <summary>Telt de rijen die nog naar de gebruiker verwijzen (bewijs voor de UserDeleted-test).</summary>
    int TelGebruiker(Guid gebruiker);

    /// <summary>Opent de eigen opslag; gooit bij een fout (voor de health-check).</summary>
    void ControleerOpslag();

    /// <summary>Export van de eigen gegevens zonder persoonsgegevens en zonder geheimen.</summary>
    JsonObject Exporteer();
}
