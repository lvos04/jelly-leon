using System;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
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
        Assert.Equal("invalid_token", Reden(Met((h, _) => h["alg"] = "HS256")));
        Assert.Equal("invalid_token", Reden(Met((h, _) => h["alg"] = "none")));
        Assert.Equal("unknown_key", Reden(Met((h, _) => h["kid"] = "0000000000000000")));
        Assert.Equal("unknown_key", Reden(Met((h, _) => h.Remove("kid"))));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["iss"] = "iemand-anders")));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["aud"] = "mediaguard")));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["aud"] = new JsonArray("jelly-leon", "mediaguard"))));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["exp"] = c["iat"]!.GetValue<long>() + 121)));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["nbf"] = c["iat"]!.GetValue<long>() + 300)));
        Assert.Equal("token_use_invalid", Reden(Met((_, c) => c["token_use"] = "refresh")));
        Assert.Equal("token_use_invalid", Reden(Met((_, c) => c["roles"] = new JsonArray("service"))));
        Assert.Equal("token_use_invalid", Reden(Met((_, c) => c["roles"] = new JsonArray("viewer", "baas"))));
        Assert.Equal("jti_missing", Reden(Met((_, c) => c.Remove("jti"))));
        Assert.Equal("invalid_token", Reden(Met((_, c) => c["jti"] = "geen-uuid")));
    }

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

        // Een dienst-token met de service_id van een andere dienst hoort niet bij deze koppeling.
        Assert.Equal("token_use_invalid", Reden("Bearer " + _h.Hub.Token(_h.Klok.Nu, "service", (_, c) =>
        {
            c["sub"] = "hub";
            c["token_use"] = "hub_service";
            c["service_id"] = "99999999-9999-4999-8999-999999999999";
        })));
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
