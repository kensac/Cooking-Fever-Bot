"""Calibration dialog: capture click positions, order regions, and timings."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional

from .. import profiles
from ..profiles import RestaurantProfile
from . import overlay


class CalibrationDialog:
    def __init__(self, parent: tk.Misc, profile: RestaurantProfile) -> None:
        self.result: Optional[RestaurantProfile] = None
        self._profile = profile.clone()

        self._window = tk.Toplevel(parent)
        self._window.title(f"Calibrate - {self._profile.name}")
        self._window.geometry("720x600")
        self._window.transient(parent)
        self._window.grab_set()

        tk.Label(
            self._window,
            text="Capture screen positions, order detection regions, and timing values.",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        notebook = ttk.Notebook(self._window)
        notebook.pack(fill="both", expand=True, padx=12, pady=4)

        self._point_tree = self._build_list_page(notebook, "Positions", self._capture_point)
        self._region_tree = self._build_list_page(notebook, "Regions", self._capture_region)
        self._timing_inputs: Dict[str, tk.DoubleVar] = {}
        notebook.add(self._build_timing_page(notebook), text="Timings")

        buttons = tk.Frame(self._window)
        buttons.pack(fill="x", padx=12, pady=8)
        tk.Button(buttons, text="Reset Defaults", command=self._reset_defaults).pack(side="left")
        tk.Button(buttons, text="Cancel", command=self._cancel).pack(side="right", padx=4)
        tk.Button(buttons, text="Save", command=self._save).pack(side="right")

        self._refresh_points()
        self._refresh_regions()

    def show(self) -> Optional[RestaurantProfile]:
        self._window.wait_window()
        return self.result

    # --- pages --------------------------------------------------------------

    def _build_list_page(self, notebook: ttk.Notebook, title: str, capture_cmd) -> ttk.Treeview:
        page = tk.Frame(notebook)
        notebook.add(page, text=title)
        tree = ttk.Treeview(page, columns=("value",), show="tree headings", height=14)
        tree.heading("#0", text="Name")
        tree.heading("value", text="Value")
        tree.column("#0", width=280)
        tree.column("value", width=300)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        label = "Capture Selected Position" if title == "Positions" else "Capture Selected Region"
        tk.Button(page, text=label, command=capture_cmd).pack(anchor="w", padx=8, pady=(0, 8))
        return tree

    def _build_timing_page(self, notebook: ttk.Notebook) -> tk.Frame:
        page = tk.Frame(notebook)
        row = 0
        for row, definition in enumerate(profiles.TIMING_DEFINITIONS):
            tk.Label(page, text=definition.label, anchor="w").grid(
                row=row, column=0, sticky="w", padx=8, pady=6
            )
            var = tk.DoubleVar(
                value=self._profile.get_timing(definition.key, definition.default_value)
            )
            self._timing_inputs[definition.key] = var
            tk.Spinbox(
                page, from_=0.1, to=120, increment=0.5, textvariable=var, width=10
            ).grid(row=row, column=1, sticky="w", padx=8, pady=6)

        # Drop Y offset: pixels to aim below every drag's drop target, since a
        # grabbed item is drawn offset above the cursor. Applies to all drops.
        row += 1
        tk.Label(page, text="Drop offset (pixels lower)", anchor="w").grid(
            row=row, column=0, sticky="w", padx=8, pady=(16, 6)
        )
        self._drop_offset_var = tk.IntVar(value=self._profile.drop_offset_y)
        tk.Spinbox(
            page, from_=-200, to=200, increment=1, textvariable=self._drop_offset_var, width=10
        ).grid(row=row, column=1, sticky="w", padx=8, pady=(16, 6))
        return page

    # --- capture ------------------------------------------------------------

    def _capture_point(self) -> None:
        selection = self._point_tree.selection()
        if not selection:
            return
        key = selection[0]
        definition = next((d for d in profiles.POINT_DEFINITIONS if d.key == key), None)
        if definition is None:
            return
        self._window.grab_release()
        self._window.withdraw()
        point = overlay.capture_point(definition.label, self._window.master)
        self._window.deiconify()
        self._window.grab_set()
        if point is not None:
            self._profile.set_point(key, point)
            self._refresh_points()

    def _capture_region(self) -> None:
        selection = self._region_tree.selection()
        if not selection:
            return
        key = selection[0]
        definition = next((d for d in profiles.REGION_DEFINITIONS if d.key == key), None)
        if definition is None:
            return
        self._window.grab_release()
        self._window.withdraw()
        region = overlay.capture_region(definition.label, self._window.master)
        self._window.deiconify()
        self._window.grab_set()
        if region is not None:
            self._profile.set_region(key, region)
            self._refresh_regions()

    # --- refresh ------------------------------------------------------------

    def _refresh_points(self) -> None:
        self._point_tree.delete(*self._point_tree.get_children())
        for definition in profiles.POINT_DEFINITIONS:
            point = self._profile.try_point(definition.key)
            value = f"{point[0]}, {point[1]}" if point is not None else "(not set)"
            self._point_tree.insert("", "end", iid=definition.key, text=definition.label,
                                    values=(value,))

    def _refresh_regions(self) -> None:
        self._region_tree.delete(*self._region_tree.get_children())
        for definition in profiles.REGION_DEFINITIONS:
            x, y, w, h = self._profile.get_region(definition.key)
            self._region_tree.insert("", "end", iid=definition.key, text=definition.label,
                                     values=(f"{x}, {y}, {w}, {h}",))

    # --- actions ------------------------------------------------------------

    def _reset_defaults(self) -> None:
        defaults = RestaurantProfile.default()
        self._profile.points = dict(defaults.points)
        self._profile.regions = dict(defaults.regions)
        self._profile.timings = dict(defaults.timings)
        self._profile.drop_offset_y = defaults.drop_offset_y
        self._refresh_points()
        self._refresh_regions()
        for definition in profiles.TIMING_DEFINITIONS:
            if definition.key in self._timing_inputs:
                self._timing_inputs[definition.key].set(
                    self._profile.get_timing(definition.key, definition.default_value)
                )
        self._drop_offset_var.set(self._profile.drop_offset_y)

    def _save(self) -> None:
        for key, var in self._timing_inputs.items():
            self._profile.set_timing(key, float(var.get()))
        self._profile.set_drop_offset(int(self._drop_offset_var.get()))
        self.result = self._profile
        self._window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self._window.destroy()
