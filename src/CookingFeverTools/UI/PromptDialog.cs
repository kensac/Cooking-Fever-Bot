using System.Drawing;
using System.Windows.Forms;

namespace CookingFeverTools;

internal sealed class PromptDialog : Form
{
    private readonly TextBox _input = new() { Dock = DockStyle.Fill };

    private PromptDialog(string title, string label, string defaultValue)
    {
        Text = title;
        Width = 440;
        Height = 150;
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MinimizeBox = false;
        MaximizeBox = false;

        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(12),
            RowCount = 3,
            ColumnCount = 1
        };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 26));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        Controls.Add(layout);

        layout.Controls.Add(new Label { Text = label, Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft }, 0, 0);
        _input.Text = defaultValue;
        layout.Controls.Add(_input, 0, 1);

        var buttons = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft
        };
        var ok = new Button { Text = "OK", DialogResult = DialogResult.OK, Width = 90 };
        var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel, Width = 90 };
        buttons.Controls.Add(cancel);
        buttons.Controls.Add(ok);
        layout.Controls.Add(buttons, 0, 2);

        AcceptButton = ok;
        CancelButton = cancel;
        Shown += (_, _) =>
        {
            _input.SelectAll();
            _input.Focus();
        };
    }

    public string Value => _input.Text.Trim();

    public static string? Show(IWin32Window owner, string title, string label, string defaultValue = "")
    {
        using var dialog = new PromptDialog(title, label, defaultValue);
        return dialog.ShowDialog(owner) == DialogResult.OK && dialog.Value.Length > 0
            ? dialog.Value
            : null;
    }
}
