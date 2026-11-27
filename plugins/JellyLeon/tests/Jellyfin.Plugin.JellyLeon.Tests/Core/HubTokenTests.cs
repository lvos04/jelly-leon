using System;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Microsoft.AspNetCore.Http;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>Hub-authenticatie van de connector (contract 1.3 §4.7; JLT-68: zonder pin, kind, replay, verlopen).</summary>
public sealed class HubTokenTests : IDisposable
{
    private readonly Harnas _h = new();

    public void Dispose() => _h.Dispose();

    private string Reden(string? authorization, bool gekoppeld = true)
    {
        var pin = gekoppeld ? new HubPinState(_h.Hub.Sleutels(), _h.Hub.ServiceId, "2026-11-11T10:00:00Z") : null;
        var fout = Assert.Throws<JlException>(() => HubTokenValidator.Valideer(authorization, pin, _h.Klok.Nu));
        Assert.Equal(401, fout.Status);
        Assert.Equal("unauthorized", fout.Code);
        return fout.Details!["reason"]!.GetValue<string>();
    }

    private string Met(Action<JsonObject, JsonObject> wijzig) => "Bearer " + _h.Hub.Token(_h.Klok.Nu, "viewer", wijzig);

    [Fact]
    public void Volgorde_KoppelstatusGaatVoorAlles()
    {
        Assert.Equal("not_linked", Reden(null, gekoppeld: false));
        Assert.Equal("not_linked", Reden("Bearer svc_abc", gekoppeld: false));
        Assert.Equal("not_linked", Reden("Bearer " + _h.Hub.Token(_h.Klok.Nu), gekoppeld: false));
    }

    [Fact]
    public void Redenen_PerSituatie()
    {
        Assert.Equal("invalid_token", Reden(null));
        Assert.Equal("invalid_token", Reden("MediaBrowser Token=\"abc\""));
        Assert.Equal("service_token_not_accepted", Reden("Bearer svc_0123456789"));
        Assert.Equal("invalid_token", Reden("Bearer geen.jwt"));
        Assert.Equal("unknown_key", Reden(Met((h, _) => h.Remove("kid"))));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["iss"] = "iemand-anders")));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["aud"] = "mediaguard")));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["exp"] = c["iat"]!.GetValue<long>() + 121)));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["nbf"] = c["iat"]!.GetValue<long>() + 300)));
        Assert.Equal("token_use_invalid", Reden(Met((_, c) => c["token_use"] = "refresh")));
        Assert.Equal("token_use_invalid", Reden(Met((_, c) => c["roles"] = new JsonArray("service"))));
        Assert.Equal("token_use_invalid", Reden(Met((_, c) => c["roles"] = new JsonArray("viewer", "baas"))));
        Assert.Equal("jti_missing", Reden(Met((_, c) => c.Remove("jti"))));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["jti"] = "geen-uuid")));
    }

    [Fact]
    public void AudienceAlsLijstWordtGeweigerd() =>
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["aud"] = new JsonArray("jelly-leon", "mediaguard"))));

    [Theory]
    [InlineData("HS256")]
    [InlineData("none")]
    public void VerkeerdAlgoritmeWordtGeweigerd(string alg) =>
        Assert.Equal("invalid_token", Reden(Met((h, _) => h["alg"] = alg)));

    [Fact]
    public void OnbekendeKidWordtGeweigerd() =>
        Assert.Equal("unknown_key", Reden(Met((h, _) => h["kid"] = "onbekend")));

    [Fact]
    public void GepindePolicysleutelMagGeenJwtOndertekenen() =>
        Assert.Equal("unknown_key", Reden("Bearer " + _h.Hub.Token(_h.Klok.Nu, metPolicysleutel: true)));

    [Fact]
    public void OngeldigeTekstInDeKopGeeftDeContractfout()
    {
        var delen = _h.Hub.Token(_h.Klok.Nu).Split('.');
        delen[0] = NepHub.B64("{\"alg\":\"EdDSA\",\"typ\":\"JWT\",\"kid\":\"\\ud800\"}"u8.ToArray());
        Assert.Equal("invalid_token", Reden("Bearer " + string.Join('.', delen)));
    }

    [Fact]
    public void OnjuistHeaderTypeWordtGeweigerd() =>
        Assert.Equal("invalid_token", Reden(Met((h, _) => h["typ"] = "anders")));

    [Fact]
    public void JtiVereistUuidVersieVier() =>
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["jti"] = Guid.CreateVersion7().ToString())));

    [Fact]
    public void LevensduurBuitenHetBereikWordtGeweigerd()
    {
        var token = Met((_, c) =>
        {
            c["iat"] = long.MinValue;
            c["exp"] = long.MaxValue;
        });
        Assert.Equal("invalid_token", Reden(token));
    }

    [Theory]
    [InlineData("iat")]
    [InlineData("nbf")]
    public void ToekomstigeTijdHeeftHooguitDertigSecondenSpeling(string claim)
    {
        var nu = _h.Klok.Nu;
        var pin = new HubPinState(_h.Hub.Sleutels(), _h.Hub.ServiceId, "x");
        string MetTijd(int verschil) => Met((_, c) => c[claim] = nu.ToUnixTimeSeconds() + verschil);
        Assert.False(HubTokenValidator.Valideer(MetTijd(30), pin, nu).IsService);
        Assert.Equal("invalid_token", Reden(MetTijd(31)));
    }

    [Fact]
    public void VerlopenTokenWordtGeweigerd() =>
        Assert.Equal("token_expired", Reden("Bearer " + _h.Hub.Token(_h.Klok.Nu.AddSeconds(-91))));

    [Fact]
    public void Handtekening_VanEenAndereSleutelWordtGeweigerd()
    {
        var header = new JsonObject { ["alg"] = "EdDSA", ["typ"] = "JWT", ["kid"] = _h.Hub.Kid };
        var t = _h.Klok.Nu.ToUnixTimeSeconds();
        var claims = new JsonObject
        {
            ["iss"] = "hub", ["aud"] = "jelly-leon", ["sub"] = Guid.NewGuid().ToString(), ["token_use"] = "user",
            ["roles"] = new JsonArray("admin"), ["iat"] = t, ["nbf"] = t, ["exp"] = t + 60, ["jti"] = Guid.NewGuid().ToString(),
        };
        Assert.Equal("invalid_token", Reden("Bearer " + _h.Hub.Teken(header, claims, NepHub.Nieuw())));

        // Een geldig token waarvan de inhoud achteraf is aangepast.
        var delen = _h.Hub.Token(_h.Klok.Nu).Split('.');
        var gewijzigd = delen[0] + "." + NepHub.B64(System.Text.Encoding.UTF8.GetBytes(claims.ToJsonString())) + "." + delen[2];
        Assert.Equal("invalid_token", Reden("Bearer " + gewijzigd));
    }

    [Fact]
    public void Klok_DertigSecondenSpeling()
    {
        var token = "Bearer " + _h.Hub.Token(_h.Klok.Nu);
        var pin = new HubPinState(_h.Hub.Sleutels(), _h.Hub.ServiceId, "x");
        Assert.Equal("viewer", HubTokenValidator.Valideer(token, pin, _h.Klok.Nu.AddSeconds(89)).Rollen[0]);
        var fout = Assert.Throws<JlException>(() => HubTokenValidator.Valideer(token, pin, _h.Klok.Nu.AddSeconds(91)));
        Assert.Equal("token_expired", fout.Details!["reason"]!.GetValue<string>());
    }

    [Fact]
    public void Dienst_EnGebruikersTokensWordenHerkend()
    {
        var pin = new HubPinState(_h.Hub.Sleutels(), _h.Hub.ServiceId, "x");
        var dienst = HubTokenValidator.Valideer("Bearer " + _h.Hub.DienstToken(_h.Klok.Nu), pin, _h.Klok.Nu);
        Assert.True(dienst.IsService);
        Assert.Equal("service:hub", dienst.Id);

        var kind = HubTokenValidator.Valideer(Met((_, c) => c["roles"] = new JsonArray("admin", "kind")), pin, _h.Klok.Nu);
        Assert.True(kind.IsKind);
    }

    [Fact]
    public void AndereDienstregistratieWordtGeweigerd()
    {
        Assert.Equal("token_use_invalid", Reden("Bearer " + _h.Hub.Token(_h.Klok.Nu, "service", (_, c) =>
        {
            c["sub"] = "hub";
            c["token_use"] = "hub_service";
            c["service_id"] = "99999999-9999-4999-8999-999999999999";
        })));
    }

    [Fact]
    public void HeropendeReplayopslagWeigertGebruikteJti()
    {
        var nu = _h.Klok.Nu;
        _h.Koppel();
        var wie = HubTokenValidator.Valideer("Bearer " + _h.Hub.Token(nu), _h.Dienst<HubPin>().Huidig, nu);
        var eerste = _h.Dienst<JtiStore>();
        eerste.Controleer(wie, "POST", "/connector/v1/propose", null, nu);
        var heropend = new JtiStore(new CoreDatabase(_h.Dienst<JlPaths>()));
        var fout = Assert.Throws<JlException>(() => heropend.Controleer(wie, "POST", "/connector/v1/propose", null, nu));
        Assert.Equal((401, "token_replayed"), (fout.Status, fout.Details["reason"]!.GetValue<string>()));
    }

    [Fact]
    public async Task GelijktijdigeMutatiesMetEenJtiLatenEenVerzoekDoor()
    {
        _h.Koppel();
        var token = _h.Hub.Token(_h.Klok.Nu);
        var start = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        async Task<Antwoord> Verzoek()
        {
            await start.Task;
            return await _h.RoepHub("connector.propose", token, "{}");
        }

        var verzoeken = new[] { Verzoek(), Verzoek() };
        start.SetResult();
        var antwoorden = await Task.WhenAll(verzoeken);
        Assert.Single(antwoorden, a => a.Status == 501 && a.Code == "capability_unavailable");
        Assert.Single(antwoorden, a => a.Status == 401 && a.Reden == "token_replayed");
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ExacteHubHerhalingKanAlleenEenBewaardAntwoordLezen(bool bewaard)
    {
        _h.Koppel();
        var route = RouteTable.Zoek("connector.propose") with { Idempotentie = JlIdem.Verplicht };
        var token = _h.Hub.Token(_h.Klok.Nu);
        var sleutel = Guid.NewGuid().ToString();
        var pipeline = _h.Dienst<JlPipeline>();
        Task<JlContext> Begin()
        {
            var http = new DefaultHttpContext();
            http.Request.Method = route.Methode;
            http.Request.Path = route.Pad;
            http.Request.Headers.Authorization = "Bearer " + token;
            http.Request.Headers["Idempotency-Key"] = sleutel;
            http.Request.Body = new System.IO.MemoryStream("{}"u8.ToArray());
            return pipeline.BereidVoorAsync(http, route, "proef");
        }

        var eerste = await Begin();
        Assert.Null(eerste.Herhaling);
        if (bewaard)
        {
            var antwoord = JlResult.Ok(new JsonObject { ["aantal"] = 1 });
            pipeline.Rond(eerste, antwoord);
            var opnieuw = (await Begin()).Herhaling;
            Assert.NotNull(opnieuw);
            Assert.Equal(antwoord.Body, opnieuw.Body);
            Assert.Equal("true", opnieuw.Headers["Idempotent-Replay"]);
        }
        else
        {
            pipeline.Rond(eerste, JlResult.Fout(Fouten.AfhankelijkheidOnbeschikbaar("proef"), "proef"));
            var fout = await Assert.ThrowsAsync<JlException>(Begin);
            Assert.Equal((401, "token_replayed"), (fout.Status, (string?)fout.Details["reason"]));
        }
    }

    [Fact]
    public async Task Connector_ZonderPinKindReplayEnVerlopen()
    {
        var zonderPin = await _h.RoepHub("connector.discover", _h.Hub.Token(_h.Klok.Nu));
        Assert.Equal((401, "unauthorized", "not_linked"), (zonderPin.Status, zonderPin.Code, zonderPin.Reden));

        _h.Koppel();
        var goed = await _h.RoepHub("connector.discover", _h.Hub.Token(_h.Klok.Nu));
        Assert.Equal(200, goed.Status);
        Assert.Equal("jelly-leon", goed.Json!["app_id"]!.GetValue<string>());
        Assert.Equal(200, (await _h.RoepHub("connector.health", _h.Hub.DienstToken(_h.Klok.Nu))).Status);

        var kind = await _h.RoepHub("connector.discover", _h.Hub.Token(_h.Klok.Nu, "kind"));
        Assert.Equal((403, "forbidden", "role_kind"), (kind.Status, kind.Code, kind.Reden));

        // Hetzelfde token twee keer op een muterende route: de tweede keer is een replay.
        var token = _h.Hub.Token(_h.Klok.Nu, "admin");
        var eerste = await _h.RoepHub("connector.propose", token);
        Assert.Equal((501, "capability_unavailable"), (eerste.Status, eerste.Code));
        var tweede = await _h.RoepHub("connector.propose", token);
        Assert.Equal((401, "unauthorized", "token_replayed"), (tweede.Status, tweede.Code, tweede.Reden));

        // Ook op een andere muterende route blijft dat token verbruikt.
        var andere = await _h.RoepHub("connector.apply", token);
        Assert.Equal("token_replayed", andere.Reden);

        var oud = _h.Hub.Token(_h.Klok.Nu.AddSeconds(-200));
        var verlopen = await _h.RoepHub("connector.discover", oud);
        Assert.Equal((401, "token_expired"), (verlopen.Status, verlopen.Reden));
    }

    [Fact]
    public async Task Connector_OntkoppelenWeigertDirect()
    {
        _h.Koppel();
        Assert.Equal(200, (await _h.RoepHub("connector.discover", _h.Hub.Token(_h.Klok.Nu))).Status);
        _h.Dienst<HubPin>().Wis();
        Assert.Equal("not_linked", (await _h.RoepHub("connector.discover", _h.Hub.Token(_h.Klok.Nu))).Reden);

        // Een sessietoken van de server hoort niet op de connector.
        _h.Koppel();
        var sessie = await _h.Roep("connector.discover", kop: ["Authorization: MediaBrowser Token=\"abc\""]);
        Assert.Equal((401, "invalid_token"), (sessie.Status, sessie.Reden));
    }
}
