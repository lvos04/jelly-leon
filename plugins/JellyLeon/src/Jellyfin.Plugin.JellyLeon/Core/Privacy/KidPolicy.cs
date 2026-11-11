using Jellyfin.Data;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Database.Implementations.Enums;

namespace Jellyfin.Plugin.JellyLeon.Core.Privacy;

/// <summary>De signalen waaruit <see cref="KidPolicy"/> afleidt of een account een kinderprofiel is.</summary>
internal readonly record struct KidSignalen(bool HeeftLeeftijdsgrens, int GeblokkeerdeTags, int Toegangsschemas, bool HubRolKind);

/// <summary>
/// De ene gedeelde <c>IsKid</c> (B03-010). Zolang BG-03 open staat geldt de breedste, veiligste regel (a): elk account
/// met een leeftijdsgrens, geblokkeerde tags of een toegangsschema is een kind; de Hub-rol kind wint altijd.
/// </summary>
internal static class KidPolicy
{
    public static bool IsKid(KidSignalen s) =>
        s.HubRolKind || s.HeeftLeeftijdsgrens || s.GeblokkeerdeTags > 0 || s.Toegangsschemas > 0;

    public static bool IsKid(User gebruiker) => IsKid(Signalen(gebruiker));

    public static KidSignalen Signalen(User gebruiker) => new(
        gebruiker.MaxParentalRatingScore.HasValue,
        gebruiker.GetPreference(PreferenceKind.BlockedTags).Length,
        gebruiker.AccessSchedules?.Count ?? 0,
        false);
}
