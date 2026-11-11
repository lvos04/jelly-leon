using System;
using System.IO;

namespace Jellyfin.Plugin.JellyLeon.Core.Storage;

/// <summary>
/// De enige weg waarlangs een module een bestand schrijft (plan §10.9): alleen onder de eigen data- en cachemap.
/// De analyzer (JL0002) verbiedt directe schrijfaanroepen buiten Core.Storage en Core.Secrets.
/// </summary>
internal sealed class InternalWriteScope
{
    private readonly JlPaths _paden;

    public InternalWriteScope(JlPaths paden)
    {
        _paden = paden;
    }

    public void SchrijfAtomisch(string pad, ReadOnlySpan<byte> inhoud)
    {
        Eis(pad);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(pad))!);
        var tijdelijk = pad + ".tmp";
        using (var stroom = new FileStream(tijdelijk, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            stroom.Write(inhoud);
            stroom.Flush(true);
        }

        File.Move(tijdelijk, pad, overwrite: true);
    }

    public void Verwijder(string pad)
    {
        Eis(pad);
        File.Delete(pad);
    }

    public void MaakMap(string pad)
    {
        Eis(Path.Combine(pad, "x"));
        Directory.CreateDirectory(pad);
    }

    private void Eis(string pad)
    {
        if (!_paden.MagSchrijven(pad))
        {
            throw new UnauthorizedAccessException("Schrijven buiten de eigen mappen van Jelly Leon is niet toegestaan.");
        }
    }
}
