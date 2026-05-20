using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Windows.Forms;

namespace CookingFeverTools;

internal sealed class AssetManagerForm : Form
{
    private readonly RestaurantProfile _profile;
    private readonly ListBox _assets = new() { Dock = DockStyle.Fill };
    private readonly PictureBox _preview = new()
    {
        Dock = DockStyle.Fill,
        SizeMode = PictureBoxSizeMode.Zoom,
        BackColor = Color.White
    };
    private readonly NumericUpDown _confidence = new()
    {
        DecimalPlaces = 2,
        Increment = 0.05M,
        Minimum = 0.1M,
        Maximum = 1M,
        Value = 0.8M,
        Width = 80
    };
    private readonly Label _status = new()
    {
        Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleLeft
    };

    public AssetManagerForm(RestaurantProfile profile)
    {
        _profile = profile;
        Text = $"Assets - {_profile.Name}";
        StartPosition = FormStartPosition.CenterParent;
        MinimumSize = new Size(860, 540);
        Size = new Size(940, 620);

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(14),
            RowCount = 3,
            ColumnCount = 1
        };
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        Controls.Add(root);

        var toolbar = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false
        };
        root.Controls.Add(toolbar, 0, 0);

        toolbar.Controls.Add(CreateButton("Open Folder", OpenAssetFolder));
        toolbar.Controls.Add(CreateButton("Refresh", RefreshAssets));
        toolbar.Controls.Add(CreateButton("Capture Template", CaptureTemplate));
        toolbar.Controls.Add(CreateButton("Test Selected", TestSelected));
        toolbar.Controls.Add(new Label { Text = "Confidence", AutoSize = true, TextAlign = ContentAlignment.MiddleLeft, Padding = new Padding(12, 8, 2, 0) });
        toolbar.Controls.Add(_confidence);

        var split = new SplitContainer
        {
            Dock = DockStyle.Fill,
            SplitterDistance = 280
        };
        root.Controls.Add(split, 0, 1);

        _assets.SelectedIndexChanged += (_, _) => DisplaySelectedAsset();
        split.Panel1.Controls.Add(_assets);
        split.Panel2.Controls.Add(_preview);

        _status.Text = $"Assets folder: {AssetsDirectory}";
        root.Controls.Add(_status, 0, 2);
        RefreshAssets();
    }

    private string AssetsDirectory => string.IsNullOrWhiteSpace(_profile.AssetsDirectory)
        ? AppPaths.AssetsDirectory
        : Path.GetFullPath(_profile.AssetsDirectory);

    private Button CreateButton(string text, Action action)
    {
        var button = new Button
        {
            Text = text,
            AutoSize = true,
            Height = 30,
            Margin = new Padding(4)
        };
        button.Click += (_, _) => RunSafely(action);
        return button;
    }

    private void OpenAssetFolder()
    {
        Directory.CreateDirectory(AssetsDirectory);
        Process.Start(new ProcessStartInfo
        {
            FileName = AssetsDirectory,
            UseShellExecute = true
        });
    }

    private void RefreshAssets()
    {
        Directory.CreateDirectory(AssetsDirectory);
        _assets.Items.Clear();

        foreach (var path in Directory.EnumerateFiles(AssetsDirectory)
            .Where(IsImageFile)
            .OrderBy(Path.GetFileName))
        {
            _assets.Items.Add(path);
        }

        _status.Text = $"{_assets.Items.Count} image asset(s) in {AssetsDirectory}";
    }

    private void CaptureTemplate()
    {
        var name = PromptDialog.Show(this, "Capture Template", "Template file name", "new-template.png");
        if (string.IsNullOrWhiteSpace(name))
        {
            return;
        }

        var fileName = Path.GetFileNameWithoutExtension(name.Trim());
        if (fileName.Length == 0)
        {
            return;
        }

        Hide();
        var region = CaptureOverlayForm.CaptureRegion(this, fileName);
        Show();
        Activate();

        if (!region.HasValue)
        {
            return;
        }

        Directory.CreateDirectory(AssetsDirectory);
        var path = Path.Combine(AssetsDirectory, $"{fileName}.png");
        using var bitmap = ScreenAutomation.Capture(region.Value);
        bitmap.Save(path, ImageFormat.Png);
        RefreshAssets();
        _assets.SelectedItem = path;
        _status.Text = $"Saved template: {path}";
    }

    private void TestSelected()
    {
        var path = SelectedPath;
        if (path is null)
        {
            return;
        }

        var match = TemplateMatcher.Locate(path, null, (double)_confidence.Value);
        _status.Text = match is null
            ? $"No match found for {Path.GetFileName(path)}"
            : $"Match: {Path.GetFileName(path)} at {match.Bounds.X}, {match.Bounds.Y}, {match.Bounds.Width}, {match.Bounds.Height} with {match.Confidence:P1}";
    }

    private void DisplaySelectedAsset()
    {
        _preview.Image?.Dispose();
        _preview.Image = null;

        var path = SelectedPath;
        if (path is null || !File.Exists(path))
        {
            return;
        }

        using var stream = File.OpenRead(path);
        using var image = Image.FromStream(stream);
        _preview.Image = new Bitmap(image);
        _status.Text = path;
    }

    private string? SelectedPath => _assets.SelectedItem as string;

    private static bool IsImageFile(string path)
    {
        var extension = Path.GetExtension(path).ToLowerInvariant();
        return extension is ".png" or ".jpg" or ".jpeg" or ".bmp";
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
            MessageBox.Show(this, ex.Message, "Asset Manager", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
