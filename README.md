# Cooking Fever Tools

Cross-platform Python tools for automating and calibrating Cooking Fever workflows.

The app is GUI-first. Run it to open the dashboard, manage profiles, calibrate
positions, capture template images, run the bot, and review logs. The same
entry point also exposes each utility as a command.

> Rewritten from the original C#/.NET Windows app into Python so it runs on
> macOS, Linux, and Windows. The legacy C# sources are kept under `src/` for
> reference and can be removed once you are happy with the port.

## Main Features

- Dashboard for starting and stopping the bot.
- JSON restaurant profiles stored in `profiles/`.
- Calibration wizard for click positions, order/coin regions, and cook/refill timings.
- Burgers, hotdogs, sodas, and fries, including topping variants (lettuce,
  tomato, ketchup) and orders containing up to 4 items.
- Interchangeable station pools: up to 4 pans, 4 grills, 3 prep plates each, and
  3 soda slots. A station exists only once it is calibrated, so you set up as
  many as your restaurant has.
- Automatic coin/tip collection: clicks coins in the calibrated coin region whenever they appear.
- Asset manager for capturing, previewing, and testing template images.
- Dry-run mode that logs bot clicks and drags without moving the mouse.
- In-dashboard mouse tracking.
- Action monitor, region selector, screenshot tool, mouse tracker, and todo utility.

## Requirements

- Python 3.10+ with Tk support (`python.org` builds include it; on macOS with
  Homebrew run `brew install python-tk`, on Debian/Ubuntu `sudo apt install python3-tk`).
- Python packages from `requirements.txt`.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### macOS permissions

Grant your Python interpreter (or terminal) these permissions in
System Settings → Privacy & Security:

- **Accessibility** — required for pyautogui/pynput to move the mouse and read keys.
- **Screen Recording** — required for screen capture and template matching.

## Run

```bash
python3 main.py                  # opens the dashboard
```

The app creates these folders beside `main.py` when needed:

```text
assets/
profiles/
screenshots/
logs/
```

## Recommended Setup

1. Open the dashboard.
2. Create or select a profile.
3. Click `Calibrate` and capture the required screen positions and order regions.
4. Click `Assets` and capture these templates:

```text
burger.png
burger-lettuce.png          # optional topping variants; crop the same area as burger.png
burger-tomato.png
burger-lettuce-tomato.png
soda.png
fries.png                   # optional; only needed if the restaurant serves fries
hotdog.png
hotdog-ketchup.png          # a hotdog order that has ketchup on it (served with ketchup added)
coins.png                   # the coins/tip that appear after serving a customer
restart-1.png
restart-2.png
```

The asset manager's **Bot Templates** panel lists every one of these by friendly
name with a live thumbnail and set/missing status, and can capture each straight
to the right filename. That list (`cooking_fever/gui/assets.py:REQUIRED_TEMPLATES`)
is the source of truth.

Capture templates with `Assets -> Capture Template` (not external screenshots).
On macOS screen capture runs at native Retina resolution, so templates must be
grabbed through the app to match the same scale; matching converts results back
to logical click coordinates automatically.

5. Use `Test Selected` in the asset manager to confirm each template can be found on screen.
6. Start the bot from the dashboard. Use `Dry Run` first to verify behavior without mouse movement.

## Bot Controls

When the bot is running, press (these are **global hotkeys** — they work even
while the game is focused):

- `s` starts (when not auto-started).
- `p` pauses or resumes.
- `gg` stops (press `g` twice quickly).
- `Ctrl+C` also stops.

Global hotkeys use pynput and need macOS **Accessibility** permission. If pynput
is unavailable, control falls back to the terminal (which must then stay
focused). From the dashboard, use the **Stop Bot** button. In the capture
overlays, **right-click** to cancel (the overlays avoid keyboard hooks because
pynput's keyboard listener crashes inside a GUI process on macOS).

## Commands

```bash
python3 main.py                                        # dashboard (default)
python3 main.py help
python3 main.py bot --profile "profiles/Burger Shop.json" --start
python3 main.py bot --dry-run --start
python3 main.py tracker
python3 main.py region
python3 main.py snap
python3 main.py monitor
python3 main.py todo
```

### Bot options

```text
--assets <path>       Template image directory. Default: ./assets
--profile <path>      Restaurant profile JSON file.
--confidence <0-1>    Template matching confidence. Default: 0.8
--delay <seconds>     Initial delay before listening for start. Default: 5
--start               Start immediately without waiting for the s hotkey.
--dry-run             Log clicks and drags without moving the mouse.
```

## Project Layout

```text
main.py                  Entry point / command dispatch.
cooking_fever/           Core package.
  automation.py          Mouse/screen input and capture (pyautogui + mss).
  template.py            OpenCV template matching.
  profiles.py            Restaurant profiles and JSON store.
  bot.py                 The order-scheduling automation bot.
  tracker.py             Mouse position printer.
  gui/                   Tkinter dashboard and tool windows.
src/                     Legacy C#/.NET sources (reference only).
```

`assets/`, `profiles/`, `screenshots/`, and `logs/` are generated locally and
ignored by git.
