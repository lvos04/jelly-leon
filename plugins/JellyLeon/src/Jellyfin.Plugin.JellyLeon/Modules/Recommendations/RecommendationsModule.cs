using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Modules;

namespace Jellyfin.Plugin.JellyLeon.Modules.Recommendations;

/// <summary>F2-1 leest alleen bibliotheekmetadata via de server en bewaart geen eigen gegevens.</summary>
internal sealed class RecommendationsModule : IJellyLeonModule
{
    public string Slug => "recommendations";

    public string Naam => "Aanbevelingen";

    public IReadOnlyList<string> ItemTypes => [];

    public IReadOnlyList<string> EventTypes => [];

    public IReadOnlyList<string> JobTypes => [];

    public IReadOnlyList<PersoonsgegevenRegel> Persoonsgegevens => [];

    public IReadOnlyList<JsonObject> Items(string type, DateTimeOffset nu) => [];

    public int VerwijderGebruiker(Guid gebruiker) => 0;

    public int TelGebruiker(Guid gebruiker) => 0;

    public void WisSporen()
    {
    }

    public void ControleerOpslag()
    {
    }

    public JsonObject Exporteer() => new() { ["module"] = Slug, ["schema_version"] = "1.0" };
}
