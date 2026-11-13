using System;
using System.Globalization;
using System.IO;

namespace Jellyfin.Plugin.JellyLeon.Core.Planner;

/// <summary>
/// De geheugenmarge van de container: <c>memory.max − memory.current</c> (cgroup v2). Zonder grens telt het vrije
/// geheugen van de machine (<c>MemAvailable</c>). Niet te lezen is <c>null</c>: dan is er geen uitzondering mogelijk.
/// </summary>
internal static class CgroupMarge
{
    public static long? Lees(string cgroupMap = "/sys/fs/cgroup", string meminfoPad = "/proc/meminfo")
    {
        try
        {
            var maxPad = Path.Combine(cgroupMap, "memory.max");
            var nuPad = Path.Combine(cgroupMap, "memory.current");
            if (File.Exists(maxPad) && File.Exists(nuPad))
            {
                var max = File.ReadAllText(maxPad).Trim();
                if (long.TryParse(max, NumberStyles.None, CultureInfo.InvariantCulture, out var grens)
                    && long.TryParse(File.ReadAllText(nuPad).Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out var gebruikt))
                {
                    return Math.Max(0, grens - gebruikt);
                }

                if (max != "max")
                {
                    return null;
                }
            }

            if (!File.Exists(meminfoPad))
            {
                return null;
            }

            foreach (var regel in File.ReadLines(meminfoPad))
            {
                if (regel.StartsWith("MemAvailable:", StringComparison.Ordinal))
                {
                    var delen = regel.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                    return delen.Length >= 2 && long.TryParse(delen[1], NumberStyles.None, CultureInfo.InvariantCulture, out var kib) ? kib * 1024 : null;
                }
            }

            return null;
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }
}
