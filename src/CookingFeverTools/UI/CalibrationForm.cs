using System.Drawing;
using System.Windows.Forms;

namespace CookingFeverTools;

internal sealed class CalibrationForm : Form
{
    private readonly RestaurantProfile _profile;
    private readonly ListView _pointList = new();
    private readonly ListView _regionList = new();
    private readonly Dictionary<string, NumericUpDown> _timingInputs = [];

    public CalibrationForm(RestaurantProfile profile)
    {
        _profile = profile.Clone();
        Text = $"Calibrate - {_profile.Name}";
        StartPosition = FormStartPosition.CenterParent;
        MinimumSize = new Size(920, 640);
        Size = new Size(980, 700);

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(14),
            RowCount = 3,
            ColumnCount = 1
        };
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
        Controls.Add(root);

        root.Controls.Add(new Label
        {
            Text = "Capture screen positions, order detection regions, and timing values for this restaurant profile.",
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft
        }, 0, 0);

        var tabs = new TabControl { Dock = DockStyle.Fill };
        tabs.TabPages.Add(BuildPointPage());
        tabs.TabPages.Add(BuildRegionPage());
        tabs.TabPages.Add(BuildTimingPage());
        root.Controls.Add(tabs, 0, 1);

        var buttons = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft
        };
        var save = new Button { Text = "Save", Width = 100, Height = 32 };
        var cancel = new Button { Text = "Cancel", Width = 100, Height = 32 };
        var reset = new Button { Text = "Reset Defaults", Width = 120, Height = 32 };
        save.Click += (_, _) =>
        {
            SaveTimings();
            DialogResult = DialogResult.OK;
            Close();
        };
        cancel.Click += (_, _) =>
        {
            DialogResult = DialogResult.Cancel;
            Close();
        };
        reset.Click += (_, _) => ResetDefaults();
        buttons.Controls.Add(cancel);
        buttons.Controls.Add(save);
        buttons.Controls.Add(reset);
        root.Controls.Add(buttons, 0, 2);
    }

    public RestaurantProfile Profile => _profile;

    private TabPage BuildPointPage()
    {
        var page = new TabPage("Positions");
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(8),
            RowCount = 2,
            ColumnCount = 1
        };
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        page.Controls.Add(layout);

        SetupList(_pointList);
        layout.Controls.Add(_pointList, 0, 0);

        var capture = new Button { Text = "Capture Selected Position", Dock = DockStyle.Left, Width = 190 };
        capture.Click += (_, _) => CaptureSelectedPoint();
        layout.Controls.Add(capture, 0, 1);
        RefreshPoints();
        return page;
    }

    private TabPage BuildRegionPage()
    {
        var page = new TabPage("Order Regions");
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(8),
            RowCount = 2,
            ColumnCount = 1
        };
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        page.Controls.Add(layout);

        SetupList(_regionList);
        layout.Controls.Add(_regionList, 0, 0);

        var capture = new Button { Text = "Capture Selected Region", Dock = DockStyle.Left, Width = 190 };
        capture.Click += (_, _) => CaptureSelectedRegion();
        layout.Controls.Add(capture, 0, 1);
        RefreshRegions();
        return page;
    }

    private TabPage BuildTimingPage()
    {
        var page = new TabPage("Timings");
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            Padding = new Padding(8),
            AutoSize = true,
            RowCount = ProfileKeys.TimingDefinitions.Count,
            ColumnCount = 2
        };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 220));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 120));
        page.Controls.Add(layout);

        var row = 0;
        foreach (var definition in ProfileKeys.TimingDefinitions)
        {
            var input = new NumericUpDown
            {
                DecimalPlaces = 1,
                Increment = 0.5M,
                Minimum = 0.1M,
                Maximum = 120M,
                Value = (decimal)_profile.GetTiming(definition.Key, definition.DefaultValue),
                Dock = DockStyle.Left,
                Width = 110
            };
            _timingInputs[definition.Key] = input;
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
            layout.Controls.Add(new Label
            {
                Text = definition.Label,
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleLeft
            }, 0, row);
            layout.Controls.Add(input, 1, row);
            row++;
        }

        return page;
    }

    private static void SetupList(ListView list)
    {
        list.Dock = DockStyle.Fill;
        list.View = View.Details;
        list.FullRowSelect = true;
        list.GridLines = true;
        list.Columns.Add("Name", 260);
        list.Columns.Add("Value", 260);
    }

    private void CaptureSelectedPoint()
    {
        if (_pointList.SelectedItems.Count == 0)
        {
            return;
        }

        var item = _pointList.SelectedItems[0];
        if (item.Tag is not ProfilePointDefinition definition)
        {
            return;
        }

        Hide();
        var point = CaptureOverlayForm.CapturePoint(this, definition.Label);
        Show();
        Activate();

        if (point.HasValue)
        {
            _profile.SetPoint(definition.Key, point.Value);
            RefreshPoints();
        }
    }

    private void CaptureSelectedRegion()
    {
        if (_regionList.SelectedItems.Count == 0)
        {
            return;
        }

        var item = _regionList.SelectedItems[0];
        if (item.Tag is not ProfileRegionDefinition definition)
        {
            return;
        }

        Hide();
        var region = CaptureOverlayForm.CaptureRegion(this, definition.Label);
        Show();
        Activate();

        if (region.HasValue)
        {
            _profile.SetRegion(definition.Key, region.Value);
            RefreshRegions();
        }
    }

    private void RefreshPoints()
    {
        _pointList.Items.Clear();
        foreach (var definition in ProfileKeys.PointDefinitions)
        {
            var value = _profile.GetPoint(definition.Key);
            var item = new ListViewItem(definition.Label)
            {
                Tag = definition
            };
            item.SubItems.Add($"{value.X}, {value.Y}");
            _pointList.Items.Add(item);
        }
    }

    private void RefreshRegions()
    {
        _regionList.Items.Clear();
        foreach (var definition in ProfileKeys.RegionDefinitions)
        {
            var value = _profile.GetRegion(definition.Key);
            var item = new ListViewItem(definition.Label)
            {
                Tag = definition
            };
            item.SubItems.Add($"{value.X}, {value.Y}, {value.Width}, {value.Height}");
            _regionList.Items.Add(item);
        }
    }

    private void SaveTimings()
    {
        foreach (var item in _timingInputs)
        {
            _profile.SetTiming(item.Key, (double)item.Value.Value);
        }
    }

    private void ResetDefaults()
    {
        var defaults = RestaurantProfile.Default();
        _profile.Points = defaults.Points.ToDictionary(item => item.Key, item => item.Value.Clone());
        _profile.Regions = defaults.Regions.ToDictionary(item => item.Key, item => item.Value.Clone());
        _profile.Timings = defaults.Timings.ToDictionary(item => item.Key, item => item.Value);
        RefreshPoints();
        RefreshRegions();

        foreach (var definition in ProfileKeys.TimingDefinitions)
        {
            if (_timingInputs.TryGetValue(definition.Key, out var input))
            {
                input.Value = (decimal)_profile.GetTiming(definition.Key, definition.DefaultValue);
            }
        }
    }
}
