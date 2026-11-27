using System;
using Jellyfin.Data;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Database.Implementations.Enums;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using MediaBrowser.Controller.Library;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.JellyLeon.Core.Privacy;

/// <summary>De drie Jellyfin-signalen voor een automatisch voorstel.</summary>
internal readonly record struct KidSignalen(bool HeeftLeeftijdsgrens, int GeblokkeerdeTags, int Toegangsschemas)
{
    public bool SteltKindVoor => HeeftLeeftijdsgrens || GeblokkeerdeTags > 0 || Toegangsschemas > 0;
}

internal sealed record Kinderprofiel(string Status)
{
    public const string Geen = "geen_voorstel";
    public const string Voorgesteld = "voorgesteld";
    public const string Kind = "bevestigd_kind";
    public const string Volwassene = "bevestigd_volwassene";

    public bool IsKid => Status switch
    {
        Voorgesteld or Kind => true,
        Geen or Volwassene => false,
        _ => throw Fouten.OpslagOnbeschikbaar(),
    };

    public string Etag => "\"" + Status + "\"";
}

/// <summary>BG-03. Een voorstel beschermt het account totdat een beheerder het als kind of volwassene bevestigt.</summary>
internal sealed class KidPolicy(CoreDatabase core, PrivacyService privacy, IUserManager gebruikers)
{
    public static KidSignalen Signalen(User gebruiker) => new(
        gebruiker.MaxParentalRatingScore.HasValue,
        gebruiker.GetPreference(PreferenceKind.BlockedTags).Length,
        gebruiker.AccessSchedules?.Count ?? 0);

    public bool IsKid(User gebruiker, bool hubRolKind = false)
    {
        if (hubRolKind)
        {
            return true;
        }

        var account = gebruiker.Id;
        var sleutel = privacy.Pseudoniem(account);
        return core.Kinderprofielen.Met(v =>
        {
            var profiel = Lees(v, sleutel);
            // Controleer het eerste voorstel tegen het actuele account onder hetzelfde slot als UserDeleted.
            return profiel.Status == Kinderprofiel.Geen && Signalen(gebruiker).SteltKindVoor
                ? Beoordeel(v, sleutel, account, profiel).IsKid
                : profiel.IsKid;
        });
    }

    public Kinderprofiel VoorAccount(Guid account)
    {
        var sleutel = privacy.Pseudoniem(account);
        return core.Kinderprofielen.Met(v => Beoordeel(v, sleutel, account, Lees(v, sleutel)));
    }

    public Kinderprofiel Bevestig(Guid account, bool kind, string ifMatch)
    {
        var sleutel = privacy.Pseudoniem(account);
        var nieuw = new Kinderprofiel(kind ? Kinderprofiel.Kind : Kinderprofiel.Volwassene);
        return core.Kinderprofielen.Met(v =>
        {
            var huidig = Lees(v, sleutel);
            if (huidig.Status == Kinderprofiel.Geen || gebruikers.GetUserById(account) is null)
            {
                throw Fouten.NietGevonden();
            }

            if (huidig.Etag != ifMatch || JlDatabase.Voer(v,
                "UPDATE kinderprofielen SET status=$nieuw WHERE account=$account AND status=$oud",
                ("$nieuw", nieuw.Status), ("$account", sleutel), ("$oud", huidig.Status)) != 1)
            {
                throw Fouten.PreconditieMislukt(Lees(v, sleutel).Etag);
            }

            return nieuw;
        });
    }

    private static Kinderprofiel Lees(SqliteConnection verbinding, string sleutel) =>
        new((string?)JlDatabase.Scalar(verbinding, "SELECT status FROM kinderprofielen WHERE account=$account", ("$account", sleutel)) ?? Kinderprofiel.Geen);

    private Kinderprofiel Beoordeel(SqliteConnection verbinding, string sleutel, Guid account, Kinderprofiel huidig)
    {
        var gebruiker = gebruikers.GetUserById(account) ?? throw Fouten.NietGevonden();
        if (huidig.Status != Kinderprofiel.Geen || !Signalen(gebruiker).SteltKindVoor)
        {
            return huidig;
        }

        JlDatabase.Voer(verbinding, "INSERT INTO kinderprofielen(account, status) VALUES($account, $status) ON CONFLICT(account) DO NOTHING",
            ("$account", sleutel), ("$status", Kinderprofiel.Voorgesteld));
        return Lees(verbinding, sleutel);
    }
}
