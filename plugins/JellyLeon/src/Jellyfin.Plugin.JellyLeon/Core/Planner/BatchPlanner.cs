using System;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Budget;
using Jellyfin.Plugin.JellyLeon.Core.Connector;
using Jellyfin.Plugin.JellyLeon.Core.Media;
using Jellyfin.Plugin.JellyLeon.Core.MediaGuard;
using Jellyfin.Plugin.JellyLeon.Core.Werker;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Core.Planner;

/// <summary>
/// De ene planner van de plugin (B03-018, plan §10.7). Hij meet (sessies, MediaGuard, mediamappen, werker, leesfouten),
/// laat <see cref="PlannerRegels"/> beslissen en zet de werker stil of laat hem verder gaan. Bij het begin van elke
/// kijksessie gaat het pauzesein meteen uit; een tik om de twee seconden vangt alles op wat een gebeurtenis mist.
/// De pauze bij een kijksessie hangt aan geen enkele schakelaar en is niet uit te zetten.
/// </summary>
internal sealed class BatchPlanner : IHostedService, IDisposable
{
    /// <summary>Interval van de controletik in seconden; ruim binnen de vijf seconden van de pauze-eis.</summary>
    public const int TikSeconden = 2;

    private readonly ISessieBron _sessies;
    private readonly MediaGuardClient _mediaGuard;
    private readonly IMediaMappen _media;
    private readonly IWerker _werker;
    private readonly LeesfoutBreker _breker;
    private readonly BudgetBeslisser _budget;
    private readonly TimeProvider _klok;
    private readonly ILogger<BatchPlanner> _log;
    private readonly object _slot = new();
    private DateTimeOffset _rustSinds;
    private DateTimeOffset? _laatsteStart;
    private DateTimeOffset? _pauzeGevraagdOp;
    private bool _stil;
    private ITimer? _timer;
    private int _bezig;

    public BatchPlanner(ISessieBron sessies, MediaGuardClient mediaGuard, IMediaMappen media, IWerker werker, LeesfoutBreker breker, BudgetBeslisser budget, TimeProvider klok, ILogger<BatchPlanner> log)
    {
        _sessies = sessies;
        _mediaGuard = mediaGuard;
        _media = media;
        _werker = werker;
        _breker = breker;
        _budget = budget;
        _klok = klok;
        _log = log;

        // Na een herstart is niet bekend wanneer er voor het laatst gekeken is: de rusttijd begint opnieuw.
        _rustSinds = klok.GetUtcNow();
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        _sessies.Gestart += BijStart;
        _sessies.Gestopt += BijStop;
        _timer = _klok.CreateTimer(_ => Tik(), null, TimeSpan.FromSeconds(TikSeconden), TimeSpan.FromSeconds(TikSeconden));
        return Task.CompletedTask;
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        _sessies.Gestart -= BijStart;
        _sessies.Gestopt -= BijStop;
        _timer?.Dispose();
        _timer = null;
        return Task.CompletedTask;
    }

    public void Dispose() => _timer?.Dispose();

    /// <summary>Meet de stand van dit moment. Leest alleen; wijzigt niets buiten de eigen rusttijd.</summary>
    public PlannerStand Meet()
    {
        var nu = _klok.GetUtcNow();
        var sessies = _sessies.Lees();
        DateTimeOffset rust;
        lock (_slot)
        {
            if (sessies.Sessies > 0)
            {
                _rustSinds = nu;
            }

            rust = _rustSinds;
        }

        var mg = _mediaGuard.Beeld;

        // Stil is: de encoder is niet aantoonbaar bereikbaar, een lane staat op pauze of de kijkpauze van MediaGuard loopt.
        var gepauzeerd = mg.EncoderBereikbaar != true || mg.KijkpauzeActief == true || mg.Lanes.Any(l => l.Paused == true);
        var paden = _media.Paden();
        var uitkomsten = paden.Select(p => MountCheck.Beoordeel(p)).ToList();
        var media = uitkomsten.Contains(MountCheck.Uitkomst.Schrijfbaar)
            ? MountCheck.Uitkomst.Schrijfbaar
            : uitkomsten.Count > 0 && uitkomsten.All(u => u == MountCheck.Uitkomst.AlleenLezen) ? MountCheck.Uitkomst.AlleenLezen : MountCheck.Uitkomst.Onbekend;
        return new PlannerStand(
            nu,
            TimeOnly.FromDateTime(TimeZoneInfo.ConvertTime(nu, _klok.LocalTimeZone).DateTime),
            sessies.Sessies,
            sessies.SoftwareTranscodes,
            rust,
            mg.Status,
            gepauzeerd,
            mg.Lanes.FirstOrDefault(l => l.Lane == "cpu")?.Running,
            media,
            _werker.Klaar,
            _breker.Open,
            CgroupMarge.Lees());
    }

    /// <summary>Het besluit van dit moment voor één kostenklasse.</summary>
    public bool Mag(Kostenklasse klasse, bool beheerderNu = false) => PlannerRegels.Mag(PlannerRegels.Beslis(Meet(), beheerderNu), klasse);

    /// <summary>Eén controleronde: meten, beslissen en de werker stilzetten of laten doorgaan. Gooit nooit.</summary>
    public void Tik()
    {
        if (Interlocked.Exchange(ref _bezig, 1) == 1)
        {
            return;
        }

        try
        {
            var besluit = PlannerRegels.Beslis(Meet());
            bool wasStil;
            lock (_slot)
            {
                wasStil = _stil;
                _stil = !besluit.Zwaar;
                if (_stil && !wasStil)
                {
                    _pauzeGevraagdOp = _klok.GetUtcNow();
                }
            }

            _ = besluit.Zwaar ? StuurAsync(false) : StuurAsync(true);
        }
#pragma warning disable CA1031 // De planner mag de server nooit laten stoppen; een mislukte ronde is "niet beslist", dus geen batch.
        catch (Exception fout)
#pragma warning restore CA1031
        {
            _log.LogWarning("Jelly Leon planner: controleronde mislukt ({Soort}).", fout.GetType().Name);
        }
        finally
        {
            Interlocked.Exchange(ref _bezig, 0);
        }
    }

    /// <summary>De stand voor de beheerder: alleen aantallen, tijden en vaste woorden.</summary>
    public JsonObject Status()
    {
        var stand = Meet();
        var besluit = PlannerRegels.Beslis(stand);
        DateTimeOffset? start;
        DateTimeOffset? gevraagd;
        lock (_slot)
        {
            start = _laatsteStart;
            gevraagd = _pauzeGevraagdOp;
        }

        var bevestigd = _werker.PauzeBevestigdOp;
        long? latentie = start is DateTimeOffset s && bevestigd is DateTimeOffset b && b >= s ? (long)(b - s).TotalMilliseconds : null;
#pragma warning disable CA1308 // De woorden zijn kleine letters in de API.
        var mediaGuard = stand.MediaGuard.ToString().ToLowerInvariant();
#pragma warning restore CA1308
        return new JsonObject
        {
            ["observed_at"] = Outbox.Outbox.Iso(stand.Nu),
            ["zwaar_toegestaan"] = besluit.Zwaar,
            ["licht_toegestaan"] = besluit.Licht,
            ["reden"] = besluit.Reden,
            ["redenen"] = new JsonArray(besluit.Redenen.Select(r => (JsonNode)r).ToArray()),
            ["sessies"] = stand.Sessies,
            ["software_transcodes"] = stand.SoftwareTranscodes,
            ["rust_sinds"] = Outbox.Outbox.Iso(stand.RustSinds),
            ["laatste_sessiestart"] = start is DateTimeOffset st ? Milli(st) : null,
            ["pauze_gevraagd_op"] = gevraagd is DateTimeOffset g ? Milli(g) : null,
            ["pauze_bevestigd_op"] = bevestigd is DateTimeOffset bv ? Milli(bv) : null,
            ["pauze_latentie_ms"] = latentie,
            ["mediaguard"] = mediaGuard,
            ["media_mount"] = stand.Media switch
            {
                MountCheck.Uitkomst.AlleenLezen => "alleen_lezen",
                MountCheck.Uitkomst.Schrijfbaar => "schrijfbaar",
                _ => "onbekend",
            },
            ["werker"] = _werker.Stand,
            ["werker_reden"] = _werker.Reden,
            ["leesfouten"] = _breker.Status(),
            ["nachtvenster"] = PlannerRegels.InVenster(stand.LokaleTijd),
            ["cgroup_marge_bytes"] = stand.CgroupMargeBytes,
            ["grenzen"] = new JsonObject
            {
                ["zware_taken"] = PlannerRegels.MaxZwareTaken,
                ["threads"] = PlannerRegels.MaxThreads,
                ["batch_bytes"] = PlannerRegels.MaxBatchBytes,
                ["pauze_seconden"] = PlannerRegels.PauzeBinnenSeconden,
                ["hervat_minuten"] = PlannerRegels.HervatNaMinuten,
                ["venster"] = "23:00-07:00",
            },
            ["budget"] = _budget.Status(_mediaGuard.Beeld, stand.Nu),
        };
    }

    private static string Milli(DateTimeOffset moment) => moment.UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ss.fffZ", CultureInfo.InvariantCulture);

    private void BijStart(object? sender, EventArgs e)
    {
        // Regel G6a: elke kijksessie pauzeert, ook Direct Play. Eerst het sein, dan pas de rest; nooit wachten of gooien.
        var nu = _klok.GetUtcNow();
        lock (_slot)
        {
            _laatsteStart = nu;
            _rustSinds = nu;
            _pauzeGevraagdOp = nu;
            _stil = true;
        }

        _ = StuurAsync(true);
    }

    private void BijStop(object? sender, EventArgs e)
    {
        lock (_slot)
        {
            _rustSinds = _klok.GetUtcNow();
        }
    }

    private async Task StuurAsync(bool pauze)
    {
        try
        {
            if (pauze)
            {
                await _werker.PauzeerAsync(CancellationToken.None).ConfigureAwait(false);
            }
            else
            {
                await _werker.HervatAsync(CancellationToken.None).ConfigureAwait(false);
            }
        }
#pragma warning disable CA1031 // Een werker die niet antwoordt mag het afspelen nooit raken.
        catch (Exception fout)
#pragma warning restore CA1031
        {
            _log.LogWarning("Jelly Leon planner: sein aan de werker mislukt ({Soort}).", fout.GetType().Name);
        }
    }
}
