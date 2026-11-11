using System;
using System.Threading.Tasks;
using Jellyfin.Data;
using Jellyfin.Database.Implementations.Enums;
using Jellyfin.Plugin.JellyLeon.Core.Errors;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using MediaBrowser.Controller.Authentication;
using MediaBrowser.Controller.Net;
using Microsoft.AspNetCore.Http;

namespace Jellyfin.Plugin.JellyLeon.Core.Http;

/// <summary>Uitkomst van de sessiecontrole van de server.</summary>
internal sealed record SessieIdentiteit(Guid? GebruikerId, bool IsBeheerder, bool IsKid);

/// <summary>Controleert een gewone serversessie (of API-sleutel) via de officiële auth-service van de server.</summary>
internal interface ISessionAuthenticator
{
    Task<SessieIdentiteit> AuthenticeerAsync(HttpRequest verzoek);
}

/// <summary>Sessiecontrole via <see cref="IAuthService"/>; de plugin leest zelf geen tokens of wachtwoorden.</summary>
internal sealed class JellyfinSessionAuthenticator : ISessionAuthenticator
{
    private readonly IAuthService _auth;

    public JellyfinSessionAuthenticator(IAuthService auth)
    {
        _auth = auth;
    }

    public async Task<SessieIdentiteit> AuthenticeerAsync(HttpRequest verzoek)
    {
        AuthorizationInfo info;
        try
        {
            info = await _auth.Authenticate(verzoek).ConfigureAwait(false);
        }
        catch (Exception fout) when (fout is AuthenticationException or MediaBrowser.Controller.Net.SecurityException or System.Security.SecurityException)
        {
            throw Fouten.NietGeauthenticeerd("invalid_token");
        }

        if (info.IsApiKey)
        {
            return new SessieIdentiteit(null, true, false);
        }

        if (!info.IsAuthenticated || info.User is null)
        {
            throw Fouten.NietGeauthenticeerd("invalid_token");
        }

        return new SessieIdentiteit(info.User.Id, info.User.HasPermission(PermissionKind.IsAdministrator), KidPolicy.IsKid(info.User));
    }
}
