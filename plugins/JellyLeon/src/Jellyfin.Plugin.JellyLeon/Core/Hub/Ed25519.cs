using System;
using System.Numerics;
using System.Security.Cryptography;

namespace Jellyfin.Plugin.JellyLeon.Core.Hub;

/// <summary>
/// Ed25519-verificatie volgens RFC 8032 §5.1.7 (alleen controleren, nooit ondertekenen; er is dus geen geheim
/// sleutelmateriaal en geen constante-tijd-eis). .NET 10 heeft geen publieke Ed25519-API en de host levert geen
/// cryptobibliotheek mee; zie ADR-0029. Strikt: S moet kleiner zijn dan L en punten moeten canoniek gecodeerd zijn.
/// </summary>
internal static class Ed25519
{
    private static readonly BigInteger _p = BigInteger.Pow(2, 255) - 19;
    private static readonly BigInteger _l = BigInteger.Pow(2, 252) + BigInteger.Parse("27742317777372353535851937790883648493", System.Globalization.CultureInfo.InvariantCulture);
    private static readonly BigInteger _d = Mod(-121665 * Inverse(121666));
    private static readonly BigInteger _wortelMinEen = BigInteger.ModPow(2, (_p - 1) / 4, _p);
    private static readonly Punt _basis = BasisPunt();

    public static bool Verifieer(ReadOnlySpan<byte> publiekeSleutel, ReadOnlySpan<byte> bericht, ReadOnlySpan<byte> handtekening)
    {
        if (publiekeSleutel.Length != 32 || handtekening.Length != 64)
        {
            return false;
        }

        if (!Decodeer(publiekeSleutel, out var a) || !Decodeer(handtekening[..32], out var r))
        {
            return false;
        }

        var s = new BigInteger(handtekening[32..], isUnsigned: true, isBigEndian: false);
        if (s >= _l)
        {
            return false;
        }

        var invoer = new byte[64 + bericht.Length];
        handtekening[..32].CopyTo(invoer);
        publiekeSleutel.CopyTo(invoer.AsSpan(32));
        bericht.CopyTo(invoer.AsSpan(64));
        var h = new BigInteger(SHA512.HashData(invoer), isUnsigned: true, isBigEndian: false) % _l;

        var links = Maal(_basis, s);
        var rechts = Plus(r, Maal(a, h));
        return Mod((links.X * rechts.Z) - (rechts.X * links.Z)).IsZero && Mod((links.Y * rechts.Z) - (rechts.Y * links.Z)).IsZero;
    }

    private static BigInteger Mod(BigInteger waarde)
    {
        var rest = waarde % _p;
        return rest.Sign < 0 ? rest + _p : rest;
    }

    private static BigInteger Inverse(BigInteger waarde) => BigInteger.ModPow(Mod(waarde), _p - 2, _p);

    private static Punt BasisPunt()
    {
        var y = Mod(4 * Inverse(5));
        HerstelX(y, false, out var x);
        return new Punt(x, y, BigInteger.One, Mod(x * y));
    }

    private static bool HerstelX(BigInteger y, bool teken, out BigInteger x)
    {
        var u = Mod((y * y) - 1);
        var v = Mod((_d * y * y) + 1);
        var xx = Mod(u * Inverse(v));
        x = BigInteger.ModPow(xx, (_p + 3) / 8, _p);
        if (!Mod((x * x) - xx).IsZero)
        {
            x = Mod(x * _wortelMinEen);
        }

        if (!Mod((x * x) - xx).IsZero)
        {
            return false;
        }

        if (x.IsZero && teken)
        {
            return false;
        }

        if (!x.IsEven != teken)
        {
            x = _p - x;
        }

        return true;
    }

    private static bool Decodeer(ReadOnlySpan<byte> bytes, out Punt punt)
    {
        punt = default;
        Span<byte> kopie = stackalloc byte[32];
        bytes.CopyTo(kopie);
        var teken = (kopie[31] & 0x80) != 0;
        kopie[31] &= 0x7F;
        var y = new BigInteger(kopie, isUnsigned: true, isBigEndian: false);
        if (y >= _p || !HerstelX(y, teken, out var x))
        {
            return false;
        }

        punt = new Punt(x, y, BigInteger.One, Mod(x * y));
        return true;
    }

    private static Punt Plus(Punt p, Punt q)
    {
        var a = Mod((p.Y - p.X) * (q.Y - q.X));
        var b = Mod((p.Y + p.X) * (q.Y + q.X));
        var c = Mod(p.T * 2 * _d * q.T);
        var d = Mod(p.Z * 2 * q.Z);
        var e = b - a;
        var f = d - c;
        var g = d + c;
        var h = b + a;
        return new Punt(Mod(e * f), Mod(g * h), Mod(f * g), Mod(e * h));
    }

    private static Punt Maal(Punt p, BigInteger factor)
    {
        var uitkomst = new Punt(BigInteger.Zero, BigInteger.One, BigInteger.One, BigInteger.Zero);
        var bits = (int)factor.GetBitLength();
        for (var i = bits - 1; i >= 0; i--)
        {
            uitkomst = Plus(uitkomst, uitkomst);
            if (!((factor >> i) & 1).IsZero)
            {
                uitkomst = Plus(uitkomst, p);
            }
        }

        return uitkomst;
    }

    private readonly record struct Punt(BigInteger X, BigInteger Y, BigInteger Z, BigInteger T);
}
