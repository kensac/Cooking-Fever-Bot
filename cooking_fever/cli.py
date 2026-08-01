"""Command dispatch for the Cooking Fever Tools Python app.

    (no command) / dashboard   Open the graphical dashboard.
    bot                        Run the automation bot.
    tracker [interval]         Print the mouse position on an interval.
    region                     Drag-select regions and print coordinates.
    snap                       Drag-select regions and save PNG snapshots.
    monitor                    Open the action monitor and screenshot tagger.
    todo                       Open the objective/task todo utility.
    help                       Show this message.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

HELP_TEXT = """Cooking Fever Tools (Python)

Commands:
  dashboard   Open the graphical dashboard. Default when no command is supplied.
  bot         Run the Cooking Fever automation bot.
  tracker     Print the current mouse position once per second.
  region      Drag-select screen regions and print their coordinates.
  snap        Drag-select screen regions and save PNG snapshots.
  monitor     Open the action monitor and screenshot tagger.
  todo        Open the objective/task todo utility.

Bot controls:
  s           Start the bot after launch.
  p           Pause or resume.
  gg          Stop (press g twice quickly).

Bot options:
  --assets <path>       Template image directory. Default: ./assets
  --profile <path>      Restaurant profile JSON file.
  --confidence <0-1>    Template matching confidence. Default: 0.8
  --delay <seconds>     Initial delay before listening for start. Default: 5
  --start               Start immediately without waiting for the s hotkey.
  --dry-run             Log clicks and drags without moving the mouse.
"""


def _run_bot(args: List[str]) -> int:
    from .bot import BotOptions, CookingFeverBot

    parser = argparse.ArgumentParser(prog="bot", add_help=False)
    parser.add_argument("--assets")
    parser.add_argument("--profile")
    parser.add_argument("--confidence", type=float, default=0.8)
    parser.add_argument("--delay", type=int, default=5)
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    parsed, _unknown = parser.parse_known_args(args)

    options = BotOptions.from_args(
        assets=parsed.assets,
        confidence=parsed.confidence,
        delay=parsed.delay,
        profile_path=parsed.profile,
        start_immediately=parsed.start,
        dry_run=parsed.dry_run,
    )
    CookingFeverBot(options).run()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0].strip().lower() if argv else "dashboard"
    rest = argv[1:]

    try:
        if command in ("dashboard", "launcher", "app"):
            from .gui.dashboard import run as run_dashboard

            run_dashboard()
            return 0
        if command == "bot":
            return _run_bot(rest)
        if command == "tracker":
            from . import tracker

            interval = float(rest[0]) if rest else 1.0
            tracker.run(interval)
            return 0
        if command in ("region", "snap"):
            from .gui.overlay import run_region_tool

            run_region_tool(capture_screenshots=(command == "snap"))
            return 0
        if command == "monitor":
            from .gui.monitor import run as run_monitor

            run_monitor()
            return 0
        if command == "todo":
            from .gui.todo import run as run_todo

            run_todo()
            return 0
        if command in ("help", "--help", "-h"):
            print(HELP_TEXT)
            return 0

        print(f"Unknown command: {command}", file=sys.stderr)
        print(HELP_TEXT, file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level guard, mirror C# behaviour
        print(str(exc), file=sys.stderr)
        return 1
