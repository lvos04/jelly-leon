using System;
using System.Text;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Hub;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Org.BouncyCastle.Crypto.Signers;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>Vingerafdruk van de Hub-sleutelset (contract 1.3 §4.5, testvectoren) en de eigen Ed25519-verificatie.</summary>
public class HubSleutelTests
{
    private const string Jwt1 = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo";
    private const string Policy1 = "A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg";
    private const string Sleutel2 = "Kay64UG8yvCyLhqU000LxzYeUm0L_hLIl5S8kyKWbdc";

    private static JsonObject Jwk(string x, string kid) => new() { ["kty"] = "OKP", ["crv"] = "Ed25519", ["x"] = x, ["kid"] = kid };

    [Fact]
    public void Thumbprint_VolgtRfc7638()
    {
        Assert.Equal("kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k", new HubKey("a", Jwt1).Thumbprint);
        Assert.Equal("1IG2tMH7J2wbJZnOf8LJzQitKf7LMvoAElsuDMVM54Y", new HubKey("b", Policy1).Thumbprint);
        Assert.Equal("AkXIZFzonb59ZmGwyKgi3H3BwMi6amevqdKQiLZhdtc", new HubKey("c", Sleutel2).Thumbprint);
    }

    [Fact]
    public void Vingerafdruk_ContractVectoren()
    {
        var een = new HubKeySet([new HubKey("a", Jwt1)], [new HubKey("p", Policy1)]);
        Assert.Equal("MEGG-8GFG-2E4Y-K2RQ", een.Vingerafdruk);

        var tweeJwt = new HubKeySet([new HubKey("a", Jwt1), new HubKey("c", Sleutel2)], [new HubKey("p", Policy1)]);
        Assert.Equal("CYRC-JS8C-14AN-JR17", tweeJwt.Vingerafdruk);
        var andersom = new HubKeySet([new HubKey("c", Sleutel2), new HubKey("a", Jwt1)], [new HubKey("p", Policy1)]);
        Assert.Equal(tweeJwt.Vingerafdruk, andersom.Vingerafdruk);

        var tweePolicy = new HubKeySet([new HubKey("a", Jwt1)], [new HubKey("p", Policy1), new HubKey("c", Sleutel2)]);
        Assert.Equal("HN69-2PHK-XV2D-X85W", tweePolicy.Vingerafdruk);
    }

    [Theory]
    [InlineData("MEGG-8GFG-2E4Y-K2RQ", true)]
    [InlineData("megg 8gfg 2e4y k2rq", true)]
    [InlineData("MEGG8GFG2E4YK2RQ", true)]
    [InlineData("MEGG-8GFG-2E4Y-K2RR", false)]
    [InlineData("", false)]
    public void VingerafdrukKlopt_VergelijktWatDeBeheerderOvertikt(string getypt, bool verwacht)
    {
        var set = new HubKeySet([new HubKey("a", Jwt1)], [new HubKey("p", Policy1)]);
        Assert.Equal(verwacht, set.VingerafdrukKlopt(getypt));
    }

    [Fact]
    public void Parse_LeestHetAntwoordVanDeHubEnWeigertOnvolledigeSets()
    {
        var keyset = new JsonObject
        {
            ["jwks"] = new JsonObject { ["keys"] = new JsonArray(Jwk(Jwt1, "k1")) },
            ["policy_public_key"] = Jwk(Policy1, "p1"),
            ["keyset_fingerprint"] = "wordt genegeerd: Jelly Leon rekent zelf",
            ["toelichting"] = "vrije tekst",
        };
        Assert.Equal("MEGG-8GFG-2E4Y-K2RQ", HubKeySet.Parse(keyset, "keyset").Vingerafdruk);

        // Heen en terug via de opslagvorm geeft dezelfde vingerafdruk.
        Assert.Equal("MEGG-8GFG-2E4Y-K2RQ", HubKeySet.Parse(HubKeySet.Parse(keyset, "keyset").NaarJson(), "keyset").Vingerafdruk);

        var zonderPolicy = new JsonObject { ["jwks"] = new JsonObject { ["keys"] = new JsonArray(Jwk(Jwt1, "k1")) } };
        Assert.Equal("validation_error", Assert.Throws<JlException>(() => HubKeySet.Parse(zonderPolicy, "keyset")).Code);

        var kortX = new JsonObject { ["jwks"] = new JsonObject { ["keys"] = new JsonArray(Jwk("AAAA", "k1")) }, ["policy_public_key"] = Jwk(Policy1, "p1") };
        Assert.Equal("validation_error", Assert.Throws<JlException>(() => HubKeySet.Parse(kortX, "keyset")).Code);

        var dubbel = new JsonObject { ["jwks"] = new JsonObject { ["keys"] = new JsonArray(Jwk(Jwt1, "k1"), Jwk(Sleutel2, "k1")) }, ["policy_public_key"] = Jwk(Policy1, "p1") };
        Assert.Equal("validation_error", Assert.Throws<JlException>(() => HubKeySet.Parse(dubbel, "keyset")).Code);

        Assert.Equal("validation_error", Assert.Throws<JlException>(() => HubKeySet.Parse(JsonValue.Create("tekst"), "keyset")).Code);
    }

    [Theory]
    [InlineData("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "", "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")]
    [InlineData("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72", "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")]
    [InlineData("fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82", "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a")]
    public void Ed25519_Rfc8032Vectoren(string sleutel, string bericht, string handtekening)
    {
        var pk = Convert.FromHexString(sleutel);
        var msg = Convert.FromHexString(bericht);
        var sig = Convert.FromHexString(handtekening);
        Assert.True(Ed25519.Verifieer(pk, msg, sig));

        sig[5] ^= 0x01;
        Assert.False(Ed25519.Verifieer(pk, msg, sig));
        sig[5] ^= 0x01;
        Assert.False(Ed25519.Verifieer(pk, [.. msg, 0x00], sig));
        pk[3] ^= 0x10;
        Assert.False(Ed25519.Verifieer(pk, msg, sig));
    }

    [Fact]
    public void Ed25519_KloptMetEenOnafhankelijkeImplementatie()
    {
        var willekeur = new Random(20261111);
        for (var i = 0; i < 40; i++)
        {
            var sleutel = NepHub.Nieuw();
            var bericht = new byte[willekeur.Next(0, 300)];
            willekeur.NextBytes(bericht);
            var signer = new Ed25519Signer();
            signer.Init(true, sleutel);
            signer.BlockUpdate(bericht, 0, bericht.Length);
            var handtekening = signer.GenerateSignature();
            var publiek = sleutel.GeneratePublicKey().GetEncoded();

            Assert.True(Ed25519.Verifieer(publiek, bericht, handtekening));
            handtekening[willekeur.Next(0, 64)] ^= 0x04;
            Assert.False(Ed25519.Verifieer(publiek, bericht, handtekening));
        }
    }

    [Fact]
    public void Ed25519_WeigertVerkeerdeLengtesEnNietCanoniekeS()
    {
        var pk = Convert.FromHexString("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a");
        var sig = Convert.FromHexString("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b");
        Assert.False(Ed25519.Verifieer(pk.AsSpan(0, 31), [], sig));
        Assert.False(Ed25519.Verifieer(pk, [], sig.AsSpan(0, 63)));

        // S + L is dezelfde handtekening modulo de groepsorde, maar niet canoniek: weigeren (RFC 8032 §5.1.7).
        var l = System.Numerics.BigInteger.Parse("7237005577332262213973186563042994240857116359379907606001950938285454250989");
        var s = new System.Numerics.BigInteger(sig.AsSpan(32), isUnsigned: true, isBigEndian: false) + l;
        var bytes = s.ToByteArray(isUnsigned: true, isBigEndian: false);
        var vervalst = (byte[])sig.Clone();
        Array.Clear(vervalst, 32, 32);
        Array.Copy(bytes, 0, vervalst, 32, Math.Min(32, bytes.Length));
        Assert.False(Ed25519.Verifieer(pk, [], vervalst));
        Assert.False(Ed25519.Verifieer(pk, Encoding.ASCII.GetBytes("x"), sig));
    }
}
