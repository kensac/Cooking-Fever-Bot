using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Timer = System.Windows.Forms.Timer;

namespace CookingFeverTools;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        return ToolHost.Run(args);
    }
}

internal static class ToolHost
{
    public static int Run(string[] args)
    {
        var command = args.Length == 0 ? "dashboard" : args[0].Trim().ToLowerInvariant();

        try
        {
            switch (command)
            {
                case "dashboard":
                case "launcher":
                case "app":
                    RunForm(() => new DashboardForm());
                    return 0;
                case "bot":
                    new CookingFeverBot(BotOptions.FromArgs(args.Skip(1))).Run();
                    return 0;
                case "tracker":
                    MouseTracker.Run(args.Skip(1).ToArray());
                    return 0;
                case "region":
                    RunForm(() => new RegionCaptureForm(captureScreenshots: false));
                    return 0;
                case "snap":
                    RunForm(() => new RegionCaptureForm(captureScreenshots: true));
                    return 0;
                case "monitor":
                    RunForm(() => new ActionMonitorForm());
                    return 0;
                case "todo":
                    RunForm(() => new TodoForm());
                    return 0;
                case "help":
                case "--help":
                case "-h":
                    PrintHelp();
                    return 0;
                default:
                    Console.Error.WriteLine($"Unknown command: {command}");
                    PrintHelp();
                    return 1;
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 1;
        }
    }

    private static void RunForm(Func<Form> formFactory)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        using var form = formFactory();
        Application.Run(form);
    }

    private static void PrintHelp()
    {
        Console.WriteLine("""
        Cooking Fever Tools

        Commands:
          dashboard Open the graphical dashboard. Default when no command is supplied.
          bot       Run the Cooking Fever automation bot.
          tracker   Print the current mouse position once per second.
          region    Drag-select screen regions and print their coordinates.
          snap      Drag-select screen regions and save PNG snapshots.
          monitor   Open the action monitor and screenshot tagger.
          todo      Open the objective/task todo utility.

        Bot controls:
          s         Start the bot after launch.
          p         Pause or resume.
          gg        Stop.

        Bot options:
          --assets <path>       Template image directory. Default: ./assets
          --profile <path>      Restaurant profile JSON file.
          --confidence <0-1>    Template matching confidence. Default: 0.8
          --delay <seconds>     Initial delay before listening for start. Default: 5
          --start               Start immediately without waiting for the s hotkey.
          --dry-run             Log clicks and drags without moving the mouse.
        """);
    }
}

internal static class AppPaths
{
    public static string AppDirectory => Path.GetFullPath(AppContext.BaseDirectory);

    public static string AssetsDirectory
    {
        get
        {
            var currentDirectoryAssets = Path.Combine(Environment.CurrentDirectory, "assets");
            return Directory.Exists(currentDirectoryAssets)
                ? currentDirectoryAssets
                : Path.Combine(AppDirectory, "assets");
        }
    }

    public static string ScreenshotsDirectory => Path.Combine(AppDirectory, "screenshots");
    public static string ProfilesDirectory => Path.Combine(AppDirectory, "profiles");
    public static string LogsDirectory => Path.Combine(AppDirectory, "logs");
}

internal sealed record BotOptions(
    string AssetsDirectory,
    double Confidence,
    int InitialDelaySeconds,
    string? ProfilePath,
    RestaurantProfile Profile,
    bool StartImmediately,
    bool DryRun)
{
    public static BotOptions FromArgs(IEnumerable<string> args)
    {
        var argList = args.ToArray();
        var assets = AppPaths.AssetsDirectory;
        var confidence = 0.8;
        var delay = 5;
        string? profilePath = null;
        var startImmediately = false;
        var dryRun = false;

        for (var i = 0; i < argList.Length; i++)
        {
            switch (argList[i])
            {
                case "--assets" when i + 1 < argList.Length:
                    assets = Path.GetFullPath(argList[++i]);
                    break;
                case "--profile" when i + 1 < argList.Length:
                    profilePath = Path.GetFullPath(argList[++i]);
                    break;
                case "--confidence" when i + 1 < argList.Length && double.TryParse(argList[++i], out var parsedConfidence):
                    confidence = Math.Clamp(parsedConfidence, 0.0, 1.0);
                    break;
                case "--delay" when i + 1 < argList.Length && int.TryParse(argList[++i], out var parsedDelay):
                    delay = Math.Max(0, parsedDelay);
                    break;
                case "--start":
                    startImmediately = true;
                    break;
                case "--dry-run":
                    dryRun = true;
                    break;
            }
        }

        var profile = ProfileStore.LoadOrDefault(profilePath);
        if (!string.IsNullOrWhiteSpace(profile.AssetsDirectory))
        {
            assets = Path.GetFullPath(profile.AssetsDirectory);
        }

        return new BotOptions(assets, confidence, delay, profilePath, profile, startImmediately, dryRun);
    }
}

internal sealed class CookingFeverBot
{
    private const double DefaultBurgerCookTime = 9.0;
    private const double DefaultSodaRefillTime = 8.0;
    private const double DefaultHotdogCookTime = 10.0;

    private readonly BotOptions _options;
    private readonly RestaurantProfile _profile;
    private readonly double _burgerCookTime;
    private readonly double _sodaRefillTime;
    private readonly double _hotdogCookTime;
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private readonly List<BotWorkItem> _tasks = [];
    private readonly Dictionary<int, bool> _regionInProgress = new()
    {
        [1] = false,
        [2] = false,
        [3] = false,
        [4] = false
    };
    private readonly Dictionary<int, int> _regionToPan = [];
    private readonly HashSet<string> _missingTemplateWarnings = [];

    private readonly Point _playButtonStageSelect;
    private readonly Point _playButtonInStage;
    private readonly Point _meatLocation;
    private readonly Point _fryingPan1;
    private readonly Point _fryingPan2;
    private readonly Point _burgerPosition;
    private readonly Point _bunLocation;
    private readonly Point _sodaMachine1;
    private readonly Point _sodaMachine2;
    private readonly Point _hotdogUncooked;
    private readonly Point _hotdogGrill;
    private readonly Point _hotdogHolding;
    private readonly Point _hotdogBun;
    private readonly Point _hotdogPrep;

    private readonly Dictionary<int, Point> _customerCoords;
    private readonly Dictionary<int, Rectangle> _orderRegions;

    private volatile bool _startRequested;
    private volatile bool _stopRequested;
    private volatile bool _paused;
    private bool _previousS;
    private bool _previousP;
    private bool _previousG;
    private double _lastGTime = -10;

    private bool _hotdogOrdersStarted;
    private int _hotdogsInWarmer;
    private double _mouseBusyUntil;
    private double _soda1BusyUntil;
    private double _soda2BusyUntil;
    private double _pan1BusyUntil;
    private double _pan2BusyUntil;
    private bool _pan1Filled;
    private bool _pan2Filled;
    private double _bunStationBusyUntil;
    private double _hotdogGrillBusyUntil;

    public CookingFeverBot(BotOptions options)
    {
        _options = options;
        _profile = options.Profile;
        _burgerCookTime = _profile.GetTiming(ProfileKeys.BurgerCookSeconds, DefaultBurgerCookTime);
        _sodaRefillTime = _profile.GetTiming(ProfileKeys.SodaRefillSeconds, DefaultSodaRefillTime);
        _hotdogCookTime = _profile.GetTiming(ProfileKeys.HotdogCookSeconds, DefaultHotdogCookTime);

        _playButtonStageSelect = _profile.GetPoint(ProfileKeys.PlayButtonStageSelect);
        _playButtonInStage = _profile.GetPoint(ProfileKeys.PlayButtonInStage);
        _meatLocation = _profile.GetPoint(ProfileKeys.MeatLocation);
        _fryingPan1 = _profile.GetPoint(ProfileKeys.FryingPan1);
        _fryingPan2 = _profile.GetPoint(ProfileKeys.FryingPan2);
        _burgerPosition = _profile.GetPoint(ProfileKeys.BurgerPosition);
        _bunLocation = _profile.GetPoint(ProfileKeys.BunLocation);
        _sodaMachine1 = _profile.GetPoint(ProfileKeys.SodaMachine1);
        _sodaMachine2 = _profile.GetPoint(ProfileKeys.SodaMachine2);
        _hotdogUncooked = _profile.GetPoint(ProfileKeys.HotdogUncooked);
        _hotdogGrill = _profile.GetPoint(ProfileKeys.HotdogGrill);
        _hotdogHolding = _profile.GetPoint(ProfileKeys.HotdogHolding);
        _hotdogBun = _profile.GetPoint(ProfileKeys.HotdogBun);
        _hotdogPrep = _profile.GetPoint(ProfileKeys.HotdogPrep);

        _customerCoords = new Dictionary<int, Point>
        {
            [1] = _profile.GetPoint(ProfileKeys.Customer1),
            [2] = _profile.GetPoint(ProfileKeys.Customer2),
            [3] = _profile.GetPoint(ProfileKeys.Customer3),
            [4] = _profile.GetPoint(ProfileKeys.Customer4)
        };

        _orderRegions = new Dictionary<int, Rectangle>
        {
            [1] = _profile.GetRegion(ProfileKeys.OrderRegion1),
            [2] = _profile.GetRegion(ProfileKeys.OrderRegion2),
            [3] = _profile.GetRegion(ProfileKeys.OrderRegion3),
            [4] = _profile.GetRegion(ProfileKeys.OrderRegion4)
        };
    }

    public void Run()
    {
        Console.WriteLine("Cooking Fever Bot - C# port");
        Console.WriteLine($"Profile: {_profile.Name}");
        Console.WriteLine($"Template assets: {_options.AssetsDirectory}");
        Console.WriteLine(_options.DryRun
            ? "Dry run is enabled. Clicks and drags will only be logged."
            : "Press 's' to start, 'gg' to stop, 'p' to pause.");
        Console.WriteLine();

        if (!Directory.Exists(_options.AssetsDirectory))
        {
            Console.WriteLine("Warning: asset directory does not exist yet. Add burger.png, soda.png, hotdog.png, restart-1.png, and restart-2.png.");
        }

        var keyboardThread = new Thread(PollControlKeys)
        {
            IsBackground = true,
            Name = "Bot hotkey polling"
        };
        keyboardThread.Start();

        Thread.Sleep(TimeSpan.FromSeconds(_options.InitialDelaySeconds));
        if (_options.StartImmediately)
        {
            _startRequested = true;
            Console.WriteLine("[CONTROL] Auto-start requested.");
        }

        while (!_startRequested && !_stopRequested)
        {
            Thread.Sleep(100);
        }

        if (!_stopRequested)
        {
            MainLoop();
        }
    }

    private void PollControlKeys()
    {
        while (!_stopRequested)
        {
            var sDown = NativeMethods.IsKeyDown(Keys.S);
            var pDown = NativeMethods.IsKeyDown(Keys.P);
            var gDown = NativeMethods.IsKeyDown(Keys.G);

            if (sDown && !_previousS && !_startRequested)
            {
                _startRequested = true;
                Console.WriteLine("[CONTROL] Start requested.");
            }

            if (pDown && !_previousP)
            {
                _paused = !_paused;
                Console.WriteLine(_paused ? "[CONTROL] Paused." : "[CONTROL] Resumed.");
            }

            if (gDown && !_previousG)
            {
                var now = Now;
                if (now - _lastGTime < 0.5)
                {
                    _stopRequested = true;
                    Console.WriteLine("[CONTROL] Stop requested.");
                }
                _lastGTime = now;
            }

            _previousS = sDown;
            _previousP = pDown;
            _previousG = gDown;
            Thread.Sleep(25);
        }
    }

    private void MainLoop()
    {
        while (!_stopRequested)
        {
            if (_paused)
            {
                Thread.Sleep(100);
                continue;
            }

            if (_tasks.Count == 0)
            {
                DoRestartStage();
            }

            DetectNewOrders();
            UpdateTasks();
            _tasks.RemoveAll(t => t.State == BotWorkItemState.Completed);

            if (_hotdogOrdersStarted)
            {
                MaintainHotdogWarmer();
            }

            Thread.Sleep(_tasks.Count > 0 ? 100 : 500);
        }

        Console.WriteLine("[DEBUG] Main loop ended.");
    }

    private double Now => _clock.Elapsed.TotalSeconds;
    internal double CurrentTime => Now;

    private bool MouseFree() => Now >= _mouseBusyUntil;
    private void LockMouseFor(double seconds) => _mouseBusyUntil = Now + seconds;
    private bool Soda1Free() => Now >= _soda1BusyUntil;
    private bool Soda2Free() => Now >= _soda2BusyUntil;
    private void LockSoda1For(double seconds) => _soda1BusyUntil = Now + seconds;
    private void LockSoda2For(double seconds) => _soda2BusyUntil = Now + seconds;
    private bool Pan1Free() => !_pan1Filled && Now >= _pan1BusyUntil;
    private bool Pan2Free() => !_pan2Filled && Now >= _pan2BusyUntil;
    private void LockPan1For(double seconds)
    {
        _pan1Filled = true;
        _pan1BusyUntil = Now + seconds;
    }
    private void LockPan2For(double seconds)
    {
        _pan2Filled = true;
        _pan2BusyUntil = Now + seconds;
    }
    private void FreePan1() => _pan1Filled = false;
    private void FreePan2() => _pan2Filled = false;
    private bool BunStationFree() => Now >= _bunStationBusyUntil;
    private void LockBunStationFor(double seconds) => _bunStationBusyUntil = Now + seconds;
    private bool GrillFree() => Now >= _hotdogGrillBusyUntil;
    private void LockGrillFor(double seconds) => _hotdogGrillBusyUntil = Now + seconds;

    private void MoveAndClick(Point point)
    {
        LockMouseFor(0.6);
        if (_options.DryRun)
        {
            Console.WriteLine($"[DRY RUN] Click ({point.X}, {point.Y})");
            return;
        }

        ScreenAutomation.Click(point);
    }

    private void MoveAndDrag(Point source, Point target)
    {
        LockMouseFor(0.8);
        if (_options.DryRun)
        {
            Console.WriteLine($"[DRY RUN] Drag ({source.X}, {source.Y}) -> ({target.X}, {target.Y})");
            return;
        }

        ScreenAutomation.Drag(source, target);
    }

    private TemplateMatch? SafeLocateOnScreen(string fileName, Rectangle? region = null)
    {
        var path = Path.Combine(_options.AssetsDirectory, fileName);
        if (!File.Exists(path))
        {
            if (_missingTemplateWarnings.Add(fileName))
            {
                Console.WriteLine($"[ASSET] Missing template: {path}");
            }
            return null;
        }

        return TemplateMatcher.Locate(path, region, _options.Confidence);
    }

    private TemplateMatch? LocateAnyRestart()
    {
        return SafeLocateOnScreen("restart-1.png") ?? SafeLocateOnScreen("restart-2.png");
    }

    private bool DoRestartStage()
    {
        var restart = LocateAnyRestart();
        if (restart is null)
        {
            return false;
        }

        Console.WriteLine("[DEBUG] Found restart button. Restarting stage.");
        MoveAndClick(restart.Bounds.Center());
        Thread.Sleep(1500);
        MoveAndClick(_playButtonStageSelect);
        Thread.Sleep(1000);
        MoveAndClick(_playButtonInStage);
        Thread.Sleep(5000);
        return true;
    }

    private void MaintainHotdogWarmer()
    {
        if (!_hotdogOrdersStarted || _hotdogsInWarmer >= 1)
        {
            return;
        }

        Console.WriteLine("[WARMER] Warmer empty, scheduling a hotdog.");
        CreateCookDogForWarmerTasks();
    }

    private void CreateCookDogForWarmerTasks()
    {
        bool CanCook() => _hotdogsInWarmer < 1 && GrillFree() && MouseFree();

        void Cook(BotWorkItem item)
        {
            Console.WriteLine("[WARMER] Cooking dog for warmer.");
            LockGrillFor(_hotdogCookTime);
            MoveAndClick(_hotdogUncooked);
            item.EndTime = 0;
        }

        var cook = new BotWorkItem("Warmer_cookDog", CanCook, Cook, this);

        void Wait(BotWorkItem item)
        {
            item.EndTime = _hotdogsInWarmer >= 1 ? 0 : _hotdogGrillBusyUntil;
        }

        var wait = new BotWorkItem("Warmer_waitGrill", () => true, Wait, this, [cook]);

        bool CanMove() => _hotdogsInWarmer < 1 && MouseFree();

        void Move(BotWorkItem item)
        {
            Console.WriteLine("[WARMER] Moving cooked dog to warmer.");
            MoveAndDrag(_hotdogGrill, _hotdogHolding);
            _hotdogsInWarmer = 1;
            item.EndTime = 0;
        }

        var move = new BotWorkItem("Warmer_moveDog", CanMove, Move, this, [wait]);
        _tasks.AddRange([cook, wait, move]);
    }

    private void DetectNewOrders()
    {
        for (var customer = 1; customer <= 4; customer++)
        {
            if (_stopRequested)
            {
                return;
            }

            if (_regionInProgress[customer])
            {
                continue;
            }

            var region = _orderRegions[customer];

            if (SafeLocateOnScreen("burger.png", region) is not null)
            {
                Console.WriteLine($"[DEBUG] Burger in region {customer}");
                CreateBurgerOrderTasks(customer);
                _regionInProgress[customer] = true;
                continue;
            }

            if (SafeLocateOnScreen("soda.png", region) is not null)
            {
                Console.WriteLine($"[DEBUG] Soda in region {customer}");
                CreateSodaOrderTasks(customer);
                _regionInProgress[customer] = true;
                continue;
            }

            if (SafeLocateOnScreen("hotdog.png", region) is not null)
            {
                Console.WriteLine($"[DEBUG] Hotdog in region {customer}");
                CreateHotdogOrderTasks(customer);
                _regionInProgress[customer] = true;
            }
        }
    }

    private void CreateBurgerOrderTasks(int customer)
    {
        bool CanPlacePatty() => MouseFree() && (Pan1Free() || Pan2Free());

        void PlacePatty(BotWorkItem item)
        {
            if (Pan1Free())
            {
                _regionToPan[customer] = 1;
                LockPan1For(_burgerCookTime);
                MoveAndDrag(_meatLocation, _fryingPan1);
                Console.WriteLine($"[BURGER] Region {customer} using pan 1.");
            }
            else
            {
                _regionToPan[customer] = 2;
                LockPan2For(_burgerCookTime);
                MoveAndDrag(_meatLocation, _fryingPan2);
                Console.WriteLine($"[BURGER] Region {customer} using pan 2.");
            }

            item.EndTime = 0;
        }

        var pan = new BotWorkItem($"Bpan-r{customer}", CanPlacePatty, PlacePatty, this);

        void WaitCook(BotWorkItem item)
        {
            var used = _regionToPan[customer];
            item.EndTime = used == 1 ? _pan1BusyUntil : _pan2BusyUntil;
        }

        var cook = new BotWorkItem($"Bcook-r{customer}", () => true, WaitCook, this, [pan]);

        bool CanPlaceBun() => MouseFree() && BunStationFree();

        void PlaceBun(BotWorkItem item)
        {
            Console.WriteLine($"[BURGER] Region {customer} placing bun.");
            LockBunStationFor(9999);
            MoveAndClick(_bunLocation);
            item.EndTime = 0;
        }

        var bun = new BotWorkItem($"Bbun-r{customer}", CanPlaceBun, PlaceBun, this, [cook]);

        void DragPatty(BotWorkItem item)
        {
            var used = _regionToPan[customer];
            MoveAndDrag(used == 1 ? _fryingPan1 : _fryingPan2, _burgerPosition);
            item.EndTime = 0;
        }

        var drag = new BotWorkItem($"Bdrag-r{customer}", MouseFree, DragPatty, this, [bun]);

        void Deliver(BotWorkItem item)
        {
            Console.WriteLine($"[BURGER] Region {customer} delivering.");
            MoveAndDrag(_burgerPosition, _customerCoords[customer]);
            item.EndTime = 0;
        }

        var deliver = new BotWorkItem($"Bdeliver-r{customer}", MouseFree, Deliver, this, [drag]);

        void Collect(BotWorkItem item)
        {
            MoveAndClick(_customerCoords[customer]);
            item.EndTime = 0;
        }

        void Finish(BotWorkItem item)
        {
            _regionInProgress[customer] = false;
            _bunStationBusyUntil = Now;

            var used = _regionToPan[customer];
            if (used == 1)
            {
                FreePan1();
            }
            else
            {
                FreePan2();
            }

            _regionToPan.Remove(customer);
            Console.WriteLine($"[BURGER] Region {customer} complete.");
        }

        var collect = new BotWorkItem($"Bcollect-r{customer}", MouseFree, Collect, this, [deliver], Finish);
        _tasks.AddRange([pan, cook, bun, drag, deliver, collect]);
    }

    private void CreateSodaOrderTasks(int customer)
    {
        bool CanServeSoda() => MouseFree() && (Soda1Free() || Soda2Free());

        void ServeSoda(BotWorkItem item)
        {
            if (Soda1Free())
            {
                LockSoda1For(_sodaRefillTime);
                MoveAndDrag(_sodaMachine1, _customerCoords[customer]);
                Console.WriteLine($"[SODA] Region {customer} using soda 1.");
            }
            else
            {
                LockSoda2For(_sodaRefillTime);
                MoveAndDrag(_sodaMachine2, _customerCoords[customer]);
                Console.WriteLine($"[SODA] Region {customer} using soda 2.");
            }

            item.EndTime = 0;
        }

        var soda = new BotWorkItem($"SodaDrag-r{customer}", CanServeSoda, ServeSoda, this);

        void Collect(BotWorkItem item)
        {
            MoveAndClick(_customerCoords[customer]);
            item.EndTime = 0;
        }

        void Finish(BotWorkItem item)
        {
            _regionInProgress[customer] = false;
            Console.WriteLine($"[SODA] Region {customer} complete.");
        }

        var collect = new BotWorkItem($"SodaCollect-r{customer}", MouseFree, Collect, this, [soda], Finish);
        _tasks.AddRange([soda, collect]);
    }

    private void CreateHotdogOrderTasks(int customer)
    {
        if (!_hotdogOrdersStarted)
        {
            _hotdogOrdersStarted = true;
            Console.WriteLine("[HOTDOG] First hotdog order found. Warmer maintenance enabled.");
        }

        var orderTasks = new List<BotWorkItem>();

        if (_hotdogsInWarmer == 0)
        {
            bool CanCook() => GrillFree() && MouseFree();

            void Cook(BotWorkItem item)
            {
                Console.WriteLine($"[HOTDOG] Region {customer} cooking on demand.");
                LockGrillFor(_hotdogCookTime);
                MoveAndClick(_hotdogUncooked);
                item.EndTime = 0;
            }

            var cook = new BotWorkItem($"HD-cookOnDemand-r{customer}", CanCook, Cook, this);
            orderTasks.Add(cook);

            void Wait(BotWorkItem item)
            {
                item.EndTime = _hotdogGrillBusyUntil;
            }

            var wait = new BotWorkItem($"HD-waitCook-r{customer}", () => true, Wait, this, [cook]);
            orderTasks.Add(wait);
        }

        void PlaceBun(BotWorkItem item)
        {
            Console.WriteLine($"[HOTDOG] Region {customer} placing bun.");
            MoveAndClick(_hotdogBun);
            item.EndTime = 0;
        }

        var bunDependencies = orderTasks.Count == 0 ? [] : new[] { orderTasks[^1] };
        var bun = new BotWorkItem($"HD-placeBun-r{customer}", MouseFree, PlaceBun, this, bunDependencies);
        orderTasks.Add(bun);

        void DragDog(BotWorkItem item)
        {
            if (_hotdogsInWarmer > 0)
            {
                Console.WriteLine($"[HOTDOG] Region {customer} using warmer dog.");
                MoveAndDrag(_hotdogHolding, _hotdogPrep);
                _hotdogsInWarmer--;
            }
            else
            {
                Console.WriteLine($"[HOTDOG] Region {customer} dragging dog from grill.");
                MoveAndDrag(_hotdogGrill, _hotdogPrep);
            }

            item.EndTime = 0;
        }

        var dragDog = new BotWorkItem($"HD-dragDog-r{customer}", MouseFree, DragDog, this, [bun]);
        orderTasks.Add(dragDog);

        void Deliver(BotWorkItem item)
        {
            Console.WriteLine($"[HOTDOG] Region {customer} delivering.");
            MoveAndDrag(_hotdogPrep, _customerCoords[customer]);
            item.EndTime = 0;
        }

        var deliver = new BotWorkItem($"HD-deliver-r{customer}", MouseFree, Deliver, this, [dragDog]);
        orderTasks.Add(deliver);

        void Collect(BotWorkItem item)
        {
            MoveAndClick(_customerCoords[customer]);
            item.EndTime = 0;
        }

        void Finish(BotWorkItem item)
        {
            _regionInProgress[customer] = false;
            Console.WriteLine($"[HOTDOG] Region {customer} complete.");
            MaintainHotdogWarmer();
        }

        var collect = new BotWorkItem($"HD-collect-r{customer}", MouseFree, Collect, this, [deliver], Finish);
        orderTasks.Add(collect);

        _tasks.AddRange(orderTasks);
    }

    private void UpdateTasks()
    {
        foreach (var task in _tasks.Where(t => t.State == BotWorkItemState.Running).ToList())
        {
            task.Update();
        }

        foreach (var task in _tasks.Where(t => t.State == BotWorkItemState.Pending).ToList())
        {
            if (task.CanStart())
            {
                task.Start();
                task.Update();
            }
        }
    }
}

internal enum BotWorkItemState
{
    Pending,
    Running,
    Completed
}

internal sealed class BotWorkItem
{
    private readonly Func<bool> _resourceCheck;
    private readonly Action<BotWorkItem> _runAction;
    private readonly IReadOnlyList<BotWorkItem> _dependencies;
    private readonly Action<BotWorkItem>? _onFinish;
    private readonly CookingFeverBot _bot;

    public BotWorkItem(
        string name,
        Func<bool> resourceCheck,
        Action<BotWorkItem> runAction,
        CookingFeverBot bot,
        IReadOnlyList<BotWorkItem>? dependencies = null,
        Action<BotWorkItem>? onFinish = null)
    {
        Name = name;
        _resourceCheck = resourceCheck;
        _runAction = runAction;
        _bot = bot;
        _dependencies = dependencies ?? [];
        _onFinish = onFinish;
    }

    public string Name { get; }
    public BotWorkItemState State { get; private set; } = BotWorkItemState.Pending;
    public double EndTime { get; set; }

    public bool CanStart()
    {
        return _dependencies.All(t => t.State == BotWorkItemState.Completed) && _resourceCheck();
    }

    public void Start()
    {
        State = BotWorkItemState.Running;
        _runAction(this);
    }

    public void Update()
    {
        if (State != BotWorkItemState.Running)
        {
            return;
        }

        if (EndTime == 0 || _bot.CurrentTime >= EndTime)
        {
            Finish();
        }
    }

    private void Finish()
    {
        State = BotWorkItemState.Completed;
        _onFinish?.Invoke(this);
    }
}

internal static class MouseTracker
{
    public static void Run(string[] args)
    {
        var interval = 1.0;
        if (args.Length > 0 && double.TryParse(args[0], out var parsed))
        {
            interval = Math.Max(0.05, parsed);
        }

        Console.WriteLine("Tracking mouse position. Press Ctrl+C to stop.");
        var stopping = false;
        Console.CancelKeyPress += (_, eventArgs) =>
        {
            eventArgs.Cancel = true;
            stopping = true;
        };

        while (!stopping)
        {
            var point = ScreenAutomation.GetCursorPosition();
            Console.WriteLine($"Mouse position: X={point.X}, Y={point.Y}");
            Thread.Sleep(TimeSpan.FromSeconds(interval));
        }
    }
}

internal static class ScreenAutomation
{
    public static Point GetCursorPosition() => Cursor.Position;

    public static void MoveTo(Point target, TimeSpan? duration = null)
    {
        var total = duration ?? TimeSpan.FromMilliseconds(200);
        var start = Cursor.Position;
        var steps = Math.Max(1, (int)(total.TotalMilliseconds / 15));

        for (var i = 1; i <= steps; i++)
        {
            var progress = i / (double)steps;
            var x = start.X + (int)Math.Round((target.X - start.X) * progress);
            var y = start.Y + (int)Math.Round((target.Y - start.Y) * progress);
            NativeMethods.SetCursorPos(x, y);
            Thread.Sleep(Math.Max(1, (int)(total.TotalMilliseconds / steps)));
        }
    }

    public static void Click(Point point)
    {
        MoveTo(point, TimeSpan.FromMilliseconds(200));
        NativeMethods.MouseDown();
        Thread.Sleep(40);
        NativeMethods.MouseUp();
    }

    public static void Drag(Point source, Point target)
    {
        MoveTo(source, TimeSpan.FromMilliseconds(200));
        NativeMethods.MouseDown();
        Thread.Sleep(100);
        MoveTo(target, TimeSpan.FromMilliseconds(400));
        NativeMethods.MouseUp();
    }

    public static Bitmap CaptureScreen() => Capture(SystemInformation.VirtualScreen);

    public static Bitmap Capture(Rectangle region)
    {
        var bounds = Rectangle.Intersect(region, SystemInformation.VirtualScreen);
        if (bounds.Width <= 0 || bounds.Height <= 0)
        {
            throw new InvalidOperationException($"Capture region is outside the virtual screen: {region}");
        }

        var bitmap = new Bitmap(bounds.Width, bounds.Height, PixelFormat.Format24bppRgb);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
        return bitmap;
    }

    public static string SaveRegion(Rectangle region, string directory, string prefix)
    {
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, $"{prefix}_{DateTime.Now:yyyy-MM-dd_HH-mm-ss_fffffff}.png");
        using var bitmap = Capture(region);
        bitmap.Save(path, ImageFormat.Png);
        return path;
    }

    public static Rectangle CenteredRegion(Point center, int size)
    {
        return new Rectangle(center.X - size / 2, center.Y - size / 2, size, size);
    }
}

internal sealed record TemplateMatch(Rectangle Bounds, double Confidence);

internal static class TemplateMatcher
{
    public static TemplateMatch? Locate(string templatePath, Rectangle? searchRegion, double confidence)
    {
        using var template = new Bitmap(templatePath);
        using var source = searchRegion.HasValue
            ? ScreenAutomation.Capture(searchRegion.Value)
            : ScreenAutomation.CaptureScreen();

        var offset = searchRegion?.Location ?? SystemInformation.VirtualScreen.Location;
        var best = FindBestMatch(source, template, confidence);
        if (best is null)
        {
            return null;
        }

        var bounds = new Rectangle(
            offset.X + best.Value.Point.X,
            offset.Y + best.Value.Point.Y,
            template.Width,
            template.Height);

        return new TemplateMatch(bounds, best.Value.Score);
    }

    private static (Point Point, double Score)? FindBestMatch(Bitmap source, Bitmap template, double confidence)
    {
        if (template.Width > source.Width || template.Height > source.Height)
        {
            return null;
        }

        var samples = BuildSamples(template);
        var bestPoint = Point.Empty;
        var bestScore = 0.0;
        var positionStep = confidence >= 0.9 ? 1 : 2;

        for (var y = 0; y <= source.Height - template.Height; y += positionStep)
        {
            for (var x = 0; x <= source.Width - template.Width; x += positionStep)
            {
                var score = ScoreAt(source, samples, x, y);
                if (score > bestScore)
                {
                    bestScore = score;
                    bestPoint = new Point(x, y);
                    if (bestScore >= 0.995)
                    {
                        return (bestPoint, bestScore);
                    }
                }
            }
        }

        return bestScore >= confidence ? (bestPoint, bestScore) : null;
    }

    private static List<TemplateSample> BuildSamples(Bitmap template)
    {
        const int maxSamples = 700;
        var pixelCount = template.Width * template.Height;
        var stride = Math.Max(1, (int)Math.Ceiling(Math.Sqrt(pixelCount / (double)maxSamples)));
        var samples = new List<TemplateSample>();

        for (var y = 0; y < template.Height; y += stride)
        {
            for (var x = 0; x < template.Width; x += stride)
            {
                var color = template.GetPixel(x, y);
                if (color.A < 32)
                {
                    continue;
                }
                samples.Add(new TemplateSample(x, y, color));
            }
        }

        if (samples.Count == 0)
        {
            samples.Add(new TemplateSample(0, 0, template.GetPixel(0, 0)));
        }

        return samples;
    }

    private static double ScoreAt(Bitmap source, IReadOnlyList<TemplateSample> samples, int left, int top)
    {
        var totalDifference = 0.0;

        foreach (var sample in samples)
        {
            var actual = source.GetPixel(left + sample.X, top + sample.Y);
            totalDifference += Math.Abs(actual.R - sample.Color.R);
            totalDifference += Math.Abs(actual.G - sample.Color.G);
            totalDifference += Math.Abs(actual.B - sample.Color.B);
        }

        var maxDifference = samples.Count * 255.0 * 3.0;
        return 1.0 - (totalDifference / maxDifference);
    }

    private readonly record struct TemplateSample(int X, int Y, Color Color);
}

internal sealed class RegionCaptureForm : Form
{
    private readonly bool _captureScreenshots;
    private readonly string _outputDirectory;
    private Point _start;
    private Rectangle _selection;
    private bool _dragging;

    public RegionCaptureForm(bool captureScreenshots)
    {
        _captureScreenshots = captureScreenshots;
        _outputDirectory = AppPaths.ScreenshotsDirectory;
        Text = captureScreenshots ? "Snapshot Region Tool" : "Region Selection Tool";
        FormBorderStyle = FormBorderStyle.None;
        Bounds = SystemInformation.VirtualScreen;
        StartPosition = FormStartPosition.Manual;
        TopMost = true;
        DoubleBuffered = true;
        KeyPreview = true;
        BackColor = Color.Black;
        Opacity = 0.22;
        Cursor = Cursors.Cross;
        ShowInTaskbar = true;
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        Console.WriteLine(_captureScreenshots
            ? "Drag a region to save a screenshot. Press Esc to exit."
            : "Drag a region to print coordinates. Press Esc to exit.");
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Escape)
        {
            Close();
        }
        base.OnKeyDown(e);
    }

    protected override void OnMouseDown(MouseEventArgs e)
    {
        if (e.Button != MouseButtons.Left)
        {
            return;
        }

        _start = PointToScreen(e.Location);
        _selection = Rectangle.Empty;
        _dragging = true;
        Invalidate();
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        if (!_dragging)
        {
            return;
        }

        var current = PointToScreen(e.Location);
        _selection = RectangleFromPoints(_start, current);
        Invalidate();
    }

    protected override void OnMouseUp(MouseEventArgs e)
    {
        if (!_dragging || e.Button != MouseButtons.Left)
        {
            return;
        }

        _dragging = false;
        var current = PointToScreen(e.Location);
        _selection = RectangleFromPoints(_start, current);

        if (_selection.Width <= 2 || _selection.Height <= 2)
        {
            Console.WriteLine("No drag movement detected; region ignored.");
            return;
        }

        Console.WriteLine($"Region defined: ({_selection.Left}, {_selection.Top}, {_selection.Width}, {_selection.Height})");

        if (_captureScreenshots)
        {
            Hide();
            Thread.Sleep(150);
            var path = ScreenAutomation.SaveRegion(_selection, _outputDirectory, "screenshot_region");
            Console.WriteLine($"Captured and saved: {path}");
            Show();
            Activate();
        }

        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        if (_selection.Width <= 0 || _selection.Height <= 0)
        {
            return;
        }

        var clientSelection = new Rectangle(
            _selection.Left - Bounds.Left,
            _selection.Top - Bounds.Top,
            _selection.Width,
            _selection.Height);

        using var fill = new SolidBrush(Color.FromArgb(70, Color.DodgerBlue));
        using var pen = new Pen(Color.White, 2);
        e.Graphics.FillRectangle(fill, clientSelection);
        e.Graphics.DrawRectangle(pen, clientSelection);
    }

    private static Rectangle RectangleFromPoints(Point a, Point b)
    {
        return new Rectangle(
            Math.Min(a.X, b.X),
            Math.Min(a.Y, b.Y),
            Math.Abs(a.X - b.X),
            Math.Abs(a.Y - b.Y));
    }
}

internal sealed class ActionMonitorForm : Form
{
    private readonly List<ActionRecord> _actions = [];
    private readonly ListBox _actionList = new();
    private readonly PictureBox _preview = new();
    private readonly TextBox _tagInput = new();
    private readonly Button _startButton = new() { Text = "Start Monitoring" };
    private readonly Button _stopButton = new() { Text = "Stop Monitoring", Enabled = false };
    private readonly Button _saveTagButton = new() { Text = "Save Tag" };
    private readonly Timer _fullscreenTimer = new() { Interval = 5000 };
    private readonly string _screenshotDirectory = AppPaths.ScreenshotsDirectory;
    private NativeMethods.HookProc? _mouseHookProc;
    private NativeMethods.HookProc? _keyboardHookProc;
    private IntPtr _mouseHook;
    private IntPtr _keyboardHook;
    private bool _dragging;
    private Point _dragStart;
    private DateTime _lastDragLog = DateTime.MinValue;

    public ActionMonitorForm()
    {
        Text = "Cooking Fever Action Monitor";
        Width = 1200;
        Height = 700;

        var root = new SplitContainer { Dock = DockStyle.Fill, SplitterDistance = 430 };
        Controls.Add(root);

        var left = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2 };
        left.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        left.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.LeftToRight };
        buttons.Controls.Add(_startButton);
        buttons.Controls.Add(_stopButton);
        left.Controls.Add(buttons, 0, 0);
        left.Controls.Add(_actionList, 0, 1);
        root.Panel1.Controls.Add(left);

        var right = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2 };
        right.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        right.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        _preview.Dock = DockStyle.Fill;
        _preview.SizeMode = PictureBoxSizeMode.Zoom;
        right.Controls.Add(_preview, 0, 0);

        var tagPanel = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
        tagPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        tagPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110));
        _tagInput.Dock = DockStyle.Fill;
        _tagInput.PlaceholderText = "Enter tag for selected action...";
        tagPanel.Controls.Add(_tagInput, 0, 0);
        tagPanel.Controls.Add(_saveTagButton, 1, 0);
        right.Controls.Add(tagPanel, 0, 1);
        root.Panel2.Controls.Add(right);

        _startButton.Click += (_, _) => StartMonitoring();
        _stopButton.Click += (_, _) => StopMonitoring();
        _saveTagButton.Click += (_, _) => SaveTag();
        _actionList.SelectedIndexChanged += (_, _) => DisplaySelectedScreenshot();
        _fullscreenTimer.Tick += (_, _) => CaptureFullScreen();
        FormClosing += (_, _) => StopMonitoring();
    }

    private void StartMonitoring()
    {
        Directory.CreateDirectory(_screenshotDirectory);
        _startButton.Enabled = false;
        _stopButton.Enabled = true;

        _mouseHookProc = MouseHookCallback;
        _keyboardHookProc = KeyboardHookCallback;
        _mouseHook = NativeMethods.SetHook(NativeMethods.WhMouseLl, _mouseHookProc);
        _keyboardHook = NativeMethods.SetHook(NativeMethods.WhKeyboardLl, _keyboardHookProc);
        _fullscreenTimer.Start();
    }

    private void StopMonitoring()
    {
        _startButton.Enabled = true;
        _stopButton.Enabled = false;
        _fullscreenTimer.Stop();

        if (_mouseHook != IntPtr.Zero)
        {
            NativeMethods.UnhookWindowsHookEx(_mouseHook);
            _mouseHook = IntPtr.Zero;
        }

        if (_keyboardHook != IntPtr.Zero)
        {
            NativeMethods.UnhookWindowsHookEx(_keyboardHook);
            _keyboardHook = IntPtr.Zero;
        }
    }

    private IntPtr MouseHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode >= 0)
        {
            var data = Marshal.PtrToStructure<NativeMethods.MouseHookStruct>(lParam);
            var point = new Point(data.Point.X, data.Point.Y);
            var message = wParam.ToInt32();

            if (message == NativeMethods.WmLbuttonDown)
            {
                _dragging = true;
                _dragStart = point;
                AddAction("mouse_click_down", $"Mouse pressed at ({point.X}, {point.Y})", point);
            }
            else if (message == NativeMethods.WmLbuttonUp)
            {
                _dragging = false;
                AddAction("mouse_click_up", $"Mouse released at ({point.X}, {point.Y}) | Drag from ({_dragStart.X}, {_dragStart.Y})", point);
            }
            else if (message == NativeMethods.WmMouseMove && _dragging && DateTime.Now - _lastDragLog > TimeSpan.FromMilliseconds(250))
            {
                _lastDragLog = DateTime.Now;
                AddAction("mouse_drag", $"Dragging mouse through ({point.X}, {point.Y})", null);
            }
        }

        return NativeMethods.CallNextHookEx(_mouseHook, nCode, wParam, lParam);
    }

    private IntPtr KeyboardHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode >= 0 && wParam.ToInt32() == NativeMethods.WmKeyDown)
        {
            var data = Marshal.PtrToStructure<NativeMethods.KeyboardHookStruct>(lParam);
            var key = (Keys)data.VirtualKeyCode;
            AddAction("key_press", $"Key pressed: {key}", ScreenAutomation.GetCursorPosition());
        }

        return NativeMethods.CallNextHookEx(_keyboardHook, nCode, wParam, lParam);
    }

    private void CaptureFullScreen()
    {
        var path = Path.Combine(_screenshotDirectory, $"fullscreen_{DateTime.Now:yyyy-MM-dd_HH-mm-ss_fffffff}.png");
        using var bitmap = ScreenAutomation.CaptureScreen();
        bitmap.Save(path, ImageFormat.Png);
        AddActionRecord(new ActionRecord("periodic_fullscreen", "Periodic full-screen capture", path));
    }

    private void AddAction(string actionType, string description, Point? screenshotPoint)
    {
        string? path = null;
        if (screenshotPoint.HasValue)
        {
            var region = ScreenAutomation.CenteredRegion(screenshotPoint.Value, 100);
            path = ScreenAutomation.SaveRegion(region, _screenshotDirectory, "screenshot_region");
        }

        AddActionRecord(new ActionRecord(actionType, description, path));
    }

    private void AddActionRecord(ActionRecord action)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => AddActionRecord(action));
            return;
        }

        _actions.Add(action);
        _actionList.Items.Add(action.ToString());
    }

    private void DisplaySelectedScreenshot()
    {
        var index = _actionList.SelectedIndex;
        if (index < 0 || index >= _actions.Count)
        {
            _preview.Image = null;
            return;
        }

        var action = _actions[index];
        if (string.IsNullOrWhiteSpace(action.ScreenshotPath) || !File.Exists(action.ScreenshotPath))
        {
            _preview.Image = null;
            return;
        }

        _preview.Image?.Dispose();
        _preview.Image = Image.FromFile(action.ScreenshotPath);
    }

    private void SaveTag()
    {
        var index = _actionList.SelectedIndex;
        if (index < 0 || index >= _actions.Count)
        {
            MessageBox.Show("Select an action first.", "No Selection", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var tag = _tagInput.Text.Trim();
        if (tag.Length == 0)
        {
            MessageBox.Show("Enter a tag before saving.", "No Tag", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        _actions[index].Tag = tag;
        _actionList.Items[index] = _actions[index].ToString();
        _tagInput.Clear();
    }
}

internal sealed class ActionRecord
{
    public ActionRecord(string actionType, string description, string? screenshotPath)
    {
        Timestamp = DateTime.Now;
        ActionType = actionType;
        Description = description;
        ScreenshotPath = screenshotPath;
    }

    public DateTime Timestamp { get; }
    public string ActionType { get; }
    public string Description { get; }
    public string? ScreenshotPath { get; }
    public string Tag { get; set; } = "";

    public override string ToString()
    {
        return $"{Timestamp:yyyy-MM-dd_HH-mm-ss} - {ActionType}: {Description} (Tag: {Tag})";
    }
}

internal sealed class TodoForm : Form
{
    private readonly List<Objective> _objectives = [];
    private readonly ListBox _objectiveList = new();
    private readonly DataGridView _taskGrid = new();
    private readonly ProgressBar _progress = new() { Minimum = 0, Maximum = 100 };
    private readonly Label _remaining = new() { Text = "Estimated time remaining: 0 mins", AutoSize = true };

    public TodoForm()
    {
        Text = "Todo App with Objectives";
        Width = 900;
        Height = 560;

        var root = new SplitContainer { Dock = DockStyle.Fill, SplitterDistance = 270 };
        Controls.Add(root);

        var left = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 3 };
        left.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));
        left.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        left.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        left.Controls.Add(new Label { Text = "Objectives", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft }, 0, 0);
        left.Controls.Add(_objectiveList, 0, 1);
        var addObjective = new Button { Text = "Add Objective", Dock = DockStyle.Fill };
        left.Controls.Add(addObjective, 0, 2);
        root.Panel1.Controls.Add(left);

        var right = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 6 };
        right.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));
        right.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        right.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));
        right.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));
        right.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        right.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));

        _taskGrid.Dock = DockStyle.Fill;
        _taskGrid.AllowUserToAddRows = false;
        _taskGrid.AllowUserToDeleteRows = false;
        _taskGrid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
        _taskGrid.Columns.Add(new DataGridViewCheckBoxColumn { HeaderText = "Done", FillWeight = 20 });
        _taskGrid.Columns.Add(new DataGridViewTextBoxColumn { HeaderText = "Task", ReadOnly = true });
        _taskGrid.Columns.Add(new DataGridViewTextBoxColumn { HeaderText = "Priority", ReadOnly = true, FillWeight = 35 });
        _taskGrid.Columns.Add(new DataGridViewTextBoxColumn { HeaderText = "Duration (mins)", ReadOnly = true, FillWeight = 35 });

        right.Controls.Add(new Label { Text = "Tasks", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft }, 0, 0);
        right.Controls.Add(_taskGrid, 0, 1);
        right.Controls.Add(new Label { Text = "Objective Progress", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft }, 0, 2);
        right.Controls.Add(_progress, 0, 3);
        right.Controls.Add(_remaining, 0, 4);
        var addTask = new Button { Text = "Add Task", Dock = DockStyle.Fill };
        right.Controls.Add(addTask, 0, 5);
        root.Panel2.Controls.Add(right);

        addObjective.Click += (_, _) => AddObjective();
        addTask.Click += (_, _) => AddTask();
        _objectiveList.SelectedIndexChanged += (_, _) => UpdateTaskGrid();
        _taskGrid.CellValueChanged += (_, e) => UpdateTaskStatus(e.RowIndex);
        _taskGrid.CurrentCellDirtyStateChanged += (_, _) =>
        {
            if (_taskGrid.IsCurrentCellDirty)
            {
                _taskGrid.CommitEdit(DataGridViewDataErrorContexts.Commit);
            }
        };
    }

    private Objective? SelectedObjective => _objectiveList.SelectedIndex >= 0 && _objectiveList.SelectedIndex < _objectives.Count
        ? _objectives[_objectiveList.SelectedIndex]
        : null;

    private void AddObjective()
    {
        using var dialog = new ObjectiveDialog();
        if (dialog.ShowDialog(this) != DialogResult.OK)
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(dialog.ObjectiveTitle))
        {
            MessageBox.Show("Objective title cannot be empty.", "Input Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var objective = new Objective(dialog.ObjectiveTitle, dialog.Repeatable);
        _objectives.Add(objective);
        _objectiveList.Items.Add(objective.Title);
    }

    private void AddTask()
    {
        var objective = SelectedObjective;
        if (objective is null)
        {
            MessageBox.Show("Select an objective first.", "No Objective Selected", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        using var dialog = new TaskDialog();
        if (dialog.ShowDialog(this) != DialogResult.OK)
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(dialog.TaskTitle))
        {
            MessageBox.Show("Task title cannot be empty.", "Input Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        objective.Tasks.Add(new TodoTask(dialog.TaskTitle, dialog.Priority, dialog.Duration));
        UpdateTaskGrid();
    }

    private void UpdateTaskGrid()
    {
        _taskGrid.Rows.Clear();
        var objective = SelectedObjective;
        if (objective is null)
        {
            UpdateProgress();
            return;
        }

        foreach (var task in objective.Tasks)
        {
            _taskGrid.Rows.Add(task.Completed, task.Title, task.Priority, task.Duration);
        }

        UpdateProgress();
    }

    private void UpdateTaskStatus(int rowIndex)
    {
        var objective = SelectedObjective;
        if (objective is null || rowIndex < 0 || rowIndex >= objective.Tasks.Count)
        {
            return;
        }

        objective.Tasks[rowIndex].Completed = Convert.ToBoolean(_taskGrid.Rows[rowIndex].Cells[0].Value);
        UpdateProgress();
    }

    private void UpdateProgress()
    {
        var objective = SelectedObjective;
        if (objective is null || objective.Tasks.Count == 0)
        {
            _progress.Value = 0;
            _remaining.Text = "Estimated time remaining: 0 mins";
            return;
        }

        var completed = objective.Tasks.Count(t => t.Completed);
        _progress.Value = (int)Math.Round(completed * 100.0 / objective.Tasks.Count);
        var remainingMinutes = objective.Tasks.Where(t => !t.Completed).Sum(t => t.Duration);
        _remaining.Text = $"Estimated time remaining: {remainingMinutes} mins";
    }
}

internal sealed record Objective(string Title, bool Repeatable)
{
    public List<TodoTask> Tasks { get; } = [];
}

internal sealed record TodoTask(string Title, string Priority, int Duration)
{
    public bool Completed { get; set; }
}

internal sealed class ObjectiveDialog : Form
{
    private readonly TextBox _title = new() { Dock = DockStyle.Fill };
    private readonly CheckBox _repeatable = new() { Text = "Repeatable", Dock = DockStyle.Fill };

    public ObjectiveDialog()
    {
        Text = "Add Objective";
        Width = 380;
        Height = 160;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterParent;
        MinimizeBox = false;
        MaximizeBox = false;

        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 3, ColumnCount = 2, Padding = new Padding(10) };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        layout.Controls.Add(new Label { Text = "Title:", TextAlign = ContentAlignment.MiddleLeft, Dock = DockStyle.Fill }, 0, 0);
        layout.Controls.Add(_title, 1, 0);
        layout.Controls.Add(_repeatable, 1, 1);

        var ok = new Button { Text = "OK", DialogResult = DialogResult.OK };
        var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel };
        var buttons = new FlowLayoutPanel { FlowDirection = FlowDirection.RightToLeft, Dock = DockStyle.Fill };
        buttons.Controls.Add(cancel);
        buttons.Controls.Add(ok);
        layout.Controls.Add(buttons, 0, 2);
        layout.SetColumnSpan(buttons, 2);
        Controls.Add(layout);
        AcceptButton = ok;
        CancelButton = cancel;
    }

    public string ObjectiveTitle => _title.Text.Trim();
    public bool Repeatable => _repeatable.Checked;
}

internal sealed class TaskDialog : Form
{
    private readonly TextBox _title = new() { Dock = DockStyle.Fill };
    private readonly ComboBox _priority = new() { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly NumericUpDown _duration = new() { Dock = DockStyle.Left, Maximum = 10000 };

    public TaskDialog()
    {
        Text = "Add Task";
        Width = 420;
        Height = 190;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterParent;
        MinimizeBox = false;
        MaximizeBox = false;
        _priority.Items.AddRange(["High", "Medium", "Low"]);
        _priority.SelectedIndex = 1;

        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 4, ColumnCount = 2, Padding = new Padding(10) };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        layout.Controls.Add(new Label { Text = "Task Title:", TextAlign = ContentAlignment.MiddleLeft, Dock = DockStyle.Fill }, 0, 0);
        layout.Controls.Add(_title, 1, 0);
        layout.Controls.Add(new Label { Text = "Priority:", TextAlign = ContentAlignment.MiddleLeft, Dock = DockStyle.Fill }, 0, 1);
        layout.Controls.Add(_priority, 1, 1);
        layout.Controls.Add(new Label { Text = "Duration:", TextAlign = ContentAlignment.MiddleLeft, Dock = DockStyle.Fill }, 0, 2);
        layout.Controls.Add(_duration, 1, 2);

        var ok = new Button { Text = "OK", DialogResult = DialogResult.OK };
        var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel };
        var buttons = new FlowLayoutPanel { FlowDirection = FlowDirection.RightToLeft, Dock = DockStyle.Fill };
        buttons.Controls.Add(cancel);
        buttons.Controls.Add(ok);
        layout.Controls.Add(buttons, 0, 3);
        layout.SetColumnSpan(buttons, 2);
        Controls.Add(layout);
        AcceptButton = ok;
        CancelButton = cancel;
    }

    public string TaskTitle => _title.Text.Trim();
    public string Priority => _priority.SelectedItem?.ToString() ?? "Medium";
    public int Duration => (int)_duration.Value;
}

internal static class RectangleExtensions
{
    public static Point Center(this Rectangle rectangle)
    {
        return new Point(rectangle.Left + rectangle.Width / 2, rectangle.Top + rectangle.Height / 2);
    }
}

internal static class NativeMethods
{
    public const int WhKeyboardLl = 13;
    public const int WhMouseLl = 14;
    public const int WmKeyDown = 0x0100;
    public const int WmLbuttonDown = 0x0201;
    public const int WmLbuttonUp = 0x0202;
    public const int WmMouseMove = 0x0200;

    private const uint MouseEventLeftDown = 0x0002;
    private const uint MouseEventLeftUp = 0x0004;

    public delegate IntPtr HookProc(int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    private static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);

    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int virtualKeyCode);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, HookProc lpfn, IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool UnhookWindowsHookEx(IntPtr hook);

    [DllImport("user32.dll")]
    public static extern IntPtr CallNextHookEx(IntPtr hook, int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string? moduleName);

    public static void MouseDown() => mouse_event(MouseEventLeftDown, 0, 0, 0, UIntPtr.Zero);
    public static void MouseUp() => mouse_event(MouseEventLeftUp, 0, 0, 0, UIntPtr.Zero);
    public static bool IsKeyDown(Keys key) => (GetAsyncKeyState((int)key) & 0x8000) != 0;

    public static IntPtr SetHook(int hookType, HookProc proc)
    {
        using var currentProcess = Process.GetCurrentProcess();
        using var currentModule = currentProcess.MainModule;
        var moduleHandle = GetModuleHandle(currentModule?.ModuleName);
        return SetWindowsHookEx(hookType, proc, moduleHandle, 0);
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct HookPoint
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MouseHookStruct
    {
        public HookPoint Point;
        public int MouseData;
        public int Flags;
        public int Time;
        public IntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct KeyboardHookStruct
    {
        public int VirtualKeyCode;
        public int ScanCode;
        public int Flags;
        public int Time;
        public IntPtr ExtraInfo;
    }
}
