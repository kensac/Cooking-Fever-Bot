"""Small geometry helpers.

Points are ``(x, y)`` tuples and regions are ``(x, y, width, height)`` tuples,
in absolute screen coordinates.
"""
from __future__ import annotations

from typing import NamedTuple, Tuple

Point = Tuple[int, int]
Region = Tuple[int, int, int, int]


class Match(NamedTuple):
    """A located template: its screen bounds and match confidence (0-1)."""

    bounds: Region
    confidence: float

    @property
    def center(self) -> Point:
        return center(self.bounds)


def center(region: Region) -> Point:
    x, y, w, h = region
    return (x + w // 2, y + h // 2)


def region_from_points(a: Point, b: Point) -> Region:
    left = min(a[0], b[0])
    top = min(a[1], b[1])
    width = abs(a[0] - b[0])
    height = abs(a[1] - b[1])
    return (left, top, width, height)


def centered_region(point: Point, size: int) -> Region:
    return (point[0] - size // 2, point[1] - size // 2, size, size)
