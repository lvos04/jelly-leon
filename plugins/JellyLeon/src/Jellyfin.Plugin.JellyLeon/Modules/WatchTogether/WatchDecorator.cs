using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using MediaBrowser.Controller.Session;
using MediaBrowser.Controller.SyncPlay;
using MediaBrowser.Controller.SyncPlay.Requests;
using MediaBrowser.Model.SyncPlay;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyLeon.Modules.WatchTogether;

/// <summary>Delegeert alle zeven leden. Alleen na een groepsmutatie leest WT-1 de werkelijke servergroep terug.</summary>
internal sealed class WatchDecorator(ISyncPlayManager inner, ISessionManager sessies, IModuleSwitches schakelaars,
    Func<WatchTogetherModule> opslag, TimeProvider klok, ILogger<WatchDecorator> log) : ISyncPlayManager
{
    private readonly Lock _slot = new();
    private readonly Dictionary<string, (Guid Groep, Guid Gebruiker)> _leden = new(StringComparer.OrdinalIgnoreCase);

    public GroupInfoDto NewGroup(SessionInfo session, NewGroupRequest request, CancellationToken cancellationToken)
    {
        if (!schakelaars.IsAan(WatchTogetherModule.ModuleSlug))
        {
            return inner.NewGroup(session, request, cancellationToken);
        }

        lock (_slot)
        {
            var groep = inner.NewGroup(session, request, cancellationToken);
            _leden[session.Id] = (groep.GroupId, session.UserId);
            Bewaar(() =>
            {
                var module = opslag();
                module.Start(klok.GetUtcNow());
                module.Noteer(groep.GroupId, session.UserId, klok.GetUtcNow());
                Controleer("reconcile", session);
            });
            return groep;
        }
    }

    public void JoinGroup(SessionInfo session, JoinGroupRequest request, CancellationToken cancellationToken)
    {
        if (!schakelaars.IsAan(WatchTogetherModule.ModuleSlug))
        {
            inner.JoinGroup(session, request, cancellationToken);
            return;
        }

        lock (_slot)
        {
            inner.JoinGroup(session, request, cancellationToken);
            Bewaar(() =>
            {
                // JoinGroup retourneert ook normaal als upstream de toegang weigert.
                if (inner.GetGroup(session, request.GroupId)?.Participants.Contains(session.UserName, StringComparer.Ordinal) == true)
                {
                    _leden[session.Id] = (request.GroupId, session.UserId);
                    var module = opslag();
                    module.Start(klok.GetUtcNow());
                    module.Noteer(request.GroupId, null, klok.GetUtcNow());
                }

                Controleer("reconcile", session);
            });
        }
    }

    public void LeaveGroup(SessionInfo session, LeaveGroupRequest request, CancellationToken cancellationToken)
    {
        if (!schakelaars.IsAan(WatchTogetherModule.ModuleSlug))
        {
            inner.LeaveGroup(session, request, cancellationToken);
            return;
        }

        lock (_slot)
        {
            inner.LeaveGroup(session, request, cancellationToken);
            _leden.Remove(session.Id);
            Bewaar(() => Controleer("reconcile", session));
        }
    }

    public GroupInfoDto GetGroup(SessionInfo session, Guid groupId) => inner.GetGroup(session, groupId);
    public List<GroupInfoDto> ListGroups(SessionInfo session, ListGroupsRequest request) => inner.ListGroups(session, request);
    public void HandleRequest(SessionInfo session, IGroupPlaybackRequest request, CancellationToken cancellationToken) =>
        inner.HandleRequest(session, request, cancellationToken);
    public bool IsUserActive(Guid userId) => inner.IsUserActive(userId);

    public void ControleerSessies(SessionInfo? afgelopen)
    {
        lock (_slot)
        {
            if (afgelopen is not null)
            {
                _leden.Remove(afgelopen.Id);
            }

            if (schakelaars.IsAan(WatchTogetherModule.ModuleSlug))
            {
                Bewaar(() => Controleer(afgelopen is null ? "reconcile" : "session_ended", afgelopen));
            }
            else
            {
                _leden.Clear();
            }
        }
    }

    public bool IsLid(Guid groep, Guid gebruiker)
    {
        lock (_slot)
        {
            return _leden.Values.Contains((groep, gebruiker));
        }
    }

    private void Controleer(string reden, SessionInfo? aanleiding)
    {
        var module = opslag();
        var nu = klok.GetUtcNow();
        var live = sessies.Sessions.Where(s => s.UserId != Guid.Empty).ToArray();
        foreach (var id in module.Actief())
        {
            // GetGroup past bibliotheekrechten toe. Eén geweigerde waarnemer bewijst geen einde.
            if ((aanleiding is not null && inner.GetGroup(aanleiding, id) is not null)
                || live.Any(s => inner.GetGroup(s, id) is not null)
                || live.Any(s => _leden.TryGetValue(s.Id, out var lid) && lid == (id, s.UserId) && inner.IsUserActive(s.UserId)))
            {
                continue;
            }

            module.Beeindig(id, reden, nu);
            foreach (var sleutel in _leden.Where(p => p.Value.Groep == id).Select(p => p.Key).ToArray())
            {
                _leden.Remove(sleutel);
            }
        }

        module.VerzendEnRuimOp(nu);
    }

    private void Bewaar(Action werk)
    {
        try
        {
            werk();
        }
        catch (Exception fout) when (fout is JlException or InvalidOperationException or System.IO.IOException or UnauthorizedAccessException)
        {
            // De upstream-mutatie is uitgevoerd. Een mislukte waarneming mag het afspelen niet onderbreken.
            log.LogWarning("Watch Together kon de groepsmetadata niet bijwerken.");
        }
    }
}
