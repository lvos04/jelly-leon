using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.MediaGuard;

namespace Jellyfin.Plugin.JellyLeon.Core.Budget;

/// <summary>De topologieën van plan §10.8. Zolang D08 (de hardware van de NAS) onbekend is, is dit <see cref="Onbekend"/>.</summary>
internal enum GpuTopologie
{
    /// <summary>Niet vastgesteld: er wordt niets aangenomen.</summary>
    Onbekend,

    /// <summary>Arc A310 en UHD 770.</summary>
    TwoGpu,

    /// <summary>Alleen de Arc A310.</summary>
    A310Only,

    /// <summary>Alleen de UHD 770.</summary>
    Uhd770Only,

    /// <summary>Eén andere GPU.</summary>
    SingleOther,

    /// <summary>Geen GPU.</summary>
    None,
}

/// <summary>Waar batchwerk mag draaien: de CPU of nergens. Een GPU-node krijgt batch in golf 1 nooit.</summary>
internal sealed record BudgetBesluit(string BatchNode, bool GpuVoorBatch, string Reden);

/// <summary>
/// De ene budgetbeslisser (B03-018, plan §10.8): live gaat voor MediaGuard-AV1, dat gaat voor batch. Batch komt nooit op
/// de GPU-lane waarop MediaGuard encodeert, en krijgt vóór D08 (BG-35) helemaal geen GPU. Deze klasse kiest geen lane
/// voor een live sessie (dat is F5, B03-063) en stuurt MediaGuard nooit aan; hij houdt alleen reserveringen bij.
/// </summary>
internal sealed class BudgetBeslisser
{
    /// <summary>Zo lang blijft een lane gereserveerd voor een gepauzeerde sessie (plan §10.8: <c>GroupPauseLaneHoldMinutes</c>).</summary>
    public const int GroupPauseLaneHoldMinutes = 30;

    private readonly object _slot = new();
    private readonly Dictionary<string, (string Node, DateTimeOffset Tot)> _reserveringen = new(StringComparer.Ordinal);

    /// <summary>Gets de topologie; vast <see cref="GpuTopologie.Onbekend"/> tot D08 is vastgesteld.</summary>
    public GpuTopologie Topologie => GpuTopologie.Onbekend;

    public static string Naam(GpuTopologie topologie) => topologie switch
    {
        GpuTopologie.TwoGpu => "two_gpu",
        GpuTopologie.A310Only => "a310_only",
        GpuTopologie.Uhd770Only => "uhd770_only",
        GpuTopologie.SingleOther => "single_other",
        GpuTopologie.None => "none",
        _ => "onbekend",
    };

    /// <summary>Waar mag batch draaien? Nooit op een GPU; op de CPU alleen als MediaGuard gemeten is en zijn CPU-lane vrij is.</summary>
    public static BudgetBesluit VoorBatch(MgBeeld mediaGuard)
    {
        if (mediaGuard.Status != MgStatus.Ok)
        {
            return new BudgetBesluit("geen", false, "mediaguard_niet_gemeten");
        }

        var cpu = mediaGuard.Lanes.FirstOrDefault(l => l.Lane == "cpu");
        if (cpu?.Running is not int bezig)
        {
            return new BudgetBesluit("geen", false, "mediaguard_lanes_onbekend");
        }

        return bezig > 0
            ? new BudgetBesluit("geen", false, "mediaguard_cpu_bezig")
            : new BudgetBesluit("cpu", false, "gpu_niet_voor_batch_tot_d08");
    }

    /// <summary>Houdt een node vast voor een sessiesleutel (ondoorzichtig), of verlengt de reservering.</summary>
    public void Houd(string sessieSleutel, string node, DateTimeOffset nu)
    {
        lock (_slot)
        {
            Ruim(nu);
            _reserveringen[sessieSleutel] = (node, nu.AddMinutes(GroupPauseLaneHoldMinutes));
        }
    }

    public void GeefVrij(string sessieSleutel)
    {
        lock (_slot)
        {
            _reserveringen.Remove(sessieSleutel);
        }
    }

    /// <summary>Het aantal lopende reserveringen per node.</summary>
    public IReadOnlyDictionary<string, int> Reserveringen(DateTimeOffset nu)
    {
        lock (_slot)
        {
            Ruim(nu);
            return _reserveringen.Values.GroupBy(r => r.Node, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.Count(), StringComparer.Ordinal);
        }
    }

    public JsonObject Status(MgBeeld mediaGuard, DateTimeOffset nu)
    {
        var besluit = VoorBatch(mediaGuard);
        var reserveringen = new JsonObject();
        foreach (var (node, aantal) in Reserveringen(nu).OrderBy(r => r.Key, StringComparer.Ordinal))
        {
            reserveringen[node] = aantal;
        }

        return new JsonObject
        {
            ["topologie"] = Naam(Topologie),
            ["batch_node"] = besluit.BatchNode,
            ["gpu_voor_batch"] = besluit.GpuVoorBatch,
            ["reden"] = besluit.Reden,
            ["reserveringen"] = reserveringen,
            ["hold_minuten"] = GroupPauseLaneHoldMinutes,
        };
    }

    private void Ruim(DateTimeOffset nu)
    {
        foreach (var verlopen in _reserveringen.Where(r => r.Value.Tot <= nu).Select(r => r.Key).ToList())
        {
            _reserveringen.Remove(verlopen);
        }
    }
}
