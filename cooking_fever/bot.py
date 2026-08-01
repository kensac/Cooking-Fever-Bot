"""The Cooking Fever automation bot.

A faithful port of the C# CookingFeverBot: a dependency-graph task scheduler
that watches four customer order regions, then cooks and delivers burgers,
sodas, and hotdogs while juggling shared resources (pans, soda machines, the
hotdog grill/warmer, and the single mouse).

Control keys (global hotkeys; work even when the game is focused):
    s   start
    p   pause / resume
    gg  stop (press g twice within 0.5s)
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import automation, profiles, template
from .geometry import Match, Point, Region
from .profiles import RestaurantProfile

DEFAULT_BURGER_COOK_TIME = 9.0
DEFAULT_SODA_REFILL_TIME = 8.0
DEFAULT_HOTDOG_COOK_TIME = 10.0
DEFAULT_FRIES_COOK_TIME = 10.0
# One click of the fryer cooks this many servings into the pickup area.
FRIES_PER_BATCH = 2

# Task states
PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"

# Scheduler priority. Higher-priority pending tasks get first claim on the shared
# mouse each tick. Grabbing a cooked patty/dog off the heat is urgent because it
# burns if left, so those beat everything else; everything else is NORMAL.
PRIORITY_NORMAL = 0
PRIORITY_GRAB = 100


@dataclass
class BotOptions:
    assets_directory: str
    confidence: float
    initial_delay_seconds: int
    profile_path: Optional[str]
    profile: RestaurantProfile
    start_immediately: bool
    dry_run: bool

    @staticmethod
    def from_args(
        assets: Optional[str] = None,
        confidence: float = 0.8,
        delay: int = 5,
        profile_path: Optional[str] = None,
        start_immediately: bool = False,
        dry_run: bool = False,
    ) -> "BotOptions":
        assets_dir = str(Path(assets).resolve()) if assets else str(profiles.paths.assets_directory())
        confidence = min(1.0, max(0.0, confidence))
        delay = max(0, delay)
        profile = profiles.load_or_default(profile_path)
        if profile.assets_directory.strip():
            assets_dir = str(Path(profile.assets_directory).resolve())
        return BotOptions(
            assets_directory=assets_dir,
            confidence=confidence,
            initial_delay_seconds=delay,
            profile_path=profile_path,
            profile=profile,
            start_immediately=start_immediately,
            dry_run=dry_run,
        )


class BotWorkItem:
    """A single scheduled action with dependencies and a completion clock."""

    def __init__(
        self,
        name: str,
        resource_check: Callable[[], bool],
        run_action: Callable[["BotWorkItem"], None],
        bot: "CookingFeverBot",
        dependencies: Optional[List["BotWorkItem"]] = None,
        on_finish: Optional[Callable[["BotWorkItem"], None]] = None,
        priority: int = PRIORITY_NORMAL,
    ) -> None:
        self.name = name
        self._resource_check = resource_check
        self._run_action = run_action
        self._bot = bot
        self._dependencies = dependencies or []
        self._on_finish = on_finish
        self.priority = priority
        self.state = PENDING
        self.end_time = 0.0

    def can_start(self) -> bool:
        return all(d.state == COMPLETED for d in self._dependencies) and self._resource_check()

    def start(self) -> None:
        self.state = RUNNING
        self._run_action(self)

    def update(self) -> None:
        if self.state != RUNNING:
            return
        if self.end_time == 0 or self._bot.now >= self.end_time:
            self._finish()

    def _finish(self) -> None:
        self.state = COMPLETED
        if self._on_finish is not None:
            self._on_finish(self)


class ControlListener:
    """Watch for s / p / gg control keystrokes.

    Primary path is a global pynput keyboard hook, so the keys work even when the
    game (not the terminal) is focused - the same approach as the district-47
    gemex.py script. This is safe here because the bot runs as its own process
    with no GUI event loop; pynput's macOS key translation only crashes when a
    tkinter/Cocoa app is running (which is why the dashboard overlays avoid it).

    If pynput is unavailable, it falls back to reading the terminal (cbreak on
    POSIX, msvcrt on Windows), which requires the terminal to stay focused.
    Ctrl+C and the dashboard Stop button always work regardless.
    """

    def __init__(self, bot: "CookingFeverBot") -> None:
        self._bot = bot
        self._last_g_time = -10.0
        self._pressed: set = set()
        self._listener = None
        self._thread: Optional[threading.Thread] = None
        self._stop = False

    def start(self) -> None:
        if self._start_global():
            print("[CONTROL] Global hotkeys active: s starts, p pauses/resumes, "
                  "gg stops. Works even when the game is focused.")
            return
        self._start_terminal()

    def _start_global(self) -> bool:
        try:
            from pynput import keyboard
        except Exception:
            return False
        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release
            )
            self._listener.daemon = True
            self._listener.start()
            return True
        except Exception as exc:  # noqa: BLE001 - best effort; fall back to terminal
            print(f"[CONTROL] Could not start global hotkeys ({exc}).")
            self._listener = None
            return False

    def _start_terminal(self) -> None:
        if not sys.stdin or not sys.stdin.isatty():
            print("[CONTROL] No global hotkeys and no interactive terminal; use "
                  "--start plus the dashboard Stop button or Ctrl+C.")
            return
        target = self._run_windows if sys.platform.startswith("win") else self._run_posix
        self._thread = threading.Thread(target=target, daemon=True, name="Bot hotkeys")
        self._thread.start()
        print("[CONTROL] Terminal hotkeys active: keep this terminal focused for s / p / gg.")

    def stop(self) -> None:
        self._stop = True
        if self._listener is not None:
            self._listener.stop()

    def _on_press(self, key) -> None:
        char = getattr(key, "char", None)
        if char is None or char in self._pressed:
            return  # ignore auto-repeat while a key is held
        self._pressed.add(char)
        self._handle(char)

    def _on_release(self, key) -> None:
        self._pressed.discard(getattr(key, "char", None))

    def _handle(self, char: str) -> None:
        if char == "s" and not self._bot.start_requested:
            self._bot.start_requested = True
            print("[CONTROL] Start requested.")
        elif char == "p":
            self._bot.paused = not self._bot.paused
            print("[CONTROL] Paused." if self._bot.paused else "[CONTROL] Resumed.")
        elif char == "g":
            now = self._bot.now
            if now - self._last_g_time < 0.5:
                self._bot.stop_requested = True
                print("[CONTROL] Stop requested.")
            self._last_g_time = now

    def _run_posix(self) -> None:
        import os
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            # Read the fd directly (not the buffered stdin object) so it stays in
            # sync with select even if several keystrokes arrive together.
            while not self._stop and not self._bot.stop_requested:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    data = os.read(fd, 4096)
                    if not data:
                        break
                    for char in data.decode(errors="ignore"):
                        self._handle(char)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _run_windows(self) -> None:
        import msvcrt

        while not self._stop and not self._bot.stop_requested:
            if msvcrt.kbhit():
                self._handle(msvcrt.getwch())
            else:
                time.sleep(0.05)


class StationPool:
    """A set of interchangeable stations: burger pans, hotdog grills, or prep
    plates.

    The pool is built from whatever points the user calibrated for those
    stations, so its size is however many exist ("unset = does not exist"). A
    station is free when it is not held and its busy timer has elapsed. Callers
    claim ``free_index`` - the lowest free index - which mirrors how the game
    fills the leftmost free plate/appliance, so a bun dispensed after claiming
    slot j lands on the same plate the bot will assemble on.
    """

    def __init__(self, name: str, points: List[Point], clock: Callable[[], float]) -> None:
        self.name = name
        self._points = points
        self._clock = clock
        self._busy_until = [0.0] * len(points)
        self._held = [False] * len(points)

    def __len__(self) -> int:
        return len(self._points)

    def point(self, index: int) -> Point:
        return self._points[index]

    def free_index(self) -> Optional[int]:
        now = self._clock()
        for i in range(len(self._points)):
            if not self._held[i] and now >= self._busy_until[i]:
                return i
        return None

    def has_free(self) -> bool:
        return self.free_index() is not None

    def active_count(self) -> int:
        """How many stations are currently held (e.g. patties/dogs on the heat)."""
        return sum(self._held)

    def busy_until(self, index: int) -> float:
        return self._busy_until[index]

    def lock(self, index: int, seconds: float, hold: bool = True) -> None:
        """Start a station's busy timer. With ``hold`` the station stays claimed
        until ``release`` (pans/prep plates); without it the station auto-frees
        when the timer elapses (soda machines refilling)."""
        self._busy_until[index] = self._clock() + seconds
        if hold:
            self._held[index] = True

    def release(self, index: int) -> None:
        self._held[index] = False


class FriesTray:
    """The fry pickup slots. The fryer cooks a batch of fries into empty slots,
    and each cooked fry sits in its own slot (calibrated in fill order) until it
    is dragged to a customer. Unlike a StationPool a slot is simply full or
    empty - cooking fills, serving empties."""

    def __init__(self, points: List[Point]) -> None:
        self._points = points
        self._filled = [False] * len(points)

    def __len__(self) -> int:
        return len(self._points)

    def point(self, index: int) -> Point:
        return self._points[index]

    def count_filled(self) -> int:
        return sum(self._filled)

    def count_empty(self) -> int:
        return len(self._points) - self.count_filled()

    def filled_index(self) -> Optional[int]:
        """The lowest slot holding a ready fry, or None."""
        for i, full in enumerate(self._filled):
            if full:
                return i
        return None

    def fill_next(self, count: int) -> int:
        """Fill up to ``count`` lowest empty slots; returns how many were filled."""
        filled = 0
        for i in range(len(self._points)):
            if filled >= count:
                break
            if not self._filled[i]:
                self._filled[i] = True
                filled += 1
        return filled

    def take(self, index: int) -> None:
        self._filled[index] = False


class CookingFeverBot:
    def __init__(self, options: BotOptions) -> None:
        self._options = options
        self._profile = options.profile
        self._burger_cook_time = self._profile.get_timing(
            profiles.BURGER_COOK_SECONDS, DEFAULT_BURGER_COOK_TIME
        )
        self._soda_refill_time = self._profile.get_timing(
            profiles.SODA_REFILL_SECONDS, DEFAULT_SODA_REFILL_TIME
        )
        self._hotdog_cook_time = self._profile.get_timing(
            profiles.HOTDOG_COOK_SECONDS, DEFAULT_HOTDOG_COOK_TIME
        )
        self._fries_cook_time = self._profile.get_timing(
            profiles.FRIES_COOK_SECONDS, DEFAULT_FRIES_COOK_TIME
        )

        p = self._profile
        self._play_button_stage_select = p.get_point(profiles.PLAY_BUTTON_STAGE_SELECT)
        self._play_button_in_stage = p.get_point(profiles.PLAY_BUTTON_IN_STAGE)
        self._meat_location = p.get_point(profiles.MEAT_LOCATION)
        self._bun_location = p.get_point(profiles.BUN_LOCATION)
        self._hotdog_uncooked = p.get_point(profiles.HOTDOG_UNCOOKED)
        self._hotdog_bun = p.get_point(profiles.HOTDOG_BUN)
        self._ketchup_bottle = p.get_point(profiles.KETCHUP_BOTTLE)
        # Optional burger toppings; None until calibrated.
        self._lettuce_source = p.try_point(profiles.LETTUCE_SOURCE)
        self._tomato_source = p.try_point(profiles.TOMATO_SOURCE)
        # Optional fryer; fries are active only if the fryer and >=1 pickup slot
        # are calibrated. The tray holds each cooked fry in its own slot.
        self._fryer = p.try_point(profiles.FRYER)
        self._fries_tray = FriesTray([
            p.get_point(k) for k in (
                profiles.FRIES_PICKUP_1, profiles.FRIES_PICKUP_2,
                profiles.FRIES_PICKUP_3, profiles.FRIES_PICKUP_4,
            ) if p.has_point(k)
        ])

        # Interchangeable-station pools, sized by whatever the user calibrated.
        # Pan/grill/prep slot 1 keeps its original key so existing profiles work;
        # slots 2-4 are optional and appear only once calibrated.
        self._burger_pans = self._pool("pan", [
            profiles.FRYING_PAN_1, profiles.FRYING_PAN_2,
            profiles.FRYING_PAN_3, profiles.FRYING_PAN_4,
        ])
        self._hotdog_grills = self._pool("grill", [
            profiles.HOTDOG_GRILL_1, profiles.HOTDOG_GRILL_2,
            profiles.HOTDOG_GRILL_3, profiles.HOTDOG_GRILL_4,
        ])
        self._burger_preps = self._pool("burger-prep", [
            profiles.BURGER_POSITION, profiles.BURGER_PREP_2, profiles.BURGER_PREP_3,
        ])
        self._hotdog_preps = self._pool("hotdog-prep", [
            profiles.HOTDOG_PREP, profiles.HOTDOG_PREP_2, profiles.HOTDOG_PREP_3,
        ])
        self._soda_machines = self._pool("soda", [
            profiles.SODA_MACHINE_1, profiles.SODA_MACHINE_2, profiles.SODA_MACHINE_3,
        ])

        self._customer_coords: Dict[int, Point] = {
            1: p.get_point(profiles.CUSTOMER_1),
            2: p.get_point(profiles.CUSTOMER_2),
            3: p.get_point(profiles.CUSTOMER_3),
            4: p.get_point(profiles.CUSTOMER_4),
        }
        self._order_regions: Dict[int, Region] = {
            1: p.get_region(profiles.ORDER_REGION_1),
            2: p.get_region(profiles.ORDER_REGION_2),
            3: p.get_region(profiles.ORDER_REGION_3),
            4: p.get_region(profiles.ORDER_REGION_4),
        }
        self._coin_region = p.get_region(profiles.COIN_REGION)

        self._tasks: List[BotWorkItem] = []
        # A ticket can hold several items; a region is "in progress" until all of
        # its item pipelines finish (tracked by the outstanding counter).
        self._region_in_progress: Dict[int, bool] = {1: False, 2: False, 3: False, 4: False}
        self._region_outstanding: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
        self._missing_template_warnings: set = set()
        self._missing_point_warnings: set = set()

        self.start_requested = False
        self.stop_requested = False
        self.paused = False

        self._mouse_busy_until = 0.0
        # Grabbed items render offset above the cursor, so aim every drop this
        # many pixels lower than the calibrated target to land it correctly.
        self._drop_offset_y = int(self._profile.drop_offset_y)

        # Fries production: the fryer cooks a shared batch into the tray; orders
        # draw from it. ``demand`` is fry orders not yet served, ``incoming`` is
        # fries that will land when the current batch finishes cooking.
        self._fryer_busy_until = 0.0
        self._fries_incoming = 0
        self._fries_demand = 0

        self._start_clock = time.monotonic()
        self._control = ControlListener(self)

    def _pool(self, name: str, keys: List[str]) -> StationPool:
        points = [self._profile.get_point(k) for k in keys if self._profile.has_point(k)]
        return StationPool(name, points, lambda: self.now)

    # --- clock and resources ------------------------------------------------

    @property
    def now(self) -> float:
        return time.monotonic() - self._start_clock

    def _mouse_free(self) -> bool:
        return self.now >= self._mouse_busy_until

    def _lock_mouse_for(self, seconds: float) -> None:
        self._mouse_busy_until = self.now + seconds

    def _complete_item(self, customer: int, kind: str) -> None:
        """Mark one item of a customer's ticket done; free the region once all
        of its items have been served so it can take a new order."""
        self._region_outstanding[customer] = max(0, self._region_outstanding[customer] - 1)
        if self._region_outstanding[customer] == 0:
            self._region_in_progress[customer] = False
            print(f"[{kind}] Region {customer} order complete.")

    # --- input --------------------------------------------------------------

    def _move_and_click(self, point: Point) -> None:
        self._lock_mouse_for(0.3)
        if self._options.dry_run:
            print(f"[DRY RUN] Click ({point[0]}, {point[1]})")
            return
        automation.click(point)

    def _move_and_drag(self, source: Point, target: Point) -> None:
        # Cover the native drag (hold + eased sweep + settle) plus a small buffer.
        self._lock_mouse_for(0.3)
        # Aim the drop lower to compensate for the held item's on-cursor offset.
        drop = (target[0], target[1] + self._drop_offset_y)
        if self._options.dry_run:
            print(f"[DRY RUN] Drag ({source[0]}, {source[1]}) -> ({drop[0]}, {drop[1]})")
            return
        automation.drag(source, drop)

    def _safe_locate(self, file_name: str, region: Optional[Region] = None) -> Optional[Match]:
        path = Path(self._options.assets_directory) / file_name
        if not path.is_file():
            if file_name not in self._missing_template_warnings:
                self._missing_template_warnings.add(file_name)
                print(f"[ASSET] Missing template: {path}")
            return None
        return template.locate(path, region, self._options.confidence)

    def _locate_any_restart(self) -> Optional[Match]:
        return self._safe_locate("restart-1.png") or self._safe_locate("restart-2.png")

    # --- lifecycle ----------------------------------------------------------

    def run(self) -> None:
        print("Cooking Fever Bot - Python port")
        print(f"Profile: {self._profile.name}")
        print(f"Template assets: {self._options.assets_directory}")
        if self._options.dry_run:
            print("Dry run is enabled. Clicks and drags will only be logged.")
        else:
            print("Press 's' to start, 'gg' to stop, 'p' to pause.")
        print()

        if not Path(self._options.assets_directory).is_dir():
            print(
                "Warning: asset directory does not exist yet. Add burger.png, soda.png, "
                "hotdog.png, restart-1.png, and restart-2.png (plus optional "
                "burger-lettuce.png, burger-tomato.png, burger-lettuce-tomato.png, "
                "hotdog-ketchup.png, coins.png)."
            )

        fries = f"{len(self._fries_tray)} slot(s)" if self._fryer is not None else "off"
        pools = (
            f"{len(self._burger_pans)} pan(s), {len(self._hotdog_grills)} grill(s), "
            f"{len(self._burger_preps)} burger prep, {len(self._hotdog_preps)} hotdog prep, "
            f"{len(self._soda_machines)} soda, fries {fries}"
        )
        print(f"Stations calibrated: {pools}.")

        self._control.start()

        try:
            time.sleep(self._options.initial_delay_seconds)
            if self._options.start_immediately:
                self.start_requested = True
                print("[CONTROL] Auto-start requested.")

            while not self.start_requested and not self.stop_requested:
                time.sleep(0.1)

            if not self.stop_requested:
                self._main_loop()
        except KeyboardInterrupt:
            print("\n[CONTROL] Interrupted; stopping.")
            self.stop_requested = True
        finally:
            self._control.stop()

    def _main_loop(self) -> None:
        while not self.stop_requested:
            if self.paused:
                time.sleep(0.1)
                continue

            if len(self._tasks) == 0:
                self._do_restart_stage()

            self._detect_new_orders()
            self._reconcile_fryer()
            self._update_tasks()
            self._tasks = [t for t in self._tasks if t.state != COMPLETED]
            self._manage_fryer()
            self._collect_money()

            time.sleep(0.1 if self._tasks else 0.5)

        print("[DEBUG] Main loop ended.")

    def _reconcile_fryer(self) -> None:
        """Drop a finished batch into the tray so its fries can be served this
        tick. Runs before the scheduler so newly-ready fries are servable now."""
        if self._fryer is None:
            return
        if self._fryer_busy_until and self.now >= self._fryer_busy_until:
            landed = self._fries_tray.fill_next(self._fries_incoming)
            if landed:
                print(f"[FRIES] Batch ready (+{landed}).")
            self._fries_incoming = 0
            self._fryer_busy_until = 0.0

    def _manage_fryer(self) -> None:
        """Keep the fry tray stocked. The fryer is a single click that cooks
        ``FRIES_PER_BATCH`` servings into empty tray slots after
        ``_fries_cook_time``.

        Fries do not burn or cost anything to over-prepare, so we cook ahead:
        besides the on-demand case (unmet fry orders), we preemptively top up the
        tray during lulls. The one guard is that we never fire the fryer while a
        burger/hotdog is on the heat - those DO burn if not grabbed promptly, and
        a fryer click would briefly hold the mouse the grab may need. Runs after
        the scheduler (serving) so ready fries go out first and batches stay full;
        production is loop-managed because it is shared across every fry order."""
        if self._fryer is None or len(self._fries_tray) == 0:
            return
        if self._fryer_busy_until != 0.0 or self._fries_tray.count_empty() == 0 or not self._mouse_free():
            return

        supply = self._fries_tray.count_filled() + self._fries_incoming
        on_demand = self._fries_demand > supply
        perishables_cooking = self._burger_pans.active_count() or self._hotdog_grills.active_count()
        # On-demand cooking always runs; preemptive top-up only when nothing that
        # can burn is currently cooking.
        if not on_demand and perishables_cooking:
            return

        batch = min(FRIES_PER_BATCH, self._fries_tray.count_empty())
        self._move_and_click(self._fryer)
        self._fryer_busy_until = self.now + self._fries_cook_time
        self._fries_incoming += batch
        reason = "on demand" if on_demand else "ahead"
        print(f"[FRIES] Cooking a batch of {batch} ({reason}).")

    def _collect_money(self) -> None:
        """Click any coins/tips on screen to collect payment after a delivery."""
        if not self._mouse_free():
            return
        match = self._safe_locate("coins.png", self._coin_region)
        if match is not None:
            print("[MONEY] Collecting coins.")
            self._move_and_click(match.center)

    def _do_restart_stage(self) -> bool:
        restart = self._locate_any_restart()
        if restart is None:
            return False

        print("[DEBUG] Found restart button. Restarting stage.")
        self._move_and_click(restart.center)
        time.sleep(1.5)
        self._move_and_click(self._play_button_stage_select)
        time.sleep(1.0)
        self._move_and_click(self._play_button_in_stage)
        time.sleep(5.0)
        return True

    # --- order detection ----------------------------------------------------

    # Order icons. Burgers and hotdogs each have look-alike variants (plain vs
    # topping); detection finds every icon in a region and lets the best-scoring
    # label win each slot, so a "burger + lettuce" reads as that, not plain.
    _ORDER_TEMPLATES = [
        ("burger", "burger.png"),
        ("burger_lettuce", "burger-lettuce.png"),
        ("burger_tomato", "burger-tomato.png"),
        ("burger_both", "burger-lettuce-tomato.png"),
        ("soda", "soda.png"),
        ("hotdog", "hotdog.png"),
        ("hotdog_ketchup", "hotdog-ketchup.png"),
        ("fries", "fries.png"),
    ]

    def _order_candidates(self):
        candidates = []
        for label, file_name in self._ORDER_TEMPLATES:
            path = Path(self._options.assets_directory) / file_name
            if path.is_file():
                candidates.append((label, path))
            elif file_name not in self._missing_template_warnings:
                self._missing_template_warnings.add(file_name)
                print(f"[ASSET] Missing template: {path}")
        return candidates

    def _detect_new_orders(self) -> None:
        candidates = self._order_candidates()
        if not candidates:
            return

        for customer in range(1, 5):
            if self.stop_requested:
                return
            if self._region_in_progress[customer]:
                continue

            region = self._order_regions[customer]
            items = template.find_items(candidates, region, self._options.confidence)
            if not items:
                continue

            pipelines = []
            for label, _match in items:
                tasks = self._tasks_for_label(customer, label)
                if tasks:
                    pipelines.append(tasks)
            if not pipelines:
                continue

            labels = ", ".join(f"{label} ({m.confidence:.2f})" for label, m in items)
            print(f"[DEBUG] Region {customer}: {len(pipelines)} item(s) -> {labels}")

            self._region_outstanding[customer] = len(pipelines)
            self._region_in_progress[customer] = True
            for tasks in pipelines:
                self._tasks.extend(tasks)

    def _tasks_for_label(self, customer: int, label: str) -> List[BotWorkItem]:
        """Build the task pipeline for one detected item."""
        if label == "soda":
            return self._create_soda_item(customer)
        if label == "fries":
            if self._fryer is None or len(self._fries_tray) == 0:
                if "fries" not in self._missing_point_warnings:
                    self._missing_point_warnings.add("fries")
                    print("[ASSET] Fryer / fries pickup slots not calibrated; skipping fries.")
                return []
            self._fries_demand += 1
            return self._create_fries_item(customer)
        if label.startswith("hotdog"):
            return self._create_hotdog_item(customer, with_ketchup=(label == "hotdog_ketchup"))

        toppings: List[Point] = []
        if label in ("burger_lettuce", "burger_both"):
            toppings += self._topping_source(profiles.LETTUCE_SOURCE, self._lettuce_source, "lettuce")
        if label in ("burger_tomato", "burger_both"):
            toppings += self._topping_source(profiles.TOMATO_SOURCE, self._tomato_source, "tomato")
        return self._create_burger_item(customer, toppings)

    def _topping_source(self, key: str, point: Optional[Point], name: str) -> List[Point]:
        """The topping's source point, or [] with a one-time warning if the user
        ordered a topped burger but never calibrated that ingredient."""
        if point is not None:
            return [point]
        if key not in self._missing_point_warnings:
            self._missing_point_warnings.add(key)
            print(f"[ASSET] {name.capitalize()} source not calibrated; serving without it.")
        return []

    # --- burger -------------------------------------------------------------

    def _create_burger_item(self, customer: int, toppings: List[Point]) -> List[BotWorkItem]:
        """One burger: cook a patty on a free pan, assemble on a free prep plate,
        drag on any toppings (lettuce/tomato), then deliver. ``slot`` carries the
        pan/plate this item claimed so its own tasks stay coordinated even when
        several burgers for the same customer run in parallel."""
        pans = self._burger_pans
        preps = self._burger_preps
        slot: Dict[str, int] = {}
        tag = f"B-r{customer}-{id(slot) & 0xfff:x}"

        def can_place_patty() -> bool:
            return self._mouse_free() and pans.has_free()

        def place_patty(item: BotWorkItem) -> None:
            i = pans.free_index()
            slot["pan"] = i
            pans.lock(i, self._burger_cook_time)
            self._move_and_drag(self._meat_location, pans.point(i))
            print(f"[BURGER] Region {customer} patty on pan {i + 1}.")
            item.end_time = 0

        pan = BotWorkItem(f"{tag}-pan", can_place_patty, place_patty, self)

        def wait_cook(item: BotWorkItem) -> None:
            item.end_time = pans.busy_until(slot["pan"])

        cook = BotWorkItem(f"{tag}-cook", lambda: True, wait_cook, self, [pan])

        def can_place_bun() -> bool:
            return self._mouse_free() and preps.has_free()

        def place_bun(item: BotWorkItem) -> None:
            j = preps.free_index()
            slot["prep"] = j
            preps.lock(j, 0)  # held until delivered; the bun lands on this plate
            self._move_and_click(self._bun_location)
            print(f"[BURGER] Region {customer} bun on plate {j + 1}.")
            item.end_time = 0

        # Prepare the bun/plate while the patty cooks (depends on the patty being
        # placed, not on the cook finishing) so the plate is ready the instant
        # the patty is done and it can be grabbed before it burns.
        bun = BotWorkItem(f"{tag}-bun", can_place_bun, place_bun, self, [pan])

        def drag_patty(item: BotWorkItem) -> None:
            self._move_and_drag(pans.point(slot["pan"]), preps.point(slot["prep"]))
            pans.release(slot["pan"])  # pan is free again once the patty is off it
            item.end_time = 0

        # High priority: a cooked patty burns if left on the pan, so grabbing it
        # (once cooked AND the plate is ready) beats starting/serving other items.
        drag = BotWorkItem(f"{tag}-drag", self._mouse_free, drag_patty, self, [cook, bun],
                           priority=PRIORITY_GRAB)

        tasks = [pan, cook, bun, drag]
        prev = drag
        for idx, source in enumerate(toppings):
            def apply_topping(item: BotWorkItem, source: Point = source) -> None:
                self._move_and_drag(source, preps.point(slot["prep"]))
                print(f"[BURGER] Region {customer} adding topping.")
                item.end_time = 0

            topping = BotWorkItem(f"{tag}-top{idx}", self._mouse_free, apply_topping, self, [prev])
            tasks.append(topping)
            prev = topping

        def deliver_action(item: BotWorkItem) -> None:
            self._move_and_drag(preps.point(slot["prep"]), self._customer_coords[customer])
            preps.release(slot["prep"])  # plate free once the burger is served
            print(f"[BURGER] Region {customer} delivering.")
            item.end_time = 0

        deliver = BotWorkItem(f"{tag}-deliver", self._mouse_free, deliver_action, self, [prev])

        def collect_action(item: BotWorkItem) -> None:
            self._move_and_click(self._customer_coords[customer])
            item.end_time = 0

        def finish(_item: BotWorkItem) -> None:
            self._complete_item(customer, "BURGER")

        collect = BotWorkItem(f"{tag}-collect", self._mouse_free, collect_action, self, [deliver], finish)
        tasks.append(deliver)
        tasks.append(collect)
        return tasks

    # --- soda ---------------------------------------------------------------

    def _create_soda_item(self, customer: int) -> List[BotWorkItem]:
        machines = self._soda_machines

        def can_serve_soda() -> bool:
            return self._mouse_free() and machines.has_free()

        def serve_soda(item: BotWorkItem) -> None:
            i = machines.free_index()
            # Machine auto-frees when its refill timer elapses (hold=False).
            machines.lock(i, self._soda_refill_time, hold=False)
            self._move_and_drag(machines.point(i), self._customer_coords[customer])
            print(f"[SODA] Region {customer} using soda {i + 1}.")
            item.end_time = 0

        soda = BotWorkItem(f"Soda-r{customer}-{id(machines) & 0xff:x}", can_serve_soda, serve_soda, self)

        def collect_action(item: BotWorkItem) -> None:
            self._move_and_click(self._customer_coords[customer])
            item.end_time = 0

        def finish(_item: BotWorkItem) -> None:
            self._complete_item(customer, "SODA")

        collect = BotWorkItem(f"Soda-r{customer}-collect", self._mouse_free, collect_action, self, [soda], finish)
        return [soda, collect]

    # --- fries --------------------------------------------------------------

    def _create_fries_item(self, customer: int) -> List[BotWorkItem]:
        """One fries serving. Production is shared (see ``_manage_fryer``); this
        pipeline just waits for a cooked fry to be sitting in the tray, then drags
        it from its slot to the customer. ``_fries_demand`` was already bumped by
        the caller so the fryer knows to cook."""
        tray = self._fries_tray
        tag = f"Fries-r{customer}-{id(object()) & 0xfff:x}"

        def can_serve() -> bool:
            return self._mouse_free() and tray.filled_index() is not None

        def serve(item: BotWorkItem) -> None:
            j = tray.filled_index()
            tray.take(j)  # this fry leaves its slot
            self._fries_demand = max(0, self._fries_demand - 1)
            self._move_and_drag(tray.point(j), self._customer_coords[customer])
            print(f"[FRIES] Region {customer} serving from slot {j + 1}.")
            item.end_time = 0

        serve_task = BotWorkItem(f"{tag}-serve", can_serve, serve, self)

        def collect_action(item: BotWorkItem) -> None:
            self._move_and_click(self._customer_coords[customer])
            item.end_time = 0

        def finish(_item: BotWorkItem) -> None:
            self._complete_item(customer, "FRIES")

        collect = BotWorkItem(f"{tag}-collect", self._mouse_free, collect_action, self, [serve_task], finish)
        return [serve_task, collect]

    # --- hotdog -------------------------------------------------------------

    def _create_hotdog_item(self, customer: int, with_ketchup: bool = False) -> List[BotWorkItem]:
        """One hotdog, mirroring the burger pipeline: a free grill (like a pan)
        and a free prep plate. With ``with_ketchup`` a ketchup drag is inserted
        after the dog is placed on the bun and before delivery."""
        grills = self._hotdog_grills
        preps = self._hotdog_preps
        slot: Dict[str, int] = {}
        tag = f"HD-r{customer}-{id(slot) & 0xfff:x}"

        def can_place_dog() -> bool:
            return self._mouse_free() and grills.has_free()

        def place_dog(item: BotWorkItem) -> None:
            i = grills.free_index()
            slot["grill"] = i
            grills.lock(i, self._hotdog_cook_time)
            self._move_and_drag(self._hotdog_uncooked, grills.point(i))
            print(f"[HOTDOG] Region {customer} dog on grill {i + 1}.")
            item.end_time = 0

        grill = BotWorkItem(f"{tag}-grill", can_place_dog, place_dog, self)

        def wait_cook(item: BotWorkItem) -> None:
            item.end_time = grills.busy_until(slot["grill"])

        cook = BotWorkItem(f"{tag}-cook", lambda: True, wait_cook, self, [grill])

        def can_place_bun() -> bool:
            return self._mouse_free() and preps.has_free()

        def place_bun(item: BotWorkItem) -> None:
            j = preps.free_index()
            slot["prep"] = j
            preps.lock(j, 0)  # held until delivered
            self._move_and_click(self._hotdog_bun)
            print(f"[HOTDOG] Region {customer} bun on plate {j + 1}.")
            item.end_time = 0

        # Prep the bun/plate while the dog grills (depends on the dog being on the
        # grill, not on it finishing) so it is ready to grab the moment it cooks.
        bun = BotWorkItem(f"{tag}-bun", can_place_bun, place_bun, self, [grill])

        def drag_dog(item: BotWorkItem) -> None:
            self._move_and_drag(grills.point(slot["grill"]), preps.point(slot["prep"]))
            grills.release(slot["grill"])
            item.end_time = 0

        # High priority: a cooked dog burns on the grill, so grab it (once cooked
        # AND the plate is ready) ahead of less urgent actions.
        drag_dog_item = BotWorkItem(f"{tag}-dragDog", self._mouse_free, drag_dog, self, [cook, bun],
                                    priority=PRIORITY_GRAB)

        prev = drag_dog_item
        tasks = [grill, cook, bun, drag_dog_item]
        if with_ketchup:
            def apply_ketchup(item: BotWorkItem) -> None:
                self._move_and_drag(self._ketchup_bottle, preps.point(slot["prep"]))
                print(f"[HOTDOG] Region {customer} adding ketchup.")
                item.end_time = 0

            ketchup = BotWorkItem(f"{tag}-ketchup", self._mouse_free, apply_ketchup, self, [prev])
            tasks.append(ketchup)
            prev = ketchup

        def deliver_action(item: BotWorkItem) -> None:
            self._move_and_drag(preps.point(slot["prep"]), self._customer_coords[customer])
            preps.release(slot["prep"])
            print(f"[HOTDOG] Region {customer} delivering.")
            item.end_time = 0

        deliver = BotWorkItem(f"{tag}-deliver", self._mouse_free, deliver_action, self, [prev])

        def collect_action(item: BotWorkItem) -> None:
            self._move_and_click(self._customer_coords[customer])
            item.end_time = 0

        def finish(_item: BotWorkItem) -> None:
            self._complete_item(customer, "HOTDOG")

        collect = BotWorkItem(f"{tag}-collect", self._mouse_free, collect_action, self, [deliver], finish)
        tasks.append(deliver)
        tasks.append(collect)
        return tasks

    # --- scheduler ----------------------------------------------------------

    def _update_tasks(self) -> None:
        for task in [t for t in self._tasks if t.state == RUNNING]:
            task.update()

        # Start pending tasks highest-priority first, so an urgent grab (a cooked
        # patty/dog that would burn) takes the mouse before less urgent actions.
        # The first mouse action locks the mouse, so lower-priority mouse tasks
        # naturally defer to the next tick.
        pending = [t for t in self._tasks if t.state == PENDING]
        pending.sort(key=lambda t: t.priority, reverse=True)
        for task in pending:
            if task.can_start():
                task.start()
                task.update()
