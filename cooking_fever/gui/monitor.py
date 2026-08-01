"""Action monitor: log global mouse/keyboard events with screenshot snippets.

Ports the C# ActionMonitorForm. Uses pynput for cross-platform global hooks
(the C# version used Windows low-level hooks). Hook callbacks run on listener
threads, so events are pushed onto a queue and drained on the tk main thread.
"""
from __future__ import annotations

import queue
import sys
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import List, Optional

from .. import automation, paths
from ..geometry import centered_region


@dataclass
class _ActionRecord:
    timestamp: datetime
    action_type: str
    description: str
    screenshot_path: Optional[str]
    tag: str = ""

    def label(self) -> str:
        stamp = self.timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        return f"{stamp} - {self.action_type}: {self.description} (Tag: {self.tag})"


class ActionMonitor:
    def __init__(self, master: tk.Misc) -> None:
        self._master = master
        self._actions: List[_ActionRecord] = []
        self._queue: "queue.Queue[_ActionRecord]" = queue.Queue()
        self._screenshot_dir = paths.screenshots_directory()
        self._mouse_listener = None
        self._keyboard_listener = None
        self._dragging = False
        self._last_drag = datetime.min
        self._periodic_job = None
        self._preview_image = None

        toolbar = tk.Frame(master)
        toolbar.pack(fill="x", padx=8, pady=6)
        self._start_button = tk.Button(toolbar, text="Start Monitoring", command=self._start)
        self._start_button.pack(side="left", padx=2)
        self._stop_button = tk.Button(
            toolbar, text="Stop Monitoring", command=self._stop, state="disabled"
        )
        self._stop_button.pack(side="left", padx=2)

        body = tk.Frame(master)
        body.pack(fill="both", expand=True, padx=8, pady=4)

        left = tk.Frame(body)
        left.pack(side="left", fill="y")
        self._listbox = tk.Listbox(left, width=54)
        self._listbox.pack(fill="both", expand=True)
        self._listbox.bind("<<ListboxSelect>>", lambda _e: self._display_selected())

        right = tk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self._preview = tk.Label(right, bg="white")
        self._preview.pack(fill="both", expand=True)
        tag_row = tk.Frame(right)
        tag_row.pack(fill="x", pady=(6, 0))
        self._tag_var = tk.StringVar()
        tk.Entry(tag_row, textvariable=self._tag_var).pack(side="left", fill="x", expand=True)
        tk.Button(tag_row, text="Save Tag", command=self._save_tag).pack(side="left", padx=4)

        master.bind("<Destroy>", lambda _e: self._stop())
        self._poll_queue()

    # --- monitoring ---------------------------------------------------------

    def _start(self) -> None:
        try:
            from pynput import keyboard, mouse
        except ImportError:
            messagebox.showerror(
                "Action Monitor",
                "pynput is required for monitoring.\nInstall with: pip install -r requirements.txt",
                parent=self._master,
            )
            return

        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._start_button.config(state="disabled")
        self._stop_button.config(state="normal")

        self._mouse_listener = mouse.Listener(on_click=self._on_click, on_move=self._on_move)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

        # pynput's macOS keyboard backend translates keys off the main thread and
        # crashes the process (SIGTRAP), so only hook the keyboard off macOS.
        if sys.platform != "darwin":
            self._keyboard_listener = keyboard.Listener(on_press=self._on_press)
            self._keyboard_listener.daemon = True
            self._keyboard_listener.start()
        else:
            self._queue.put(_ActionRecord(datetime.now(), "info",
                            "Keyboard capture disabled on macOS (mouse only).", None))

        self._periodic_job = self._master.after(5000, self._capture_fullscreen)

    def _stop(self) -> None:
        self._start_button.config(state="normal")
        self._stop_button.config(state="disabled")
        if self._periodic_job is not None:
            try:
                self._master.after_cancel(self._periodic_job)
            except tk.TclError:
                pass
            self._periodic_job = None
        for listener in (self._mouse_listener, self._keyboard_listener):
            if listener is not None:
                listener.stop()
        self._mouse_listener = None
        self._keyboard_listener = None

    # --- hook callbacks (listener threads) ----------------------------------

    def _on_click(self, x, y, button, pressed) -> None:
        point = (int(x), int(y))
        if pressed:
            self._dragging = True
            self._enqueue("mouse_click_down", f"Mouse pressed at ({point[0]}, {point[1]})", point)
        else:
            self._dragging = False
            self._enqueue("mouse_click_up", f"Mouse released at ({point[0]}, {point[1]})", point)

    def _on_move(self, x, y) -> None:
        if not self._dragging:
            return
        now = datetime.now()
        if (now - self._last_drag).total_seconds() < 0.25:
            return
        self._last_drag = now
        self._enqueue("mouse_drag", f"Dragging mouse through ({int(x)}, {int(y)})", None)

    def _on_press(self, key) -> None:
        try:
            point = automation.position()
        except RuntimeError:
            point = None
        self._enqueue("key_press", f"Key pressed: {key}", point)

    def _enqueue(self, action_type: str, description: str, point) -> None:
        path = None
        if point is not None:
            try:
                region = centered_region(point, 100)
                path = str(automation.save_region(region, self._screenshot_dir, "screenshot_region"))
            except RuntimeError:
                path = None
        self._queue.put(_ActionRecord(datetime.now(), action_type, description, path))

    # --- tk main thread -----------------------------------------------------

    def _capture_fullscreen(self) -> None:
        try:
            path = self._screenshot_dir / f"fullscreen_{datetime.now():%Y-%m-%d_%H-%M-%S_%f}.png"
            automation.grab_image(automation.virtual_screen()).save(path, format="PNG")
            self._queue.put(
                _ActionRecord(datetime.now(), "periodic_fullscreen",
                              "Periodic full-screen capture", str(path))
            )
        except RuntimeError:
            pass
        self._periodic_job = self._master.after(5000, self._capture_fullscreen)

    def _poll_queue(self) -> None:
        while not self._queue.empty():
            record = self._queue.get()
            self._actions.append(record)
            self._listbox.insert("end", record.label())
        self._master.after(120, self._poll_queue)

    def _display_selected(self) -> None:
        selection = self._listbox.curselection()
        if not selection:
            return
        record = self._actions[selection[0]]
        if not record.screenshot_path or not Path(record.screenshot_path).is_file():
            self._preview.config(image="", text="")
            self._preview_image = None
            return
        try:
            self._preview_image = tk.PhotoImage(file=record.screenshot_path)
            self._preview.config(image=self._preview_image, text="")
        except tk.TclError:
            self._preview.config(image="", text=record.screenshot_path)
            self._preview_image = None

    def _save_tag(self) -> None:
        selection = self._listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Select an action first.", parent=self._master)
            return
        tag = self._tag_var.get().strip()
        if not tag:
            messagebox.showwarning("No Tag", "Enter a tag before saving.", parent=self._master)
            return
        index = selection[0]
        self._actions[index].tag = tag
        self._listbox.delete(index)
        self._listbox.insert(index, self._actions[index].label())
        self._tag_var.set("")


def open_window(parent: tk.Misc) -> None:
    window = tk.Toplevel(parent)
    window.title("Cooking Fever Action Monitor")
    window.geometry("1100x640")
    ActionMonitor(window)


def run() -> None:
    root = tk.Tk()
    root.title("Cooking Fever Action Monitor")
    root.geometry("1100x640")
    ActionMonitor(root)
    root.mainloop()
