using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Budget;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Media;
using Jellyfin.Plugin.JellyLeon.Core.MediaGuard;
using Jellyfin.Plugin.JellyLeon.Core.Planner;
using Jellyfin.Plugin.JellyLeon.Core.Werker;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Session;
using MediaBrowser.Model.Dto;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.Session;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>
/// De planner zoals hij nu is (B03-018, stand na ronde 3; ADR-0035): de regels, de leesfoutonderbreker, de cgroup-marge,
/// de sessiebron, de standaardwerker (er is geen werker) en de beheerroute <c>GET /media/v1/planner</c>. Er is nog geen
/// wachtrij: de planner start zelf nooit een taak. Wachtrij, grenzen per procesgroep, noodstop en Δ-MG-AUTH horen bij
/// S-G1-36; de echte werker bij S-G1-32.
/// </summary>
public sealed class PlannerTests : IDisposable
{
    private static readonly JsonObject _openapi = OpenApiBouwer.Bouw();
    private static readonly DateTimeOffset _nacht = new(2026, 11, 11, 23, 30, 0, TimeSpan.Zero);
    private readonly Harnas _h = new();
    private readonly StilleKlok _klok = new();

    public void Dispose() => _h.Dispose();

    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    /// <summary>Een stand waarin alles in orde is: 's nachts, niemand kijkt al 11 minuten, MediaGuard gemeten en vrij.</summary>
    private static PlannerStand InOrde() => new(
        _nacht,
        new TimeOnly(23, 30),
        0,
        0,
        _nacht.AddMinutes(-11),
        MgStatus.Ok,
        false,
        0,
        MountCheck.Uitkomst.AlleenLezen,
        true,
        false,
        2L * 1024 * 1024 * 1024);

    private static PlannerStand Verstoor(string reden) => reden switch
    {
        "leesfouten" => InOrde() with { LeesfoutenOpen = true },
        "media_schrijfbaar" => InOrde() with { Media = MountCheck.Uitkomst.Schrijfbaar },
        "media_onbekend" => InOrde() with { Media = MountCheck.Uitkomst.Onbekend },
        "mediaguard_gepauzeerd" => InOrde() with { MediaGuardGepauzeerd = true },
        "mediaguard_geweigerd" => InOrde() with { MediaGuard = MgStatus.Geweigerd },
        "mediaguard_onbereikbaar" => InOrde() with { MediaGuard = MgStatus.Onbereikbaar },
        "mediaguard_onbekend" => InOrde() with { MediaGuard = MgStatus.Onbekend },
        "software_transcode" => InOrde() with { SoftwareTranscodes = 1 },
        "actieve_sessie" => InOrde() with { Sessies = 1 },
        "wacht_na_kijken" => InOrde() with { RustSinds = _nacht.AddMinutes(-9) },
        "werker_niet_beschikbaar" => InOrde() with { WerkerKlaar = false },
        "mediaguard_lanes_onbekend" => InOrde() with { MediaGuardCpuBezig = null },
        "mediaguard_cpu_bezig" => InOrde() with { MediaGuardCpuBezig = 1 },
        "buiten_venster" => InOrde() with { LokaleTijd = new TimeOnly(12, 0) },
        _ => throw new ArgumentOutOfRangeException(nameof(reden), reden, "onbekende reden in de test"),
    };

    [Fact]
    public void Regels_AllesInOrde_ZwaarEnLichtMogen()
    {
        // Tegenproef voor alle tests hieronder: zonder verstoring is het besluit "vrij".
        var besluit = PlannerRegels.Beslis(InOrde());
        Assert.True(besluit.Zwaar);
        Assert.True(besluit.Licht);
        Assert.Equal("vrij", besluit.Reden);
        Assert.Empty(besluit.Redenen);
    }

    [Fact]
    public void Regels_ZonderWerker_GeenZwaarWerkWelLicht()
    {
        var besluit = PlannerRegels.Beslis(InOrde() with { WerkerKlaar = false });
        Assert.False(besluit.Zwaar);
        Assert.True(besluit.Licht);
        Assert.Equal("werker_niet_beschikbaar", besluit.Reden);
        Assert.Equal(["werker_niet_beschikbaar"], besluit.Redenen);
        Assert.False(PlannerRegels.Mag(besluit, Kostenklasse.Zwaar));

        // Ook een beheerder die "nu analyseren" vraagt, krijgt zonder werker niets.
        Assert.False(PlannerRegels.Beslis(InOrde() with { WerkerKlaar = false }, beheerderNu: true).Zwaar);
    }

    [Theory]
    [InlineData("leesfouten")]
    [InlineData("media_schrijfbaar")]
    [InlineData("media_onbekend")]
    [InlineData("mediaguard_gepauzeerd")]
    [InlineData("mediaguard_geweigerd")]
    [InlineData("mediaguard_onbereikbaar")]
    [InlineData("mediaguard_onbekend")]
    [InlineData("software_transcode")]
    [InlineData("actieve_sessie")]
    [InlineData("wacht_na_kijken")]
    public void Regels_StilstandVoorAlBatchwerk(string reden)
    {
        var besluit = PlannerRegels.Beslis(Verstoor(reden));
        Assert.False(besluit.Zwaar);
        Assert.False(besluit.Licht);
        Assert.Equal(reden, besluit.Reden);
        Assert.Equal([reden], besluit.Redenen);
        Assert.True(PlannerRegels.Mag(besluit, Kostenklasse.Geen));
        Assert.False(PlannerRegels.Mag(besluit, Kostenklasse.CpuLicht));
    }

    [Theory]
    [InlineData("werker_niet_beschikbaar")]
    [InlineData("mediaguard_lanes_onbekend")]
    [InlineData("mediaguard_cpu_bezig")]
    [InlineData("buiten_venster")]
    public void Regels_AlleenZwaarWerkStaatStil(string reden)
    {
        var besluit = PlannerRegels.Beslis(Verstoor(reden));
        Assert.False(besluit.Zwaar);
        Assert.True(besluit.Licht);
        Assert.Equal([reden], besluit.Redenen);
        Assert.True(PlannerRegels.Mag(besluit, Kostenklasse.CpuLicht));
    }

    [Fact]
    public void Regels_OnbekendIsNooitInOrde_AlleRedenenTellen()
    {
        var stand = InOrde() with
        {
            MediaGuard = MgStatus.Onbekend,
            Media = MountCheck.Uitkomst.Onbekend,
            WerkerKlaar = false,
            CgroupMargeBytes = null,
            LokaleTijd = new TimeOnly(12, 0),
        };
        var besluit = PlannerRegels.Beslis(stand);
        Assert.False(besluit.Zwaar);
        Assert.False(besluit.Licht);
        Assert.Equal(["media_onbekend", "mediaguard_onbekend", "werker_niet_beschikbaar", "buiten_venster"], besluit.Redenen);
        Assert.Equal("media_onbekend", besluit.Reden);
    }

    [Fact]
    public void Regels_HervatPasNaTienMinutenZonderKijken()
    {
        Assert.Equal(10, PlannerRegels.HervatNaMinuten);
        var bijna = InOrde() with { RustSinds = _nacht - TimeSpan.FromMinutes(10) + TimeSpan.FromTicks(1) };
        Assert.Equal(["wacht_na_kijken"], PlannerRegels.Beslis(bijna).Redenen);
        Assert.True(PlannerRegels.Beslis(InOrde() with { RustSinds = _nacht.AddMinutes(-10) }).Zwaar);
    }

    [Fact]
    public void Regels_NachtvensterVan23Tot7UurLokaleTijd()
    {
        Assert.False(PlannerRegels.InVenster(new TimeOnly(22, 59, 59)));
        Assert.True(PlannerRegels.InVenster(new TimeOnly(23, 0)));
        Assert.True(PlannerRegels.InVenster(new TimeOnly(0, 0)));
        Assert.True(PlannerRegels.InVenster(new TimeOnly(6, 59, 59)));
        Assert.False(PlannerRegels.InVenster(new TimeOnly(7, 0)));
    }

    [Fact]
    public void Regels_BeheerderNu_AlleenMetGenoegMargeEnZonderSoftwareTranscode()
    {
        var kijkt = InOrde() with { Sessies = 1, LokaleTijd = new TimeOnly(12, 0) };
        Assert.Equal(["actieve_sessie", "buiten_venster"], PlannerRegels.Beslis(kijkt).Redenen);
        Assert.Equal(["marge_onbekend"], PlannerRegels.Beslis(kijkt with { CgroupMargeBytes = null }, beheerderNu: true).Redenen);
        Assert.Equal(["marge_te_klein"], PlannerRegels.Beslis(kijkt with { CgroupMargeBytes = PlannerRegels.BeheerMargeBytes - 1 }, beheerderNu: true).Redenen);

        var genoeg = PlannerRegels.Beslis(kijkt with { CgroupMargeBytes = PlannerRegels.BeheerMargeBytes }, beheerderNu: true);
        Assert.True(genoeg.Zwaar);
        Assert.Equal("beheerder_nu", genoeg.Reden);

        var software = PlannerRegels.Beslis(kijkt with { CgroupMargeBytes = PlannerRegels.BeheerMargeBytes, SoftwareTranscodes = 1 }, beheerderNu: true);
        Assert.False(software.Zwaar);
        Assert.Equal(["software_transcode"], software.Redenen);
    }

    [Fact]
    public void Regels_DezelfdeStandGeeftAltijdHetzelfdeBesluit()
    {
        var stand = Verstoor("mediaguard_cpu_bezig");
        var een = PlannerRegels.Beslis(stand);
        var twee = PlannerRegels.Beslis(stand);
        Assert.Equal((een.Zwaar, een.Licht, een.Reden), (twee.Zwaar, twee.Licht, twee.Reden));
        Assert.Equal(een.Redenen, twee.Redenen);
    }

    [Fact]
    public void Regels_KostenklassenEnGrenzen()
    {
        Assert.Equal(Kostenklasse.Geen, PlannerRegels.Kosten("quality.inventory"));
        Assert.Equal(Kostenklasse.CpuLicht, PlannerRegels.Kosten("rec.rebuild"));
        Assert.Equal(Kostenklasse.Zwaar, PlannerRegels.Kosten("quality.scan"));
        Assert.Equal(Kostenklasse.Zwaar, PlannerRegels.Kosten("onbekend.type"));
        Assert.Equal(1, PlannerRegels.MaxZwareTaken);
        Assert.Equal(2, PlannerRegels.MaxThreads);
        Assert.Equal(1024L * 1024 * 1024, PlannerRegels.MaxBatchBytes);
        Assert.Equal(5, PlannerRegels.PauzeBinnenSeconden);
        Assert.Equal(1024L * 1024 * 1024, PlannerRegels.BeheerMargeBytes);
    }

    [Fact]
    public void LeesfoutBreker_SlaatAanBijDrieVerschillendeBestanden()
    {
        Assert.Equal(3, LeesfoutBreker.Drempel);
        Assert.Equal(60, LeesfoutBreker.VensterMinuten);
        var breker = new LeesfoutBreker();
        Assert.False(breker.Meld("bestand-a", _nacht));
        Assert.False(breker.Meld("bestand-a", _nacht.AddMinutes(1)));
        Assert.False(breker.Meld("bestand-a", _nacht.AddMinutes(2)));
        Assert.False(breker.Meld("bestand-b", _nacht.AddMinutes(3)));
        Assert.False(breker.Open);
        Assert.Equal(2, breker.Status()["bestanden"]!.GetValue<int>());

        Assert.True(breker.Meld("bestand-c", _nacht.AddMinutes(4)));
        Assert.True(breker.Open);
        Assert.False(breker.Meld("bestand-d", _nacht.AddMinutes(5)));
        var status = breker.Status();
        Assert.True(status["open"]!.GetValue<bool>());
        Assert.Equal(3, status["bestanden"]!.GetValue<int>());
        Assert.Equal("2026-11-11T23:34:00Z", status["open_sinds"]!.GetValue<string>());
        Assert.DoesNotContain("bestand-", status.ToJsonString(), StringComparison.Ordinal);
    }

    [Fact]
    public void LeesfoutBreker_TeltAlleenFoutenBinnenHetUur()
    {
        var breker = new LeesfoutBreker();
        breker.Meld("bestand-a", _nacht);
        breker.Meld("bestand-b", _nacht.AddMinutes(30));
        Assert.False(breker.Meld("bestand-c", _nacht.AddMinutes(60).AddTicks(1)));
        Assert.False(breker.Open);

        var grens = new LeesfoutBreker();
        grens.Meld("bestand-a", _nacht);
        grens.Meld("bestand-b", _nacht.AddMinutes(30));
        Assert.True(grens.Meld("bestand-c", _nacht.AddMinutes(60)));
    }

    [Fact]
    public void LeesfoutBreker_BlijftOpenTotEenBeheerderHerstelt()
    {
        var breker = new LeesfoutBreker();
        breker.Meld("bestand-a", _nacht);
        breker.Meld("bestand-b", _nacht);
        breker.Meld("bestand-c", _nacht);
        Assert.True(breker.Open);
        Assert.False(breker.Meld("bestand-e", _nacht.AddDays(2)));
        Assert.True(breker.Open);

        breker.Herstel();
        Assert.False(breker.Open);
        Assert.Equal(0, breker.Status()["bestanden"]!.GetValue<int>());
        Assert.Null(breker.Status()["open_sinds"]);
        Assert.False(breker.Meld("bestand-a", _nacht.AddDays(2)));
    }

    [Fact]
    public void LeesfoutBreker_MeldtEenEventZonderPadOfSleutel()
    {
        var breker = _h.Dienst<LeesfoutBreker>();
        breker.Meld("vingerafdruk-1", _h.Klok.Nu);
        breker.Meld("vingerafdruk-2", _h.Klok.Nu);
        breker.Meld("vingerafdruk-3", _h.Klok.Nu);
        var events = _h.Dienst<global::Jellyfin.Plugin.JellyLeon.Core.Outbox.Outbox>().Lees(0, 10).Events;
        var ev = Assert.Single(events, e => e!["event_type"]!.GetValue<string>() == "media.storage.read_failed");
        Assert.Equal(3, ev!["payload"]!["files"]!.GetValue<int>());
        Assert.True(ev["payload"]!["breaker"]!.GetValue<bool>());
        Assert.DoesNotContain("vingerafdruk-", ev.ToJsonString(), StringComparison.Ordinal);
    }

    [Fact]
    public void CgroupMarge_GrensMinGebruikMetTerugvalOpMemAvailable()
    {
        var map = Directory.CreateTempSubdirectory("jl-cgroup-").FullName;
        try
        {
            var meminfo = Path.Combine(map, "meminfo");
            Assert.Null(CgroupMarge.Lees(map, meminfo));

            File.WriteAllText(meminfo, "MemTotal:       8000 kB\nMemAvailable:   2048 kB\n");
            Assert.Equal(2048L * 1024, CgroupMarge.Lees(map, meminfo));

            File.WriteAllText(Path.Combine(map, "memory.max"), "max\n");
            File.WriteAllText(Path.Combine(map, "memory.current"), "100\n");
            Assert.Equal(2048L * 1024, CgroupMarge.Lees(map, meminfo));

            File.WriteAllText(Path.Combine(map, "memory.max"), "3000\n");
            Assert.Equal(2900L, CgroupMarge.Lees(map, meminfo));

            File.WriteAllText(Path.Combine(map, "memory.current"), "5000\n");
            Assert.Equal(0L, CgroupMarge.Lees(map, meminfo));

            File.WriteAllText(Path.Combine(map, "memory.max"), "onleesbaar\n");
            Assert.Null(CgroupMarge.Lees(map, meminfo));

            File.WriteAllText(Path.Combine(map, "memory.max"), "max\n");
            File.WriteAllText(meminfo, "MemTotal:       8000 kB\n");
            Assert.Null(CgroupMarge.Lees(map, meminfo));
        }
        finally
        {
            Directory.Delete(map, true);
        }
    }

    [Theory]
    [InlineData(true, false, null, true)]
    [InlineData(true, false, "", true)]
    [InlineData(true, false, "none", true)]
    [InlineData(true, false, "qsv", false)]
    [InlineData(true, true, null, false)]
    [InlineData(false, false, null, false)]
    public void ServerSessies_HerkentSoftwareTranscode(bool transcode, bool videoDirect, string? hardware, bool software) =>
        Assert.Equal(software, ServerSessies.IsSoftware(transcode, videoDirect, hardware));

    [Fact]
    public async Task ServerSessies_TeltAlleenAfspelendeSessies()
    {
        var beheer = new Mock<ISessionManager>();
        await using var stil = new SessionInfo(beheer.Object, NullLogger.Instance);
        await using var direct = new SessionInfo(beheer.Object, NullLogger.Instance) { NowPlayingItem = new BaseItemDto() };
        await using var software = new SessionInfo(beheer.Object, NullLogger.Instance)
        {
            NowPlayingItem = new BaseItemDto(),
            TranscodingInfo = new TranscodingInfo { IsVideoDirect = false, HardwareAccelerationType = HardwareAccelerationType.none },
        };
        await using var hardware = new SessionInfo(beheer.Object, NullLogger.Instance)
        {
            NowPlayingItem = new BaseItemDto(),
            TranscodingInfo = new TranscodingInfo { IsVideoDirect = false, HardwareAccelerationType = HardwareAccelerationType.qsv },
        };
        beheer.SetupGet(s => s.Sessions).Returns([stil, direct, software, hardware]);
        using var bron = new ServerSessies(beheer.Object);
        Assert.Equal(new SessieBeeld(3, 1), bron.Lees());
    }

    [Fact]
    public void ServerSessies_GeeftStartEnStopDoorTotDispose()
    {
        var beheer = new Mock<ISessionManager>();
        using var bron = new ServerSessies(beheer.Object);
        var (gestart, gestopt) = (0, 0);
        bron.Gestart += (_, _) => gestart++;
        bron.Gestopt += (_, _) => gestopt++;
        beheer.Raise(s => s.PlaybackStart += null, new PlaybackProgressEventArgs());
        beheer.Raise(s => s.PlaybackStopped += null, new PlaybackStopEventArgs());
        Assert.Equal((1, 1), (gestart, gestopt));

        bron.Dispose();
        beheer.Raise(s => s.PlaybackStart += null, new PlaybackProgressEventArgs());
        Assert.Equal((1, 1), (gestart, gestopt));
    }

    [Fact]
    public async Task GeenWerker_IsNooitKlaarEnDoetNiets()
    {
        var werker = new GeenWerker();
        Assert.False(werker.Klaar);
        Assert.Equal("afwezig", werker.Stand);
        Assert.Equal("werker_niet_beschikbaar", werker.Reden);
        Assert.Null(werker.PauzeBevestigdOp);
        Assert.False(await werker.PauzeerAsync(Ct));
        Assert.False(await werker.HervatAsync(Ct));
    }

    [Fact]
    public void BatchPlanner_StandaardregistratieHeeftGeenWerkerEnStaatStil()
    {
        Assert.IsType<GeenWerker>(_h.Dienst<IWerker>());
        var planner = _h.Dienst<BatchPlanner>();
        Assert.False(planner.Mag(Kostenklasse.Zwaar));
        Assert.False(planner.Mag(Kostenklasse.Zwaar, beheerderNu: true));
        Assert.True(planner.Mag(Kostenklasse.Geen));

        var status = planner.Status();
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Planner", JsonNode.Parse(status.ToJsonString())));
        Assert.False(status["zwaar_toegestaan"]!.GetValue<bool>());
        Assert.Contains("werker_niet_beschikbaar", status["redenen"]!.AsArray().Select(r => r!.GetValue<string>()));
        Assert.Equal("afwezig", status["werker"]!.GetValue<string>());
        Assert.Equal("werker_niet_beschikbaar", status["werker_reden"]!.GetValue<string>());
        Assert.Equal("onbekend", status["mediaguard"]!.GetValue<string>());
        Assert.Equal("onbekend", status["budget"]!["topologie"]!.GetValue<string>());
        Assert.Equal("geen", status["budget"]!["batch_node"]!.GetValue<string>());
    }

    [Fact]
    public void BatchPlanner_ZonderWerkerStartNietsEnSeintAlleenPauze()
    {
        var werker = new TelWerker();
        var sessies = new NepSessieBron();
        using var planner = Planner(werker, sessies);
        for (var i = 0; i < 5; i++)
        {
            planner.Tik();
        }

        Assert.Equal(0, werker.Hervat);
        Assert.Equal(5, werker.Pauzeer);
        Assert.False(planner.Status()["zwaar_toegestaan"]!.GetValue<bool>());
    }

    [Fact]
    public async Task BatchPlanner_PauzeertMeteenBijElkeKijksessie()
    {
        var werker = new TelWerker();
        var sessies = new NepSessieBron();
        using var planner = Planner(werker, sessies);
        await planner.StartAsync(Ct);
        Assert.Equal(TimeSpan.FromSeconds(BatchPlanner.TikSeconden), _klok.Periode);
        try
        {
            _klok.Nu = _klok.Nu.AddMinutes(1);
            sessies.Start();
            Assert.Equal(1, werker.Pauzeer);
            var status = planner.Status();
            Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Planner", JsonNode.Parse(status.ToJsonString())));
            Assert.Equal("2026-11-11T10:01:00.000Z", status["laatste_sessiestart"]!.GetValue<string>());
            Assert.Equal("2026-11-11T10:01:00.000Z", status["pauze_gevraagd_op"]!.GetValue<string>());
            Assert.Equal("2026-11-11T10:01:00Z", status["rust_sinds"]!.GetValue<string>());

            // Zolang er gekeken wordt, schuift de rusttijd mee; na het stoppen begint hij te lopen.
            sessies.Beeld = new SessieBeeld(1, 0);
            _klok.Nu = _klok.Nu.AddMinutes(5);
            Assert.Equal("2026-11-11T10:06:00Z", planner.Status()["rust_sinds"]!.GetValue<string>());
            Assert.Contains("actieve_sessie", planner.Status()["redenen"]!.AsArray().Select(r => r!.GetValue<string>()));
            sessies.Beeld = new SessieBeeld(0, 0);
            _klok.Nu = _klok.Nu.AddMinutes(1);
            sessies.Stop();
            _klok.Nu = _klok.Nu.AddMinutes(1);
            Assert.Equal("2026-11-11T10:07:00Z", planner.Status()["rust_sinds"]!.GetValue<string>());
        }
        finally
        {
            await planner.StopAsync(Ct);
        }

        // Na het stoppen luistert de planner niet meer naar sessies.
        sessies.Start();
        Assert.Equal(1, werker.Pauzeer);
        Assert.Equal(0, werker.Hervat);
    }

    [Fact]
    public async Task Route_PlannerStatus_AlleenVoorEenBeheerder()
    {
        var spec = RouteTable.Zoek("planner.status");
        Assert.Equal(("GET", "/media/v1/planner", JlAuth.SessieBeheerder, JlIdem.Geen), (spec.Methode, spec.Pad, spec.Auth, spec.Idempotentie));
        Assert.Single(RouteTable.Alle, r => r.Pad == "/media/v1/planner");

        var ok = await _h.Roep("planner.status");
        Assert.Equal(200, ok.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Planner", ok.Json));
        Assert.False(ok.Json!["zwaar_toegestaan"]!.GetValue<bool>());

        _h.Sessies.Wie = null;
        var anoniem = await _h.Roep("planner.status");
        Assert.Equal(401, anoniem.Status);
        Assert.Equal("unauthorized", anoniem.Code);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Fout", anoniem.Json));

        // Een Hub-token is geen beheerdersbewijs voor /media/v1.
        Assert.Equal(401, (await _h.Roep("planner.status", kop: ["Authorization: Bearer " + _h.Hub.Token(_h.Klok.Nu, "admin")])).Status);

        _h.Sessies.Wie = new SessieIdentiteit(Guid.NewGuid(), false, false);
        var gewoon = await _h.Roep("planner.status");
        Assert.Equal(403, gewoon.Status);
        Assert.Equal(("forbidden", "admin_required"), (gewoon.Code, gewoon.Reden));
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Fout", gewoon.Json));
        Assert.DoesNotContain("zwaar_toegestaan", gewoon.Json!.ToJsonString(), StringComparison.Ordinal);

        _h.Sessies.Wie = new SessieIdentiteit(Guid.NewGuid(), true, true);
        var kind = await _h.Roep("planner.status");
        Assert.Equal(403, kind.Status);
        Assert.Equal("kid_profile", kind.Reden);
    }

    private BatchPlanner Planner(IWerker werker, ISessieBron sessies) => new(
        sessies,
        _h.Dienst<MediaGuardClient>(),
        _h.Media,
        werker,
        new LeesfoutBreker(),
        new BudgetBeslisser(),
        _klok,
        NullLogger<BatchPlanner>.Instance);

    /// <summary>Een klok in UTC waarvan de timer nooit vanzelf afgaat: de test roept <see cref="BatchPlanner.Tik"/> zelf aan.</summary>
    private sealed class StilleKlok : TimeProvider
    {
        public DateTimeOffset Nu { get; set; } = new(2026, 11, 11, 10, 0, 0, TimeSpan.Zero);

        public TimeSpan? Periode { get; private set; }

        public override TimeZoneInfo LocalTimeZone => TimeZoneInfo.Utc;

        public override DateTimeOffset GetUtcNow() => Nu;

        public override ITimer CreateTimer(TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
        {
            Periode = period;
            return new StilleTimer();
        }

        private sealed class StilleTimer : ITimer
        {
            public bool Change(TimeSpan dueTime, TimeSpan period) => true;

            public void Dispose()
            {
            }

            public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        }
    }

    /// <summary>Een werker die nooit klaar is en alleen telt welke seinen hij krijgt.</summary>
    private sealed class TelWerker : IWerker
    {
        public int Pauzeer { get; private set; }

        public int Hervat { get; private set; }

        public bool Klaar => false;

        public string Stand => "afwezig";

        public string Reden => "werker_niet_beschikbaar";

        public DateTimeOffset? PauzeBevestigdOp => null;

        public Task<bool> PauzeerAsync(CancellationToken annulering)
        {
            Pauzeer++;
            return Task.FromResult(false);
        }

        public Task<bool> HervatAsync(CancellationToken annulering)
        {
            Hervat++;
            return Task.FromResult(false);
        }
    }

    private sealed class NepSessieBron : ISessieBron
    {
        public event EventHandler? Gestart;

        public event EventHandler? Gestopt;

        public SessieBeeld Beeld { get; set; } = new(0, 0);

        public SessieBeeld Lees() => Beeld;

        public void Start() => Gestart?.Invoke(this, EventArgs.Empty);

        public void Stop() => Gestopt?.Invoke(this, EventArgs.Empty);
    }
}
