using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Jellyfin.Data.Events.Users;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Secrets;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using MediaBrowser.Controller.Events;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Core.Privacy;

/// <summary>
/// Register van persoonsgegevens en de ene verwijderroute: na het verwijderen van een gebruiker staat zijn GUID in
/// geen enkele module-database meer — ook niet in die van een module die uit staat (plan §10.9).
/// </summary>
internal sealed class PrivacyService
{
    private readonly ModuleRegistry _modules;
    private readonly CoreDatabase _core;
    private readonly SecretStore _geheimen;

    public PrivacyService(ModuleRegistry modules, CoreDatabase core, SecretStore geheimen)
    {
        _modules = modules;
        _core = core;
        _geheimen = geheimen;
    }

    public IReadOnlyList<PersoonsgegevenRegel> Register()
    {
        var regels = new List<PersoonsgegevenRegel>
        {
            new("core", "idempotentie", "pseudoniem van het account (HMAC, niet terug te rekenen)", "herhaalde wijzigingen herkennen", "24 uur"),
        };
        regels.AddRange(_modules.Alle.SelectMany(m => m.Persoonsgegevens));
        return regels;
    }

    public string Pseudoniem(Guid gebruiker) => "o_" + _geheimen.OpaakId("user", gebruiker.ToString("N"));

    public int VerwijderGebruiker(Guid gebruiker)
    {
        var pseudoniem = "session:" + Pseudoniem(gebruiker);
        var verwijderd = _core.Db.Met(v => JlDatabase.Voer(v, "DELETE FROM idempotentie WHERE scope LIKE $p || '%'", ("$p", pseudoniem)));
        foreach (var module in _modules.Alle)
        {
            verwijderd += module.VerwijderGebruiker(gebruiker);
        }

        return verwijderd;
    }

    public int TelGebruiker(Guid gebruiker) => _modules.Alle.Sum(m => m.TelGebruiker(gebruiker));
}

/// <summary>De ene UserDeleted-afhandeling van de plugin (officiële gebeurtenis van de server).</summary>
internal sealed class UserDeletedConsumer : IEventConsumer<UserDeletedEventArgs>
{
    private readonly PrivacyService _privacy;
    private readonly ILogger<UserDeletedConsumer> _log;

    public UserDeletedConsumer(PrivacyService privacy, ILogger<UserDeletedConsumer> log)
    {
        _privacy = privacy;
        _log = log;
    }

    public Task OnEvent(UserDeletedEventArgs eventArgs)
    {
        var rijen = _privacy.VerwijderGebruiker(eventArgs.Argument.Id);
        _log.LogInformation("Jelly Leon: gegevens van een verwijderd account gewist ({Rijen} rijen).", rijen);
        return Task.CompletedTask;
    }
}
