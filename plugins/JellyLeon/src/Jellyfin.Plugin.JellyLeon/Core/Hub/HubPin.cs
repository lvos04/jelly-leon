using System;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;

namespace Jellyfin.Plugin.JellyLeon.Core.Hub;

/// <summary>De vastgelegde Hub-koppeling (JL4): sleutelset, <c>service_id</c> en moment van pinnen.</summary>
internal sealed record HubPinState(HubKeySet Sleutels, string ServiceId, string GepindOp);

/// <summary>Bewaart de pin in de geheimenmap. Alleen een veilig leesbare pin geeft de Hub toegang.</summary>
internal sealed class HubPin
{
    private const string Bestand = "hub-pin.json";
    private const string Tijdformaat = "yyyy-MM-dd'T'HH:mm:ss'Z'";
    private readonly SecretStore _geheimen;
    private readonly object _slot = new();
    private byte[]? _laatsteBytes;
    private HubPinState? _laatstePin;

    public HubPin(SecretStore geheimen)
    {
        _geheimen = geheimen;
    }

    public HubPinState? Huidig => LeesStatus().Pin;

    public (HubPinState? Pin, bool Onleesbaar) LeesStatus()
    {
        lock (_slot)
        {
            try
            {
                // Ook na rotatie, verwijdering of gewijzigde rechten geldt de toestand van het bestand.
                // De eigen opslagvorm voor maximaal zestien publieke sleutels past binnen 32 KiB.
                var bytes = _geheimen.Lees(Bestand, 32 * 1024);
                if (bytes is null)
                {
                    return (null, false);
                }

                if (_laatstePin is not null && bytes.AsSpan().SequenceEqual(_laatsteBytes))
                {
                    return (_laatstePin, false);
                }

                var json = JsonNode.Parse(bytes, documentOptions: new JsonDocumentOptions { AllowDuplicateProperties = false, MaxDepth = 16 });
                if (json is not JsonObject o || o["service_id"] is not JsonValue id || !id.TryGetValue<string>(out var serviceId)
                    || serviceId.Length != 36 || !Guid.TryParseExact(serviceId, "D", out _)
                    || o["gepind_op"] is not JsonValue tijd || !tijd.TryGetValue<string>(out var gepindOp)
                    || !DateTimeOffset.TryParseExact(gepindOp, Tijdformaat, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out _))
                {
                    return (null, true);
                }

                _laatstePin = new HubPinState(HubKeySet.Parse(o["keyset"], "keyset"), serviceId, gepindOp);
                _laatsteBytes = bytes;
                return (_laatstePin, false);
            }
            catch (Exception fout) when (fout is JlException or JsonException or InvalidOperationException or ArgumentException)
            {
                return (null, true);
            }
        }
    }

    public HubPinState Zet(HubKeySet sleutels, string serviceId, DateTimeOffset nu)
    {
        var staat = new HubPinState(sleutels, serviceId, nu.UtcDateTime.ToString(Tijdformaat, CultureInfo.InvariantCulture));
        var json = new JsonObject { ["keyset"] = sleutels.NaarJson(), ["service_id"] = serviceId, ["gepind_op"] = staat.GepindOp };
        lock (_slot)
        {
            _geheimen.Schrijf(Bestand, Encoding.UTF8.GetBytes(json.ToJsonString()));
        }

        return staat;
    }

    public void Wis()
    {
        lock (_slot)
        {
            _geheimen.Verwijder(Bestand);
            _laatstePin = null;
            _laatsteBytes = null;
        }
    }
}
