using System.Drawing;
using System.Text.Json.Serialization;

namespace CookingFeverTools;

internal sealed class RestaurantProfile
{
    public string Name { get; set; } = "Burger Shop";
    public string AssetsDirectory { get; set; } = "";
    public Dictionary<string, ScreenPoint> Points { get; set; } = [];
    public Dictionary<string, ScreenRegion> Regions { get; set; } = [];
    public Dictionary<string, double> Timings { get; set; } = [];
    public DateTime UpdatedAt { get; set; } = DateTime.Now;

    [JsonIgnore]
    public string FilePath { get; set; } = "";

    public Point GetPoint(string key)
    {
        var defaults = Default();
        return Points.TryGetValue(key, out var value)
            ? value.ToPoint()
            : defaults.Points[key].ToPoint();
    }

    public Rectangle GetRegion(string key)
    {
        var defaults = Default();
        return Regions.TryGetValue(key, out var value)
            ? value.ToRectangle()
            : defaults.Regions[key].ToRectangle();
    }

    public double GetTiming(string key, double fallback)
    {
        return Timings.TryGetValue(key, out var value) && value > 0
            ? value
            : fallback;
    }

    public void SetPoint(string key, Point point)
    {
        Points[key] = ScreenPoint.FromPoint(point);
        Touch();
    }

    public void SetRegion(string key, Rectangle rectangle)
    {
        Regions[key] = ScreenRegion.FromRectangle(rectangle);
        Touch();
    }

    public void SetTiming(string key, double seconds)
    {
        Timings[key] = Math.Max(0.1, seconds);
        Touch();
    }

    public void Touch()
    {
        UpdatedAt = DateTime.Now;
    }

    public RestaurantProfile Clone()
    {
        return new RestaurantProfile
        {
            Name = Name,
            AssetsDirectory = AssetsDirectory,
            Points = Points.ToDictionary(item => item.Key, item => item.Value.Clone()),
            Regions = Regions.ToDictionary(item => item.Key, item => item.Value.Clone()),
            Timings = Timings.ToDictionary(item => item.Key, item => item.Value),
            UpdatedAt = UpdatedAt,
            FilePath = FilePath
        };
    }

    public static RestaurantProfile Default()
    {
        return new RestaurantProfile
        {
            Name = "Burger Shop",
            AssetsDirectory = "",
            Points = new Dictionary<string, ScreenPoint>
            {
                [ProfileKeys.PlayButtonStageSelect] = new(524, 863),
                [ProfileKeys.PlayButtonInStage] = new(973, 942),
                [ProfileKeys.MeatLocation] = new(1340, 928),
                [ProfileKeys.FryingPan1] = new(1302, 814),
                [ProfileKeys.FryingPan2] = new(1270, 711),
                [ProfileKeys.BurgerPosition] = new(771, 712),
                [ProfileKeys.BunLocation] = new(772, 846),
                [ProfileKeys.SodaMachine1] = new(421, 694),
                [ProfileKeys.SodaMachine2] = new(515, 694),
                [ProfileKeys.HotdogUncooked] = new(1496, 904),
                [ProfileKeys.HotdogGrill] = new(1446, 782),
                [ProfileKeys.HotdogHolding] = new(1593, 755),
                [ProfileKeys.HotdogBun] = new(963, 859),
                [ProfileKeys.HotdogPrep] = new(948, 721),
                [ProfileKeys.Customer1] = new(507, 420),
                [ProfileKeys.Customer2] = new(860, 420),
                [ProfileKeys.Customer3] = new(1207, 420),
                [ProfileKeys.Customer4] = new(1552, 420)
            },
            Regions = new Dictionary<string, ScreenRegion>
            {
                [ProfileKeys.OrderRegion1] = new(288, 140, 154, 262),
                [ProfileKeys.OrderRegion2] = new(634, 142, 149, 257),
                [ProfileKeys.OrderRegion3] = new(981, 140, 151, 263),
                [ProfileKeys.OrderRegion4] = new(1324, 143, 153, 261)
            },
            Timings = ProfileKeys.TimingDefinitions.ToDictionary(item => item.Key, item => item.DefaultValue),
            UpdatedAt = DateTime.Now
        };
    }
}

internal sealed class ScreenPoint
{
    public ScreenPoint()
    {
    }

    public ScreenPoint(int x, int y)
    {
        X = x;
        Y = y;
    }

    public int X { get; set; }
    public int Y { get; set; }

    public Point ToPoint() => new(X, Y);
    public ScreenPoint Clone() => new(X, Y);
    public static ScreenPoint FromPoint(Point point) => new(point.X, point.Y);
    public override string ToString() => $"{X}, {Y}";
}

internal sealed class ScreenRegion
{
    public ScreenRegion()
    {
    }

    public ScreenRegion(int x, int y, int width, int height)
    {
        X = x;
        Y = y;
        Width = width;
        Height = height;
    }

    public int X { get; set; }
    public int Y { get; set; }
    public int Width { get; set; }
    public int Height { get; set; }

    public Rectangle ToRectangle() => new(X, Y, Width, Height);
    public ScreenRegion Clone() => new(X, Y, Width, Height);
    public static ScreenRegion FromRectangle(Rectangle rectangle) => new(rectangle.X, rectangle.Y, rectangle.Width, rectangle.Height);
    public override string ToString() => $"{X}, {Y}, {Width}, {Height}";
}
