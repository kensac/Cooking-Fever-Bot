"""Screen automation: mouse movement, clicking, dragging, and capture.

Uses pyautogui for input and mss for fast screen grabs, matching the stack
used by the district-47 scripts. Heavy dependencies are imported lazily so
that ``--help`` and pure-UI code can run without them installed.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .geometry import Point, Region

# Drag tuning (macOS native path). A hold after mouse-down lets the game register
# the "pick up", the eased sweep keeps the item attached, and a settle before
# release registers the "drop". DRAG_STEPS is the smoothness (points along the
# path); DRAG_DURATION is how fast the cursor covers them. The hold/settle are
# stationary game-registration pauses (not movement), so they stay short and are
# what keeps items from dropping mid-drag. Raise DRAG_DURATION/DRAG_STEPS if
# items fall mid-drag; lower DRAG_DURATION to move faster (steps unchanged).
DRAG_HOLD = 0.05
DRAG_DURATION = 0.11
DRAG_STEPS = 36
DRAG_SETTLE = 0.04

_INSTALL_HINT = (
    "This feature needs pyautogui and mss.\n"
    "Install dependencies with:\n    pip install -r requirements.txt"
)


def _pyautogui():
    try:
        import pyautogui
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(_INSTALL_HINT) from exc
    # Moving into a screen corner should not abort a long automation run.
    pyautogui.FAILSAFE = False
    return pyautogui


def _open_mss():
    """Open a platform MSS screen-grab context.

    mss 10 renamed the ``mss.mss`` factory to ``mss.MSS``; fall back for older
    versions.
    """
    try:
        import mss
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(_INSTALL_HINT) from exc
    factory = getattr(mss, "MSS", None) or mss.mss
    return factory()


def position() -> Point:
    x, y = _pyautogui().position()
    return (int(x), int(y))


def move_to(target: Point, duration: float = 0.1) -> None:
    _pyautogui().moveTo(target[0], target[1], duration=max(0.0, duration))


def click(point: Point) -> None:
    pg = _pyautogui()
    pg.moveTo(point[0], point[1], duration=0.1)
    pg.mouseDown()
    time.sleep(0.03)
    pg.mouseUp()


def _quartz():
    try:
        import Quartz
    except ImportError:  # pragma: no cover - non-macOS
        return None
    return Quartz


def _post(q, event_type, x: float, y: float) -> None:
    event = q.CGEventCreateMouseEvent(None, event_type, (float(x), float(y)), q.kCGMouseButtonLeft)
    q.CGEventPost(q.kCGHIDEventTap, event)


def _mac_drag(q, source: Point, target: Point) -> None:
    """Smooth drag via Quartz, posting real LeftMouseDragged events.

    pyautogui moves the cursor with the button held but emits mouse-*moved*
    events, which many games (Cooking Fever included) read as "not dragging" and
    drop the item. Posting kCGEventLeftMouseDragged fixes that.
    """
    x0, y0 = float(source[0]), float(source[1])
    x1, y1 = float(target[0]), float(target[1])

    _post(q, q.kCGEventMouseMoved, x0, y0)
    time.sleep(0.03)
    _post(q, q.kCGEventLeftMouseDown, x0, y0)
    time.sleep(DRAG_HOLD)

    for i in range(1, DRAG_STEPS + 1):
        t = i / DRAG_STEPS
        ease = t * t * (3 - 2 * t)  # smoothstep: slow start/end, fast middle
        _post(q, q.kCGEventLeftMouseDragged, x0 + (x1 - x0) * ease, y0 + (y1 - y0) * ease)
        time.sleep(DRAG_DURATION / DRAG_STEPS)

    time.sleep(DRAG_SETTLE)
    _post(q, q.kCGEventLeftMouseUp, x1, y1)


def drag(source: Point, target: Point) -> None:
    if sys.platform == "darwin":
        q = _quartz()
        if q is not None:
            _mac_drag(q, source, target)
            return

    pg = _pyautogui()
    pg.moveTo(source[0], source[1], duration=0.1)
    pg.mouseDown()
    time.sleep(0.05)
    pg.moveTo(target[0], target[1], duration=0.2)
    pg.mouseUp()


def virtual_screen() -> Region:
    """The bounding box that spans every monitor, as (x, y, width, height)."""
    with _open_mss() as sct:
        monitor = sct.monitors[0]
        return (monitor["left"], monitor["top"], monitor["width"], monitor["height"])


# Set False to force the mss (logical-resolution) capture path everywhere.
HIGH_RES_CAPTURE = True


def _capture_quartz_bgr(region: Region):
    """Capture a logical region at native (Retina) resolution via Quartz.

    On a 2x display a logical WxH region comes back as a 2W x 2H BGR image, so
    template matching runs on sharper pixels. Returns None if Quartz is
    unavailable or the grab fails, so callers can fall back to mss. Callers must
    treat the result as scale-agnostic (its size may exceed the logical region).
    """
    try:
        import numpy as np
        import Quartz
    except ImportError:
        return None

    x, y, w, h = region
    rect = Quartz.CGRectMake(x, y, w, h)
    image = Quartz.CGDisplayCreateImageForRect(Quartz.CGMainDisplayID(), rect)
    if image is None:
        return None

    iw = Quartz.CGImageGetWidth(image)
    ih = Quartz.CGImageGetHeight(image)
    bytes_per_row = Quartz.CGImageGetBytesPerRow(image)
    provider = Quartz.CGImageGetDataProvider(image)
    data = Quartz.CGDataProviderCopyData(provider)
    buffer = np.frombuffer(bytes(data), dtype=np.uint8)

    # Rows are padded to a hardware-aligned stride, and the buffer can carry
    # trailing padding, so reshape by the real stride then trim to iw x ih.
    row_pixels = bytes_per_row // 4
    rows = buffer.size // bytes_per_row
    arr = buffer[: rows * bytes_per_row].reshape((rows, row_pixels, 4))
    # macOS gives BGRA byte order, so [:, :, :3] is already BGR for OpenCV.
    arr = arr[:ih, :iw, :3]
    return np.ascontiguousarray(arr)


def capture_bgr(region: Optional[Region] = None):
    """Grab a screen region as a BGR numpy array for OpenCV.

    On macOS this captures at native resolution (2x on Retina); the array may be
    larger than the logical region. Template matching derives the scale from the
    array size, so it stays correct.
    """
    import numpy as np

    if region is None:
        region = virtual_screen()

    if HIGH_RES_CAPTURE and sys.platform == "darwin":
        arr = _capture_quartz_bgr(region)
        if arr is not None:
            return arr

    box = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
    with _open_mss() as sct:
        shot = sct.grab(box)
    # mss returns BGRA; drop the alpha channel to get BGR for OpenCV.
    return np.array(shot)[:, :, :3]


def grab_image(region: Region):
    """Grab a screen region as a Pillow RGB image (for saving PNGs).

    Uses the same native-resolution path as capture_bgr on macOS so that saved
    template images are at the same scale as what matching captures.
    """
    from PIL import Image

    if HIGH_RES_CAPTURE and sys.platform == "darwin":
        arr = _capture_quartz_bgr(region)
        if arr is not None:
            return Image.fromarray(arr[:, :, ::-1])  # BGR -> RGB

    box = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
    with _open_mss() as sct:
        shot = sct.grab(box)
    return Image.frombytes("RGB", shot.size, shot.rgb)


def save_region(region: Region, directory: os.PathLike | str, prefix: str) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    path = directory / f"{prefix}_{stamp}.png"
    grab_image(region).save(path, format="PNG")
    return path
