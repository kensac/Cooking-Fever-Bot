# Agent Instructions

This repository is a cross-platform, GUI-first Python app for Cooking Fever tools.
The main entry point is `main.py`; the code lives in the `cooking_fever/` package.
Legacy C#/.NET sources remain under `src/` for reference only.

## Version Management

- Keep `version.md` current whenever functionality or user-facing behavior changes.
- Keep the `version` in `pyproject.toml` and `cooking_fever/__init__.py` (`__version__`)
  in sync with `version.md`.
- Use semantic versions:
  - Patch for fixes and small usability changes.
  - Minor for new features.
  - Major for breaking changes or large workflow changes.
- Add a short note in `version.md` explaining what changed.

## Structure

- `main.py` — command dispatch (`dashboard`, `bot`, `tracker`, `region`, `snap`, `monitor`, `todo`).
- `cooking_fever/automation.py` — mouse/screen input and capture (pyautogui + mss).
- `cooking_fever/template.py` — OpenCV template matching.
- `cooking_fever/profiles.py` — restaurant profiles and JSON store.
- `cooking_fever/bot.py` — the order-scheduling automation bot.
- `cooking_fever/gui/` — tkinter dashboard and tool windows.

## Generated Output

- `assets/`, `profiles/`, `screenshots/`, and `logs/` are local generated output
  and stay ignored by git.
- Do not commit generated files, virtual environments, or `__pycache__/`.

## Verification

- Before handing off, run:

```bash
python3 -m compileall cooking_fever main.py
python3 main.py help
```

- Heavy dependencies (pyautogui, mss, opencv-python, pynput) are imported lazily,
  so `help` and the pure-logic modules import without them installed.
- The GUI needs a Python built with Tk support; if `_tkinter` is missing, install
  it (`brew install python-tk`, `apt install python3-tk`, or use a python.org build).
- For automation or GUI changes, smoke test with `python3 main.py bot --dry-run --start`
  and by opening the dashboard where a display is available.
