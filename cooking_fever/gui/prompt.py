"""Simple text-input dialog, mirroring the C# PromptDialog."""
from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog
from typing import Optional


def ask(parent: tk.Misc, title: str, label: str, default: str = "") -> Optional[str]:
    value = simpledialog.askstring(title, label, initialvalue=default, parent=parent)
    if value is None:
        return None
    value = value.strip()
    return value or None
