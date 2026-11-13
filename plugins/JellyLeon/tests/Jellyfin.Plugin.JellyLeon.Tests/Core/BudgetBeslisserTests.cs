using System;
using System.Linq;
using Jellyfin.Plugin.JellyLeon.Core.Budget;
using Jellyfin.Plugin.JellyLeon.Core.MediaGuard;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// De budgetbeslisser zoals hij nu is (B03-018, stand na ronde 3; ADR-0035). Legt het bestaande gedrag vast: batch krijgt
/// nooit een GPU, de CPU alleen als MediaGuard gemeten is en zijn CPU-lane vrij is, en de topologie staat vast op
/// "onbekend" (D08). De regels G1–G10 en de live-bezetting horen bij S-G1-38 en zijn hier niet getest.
/// </summary>
public sealed class BudgetBeslisserTests
{
    private static readonly DateTimeOffset _nu = new(2026, 11, 11, 23, 30, 0, TimeSpan.Zero);

    private static MgBeeld Gemeten(params MgLane[] lanes) =>
        new(MgStatus.Ok, "gemeten", _nu, true, lanes, false, true, "emby");

    [Fact]
    public void Topologie_StaatVastOpOnbekendTotD08()
    {
        var budget = new BudgetBeslisser();
        Assert.Equal(GpuTopologie.Onbekend, budget.Topologie);
        Assert.Equal("onbekend", BudgetBeslisser.Naam(budget.Topologie));
        Assert.Equal("onbekend", budget.Status(Gemeten(new MgLane("cpu", 0, 2, false)), _nu)["topologie"]!.GetValue<string>());
    }

    [Theory]
    [InlineData("Onbekend", "onbekend")]
    [InlineData("TwoGpu", "two_gpu")]
    [InlineData("A310Only", "a310_only")]
    [InlineData("Uhd770Only", "uhd770_only")]
    [InlineData("SingleOther", "single_other")]
    [InlineData("None", "none")]
    public void Topologie_HeeftEenVastWoordPerStand(string topologie, string woord) =>
        Assert.Equal(woord, BudgetBeslisser.Naam(Enum.Parse<GpuTopologie>(topologie)));

    [Fact]
    public void Topologie_KentPreciesDeVijfStandenPlusOnbekend() =>
        Assert.Equal(6, Enum.GetValues<GpuTopologie>().Select(BudgetBeslisser.Naam).Distinct(StringComparer.Ordinal).Count());

    [Theory]
    [InlineData("Onbekend")]
    [InlineData("Geweigerd")]
    [InlineData("Onbereikbaar")]
    public void VoorBatch_ZonderMetingVanMediaGuard_Nergens(string status)
    {
        // Ook met een vrije CPU-lane in het beeld: zonder status Ok is er geen uitspraak, dus geen batch.
        var beeld = new MgBeeld(Enum.Parse<MgStatus>(status), "x", _nu, true, [new MgLane("cpu", 0, 2, false)], false, true, "emby");
        Assert.Equal(new BudgetBesluit("geen", false, "mediaguard_niet_gemeten"), BudgetBeslisser.VoorBatch(beeld));
    }

    [Fact]
    public void VoorBatch_OnbekendeCpuLane_Nergens()
    {
        Assert.Equal(new BudgetBesluit("geen", false, "mediaguard_lanes_onbekend"), BudgetBeslisser.VoorBatch(Gemeten()));
        Assert.Equal(new BudgetBesluit("geen", false, "mediaguard_lanes_onbekend"), BudgetBeslisser.VoorBatch(Gemeten(new MgLane("gpu", 0, 1, false))));
        Assert.Equal(new BudgetBesluit("geen", false, "mediaguard_lanes_onbekend"), BudgetBeslisser.VoorBatch(Gemeten(new MgLane("cpu", null, 2, false))));
    }

    [Fact]
    public void VoorBatch_MediaGuardEncodeertOpDeCpu_Nergens() =>
        Assert.Equal(new BudgetBesluit("geen", false, "mediaguard_cpu_bezig"), BudgetBeslisser.VoorBatch(Gemeten(new MgLane("cpu", 1, 2, false))));

    [Fact]
    public void VoorBatch_VrijeCpuLane_AlleenDeCpuNooitEenGpu()
    {
        // De GPU-lane is vrij, en toch krijgt batch hem niet (vóór D08 nooit een GPU voor batch).
        var besluit = BudgetBeslisser.VoorBatch(Gemeten(new MgLane("gpu", 0, 1, false), new MgLane("cpu", 0, 2, false)));
        Assert.Equal(new BudgetBesluit("cpu", false, "gpu_niet_voor_batch_tot_d08"), besluit);
    }

    [Fact]
    public void VoorBatch_GeeftInGeenEnkeleStandEenGpu()
    {
        var beelden = new[]
        {
            MgBeeld.Zonder(MgStatus.Onbekend, "nog_niet_gemeten"),
            Gemeten(),
            Gemeten(new MgLane("gpu", 0, 1, false)),
            Gemeten(new MgLane("gpu", 0, 1, false), new MgLane("cpu", 0, 2, false)),
            Gemeten(new MgLane("gpu", 1, 1, false), new MgLane("cpu", 1, 2, false)),
        };
        Assert.All(beelden, b => Assert.False(BudgetBeslisser.VoorBatch(b).GpuVoorBatch));
        Assert.All(beelden, b => Assert.Contains(BudgetBeslisser.VoorBatch(b).BatchNode, new[] { "cpu", "geen" }));
    }

    [Fact]
    public void Reservering_BlijftDertigMinutenEnVerlengtBijOpnieuwHouden()
    {
        var budget = new BudgetBeslisser();
        Assert.Equal(30, BudgetBeslisser.GroupPauseLaneHoldMinutes);
        budget.Houd("sessie-a", "gpu0", _nu);
        budget.Houd("sessie-b", "gpu0", _nu);
        budget.Houd("sessie-c", "cpu", _nu);
        Assert.Equal(2, budget.Reserveringen(_nu)["gpu0"]);
        Assert.Equal(1, budget.Reserveringen(_nu)["cpu"]);

        // Net vóór de grens telt de reservering nog; op de grens is hij verlopen.
        Assert.Equal(2, budget.Reserveringen(_nu.AddMinutes(30).AddTicks(-1))["gpu0"]);

        // Opnieuw houden (seek, hervatten) verlengt vanaf dat moment.
        budget.Houd("sessie-a", "gpu0", _nu.AddMinutes(20));
        var later = budget.Reserveringen(_nu.AddMinutes(30));
        Assert.Equal(1, later["gpu0"]);
        Assert.False(later.ContainsKey("cpu"));
        Assert.Empty(budget.Reserveringen(_nu.AddMinutes(50)));
    }

    [Fact]
    public void Reservering_VrijgevenHaaltAlleenDieSessieWeg()
    {
        var budget = new BudgetBeslisser();
        budget.Houd("sessie-a", "gpu0", _nu);
        budget.Houd("sessie-b", "gpu0", _nu);
        budget.GeefVrij("sessie-a");
        budget.GeefVrij("bestaat-niet");
        Assert.Equal(1, budget.Reserveringen(_nu)["gpu0"]);
        budget.GeefVrij("sessie-b");
        Assert.Empty(budget.Reserveringen(_nu));
    }

    [Fact]
    public void Status_NoemtAlleenVasteWoordenEnAantallen()
    {
        var budget = new BudgetBeslisser();
        budget.Houd("ondoorzichtige-sleutel-1", "cpu", _nu);
        var status = budget.Status(Gemeten(new MgLane("cpu", 0, 2, false)), _nu);
        Assert.Equal(
            new[] { "topologie", "batch_node", "gpu_voor_batch", "reden", "reserveringen", "hold_minuten" },
            status.Select(p => p.Key).ToArray());
        Assert.Equal("cpu", status["batch_node"]!.GetValue<string>());
        Assert.False(status["gpu_voor_batch"]!.GetValue<bool>());
        Assert.Equal("gpu_niet_voor_batch_tot_d08", status["reden"]!.GetValue<string>());
        Assert.Equal(1, status["reserveringen"]!["cpu"]!.GetValue<int>());
        Assert.Equal(30, status["hold_minuten"]!.GetValue<int>());
        Assert.DoesNotContain("ondoorzichtige-sleutel-1", status.ToJsonString(), StringComparison.Ordinal);
    }
}
