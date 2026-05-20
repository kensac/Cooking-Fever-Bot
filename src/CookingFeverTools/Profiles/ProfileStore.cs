using System.Text.Json;

namespace CookingFeverTools;

internal static class ProfileStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true
    };

    public static IReadOnlyList<RestaurantProfile> LoadAll()
    {
        EnsureDirectories();
        EnsureDefaultProfile();

        return Directory.EnumerateFiles(AppPaths.ProfilesDirectory, "*.json")
            .OrderBy(path => path)
            .Select(LoadOrDefault)
            .ToList();
    }

    public static RestaurantProfile LoadOrDefault(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            var profile = RestaurantProfile.Default();
            profile.FilePath = GetPathForName(profile.Name);
            return profile;
        }

        try
        {
            var json = File.ReadAllText(path);
            var profile = JsonSerializer.Deserialize<RestaurantProfile>(json, JsonOptions) ?? RestaurantProfile.Default();
            MergeMissingDefaults(profile);
            profile.FilePath = Path.GetFullPath(path);
            return profile;
        }
        catch
        {
            var profile = RestaurantProfile.Default();
            profile.FilePath = Path.GetFullPath(path);
            return profile;
        }
    }

    public static void Save(RestaurantProfile profile)
    {
        EnsureDirectories();
        MergeMissingDefaults(profile);

        if (string.IsNullOrWhiteSpace(profile.FilePath))
        {
            profile.FilePath = GetPathForName(profile.Name);
        }

        profile.Touch();
        var json = JsonSerializer.Serialize(profile, JsonOptions);
        File.WriteAllText(profile.FilePath, json);
    }

    public static RestaurantProfile Create(string name)
    {
        var profile = RestaurantProfile.Default();
        profile.Name = string.IsNullOrWhiteSpace(name) ? "New Profile" : name.Trim();
        profile.FilePath = GetPathForName(profile.Name);
        Save(profile);
        return profile;
    }

    public static void Delete(RestaurantProfile profile)
    {
        if (!string.IsNullOrWhiteSpace(profile.FilePath) && File.Exists(profile.FilePath))
        {
            File.Delete(profile.FilePath);
        }
    }

    public static void EnsureDefaultProfile()
    {
        EnsureDirectories();
        var defaultPath = GetPathForName("Burger Shop");
        if (File.Exists(defaultPath))
        {
            return;
        }

        var profile = RestaurantProfile.Default();
        profile.FilePath = defaultPath;
        Save(profile);
    }

    public static string GetPathForName(string name)
    {
        EnsureDirectories();
        var fileName = SanitizeFileName(name);
        return Path.Combine(AppPaths.ProfilesDirectory, $"{fileName}.json");
    }

    public static void EnsureDirectories()
    {
        Directory.CreateDirectory(AppPaths.ProfilesDirectory);
        Directory.CreateDirectory(AppPaths.AssetsDirectory);
        Directory.CreateDirectory(AppPaths.ScreenshotsDirectory);
        Directory.CreateDirectory(AppPaths.LogsDirectory);
    }

    private static void MergeMissingDefaults(RestaurantProfile profile)
    {
        var defaults = RestaurantProfile.Default();

        foreach (var item in defaults.Points)
        {
            profile.Points.TryAdd(item.Key, item.Value.Clone());
        }

        foreach (var item in defaults.Regions)
        {
            profile.Regions.TryAdd(item.Key, item.Value.Clone());
        }

        foreach (var item in defaults.Timings)
        {
            profile.Timings.TryAdd(item.Key, item.Value);
        }

        if (string.IsNullOrWhiteSpace(profile.Name))
        {
            profile.Name = defaults.Name;
        }
    }

    private static string SanitizeFileName(string name)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var cleaned = new string(name.Select(ch => invalid.Contains(ch) ? '-' : ch).ToArray()).Trim();
        return string.IsNullOrWhiteSpace(cleaned) ? "profile" : cleaned;
    }
}
