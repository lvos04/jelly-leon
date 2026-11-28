using System;
using System.Collections.Generic;
using System.Linq;
using Jellyfin.Plugin.JellyLeon.Modules.Recommendations.Engine;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Recommendations;

public sealed class KlassiekeEngineTests
{
    private static readonly DateTimeOffset T = new(2024, 5, 1, 12, 0, 0, TimeSpan.Zero);
    private sealed class Klok : TimeProvider { public override DateTimeOffset GetUtcNow() => T; }

    private static Titel Film(string id, string genre = "Drama") => new(id, "Movie") { Genres = [genre], Waardering = 7, Toegevoegd = T.AddDays(-10) };
    private static Kijkprofiel Profiel(Titel[] titels, params Kijktoestand[] toestand) => new("eigen", titels.Select(t => t.Id).ToHashSet(), toestand);
    private static Kijktoestand Gezien(string id) => new(id, T.AddDays(-8), Bekeken: true, Favoriet: true);

    [Fact]
    public void Kenmerken_NormaliserenSynoniemenGebruikenVijfActeursEnWegenZeldzameTermenZwaarder()
    {
        var film = Film("a", "Sciencefiction") with { Tags = ["uniek"], Acteurs = ["een", "twee", "drie", "vier", "vijf", "zes"] };
        var gelijk = Film("b", "Sci-Fi & Fantasy");
        var k = new Kenmerken([film, gelijk, Film("c", "science fiction"), Film("d", "sci-fi"), Film("e", "Sciencefiction")]);
        var vector = k.Vectoren["a"];
        Assert.True(vector["tag/uniek"] > vector["genre/sciencefiction"]);
        Assert.Contains("acteur/vijf", vector.Keys);
        Assert.DoesNotContain("acteur/zes", vector.Keys);
        Assert.False(k.HeeftZeldzaam("a", ["genre/sciencefiction"]));
        Assert.True(k.HeeftZeldzaam("a", ["tag/uniek"]));
        Assert.Equal(1, Kenmerken.Cosinus(k.Vectoren["b"], k.Vectoren["d"]), 12);
        Assert.True((Film("anime", "Animatie") with { Landen = ["Japan"] }).Anime);
        Assert.True((Film("anime") with { AnimeBibliotheek = true }).Anime);
        Assert.True((Film("a", "Eigen genre") with { AnimeGenres = ["eigen genre"] }).Anime);
        Assert.False(Film("b", "Animatie").Anime);
    }

    [Fact]
    public void Profiel_ActueleToestandHalveringEnAfhaken()
    {
        var nu = new Kijktoestand("a", T, Bekeken: true, Favoriet: true, Rating: 8, Likes: true);
        Assert.Equal(3, nu.Gewicht(T));
        Assert.Equal(1.5, (nu with { Tijd = T.AddDays(-365) }).Gewicht(T), 12);
        Assert.Equal(0.5, new Kijktoestand("a", T, Bekeken: true, Gemarkeerd: true).Gewicht(T));
        Assert.True(new Kijktoestand("a", T.AddDays(-15), Fractie: 0.1).Gewicht(T) < 0);
        Assert.Equal(0, new Kijktoestand("a", T.AddDays(-14), Fractie: 0.1).Gewicht(T));
        Assert.Equal(-1, new Kijktoestand("a", T, Likes: false, Minder: true).Gewicht(T));
    }

    [Fact]
    public void Onboardingtitel_GebruiktAlleenZichtbareKenmerken()
    {
        var bron = Film("bron", "Avontuur") with { Tags = ["zee"] };
        var passend = Film("passend", "Drama") with { Tags = ["zee"] };
        var algemeen = Film("algemeen", "Komedie") with { Waardering = 10, Toegevoegd = T };
        var afgeschermd = Film("verborgen", "Horror") with { Tags = ["zee"] };
        Titel[] catalogus = [bron, passend, algemeen, afgeschermd];
        var profiel = Profiel([bron, passend, algemeen]) with { OnboardingTitels = ["bron"], NietInteressant = ["bron"] };
        var engine = new KlassiekeEngine(new Klok());
        var gekozen = engine.Rangschik(catalogus, profiel, stop: TestContext.Current.CancellationToken)[0];
        Assert.Equal(("passend", new Reden("onboarding_choice")), (gekozen.Item, gekozen.Redenen[0]));
        var ander = engine.Rangschik(catalogus, profiel with { OnboardingTitels = ["verborgen"] }, stop: TestContext.Current.CancellationToken);
        Assert.Equal("algemeen", ander[0].Item);
        Assert.DoesNotContain(ander, r => r.Redenen.Any(reden => reden.Code == "onboarding_choice"));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public void Training_WeigertGrensEnToekomst(int dagen)
    {
        var t = Film("a");
        var p = Profiel([t], Gezien(t.Id) with { Tijd = T.AddDays(dagen) });
        Assert.Throws<ArgumentException>(() => new KlassiekeEngine(new Klok()).Rangschik([t], p, evaluatie: true, stop: TestContext.Current.CancellationToken));
    }

    [Fact]
    public void Ranglijst_BewaaktToegangUitsluitingGroepenEnQuotumOokBijExploratie()
    {
        var titels = Enumerable.Range(0, 40).Select(i => Film("f" + i) with { Collecties = i < 25 ? ["groep"] : [] })
            .Concat(Enumerable.Range(0, 15).Select(i => new Titel("s" + i, "Series") { Genres = [i % 2 == 0 ? "Anime" : "Drama"] }))
            .Append(Film("verboden")).Append(Film("verborgen") with { Collecties = ["afgekeurd"] })
            .Append(new Titel("foto", "Photo")).ToArray();
        var p = Profiel(titels, Gezien("f0"), Gezien("s0"), Gezien("s1"), Gezien("verboden")) with
        {
            Volgende = ["s3"], NietInteressant = ["afgekeurd", "f28"], Toegang = titels.Select(t => t.Id).Except(["verboden"]).ToHashSet(),
        };
        var engine = new KlassiekeEngine(new Klok());
        var top = engine.Rangschik(titels, p, evaluatie: true, stop: TestContext.Current.CancellationToken);
        var ids = top.Select(r => r.Item).ToArray();
        Assert.Equal(10, ids.Distinct().Count());
        Assert.Equal(ids, engine.Rangschik(titels.Reverse(), p, evaluatie: true, stop: TestContext.Current.CancellationToken).Select(r => r.Item));
        Assert.Single(top, r => r.Exploratie);
        Assert.All(ids, id => Assert.DoesNotContain(id, new[] { "f0", "s0", "s1", "s3", "f28", "verboden", "verborgen", "foto" }));
        var gekozen = titels.Where(t => ids.Contains(t.Id)).ToArray();
        Assert.True(gekozen.Count(t => t.Collecties.Contains("groep")) <= 2);
        Assert.Equal(["Anime", "Movie", "Series"], gekozen.Select(t => t.QuotumType).Distinct().Order());
        foreach (var r in top)
        {
            Assert.NotEmpty(r.Redenen);
            Assert.All(r.Redenen.Where(x => x.RefItemId is not null), x => Assert.Contains(x.RefItemId!, new[] { "f0", "s0", "s1" }));
        }
    }

    [Fact]
    public void Mmr_KiestVerschilBijGelijkeScoreEnIdBijGelijkeInhoud()
    {
        var titels = new[] { Film("a"), Film("b"), Film("c", "Animatie") };
        var p = Profiel(titels) with { Exploratie = false };
        Assert.Equal(["a", "c", "b"], new KlassiekeEngine(new Klok()).Rangschik(titels, p, stop: TestContext.Current.CancellationToken).Select(r => r.Item));
        Assert.Empty(new KlassiekeEngine(new Klok()).Rangschik(titels, p with { Toegang = [] }, stop: TestContext.Current.CancellationToken));
    }

    [Fact]
    public void KoudeStart_OnboardingVoorDrieAndereVolwassenDelersDanMetadata()
    {
        var titels = new[] { Film("eigen", "Avontuur"), Film("groep"), Film("hoog") with { Waardering = 10 } };
        var delers = new[] { "eigen", "A", "B", "C" }.Select(id => new Deler(id, "thuis", true, true, ["groep"])).ToArray();
        var p = Profiel(titels) with { Volwassen = true, Huishouden = "thuis", HuishoudenAan = true, Ontvangt = true, Delers = delers };
        var engine = new KlassiekeEngine(new Klok());
        Assert.Equal("onboarding_choice", engine.Rangschik(titels, p with { OnboardingGenres = ["Adventure"] }, stop: TestContext.Current.CancellationToken)[0].Redenen[0].Code);
        var groepskeus = engine.Rangschik(titels, p, stop: TestContext.Current.CancellationToken)[0];
        Assert.Equal(("groep", new Reden("household_popular")), (groepskeus.Item, groepskeus.Redenen[0]));
        foreach (var ongeldig in new[] { p with { Ontvangt = false }, p with { Volwassen = false }, p with { HuishoudenAan = false },
            p with { Delers = [.. delers[..3], delers[2]] }, p with { Delers = [.. delers[..3], delers[3] with { Deelt = false }] },
            p with { Delers = [.. delers[..3], delers[3] with { Volwassen = false }] },
            p with { Delers = [.. delers[..3], delers[3] with { Huishouden = "ander" }] },
            p with { Delers = [.. delers[..3], delers[3] with { Bekeken = ["ander"] }] } })
        {
            Assert.Equal("hoog", engine.Rangschik(titels, ongeldig, stop: TestContext.Current.CancellationToken)[0].Item);
            Assert.Empty(ongeldig.Huishoudscores());
        }
    }
}
