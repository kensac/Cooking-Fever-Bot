"""Print the current mouse position on an interval. Ctrl+C to stop."""
from __future__ import annotations

import time

from . import automation


def run(interval: float = 1.0) -> None:
    interval = max(0.05, interval)
    print("Tracking mouse position. Press Ctrl+C to stop.")
    try:
        while True:
            x, y = automation.position()
            print(f"Mouse position: X={x}, Y={y}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nExiting.")
