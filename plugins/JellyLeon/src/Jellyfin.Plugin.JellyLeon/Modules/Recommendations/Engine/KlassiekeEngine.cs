using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;

namespace Jellyfin.Plugin.JellyLeon.Modules.Recommendations.Engine;

internal sealed record ScoreGewichten(double Inhoud, double Seed)
{
    public static ScoreGewichten Vast { get; } = new(0.60, 0.20);
    public const double Kwaliteit = 0.10;
    public const double Versheid = 0.05;
}

internal sealed record Kandidaat(Titel Titel, double Score, Reden Reden, Dictionary<string, double> Vector);

internal sealed class KlassiekeEngine(TimeProvider klok, ScoreGewichten? gewichten = null)
{
    private readonly ScoreGewichten _gewichten = gewichten ?? ScoreGewichten.Vast;

    public IReadOnlyList<Aanbeveling> Rangschik(IEnumerable<Titel> catalogus, Kijkprofiel profiel,
        int limiet = 10, string? bron = null, bool evaluatie = false, CancellationToken stop = default)
    {
        stop.ThrowIfCancellationRequested();
        var nu = klok.GetUtcNow();
        if (evaluatie && profiel.Toestand.Any(t => t.Tijd is null || t.Tijd >= nu))
        {
            throw new ArgumentException("Training bevat een ongedateerde interactie of een interactie op of na T.", nameof(profiel));
        }

        // Ook de documentfrequentie, zaaditems en uitleg mogen alleen zichtbare metadata gebruiken.
        var zichtbaar = catalogus.Where(t => t.Soort is "Movie" or "Series" && profiel.Toegang.Contains(t.Id))
            .ToDictionary(t => t.Id, StringComparer.Ordinal);
        if (limiet <= 0 || zichtbaar.Count == 0 || (bron is not null && !zichtbaar.ContainsKey(bron)))
        {
            return [];
        }

        limiet = Math.Min(limiet, zichtbaar.Count);
        var kenmerken = new Kenmerken(zichtbaar.Values);
        var toestand = profiel.Toestand.Where(t => zichtbaar.ContainsKey(t.Item)).ToDictionary(t => t.Item, StringComparer.Ordinal);
        var positief = toestand.Values.Where(t => t.Gewicht(nu) > 0)
            .OrderByDescending(t => t.Tijd).ThenBy(t => t.Item, StringComparer.Ordinal).ToArray();
        var smaak = new Dictionary<string, double>(StringComparer.Ordinal);
        foreach (var t in toestand.Values.OrderBy(t => t.Item, StringComparer.Ordinal))
        {
            var gewicht = t.Gewicht(nu);
            foreach (var (k, v) in kenmerken.Vectoren[t.Item]) { smaak[k] = smaak.GetValueOrDefault(k) + gewicht * v; }
        }

        var onboarding = profiel.OnboardingGenres.Select(g => "genre/" + Kenmerken.Genre(g)).ToHashSet(StringComparer.Ordinal);
        foreach (var id in profiel.OnboardingTitels.Where(zichtbaar.ContainsKey).Order(StringComparer.Ordinal))
        {
            foreach (var (term, gewicht) in kenmerken.Vectoren[id])
            {
                smaak[term] = smaak.GetValueOrDefault(term) + gewicht;
                if (term.Split('/')[0] is "genre" or "tag" or "studio" or "regisseur" or "schrijver" or "acteur" or "collectie")
                {
                    onboarding.Add(term);
                }
            }
        }

        foreach (var genre in profiel.OnboardingGenres.Select(Kenmerken.Genre).Distinct(StringComparer.Ordinal))
        {
            var term = "genre/" + genre;
            smaak[term] = smaak.GetValueOrDefault(term) + 1;
        }

        Kenmerken.Normaliseer(smaak);
        var zaden = positief.Take(5).ToArray();
        var voorkeur = smaak.Where(p => p.Value > 0).Select(p => p.Key).ToHashSet(StringComparer.Ordinal);
        if (bron is not null) { voorkeur.UnionWith(kenmerken.Vectoren[bron].Keys); }
        var huishouden = profiel.Huishoudscores();
        var typen = positief.Select(t => zichtbaar[t.Item].QuotumType).CountBy(t => t).ToDictionary();

        bool Toegelaten(Titel t) => t.Id != bron && !profiel.Volgende.Contains(t.Id)
            && !profiel.NietInteressant.Contains(t.Id)
            && (t.Serie is null || (!profiel.Volgende.Contains(t.Serie) && !profiel.NietInteressant.Contains(t.Serie)))
            && !t.Collecties.Any(profiel.NietInteressant.Contains)
            && (bron is not null || !toestand.TryGetValue(t.Id, out var s) || !s.Bekeken);

        var kandidaten = zichtbaar.Values.Where(Toegelaten).ToArray();
        // Algemene kenmerken dragen bij aan de score. Alleen zeldzame termen openen een op inhoud gevonden kandidaat.
        // Het globale aanbod per type vult het aanbod ook voor nieuwe gebruikers en schaarse metadata.
        var algemeen = kandidaten.GroupBy(t => t.QuotumType).SelectMany(g => g
            .OrderByDescending(t => ScoreGewichten.Kwaliteit * Kwaliteit(t) + ScoreGewichten.Versheid * Versheid(t, nu))
            .ThenBy(t => t.Id, StringComparer.Ordinal).Take(Math.Max(50, 5 * limiet))).Select(t => t.Id).ToHashSet();
        bool PastBijOnboarding(Titel t) => profiel.OnboardingTitels.Contains(t.Id)
            || (onboarding.Count > 0 && kenmerken.Vectoren[t.Id].Keys.Any(onboarding.Contains));
        var selectie = kandidaten.Where(t => algemeen.Contains(t.Id) || kenmerken.HeeftZeldzaam(t.Id, voorkeur)
            || PastBijOnboarding(t) || huishouden.ContainsKey(t.Id)).ToArray();

        Kandidaat Bereken(Titel titel)
        {
            stop.ThrowIfCancellationRequested();
            var vector = kenmerken.Vectoren[titel.Id];
            var inhoud = Kenmerken.Cosinus(smaak, vector);
            var besteZaad = zaden.Select(z => (Toestand: z, Gelijk: Kenmerken.Cosinus(kenmerken.Vectoren[z.Item], vector)))
                .DefaultIfEmpty().MaxBy(z => z.Gelijk);
            var kwaliteit = ScoreGewichten.Kwaliteit * Kwaliteit(titel);
            var vers = ScoreGewichten.Versheid * Versheid(titel, nu);
            var basis = kwaliteit + vers;
            var reden = kwaliteit > 0 && kwaliteit >= vers ? new Reden("highly_rated")
                : new Reden(vers > 0 ? "recently_added" : "exploration");
            var zaadscore = _gewichten.Seed * besteZaad.Gelijk;
            var inhoudscore = _gewichten.Inhoud * inhoud;
            var score = basis + zaadscore + inhoudscore;
            if (besteZaad.Toestand is { } zaad && (zaad.Favoriet || zaad.Bekeken) && Math.Max(zaadscore, inhoudscore) > Math.Max(kwaliteit, vers))
            {
                reden = new(zaad.Favoriet ? "because_favorite" : "because_watched", zaad.Item);
            }

            if (bron is not null)
            {
                score = 0.85 * Kenmerken.Cosinus(kenmerken.Vectoren[bron], vector) + 0.10 * inhoud + vers;
                var gedeeld = kenmerken.Vectoren[bron];
                var bijdrage = vector.Where(k => gedeeld.ContainsKey(k.Key))
                    .OrderByDescending(k => k.Value * gedeeld[k.Key]).Select(k => k.Key.Split('/')[0]);
                var code = bijdrage.Select(kenmerk => kenmerk switch
                {
                    "regisseur" => "same_director", "acteur" => "same_actor", "collectie" => "same_collection",
                    "studio" => "same_studio", "genre" => "genre_match", _ => null,
                }).FirstOrDefault(c => c is not null);
                if (code is not null) { reden = new(code); }
                if (toestand.GetValueOrDefault(titel.Id)?.Bekeken == true) { score *= 0.5; }
            }
            else if (positief.Length < 3)
            {
                // Een passende onboardingkeuze gaat voor het geanonimiseerde huishoudsignaal en de globale selectie.
                if (PastBijOnboarding(titel))
                {
                    score = 0.8 + basis;
                    reden = new("onboarding_choice");
                }
                else if (huishouden.TryGetValue(titel.Id, out var aandeel))
                {
                    score = 0.55 + 0.10 * aandeel + basis;
                    reden = new("household_popular");
                }
                else
                {
                    score = basis + 0.20 * besteZaad.Gelijk;
                }
            }
            else
            {
                score += 0.05 * huishouden.GetValueOrDefault(titel.Id);
            }

            return new(titel, Math.Clamp(score, 0, 1), reden, vector);
        }

        List<Aanbeveling> Kies(IEnumerable<Titel> pool) =>
            Herrangschikking.Kies(pool.Select(Bereken).ToList(), typen, limiet, profiel.Exploratie && bron is null, profiel.Id, nu, stop);
        var rij = Kies(selectie);
        // Een grote collectie mag het globale aanbod niet opvullen en daardoor andere zichtbare films verdringen.
        return rij.Count < limiet && selectie.Length < kandidaten.Length ? Kies(kandidaten) : rij;
    }

    private static double Kwaliteit(Titel t) => Math.Clamp(t.Waardering.GetValueOrDefault() / 10, 0, 1);

    private static double Versheid(Titel t, DateTimeOffset nu) => t.Toegevoegd is { } tijd && tijd <= nu
        ? Math.Pow(0.5, (nu - tijd).TotalDays / 365) : 0;
}
