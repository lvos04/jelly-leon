using System;
using System.Threading;
using System.Threading.Tasks;

namespace Jellyfin.Plugin.JellyLeon.Core.MediaGuard;

/// <summary>Een ruw antwoord van MediaGuard. Leeft alleen binnen de client en wordt nooit gelogd of bewaard.</summary>
internal readonly record struct MgAntwoord(int Status, ReadOnlyMemory<byte> Body);

/// <summary>
/// De weg naar MediaGuard. Besluit BG-04: die loopt via de Hub (Jelly Leon heeft zelf geen MediaGuard-sleutel). De
/// client kent alleen deze grens; welke route de Hub daarvoor aanbiedt hoort in het contract (ADR-0034).
/// </summary>
internal interface IMediaGuardVervoer
{
    /// <summary>Gets a value indicating whether er een weg naar MediaGuard is. Zonder weg doet de client geen enkele aanroep.</summary>
    bool Beschikbaar { get; }

    /// <summary>Vraagt één route van de witte lijst op.</summary>
    Task<MgAntwoord> VraagAsync(MgRoute route, CancellationToken annulering);
}

/// <summary>
/// De standaard: er is geen weg naar MediaGuard, want contract 1.3 kent nog geen Hub-route waarlangs Jelly Leon
/// MediaGuard-gegevens kan opvragen. De status blijft dan <c>onbekend</c>; er wordt niets gesimuleerd.
/// </summary>
internal sealed class GeenMediaGuardVervoer : IMediaGuardVervoer
{
    public bool Beschikbaar => false;

    public Task<MgAntwoord> VraagAsync(MgRoute route, CancellationToken annulering) =>
        throw new InvalidOperationException("Er is geen weg naar MediaGuard (BG-04: via de Hub; die route bestaat nog niet).");
}
