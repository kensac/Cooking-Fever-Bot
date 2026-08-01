"""Asset manager dialog: capture, preview, and test template images.

The top "Bot Templates" panel lists every image the bot actually needs by a
friendly name, shows whether it exists (with a thumbnail), and lets you replace
each one straight from a live screenshot - no manual file naming or copying. The
lower list is the raw folder view for any extra/manual assets.
"""
from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox
from typing import Dict, Optional

from .. import automation, paths, template
from ..profiles import RestaurantProfile
from . import overlay, prompt

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}


@dataclass(frozen=True)
class TemplateSpec:
    """A template image the bot requires, with a human-facing label."""

    file_name: str
    label: str
    hint: str


# Single source of truth for the images the bot loads. Keep filenames in sync
# with bot.py (_ORDER_TEMPLATES, restart-1/2.png, coins.png).
REQUIRED_TEMPLATES = [
    TemplateSpec("burger.png", "Burger order", "The plain burger icon in an order bubble."),
    TemplateSpec("burger-lettuce.png", "Burger + lettuce order",
                 "Burger-with-lettuce icon. Crop the same area as the plain burger. Optional."),
    TemplateSpec("burger-tomato.png", "Burger + tomato order",
                 "Burger-with-tomato icon. Crop the same area as the plain burger. Optional."),
    TemplateSpec("burger-lettuce-tomato.png", "Burger + lettuce & tomato order",
                 "Burger-with-both icon. Crop the same area as the plain burger. Optional."),
    TemplateSpec("soda.png", "Soda order", "The soda icon in an order bubble."),
    TemplateSpec("fries.png", "Fries order", "The fries icon in an order bubble. Optional."),
    TemplateSpec("hotdog.png", "Hotdog order", "The plain hotdog icon in an order bubble."),
    TemplateSpec("hotdog-ketchup.png", "Hotdog + ketchup order",
                 "The hotdog-with-ketchup icon. Crop the same area as the plain hotdog."),
    TemplateSpec("coins.png", "Coins / tip", "The coins that appear after a delivery."),
    TemplateSpec("restart-1.png", "Restart button 1", "The stage restart / continue button."),
    TemplateSpec("restart-2.png", "Restart button 2", "The alternate restart / continue button."),
]

_THUMB_HEIGHT = 44


class AssetManagerDialog:
    def __init__(self, parent: tk.Misc, profile: RestaurantProfile) -> None:
        self._profile = profile
        self._window = tk.Toplevel(parent)
        self._window.title(f"Assets - {profile.name}")
        self._window.geometry("860x680")
        self._window.transient(parent)
        self._window.grab_set()

        toolbar = tk.Frame(self._window)
        toolbar.pack(fill="x", padx=10, pady=8)
        tk.Button(toolbar, text="Open Folder", command=self._open_folder).pack(side="left", padx=2)
        tk.Button(toolbar, text="Refresh", command=self._refresh).pack(side="left", padx=2)
        tk.Label(toolbar, text="Confidence").pack(side="left", padx=(12, 2))
        self._confidence = tk.DoubleVar(value=0.8)
        tk.Spinbox(toolbar, from_=0.1, to=1.0, increment=0.05, width=6,
                   textvariable=self._confidence).pack(side="left")

        # --- Bot templates panel ------------------------------------------------
        required = tk.LabelFrame(self._window, text="Bot Templates (replace from a live screenshot)")
        required.pack(fill="x", padx=10, pady=(4, 6))
        self._rows: Dict[str, Dict[str, object]] = {}
        self._thumbs: Dict[str, tk.PhotoImage] = {}
        for i, spec in enumerate(REQUIRED_TEMPLATES):
            self._build_required_row(required, spec, i)
        required.grid_columnconfigure(1, weight=1)

        # --- Raw folder view ----------------------------------------------------
        lower = tk.LabelFrame(self._window, text="All assets in folder")
        lower.pack(fill="both", expand=True, padx=10, pady=4)
        lower_toolbar = tk.Frame(lower)
        lower_toolbar.pack(fill="x", padx=6, pady=4)
        tk.Button(lower_toolbar, text="Capture New...", command=self._capture_named).pack(side="left", padx=2)
        tk.Button(lower_toolbar, text="Test Selected", command=self._test_selected).pack(side="left", padx=2)

        body = tk.Frame(lower)
        body.pack(fill="both", expand=True, padx=6, pady=4)
        self._listbox = tk.Listbox(body, width=32)
        self._listbox.pack(side="left", fill="y")
        self._listbox.bind("<<ListboxSelect>>", lambda _e: self._display_selected())

        self._preview = tk.Label(body, bg="white", anchor="center")
        self._preview.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self._preview_image = None  # keep a reference so tk does not GC it

        self._status = tk.Label(self._window, anchor="w")
        self._status.pack(fill="x", padx=10, pady=6)

        self._refresh()

    def show(self) -> None:
        self._window.wait_window()

    @property
    def _assets_dir(self) -> Path:
        if self._profile.assets_directory.strip():
            return Path(self._profile.assets_directory).resolve()
        return paths.assets_directory()

    # -- Bot templates panel ---------------------------------------------------

    def _build_required_row(self, parent: tk.Misc, spec: TemplateSpec, row: int) -> None:
        thumb = tk.Label(parent, bg="white", width=8, anchor="center")
        thumb.grid(row=row, column=0, padx=(8, 6), pady=3, sticky="w")

        name = tk.Label(parent, text=spec.label, anchor="w", font=("Helvetica", 12, "bold"))
        name.grid(row=row, column=1, sticky="w")

        status = tk.Label(parent, text="", anchor="w", fg="gray")
        status.grid(row=row, column=2, padx=8, sticky="w")

        tk.Button(parent, text="Replace with Screenshot",
                  command=lambda s=spec: self._replace(s)).grid(row=row, column=3, padx=2, pady=2)
        tk.Button(parent, text="Test",
                  command=lambda s=spec: self._test_file(s.file_name)).grid(row=row, column=4, padx=(2, 8))

        self._rows[spec.file_name] = {"thumb": thumb, "status": status, "spec": spec}

    def _refresh_required(self) -> None:
        for file_name, widgets in self._rows.items():
            path = self._assets_dir / file_name
            status: tk.Label = widgets["status"]  # type: ignore[assignment]
            thumb: tk.Label = widgets["thumb"]  # type: ignore[assignment]
            if path.is_file():
                image = self._make_thumb(path)
                if image is not None:
                    self._thumbs[file_name] = image
                    thumb.config(image=image, text="")
                else:
                    thumb.config(image="", text="?")
                status.config(text="✓ set", fg="#1a7f37")
            else:
                self._thumbs.pop(file_name, None)
                thumb.config(image="", text="—")
                status.config(text="missing", fg="#b00020")

    def _make_thumb(self, path: Path) -> Optional[tk.PhotoImage]:
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return None
        factor = max(1, round(image.height() / _THUMB_HEIGHT))
        if factor > 1:
            image = image.subsample(factor, factor)
        return image

    def _replace(self, spec: TemplateSpec) -> None:
        region = self._capture_region(spec.label)
        if region is None:
            return
        directory = self._assets_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / spec.file_name
        automation.grab_image(region).save(path, format="PNG")
        self._refresh()
        self._status.config(text=f"Saved {spec.label} → {path.name}")

    # -- Shared capture / raw folder view --------------------------------------

    def _capture_region(self, label: str):
        """Hide the dialog, run the fullscreen capture overlay, restore it."""
        self._window.grab_release()
        self._window.withdraw()
        try:
            region = overlay.capture_region(label, self._window.master)
        finally:
            self._window.deiconify()
            self._window.grab_set()
        return region

    def _capture_named(self) -> None:
        name = prompt.ask(self._window, "Capture Template", "Template file name", "new-template.png")
        if not name:
            return
        stem = Path(name).stem
        if not stem:
            return
        region = self._capture_region(stem)
        if region is None:
            return
        directory = self._assets_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{stem}.png"
        automation.grab_image(region).save(path, format="PNG")
        self._refresh()
        self._status.config(text=f"Saved template: {path}")

    def _selected_path(self) -> Optional[Path]:
        selection = self._listbox.curselection()
        if not selection:
            return None
        return self._assets_dir / self._listbox.get(selection[0])

    def _open_folder(self) -> None:
        directory = self._assets_dir
        directory.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.run(["open", str(directory)], check=False)
        elif sys.platform.startswith("win"):
            subprocess.run(["explorer", str(directory)], check=False)
        else:
            subprocess.run(["xdg-open", str(directory)], check=False)

    def _refresh(self) -> None:
        directory = self._assets_dir
        directory.mkdir(parents=True, exist_ok=True)
        self._listbox.delete(0, "end")
        names = sorted(
            p.name for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
        )
        for name in names:
            self._listbox.insert("end", name)
        self._refresh_required()
        missing = sum(1 for f in self._rows if not (directory / f).is_file())
        suffix = f" - {missing} bot template(s) missing" if missing else " - all bot templates set"
        self._status.config(text=f"{len(names)} image asset(s) in {directory}{suffix}")

    def _test_selected(self) -> None:
        path = self._selected_path()
        if path is not None:
            self._test_file(path.name)

    def _test_file(self, file_name: str) -> None:
        path = self._assets_dir / file_name
        if not path.is_file():
            self._status.config(text=f"{file_name} is not set yet - capture it first.")
            return
        try:
            match = template.locate(path, None, float(self._confidence.get()))
        except RuntimeError as exc:
            messagebox.showerror("Asset Manager", str(exc), parent=self._window)
            return
        if match is None:
            self._status.config(text=f"No match found on screen for {path.name}")
        else:
            x, y, w, h = match.bounds
            self._status.config(
                text=f"Match: {path.name} at {x}, {y}, {w}, {h} with {match.confidence:.1%}"
            )

    def _display_selected(self) -> None:
        path = self._selected_path()
        if path is None or not path.is_file():
            self._preview.config(image="", text="")
            self._preview_image = None
            return
        try:
            self._preview_image = tk.PhotoImage(file=str(path))
            self._preview.config(image=self._preview_image, text="")
        except tk.TclError:
            # tk.PhotoImage only reads PNG/GIF; show a path fallback otherwise.
            self._preview.config(image="", text=str(path))
            self._preview_image = None
        self._status.config(text=str(path))
