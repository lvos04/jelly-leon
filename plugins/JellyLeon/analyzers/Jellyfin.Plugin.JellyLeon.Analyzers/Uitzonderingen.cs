using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.IO;
using System.Linq;
using System.Threading;
using Microsoft.CodeAnalysis;

namespace Jellyfin.Plugin.JellyLeon.Analyzers;

/// <summary>
/// De witte lijst: per regel één API en één klasse (<c>JL0001 Type.Methode Volledige.Klassenaam</c>). Een regel die
/// niet precies past is een bouwfout, zodat een tikfout nooit stil iets toestaat of stil genegeerd wordt.
/// </summary>
internal sealed class Uitzonderingen
{
    private readonly HashSet<string> _toegestaan = new(StringComparer.Ordinal);

    public List<(string Regel, string Reden)> Fouten { get; } = new();

    public bool Bevat(string regelId, string api, string klasse) => _toegestaan.Contains(regelId + " " + api + " " + klasse);

    public static Uitzonderingen Lees(ImmutableArray<AdditionalText> bestanden, CancellationToken stop)
    {
        var resultaat = new Uitzonderingen();
        foreach (var bestand in bestanden.Where(b => string.Equals(Path.GetFileName(b.Path), Regels.UitzonderingenBestand, StringComparison.Ordinal)))
        {
            var tekst = bestand.GetText(stop);
            if (tekst is null)
            {
                continue;
            }

            foreach (var regel in tekst.Lines.Select(l => l.ToString().Trim()).Where(l => l.Length > 0 && l[0] != '#'))
            {
                resultaat.Voeg(regel);
            }
        }

        return resultaat;
    }

    private void Voeg(string regel)
    {
        var delen = regel.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
        if (delen.Length != 3)
        {
            Fouten.Add((regel, "verwacht: <regel-id> <Type.Methode> <volledige klassenaam>"));
            return;
        }

        var (regelId, api, klasse) = (delen[0], delen[1], delen[2]);
        var punt = api.LastIndexOf('.');
        var type = punt > 0 ? api.Substring(0, punt) : string.Empty;
        var lid = punt > 0 ? api.Substring(punt + 1) : string.Empty;
        var typeRegel = Regels.Typen.FirstOrDefault(t => t.RegelId == regelId && t.Type == type);
        if (typeRegel is null || !typeRegel.IsVerboden(lid))
        {
            Fouten.Add((regel, "deze API wordt door deze regel niet bewaakt"));
        }
        else if (!typeRegel.UitzonderingMogelijk)
        {
            Fouten.Add((regel, "voor deze API bestaat geen uitzondering (nergens toegestaan)"));
        }
        else if (!klasse.StartsWith(Regels.PluginNamespace + ".Modules.", StringComparison.Ordinal) || klasse.EndsWith(".", StringComparison.Ordinal) || klasse.Contains("*"))
        {
            Fouten.Add((regel, "een uitzondering geldt voor precies één klasse onder " + Regels.PluginNamespace + ".Modules"));
        }
        else if (!_toegestaan.Add(regelId + " " + api + " " + klasse))
        {
            Fouten.Add((regel, "dubbele regel"));
        }
    }
}
