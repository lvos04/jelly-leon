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

    public void SchrijfAtomisch(string pad, ReadOnlySpan<byte> inhoud) => SchrijfAtomisch(pad, inhoud, null);

    public void SchrijfAtomisch(string pad, Action<Stream> schrijf) => SchrijfAtomisch(pad, default, schrijf);

    private void SchrijfAtomisch(string pad, ReadOnlySpan<byte> inhoud, Action<Stream>? schrijf)
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
                if (schrijf is null)
                {
                    stroom.Write(inhoud);
                }
                else
                {
                    schrijf(stroom);
                }

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

    public byte[]? LeesGeheim(string pad, int maxBytes)
    {
        _paden.EisVeiligBestand(pad);
        EisBeslotenMap(Path.GetDirectoryName(pad)!);
        try
        {
            using var stroom = new FileStream(pad, FileMode.Open, FileAccess.Read, FileShare.Read);
            _paden.EisGeopendBestand(stroom, pad);
            const UnixFileMode EigenBestand = UnixFileMode.UserRead | UnixFileMode.UserWrite;
            if (!OperatingSystem.IsLinux() || File.GetUnixFileMode(stroom.SafeFileHandle) != EigenBestand)
            {
                throw new UnauthorizedAccessException("Een geheim vereist bestandsmodus 0600.");
            }

            // Dezelfde eigendomsproef als JlPaths, nu op het gecontroleerde open bestand.
            File.SetUnixFileMode(stroom.SafeFileHandle, EigenBestand);
            var lengte = stroom.Length;
            if (lengte > maxBytes)
            {
                throw new IOException("Het geheim overschrijdt de verwachte omvang.");
            }

            var inhoud = new byte[(int)lengte];
            stroom.ReadExactly(inhoud);
            if (stroom.ReadByte() != -1)
            {
                throw new IOException("Het geheim veranderde tijdens het lezen.");
            }

            return inhoud;
        }
        catch (IOException fout) when (fout is FileNotFoundException or DirectoryNotFoundException)
        {
            return null;
        }
    }

    public void MaakGeheimenmap(string pad)
    {
        MaakMap(pad);
        EisBeslotenMap(pad);
    }

    private static void EisBeslotenMap(string pad)
    {
        const UnixFileMode EigenMap = UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
        if (Directory.Exists(pad) && (!OperatingSystem.IsLinux() || File.GetUnixFileMode(pad) != EigenMap))
        {
            throw new UnauthorizedAccessException("De geheimenmap vereist mapmodus 0700.");
        }
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
        JlPaths.EisVeiligeMap(pad, maak: true, _paden.EigenTmpfs);
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
