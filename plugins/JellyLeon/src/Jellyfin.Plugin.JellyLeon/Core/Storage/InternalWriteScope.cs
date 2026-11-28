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

    public bool MaakGeheimEenmalig(string pad, ReadOnlySpan<byte> inhoud) => SchrijfAtomisch(pad, inhoud, null, overschrijven: false);

    private bool SchrijfAtomisch(string pad, ReadOnlySpan<byte> inhoud, Action<Stream>? schrijf, bool overschrijven = true)
    {
        _paden.EisVeiligBestand(pad);
        // Een bestaand onveilig tijdelijk pad weigeren, ook bij een gewone vervanging.
        _paden.EisVeiligBestand(pad + ".tmp");
        MaakMap(Path.GetDirectoryName(Path.GetFullPath(pad))!);
        // Eén exclusieve naam ordent eerste starts, ook vanuit verschillende processen.
        var tijdelijk = overschrijven ? pad + "." + Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16)) + ".tmp" : pad + ".tmp";
        var aangemaakt = false;
        try
        {
            using (var stroom = OpenNieuw(tijdelijk))
            {
                aangemaakt = true;
                _paden.EisGeopendBestand(stroom, tijdelijk);
                if (!overschrijven && File.Exists(pad))
                {
                    return false;
                }

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

            Publiceer(tijdelijk, pad, overschrijven);
            aangemaakt = false;
            return true;
        }
        catch (IOException) when (!overschrijven && !aangemaakt && (File.Exists(tijdelijk) || File.Exists(pad)))
        {
            return false;
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

    public void Publiceer(string tijdelijk, string pad, bool overschrijven)
    {
        _paden.EisVeiligBestand(tijdelijk);
        _paden.EisVeiligBestand(pad);
        File.Move(tijdelijk, pad, overwrite: overschrijven);
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
        using var stroom = OpenGeheim(pad);
        if (stroom is null)
        {
            return null;
        }

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

    public void ControleerGeheim(string pad)
    {
        using var stroom = OpenGeheim(pad);
    }

    private FileStream? OpenGeheim(string pad)
    {
        _paden.EisVeiligBestand(pad);
        EisBeslotenMap(Path.GetDirectoryName(pad)!);
        FileStream stroom;
        try
        {
            stroom = new FileStream(pad, FileMode.Open, FileAccess.Read, FileShare.Read);
        }
        catch (IOException fout) when (fout is FileNotFoundException or DirectoryNotFoundException)
        {
            return null;
        }

        try
        {
            _paden.EisGeopendBestand(stroom, pad);
            const UnixFileMode EigenBestand = UnixFileMode.UserRead | UnixFileMode.UserWrite;
            if (!OperatingSystem.IsLinux() || File.GetUnixFileMode(stroom.SafeFileHandle) != EigenBestand)
            {
                throw new UnauthorizedAccessException("Een geheim vereist bestandsmodus 0600.");
            }

            // Het proces is UID 568 zonder capabilities. Dezelfde modus terugzetten bewijst het eigendom op de open handle.
            File.SetUnixFileMode(stroom.SafeFileHandle, EigenBestand);
            return stroom;
        }
        catch
        {
            stroom.Dispose();
            throw;
        }
    }

    public void MaakGeheimenmap(string pad)
    {
        EisBeslotenMap(pad);
        MaakMap(pad);
        EisBeslotenMap(pad);
    }

    public void ControleerGeheimenmap(string pad)
    {
        _paden.EisVeiligBestand(Path.Combine(pad, "x"));
        EisBeslotenMap(pad);
        foreach (var bestand in Directory.EnumerateFileSystemEntries(pad))
        {
            ControleerGeheim(bestand);
        }
    }

    private static void EisBeslotenMap(string pad)
    {
        const UnixFileMode EigenMap = UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
        if (!OperatingSystem.IsLinux() || JlPaths.OpslagGebruiker() != "568" ||
            (Directory.Exists(pad) && File.GetUnixFileMode(pad) != EigenMap))
        {
            throw new UnauthorizedAccessException("De geheimenmap vereist eigenaar 568 en mapmodus 0700.");
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
