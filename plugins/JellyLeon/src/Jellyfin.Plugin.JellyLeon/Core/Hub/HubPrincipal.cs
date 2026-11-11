using System.Collections.Generic;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Core.Hub;

/// <summary>De geverifieerde afzender van een Hub-token (contract §4.2 en §4.3).</summary>
internal sealed record HubPrincipal(string Subject, bool IsService, IReadOnlyList<string> Rollen, string Jti, long Exp)
{
    /// <summary>De rol kind wint altijd (contract §4.2).</summary>
    public bool IsKind => Rollen.Contains("kind");

    public string Id => IsService ? "service:hub" : "hub-user:" + Subject;
}
