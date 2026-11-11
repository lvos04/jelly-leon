using System;
using System.Text;
using System.Text.Json.Nodes;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;

namespace Jellyfin.Plugin.JellyLeon.Core.Hub;

/// <summary>De vastgelegde Hub-koppeling (JL4): sleutelset, <c>service_id</c> en moment van pinnen.</summary>
internal sealed record HubPinState(HubKeySet Sleutels, string ServiceId, string GepindOp);

/// <summary>
/// Bewaart de pin in de geheimenmap (nooit in de plugin-XML). Zonder pin is de status <c>not_linked</c> en weigert
/// elke Hub-route met 401.
/// </summary>
internal sealed class HubPin
{
    private const string Bestand = "hub-pin.json";
    private readonly SecretStore _geheimen;
    private readonly object _slot = new();
    private HubPinState? _huidig;
    private bool _geladen;

    public HubPin(SecretStore geheimen)
    {
        _geheimen = geheimen;
    }

    public HubPinState? Huidig
    {
        get
        {
            lock (_slot)
            {
                if (!_geladen)
                {
                    _huidig = Laad();
                    _geladen = true;
                }

                return _huidig;
            }
        }
    }

    public HubPinState Zet(HubKeySet sleutels, string serviceId, DateTimeOffset nu)
    {
        var staat = new HubPinState(sleutels, serviceId, nu.UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ", System.Globalization.CultureInfo.InvariantCulture));
        var json = new JsonObject { ["keyset"] = sleutels.NaarJson(), ["service_id"] = serviceId, ["gepind_op"] = staat.GepindOp };
        lock (_slot)
        {
            _geheimen.Schrijf(Bestand, Encoding.UTF8.GetBytes(json.ToJsonString()));
            _huidig = staat;
            _geladen = true;
        }

        return staat;
    }

    public void Wis()
    {
        lock (_slot)
        {
            _geheimen.Verwijder(Bestand);
            _huidig = null;
            _geladen = true;
        }
    }

    private HubPinState? Laad()
    {
        var bytes = _geheimen.Lees(Bestand);
        if (bytes is null)
        {
            return null;
        }

        try
        {
            var json = JsonNode.Parse(bytes) as JsonObject;
            var sleutels = HubKeySet.Parse(json?["keyset"], "keyset");
            return new HubPinState(sleutels, json!["service_id"]!.GetValue<string>(), json["gepind_op"]!.GetValue<string>());
        }
        catch (Exception fout) when (fout is System.Text.Json.JsonException or Errors.JlException or NullReferenceException or InvalidOperationException)
        {
            // Een onleesbare pin is geen pin: de koppeling staat dan op not_linked tot de beheerder opnieuw pint.
            return null;
        }
    }
}
