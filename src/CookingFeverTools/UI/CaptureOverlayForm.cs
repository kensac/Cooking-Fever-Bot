using System.Drawing;
using System.Windows.Forms;

namespace CookingFeverTools;

internal enum CaptureOverlayMode
{
    Point,
    Region
}

internal sealed class CaptureOverlayForm : Form
{
    private readonly CaptureOverlayMode _mode;
    private readonly string _prompt;
    private Point _start;
    private Rectangle _selection;
    private bool _dragging;

    private CaptureOverlayForm(CaptureOverlayMode mode, string prompt)
    {
        _mode = mode;
        _prompt = prompt;
        FormBorderStyle = FormBorderStyle.None;
        Bounds = SystemInformation.VirtualScreen;
        StartPosition = FormStartPosition.Manual;
        TopMost = true;
        DoubleBuffered = true;
        KeyPreview = true;
        BackColor = Color.Black;
        Opacity = 0.28;
        Cursor = Cursors.Cross;
        ShowInTaskbar = false;
    }

    public Point? CapturedPoint { get; private set; }
    public Rectangle? CapturedRegion { get; private set; }

    public static Point? CapturePoint(IWin32Window owner, string label)
    {
        using var overlay = new CaptureOverlayForm(CaptureOverlayMode.Point, $"Click {label}. Press Esc to cancel.");
        return overlay.ShowDialog(owner) == DialogResult.OK ? overlay.CapturedPoint : null;
    }

    public static Rectangle? CaptureRegion(IWin32Window owner, string label)
    {
        using var overlay = new CaptureOverlayForm(CaptureOverlayMode.Region, $"Drag around {label}. Press Esc to cancel.");
        return overlay.ShowDialog(owner) == DialogResult.OK ? overlay.CapturedRegion : null;
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Escape)
        {
            DialogResult = DialogResult.Cancel;
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

        var point = PointToScreen(e.Location);
        if (_mode == CaptureOverlayMode.Point)
        {
            CapturedPoint = point;
            DialogResult = DialogResult.OK;
            Close();
            return;
        }

        _start = point;
        _selection = Rectangle.Empty;
        _dragging = true;
        Invalidate();
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        if (!_dragging || _mode != CaptureOverlayMode.Region)
        {
            return;
        }

        _selection = RectangleFromPoints(_start, PointToScreen(e.Location));
        Invalidate();
    }

    protected override void OnMouseUp(MouseEventArgs e)
    {
        if (!_dragging || _mode != CaptureOverlayMode.Region || e.Button != MouseButtons.Left)
        {
            return;
        }

        _dragging = false;
        _selection = RectangleFromPoints(_start, PointToScreen(e.Location));
        if (_selection.Width <= 2 || _selection.Height <= 2)
        {
            Invalidate();
            return;
        }

        CapturedRegion = _selection;
        DialogResult = DialogResult.OK;
        Close();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;

        using var promptFont = new Font("Segoe UI", 18, FontStyle.Bold, GraphicsUnit.Point);
        using var promptBrush = new SolidBrush(Color.White);
        using var shadowBrush = new SolidBrush(Color.FromArgb(180, Color.Black));
        var textPoint = new PointF(24, 24);
        e.Graphics.DrawString(_prompt, promptFont, shadowBrush, textPoint.X + 2, textPoint.Y + 2);
        e.Graphics.DrawString(_prompt, promptFont, promptBrush, textPoint);

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
