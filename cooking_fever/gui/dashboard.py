"""The main dashboard window.

Ports the C# DashboardForm: profile management, bot start/stop, calibration,
asset management, utilities, and a live log. The bot runs as a child process
(``main.py bot ...``) so it can be killed cleanly, mirroring the original
BotProcessController design.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import List, Optional

from .. import paths, profiles, settings
from ..profiles import RestaurantProfile
from . import assets as assets_dialog
from . import calibration, monitor, overlay, prompt, todo

_MAIN_SCRIPT = paths.APP_DIRECTORY / "main.py"


class BotProcess:
    """Runs the bot as a child process and streams its output to a queue."""

    def __init__(self, log_queue: "queue.Queue[str]") -> None:
        self._log_queue = log_queue
        self._process: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, profile_path: str, assets_directory: str, confidence: float, dry_run: bool) -> None:
        if self.running:
            raise RuntimeError("The bot is already running.")

        # -u so the child's stdout is unbuffered and its logs (including the
        # per-detection scores) stream to the dashboard live instead of only
        # appearing when the process exits.
        args: List[str] = [
            sys.executable, "-u", str(_MAIN_SCRIPT), "bot",
            "--profile", profile_path,
            "--assets", assets_directory,
            "--confidence", f"{confidence:.2f}",
            "--delay", "0",
            "--start",
        ]
        if dry_run:
            args.append("--dry-run")

        self._process = subprocess.Popen(
            args,
            cwd=str(paths.APP_DIRECTORY),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=dict(os.environ, PYTHONUNBUFFERED="1"),
        )
        self._reader = threading.Thread(target=self._pump_output, daemon=True)
        self._reader.start()

    def _pump_output(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            self._log_queue.put(line.rstrip("\n"))
        code = self._process.wait()
        self._log_queue.put(f"__STATE__Stopped with exit code {code}")

    def stop(self) -> None:
        if self._process is not None and self.running:
            self._process.terminate()


class Dashboard:
    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._bot = BotProcess(self._log_queue)
        self._profiles: List[RestaurantProfile] = []
        self._tracking = False
        self._tracker_job = None
        self._settings = settings.load()
        self._loaded = False

        profiles.paths.ensure_directories()
        self._build()
        self._load_profiles(self._settings.get("last_profile_path") or None)
        self._loaded = True
        self._poll_log()

    # --- layout -------------------------------------------------------------

    def _build(self) -> None:
        self._root.title("Cooking Fever Tools")
        self._root.geometry("1180x760")

        tk.Label(self._root, text="Cooking Fever Tools", font=("Helvetica", 20, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(12, 0))
        self._summary = tk.Label(self._root, text="No profile selected", anchor="w")
        self._summary.pack(fill="x", padx=16)

        body = tk.Frame(self._root)
        body.pack(fill="both", expand=True, padx=16, pady=8)

        controls = tk.Frame(body)
        controls.pack(side="left", fill="y")
        self._build_profile_group(controls)
        self._build_bot_group(controls)
        self._build_tool_group(controls)
        self._build_folder_group(controls)

        log_frame = tk.Frame(body)
        log_frame.pack(side="left", fill="both", expand=True, padx=(16, 0))
        tk.Label(log_frame, text="Bot Log", font=("Helvetica", 12, "bold"), anchor="w").pack(fill="x")
        self._log = tk.Text(log_frame, wrap="none", font=("Menlo", 10), state="disabled")
        self._log.pack(fill="both", expand=True)

        self._status = tk.Label(self._root, text="Ready", anchor="w")
        self._status.pack(fill="x", padx=16, pady=(0, 8))

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_profile_group(self, parent: tk.Misc) -> None:
        group = tk.LabelFrame(parent, text="Profile", padx=8, pady=8)
        group.pack(fill="x", pady=4)
        self._profile_var = tk.StringVar()
        self._profile_combo = ttk.Combobox(group, textvariable=self._profile_var,
                                           state="readonly", width=34)
        self._profile_combo.pack(fill="x")
        self._profile_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_summary())

        row1 = tk.Frame(group)
        row1.pack(fill="x", pady=4)
        tk.Button(row1, text="New", command=self._new_profile, width=8).pack(side="left", padx=2)
        tk.Button(row1, text="Save", command=self._save_profile, width=8).pack(side="left", padx=2)
        tk.Button(row1, text="Delete", command=self._delete_profile, width=8).pack(side="left", padx=2)

        row2 = tk.Frame(group)
        row2.pack(fill="x")
        tk.Button(row2, text="Calibrate", command=self._calibrate, width=12).pack(side="left", padx=2)
        tk.Button(row2, text="Assets", command=self._open_assets, width=12).pack(side="left", padx=2)

    def _build_bot_group(self, parent: tk.Misc) -> None:
        group = tk.LabelFrame(parent, text="Bot", padx=8, pady=8)
        group.pack(fill="x", pady=4)
        settings = tk.Frame(group)
        settings.pack(fill="x")
        tk.Label(settings, text="Confidence").pack(side="left")
        self._confidence = tk.DoubleVar(value=float(self._settings.get("confidence", 0.8)))
        tk.Spinbox(settings, from_=0.1, to=1.0, increment=0.05, width=6,
                   textvariable=self._confidence).pack(side="left", padx=6)
        self._dry_run = tk.BooleanVar(value=bool(self._settings.get("dry_run", False)))
        tk.Checkbutton(settings, text="Dry Run", variable=self._dry_run).pack(side="left")

        self._confidence.trace_add("write", lambda *_: self._save_settings())
        self._dry_run.trace_add("write", lambda *_: self._save_settings())

        actions = tk.Frame(group)
        actions.pack(fill="x", pady=6)
        self._start_button = tk.Button(actions, text="Start Bot", command=self._start_bot, width=12)
        self._start_button.pack(side="left", padx=2)
        self._stop_button = tk.Button(actions, text="Stop Bot", command=self._stop_bot,
                                      width=12, state="disabled")
        self._stop_button.pack(side="left", padx=2)

        tk.Label(group, wraplength=320, justify="left",
                 text="Dashboard start runs immediately. Keyboard controls still work: "
                      "p pauses/resumes, gg stops.").pack(fill="x")

    def _build_tool_group(self, parent: tk.Misc) -> None:
        group = tk.LabelFrame(parent, text="Utilities", padx=8, pady=8)
        group.pack(fill="x", pady=4)
        tk.Button(group, text="Action Monitor",
                  command=lambda: monitor.open_window(self._root)).pack(fill="x", pady=1)
        tk.Button(group, text="Todo Utility",
                  command=lambda: todo.open_window(self._root)).pack(fill="x", pady=1)
        tk.Button(group, text="Select Region",
                  command=lambda: self._open_region_tool(False)).pack(fill="x", pady=1)
        tk.Button(group, text="Snapshot Region",
                  command=lambda: self._open_region_tool(True)).pack(fill="x", pady=1)
        self._tracker_button = tk.Button(group, text="Track Mouse", command=self._toggle_tracker)
        self._tracker_button.pack(fill="x", pady=1)
        self._mouse_label = tk.Label(group, text="Mouse: not tracking", anchor="w")
        self._mouse_label.pack(fill="x")

    def _build_folder_group(self, parent: tk.Misc) -> None:
        group = tk.LabelFrame(parent, text="Folders", padx=8, pady=8)
        group.pack(fill="x", pady=4)
        tk.Button(group, text="Profiles",
                  command=lambda: self._open_folder(paths.profiles_directory())).pack(fill="x", pady=1)
        tk.Button(group, text="Assets",
                  command=lambda: self._open_folder(paths.assets_directory())).pack(fill="x", pady=1)
        tk.Button(group, text="Screenshots",
                  command=lambda: self._open_folder(paths.screenshots_directory())).pack(fill="x", pady=1)
        tk.Button(group, text="Logs",
                  command=lambda: self._open_folder(paths.logs_directory())).pack(fill="x", pady=1)
        tk.Button(group, text="Clear Log", command=self._clear_log).pack(fill="x", pady=1)

    # --- profiles -----------------------------------------------------------

    @property
    def _selected_profile(self) -> Optional[RestaurantProfile]:
        index = self._profile_combo.current()
        if index < 0 or index >= len(self._profiles):
            return None
        return self._profiles[index]

    def _load_profiles(self, select_path: Optional[str] = None) -> None:
        self._profiles = profiles.load_all()
        self._profile_combo["values"] = [p.name for p in self._profiles]
        if not self._profiles:
            return
        index = 0
        if select_path:
            for i, profile in enumerate(self._profiles):
                if profile.file_path == select_path:
                    index = i
                    break
        self._profile_combo.current(index)
        self._update_summary()

    def _new_profile(self) -> None:
        name = prompt.ask(self._root, "New Profile", "Profile name", "New Restaurant")
        if name is None:
            return
        profile = profiles.create(name)
        self._load_profiles(profile.file_path)
        self._append_log(f"Created profile: {profile.name}")

    def _save_profile(self) -> None:
        profile = self._selected_profile
        if profile is None:
            return
        profiles.save(profile)
        self._update_summary()
        self._append_log(f"Saved profile: {profile.name}")

    def _delete_profile(self) -> None:
        profile = self._selected_profile
        if profile is None:
            return
        if not messagebox.askyesno("Delete Profile", f"Delete profile '{profile.name}'?",
                                   parent=self._root):
            return
        profiles.delete(profile)
        profiles.ensure_default_profile()
        self._load_profiles()

    def _calibrate(self) -> None:
        profile = self._selected_profile
        if profile is None:
            return
        updated = calibration.CalibrationDialog(self._root, profile).show()
        if updated is None:
            return
        updated.file_path = profile.file_path
        updated.name = profile.name
        updated.assets_directory = profile.assets_directory
        profiles.save(updated)
        self._load_profiles(updated.file_path)
        self._append_log(f"Updated calibration for: {updated.name}")

    def _open_assets(self) -> None:
        profile = self._selected_profile
        if profile is None:
            return
        assets_dialog.AssetManagerDialog(self._root, profile).show()

    # --- bot ----------------------------------------------------------------

    def _resolve_assets(self, profile: RestaurantProfile) -> str:
        if profile.assets_directory.strip():
            return str(Path(profile.assets_directory).resolve())
        return str(paths.assets_directory())

    def _start_bot(self) -> None:
        profile = self._selected_profile
        if profile is None:
            return
        profiles.save(profile)
        assets_dir = self._resolve_assets(profile)
        Path(assets_dir).mkdir(parents=True, exist_ok=True)
        self._append_log(f"Starting bot with profile: {profile.name}")
        try:
            self._bot.start(profile.file_path, assets_dir,
                            float(self._confidence.get()), self._dry_run.get())
        except (RuntimeError, OSError) as exc:
            messagebox.showerror("Cooking Fever Tools", str(exc), parent=self._root)
            return
        self._start_button.config(state="disabled")
        self._stop_button.config(state="normal")
        self._status.config(text="Running")

    def _stop_bot(self) -> None:
        self._bot.stop()
        self._status.config(text="Stopping")

    # --- utilities ----------------------------------------------------------

    def _open_region_tool(self, capture_screenshots: bool) -> None:
        self._root.withdraw()
        try:
            overlay.run_region_tool(capture_screenshots, parent=self._root)
        finally:
            self._root.deiconify()

    def _toggle_tracker(self) -> None:
        if self._tracking:
            self._tracking = False
            if self._tracker_job is not None:
                self._root.after_cancel(self._tracker_job)
                self._tracker_job = None
            self._tracker_button.config(text="Track Mouse")
            self._mouse_label.config(text="Mouse: not tracking")
            self._status.config(text="Mouse tracking stopped")
            return
        self._tracking = True
        self._tracker_button.config(text="Stop Tracking")
        self._status.config(text="Mouse tracking in dashboard")
        self._update_mouse()

    def _update_mouse(self) -> None:
        if not self._tracking:
            return
        try:
            from .. import automation

            x, y = automation.position()
            self._mouse_label.config(text=f"Mouse: X={x}, Y={y}")
        except RuntimeError as exc:
            self._mouse_label.config(text=str(exc))
            self._tracking = False
            return
        self._tracker_job = self._root.after(250, self._update_mouse)

    def _open_folder(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.run(["open", str(directory)], check=False)
        elif sys.platform.startswith("win"):
            subprocess.run(["explorer", str(directory)], check=False)
        else:
            subprocess.run(["xdg-open", str(directory)], check=False)

    # --- log ----------------------------------------------------------------

    def _poll_log(self) -> None:
        while not self._log_queue.empty():
            line = self._log_queue.get()
            if line.startswith("__STATE__"):
                self._status.config(text=line[len("__STATE__"):])
                self._start_button.config(state="normal")
                self._stop_button.config(state="disabled")
            else:
                self._append_log(line)
        self._root.after(120, self._poll_log)

    def _append_log(self, message: str) -> None:
        line = f"[{datetime.now():%H:%M:%S}] {message}\n"
        self._log.config(state="normal")
        self._log.insert("end", line)
        self._log.see("end")
        self._log.config(state="disabled")
        try:
            paths.logs_directory().mkdir(parents=True, exist_ok=True)
            with open(paths.logs_directory() / "dashboard.log", "a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass

    def _clear_log(self) -> None:
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    def _update_summary(self) -> None:
        profile = self._selected_profile
        if profile is None:
            self._summary.config(text="No profile selected")
            return
        self._summary.config(
            text=f"Profile: {profile.name} | File: {profile.file_path} | "
                 f"Assets: {self._resolve_assets(profile)}"
        )
        self._save_settings()

    def _save_settings(self) -> None:
        if not self._loaded:
            return
        profile = self._selected_profile
        try:
            confidence = float(self._confidence.get())
        except (tk.TclError, ValueError):
            confidence = 0.8
        settings.save({
            "last_profile_path": profile.file_path if profile else "",
            "confidence": confidence,
            "dry_run": bool(self._dry_run.get()),
        })

    def _on_close(self) -> None:
        self._save_settings()
        self._tracking = False
        self._bot.stop()
        self._root.destroy()


def run() -> None:
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()
