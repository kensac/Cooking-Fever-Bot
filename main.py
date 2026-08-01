#!/usr/bin/env python3
"""Entry point for the Cooking Fever Tools Python app.

Run without arguments to open the dashboard, or pass a command
(bot, tracker, region, snap, monitor, todo, help). See `python main.py help`.
"""
import sys

from cooking_fever.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
