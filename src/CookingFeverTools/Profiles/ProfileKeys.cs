using System.Collections.ObjectModel;

namespace CookingFeverTools;

internal static class ProfileKeys
{
    public const string PlayButtonStageSelect = "playButtonStageSelect";
    public const string PlayButtonInStage = "playButtonInStage";
    public const string MeatLocation = "meatLocation";
    public const string FryingPan1 = "fryingPan1";
    public const string FryingPan2 = "fryingPan2";
    public const string BurgerPosition = "burgerPosition";
    public const string BunLocation = "bunLocation";
    public const string SodaMachine1 = "sodaMachine1";
    public const string SodaMachine2 = "sodaMachine2";
    public const string HotdogUncooked = "hotdogUncooked";
    public const string HotdogGrill = "hotdogGrill";
    public const string HotdogHolding = "hotdogHolding";
    public const string HotdogBun = "hotdogBun";
    public const string HotdogPrep = "hotdogPrep";
    public const string Customer1 = "customer1";
    public const string Customer2 = "customer2";
    public const string Customer3 = "customer3";
    public const string Customer4 = "customer4";

    public const string OrderRegion1 = "orderRegion1";
    public const string OrderRegion2 = "orderRegion2";
    public const string OrderRegion3 = "orderRegion3";
    public const string OrderRegion4 = "orderRegion4";

    public const string BurgerCookSeconds = "burgerCookSeconds";
    public const string SodaRefillSeconds = "sodaRefillSeconds";
    public const string HotdogCookSeconds = "hotdogCookSeconds";

    public static IReadOnlyList<ProfilePointDefinition> PointDefinitions { get; } =
        new ReadOnlyCollection<ProfilePointDefinition>(
        [
            new(PlayButtonStageSelect, "Stage Select Play Button"),
            new(PlayButtonInStage, "In-Stage Play Button"),
            new(MeatLocation, "Meat Source"),
            new(FryingPan1, "Frying Pan 1"),
            new(FryingPan2, "Frying Pan 2"),
            new(BurgerPosition, "Burger Prep Position"),
            new(BunLocation, "Burger Bun Source"),
            new(SodaMachine1, "Soda Machine 1"),
            new(SodaMachine2, "Soda Machine 2"),
            new(HotdogUncooked, "Uncooked Hotdog Source"),
            new(HotdogGrill, "Hotdog Grill"),
            new(HotdogHolding, "Hotdog Warmer"),
            new(HotdogBun, "Hotdog Bun Source"),
            new(HotdogPrep, "Hotdog Prep Position"),
            new(Customer1, "Customer 1 Delivery"),
            new(Customer2, "Customer 2 Delivery"),
            new(Customer3, "Customer 3 Delivery"),
            new(Customer4, "Customer 4 Delivery")
        ]);

    public static IReadOnlyList<ProfileRegionDefinition> RegionDefinitions { get; } =
        new ReadOnlyCollection<ProfileRegionDefinition>(
        [
            new(OrderRegion1, "Customer 1 Order Region"),
            new(OrderRegion2, "Customer 2 Order Region"),
            new(OrderRegion3, "Customer 3 Order Region"),
            new(OrderRegion4, "Customer 4 Order Region")
        ]);

    public static IReadOnlyList<ProfileTimingDefinition> TimingDefinitions { get; } =
        new ReadOnlyCollection<ProfileTimingDefinition>(
        [
            new(BurgerCookSeconds, "Burger cook time", 9),
            new(SodaRefillSeconds, "Soda refill time", 8),
            new(HotdogCookSeconds, "Hotdog cook time", 10)
        ]);
}

internal sealed record ProfilePointDefinition(string Key, string Label);
internal sealed record ProfileRegionDefinition(string Key, string Label);
internal sealed record ProfileTimingDefinition(string Key, string Label, double DefaultValue);
