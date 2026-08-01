"""Fullscreen capture overlay for calibrating points and regions.

A dimmed, always-on-top window covering the screen. In point mode a single
click returns the screen coordinate; in region mode a drag returns the selected
rectangle. Coordinates are absolute screen pixels taken from the event's *_root
fields.

macOS notes:
- We use a borderless (overrideredirect) window sized to the screen rather than
  Tk's ``-fullscreen`` attribute, because the latter animates into a separate
  Space (a whole new desktop), which is jarring.
- Borderless Tk windows often never receive keyboard focus on macOS, so Escape
  bound through Tk can silently do nothing. The reliable cancel is a right-click;
  Escape is kept as a bonus for platforms where focus works. (We deliberately do
  NOT use a pynput keyboard hook here: pynput's macOS key translation runs on a
  background thread and crashes the process with SIGTRAP.)

``run_region_tool`` is the standalone region/snap utility: it stays open and
reports (or screenshots) each dragged region until cancelled.
"""
from __future__ import annotations

import time
import tkinter as tk
from typing import Optional

from .. import automation, paths
from ..geometry import Point, Region, region_from_points

_POINT = "point"
_REGION = "region"

_CANCEL_HINT = "Right-click to cancel (or press Esc)."


def _cover_screen(window: tk.Misc, alpha: float) -> None:
    """Make ``window`` a borderless, topmost overlay covering the whole screen."""
    sw = window.winfo_screenwidth()
    sh = window.winfo_screenheight()
    window.overrideredirect(True)
    window.geometry(f"{sw}x{sh}+0+0")
    window.attributes("-topmost", True)
    try:
        window.attributes("-alpha", alpha)
    except tk.TclError:
        pass
    window.configure(bg="black")
    window.update_idletasks()
    window.lift()
    window.after(10, window.focus_force)


class _Overlay:
    def __init__(self, parent: Optional[tk.Misc], mode: str, prompt: str) -> None:
        self._mode = mode
        self._owns_root = parent is None
        self._window = tk.Tk() if parent is None else tk.Toplevel(parent)
        self._window.title("Capture")
        _cover_screen(self._window, alpha=0.28)
        self._window.config(cursor="cross")

        self._canvas = tk.Canvas(self._window, highlightthickness=0, bg="black", cursor="cross")
        self._canvas.pack(fill="both", expand=True)
        self._canvas.create_text(
            28, 28, anchor="nw", text=prompt, fill="white",
            font=("Helvetica", 18, "bold"),
        )

        self._start: Optional[Point] = None
        self._rect_id: Optional[int] = None

        self.point: Optional[Point] = None
        self.region: Optional[Region] = None

        for widget in (self._window, self._canvas):
            widget.bind("<Escape>", self._on_cancel)
            widget.bind("<Button-2>", self._on_cancel)
            widget.bind("<Button-3>", self._on_cancel)
        self._canvas.bind("<Button-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

        self._window.grab_set()

    def _origin(self) -> Point:
        return (self._window.winfo_rootx(), self._window.winfo_rooty())

    def _on_cancel(self, _event=None) -> str:
        self.point = None
        self.region = None
        self._close()
        return "break"

    def _on_press(self, event) -> None:
        if self._mode == _POINT:
            self.point = (event.x_root, event.y_root)
            self._close()
            return
        self._start = (event.x_root, event.y_root)
        if self._rect_id is not None:
            self._canvas.delete(self._rect_id)
        self._rect_id = None

    def _on_drag(self, event) -> None:
        if self._mode != _REGION or self._start is None:
            return
        ox, oy = self._origin()
        x0, y0 = self._start[0] - ox, self._start[1] - oy
        x1, y1 = event.x_root - ox, event.y_root - oy
        if self._rect_id is None:
            self._rect_id = self._canvas.create_rectangle(
                x0, y0, x1, y1, outline="white", width=2, fill="#1e90ff"
            )
        else:
            self._canvas.coords(self._rect_id, x0, y0, x1, y1)

    def _on_release(self, event) -> None:
        if self._mode != _REGION or self._start is None:
            return
        region = region_from_points(self._start, (event.x_root, event.y_root))
        if region[2] <= 2 or region[3] <= 2:
            return
        self.region = region
        self._close()

    def _close(self) -> None:
        try:
            self._window.grab_release()
        except tk.TclError:
            pass
        if self._owns_root:
            self._window.quit()
        self._window.destroy()

    def run(self) -> None:
        if self._owns_root:
            self._window.mainloop()
        else:
            self._window.wait_window()


def capture_point(label: str, parent: Optional[tk.Misc] = None) -> Optional[Point]:
    overlay = _Overlay(parent, _POINT, f"Click {label}. {_CANCEL_HINT}")
    overlay.run()
    return overlay.point


def capture_region(label: str, parent: Optional[tk.Misc] = None) -> Optional[Region]:
    overlay = _Overlay(parent, _REGION, f"Drag around {label}. {_CANCEL_HINT}")
    overlay.run()
    return overlay.region


def run_region_tool(capture_screenshots: bool, parent: Optional[tk.Misc] = None) -> None:
    """Region / snap tool. Repeats until cancelled.

    With no parent it owns a Tk root and its own mainloop; with a parent it runs
    as a modal Toplevel so it can be launched from the dashboard.
    """
    output_directory = paths.screenshots_directory()
    action = "save a screenshot" if capture_screenshots else "print coordinates"
    prompt = f"Drag a region to {action}. {_CANCEL_HINT}"
    print(prompt)

    owns_root = parent is None
    root = tk.Tk() if owns_root else tk.Toplevel(parent)
    root.title("Snapshot Region Tool" if capture_screenshots else "Region Selection Tool")
    _cover_screen(root, alpha=0.22)

    canvas = tk.Canvas(root, highlightthickness=0, bg="black", cursor="cross")
    canvas.pack(fill="both", expand=True)
    canvas.create_text(28, 28, anchor="nw", text=prompt, fill="white",
                       font=("Helvetica", 16, "bold"))

    state = {"start": None, "rect": None}

    def origin():
        return root.winfo_rootx(), root.winfo_rooty()

    def close(_event=None) -> str:
        try:
            root.grab_release()
        except tk.TclError:
            pass
        if owns_root:
            root.quit()
        root.destroy()
        return "break"

    def on_press(event):
        state["start"] = (event.x_root, event.y_root)
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = None

    def on_drag(event):
        if state["start"] is None:
            return
        ox, oy = origin()
        x0, y0 = state["start"][0] - ox, state["start"][1] - oy
        x1, y1 = event.x_root - ox, event.y_root - oy
        if state["rect"] is None:
            state["rect"] = canvas.create_rectangle(
                x0, y0, x1, y1, outline="white", width=2, fill="#1e90ff"
            )
        else:
            canvas.coords(state["rect"], x0, y0, x1, y1)

    def on_release(event):
        if state["start"] is None:
            return
        region = region_from_points(state["start"], (event.x_root, event.y_root))
        state["start"] = None
        if region[2] <= 2 or region[3] <= 2:
            print("No drag movement detected; region ignored.")
            return
        print(f"Region defined: ({region[0]}, {region[1]}, {region[2]}, {region[3]})")
        if capture_screenshots:
            # Hide the dim overlay for the grab, then restore it.
            root.attributes("-alpha", 0.0)
            root.update()
            time.sleep(0.15)
            path = automation.save_region(region, output_directory, "screenshot_region")
            print(f"Captured and saved: {path}")
            root.attributes("-alpha", 0.22)
            root.lift()

    canvas.bind("<Button-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    for widget in (root, canvas):
        widget.bind("<Escape>", close)
        widget.bind("<Button-2>", close)
        widget.bind("<Button-3>", close)

    root.grab_set()
    if owns_root:
        root.mainloop()
    else:
        root.wait_window()
