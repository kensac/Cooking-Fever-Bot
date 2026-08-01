"""Restaurant profiles: calibrated points, order regions, and timings.

Ports the C# ProfileKeys / RestaurantProfile / ProfileStore trio. Profiles are
stored as JSON in the profiles/ directory. Keys and default coordinates match
the original so existing calibrations stay meaningful as references.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from . import paths
from .geometry import Point, Region

# --- Profile keys -----------------------------------------------------------

PLAY_BUTTON_STAGE_SELECT = "playButtonStageSelect"
PLAY_BUTTON_IN_STAGE = "playButtonInStage"
MEAT_LOCATION = "meatLocation"
FRYING_PAN_1 = "fryingPan1"
FRYING_PAN_2 = "fryingPan2"
# Optional extra burger pans (up to 4 total). A pan "exists" only if calibrated.
FRYING_PAN_3 = "fryingPan3"
FRYING_PAN_4 = "fryingPan4"
BURGER_POSITION = "burgerPosition"
# Optional extra burger prep/assembly plates (up to 3 total; plate 1 is
# BURGER_POSITION). A plate "exists" only if calibrated.
BURGER_PREP_2 = "burgerPrep2"
BURGER_PREP_3 = "burgerPrep3"
BUN_LOCATION = "bunLocation"
# Optional burger toppings, dragged onto the assembled burger before serving.
LETTUCE_SOURCE = "lettuceSource"
TOMATO_SOURCE = "tomatoSource"
SODA_MACHINE_1 = "sodaMachine1"
SODA_MACHINE_2 = "sodaMachine2"
# Optional 3rd soda position (3 total). Exists only once calibrated.
SODA_MACHINE_3 = "sodaMachine3"
HOTDOG_UNCOOKED = "hotdogUncooked"
HOTDOG_GRILL_1 = "hotdogGrill1"
HOTDOG_GRILL_2 = "hotdogGrill2"
# Optional extra hotdog grills (up to 4 total). A grill "exists" only if calibrated.
HOTDOG_GRILL_3 = "hotdogGrill3"
HOTDOG_GRILL_4 = "hotdogGrill4"
HOTDOG_BUN = "hotdogBun"
HOTDOG_PREP = "hotdogPrep"
# Optional extra hotdog prep plates (up to 3 total; plate 1 is HOTDOG_PREP).
HOTDOG_PREP_2 = "hotdogPrep2"
HOTDOG_PREP_3 = "hotdogPrep3"
KETCHUP_BOTTLE = "ketchupBottle"
# Fries: click the fryer to cook a batch (2 servings). Each cooked fry lands in
# its own pickup slot (like a soda machine slot) to be dragged to a customer.
# All optional; fries are active only once the fryer and at least one pickup
# slot are calibrated. Calibrate slots in the order the game fills them.
FRYER = "fryer"
FRIES_PICKUP_1 = "friesPickup1"
FRIES_PICKUP_2 = "friesPickup2"
FRIES_PICKUP_3 = "friesPickup3"
FRIES_PICKUP_4 = "friesPickup4"
CUSTOMER_1 = "customer1"
CUSTOMER_2 = "customer2"
CUSTOMER_3 = "customer3"
CUSTOMER_4 = "customer4"

ORDER_REGION_1 = "orderRegion1"
ORDER_REGION_2 = "orderRegion2"
ORDER_REGION_3 = "orderRegion3"
ORDER_REGION_4 = "orderRegion4"
COIN_REGION = "coinRegion"

BURGER_COOK_SECONDS = "burgerCookSeconds"
SODA_REFILL_SECONDS = "sodaRefillSeconds"
HOTDOG_COOK_SECONDS = "hotdogCookSeconds"
FRIES_COOK_SECONDS = "friesCookSeconds"


@dataclass(frozen=True)
class PointDefinition:
    key: str
    label: str


@dataclass(frozen=True)
class RegionDefinition:
    key: str
    label: str


@dataclass(frozen=True)
class TimingDefinition:
    key: str
    label: str
    default_value: float


POINT_DEFINITIONS: List[PointDefinition] = [
    PointDefinition(PLAY_BUTTON_STAGE_SELECT, "Stage Select Play Button"),
    PointDefinition(PLAY_BUTTON_IN_STAGE, "In-Stage Play Button"),
    PointDefinition(MEAT_LOCATION, "Meat Source"),
    PointDefinition(FRYING_PAN_1, "Frying Pan 1"),
    PointDefinition(FRYING_PAN_2, "Frying Pan 2"),
    PointDefinition(FRYING_PAN_3, "Frying Pan 3 (optional)"),
    PointDefinition(FRYING_PAN_4, "Frying Pan 4 (optional)"),
    PointDefinition(BURGER_POSITION, "Burger Prep Position 1"),
    PointDefinition(BURGER_PREP_2, "Burger Prep Position 2 (optional)"),
    PointDefinition(BURGER_PREP_3, "Burger Prep Position 3 (optional)"),
    PointDefinition(BUN_LOCATION, "Burger Bun Source"),
    PointDefinition(LETTUCE_SOURCE, "Lettuce Source (optional)"),
    PointDefinition(TOMATO_SOURCE, "Tomato Source (optional)"),
    PointDefinition(SODA_MACHINE_1, "Soda Machine 1"),
    PointDefinition(SODA_MACHINE_2, "Soda Machine 2"),
    PointDefinition(SODA_MACHINE_3, "Soda Machine 3 (optional)"),
    PointDefinition(HOTDOG_UNCOOKED, "Uncooked Hotdog Source"),
    PointDefinition(HOTDOG_GRILL_1, "Hotdog Grill 1"),
    PointDefinition(HOTDOG_GRILL_2, "Hotdog Grill 2"),
    PointDefinition(HOTDOG_GRILL_3, "Hotdog Grill 3 (optional)"),
    PointDefinition(HOTDOG_GRILL_4, "Hotdog Grill 4 (optional)"),
    PointDefinition(HOTDOG_BUN, "Hotdog Bun Source"),
    PointDefinition(HOTDOG_PREP, "Hotdog Prep Position 1"),
    PointDefinition(HOTDOG_PREP_2, "Hotdog Prep Position 2 (optional)"),
    PointDefinition(HOTDOG_PREP_3, "Hotdog Prep Position 3 (optional)"),
    PointDefinition(KETCHUP_BOTTLE, "Ketchup Bottle"),
    PointDefinition(FRYER, "Fryer (optional)"),
    PointDefinition(FRIES_PICKUP_1, "Fries Pickup Slot 1 (optional)"),
    PointDefinition(FRIES_PICKUP_2, "Fries Pickup Slot 2 (optional)"),
    PointDefinition(FRIES_PICKUP_3, "Fries Pickup Slot 3 (optional)"),
    PointDefinition(FRIES_PICKUP_4, "Fries Pickup Slot 4 (optional)"),
    PointDefinition(CUSTOMER_1, "Customer 1 Delivery"),
    PointDefinition(CUSTOMER_2, "Customer 2 Delivery"),
    PointDefinition(CUSTOMER_3, "Customer 3 Delivery"),
    PointDefinition(CUSTOMER_4, "Customer 4 Delivery"),
]

REGION_DEFINITIONS: List[RegionDefinition] = [
    RegionDefinition(ORDER_REGION_1, "Customer 1 Order Region"),
    RegionDefinition(ORDER_REGION_2, "Customer 2 Order Region"),
    RegionDefinition(ORDER_REGION_3, "Customer 3 Order Region"),
    RegionDefinition(ORDER_REGION_4, "Customer 4 Order Region"),
    RegionDefinition(COIN_REGION, "Coin / Money Collection Region"),
]

TIMING_DEFINITIONS: List[TimingDefinition] = [
    TimingDefinition(BURGER_COOK_SECONDS, "Burger cook time", 9.0),
    TimingDefinition(SODA_REFILL_SECONDS, "Soda refill time", 8.0),
    TimingDefinition(HOTDOG_COOK_SECONDS, "Hotdog cook time", 10.0),
    TimingDefinition(FRIES_COOK_SECONDS, "Fries cook time", 10.0),
]

_DEFAULT_POINTS: Dict[str, Point] = {
    PLAY_BUTTON_STAGE_SELECT: (524, 863),
    PLAY_BUTTON_IN_STAGE: (973, 942),
    MEAT_LOCATION: (1340, 928),
    FRYING_PAN_1: (1302, 814),
    FRYING_PAN_2: (1270, 711),
    BURGER_POSITION: (771, 712),
    BUN_LOCATION: (772, 846),
    SODA_MACHINE_1: (421, 694),
    SODA_MACHINE_2: (515, 694),
    HOTDOG_UNCOOKED: (1496, 904),
    HOTDOG_GRILL_1: (1446, 782),
    HOTDOG_GRILL_2: (1478, 685),
    HOTDOG_BUN: (963, 859),
    HOTDOG_PREP: (948, 721),
    KETCHUP_BOTTLE: (1080, 859),
    CUSTOMER_1: (507, 420),
    CUSTOMER_2: (860, 420),
    CUSTOMER_3: (1207, 420),
    CUSTOMER_4: (1552, 420),
}

_DEFAULT_REGIONS: Dict[str, Region] = {
    ORDER_REGION_1: (288, 140, 154, 262),
    ORDER_REGION_2: (634, 142, 149, 257),
    ORDER_REGION_3: (981, 140, 151, 263),
    ORDER_REGION_4: (1324, 143, 153, 261),
    # Wide strip over the customer counter where coins/tips appear after payment.
    COIN_REGION: (150, 340, 1250, 260),
}


# --- Profile model ----------------------------------------------------------


@dataclass
class RestaurantProfile:
    name: str = "Burger Shop"
    assets_directory: str = ""
    points: Dict[str, Point] = field(default_factory=dict)
    regions: Dict[str, Region] = field(default_factory=dict)
    timings: Dict[str, float] = field(default_factory=dict)
    # Pixels to aim the cursor *below* a drag's drop target. A grabbed item is
    # drawn offset above the cursor, so dropping lower makes it land on the
    # intended spot. Applies to every drag destination; pickups are unaffected.
    drop_offset_y: int = 0
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    file_path: str = ""

    @staticmethod
    def default() -> "RestaurantProfile":
        return RestaurantProfile(
            name="Burger Shop",
            assets_directory="",
            points=dict(_DEFAULT_POINTS),
            regions=dict(_DEFAULT_REGIONS),
            timings={d.key: d.default_value for d in TIMING_DEFINITIONS},
        )

    def get_point(self, key: str) -> Point:
        if key in self.points:
            return tuple(self.points[key])  # type: ignore[return-value]
        return _DEFAULT_POINTS[key]

    def has_point(self, key: str) -> bool:
        """True if ``key`` has been calibrated or has a built-in default.

        Optional stations (extra pans/grills/prep plates, toppings) have no
        default, so this returns True only once the user calibrates them - which
        is how the bot decides a station "exists".
        """
        return key in self.points or key in _DEFAULT_POINTS

    def try_point(self, key: str) -> Optional[Point]:
        """The calibrated/default point, or None if the station is not set."""
        return self.get_point(key) if self.has_point(key) else None

    def get_region(self, key: str) -> Region:
        if key in self.regions:
            return tuple(self.regions[key])  # type: ignore[return-value]
        return _DEFAULT_REGIONS[key]

    def get_timing(self, key: str, fallback: float) -> float:
        value = self.timings.get(key)
        return value if value and value > 0 else fallback

    def set_point(self, key: str, point: Point) -> None:
        self.points[key] = (int(point[0]), int(point[1]))
        self.touch()

    def set_region(self, key: str, region: Region) -> None:
        self.regions[key] = tuple(int(v) for v in region)  # type: ignore[assignment]
        self.touch()

    def set_timing(self, key: str, seconds: float) -> None:
        self.timings[key] = max(0.1, float(seconds))
        self.touch()

    def set_drop_offset(self, pixels: int) -> None:
        self.drop_offset_y = int(pixels)
        self.touch()

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat()

    def clone(self) -> "RestaurantProfile":
        return RestaurantProfile(
            name=self.name,
            assets_directory=self.assets_directory,
            points=dict(self.points),
            regions=dict(self.regions),
            timings=dict(self.timings),
            drop_offset_y=self.drop_offset_y,
            updated_at=self.updated_at,
            file_path=self.file_path,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "assetsDirectory": self.assets_directory,
            "points": {k: {"x": v[0], "y": v[1]} for k, v in self.points.items()},
            "regions": {
                k: {"x": v[0], "y": v[1], "width": v[2], "height": v[3]}
                for k, v in self.regions.items()
            },
            "timings": dict(self.timings),
            "dropOffsetY": self.drop_offset_y,
            "updatedAt": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "RestaurantProfile":
        points = {
            k: (int(v["x"]), int(v["y"]))
            for k, v in (data.get("points") or {}).items()
        }
        regions = {
            k: (int(v["x"]), int(v["y"]), int(v["width"]), int(v["height"]))
            for k, v in (data.get("regions") or {}).items()
        }
        timings = {k: float(v) for k, v in (data.get("timings") or {}).items()}
        return RestaurantProfile(
            name=data.get("name") or "Burger Shop",
            assets_directory=data.get("assetsDirectory") or "",
            points=points,
            regions=regions,
            timings=timings,
            drop_offset_y=int(data.get("dropOffsetY") or 0),
            updated_at=data.get("updatedAt") or datetime.now().isoformat(),
        )


# --- Profile store ----------------------------------------------------------


def _merge_missing_defaults(profile: RestaurantProfile) -> None:
    defaults = RestaurantProfile.default()
    for key, value in defaults.points.items():
        profile.points.setdefault(key, value)
    for key, value in defaults.regions.items():
        profile.regions.setdefault(key, value)
    for key, value in defaults.timings.items():
        profile.timings.setdefault(key, value)
    if not profile.name.strip():
        profile.name = defaults.name


def _sanitize_file_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name).strip()
    return cleaned or "profile"


def path_for_name(name: str) -> Path:
    paths.ensure_directories()
    return paths.profiles_directory() / f"{_sanitize_file_name(name)}.json"


def load_or_default(path: Optional[str]) -> RestaurantProfile:
    if not path or not Path(path).is_file():
        profile = RestaurantProfile.default()
        profile.file_path = str(path_for_name(profile.name))
        return profile

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        profile = RestaurantProfile.from_dict(data)
        _merge_missing_defaults(profile)
        profile.file_path = str(Path(path).resolve())
        return profile
    except (OSError, ValueError, KeyError):
        profile = RestaurantProfile.default()
        profile.file_path = str(Path(path).resolve())
        return profile


def save(profile: RestaurantProfile) -> None:
    paths.ensure_directories()
    _merge_missing_defaults(profile)
    if not profile.file_path.strip():
        profile.file_path = str(path_for_name(profile.name))
    profile.touch()
    Path(profile.file_path).write_text(
        json.dumps(profile.to_dict(), indent=2), encoding="utf-8"
    )


def create(name: str) -> RestaurantProfile:
    profile = RestaurantProfile.default()
    profile.name = name.strip() or "New Profile"
    profile.file_path = str(path_for_name(profile.name))
    save(profile)
    return profile


def delete(profile: RestaurantProfile) -> None:
    if profile.file_path and Path(profile.file_path).is_file():
        Path(profile.file_path).unlink()


def ensure_default_profile() -> None:
    paths.ensure_directories()
    default_path = path_for_name("Burger Shop")
    if default_path.is_file():
        return
    profile = RestaurantProfile.default()
    profile.file_path = str(default_path)
    save(profile)


def load_all() -> List[RestaurantProfile]:
    paths.ensure_directories()
    ensure_default_profile()
    return [
        load_or_default(str(p))
        for p in sorted(paths.profiles_directory().glob("*.json"))
    ]
