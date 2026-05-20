using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;

namespace CookingFeverTools;

internal sealed class DashboardForm : Form
{
    private readonly BotProcessController _bot = new();
    private readonly ComboBox _profileCombo = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 260 };
    private readonly NumericUpDown _confidence = new()
    {
        DecimalPlaces = 2,
        Increment = 0.05M,
        Minimum = 0.1M,
        Maximum = 1M,
        Value = 0.8M,
        Width = 80
    };
    private readonly CheckBox _dryRun = new() { Text = "Dry Run", AutoSize = true };
    private readonly System.Windows.Forms.Timer _mouseTimer = new() { Interval = 250 };
    private readonly Button _mouseTracker = new() { Text = "Track Mouse", Width = 130, Height = 30 };
    private readonly Label _mousePosition = new()
    {
        AutoSize = false,
        Width = 210,
        Height = 30,
        Text = "Mouse: not tracking",
        TextAlign = ContentAlignment.MiddleLeft
    };
    private readonly TextBox _log = new()
    {
        Dock = DockStyle.Fill,
        Multiline = true,
        ReadOnly = true,
        ScrollBars = ScrollBars.Vertical,
        Font = new Font("Consolas", 9)
    };
    private readonly Label _profileSummary = new()
    {
        Dock = DockStyle.Fill,
        AutoEllipsis = true,
        TextAlign = ContentAlignment.MiddleLeft
    };
    private readonly Label _status = new()
    {
        Dock = DockStyle.Fill,
        Text = "Ready",
        TextAlign = ContentAlignment.MiddleLeft
    };
    private readonly Button _start = new() { Text = "Start Bot", Width = 110, Height = 34 };
    private readonly Button _stop = new() { Text = "Stop Bot", Width = 110, Height = 34, Enabled = false };

    public DashboardForm()
    {
        Text = "Cooking Fever Tools";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(1060, 720);
        Size = new Size(1180, 780);
        Font = new Font("Segoe UI", 9.5f, FontStyle.Regular, GraphicsUnit.Point);

        ProfileStore.EnsureDirectories();
        BuildLayout();
        WireEvents();
        LoadProfiles();
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _mouseTimer.Stop();
        _bot.Dispose();
        base.OnFormClosing(e);
    }

    private RestaurantProfile? SelectedProfile => (_profileCombo.SelectedItem as ProfileListItem)?.Profile;

    private void BuildLayout()
    {
        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(16),
            RowCount = 4,
            ColumnCount = 1
        };
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 56));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        Controls.Add(root);

        var title = new Label
        {
            Text = "Cooking Fever Tools",
            Dock = DockStyle.Fill,
            Font = new Font(Font.FontFamily, 20, FontStyle.Bold),
            TextAlign = ContentAlignment.MiddleLeft
        };
        root.Controls.Add(title, 0, 0);
        root.Controls.Add(_profileSummary, 0, 1);

        var split = new SplitContainer
        {
            Dock = DockStyle.Fill,
            SplitterDistance = 360
        };
        root.Controls.Add(split, 0, 2);
        split.Panel1.Controls.Add(BuildControls());

        var logPanel = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            RowCount = 2,
            ColumnCount = 1
        };
        logPanel.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        logPanel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        logPanel.Controls.Add(new Label
        {
            Text = "Bot Log",
            Dock = DockStyle.Fill,
            Font = new Font(Font.FontFamily, 11, FontStyle.Bold),
            TextAlign = ContentAlignment.MiddleLeft
        }, 0, 0);
        logPanel.Controls.Add(_log, 0, 1);
        split.Panel2.Controls.Add(logPanel);
        root.Controls.Add(_status, 0, 3);
    }

    private Control BuildControls()
    {
        var panel = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            RowCount = 4,
            ColumnCount = 1,
            Padding = new Padding(0, 0, 14, 0)
        };
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 160));
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 150));
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 190));
        panel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        panel.Controls.Add(BuildProfileGroup(), 0, 0);
        panel.Controls.Add(BuildBotGroup(), 0, 1);
        panel.Controls.Add(BuildToolGroup(), 0, 2);
        panel.Controls.Add(BuildFolderGroup(), 0, 3);
        return panel;
    }

    private Control BuildProfileGroup()
    {
        var group = new GroupBox { Text = "Profile", Dock = DockStyle.Fill };
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(10),
            RowCount = 3,
            ColumnCount = 1
        };
        group.Controls.Add(layout);
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));

        layout.Controls.Add(_profileCombo, 0, 0);
        var row1 = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
        row1.Controls.Add(CreateButton("New", NewProfile));
        row1.Controls.Add(CreateButton("Save", SaveSelectedProfile));
        row1.Controls.Add(CreateButton("Delete", DeleteSelectedProfile));
        layout.Controls.Add(row1, 0, 1);

        var row2 = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
        row2.Controls.Add(CreateButton("Calibrate", CalibrateProfile));
        row2.Controls.Add(CreateButton("Assets", OpenAssetManager));
        layout.Controls.Add(row2, 0, 2);
        return group;
    }

    private Control BuildBotGroup()
    {
        var group = new GroupBox { Text = "Bot", Dock = DockStyle.Fill };
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(10),
            RowCount = 3,
            ColumnCount = 1
        };
        group.Controls.Add(layout);
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));

        var settings = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
        settings.Controls.Add(new Label { Text = "Confidence", AutoSize = true, Padding = new Padding(0, 7, 4, 0) });
        settings.Controls.Add(_confidence);
        settings.Controls.Add(_dryRun);
        layout.Controls.Add(settings, 0, 0);

        var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
        actions.Controls.Add(_start);
        actions.Controls.Add(_stop);
        layout.Controls.Add(actions, 0, 1);

        layout.Controls.Add(new Label
        {
            Text = "Dashboard start runs immediately. Keyboard controls still work: p pauses/resumes, gg stops.",
            Dock = DockStyle.Fill,
            AutoEllipsis = true,
            TextAlign = ContentAlignment.MiddleLeft
        }, 0, 2);
        return group;
    }

    private Control BuildToolGroup()
    {
        var group = new GroupBox { Text = "Utilities", Dock = DockStyle.Fill };
        var layout = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(10),
            WrapContents = true
        };
        group.Controls.Add(layout);
        layout.Controls.Add(CreateButton("Action Monitor", () => OpenToolWindow(new ActionMonitorForm()), 140));
        layout.Controls.Add(CreateButton("Todo Utility", () => OpenToolWindow(new TodoForm()), 120));
        layout.Controls.Add(CreateButton("Select Region", () => OpenRegionTool(false), 120));
        layout.Controls.Add(CreateButton("Snapshot Region", () => OpenRegionTool(true), 140));
        layout.Controls.Add(_mouseTracker);
        layout.Controls.Add(_mousePosition);
        return group;
    }

    private Control BuildFolderGroup()
    {
        var group = new GroupBox { Text = "Folders", Dock = DockStyle.Fill };
        var layout = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(10),
            WrapContents = true
        };
        group.Controls.Add(layout);
        layout.Controls.Add(CreateButton("Profiles", () => OpenFolder(AppPaths.ProfilesDirectory), 110));
        layout.Controls.Add(CreateButton("Assets", () => OpenFolder(AppPaths.AssetsDirectory), 110));
        layout.Controls.Add(CreateButton("Screenshots", () => OpenFolder(AppPaths.ScreenshotsDirectory), 130));
        layout.Controls.Add(CreateButton("Logs", () => OpenFolder(AppPaths.LogsDirectory), 100));
        layout.Controls.Add(CreateButton("Clear Log", () => _log.Clear(), 100));
        return group;
    }

    private Button CreateButton(string text, Action action, int width = 90)
    {
        var button = new Button
        {
            Text = text,
            Width = width,
            Height = 30,
            Margin = new Padding(4)
        };
        button.Click += (_, _) => RunSafely(action);
        return button;
    }

    private void WireEvents()
    {
        _profileCombo.SelectedIndexChanged += (_, _) => UpdateProfileSummary();
        _start.Click += (_, _) => RunSafely(StartBot);
        _stop.Click += (_, _) => RunSafely(StopBot);
        _mouseTracker.Click += (_, _) => RunSafely(ToggleMouseTracker);
        _mouseTimer.Tick += (_, _) => UpdateMousePosition();
        _bot.LogReceived += AppendLog;
        _bot.StateChanged += state =>
        {
            RunOnUi(() =>
            {
                _status.Text = state;
                _start.Enabled = !_bot.IsRunning;
                _stop.Enabled = _bot.IsRunning;
            });
        };
    }

    private void LoadProfiles(string? selectPath = null)
    {
        var profiles = ProfileStore.LoadAll();
        _profileCombo.Items.Clear();

        foreach (var profile in profiles)
        {
            _profileCombo.Items.Add(new ProfileListItem(profile));
        }

        if (_profileCombo.Items.Count == 0)
        {
            return;
        }

        var selectedIndex = 0;
        if (!string.IsNullOrWhiteSpace(selectPath))
        {
            for (var i = 0; i < _profileCombo.Items.Count; i++)
            {
                if (_profileCombo.Items[i] is ProfileListItem item &&
                    string.Equals(item.Profile.FilePath, selectPath, StringComparison.OrdinalIgnoreCase))
                {
                    selectedIndex = i;
                    break;
                }
            }
        }

        _profileCombo.SelectedIndex = selectedIndex;
        UpdateProfileSummary();
    }

    private void NewProfile()
    {
        var name = PromptDialog.Show(this, "New Profile", "Profile name", "New Restaurant");
        if (name is null)
        {
            return;
        }

        var profile = ProfileStore.Create(name);
        LoadProfiles(profile.FilePath);
        AppendLog($"Created profile: {profile.Name}");
    }

    private void SaveSelectedProfile()
    {
        var profile = SelectedProfile;
        if (profile is null)
        {
            return;
        }

        ProfileStore.Save(profile);
        UpdateProfileSummary();
        AppendLog($"Saved profile: {profile.Name}");
    }

    private void DeleteSelectedProfile()
    {
        var profile = SelectedProfile;
        if (profile is null)
        {
            return;
        }

        var result = MessageBox.Show(this, $"Delete profile '{profile.Name}'?", "Delete Profile", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
        if (result != DialogResult.Yes)
        {
            return;
        }

        ProfileStore.Delete(profile);
        ProfileStore.EnsureDefaultProfile();
        LoadProfiles();
    }

    private void CalibrateProfile()
    {
        var profile = SelectedProfile;
        if (profile is null)
        {
            return;
        }

        using var dialog = new CalibrationForm(profile);
        if (dialog.ShowDialog(this) != DialogResult.OK)
        {
            return;
        }

        var updated = dialog.Profile;
        updated.FilePath = profile.FilePath;
        updated.Name = profile.Name;
        updated.AssetsDirectory = profile.AssetsDirectory;
        ProfileStore.Save(updated);
        LoadProfiles(updated.FilePath);
        AppendLog($"Updated calibration for: {updated.Name}");
    }

    private void OpenAssetManager()
    {
        var profile = SelectedProfile;
        if (profile is null)
        {
            return;
        }

        using var dialog = new AssetManagerForm(profile);
        dialog.ShowDialog(this);
    }

    private void StartBot()
    {
        var profile = SelectedProfile;
        if (profile is null)
        {
            return;
        }

        ProfileStore.Save(profile);
        Directory.CreateDirectory(ResolveAssetsDirectory(profile));
        AppendLog($"Starting bot with profile: {profile.Name}");
        _bot.Start(new BotLaunchOptions(
            profile.FilePath,
            ResolveAssetsDirectory(profile),
            (double)_confidence.Value,
            _dryRun.Checked));
        _start.Enabled = false;
        _stop.Enabled = true;
    }

    private void StopBot()
    {
        _bot.Stop();
        _status.Text = "Stopping";
    }

    private void ToggleMouseTracker()
    {
        if (_mouseTimer.Enabled)
        {
            _mouseTimer.Stop();
            _mouseTracker.Text = "Track Mouse";
            _mousePosition.Text = "Mouse: not tracking";
            _status.Text = "Mouse tracking stopped";
            return;
        }

        UpdateMousePosition();
        _mouseTimer.Start();
        _mouseTracker.Text = "Stop Tracking";
        _status.Text = "Mouse tracking in dashboard";
    }

    private void UpdateMousePosition()
    {
        var point = ScreenAutomation.GetCursorPosition();
        _mousePosition.Text = $"Mouse: X={point.X}, Y={point.Y}";
    }

    private void OpenRegionTool(bool captureScreenshots)
    {
        Hide();
        var form = new RegionCaptureForm(captureScreenshots);
        form.FormClosed += (_, _) =>
        {
            Show();
            Activate();
        };
        form.Show();
    }

    private void OpenToolWindow(Form form)
    {
        form.StartPosition = FormStartPosition.CenterScreen;
        form.Show(this);
    }

    private static void OpenFolder(string directory)
    {
        Directory.CreateDirectory(directory);
        Process.Start(new ProcessStartInfo
        {
            FileName = directory,
            UseShellExecute = true
        });
    }

    private void UpdateProfileSummary()
    {
        var profile = SelectedProfile;
        if (profile is null)
        {
            _profileSummary.Text = "No profile selected";
            return;
        }

        _profileSummary.Text = $"Profile: {profile.Name} | File: {profile.FilePath} | Assets: {ResolveAssetsDirectory(profile)}";
    }

    private static string ResolveAssetsDirectory(RestaurantProfile profile)
    {
        return string.IsNullOrWhiteSpace(profile.AssetsDirectory)
            ? AppPaths.AssetsDirectory
            : Path.GetFullPath(profile.AssetsDirectory);
    }

    private void AppendLog(string message)
    {
        RunOnUi(() =>
        {
            var line = $"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}";
            _log.AppendText(line);
            Directory.CreateDirectory(AppPaths.LogsDirectory);
            File.AppendAllText(Path.Combine(AppPaths.LogsDirectory, "dashboard.log"), line);
        });
    }

    private void RunSafely(Action action)
    {
        try
        {
            action();
        }
        catch (Exception ex)
        {
            _status.Text = ex.Message;
            MessageBox.Show(this, ex.Message, "Cooking Fever Tools", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void RunOnUi(Action action)
    {
        if (IsDisposed)
        {
            return;
        }

        if (InvokeRequired)
        {
            BeginInvoke(action);
            return;
        }

        action();
    }

    private sealed class ProfileListItem
    {
        public ProfileListItem(RestaurantProfile profile)
        {
            Profile = profile;
        }

        public RestaurantProfile Profile { get; }
        public override string ToString() => Profile.Name;
    }
}
