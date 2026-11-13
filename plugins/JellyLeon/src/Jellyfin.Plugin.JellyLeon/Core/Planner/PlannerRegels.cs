using System;
using System.Collections.Generic;
using Jellyfin.Plugin.JellyLeon.Core.Media;
using Jellyfin.Plugin.JellyLeon.Core.MediaGuard;

namespace Jellyfin.Plugin.JellyLeon.Core.Planner;

/// <summary>Kostenklasse van een jobtype (plan §10.7). Onbekend werk telt als zwaar.</summary>
internal enum Kostenklasse
{
    /// <summary>Kost niets: leest alleen wat de server al weet, opent geen mediabestand.</summary>
    Geen,

    /// <summary>Licht rekenwerk in het serverproces, zonder mediabestand te lezen.</summary>
    CpuLicht,

    /// <summary>Leest of analyseert mediabestanden: alleen via de werker, hooguit één tegelijk.</summary>
    Zwaar,
}

/// <summary>Alles wat de planner meet voordat hij beslist. Onbekend is nooit "in orde".</summary>
internal sealed record PlannerStand(
    DateTimeOffset Nu,
    TimeOnly LokaleTijd,
    int Sessies,
    int SoftwareTranscodes,
    DateTimeOffset RustSinds,
    MgStatus MediaGuard,
    bool MediaGuardGepauzeerd,
    int? MediaGuardCpuBezig,
    MountCheck.Uitkomst Media,
    bool WerkerKlaar,
    bool LeesfoutenOpen,
    long? CgroupMargeBytes);

/// <summary>De uitkomst: mag zwaar werk, mag licht werk, en alle redenen waarom niet (vaste woorden).</summary>
internal sealed record PlannerBesluit(bool Zwaar, bool Licht, string Reden, IReadOnlyList<string> Redenen);

/// <summary>
/// De regels van de ene planner (B03-018, plan §10.7), zonder toestand en zonder klok: dezelfde stand geeft altijd
/// hetzelfde besluit. Modules beslissen hier niets; zij leveren alleen jobtype, kostenklasse en prioriteit.
/// </summary>
internal static class PlannerRegels
{
    /// <summary>Hooguit één zware taak tegelijk.</summary>
    public const int MaxZwareTaken = 1;

    /// <summary>Hooguit twee threads voor al het batchwerk samen.</summary>
    public const int MaxThreads = 2;

    /// <summary>Hooguit 1 GiB werkgeheugen voor al het batchwerk samen.</summary>
    public const long MaxBatchBytes = 1024L * 1024 * 1024;

    /// <summary>Een zware taak staat binnen zoveel seconden stil na het begin van een kijksessie.</summary>
    public const int PauzeBinnenSeconden = 5;

    /// <summary>Pas na zoveel minuten zonder kijken gaat batchwerk verder (besluit Q3).</summary>
    public const int HervatNaMinuten = 10;

    /// <summary>Marge die "nu analyseren" van een beheerder eist: <c>memory.max − memory.current</c>.</summary>
    public const long BeheerMargeBytes = 1024L * 1024 * 1024;

    /// <summary>Begin van het nachtvenster (gelijk aan het AV1-venster van MediaGuard), lokale tijd van de server.</summary>
    public static readonly TimeOnly VensterBegin = new(23, 0);

    /// <summary>Einde van het nachtvenster, lokale tijd van de server.</summary>
    public static readonly TimeOnly VensterEinde = new(7, 0);

    public static bool InVenster(TimeOnly lokaal) => lokaal >= VensterBegin || lokaal < VensterEinde;

    /// <summary>De kostenklasse van een jobtype. Wat hier niet staat is zwaar: nooit per ongeluk overdag draaien.</summary>
    public static Kostenklasse Kosten(string jobType) => jobType switch
    {
        "quality.inventory" => Kostenklasse.Geen,
        "rec.rebuild" => Kostenklasse.CpuLicht,
        _ => Kostenklasse.Zwaar,
    };

    public static bool Mag(PlannerBesluit besluit, Kostenklasse klasse) => klasse switch
    {
        Kostenklasse.Geen => true,
        Kostenklasse.CpuLicht => besluit.Licht,
        _ => besluit.Zwaar,
    };

    /// <summary>
    /// Beslist. <paramref name="beheerderNu"/> is het uitdrukkelijke verzoek "nu analyseren" van een beheerder: de enige
    /// uitzondering op "elke kijksessie pauzeert", en alleen met genoeg geheugenmarge en zonder software-transcode.
    /// </summary>
    public static PlannerBesluit Beslis(PlannerStand stand, bool beheerderNu = false)
    {
        var hard = new List<string>();
        if (stand.LeesfoutenOpen)
        {
            hard.Add("leesfouten");
        }

        if (stand.Media == MountCheck.Uitkomst.Schrijfbaar)
        {
            hard.Add("media_schrijfbaar");
        }
        else if (stand.Media == MountCheck.Uitkomst.Onbekend)
        {
            hard.Add("media_onbekend");
        }

        switch (stand.MediaGuard)
        {
            case MgStatus.Ok:
                if (stand.MediaGuardGepauzeerd)
                {
                    hard.Add("mediaguard_gepauzeerd");
                }

                break;
            case MgStatus.Geweigerd:
                hard.Add("mediaguard_geweigerd");
                break;
            case MgStatus.Onbereikbaar:
                hard.Add("mediaguard_onbereikbaar");
                break;
            default:
                hard.Add("mediaguard_onbekend");
                break;
        }

        if (stand.SoftwareTranscodes > 0)
        {
            hard.Add("software_transcode");
        }

        var kijken = new List<string>();
        var uitzondering = false;
        if (stand.Sessies > 0)
        {
            if (!beheerderNu)
            {
                kijken.Add("actieve_sessie");
            }
            else if (stand.CgroupMargeBytes is not long marge)
            {
                kijken.Add("marge_onbekend");
            }
            else if (marge < BeheerMargeBytes)
            {
                kijken.Add("marge_te_klein");
            }
            else
            {
                uitzondering = true;
            }
        }
        else if (!beheerderNu && stand.Nu - stand.RustSinds < TimeSpan.FromMinutes(HervatNaMinuten))
        {
            kijken.Add("wacht_na_kijken");
        }

        var licht = new List<string>(hard);
        licht.AddRange(kijken);
        var zwaar = new List<string>(licht);
        if (!stand.WerkerKlaar)
        {
            zwaar.Add("werker_niet_beschikbaar");
        }

        if (stand.MediaGuard == MgStatus.Ok)
        {
            if (stand.MediaGuardCpuBezig is not int bezig)
            {
                zwaar.Add("mediaguard_lanes_onbekend");
            }
            else if (bezig > 0)
            {
                zwaar.Add("mediaguard_cpu_bezig");
            }
        }

        if (!beheerderNu && !InVenster(stand.LokaleTijd))
        {
            zwaar.Add("buiten_venster");
        }

        var vrij = uitzondering || beheerderNu ? "beheerder_nu" : "vrij";
        var reden = zwaar.Count > 0 ? zwaar[0] : vrij;
        return new PlannerBesluit(zwaar.Count == 0, licht.Count == 0, reden, zwaar);
    }
}
