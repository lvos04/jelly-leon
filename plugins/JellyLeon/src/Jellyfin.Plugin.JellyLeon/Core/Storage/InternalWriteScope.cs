using System;
using System.IO;
using System.Security.Cryptography;

namespace Jellyfin.Plugin.JellyLeon.Core.Storage;

/// <summary>De beheerde bestandsgrens: eigen mappen, veilige ouders, exclusieve aanmaak en controle na openen.</summary>
internal sealed class InternalWriteScope
{
    private readonly JlPaths _paden;

    public InternalWriteScope(JlPaths paden)
    {
        _paden = paden;
    }

    public void SchrijfAtomisch(string pad, ReadOnlySpan<byte> inhoud)
    {
        _paden.EisVeiligBestand(pad);
        // Bestaande weigering van een onveilig oud tijdelijk pad behouden, ook al gebruiken we die naam niet meer.
        _paden.EisVeiligBestand(pad + ".tmp");
        MaakMap(Path.GetDirectoryName(Path.GetFullPath(pad))!);
        var tijdelijk = pad + "." + Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16)) + ".tmp";
        var aangemaakt = false;
        try
        {
            using (var stroom = OpenNieuw(tijdelijk))
            {
                aangemaakt = true;
                _paden.EisGeopendBestand(stroom, tijdelijk);
                stroom.Write(inhoud);
                stroom.Flush(true);
                _paden.EisGeopendBestand(stroom, tijdelijk);
            }

            _paden.EisVeiligBestand(tijdelijk);
            _paden.EisVeiligBestand(pad);
            File.Move(tijdelijk, pad, overwrite: true);
            aangemaakt = false;
        }
        finally
        {
            // Een botsing bij CreateNew is van iemand anders: dat bestand nooit verwijderen.
            if (aangemaakt)
            {
                Verwijder(tijdelijk);
            }
        }
    }

    public void SchrijfEenmalig(string pad, ReadOnlySpan<byte> inhoud)
    {
        MaakMap(Path.GetDirectoryName(Path.GetFullPath(pad))!);
        using var stroom = OpenNieuw(pad);
        _paden.EisGeopendBestand(stroom, pad);
        stroom.Write(inhoud);
        stroom.Flush(true);
    }

    public byte[]? Lees(string pad)
    {
        _paden.EisVeiligBestand(pad);
        if (!File.Exists(pad))
        {
            return null;
        }

        using var stroom = new FileStream(pad, FileMode.Open, FileAccess.Read, FileShare.Read);
        _paden.EisGeopendBestand(stroom, pad);
        using var inhoud = new MemoryStream();
        stroom.CopyTo(inhoud);
        return inhoud.ToArray();
    }

    public void KopieerNieuw(string bron, string doel)
    {
        _paden.EisVeiligBestand(bron);
        using var invoer = new FileStream(bron, FileMode.Open, FileAccess.Read, FileShare.Read);
        _paden.EisGeopendBestand(invoer, bron);
        using var uitvoer = OpenNieuw(doel);
        _paden.EisGeopendBestand(uitvoer, doel);
        invoer.CopyTo(uitvoer);
        uitvoer.Flush(true);
    }

    public void Verwijder(string pad)
    {
        _paden.EisVeiligBestand(pad);
        File.Delete(pad);
    }

    public void MaakMap(string pad)
    {
        // De wortel zelf is geen bestandspad; een fictief kind toetst dezelfde schrijfgrens.
        _paden.EisVeiligBestand(Path.Combine(pad, "x"));
        JlPaths.EisVeiligeMap(pad, maak: true);
    }

    private FileStream OpenNieuw(string pad)
    {
        _paden.EisVeiligBestand(pad);
        var opties = new FileStreamOptions { Mode = FileMode.CreateNew, Access = FileAccess.Write, Share = FileShare.None };
        if (!OperatingSystem.IsWindows())
        {
            opties.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
        }

        return new FileStream(pad, opties);
    }
}
