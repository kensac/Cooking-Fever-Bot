"""Template matching using OpenCV normalized cross-correlation.

Replaces the C# hand-rolled pixel-difference scan with cv2.matchTemplate.
``locate`` returns the best match on screen above a confidence threshold, or None.

Order icons render slightly smaller or larger depending on how many items are in
the order, and cv2.matchTemplate is not scale-invariant, so each template is
matched across a range of sizes (multi-scale) and the best score is kept. Widen
SCALE_MIN/SCALE_MAX or raise SCALE_STEPS if sizes vary more than expected.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from . import automation
from .geometry import Match, Region

SCALE_MIN = 0.8
SCALE_MAX = 1.2
SCALE_STEPS = 9


def _scales() -> List[float]:
    if SCALE_STEPS <= 1:
        return [1.0]
    step = (SCALE_MAX - SCALE_MIN) / (SCALE_STEPS - 1)
    return [round(SCALE_MIN + i * step, 4) for i in range(SCALE_STEPS)]


def _best_scaled(source, template, scales: List[float]):
    """Best (score, (x, y), w, h) of ``template`` vs ``source`` across scales.

    ``w``/``h`` are the matched template size in source pixels at the winning
    scale. Returns None if the template never fits the source.
    """
    import cv2

    sh, sw = source.shape[:2]
    best = None
    for scale in scales:
        if abs(scale - 1.0) < 1e-9:
            resized = template
        else:
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            resized = cv2.resize(template, None, fx=scale, fy=scale, interpolation=interp)
        th, tw = resized.shape[:2]
        if th > sh or tw > sw or th < 4 or tw < 4:
            continue
        result = cv2.matchTemplate(source, resized, cv2.TM_CCOEFF_NORMED)
        _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)
        if best is None or max_val > best[0]:
            best = (float(max_val), max_loc, tw, th)
    return best


def _to_bounds(region: Region, source_shape, loc, tw: int, th: int) -> Region:
    """Convert a source-pixel match to logical screen bounds (x, y, w, h)."""
    sh, sw = source_shape[:2]
    scale_x = sw / region[2] if region[2] else 1.0
    scale_y = sh / region[3] if region[3] else 1.0
    left = region[0] + loc[0] / scale_x
    top = region[1] + loc[1] / scale_y
    return (int(round(left)), int(round(top)), int(round(tw / scale_x)), int(round(th / scale_y)))


def locate(
    template_path: str | Path,
    region: Optional[Region] = None,
    confidence: float = 0.8,
    multiscale: bool = False,
) -> Optional[Match]:
    """Locate a single template. ``multiscale`` searches a range of sizes; leave
    it off for fixed-size UI (restart button, coins) to stay fast."""
    import cv2

    template = cv2.imread(str(Path(template_path)), cv2.IMREAD_COLOR)
    if template is None:
        return None

    search_region = region if region is not None else automation.virtual_screen()
    source = automation.capture_bgr(search_region)

    best = _best_scaled(source, template, _scales() if multiscale else [1.0])
    if best is None:
        return None
    score, loc, tw, th = best
    if score < confidence:
        return None

    return Match(bounds=_to_bounds(search_region, source.shape, loc, tw, th), confidence=score)


def _iou(a: Region, b: Region) -> float:
    """Intersection-over-union of two (x, y, w, h) boxes."""
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx1, by1 = bx0 + bw, by0 + bh
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def find_items(
    candidates: List[Tuple[str, Path]],
    region: Region,
    confidence: float = 0.8,
    max_items: int = 4,
    overlap: float = 0.4,
) -> List[Tuple[str, Match]]:
    """Find every distinct order icon inside ``region`` (up to ``max_items``).

    Unlike ``best_match`` (one icon per bubble), a single customer ticket can now
    show several items anywhere in the region, possibly duplicated and each at a
    *different* size (icons shrink as more fit in the bubble). So every template
    is matched at every scale, and from each scale's correlation map we pull out
    every peak above ``confidence`` (suppressing a template-sized neighbourhood
    around each so one spot is not counted twice at that scale). All of those
    candidates - across templates and scales - are then run through a single
    greedy non-maximum suppression by IoU. That does double duty: the same
    physical icon found at neighbouring scales collapses to its best hit, and
    when look-alike templates (burger vs burger+lettuce, hotdog vs
    hotdog+ketchup) fire on the same icon, the highest-scoring label wins the
    slot - while two genuinely separate items keep their own slots even if their
    sizes differ.

    Returns ``(label, match)`` pairs sorted by descending score.
    """
    import cv2

    source = automation.capture_bgr(region)
    sh, sw = source.shape[:2]
    detections: List[Tuple[float, str, Region]] = []

    for label, path in candidates:
        template_img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if template_img is None:
            continue
        for scale in _scales():
            if abs(scale - 1.0) < 1e-9:
                resized = template_img
            else:
                interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                resized = cv2.resize(template_img, None, fx=scale, fy=scale, interpolation=interp)
            rh, rw = resized.shape[:2]
            if rh > sh or rw > sw or rh < 4 or rw < 4:
                continue
            result = cv2.matchTemplate(source, resized, cv2.TM_CCOEFF_NORMED)
            for _ in range(max_items):
                _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)
                if max_val < confidence:
                    break
                detections.append((float(max_val), label, _to_bounds(region, source.shape, max_loc, rw, rh)))
                # Blank a template-sized box so the next peak is a different icon.
                x0 = max(0, max_loc[0] - rw // 2)
                y0 = max(0, max_loc[1] - rh // 2)
                x1 = min(result.shape[1], max_loc[0] + rw // 2)
                y1 = min(result.shape[0], max_loc[1] + rh // 2)
                result[y0:y1, x0:x1] = -1.0

    detections.sort(key=lambda d: d[0], reverse=True)
    kept: List[Tuple[float, str, Region]] = []
    for det in detections:
        if all(_iou(det[2], k[2]) < overlap for k in kept):
            kept.append(det)
        if len(kept) >= max_items:
            break
    return [(label, Match(bounds=bounds, confidence=score)) for score, label, bounds in kept]


def best_match(
    candidates: List[Tuple[str, Path]],
    region: Region,
    confidence: float = 0.8,
    margin: float = 0.0,
) -> Optional[Tuple[str, Match, List[Tuple[str, float]]]]:
    """Pick the best-scoring template among several look-alike candidates.

    Captures ``region`` once and scores every candidate against it (each matched
    multi-scale), then returns the single highest-scoring one (argmax) that clears
    ``confidence`` - so near-identical icons like hotdog vs hotdog-with-ketchup are
    disambiguated by whichever correlates best, and size differences from the item
    count are absorbed by the per-template scale search.

    ``margin`` optionally requires the winner to beat the runner-up by that much;
    if it does not, the match is treated as too ambiguous and None is returned.

    Returns ``(label, match, scores)`` where ``scores`` is every candidate's best
    score (for logging/tuning), or None if nothing clears the bar.
    """
    import cv2

    source = automation.capture_bgr(region)

    scored: List[Tuple[str, float, Region]] = []
    for label, path in candidates:
        template = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if template is None:
            continue
        best = _best_scaled(source, template, _scales())
        if best is None:
            continue
        score, loc, tw, th = best
        scored.append((label, score, _to_bounds(region, source.shape, loc, tw, th)))

    if not scored:
        return None

    scored.sort(key=lambda s: s[1], reverse=True)
    scores = [(label, score) for label, score, _ in scored]
    best_label, best_score, best_bounds = scored[0]
    if best_score < confidence:
        return None
    if len(scored) > 1 and (best_score - scored[1][1]) < margin:
        return None
    return best_label, Match(bounds=best_bounds, confidence=best_score), scores
