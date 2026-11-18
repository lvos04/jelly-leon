using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;

namespace Jellyfin.Plugin.JellyLeon.Core.Storage;

/// <summary>
/// De enige schrijfplekken van de pluginlaag (plan §10.9): <c>&lt;data&gt;/jelly-leon/**</c> en
/// <c>&lt;cache&gt;/jelly-leon/**</c>. Nooit een mediamap, nooit de database van de server.
/// </summary>
internal sealed class JlPaths
{
    /// <summary>Zoveel symbolische koppelingen volgt het pad hooguit (zoals de kernel); daarboven is het geen eigen plek.</summary>
    private const int MaxKoppelingen = 40;

    private const string RunWortel = "/run/jelly-leon";

    public JlPaths(string dataPath, string cachePath)
        : this(dataPath, cachePath, OperatingSystem.IsLinux() ? File.ReadLines("/proc/self/mountinfo") : [])
    {
    }

    /// <param name="dataPath">De datamap van de server.</param>
    /// <param name="cachePath">De cachemap van de server.</param>
    /// <param name="mountinfo">De regels van <c>/proc/self/mountinfo</c> (tests geven een eigen tabel).</param>
    internal JlPaths(string dataPath, string cachePath, IEnumerable<string> mountinfo)
    {
        if (new[] { dataPath, cachePath }.Any(p => Path.GetFullPath(p).TrimEnd('/') is "" or "/tmp" or "/run"))
        {
            throw new UnauthorizedAccessException("Een systeemouder is geen eigen gegevensmap van Jelly Leon.");
        }

        DataRoot = Path.GetFullPath(Path.Combine(dataPath, "jelly-leon"));
        CacheRoot = Path.GetFullPath(Path.Combine(cachePath, "jelly-leon"));
        var cacheMap = Path.GetDirectoryName(CacheRoot)!;
        EigenTmpfs = IsEigenTmpfs(cacheMap, mountinfo) ? cacheMap : null;
        EisVeiligeMap(DataRoot, maak: false);
        EisVeiligeMap(CacheRoot, maak: false, EigenTmpfs);
    }

    public string DataRoot { get; }

    public string CacheRoot { get; }

    /// <summary>
    /// De cachemap van de server als die een eigen tmpfs van deze container is (deel 1f, BN-1), anders null. Zo'n tmpfs
    /// (opslagtype tmpfs) krijgt zijn eigenaar en modus (ook 1777) van Docker of TrueNAS. Een lege gedeelde tmpfs (Host
    /// Path /dev/shm) is hier niet van te onderscheiden (deel 1g; CUSTOM_APP.md, Verplicht 3). Alleen voor de cache: de
    /// datamap blijft even streng.
    /// </summary>
    public string? EigenTmpfs { get; }

    public string SecretsDir => Path.Combine(DataRoot, "secrets");

    public string CoreDb => Path.Combine(DataRoot, "core", "core.db");

    /// <summary>Map van de unix-socket van de analysewerker: /run/jelly-leon als die bestaat, anders onder de cache.</summary>
    public string RunDir => Directory.Exists(RunWortel) ? RunWortel : Path.Combine(CacheRoot, "run");

    public string ModuleDir(string slug) => Path.Combine(DataRoot, slug);

    public string ModuleDb(string slug) => Path.Combine(ModuleDir(slug), slug + ".db");

    /// <summary>
    /// Is <paramref name="pad"/> een toegestane schrijfplek van de pluginlaag? Twee eisen (HARDE EIS, ADR-0032): het pad
    /// zoals het er staat ligt in een eigen map, en het echte pad ook. Het echte pad volgt elke symbolische koppeling
    /// zoals het besturingssysteem dat doet: het bestand zelf en elke bovenliggende map, relatief of in een keten, en
    /// <c>..</c> na het volgen. Een eigen map die zelf een koppeling is, telt niet als eigen plek.
    /// </summary>
    public bool MagSchrijven(string pad)
    {
        var wortels = new[] { DataRoot, CacheRoot, RunWortel };
        var vol = Path.GetFullPath(pad);
        if (!wortels.Any(w => Binnen(vol, w)))
        {
            return false;
        }

        // Niet de tekstueel opgeschoonde vorm volgen: na een koppeling betekent ".." de ouder van het doel.
        return EchtInEigenMap(pad);
    }

    /// <summary>
    /// Alleen de tweede eis van <see cref="MagSchrijven"/>: het echte pad van <paramref name="pad"/> ligt in een eigen map.
    /// Voor een pad dat zelf al een echt pad is (zoals de naam waaronder SQLite de bestanden naast een database zet),
    /// waar de eerste eis (het pad zoals het er staat) niets toevoegt.
    /// </summary>
    public bool EchtInEigenMap(string pad)
    {
        var echt = EchtPad(Path.IsPathRooted(pad) ? pad : Path.Combine(Directory.GetCurrentDirectory(), pad));
        return echt is not null && new[] { DataRoot, CacheRoot, RunWortel }.Any(w => EchteWortel(w) is { } e && Binnen(echt, e));
    }

    /// <summary>
    /// Het echte pad: elke bestaande symbolische koppeling in <paramref name="pad"/> (absoluut) is vervangen door haar
    /// doel, <c>.</c> is weggelaten en <c>..</c> gaat naar de ouder van het echte pad tot dan toe. Wat (nog) niet bestaat,
    /// blijft zoals het er staat. Null bij meer dan <see cref="MaxKoppelingen"/> koppelingen (een lus).
    /// </summary>
    internal static string? EchtPad(string pad)
    {
        var stappen = 0;
        return Volg(pad, ref stappen);
    }

    private static string? Volg(string pad, ref int stappen)
    {
        var wortel = Path.GetPathRoot(pad);
        if (string.IsNullOrEmpty(wortel))
        {
            return null;
        }

        var huidig = wortel;
        foreach (var deel in pad[wortel.Length..].Split([Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar], StringSplitOptions.RemoveEmptyEntries))
        {
            if (deel == ".")
            {
                continue;
            }

            if (deel == "..")
            {
                huidig = Path.GetDirectoryName(huidig) ?? wortel;
                continue;
            }

            var volgende = Path.Combine(huidig, deel);
            var doel = new FileInfo(volgende).LinkTarget;
            if (doel is null)
            {
                huidig = volgende;
                continue;
            }

            if (++stappen > MaxKoppelingen)
            {
                return null;
            }

            // Een relatief doel geldt vanaf de map waarin de koppeling staat.
            var opgelost = Volg(Path.IsPathRooted(doel) ? doel : Path.Combine(huidig, doel), ref stappen);
            if (opgelost is null)
            {
                return null;
            }

            huidig = opgelost;
        }

        return huidig;
    }

    /// <summary>
    /// Is <paramref name="map"/> zelf het koppelpunt van een heel tmpfs-bestandssysteem (wortel "/", dus geen gekoppelde
    /// map van de host)? Vastgesteld uit de mounttabel (<c>/proc/self/mountinfo</c>), niet uit de naam; bij gestapelde
    /// mounts telt de laatste. Een tmpfs uit het formulier maakt Docker bij elke start nieuw; de start van de container
    /// eist bovendien dat hij dan leeg is (ADR-0032, deel 1f).
    /// </summary>
    internal static bool IsEigenTmpfs(string map, IEnumerable<string> mountinfo)
    {
        var doel = Path.GetFullPath(map).TrimEnd('/');
        bool? uitkomst = null;
        foreach (var regel in mountinfo)
        {
            var delen = regel.Split(" - ", 2);
            var links = delen[0].Split(' ');
            if (delen.Length != 2 || links.Length < 6 || Ontsnap(links[4]) != doel)
            {
                continue;
            }

            uitkomst = delen[1].Split(' ')[0] == "tmpfs" && links[3] == "/";
        }

        return uitkomst ?? false;
    }

    /// <summary>Controleert elke bestaande ouder, ook boven de eigen wortel; nieuwe mappen zijn 0700.</summary>
    /// <param name="pad">De map.</param>
    /// <param name="maak">Ontbrekende mappen aanmaken (0700).</param>
    /// <param name="eigenTmpfs">De cachemap als die een eigen tmpfs van deze container is (zie <see cref="EigenTmpfs"/>).</param>
    internal static void EisVeiligeMap(string pad, bool maak, string? eigenTmpfs = null)
    {
        if (!OperatingSystem.IsLinux())
        {
            throw new PlatformNotSupportedException("Veilige opslag van Jelly Leon vereist de gecontroleerde Linux-omgeving.");
        }

        // Zonder CAP_FOWNER mag uitsluitend de eigenaar chmod uitvoeren. Dezelfde modus terugzetten is een
        // beheerde eigendomsproef; geen P/Invoke, geen rechtenreparatie. Zie ADR-0032, opslagdreigingen deel 1b.
        var status = File.ReadAllLines("/proc/self/status");
        var uid = status.First(l => l.StartsWith("Uid:", StringComparison.Ordinal)).Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        var caps = status.First(l => l.StartsWith("CapEff:", StringComparison.Ordinal)).Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        if (uid.Length != 5 || uid[1] == "0" || uid.Skip(1).Any(u => u != uid[1]) || caps.Length != 2
            || ulong.Parse(caps[1], NumberStyles.HexNumber, CultureInfo.InvariantCulture) != 0)
        {
            throw new UnauthorizedAccessException("Jelly Leon-opslag vereist één niet-rootgebruiker zonder effectieve capabilities.");
        }

        ControleerMap(Path.GetFullPath(pad), maak, eigenTmpfs);
    }

    private static void ControleerMap(string pad, bool maak, string? eigenTmpfs)
    {
        if (!OperatingSystem.IsLinux())
        {
            throw new PlatformNotSupportedException("Veilige opslag vereist Linux.");
        }

        var ouder = Path.GetDirectoryName(pad);
        if (ouder is not null)
        {
            ControleerMap(ouder, maak, eigenTmpfs);
        }

        if (new FileInfo(pad).LinkTarget is not null)
        {
            throw new UnauthorizedAccessException("Een opslagmap of bovenliggende map van Jelly Leon mag geen symbolische koppeling zijn.");
        }

        if (!Directory.Exists(pad))
        {
            if (!maak)
            {
                return;
            }

            Directory.CreateDirectory(pad, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        }

        // Een eigen tmpfs van deze container (alleen de cachemap): niemand buiten de container kan daarin iets neerleggen.
        if (pad == eigenTmpfs)
        {
            return;
        }

        var modus = File.GetUnixFileMode(pad);
        // Alleen de vaste, sticky systeemmap /tmp is gedeeld: andere gebruikers kunnen de eigen ingang niet wisselen.
        if ((modus & (UnixFileMode.GroupWrite | UnixFileMode.OtherWrite)) != 0
            && !(pad == "/tmp" && (modus & UnixFileMode.StickyBit) != 0))
        {
            throw new UnauthorizedAccessException("Een opslagmap of bovenliggende map van Jelly Leon is voor groep of anderen beschrijfbaar; start geweigerd.");
        }

        // Vaste systeemouders uit de vertrouwde containerimage. Elke andere ouder moet van de procesgebruiker zijn.
        if (pad is "/" or "/tmp" or "/run")
        {
            return;
        }

        try
        {
            File.SetUnixFileMode(pad, modus);
        }
        catch (UnauthorizedAccessException)
        {
            throw new UnauthorizedAccessException("Een opslagmap of bovenliggende map van Jelly Leon is niet van de eigen gebruiker; start geweigerd.");
        }
    }

    /// <summary>Een schrijfnaam zonder koppelingen en met veilige ouders, ook bij elke latere bewerking.</summary>
    internal void EisVeiligBestand(string pad)
    {
        if (!MagSchrijven(pad) || new FileInfo(pad).LinkTarget is not null)
        {
            throw new UnauthorizedAccessException("Opslag buiten de eigen mappen of via een koppeling is niet toegestaan.");
        }

        EisVeiligeMap(Path.GetDirectoryName(Path.GetFullPath(pad))!, maak: false, EigenTmpfs);
        if (!OperatingSystem.IsLinux())
        {
            throw new PlatformNotSupportedException("Controle van opslagrechten vereist Linux.");
        }

        if (File.Exists(pad) && (File.GetUnixFileMode(pad) & (UnixFileMode.GroupWrite | UnixFileMode.OtherWrite)) != 0)
        {
            throw new UnauthorizedAccessException("Een opslagbestand van Jelly Leon is voor groep of anderen beschrijfbaar; bewerking geweigerd.");
        }
    }

    /// <summary>
    /// Deel 1f (B1, optie A3): de pluginconfiguratie die de server leest en bij een mislukte lezing of een opslag met
    /// <c>FileMode.Create</c> schrijft (volgt een koppeling). Vóór elke lezing of opslag door de plugin: de map en haar ouders
    /// zoals bij de eigen opslag, en het bestand zelf geen symbolische koppeling of map. Een harde koppeling of FIFO is in
    /// beheerde code niet te zien (die weigert de start); de serverroute voor pluginconfiguratie gaat hier niet langs.
    /// </summary>
    internal static void EisVeiligConfiguratiebestand(string pad)
    {
        EisVeiligeMap(Path.GetDirectoryName(Path.GetFullPath(pad))!, maak: false);
        if (new FileInfo(pad).LinkTarget is not null || Directory.Exists(pad))
        {
            throw new UnauthorizedAccessException("De pluginconfiguratie is geen gewoon bestand; niet gelezen of opgeslagen.");
        }
    }

    /// <summary>
    /// Een bestaand bestand is van de procesgebruiker: dezelfde eigendomsproef als bij de mappen (dezelfde modus
    /// terugzetten; zonder CAP_FOWNER kan alleen de eigenaar dat). Alleen na <see cref="EisVeiligBestand"/>, dat een
    /// koppeling al weigert.
    /// </summary>
    internal static void EisEigenBestand(string pad)
    {
        if (!OperatingSystem.IsLinux())
        {
            throw new PlatformNotSupportedException("Controle van de eigenaar van een opslagbestand vereist Linux.");
        }

        if (!File.Exists(pad))
        {
            return;
        }

        try
        {
            File.SetUnixFileMode(pad, File.GetUnixFileMode(pad));
        }
        catch (UnauthorizedAccessException)
        {
            throw new UnauthorizedAccessException("Een opslagbestand van Jelly Leon is niet van de eigen gebruiker; start geweigerd.");
        }
    }

    /// <summary>Controleert de geopende bestandsnaam en modus vóór de eerste schrijf- of leeshandeling.</summary>
    internal void EisGeopendBestand(FileStream stroom, string pad)
    {
        EisVeiligBestand(pad);
        if (!OperatingSystem.IsLinux())
        {
            throw new PlatformNotSupportedException("Controle van een geopend opslagbestand vereist Linux.");
        }

        var fd = stroom.SafeFileHandle.DangerousGetHandle().ToInt64().ToString(CultureInfo.InvariantCulture);
        var geopend = File.ResolveLinkTarget("/proc/self/fd/" + fd, returnFinalTarget: true)?.FullName;
        if (!string.Equals(geopend, Path.GetFullPath(pad), StringComparison.Ordinal)
            || (File.GetUnixFileMode(stroom.SafeFileHandle) & (UnixFileMode.GroupWrite | UnixFileMode.OtherWrite)) != 0)
        {
            throw new UnauthorizedAccessException("Het geopende opslagbestand heeft een andere plek of onveilige rechten; bewerking geweigerd.");
        }
    }

    /// <summary>Het echte pad van een eigen map; null als de eigen map zelf een koppeling is of niet te volgen is.</summary>
    private static string? EchteWortel(string wortel)
    {
        var vol = Path.GetFullPath(wortel).TrimEnd(Path.DirectorySeparatorChar);
        if (new FileInfo(vol).LinkTarget is not null)
        {
            return null;
        }

        var ouder = Path.GetDirectoryName(vol);
        if (ouder is null)
        {
            return vol;
        }

        var echteOuder = EchtPad(ouder);
        return echteOuder is null ? null : Path.Combine(echteOuder, Path.GetFileName(vol));
    }

    /// <summary>Een pad uit mountinfo: spatie, tab, regeleinde en backslash staan daar als octale code.</summary>
    private static string Ontsnap(string veld) =>
        veld.Replace("\\040", " ", StringComparison.Ordinal).Replace("\\011", "\t", StringComparison.Ordinal)
            .Replace("\\012", "\n", StringComparison.Ordinal).Replace("\\134", "\\", StringComparison.Ordinal);

    private static bool Binnen(string pad, string wortel)
    {
        var w = Path.GetFullPath(wortel).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return pad.StartsWith(w, StringComparison.Ordinal);
    }
}
