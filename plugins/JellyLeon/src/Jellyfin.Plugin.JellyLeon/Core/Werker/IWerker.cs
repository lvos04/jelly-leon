using System;
using System.Threading;
using System.Threading.Tasks;

namespace Jellyfin.Plugin.JellyLeon.Core.Werker;

/// <summary>Wat de planner van de analysewerker moet weten en kunnen (B03-018, plan §10.6).</summary>
internal interface IWerker
{
    /// <summary>Gets a value indicating whether de werker draait en een taak kan aannemen.</summary>
    bool Klaar { get; }

    /// <summary>Gets de stand in één vast woord (bijvoorbeeld <c>afwezig</c>, <c>klaar</c>, <c>gepauzeerd</c>).</summary>
    string Stand { get; }

    /// <summary>Gets de reden bij een stand die niet <c>klaar</c> is; een vast woord, nooit een pad of melding.</summary>
    string Reden { get; }

    /// <summary>Gets het moment waarop de werker de laatste pauze bevestigde; <c>null</c> als dat nog niet gebeurde.</summary>
    DateTimeOffset? PauzeBevestigdOp { get; }

    /// <summary>Zet de lopende taak stil (de hele procesgroep). Gooit nooit; <c>false</c> als er niets te pauzeren viel.</summary>
    Task<bool> PauzeerAsync(CancellationToken annulering);

    /// <summary>Laat de gepauzeerde taak verder gaan. Gooit nooit.</summary>
    Task<bool> HervatAsync(CancellationToken annulering);
}

/// <summary>Er is geen werker (geen interpreter in dit image, of geen module met jobs): er draait dan ook niets.</summary>
internal sealed class GeenWerker : IWerker
{
    public bool Klaar => false;

    public string Stand => "afwezig";

    public string Reden => "werker_niet_beschikbaar";

    public DateTimeOffset? PauzeBevestigdOp => null;

    public Task<bool> PauzeerAsync(CancellationToken annulering) => Task.FromResult(false);

    public Task<bool> HervatAsync(CancellationToken annulering) => Task.FromResult(false);
}
