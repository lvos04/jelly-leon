using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>Beheerroutes: de Hub-koppeling JL4 (plakken, vingerafdruk vergelijken, pinnen) en de moduleschakelaars.</summary>
public sealed class BeheerTests : IDisposable
{
    private static readonly JsonObject _openapi = OpenApiBouwer.Bouw();
    private readonly Harnas _h = new();

    public void Dispose() => _h.Dispose();

    private static string Sleutel() => "Idempotency-Key: " + Guid.NewGuid();

    [Fact]
    public async Task HubKoppeling_PlakkenVergelijkenPinnenEnOntkoppelen()
    {
        var keyset = _h.Hub.Keyset().ToJsonString();
        var begin = await _h.Roep("hublink.get");
        Assert.Equal(200, begin.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "HubLink", begin.Json));
        Assert.Equal("not_linked", begin.Json!["status"]!.GetValue<string>());
        Assert.Null(begin.Json["fingerprint"]);
        Assert.Equal(401, (await _h.RoepHub("connector.health", _h.Hub.Token(_h.Klok.Nu))).Status);

        // Stap 1: de beheerder plakt de set; de plugin toont de vingerafdruk zonder iets op te slaan.
        var verify = await _h.Roep("hublink.verify", "{\"keyset\":" + keyset + "}");
        Assert.Equal(200, verify.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "HubLinkVerify", verify.Json));
        var vingerafdruk = verify.Json!["fingerprint"]!.GetValue<string>();
        Assert.Equal(_h.Hub.Sleutels().Vingerafdruk, vingerafdruk);
        Assert.Equal(1, verify.Json["jwt_sleutels"]!.GetValue<int>());
        Assert.Equal("not_linked", (await _h.Roep("hublink.get")).Json!["status"]!.GetValue<string>());

        // Stap 2: pinnen lukt alleen met de vingerafdruk van precies deze set.
        var andere = new NepHub().Sleutels().Vingerafdruk;
        var fout = await _h.Roep("hublink.put", "{\"keyset\":" + keyset + ",\"fingerprint\":\"" + andere + "\",\"service_id\":\"" + _h.Hub.ServiceId + "\"}", [Sleutel()]);
        Assert.Equal(422, fout.Status);
        Assert.Equal("vingerafdruk_klopt_niet", fout.Json!["details"]!["fouten"]![0]!["code"]!.GetValue<string>());
        var geenUuid = await _h.Roep("hublink.put", "{\"keyset\":" + keyset + ",\"fingerprint\":\"" + vingerafdruk + "\",\"service_id\":\"hub\"}", [Sleutel()]);
        Assert.Equal(422, geenUuid.Status);
        Assert.Equal("service_id", geenUuid.Json!["details"]!["fouten"]![0]!["veld"]!.GetValue<string>());
        var kapot = await _h.Roep("hublink.put", "{\"keyset\":{\"jwks\":{\"keys\":[]}},\"fingerprint\":\"" + vingerafdruk + "\",\"service_id\":\"" + _h.Hub.ServiceId + "\"}", [Sleutel()]);
        Assert.Equal(422, kapot.Status);
        Assert.Equal("not_linked", (await _h.Roep("hublink.get")).Json!["status"]!.GetValue<string>());

        var zonderSleutel = await _h.Roep("hublink.put", "{\"keyset\":" + keyset + ",\"fingerprint\":\"" + vingerafdruk + "\",\"service_id\":\"" + _h.Hub.ServiceId + "\"}");
        Assert.Equal(400, zonderSleutel.Status);
        Assert.Equal("idempotency_key_required", zonderSleutel.Code);

        // Kleine letters en zonder streepjes overtikken mag (de beheerder leest de code van een ander scherm).
        var getypt = vingerafdruk.Replace("-", string.Empty, StringComparison.Ordinal).ToLowerInvariant();
        var pin = await _h.Roep("hublink.put", "{\"keyset\":" + keyset + ",\"fingerprint\":\"" + getypt + "\",\"service_id\":\"" + _h.Hub.ServiceId.ToUpperInvariant() + "\"}", [Sleutel()]);
        Assert.Equal(200, pin.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "HubLink", pin.Json));
        Assert.Equal("linked", pin.Json!["status"]!.GetValue<string>());
        Assert.Equal(vingerafdruk, pin.Json["fingerprint"]!.GetValue<string>());
        Assert.Equal(_h.Hub.ServiceId, pin.Json["service_id"]!.GetValue<string>());
        Assert.Equal("jelly-leon", pin.Json["audience"]!.GetValue<string>());
        Assert.DoesNotContain(_h.Hub.Keyset()["jwks"]!["keys"]![0]!["x"]!.GetValue<string>(), pin.Json.ToJsonString(), StringComparison.Ordinal);

        // Nu accepteert de connector tokens van deze Hub — en alleen van deze Hub.
        Assert.Equal(200, (await _h.RoepHub("connector.health", _h.Hub.Token(_h.Klok.Nu))).Status);
        Assert.Equal(200, (await _h.RoepHub("connector.health", _h.Hub.DienstToken(_h.Klok.Nu))).Status);
        var vreemd = await _h.RoepHub("connector.health", new NepHub().Token(_h.Klok.Nu));
        Assert.Equal(401, vreemd.Status);
        Assert.Equal("unknown_key", vreemd.Reden);

        // Een Hub-token is geen beheerdersbewijs voor /media/v1.
        _h.Sessies.Wie = null;
        Assert.Equal(401, (await _h.Roep("hublink.get", kop: ["Authorization: Bearer " + _h.Hub.Token(_h.Klok.Nu, "admin")])).Status);
        _h.Sessies.Wie = new SessieIdentiteit(Guid.NewGuid(), true, false);

        var los = await _h.Roep("hublink.delete", kop: [Sleutel()]);
        Assert.Equal(200, los.Status);
        Assert.Equal("not_linked", los.Json!["status"]!.GetValue<string>());
        var na = await _h.RoepHub("connector.health", _h.Hub.Token(_h.Klok.Nu));
        Assert.Equal(401, na.Status);
        Assert.Equal("not_linked", na.Reden);
    }

    [Fact]
    public async Task HubKoppeling_AlleenEenBeheerderEnNooitEenKinderprofiel()
    {
        var keyset = _h.Hub.Keyset().ToJsonString();
        var body = "{\"keyset\":" + keyset + ",\"fingerprint\":\"" + _h.Hub.Sleutels().Vingerafdruk + "\",\"service_id\":\"" + _h.Hub.ServiceId + "\"}";
        _h.Sessies.Wie = new SessieIdentiteit(Guid.NewGuid(), false, false);
        var gewoon = await _h.Roep("hublink.put", body, [Sleutel()]);
        Assert.Equal(403, gewoon.Status);
        Assert.Equal("admin_required", gewoon.Reden);
        _h.Sessies.Wie = new SessieIdentiteit(Guid.NewGuid(), true, true);
        var kind = await _h.Roep("hublink.put", body, [Sleutel()]);
        Assert.Equal(403, kind.Status);
        Assert.Equal("kid_profile", kind.Reden);
        _h.Sessies.Wie = null;
        Assert.Equal(401, (await _h.Roep("hublink.verify", "{\"keyset\":" + keyset + "}")).Status);
        _h.Sessies.Wie = new SessieIdentiteit(Guid.NewGuid(), true, false);
        Assert.Equal("not_linked", (await _h.Roep("hublink.get")).Json!["status"]!.GetValue<string>());
    }

    [Fact]
    public async Task Modules_SchakelenMetEtagEnZonderVerlorenUpdate()
    {
        var lijst = await _h.Roep("modules.list");
        Assert.Equal(200, lijst.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Modules", lijst.Json));
        Assert.Equal(["devices", "quality"], lijst.Json!["items"]!.AsArray().Select(m => m!["slug"]!.GetValue<string>()));
        Assert.All(lijst.Json["items"]!.AsArray(), m => Assert.False(m!["enabled"]!.GetValue<bool>()));
        var etag = lijst.Kop["ETag"];
        var pad = new Dictionary<string, string> { ["slug"] = "quality" };

        Assert.Equal(404, (await _h.Roep("quality.status")).Status);
        Assert.Equal(428, (await _h.Roep("modules.put", "{\"enabled\":true}", [Sleutel()], pad)).Status);
        var aan = await _h.Roep("modules.put", "{\"enabled\":true}", [Sleutel(), "If-Match: " + etag], pad);
        Assert.Equal(200, aan.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "Modules", aan.Json));
        Assert.True(aan.Json!["items"]![1]!["enabled"]!.GetValue<bool>());
        Assert.NotEqual(etag, aan.Kop["ETag"]);
        var status = await _h.Roep("quality.status");
        Assert.Equal(200, status.Status);
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "ModuleStatus", status.Json));
        var instellingen = await _h.Roep("quality.settings.get");
        Assert.Empty(SchemaControle.Afwijkingen(_openapi, "ModuleInstellingen", instellingen.Json));

        // Een tweede beheerder met de oude ETag verliest: 412 met de huidige ETag.
        var oud = await _h.Roep("modules.put", "{\"enabled\":false}", [Sleutel(), "If-Match: " + etag], pad);
        Assert.Equal(412, oud.Status);
        Assert.Equal("precondition_failed", oud.Code);
        Assert.Equal(aan.Kop["ETag"], oud.Json!["details"]!["huidige_etag"]!.GetValue<string>());
        Assert.Equal(200, (await _h.Roep("quality.status")).Status);

        var onbekend = await _h.Roep("modules.put", "{\"enabled\":true}", [Sleutel(), "If-Match: " + aan.Kop["ETag"]], new Dictionary<string, string> { ["slug"] = "subtitles" });
        Assert.Equal(404, onbekend.Status);
        var fout = await _h.Roep("modules.put", "{\"enabled\":\"ja\"}", [Sleutel(), "If-Match: " + aan.Kop["ETag"]], pad);
        Assert.Equal(422, fout.Status);
        var extra = await _h.Roep("modules.put", "{\"enabled\":true,\"anders\":1}", [Sleutel(), "If-Match: " + aan.Kop["ETag"]], pad);
        Assert.Equal(422, extra.Status);
        Assert.Equal("onbekend_veld", extra.Json!["details"]!["fouten"]![0]!["code"]!.GetValue<string>());
    }
}
