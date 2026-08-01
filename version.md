# Version

Current version: 2.2.0

Date: 2026-08-01

Notes:

- Added a configurable drop Y-offset. A grabbed item renders offset above the
  cursor, so a new per-profile `dropOffsetY` (pixels) aims the cursor that many
  pixels *lower* than every drag's drop target to land the item correctly.
  Applies uniformly to all drag destinations (patty->plate, plate->customer,
  toppings, soda/fries serving, meat->pan, etc.); pickups and plain clicks are
  unaffected. Set it in the Calibrate dialog's Timings tab ("Drop offset
  (pixels lower)"). Defaults to 0 (no change) and is a single global value for
  now - if one value doesn't suit every action we can add per-point offsets.
- Added a 3rd soda position (`sodaMachine3`, optional) - up to 3 total.
- Perishable-aware scheduling. Burgers/hotdogs burn if not taken off the heat
  when done, but fries/sodas cost nothing to over-prepare, so the bot now:
  (1) gives the "grab the cooked patty/dog off the pan/grill" step top mouse
  priority (`PRIORITY_GRAB`) via a new priority field on work items, so it beats
  starting or serving anything else; (2) prepares each burger/hotdog bun+plate
  *while* the patty/dog cooks (the bun step now depends on the patty being
  placed, not on the cook finishing, and the grab depends on both cook and
  bun), so the plate is ready the instant it's cooked; and (3) fries the fryer
  preemptively to keep the tray topped up during lulls (not just on demand),
  while never firing the fryer while a burger/hotdog is on the heat so the grab
  is never blocked.
- Added fries. Unlike the other items, fries come from one shared fryer: a
  `fryer` click cooks a batch of `FRIES_PER_BATCH` (2) servings after
  `friesCookSeconds`, and each cooked fry lands in its own pickup slot
  (`friesPickup1..4`, like soda machine slots). Production is loop-managed
  (`_manage_fryer`/`_reconcile_fryer`, a `FriesTray`): the bot cooks a fresh
  batch only when outstanding fry orders exceed the fries ready plus those
  cooking and the tray has room, serving ready fries before cooking more so
  batches stay full and a leftover just waits in its slot. A `fries.png` order
  icon drives it; each fries order drags one ready fry from its slot to the
  customer. All fries points are optional - fries are active only once the
  fryer and at least one pickup slot are calibrated (unset = does not exist).
- Roughly 2x faster cursor movement. Halved the drag sweep (`DRAG_DURATION`
  0.22->0.11) and the click/move `moveTo` durations while keeping `DRAG_STEPS`
  at 36, so motion stays as smooth but covers the path twice as fast. The
  stationary pickup/drop pauses (`DRAG_HOLD`/`DRAG_SETTLE`) are kept short but
  intact so items still don't drop mid-drag. Per-action mouse locks dropped to
  0.3s to match, improving scheduler throughput.
- Multiple items per ticket: a customer order can now contain up to 4 items
  (any mix of burgers/sodas/hotdogs). Detection finds every icon in a region
  (`template.find_items`) instead of one, builds an independent task pipeline
  per item, and the region only reopens for a new order once all of its items
  are served (`_region_outstanding`). Icons are matched at every scale and
  deduped by IoU non-maximum suppression, so items shown at different sizes in
  the same bubble (and look-alike variants) are each detected correctly.
- Up to 4 burger pans and 4 hotdog grills, and up to 3 prep/assembly plates
  each, replacing the fixed 2 pans / 2 grills / 1 prep. Stations are now an
  interchangeable `StationPool`; a station "exists" only once it is calibrated,
  so the pool size is however many you set up (uncalibrated = does not exist).
  New optional points: Frying Pan 3/4, Hotdog Grill 3/4, Burger Prep Position
  2/3, Hotdog Prep Position 2/3. Pans/grills free up as soon as the patty/dog
  is dragged off (more throughput); prep plates free on delivery.
- Burger toppings: lettuce, tomato, or both, mirroring the hotdog-ketchup flow.
  An order icon (`burger-lettuce.png`, `burger-tomato.png`,
  `burger-lettuce-tomato.png`) triggers a burger pipeline that drags the new
  `Lettuce Source` / `Tomato Source` points onto the assembled burger before
  serving. Uncalibrated topping sources are skipped with a one-time warning.
  The new order icons are listed in the Asset Manager's Bot Templates panel.
- Asset Manager now has a "Bot Templates" panel that lists every image the bot
  needs by a friendly name (burger/soda/hotdog/hotdog+ketchup order, coins,
  restart 1/2) with a live thumbnail and set/missing status. Each has a "Replace
  with Screenshot" button that captures a live region and saves it straight to
  the correct filename - no more manually naming or copying files into assets/.
  The required-template list is the single source of truth in
  `gui/assets.py:REQUIRED_TEMPLATES` (kept in sync with bot.py).
- Fixed a macOS hard crash (SIGTRAP) caused by pynput's keyboard hook running
  inside the GUI process. Capture overlays now cancel via right-click and use no
  keyboard hook. The bot keeps global s/p/gg hotkeys (they work when the game is
  focused) because it runs as its own GUI-less process, where pynput is safe; a
  terminal reader is the fallback if pynput is unavailable.
- Capture overlay no longer uses native fullscreen (which spawned a new macOS
  Space); it is now a borderless screen-sized window.
- Added persisted dashboard settings (last profile, confidence, dry-run) in
  settings.json so the app reopens as it was left. Profiles/calibration already
  persisted in profiles/.
- Added Pillow for PNG capture output.
- Made order-icon detection scale-tolerant: icons render slightly smaller/larger
  depending on the item count, so each template is now matched multi-scale
  (0.8-1.2x, `template.SCALE_*`) and the best size wins. Fixed-size UI (restart,
  coins) stays single-scale for speed via `locate(multiscale=...)`.
- The bot process is now launched unbuffered (`-u`/PYTHONUNBUFFERED) so its logs
  (including per-detection scores) stream to the dashboard live.
- Improved order-icon detection for look-alikes (hotdog vs hotdog-with-ketchup):
  detection now scores all order templates against one capture of the region and
  picks the highest (argmax) instead of the first over the threshold, and logs
  every candidate's score. Added `template.best_match`.
- Added a ketchup hotdog variant: a `hotdog-ketchup.png` order icon triggers a
  hotdog pipeline that drags the new `Ketchup Bottle` point onto the prepped dog
  before delivery.
- Enabled native high-resolution screen capture on macOS (Quartz, 2x on Retina)
  for sharper template matching; matching is now scale-agnostic and converts
  matches back to logical click coordinates. Toggle with HIGH_RES_CAPTURE in
  automation.py. Recapture templates through the app so they match the scale.
- Reworked hotdogs to cook on two grills in parallel, mirroring the two-pan
  burger pipeline (grill 1 / grill 2 with a single prep slot). Replaced the
  `Hotdog Grill` + `Hotdog Warmer` points with `Hotdog Grill 1` / `Hotdog Grill 2`
  and removed the warmer-maintenance logic.
- Sped up drag-and-drop (~0.45s, was ~0.84s) via shorter DRAG_* timings now that
  native Quartz dragged-events are reliable; lowered the per-drag mouse lock to match.
- Added automatic coin/tip collection: a new `Coin / Money Collection Region`
  (calibratable) is scanned every loop for a `coins.png` template, and any coins
  found are clicked to collect payment after deliveries.
- Fixed drag-and-drop dropping items mid-drag on macOS: drags now post native
  Quartz `LeftMouseDragged` events (eased sweep with a hold after mouse-down and a
  settle before release) instead of pyautogui's mouse-moved events, which games
  read as "not dragging". Tunable via DRAG_* constants in automation.py; pyautogui
  remains the fallback on other platforms.

## 2.0.0

Date: 2026-07-18

Notes:

- Rewrote the application from C#/.NET into a cross-platform Python package
  (`cooking_fever/`) that runs on macOS, Linux, and Windows.
- Ported the full order-scheduling bot (burgers, sodas, hotdogs, and hotdog
  warmer maintenance) with its dependency-graph task scheduler intact.
- Replaced the hand-rolled pixel-difference template matcher with OpenCV
  normalized cross-correlation via `cv2.matchTemplate`.
- Reimplemented the GUI in tkinter: dashboard, calibration wizard, asset
  manager, capture overlay, action monitor, region/snapshot tools, and todo.
- Switched screen input/capture to pyautogui + mss and global hotkeys/hooks to
  pynput, matching the stack used by the district-47 scripts.
- Kept the legacy C#/.NET sources under `src/` for reference.

## Previous (C#)

- 1.0.1 (2026-05-20): C#/.NET GUI dashboard with profiles, calibration, asset
  management, dry-run bot execution, and persistent logs.
