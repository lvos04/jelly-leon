using System.Collections.Generic;
using MediaBrowser.Model.Plugins;

namespace Jellyfin.Plugin.JellyLeon.Configuration;

/// <summary>Schakelaar van één module. Standaard uit.</summary>
public class ModuleSwitch
{
    /// <summary>Gets or sets a value indicating whether de module aan staat.</summary>
    public bool Enabled { get; set; }
}

/// <summary>De module staat standaard uit. Na inschakelen doet de lokale Similar-provider mee.</summary>
public sealed class RecommendationsOptions : ModuleSwitch
{
    /// <summary>Gets or sets de herkenning van anime binnen de toegankelijke bibliotheken.</summary>
    public AnimeOptions Anime { get; set; } = new();

    /// <summary>Gets or sets de afzonderlijke schakelaar voor Meer zoals dit.</summary>
    public ModuleSwitch Similar { get; set; } = new() { Enabled = true };
}

/// <summary>Herkenning van anime voor de klassieke aanbevelingen.</summary>
public sealed class AnimeOptions
{
    /// <summary>Gets or sets de als anime gemarkeerde bibliotheken.</summary>
    public System.Guid[] LibraryIds { get; set; } = [];

    /// <summary>Gets or sets de genrenamen die anime aanduiden.</summary>
    public string[] GenreNames { get; set; } = ["Anime"];
}

/// <summary>Instellingen voor Watch Together. Een ingestelde gast vereist de conservatieve zelftest.</summary>
public class WatchTogetherOptions : ModuleSwitch
{
    /// <summary>Gets or sets de door de beheerder aangewezen gastaccounts.</summary>
    public System.Guid[] GuestUserIds { get; set; } = [];

    /// <summary>Gets or sets de bewaartermijn van beëindigde groepen in uren.</summary>
    public int GroupRetentionHours { get; set; } = 6;
}

/// <summary>Instellingen van de MediaGuard-viewerclient (plan §10.5). Nooit een sleutel: die beheert de Hub (BG-04).</summary>
public class MediaGuardOptions
{
    /// <summary>Gets or sets het aantal seconden tussen twee peilingen van dezelfde route.</summary>
    public int PollSeconds { get; set; } = 20;

    /// <summary>Gets or sets het aantal minuten tussen twee controles van rol en koppeling.</summary>
    public int LinkCheckMinutes { get; set; } = 60;
}

/// <summary>Instellingen van de batchplanner (ADR-0018). De pauze bij afspelen is niet uit te zetten.</summary>
public class PlannerOptions
{
    /// <summary>Gets or sets het beginuur van het batchvenster (lokale tijd, 0–23).</summary>
    public int WindowStartHour { get; set; } = 23;

    /// <summary>Gets or sets het einduur van het batchvenster (lokale tijd, 0–23).</summary>
    public int WindowEndHour { get; set; } = 7;

    /// <summary>Gets or sets a value indicating whether batch alleen binnen het venster mag draaien.</summary>
    public bool WindowOnly { get; set; } = true;
}

/// <summary>
/// Configuratie van de Jelly Leon-plugin. Bevat uitsluitend schakelaars en instellingen; geheimen en de gepinde
/// Hub-sleutelset staan in de geheimenmap en nooit in dit XML-bestand (plan §10.9).
/// </summary>
public class PluginConfiguration : BasePluginConfiguration
{
    /// <summary>Gets or sets de schakelaar van module Devices.</summary>
    public ModuleSwitch Devices { get; set; } = new();

    /// <summary>Gets or sets de schakelaar van module Quality.</summary>
    public ModuleSwitch Quality { get; set; } = new();

    /// <summary>Gets or sets de instellingen van de module Recommendations.</summary>
    public RecommendationsOptions Recommendations { get; set; } = new();

    /// <summary>Gets or sets de schakelaar voor segmenten.</summary>
    public ModuleSwitch Segments { get; set; } = new();

    /// <summary>Gets or sets de aangewezen volwassen segmenteditors. Het kinderbeleid blijft leidend.</summary>
    public System.Guid[] SegmentEditors { get; set; } = [];
    /// <summary>Gets or sets de Watch Together-schakelaar en gastinstelling.</summary>
    public WatchTogetherOptions WatchTogether { get; set; } = new();

    /// <summary>Gets or sets de instellingen van de MediaGuard-viewerclient.</summary>
    public MediaGuardOptions MediaGuard { get; set; } = new();

    /// <summary>Gets or sets de instellingen van de batchplanner.</summary>
    public PlannerOptions Planner { get; set; } = new();

    /// <summary>Alle schakelaars met hun slug, in vaste volgorde.</summary>
    /// <returns>De paren van slug en schakelaar.</returns>
    internal IEnumerable<(string Slug, ModuleSwitch Schakelaar)> Schakelaars()
    {
        yield return ("devices", Devices ??= new ModuleSwitch());
        yield return ("quality", Quality ??= new ModuleSwitch());
        yield return ("recommendations", Recommendations ??= new RecommendationsOptions());
        yield return ("segments", Segments ??= new ModuleSwitch());
        yield return ("watch", WatchTogether ??= new WatchTogetherOptions());
    }
}
