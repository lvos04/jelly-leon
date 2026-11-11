namespace Jellyfin.Plugin.JellyLeon.Core.Media;

/// <summary>
/// Stroomonderbreker voor wezen (plan §10.9): verdwijnen er ineens meer dan 5 % of meer dan 50 items, dan bevriest de
/// module haar gegevens (status degraded, incident) in plaats van ze op te ruimen. Nooit automatisch wissen.
/// </summary>
internal static class OrphanBreaker
{
    public const int MaxAantal = 50;
    public const double MaxAandeel = 0.05;

    public static bool MoetBevriezen(int totaal, int wezen) =>
        wezen > MaxAantal || (totaal > 0 && wezen > totaal * MaxAandeel);
}
