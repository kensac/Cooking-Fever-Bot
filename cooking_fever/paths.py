"""Filesystem locations used by the app.

Mirrors the C# AppPaths helper: assets/, profiles/, screenshots/, and logs/
live beside the application. The assets directory prefers ./assets in the
current working directory when it exists, matching the original behaviour.
"""
from __future__ import annotations

import os
from pathlib import Path

# Project root = the directory that contains the cooking_fever package.
APP_DIRECTORY = Path(__file__).resolve().parent.parent


def assets_directory() -> Path:
    cwd_assets = Path.cwd() / "assets"
    if cwd_assets.is_dir():
        return cwd_assets
    return APP_DIRECTORY / "assets"


def screenshots_directory() -> Path:
    return APP_DIRECTORY / "screenshots"


def profiles_directory() -> Path:
    return APP_DIRECTORY / "profiles"


def logs_directory() -> Path:
    return APP_DIRECTORY / "logs"


def ensure_directories() -> None:
    for directory in (
        profiles_directory(),
        assets_directory(),
        screenshots_directory(),
        logs_directory(),
    ):
        os.makedirs(directory, exist_ok=True)
