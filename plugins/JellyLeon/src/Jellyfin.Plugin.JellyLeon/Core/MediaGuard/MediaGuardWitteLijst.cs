using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Jellyfin.Plugin.JellyLeon.Core.MediaGuard;

/// <summary>Eén toegestane MediaGuard-route met de velden die Jelly Leon eruit mag overnemen.</summary>
/// <param name="Id">Vaste naam van de route binnen de plugin.</param>
/// <param name="Methode">HTTP-methode; alleen GET, plus het niet-muterende POST van <c>audio/inspect</c>.</param>
/// <param name="Pad">Het pad bij MediaGuard.</param>
/// <param name="Velden">Veldenwitte lijst: paden met punten, <c>[]</c> voor "elk element". Leeg = nog niet bruikbaar.</param>
internal sealed record MgRoute(string Id, string Methode, string Pad, IReadOnlyList<string> Velden)
{
    /// <summary>Een route zonder veldenlijst staat wel op de routewitte lijst, maar wordt nog niet aangeroepen.</summary>
    public bool Bruikbaar => Velden.Count > 0;
}

/// <summary>
/// De route- en veldenwitte lijst van de ene MediaGuard-viewerclient (B03-009, contract 1.3 §2.3, plan §10.5). Alles wat
/// hier niet staat bestaat voor Jelly Leon niet: geen andere route, geen ander veld. <c>sessions</c>, <c>hold.reason</c>,
/// <c>actions</c>, <c>tests</c> en <c>last</c> staan er bewust niet in (die zeggen wie wat kijkt).
/// </summary>
internal static class MediaGuardWitteLijst
{
    public static readonly MgRoute AuthMe = new("auth.me", "GET", "/api/v1/auth/me", ["role"]);

    public static readonly MgRoute AppStatus = new("app.status", "GET", "/api/v1/app/status", ["encoder.reachable", "encoder.lanes[].lane", "encoder.lanes[].running", "encoder.lanes[].slots", "encoder.lanes[].paused"]);

    public static readonly MgRoute MediaserverStatus = new("mediaserver.status", "GET", "/api/v1/mediaserver/status", ["kind", "url", "connected", "hold.active", "subtitles.source", "subtitles.nl_wanted", "subtitles.nl_auto", "subtitles.missing"]);

    /// <summary>Alle routes van de witte lijst. De routes zonder veldenlijst krijgen die van de module die ze nodig heeft.</summary>
    public static readonly IReadOnlyList<MgRoute> Alle =
    [
        AuthMe,
        AppStatus,
        MediaserverStatus,
        new("encoding.resources", "GET", "/api/v1/encoding/resources", []),
        new("encoding.capabilities", "GET", "/api/v1/encoding/capabilities", []),
        new("mediaserver.subtitles.missing", "GET", "/api/v1/mediaserver/subtitles/missing", []),
        new("policy.effective", "GET", "/api/v1/policy/effective", []),
        new("recovery.transaction", "GET", "/api/v1/recovery/transactions/{id}", []),
        new("audio.inspect", "POST", "/api/v1/audio/inspect", []),
    ];

    /// <summary>Staat deze route (zelfde object, dus zelfde methode en pad) op de witte lijst?</summary>
    public static bool Bevat(MgRoute route) => Alle.Any(r => ReferenceEquals(r, route));

    /// <summary>
    /// Neemt uit een ruw antwoord alleen de velden van de witte lijst over. Alleen enkelvoudige waarden (tekst, getal,
    /// waar/onwaar) komen mee; een object of lijst op de plek van een blad vervalt, zodat er nooit een hele tak meelift.
    /// </summary>
    public static JsonObject Filter(JsonNode? ruw, IReadOnlyList<string> velden)
    {
        var uit = new JsonObject();
        foreach (var veld in velden)
        {
            Neem(ruw, uit, veld.Split('.'), 0);
        }

        return uit;
    }

    private static void Neem(JsonNode? bron, JsonObject doel, string[] delen, int index)
    {
        if (bron is not JsonObject bronObject)
        {
            return;
        }

        var deel = delen[index];
        var lijst = deel.EndsWith("[]", StringComparison.Ordinal);
        var naam = lijst ? deel[..^2] : deel;
        if (!bronObject.TryGetPropertyValue(naam, out var waarde) || waarde is null)
        {
            return;
        }

        if (lijst)
        {
            if (waarde is not JsonArray bronLijst || index == delen.Length - 1)
            {
                return;
            }

            if (doel[naam] is not JsonArray doelLijst)
            {
                doelLijst = [];
                doel[naam] = doelLijst;
            }

            for (var i = 0; i < bronLijst.Count; i++)
            {
                if (doelLijst.Count <= i)
                {
                    doelLijst.Add(new JsonObject());
                }

                Neem(bronLijst[i], doelLijst[i]!.AsObject(), delen, index + 1);
            }

            return;
        }

        if (index == delen.Length - 1)
        {
            if (waarde is JsonValue blad && blad.GetValueKind() is JsonValueKind.String or JsonValueKind.Number or JsonValueKind.True or JsonValueKind.False)
            {
                doel[naam] = blad.DeepClone();
            }

            return;
        }

        if (waarde is not JsonObject)
        {
            return;
        }

        if (doel[naam] is not JsonObject doelObject)
        {
            doelObject = new JsonObject();
            doel[naam] = doelObject;
        }

        Neem(waarde, doelObject, delen, index + 1);
    }
}
